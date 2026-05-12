"""Anthropic-interface wrapper around a vLLM-on-Dispersed endpoint.

`llm_call()` in utilities/__init__.py uses one specific shape:

    with client.messages.stream(model=..., max_tokens=..., messages=[...], system=...) as s:
        return s.get_final_message().content[0].text

We mimic that shape exactly so the rest of the pipeline can stay
unchanged. Underneath, we call the vLLM server's OpenAI-compatible
/v1/chat/completions endpoint via the openai SDK.

Job management is lazy and per-model:
  - First time llm_call() asks for model X, we look up X in `recipe_map`
    to find the recipe UUID, then either reuse an existing RUNNING
    PERSISTENT job or start a new one. The endpoint URL is cached for
    the lifetime of this client instance.
  - Subsequent calls for model X reuse the cached endpoint with no new
    Dispersed API traffic.

Fallback:
  - If a model's job can't be discovered/started AND `fallback_client`
    is provided, we delegate to it transparently. This lets the user
    set DISPERSED_FALLBACK=openrouter and have the pipeline keep going
    when Dispersed is down.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from utilities.dispersed.api_client import DispersedAPIClient, DispersedAPIError

log = logging.getLogger("pipeline")


@dataclass
class _JobEndpoint:
    """Cached job state per model."""
    endpoint_url: str
    job_uuid: str


# ── Anthropic-shaped response stand-ins ─────────────────────────────────────
#
# llm_call() drills into `stream.get_final_message().content[0].text`. We
# build the smallest possible object graph that satisfies that path.

class _TextBlock:
    __slots__ = ("text",)

    def __init__(self, text: str):
        self.text = text


class _Message:
    __slots__ = ("content",)

    def __init__(self, text: str):
        self.content = [_TextBlock(text)]


class _Stream:
    """Context manager mimicking anthropic's MessageStreamManager."""

    def __init__(self, completion_fn, kwargs: dict):
        self._completion_fn = completion_fn
        self._kwargs = kwargs
        self._final: _Message | None = None

    def __enter__(self) -> "_Stream":
        return self

    def __exit__(self, *_exc) -> None:
        return None

    def get_final_message(self) -> _Message:
        if self._final is None:
            text = self._completion_fn(self._kwargs)
            self._final = _Message(text)
        return self._final


# ── Messages namespace (mirrors anthropic.Anthropic.messages) ───────────────
class _Messages:
    def __init__(self, parent: "DispersedLLMClient"):
        self._parent = parent

    def stream(self, **kwargs) -> _Stream:
        return _Stream(self._parent._complete, kwargs)


# ── Main client ─────────────────────────────────────────────────────────────
class DispersedLLMClient:
    """Talks to Dispersed-hosted vLLM endpoints with an Anthropic-shaped API.

    Constructor args:
      recipe_map: {model_name: recipe_uuid}. e.g.
                  {"Qwen/Qwen3-8B": "<fast-recipe-uuid>",
                   "Qwen/Qwen3-32B": "<strong-recipe-uuid>"}
      api_client: an authenticated DispersedAPIClient
      fallback_client: optional anthropic-shaped client used when a
                      Dispersed job can't be brought up. Should expose the
                      same `.messages.stream(...)` shape.
      job_timeout: how long to wait for a new job to reach RUNNING (sec)
    """

    def __init__(
        self,
        recipe_map: dict[str, str],
        api_client: DispersedAPIClient,
        *,
        fallback_client: Any | None = None,
        job_timeout: float = 600.0,
    ):
        if not recipe_map:
            raise ValueError(
                "DispersedLLMClient requires recipe_map with at least one "
                "{model_name: recipe_uuid} entry"
            )
        self._recipe_map = dict(recipe_map)
        self._api = api_client
        self._fallback = fallback_client
        self._job_timeout = job_timeout
        # Per-model endpoint cache + a lock so concurrent worker threads
        # don't double-start a job for the same model.
        self._endpoints: dict[str, _JobEndpoint] = {}
        self._endpoint_locks: dict[str, threading.Lock] = {
            m: threading.Lock() for m in self._recipe_map
        }
        # OpenAI client is reusable across endpoints — we set base_url
        # per-request to route correctly.
        # vLLM doesn't require an API key but the openai SDK insists on one.
        self._openai = OpenAI(api_key="not-needed", base_url="http://placeholder")

        # Public Anthropic-shaped namespace
        self.messages = _Messages(self)

    # ── Job discovery / startup (lazy, per-model) ──────────────────────────
    def _ensure_endpoint(self, model: str) -> _JobEndpoint:
        """Return cached endpoint for `model`, or discover/start one."""
        if (cached := self._endpoints.get(model)):
            return cached
        recipe_uuid = self._recipe_map.get(model)
        if not recipe_uuid:
            raise DispersedAPIError(
                0,
                f"no Dispersed recipe configured for model {model!r}; "
                f"set DISPERSED_RECIPE_FAST / DISPERSED_RECIPE_STRONG or "
                f"adjust MODEL_FAST / MODEL_STRONG to match",
                code="NO_RECIPE",
            )

        lock = self._endpoint_locks.setdefault(model, threading.Lock())
        with lock:
            # Re-check after acquiring the lock — another thread may have
            # started the job while we waited.
            if (cached := self._endpoints.get(model)):
                return cached

            # 1. Try to reuse a RUNNING job for this recipe.
            running = self._api.list_jobs(
                recipe_uuid=recipe_uuid, status="RUNNING", limit=10,
            )
            url = None
            job_uuid = None
            for job in running:
                if (url := self._api.extract_endpoint(job)):
                    job_uuid = job.get("uuid") or job.get("id")
                    log.info(
                        f"Dispersed: reusing running job {str(job_uuid)[:8]}… "
                        f"for model {model!r}"
                    )
                    break

            # 2. Otherwise create one and wait for it to start.
            if not url:
                log.info(
                    f"Dispersed: no running job found for {model!r}; "
                    f"starting one from recipe {recipe_uuid[:8]}…"
                )
                created = self._api.create_job(recipe_uuid, task_type="PERSISTENT")
                job_uuid = created.get("uuid") or created.get("id")
                if not job_uuid:
                    raise DispersedAPIError(
                        0, f"create_job returned no uuid: {created!r}",
                        code="NO_JOB_UUID",
                    )
                job = self._api.wait_for_running(
                    job_uuid, timeout=self._job_timeout,
                )
                url = self._api.extract_endpoint(job)
                if not url:
                    raise DispersedAPIError(
                        0,
                        f"job {job_uuid} is RUNNING but no endpoint URL "
                        f"could be extracted from response",
                        code="NO_ENDPOINT",
                    )

            # Normalize: openai SDK wants the URL to end at /v1
            url = url.rstrip("/")
            if not url.endswith("/v1"):
                url = url + "/v1"

            ep = _JobEndpoint(endpoint_url=url, job_uuid=str(job_uuid))
            self._endpoints[model] = ep
            log.info(f"Dispersed: model {model!r} → {ep.endpoint_url}")
            return ep

    # ── Completion call ────────────────────────────────────────────────────
    def _complete(self, kwargs: dict) -> str:
        """Run a single chat completion. Falls back if Dispersed is down."""
        model = kwargs["model"]
        try:
            ep = self._ensure_endpoint(model)
        except (DispersedAPIError, TimeoutError) as e:
            if self._fallback is None:
                raise
            log.warning(
                f"Dispersed unavailable for {model!r} ({e}); "
                f"falling back to {type(self._fallback).__name__}"
            )
            return self._fallback_complete(kwargs)

        oai_messages = _to_openai_messages(
            messages=kwargs["messages"],
            system=kwargs.get("system"),
        )
        try:
            resp = self._openai.with_options(base_url=ep.endpoint_url).chat.completions.create(
                model=model,
                messages=oai_messages,
                max_tokens=kwargs.get("max_tokens", 1024),
            )
        except Exception as e:
            if self._fallback is None:
                raise
            log.warning(
                f"Dispersed call failed for {model!r} ({e}); "
                f"falling back."
            )
            return self._fallback_complete(kwargs)

        choice = resp.choices[0]
        return choice.message.content or ""

    def _fallback_complete(self, kwargs: dict) -> str:
        """Delegate to the fallback client using the same Anthropic-shaped API."""
        with self._fallback.messages.stream(**kwargs) as s:
            msg = s.get_final_message()
            return msg.content[0].text


# ── Helpers ─────────────────────────────────────────────────────────────────
def _to_openai_messages(
    messages: list[dict], system: str | None = None,
) -> list[dict]:
    """Convert Anthropic-style messages to OpenAI chat format.

    Anthropic carries the system prompt as a top-level field; OpenAI puts
    it as a first 'system' message in the list.
    """
    out: list[dict] = []
    if system:
        out.append({"role": "system", "content": system})
    for m in messages:
        out.append({"role": m["role"], "content": m["content"]})
    return out
