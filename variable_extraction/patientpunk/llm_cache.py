"""
Content-addressable on-disk cache for LLM API responses.

Layout::

    {LLM_CACHE_DIR}/PROVIDER/MODEL/{hash[:3]}/{hash}.json

Enabled by default. Opt out with ``LLM_CACHE=0`` (or ``false`` / ``no`` / ``off``)
or ``--no-llm-cache``. Root defaults to ``cache/`` (cwd-relative); override with
``LLM_CACHE_DIR``.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}

# Process-level override set by CLI (--llm-cache / --no-llm-cache).
# None = defer to LLM_CACHE env (default on when unset).
_enabled_override: bool | None = None
_lock = threading.Lock()


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


def cache_root() -> Path:
    """Return the cache root directory (default: ``cache``)."""
    return Path(os.environ.get("LLM_CACHE_DIR") or "cache")


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
    )
    path = cache_path(provider, model, key)
    hit = get(path)
    if hit is not None:
        return hit

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
    return text
