"""Shared utilities for the drug mention pipeline."""
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
# Load .env from project root. override=False so explicitly-exported
# env vars always win over .env file values. Root is the single source
# of truth; src/.env is a fallback only if root doesn't exist.
_root_env = Path(__file__).parent.parent.parent / ".env"
_src_env = Path(__file__).parent.parent / ".env"
if _root_env.exists():
    load_dotenv(_root_env, override=False)
elif _src_env.exists():
    load_dotenv(_src_env, override=False)

import anthropic
import httpx  # anthropic's transport; TransportError covers the mid-stream drops

# ── Output file names ────────────────────────────────────────────────────────
TAGGED_MENTIONS = "tagged_mentions.json"
CANONICALIZED_MENTIONS = "canonicalized_mentions.json"


# ── Pipeline Config ──────────────────────────────────────────────────────────
@dataclass
class PipelineConfig:
    """Shared configuration for all pipeline steps."""
    client: anthropic.Anthropic
    output_dir: Path
    db_path: Path
    limit: int = 100
    reclassify: bool = False
    max_upstream_chars: int | None = None  # None = unlimited; truncate upstream comment text to N chars
    max_upstream_depth: int | None = None  # None = unlimited; max upstream hops for drug context
    workers: int = 20                      # ThreadPoolExecutor workers; 1 = sequential
    drug: str | None = None                # If set, extract + canonicalize + classify operate on this drug and its synonyms only
    drug_aliases: list[str] | None = None  # If set, use as the alias list directly and skip LLM alias lookup

    def __post_init__(self):
        if self.max_upstream_chars is not None and self.max_upstream_chars < 0:
            raise ValueError(f"max_upstream_chars must be non-negative, got {self.max_upstream_chars}")
        if self.max_upstream_depth is not None and self.max_upstream_depth < 0:
            raise ValueError(f"max_upstream_depth must be non-negative, got {self.max_upstream_depth}")

    def path(self, filename: str) -> Path:
        return self.output_dir / filename

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("pipeline")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)

# ── Models + Provider ────────────────────────────────────────────────────────
# Provider is auto-detected from which API key is set, unless overridden:
#   OPENROUTER_API_KEY set → openrouter (default models: anthropic/claude-*)
#   ANTHROPIC_API_KEY set  → anthropic  (default models: claude-*-20251001)
#   LLM_PROVIDER=...       → explicit override
#
# Override models in .env:
#   MODEL_FAST=google/gemini-2.0-flash
#   MODEL_STRONG=openai/gpt-4o
# Any model supported by your provider works.
_PLACEHOLDER_KEYS = {"", "your_openrouter_key_here", "your_anthropic_key_here", "XXX"}

_has_openrouter = os.environ.get("OPENROUTER_API_KEY", "") not in _PLACEHOLDER_KEYS
_has_anthropic = os.environ.get("ANTHROPIC_API_KEY", "") not in _PLACEHOLDER_KEYS

# Auto-detect provider from available keys, or use explicit override
_explicit_provider = os.environ.get("LLM_PROVIDER", "").strip().lower() or None
if _explicit_provider and _explicit_provider not in ("openrouter", "anthropic"):
    sys.exit(f"Unsupported LLM_PROVIDER={_explicit_provider!r} (expected 'openrouter' or 'anthropic')")
if _explicit_provider:
    LLM_PROVIDER = _explicit_provider
elif _has_openrouter:
    LLM_PROVIDER = "openrouter"
elif _has_anthropic:
    LLM_PROVIDER = "anthropic"
else:
    LLM_PROVIDER = "anthropic"  # default for backward compatibility

if LLM_PROVIDER == "openrouter":
    _DEFAULT_FAST = "anthropic/claude-haiku-4.5"
    _DEFAULT_STRONG = "anthropic/claude-sonnet-4.6"
    _API_BASE = "https://openrouter.ai/api"
else:
    _DEFAULT_FAST = "claude-haiku-4-5-20251001"
    _DEFAULT_STRONG = "claude-sonnet-4-6"
    _API_BASE = None

MODEL_FAST = os.environ.get("MODEL_FAST", _DEFAULT_FAST)
MODEL_STRONG = os.environ.get("MODEL_STRONG", _DEFAULT_STRONG)


# ── Git ──────────────────────────────────────────────────────────────────────
def get_git_commit() -> str:
    """Return current git commit hash, or 'unknown' (with a loud warning).

    If git metadata is unavailable we still return rather than raising — some
    environments (CI containers, standalone notebook runs, downstream
    consumers re-running the build with our DBs) legitimately won't have git
    installed. But we log loudly so 'unknown' provenance can never enter the
    audit trail silently."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
        )
        commit = result.stdout.strip()
        # Also flag dirty working tree so downstream consumers can see if the
        # build was made from a non-clean checkout.
        try:
            dirty = subprocess.run(
                ["git", "status", "--porcelain"], capture_output=True, text=True, check=True,
            ).stdout.strip()
            if dirty:
                log.warning(
                    "Git working tree is DIRTY at build time (commit %s + uncommitted "
                    "changes). Provenance manifest will include the commit hash but "
                    "the actual code may differ. Commit before treating outputs as "
                    "reproducible.", commit[:8],
                )
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass  # can't check dirty state, but we have the commit; proceed
        return commit
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log.warning(
            "Could not resolve git commit hash (got %s). Provenance manifest "
            "will record 'unknown' for git_commit; reproducibility chain broken. "
            "If this is a release build, install git and rerun from a clean "
            "checkout.", type(e).__name__,
        )
        return "unknown"


# ── OpenRouter via its OpenAI-compatible endpoint ────────────────────────────
# OpenRouter exposes two surfaces. Its Anthropic Skin (/api, spoken by the
# Anthropic SDK) silently DROPS the `reasoning` parameter -- the request 200s and
# the field is ignored. Its OpenAI surface (/api/v1) honours it.
#
# That matters because deepseek/deepseek-v4-flash is a reasoning model: it spends
# output tokens thinking before it answers, and those tokens count against
# max_tokens. Measured over 6 calls on one trivial 20-item prompt:
#
#     endpoint            reasoning chars                 suppressed
#     OpenAI  effort=none [0, 0, 0, 0, 0, 0]              6/6
#     Anthropic (same)    [705, 268, 0, 239, 523, 494]    1/6   (= baseline)
#
# Unsuppressed, reasoning ran 239-862 chars and blew every per-stage max_tokens
# heuristic in src/ (10/item at prefilter, 15/name at canonicalize, 250/text at
# extract), which check_response then turned into a hard failure. Suppressing it
# also cut output tokens ~3.5x on that prompt, so this is a cost fix as well.
#
# Set LLM_REASONING=1 to re-enable reasoning (and re-inflate every budget).
_REASONING_OFF = os.environ.get("LLM_REASONING", "").strip().lower() not in ("1", "true", "yes")


class _ORStream:
    """Anthropic-SDK-shaped streaming context manager over OpenAI chat completions.

    Streaming is not optional here: a full-corpus canonicalization batch has been
    observed taking 710s, and a non-streaming call would hit the client timeout
    long before that.
    """

    def __init__(self, client, **kwargs) -> None:
        self._client, self._kwargs = client, kwargs

    def __enter__(self):
        self._stream = self._client.chat.completions.create(stream=True, **self._kwargs)
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def get_final_message(self):
        parts: list[str] = []
        finish = None
        for chunk in self._stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if getattr(delta, "content", None):
                parts.append(delta.content)
            if chunk.choices[0].finish_reason:
                finish = chunk.choices[0].finish_reason
        # OpenAI spells truncation "length"; normalize so check_response, which
        # keys off the Anthropic name, behaves identically on both surfaces.
        from types import SimpleNamespace
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="".join(parts))],
            stop_reason="max_tokens" if finish == "length" else "end_turn",
        )


class _ORMessages:
    def __init__(self, client) -> None:
        self._client = client

    def stream(self, *, model, messages, max_tokens=1024, system=None,
               temperature=0.0, extra_body=None, **_ignored):
        oai = ([{"role": "system", "content": system}] if system else []) + [
            {"role": m["role"], "content": m["content"]} for m in messages]
        body = dict(extra_body or {})
        if _REASONING_OFF:
            body.setdefault("reasoning", {"effort": "none"})
        return _ORStream(self._client, model=model, messages=oai,
                         max_tokens=max_tokens, temperature=temperature,
                         extra_body=body)


class _ORClient:
    """Anthropic-SDK-shaped wrapper so callers need not know which surface is in use."""

    def __init__(self, client) -> None:
        self.messages = _ORMessages(client)


# ── Client ───────────────────────────────────────────────────────────────────
def get_client() -> anthropic.Anthropic:
    """Return a configured Anthropic client (direct or via OpenRouter).

    Key selection is tied to the provider:
      openrouter → requires OPENROUTER_API_KEY
      anthropic  → requires ANTHROPIC_API_KEY
    """
    if LLM_PROVIDER == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        key_name = "OPENROUTER_API_KEY"
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        key_name = "ANTHROPIC_API_KEY"

    if not api_key or api_key in _PLACEHOLDER_KEYS:
        sys.exit(
            f"{key_name} not set (provider={LLM_PROVIDER}).\n"
            f"  Add {key_name}=... to .env\n"
            f"  Or switch provider: LLM_PROVIDER={'anthropic' if LLM_PROVIDER == 'openrouter' else 'openrouter'}"
        )

    log.info(f"LLM provider: {LLM_PROVIDER} | fast: {MODEL_FAST} | strong: {MODEL_STRONG}"
             + (" | reasoning: off" if LLM_PROVIDER == "openrouter" and _REASONING_OFF else ""))

    if LLM_PROVIDER == "openrouter":
        # Deliberately the OpenAI surface, not the Anthropic Skin: it is the only
        # one that honours `reasoning`. See _ORStream above for the measurements.
        import openai
        return _ORClient(openai.OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            max_retries=4,
            timeout=600.0,   # a canonicalization batch has run 710s; streaming keeps it alive
        ))

    kwargs: dict = {
        "api_key": api_key,
        # leaving the SDK's own retries on nests 5 attempts inside each of ours.
        "max_retries": 0,
        "timeout": 60.0,
    }
    if _API_BASE:
        kwargs["base_url"] = _API_BASE
    return anthropic.Anthropic(**kwargs)


# ── LLM response parsing ────────────────────────────────────────────────────
def _strip_markdown(raw: str) -> str:
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


class LLMParseError(ValueError):
    """LLM response could not be parsed as JSON."""


import re

_TRAILING_COMMA = re.compile(r",\s*([}\]])")

def parse_json_array(raw: str) -> list:
    raw = _strip_markdown(raw)
    start, end = raw.find("["), raw.rfind("]") + 1
    if start < 0 or end <= start:
        raise LLMParseError(f"No JSON array in response: {raw[:200]}")
    text = _TRAILING_COMMA.sub(r"\1", raw[start:end])
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMParseError(f"JSON decode failed: {e} — {raw[:200]}") from e


def parse_json_object(raw: str) -> dict:
    raw = _strip_markdown(raw)
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start < 0 or end <= start:
        raise LLMParseError(f"No JSON object in response: {raw[:200]}")
    text = _TRAILING_COMMA.sub(r"\1", raw[start:end])
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMParseError(f"JSON decode failed: {e} — {raw[:200]}") from e


# ── Drug aliases ─────────────────────────────────────────────────────────────
def resolve_aliases(config: "PipelineConfig") -> tuple[str, list[str]]:
    """Return (target, aliases) for config.drug.

    Uses config.drug_aliases if set (hand-curated list); otherwise falls back
    to get_drug_aliases (LLM lookup + disk cache). Target is always included.
    """
    target = config.drug.strip().lower()
    if config.drug_aliases is not None:
        aliases = [a.lower().strip() for a in config.drug_aliases if a.strip()]
        if target not in aliases:
            aliases.append(target)
        return target, aliases
    return target, get_drug_aliases(config.client, target, config.path(f"aliases_{target}.json"))


def get_drug_aliases(client, drug: str, cache_path: Path) -> list[str]:
    """Return [drug, ...aliases] for filtering in --drug mode.

    Asks the strong model once for common names, abbreviations, brand names,
    and plausible misspellings. Result is cached to disk and editable by hand.
    """
    from prompts.intervention_config import drug_aliases_prompt
    target = drug.strip().lower()
    if cache_path.exists():
        aliases = [a.lower().strip() for a in json.loads(cache_path.read_text(encoding="utf-8")) if a.strip()]
        log.info(f"Loaded {len(aliases)} cached aliases for {target!r} from {cache_path.name}.")
    else:
        raw = llm_call(client, drug_aliases_prompt(target), model=MODEL_STRONG, max_tokens=2000)
        aliases = [a.lower().strip() for a in parse_json_array(raw) if a.strip()]
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(aliases, indent=2))
        log.info(f"Fetched {len(aliases)} aliases for {target!r}; cached to {cache_path.name}.")
    if target not in aliases:
        aliases.append(target)
    log.info(f"Aliases for {target!r}: {', '.join(aliases)}")
    return aliases


# ── LLM Call Wrapper ─────────────────────────────────────────────────────────
RETRY_DELAYS = [2, 5, 15, 30]

# Substrings a gateway uses to say "the upstream is unavailable, try again" in a
# body it has already sent 200 for. Kept narrow: whatever matches here is retried
# five times, so a permanent fault landing in this list costs ~52s per call.
IN_BAND_TRANSIENT = ("provider_unavailable", "overloaded",
                     "no instances available", "temporarily unavailable")


def is_transient_failure(exc: BaseException) -> bool:
    """True for failures where the same request may well succeed on a retry.
    """
    if isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError,
                        anthropic.RateLimitError, anthropic.InternalServerError)):
        return True
    if isinstance(exc, httpx.TransportError):
        return True
    status = getattr(exc, "status_code", None)
    if status == 429 or (isinstance(status, int) and 500 <= status < 600):
        return True
    # A gateway that multiplexes upstreams (OpenRouter) reports a dead backend by
    # injecting an error object into a stream it has already sent 200 for. The SDK
    # raises that via _make_status_error against the stream's own response, so it
    # arrives as a bare APIStatusError carrying 200 and matches nothing above.
    # Read the body instead -- but never for a 4xx, where the request is at fault
    # and a retry sends the same bad request again.
    if isinstance(exc, anthropic.APIStatusError) and not (
            isinstance(status, int) and 400 <= status < 500):
        return any(t in str(exc).lower() for t in IN_BAND_TRANSIENT)
    return False


def llm_call(
    client: anthropic.Anthropic,
    prompt: str,
    model: str = MODEL_FAST,
    system: str | None = None,
    max_tokens: int = 100,
) -> str:
    from patientpunk.llm_cache import cached_completion
    from patientpunk._utils import check_response, response_text

    def _once() -> str:
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        with client.messages.stream(**kwargs) as stream:
            return response_text(check_response(stream.get_final_message(), model=model))

    def _call() -> str:
        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                time.sleep(delay)
            try:
                return _once()
            except Exception as e:
                if not is_transient_failure(e) or attempt == len(RETRY_DELAYS):
                    raise
                log.warning(
                    f"{type(e).__name__} on {model} "
                    f"(attempt {attempt + 1}/{len(RETRY_DELAYS) + 1}), retrying...")
        raise AssertionError("unreachable")  # pragma: no cover

    return cached_completion(
        provider=LLM_PROVIDER,
        model=model,
        system=system,
        prompt=prompt,
        temperature=0.0,
        max_tokens=max_tokens,
        call_fn=_call,
    )
