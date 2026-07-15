"""Shared utilities for the drug mention pipeline."""
import json
import logging
import os
import sys
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

# ── Output file names ────────────────────────────────────────────────────────
TAGGED_MENTIONS = "tagged_mentions.json"
CANONICALIZED_MENTIONS = "canonicalized_mentions.json"

# Community name injected into the classifier prompt when the DB has no
# source_subreddit (e.g. a writer-less / no-DB run).
DEFAULT_SUBREDDIT = "Long COVID"


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
    workers: int = 3                       # ThreadPoolExecutor workers; 1 = sequential
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
if _explicit_provider and _explicit_provider not in ("openrouter", "anthropic", "openai"):
    sys.exit(f"Unsupported LLM_PROVIDER={_explicit_provider!r} (expected 'openrouter', 'anthropic', or 'openai')")
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
elif LLM_PROVIDER == "openai":
    # OpenAI-compatible server (OpenRouter /v1, vLLM, Ollama, DeepSeek). No model
    # defaults -- set MODEL_FAST / MODEL_STRONG explicitly. base_url from LLM_BASE_URL.
    _DEFAULT_FAST = ""
    _DEFAULT_STRONG = ""
    _API_BASE = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1")
else:
    _DEFAULT_FAST = "claude-haiku-4-5-20251001"
    _DEFAULT_STRONG = "claude-sonnet-4-6"
    _API_BASE = None

MODEL_FAST = os.environ.get("MODEL_FAST", _DEFAULT_FAST)
MODEL_STRONG = os.environ.get("MODEL_STRONG", _DEFAULT_STRONG)

if LLM_PROVIDER == "openai" and not (MODEL_FAST and MODEL_STRONG):
    sys.exit(
        "LLM_PROVIDER=openai has no default model. Set MODEL_FAST and MODEL_STRONG "
        "to the model your endpoint serves (e.g. Qwen/Qwen2.5-32B-Instruct-AWQ)."
    )


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


# ── OpenAI-compatible adapter (LLM_PROVIDER=openai: vLLM / OpenRouter / DeepSeek) ──
# Mimics the slice of the Anthropic client that llm_call() uses:
#   client.messages.stream(**kwargs).get_final_message().content[0].text
# (plus .create() for completeness). No real streaming -- a single non-streamed
# chat.completions call wrapped in the shape src/ expects. `system` is a plain str.
class _Block:
    def __init__(self, text: str): self.text = text
class _Msg:
    def __init__(self, text: str): self.content = [_Block(text)]
class _Stream:
    def __init__(self, text: str): self._text = text
    def __enter__(self): return self
    def __exit__(self, *exc): return False
    def get_final_message(self): return _Msg(self._text)
class _OpenAIMessages:
    def __init__(self, client, temperature: float = 0.0):
        self._client = client
        self._temperature = temperature
    def _call(self, model, messages, max_tokens, system) -> str:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system if isinstance(system, str)
                         else "\n".join(b.get("text", "") for b in system)})
        msgs.extend(messages)
        r = self._client.chat.completions.create(
            model=model, messages=msgs, max_tokens=max_tokens, temperature=self._temperature)
        if not r.choices:
            raise RuntimeError(
                f"OpenAI-compatible endpoint returned no choices for model {model!r} "
                f"(empty response — transient backend failure or a filtered output)."
            )
        return r.choices[0].message.content or ""
    def stream(self, *, model, messages, max_tokens=1024, system=None, **kw):
        return _Stream(self._call(model, messages, max_tokens, system))
    def create(self, *, model, messages, max_tokens=1024, system=None, **kw):
        return _Msg(self._call(model, messages, max_tokens, system))
class _OpenAIAdapter:
    def __init__(self, client, temperature: float = 0.0):
        self.messages = _OpenAIMessages(client, temperature)


# ── Client ───────────────────────────────────────────────────────────────────
# Request timeout (seconds) and retry budget, shared by both provider branches below.
CLIENT_TIMEOUT_SECONDS = 60.0
CLIENT_MAX_RETRIES = 4


def get_client() -> anthropic.Anthropic:
    """Return a configured LLM client.

    Key selection is tied to the provider:
      openrouter → requires OPENROUTER_API_KEY (Anthropic SDK + base_url)
      anthropic  → requires ANTHROPIC_API_KEY
      openai     → OpenAI-compatible server (DeepSeek/vLLM/Ollama via OpenRouter
                   or any /v1 endpoint); uses LLM_API_KEY or OPENROUTER_API_KEY.
    """
    if LLM_PROVIDER == "openai":
        api_key = (os.environ.get("LLM_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or "EMPTY")
        try:
            from openai import OpenAI
        except ImportError:
            sys.exit("LLM_PROVIDER=openai needs the openai package: pip install openai")
        log.info(f"LLM provider: openai | base: {_API_BASE} | fast: {MODEL_FAST} | strong: {MODEL_STRONG}")
        return _OpenAIAdapter(
            OpenAI(api_key=api_key, base_url=_API_BASE, max_retries=CLIENT_MAX_RETRIES, timeout=CLIENT_TIMEOUT_SECONDS),
            temperature=float(os.environ.get("LLM_TEMPERATURE", "0") or 0),
        )

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

    log.info(f"LLM provider: {LLM_PROVIDER} | fast: {MODEL_FAST} | strong: {MODEL_STRONG}")

    kwargs: dict = {
        "api_key": api_key,
        "max_retries": CLIENT_MAX_RETRIES,
        "timeout": CLIENT_TIMEOUT_SECONDS,
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

def _parse_json(raw: str, open_ch: str, close_ch: str, label: str):
    raw = _strip_markdown(raw)
    start, end = raw.find(open_ch), raw.rfind(close_ch) + 1
    if start < 0 or end <= start:
        raise LLMParseError(f"No JSON {label} in response: {raw[:200]}")
    text = _TRAILING_COMMA.sub(r"\1", raw[start:end])
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMParseError(f"JSON decode failed: {e} — {raw[:200]}") from e


def parse_json_array(raw: str) -> list:
    return _parse_json(raw, "[", "]", "array")


def parse_json_object(raw: str) -> dict:
    return _parse_json(raw, "{", "}", "object")


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
def llm_call(
    client: anthropic.Anthropic,
    prompt: str,
    model: str = MODEL_FAST,
    system: str | None = None,
    max_tokens: int = 100,
) -> str:
    kwargs = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if system:
        kwargs["system"] = system
    with client.messages.stream(**kwargs) as stream:
        return stream.get_final_message().content[0].text
