"""
patientpunk._utils
~~~~~~~~~~~~~~~~~~
Internal shared helpers.  Not part of the public API.

These are small, stateless utility functions used by multiple modules inside
the ``patientpunk`` package.  Nothing here should import from the rest of the
package -- this module sits at the bottom of the dependency graph so that
corpus.py, schema.py, and pipeline.py can all import from it without creating
circular imports.

Functions
---------
load_json           Safe JSON file loader; returns None on any error instead
                    of raising.  Used wherever we need to read a file that
                    might not exist yet (e.g. intermediate temp files).

get_schema_id       Extract the ``schema_id`` string from a schema JSON file.
                    Falls back to the filename stem so callers always get a
                    usable string even if the schema is malformed.

find_newest_glob    Return the most recently modified file matching a glob
                    pattern.  Used to locate the latest discovered_records_*
                    file in temp/ without knowing the exact schema_id timestamp.

clean_temp_dir      Delete intermediate files by glob pattern.  Called at the
                    start of a full pipeline run to ensure stale results from
                    a prior run don't contaminate the new one.

csv_fill_rate       Compute basic fill-rate statistics for a CSV file.
                    Useful for ad-hoc coverage checks; Pipeline prefers
                    ``PhaseResult.stats`` from ``run_export_csv``.

collect_texts_from_post  Collect title/body (optionally + comments) text from
                    a single subreddit post. Shared by biomedical.py,
                    llm_extract.py, and discover.py so the comments-inclusion
                    difference between them is an explicit flag, not three
                    silently-diverging copies.

strip_markdown_fences    Strip ``` / ```json fences (multi- and single-line).
parse_json_response      Tolerant LLM JSON parse (fences + embedded {...}/[...]).
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from types import SimpleNamespace

# Root of the variable_extraction package tree.
# All path resolution should reference this constant instead of
# repeating Path(__file__).parent.parent... chains.
PACKAGE_ROOT: Path = Path(__file__).resolve().parent.parent


def load_env() -> None:
    """Load .env from the repo root and variable_extraction/, if present.

    The variable_extraction/.env values win (loaded second, override=True).
    Runs once at import time here so every module that reads os.environ for
    LLM config (including this module's own _CFG below) sees .env values,
    regardless of which module a caller imports first.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        raise ImportError("python-dotenv is required: pip install python-dotenv") from None
    load_dotenv(PACKAGE_ROOT.parent / ".env", override=True)  # repo root
    load_dotenv(PACKAGE_ROOT / ".env", override=True)         # variable_extraction/


load_env()


# ---------------------------------------------------------------------------
# LLM client configuration
# ---------------------------------------------------------------------------
# Provider is auto-detected from which API key is set, unless overridden.  Every
# knob is env-configurable, so the SAME pipeline runs against Anthropic,
# OpenRouter, or a self-hosted / dispersed endpoint -- and runs are reproducible
# (pinned model + temperature) and recorded (see llm_config()).
#
#   LLM_PROVIDER     openrouter | anthropic | openai   (default: auto-detect from keys)
#                    openai -> OpenAI-compatible endpoint (vLLM / Ollama / etc.)
#   Key precedence (LLM_API_KEY always wins when set):
#     openrouter → LLM_API_KEY | OPENROUTER_API_KEY | ANTHROPIC_API_KEY
#     openai     → LLM_API_KEY | OPENROUTER_API_KEY
#                  (never ANTHROPIC_API_KEY — wrong key against OpenAI-compat → 401)
#     anthropic  → LLM_API_KEY | ANTHROPIC_API_KEY | OPENROUTER_API_KEY
#   LLM_BASE_URL     override the API base URL (point extraction at any endpoint:
#                    an Anthropic-compatible gateway, or an OpenAI-compatible
#                    server like vLLM on a dispersed node with LLM_PROVIDER=openai)
#   MODEL_FAST / MODEL_STRONG   override the default models
#   LLM_TEMPERATURE  sampling temperature (default 0.0 -- deterministic)
#   LLM_SERVICE_TIER flex | priority   (LLM_PROVIDER=openai only; others 400)

_PLACEHOLDER_KEYS = {"", "XXX", "your_openrouter_key_here", "your_anthropic_key_here"}


def _real_key(env: dict, name: str) -> str:
    v = (env.get(name) or "").strip()
    if v in _PLACEHOLDER_KEYS or v.startswith(("your_", "sk-ant-your-")):
        return ""
    return v


def resolve_llm_config(env: dict | None = None) -> dict:
    """Resolve the active LLM configuration from environment variables.

    Pure (no side effects): returns ``provider``, ``model_fast``,
    ``model_strong``, ``base_url``, ``temperature``, ``api_key`` and
    ``service_tier``.  Used both to build the client and -- minus the key --
    to record run provenance.
    """
    env = os.environ if env is None else env
    or_key = _real_key(env, "OPENROUTER_API_KEY")
    an_key = _real_key(env, "ANTHROPIC_API_KEY")

    explicit = (env.get("LLM_PROVIDER") or "").strip().lower() or None
    if explicit in ("openrouter", "anthropic", "openai"):
        provider = explicit
    elif or_key:
        provider = "openrouter"
    elif an_key:
        provider = "anthropic"
    else:
        provider = "anthropic"  # default; get_llm_client() errors if no key

    if provider == "openrouter":
        default_fast, default_strong = "anthropic/claude-haiku-4.5", "anthropic/claude-sonnet-4.6"
        default_base = "https://openrouter.ai/api"
    elif provider == "openai":
        # OpenAI-compatible endpoint (vLLM / Ollama / ...).  Set MODEL_FAST and
        # MODEL_STRONG to the served model id; base_url defaults to vLLM's.
        default_fast, default_strong = "", ""
        default_base = "http://localhost:8000/v1"
    else:
        default_fast, default_strong = "claude-haiku-4-5-20251001", "claude-sonnet-4-6"
        default_base = None

    llm_key = _real_key(env, "LLM_API_KEY")
    if provider == "openrouter":
        api_key = llm_key or or_key or an_key
    elif provider == "openai":
        # OpenAI-compat must not inherit ANTHROPIC_API_KEY (e.g. OpenRouter via
        # LLM_PROVIDER=openai + LLM_BASE_URL=.../v1 would 401 on an Anthropic key).
        api_key = llm_key or or_key
    else:
        api_key = llm_key or an_key or or_key
    try:
        temperature = float(env.get("LLM_TEMPERATURE", "0") or 0)
    except ValueError:
        temperature = 0.0

    return {
        "provider": provider,
        "model_fast": (env.get("MODEL_FAST") or "").strip() or default_fast,
        "model_strong": (env.get("MODEL_STRONG") or "").strip() or default_strong,
        "base_url": (env.get("LLM_BASE_URL") or "").strip() or default_base,
        "temperature": temperature,
        "api_key": api_key,
        # "flex" (cheaper/slower) or "priority"; None omits the param.
        "service_tier": (env.get("LLM_SERVICE_TIER") or "").strip().lower() or None,
    }


_CFG = resolve_llm_config()
LLM_PROVIDER = _CFG["provider"]
MODEL_FAST = _CFG["model_fast"]
MODEL_STRONG = _CFG["model_strong"]
LLM_TEMPERATURE = _CFG["temperature"]
LLM_SERVICE_TIER = _CFG["service_tier"]


def llm_config() -> dict:
    """Active LLM config for logging / provenance (re-read from env; no api_key)."""
    cfg = resolve_llm_config()
    cfg.pop("api_key", None)
    return cfg


# --- Response validation ------------------------------------------------------

class LLMResponseError(RuntimeError):
    """A provider returned a 200 whose body is unusable (empty / truncated).

    Raised rather than returned so callers can retry (hotter temperature /
    split_retry_batch) and the response cache -- which only stores successful
    returns -- never persists it.
    """


def response_text(response) -> str:
    """Concatenate text content blocks; skip thinking/tool blocks without ``.text``.

    Thinking models (e.g. DeepSeek via Anthropic Messages) may return
    ``[ThinkingBlock, TextBlock, ...]``. Indexing ``content[0].text`` raises
    ``AttributeError`` on the thinking block; this helper only joins blocks that
    expose a text payload.
    """
    return "".join(
        t for b in (getattr(response, "content", None) or [])
        if (t := getattr(b, "text", None))
    )


def check_response(response, model: str = ""):
    """Raise LLMResponseError if a 200-OK response is empty or truncated.

    ``stop_reason == "max_tokens"`` means the reply was cut off mid-generation:
    for the JSON callers here that reply is unparseable, and caching it would
    make the loss permanent across re-runs.
    """
    if getattr(response, "stop_reason", None) == "max_tokens":
        raise LLMResponseError(
            f"{model}: response truncated at max_tokens (raise LLM_MAX_TOKENS "
            f"or shrink the batch)"
        )
    if not response_text(response).strip():
        raise LLMResponseError(f"{model}: response was empty")
    return response


# --- OpenAI-compatible adapter ------------------------------------------------
# vLLM / Ollama / TGI and most self-hosted open-model servers speak the OpenAI
# API. This thin adapter exposes the same ``.messages.create(...)`` surface as
# the Anthropic SDK (translating the system prompt and reshaping the response),
# so the extraction modules work unchanged regardless of backend.

class _AnthropicShapedResponse:
    def __init__(self, text: str, stop_reason: str = "end_turn") -> None:
        self.content = [SimpleNamespace(text=text)]
        self.stop_reason = stop_reason


class _OpenAIMessages:
    def __init__(self, client) -> None:
        self._client = client

    def create(self, *, model, messages, max_tokens=1024, system=None,
               temperature=0.0, service_tier: str | None = None, **_ignored):
        oai_messages = []
        if system:
            if isinstance(system, str):
                sys_text = system
            else:  # Anthropic-style list of {type,text,cache_control} blocks
                sys_text = "\n".join(
                    b.get("text", "") for b in system if isinstance(b, dict))
            if sys_text.strip():
                oai_messages.append({"role": "system", "content": sys_text})
        for m in messages:
            oai_messages.append({"role": m["role"], "content": m["content"]})
        tier = {"service_tier": service_tier} if service_tier else {}
        resp = self._client.chat.completions.create(
            model=model, messages=oai_messages,
            max_tokens=max_tokens, temperature=temperature, **tier,
        )
        # A degenerate reply is a failure, not an empty answer: raise so callers
        # retry and the response cache never stores it.
        if not resp.choices:
            raise LLMResponseError(f"{model}: provider returned no choices")
        choice = resp.choices[0]
        if choice.message.content is None:
            raise LLMResponseError(f"{model}: provider returned null content")
        # OpenAI spells truncation "length"; normalize to the Anthropic name so
        # check_response() works the same on both backends.
        stop_reason = "max_tokens" if choice.finish_reason == "length" else "end_turn"
        return _AnthropicShapedResponse(choice.message.content, stop_reason)


class _OpenAIAdapter:
    """Anthropic-SDK-shaped wrapper around an OpenAI-compatible client."""

    def __init__(self, client) -> None:
        self.messages = _OpenAIMessages(client)


def get_llm_client():
    """Return an LLM client whose ``.messages.create(...)`` matches the Anthropic
    SDK, regardless of backend.

    ``LLM_PROVIDER=openai`` routes to an OpenAI-compatible endpoint (vLLM /
    Ollama / any self-hosted open model) via a thin adapter; otherwise the native
    Anthropic SDK is used (Anthropic, OpenRouter, or any Anthropic-compatible
    endpoint via ``LLM_BASE_URL``).  Key precedence is provider-specific
    (see ``resolve_llm_config``); ``LLM_API_KEY`` always wins when set.
    """
    cfg = resolve_llm_config()

    if cfg["provider"] == "openai":
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "openai package required for LLM_PROVIDER=openai: pip install openai"
            ) from None
        # Self-hosted servers (vLLM/Ollama) often need no real key -> send a dummy.
        client = OpenAI(api_key=cfg["api_key"] or "EMPTY",
                        base_url=cfg["base_url"] or "http://localhost:8000/v1")
        return _OpenAIAdapter(client)

    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package required: pip install anthropic") from None
    if not cfg["api_key"]:
        raise RuntimeError(
            "API key not set. Set OPENROUTER_API_KEY, ANTHROPIC_API_KEY, or LLM_API_KEY."
        )
    kwargs: dict = {"api_key": cfg["api_key"]}
    if cfg["base_url"]:
        kwargs["base_url"] = cfg["base_url"]
    return anthropic.Anthropic(**kwargs)


# Failures that split_retry_batch absorbs (parse errors + unusable 200-OK
# bodies). Auth / non-transient API errors must still propagate.
_SPLIT_RETRY_ERRORS = (ValueError, json.JSONDecodeError, LLMResponseError)


def split_retry_batch(
    call_fn,
    items: list,
    max_depth: int = 2,
    _depth: int = 0,
) -> list:
    """Call *call_fn* with a batch of items; on parse failure split and retry.

    This implements Polina's recursive split pattern for multi-item LLM calls:
    1. Try the full batch → expect a list with len == len(items)
    2. On ValueError / JSONDecodeError / LLMResponseError (wrong count, bad
       JSON, empty/truncated reply): split in half and recurse
    3. At max depth or single item: call individually and collect results

    Parameters
    ----------
    call_fn : callable(list) -> list
        Function that sends items to the LLM and returns a list of results.
        Must raise ValueError, json.JSONDecodeError, or LLMResponseError on
        absorbable failure.
    items : list
        Batch of work items (records, texts, etc.)
    max_depth : int
        Maximum recursion depth before falling back to individual calls.

    Returns
    -------
    list, same length as *items*, in the same order. Entries are whatever
    *call_fn* returned for a successful item, or **None** for an item that still
    failed to parse after the individual-call fallback. Callers MUST treat any
    element as possibly-None (e.g. ``if result is None or not isinstance(...)``)
    -- a None is the explicit "gave up on this item" signal, not a result.
    """
    try:
        results = call_fn(items)
        if len(results) != len(items):
            raise ValueError(
                f"Expected {len(items)} results, got {len(results)}"
            )
        return results
    except _SPLIT_RETRY_ERRORS:
        if _depth >= max_depth or len(items) <= 1:
            # Fall back to individual calls. Only absorb parse / truncated
            # failures here -- anything else (auth errors, other non-transient
            # API errors) is fatal and must propagate so the caller fails
            # loudly instead of silently recording a "PARSE FAILED" that hides
            # the real cause.
            individual = []
            for item in items:
                try:
                    r = call_fn([item])
                    individual.append(r[0])
                except _SPLIT_RETRY_ERRORS:
                    individual.append(None)
            return individual
        mid = len(items) // 2
        left = split_retry_batch(call_fn, items[:mid], max_depth, _depth + 1)
        right = split_retry_batch(call_fn, items[mid:], max_depth, _depth + 1)
        return left + right


def load_json(path: Path) -> dict | list | None:
    """Load a JSON file, returning *None* on any filesystem or parse error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # JSONDecodeError -- file exists but is not valid JSON.
        # OSError -- file not found, permission denied, etc.
        return None


def strip_markdown_fences(raw: str) -> str:
    """Strip ``` / ```json fences from LLM output (multi- and single-line)."""
    raw = raw.strip()
    if raw.startswith("```"):
        nl = raw.find("\n")
        if nl != -1:
            raw = raw[nl + 1:]
        else:
            raw = raw[3:]
            if raw[:4].lower() == "json":
                raw = raw[4:]
        if raw.endswith("```"):
            raw = raw[:-3]
    return raw.strip()


def parse_json_response(text: str) -> dict | list | None:
    """Extract a JSON object or array from an LLM response.

    Handles markdown fences (including single-line `````json{...}``` ``) and
    leading/trailing prose by isolating the outermost ``{...}`` or ``[...]``.
    """
    text = strip_markdown_fences(text.strip())
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for opener, closer in (("{", "}"), ("[", "]")):
            start = text.find(opener)
            end = text.rfind(closer)
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    continue
    return None


def get_schema_id(schema_path: Path) -> str:
    """Return the schema_id from a schema JSON file, falling back to the stem."""
    data = load_json(schema_path)
    if isinstance(data, dict):
        return data.get("schema_id", schema_path.stem)
    return schema_path.stem


def find_newest_glob(directory: Path, pattern: str) -> Path | None:
    """Return the most recently modified file matching *pattern* in *directory*."""
    newest: Path | None = None
    newest_mtime = float("-inf")

    for path in directory.glob(pattern):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > newest_mtime:
            newest = path
            newest_mtime = mtime

    return newest


def find_discovery_reports(temp_dir: Path, base_schema_id: str) -> list[tuple[Path, dict]]:
    """Return ``(report_path, report_dict)`` for every ``discovered_field_report_*.json``
    in *temp_dir* whose ``pipeline_run.base_schema`` matches *base_schema_id*.

    Malformed or non-matching reports are skipped.  This is the single source of
    truth for locating a run's discovery output, used by the pipeline (to find
    the discovered records and schema for Phase 4 / Phase 5) and by the ``promote``
    command (to find the discovery run to merge into a curated schema).
    """
    matches: list[tuple[Path, dict]] = []
    if not temp_dir.exists():
        return matches
    for report_path in temp_dir.glob("discovered_field_report_*.json"):
        report = load_json(report_path)
        if not isinstance(report, dict):
            continue
        run_meta = report.get("pipeline_run", {})
        if not isinstance(run_meta, dict):
            continue
        if run_meta.get("base_schema") != base_schema_id:
            continue
        matches.append((report_path, report))
    return matches


def clean_temp_dir(temp_dir: Path, patterns: list[str]) -> list[str]:
    """
    Delete intermediate files matching any of *patterns* inside *temp_dir*.

    Returns the list of filenames removed.
    """
    if not temp_dir.exists():
        return []
    removed: list[str] = []
    for pattern in patterns:
        for matching_file in temp_dir.glob(pattern):
            try:
                matching_file.unlink()
                removed.append(matching_file.name)
            except OSError:
                # File may be locked or permission-restricted; skip it
                pass
    return sorted(removed)


def csv_fill_rate(csv_path: Path) -> dict:
    """
    Return basic fill-rate statistics for a CSV file.

    Streams rows instead of materialising the entire CSV, so memory
    usage stays constant regardless of corpus size.
    """
    if not csv_path.exists():
        return {}
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        if not columns:
            return {}
        col_count = len(columns)
        row_count = 0
        filled_cells = 0
        for row in reader:
            row_count += 1
            filled_cells += sum(
                1 for value in row.values() if value and value.strip()
            )
    if row_count == 0:
        return {}
    total_cells = row_count * col_count
    return {
        "rows": row_count,
        "columns": col_count,
        "fill_rate": round(filled_cells / total_cells * 100, 1) if total_cells else 0,
        "total_cells": total_cells,
        "filled_cells": filled_cells,
    }


def collect_texts_from_post(post: dict, include_comments: bool = False) -> list[str]:
    """Collect non-empty text segments from a subreddit post.

    Title + body only by default: comments are written by OTHER users, so
    including them would attribute their conditions/treatments to the post
    author. Commenters are captured as their own patients via the aggregate
    path (aggregate_corpus_by_author). Pass include_comments=True only for
    callers that intentionally want discussion text (not per-author attribution).
    """
    texts = [t for t in (post.get("title"), post.get("body")) if t]
    if include_comments:
        texts.extend(c["body"] for c in post.get("comments", []) if c.get("body"))
    return texts
