"""
Content-addressable on-disk cache for LLM API responses.

Layout::

    {LLM_CACHE_DIR}/PROVIDER/MODEL/{hash[:3]}/{hash}.json

Enabled by default. Opt out with ``LLM_CACHE=0`` (or ``false`` / ``no`` / ``off``)
or ``--no-llm-cache``. Root defaults to ``cache/`` at the repo root -- located
from this file, not the cwd, so it is the same cache whether the pipeline is
driven from the repo root or from ``variable_extraction/``. Override with
``LLM_CACHE_DIR`` (resolved to an absolute path).

Events are appended to ``{LLM_CACHE_DIR}/log.txt`` in a minimal format::

    H <key12>   # hit
    M <key12>   # miss
    W <key12>   # write
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}

# Process-level override set by CLI (--llm-cache / --no-llm-cache).
# None = defer to LLM_CACHE env (default on when unset).
_enabled_override: bool | None = None
_lock = threading.Lock()

# Markers that identify the repo root, in priority order.
_ROOT_MARKERS = (".git", "pyproject.toml")

# cache_root() is called on every hit, miss and write; the walk is done once.
_repo_root_cache: Path | None = None


class _CacheFileHandler(logging.Handler):
    """Append-only handler that always writes to ``{cache_root()}/log.txt``."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            path = cache_root() / "log.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            line = self.format(record) + "\n"
            with _lock:
                with path.open("a", encoding="utf-8") as f:
                    f.write(line)
        except Exception:
            self.handleError(record)


_log = logging.getLogger("patientpunk.llm_cache")
_log.setLevel(logging.INFO)
_log.propagate = False
if not any(isinstance(h, _CacheFileHandler) for h in _log.handlers):
    _handler = _CacheFileHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _log.addHandler(_handler)


def _elog(event: str, key: str) -> None:
    """Extremely concise cache event: ``H|M|W <key[:12]>``."""
    _log.info("%s %s", event, key[:12])


def set_cache_enabled(enabled: bool | None) -> None:
    """Override cache enablement for this process (None = use env)."""
    global _enabled_override
    _enabled_override = enabled


def cache_enabled() -> bool:
    """Return True when the API response cache should be used (default: on)."""
    if _enabled_override is not None:
        return _enabled_override
    raw = (os.environ.get("LLM_CACHE") or "").strip().lower()
    if not raw:
        return True
    if raw in _FALSE:
        return False
    if raw in _TRUE:
        return True
    # Unrecognized value: treat as enabled (same as unset) rather than silent off
    return True


def _repo_root() -> Path:
    """Return the repo root: nearest ancestor of this file holding a marker.

    Anchored on ``__file__`` rather than the cwd so the answer does not change
    with the directory the process happens to start in. Falls back to the cwd
    when no marker is found (i.e. the package is installed into site-packages
    rather than run from a checkout), which preserves the historical behaviour
    for that case.
    """
    global _repo_root_cache
    if _repo_root_cache is None:
        here = Path(__file__).resolve()
        _repo_root_cache = next(
            (p for p in here.parents for m in _ROOT_MARKERS if (p / m).exists()),
            Path.cwd(),
        )
    return _repo_root_cache


def cache_root() -> Path:
    """Return the cache root directory (default: ``{repo_root}/cache``).

    Absolute, and independent of the cwd: ``main.py`` is run from
    ``variable_extraction/`` but the pipeline is also driven from the repo root,
    and a cwd-relative root silently gave each its own cache -- so the second
    invocation re-paid for every response the first had already bought.
    """
    override = os.environ.get("LLM_CACHE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return _repo_root() / "cache"


def sanitize_path_segment(name: str) -> str:
    """Make a provider/model id safe as a single path segment (``/`` → ``--``)."""
    return (name or "unknown").replace("/", "--").replace("\\", "--")


def normalize_system(system: str | list | dict | None) -> str:
    """Flatten Anthropic system blocks / strings to a stable key string."""
    if system is None:
        return ""
    if isinstance(system, str):
        return system
    if isinstance(system, dict):
        return str(system.get("text") or "")
    if isinstance(system, list):
        parts: list[str] = []
        for block in system:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(system)


def make_key(
    *,
    provider: str,
    model: str,
    system: str | list | dict | None,
    prompt: str,
    temperature: float,
    max_tokens: int,
    request_variant: dict[str, Any] | None = None,
) -> str:
    """SHA-256 hex digest of the canonical request payload."""
    payload = {
        "provider": provider or "",
        "model": model or "",
        "system": normalize_system(system),
        "prompt": prompt or "",
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }
    if request_variant is not None:
        payload["request_variant"] = request_variant
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def cache_path(provider: str, model: str, key: str, *, root: Path | None = None) -> Path:
    """Build ``root/PROVIDER/MODEL/{key[:3]}/{key}.json``."""
    base = root if root is not None else cache_root()
    return (
        base
        / sanitize_path_segment(provider)
        / sanitize_path_segment(model)
        / key[:3]
        / f"{key}.json"
    )


def get(path: Path) -> str | None:
    """Return cached ``response_text``, or None on miss / corrupt file."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    text = data.get("response_text")
    return text if isinstance(text, str) else None


def put(
    path: Path,
    *,
    key: str,
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
    response_text: str,
) -> None:
    """Atomically write a cache entry (``.tmp`` then ``replace``)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "key": key,
        "provider": provider,
        "model": model,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "response_text": response_text,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    with _lock:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


def cached_completion(
    *,
    provider: str,
    model: str,
    system: str | list | dict | None,
    prompt: str,
    temperature: float,
    max_tokens: int,
    request_variant: dict[str, Any] | None = None,
    call_fn: Callable[[], str],
) -> str:
    """Return a cached response when enabled+hit; otherwise call ``call_fn`` and store.

    Exceptions from ``call_fn`` are never cached.
    """
    if not cache_enabled():
        return call_fn()

    key = make_key(
        provider=provider,
        model=model,
        system=system,
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        request_variant=request_variant,
    )
    path = cache_path(provider, model, key)
    hit = get(path)
    if hit is not None:
        _elog("H", key)
        return hit

    _elog("M", key)
    text = call_fn()
    put(
        path,
        key=key,
        provider=provider,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        response_text=text,
    )
    _elog("W", key)
    return text
