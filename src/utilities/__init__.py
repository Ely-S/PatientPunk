"""Shared utilities for the drug mention pipeline."""
import json
import logging
import os
import re
import subprocess
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
    workers: int = 3                       # ThreadPoolExecutor workers; 1 = sequential
    drug: str | None = None                # If set, canonicalize + classify operate on this drug and its synonyms only

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
#   OPENROUTER_API_KEY set → openrouter
#   ANTHROPIC_API_KEY set  → anthropic
#   LLM_PROVIDER=...       → explicit override
#
# Override models in .env via MODEL_FAST / MODEL_STRONG.
_PLACEHOLDER_KEYS = {"", "your_openrouter_key_here", "your_anthropic_key_here", "XXX"}

PROVIDERS: dict[str, dict] = {
    "openrouter": {
        "key": "OPENROUTER_API_KEY",
        "fast": "anthropic/claude-haiku-4.5",
        "strong": "anthropic/claude-sonnet-4.6",
        "base_url": "https://openrouter.ai/api",
    },
    "anthropic": {
        "key": "ANTHROPIC_API_KEY",
        "fast": "claude-haiku-4-5-20251001",
        "strong": "claude-sonnet-4-6",
        "base_url": None,
    },
}


def _valid_key(name: str) -> bool:
    return os.environ.get(name, "") not in _PLACEHOLDER_KEYS


_explicit = os.environ.get("LLM_PROVIDER", "").strip().lower() or None
if _explicit and _explicit not in PROVIDERS:
    sys.exit(f"Unsupported LLM_PROVIDER={_explicit!r} (expected one of {sorted(PROVIDERS)})")
if _explicit:
    LLM_PROVIDER = _explicit
elif _valid_key("OPENROUTER_API_KEY"):
    LLM_PROVIDER = "openrouter"
else:
    LLM_PROVIDER = "anthropic"

_provider_cfg = PROVIDERS[LLM_PROVIDER]
MODEL_FAST = os.environ.get("MODEL_FAST", _provider_cfg["fast"])
MODEL_STRONG = os.environ.get("MODEL_STRONG", _provider_cfg["strong"])


# ── Git ──────────────────────────────────────────────────────────────────────
def get_git_commit() -> str:
    """Return current git commit hash, or 'unknown'."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


# ── Client ───────────────────────────────────────────────────────────────────
def get_client() -> anthropic.Anthropic:
    """Return a configured Anthropic client (direct or via OpenRouter)."""
    key_name = _provider_cfg["key"]
    if not _valid_key(key_name):
        other = next(p for p in PROVIDERS if p != LLM_PROVIDER)
        sys.exit(
            f"{key_name} not set (provider={LLM_PROVIDER}).\n"
            f"  Add {key_name}=... to .env\n"
            f"  Or switch provider: LLM_PROVIDER={other}"
        )

    log.info(f"LLM provider: {LLM_PROVIDER} | fast: {MODEL_FAST} | strong: {MODEL_STRONG}")

    kwargs: dict = {
        "api_key": os.environ[key_name],
        "max_retries": 4,
        "timeout": 60.0,
    }
    if _provider_cfg["base_url"]:
        kwargs["base_url"] = _provider_cfg["base_url"]
    return anthropic.Anthropic(**kwargs)


# ── LLM response parsing ────────────────────────────────────────────────────
class LLMParseError(ValueError):
    """LLM response could not be parsed as JSON."""


_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _strip_markdown(raw: str) -> str:
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _parse_json(raw: str, open_ch: str, close_ch: str, kind: str):
    raw = _strip_markdown(raw)
    start, end = raw.find(open_ch), raw.rfind(close_ch) + 1
    if start < 0 or end <= start:
        raise LLMParseError(f"No JSON {kind} in response: {raw[:200]}")
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
def get_drug_aliases(client, drug: str, cache_path: Path) -> list[str]:
    """Return [drug, ...aliases] for filtering in --drug mode.

    Asks the strong model once for common names, abbreviations, brand names,
    and plausible misspellings. Result is cached to disk and editable by hand.
    """
    target = drug.strip().lower()
    if cache_path.exists():
        aliases = [a.lower().strip() for a in json.loads(cache_path.read_text()) if a.strip()]
        log.info(f"Loaded {len(aliases)} cached aliases for {target!r} from {cache_path.name}.")
    else:
        prompt = (
            f"List common names, abbreviations, brand names, generic names, "
            f"and plausible misspellings/typos for the drug, supplement, or intervention "
            f"'{target}'. Return ONLY a JSON array of lowercase strings — no prose. "
            f"Include the canonical name. Only include names a reader might plausibly "
            f"write for this exact substance; do not enumerate every dosage variant. "
            f"Return at most 30 entries."
        )
        raw = llm_call(client, prompt, model=MODEL_STRONG, max_tokens=2000)
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
    retries: int = 2,
) -> str:
    kwargs = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if system:
        kwargs["system"] = system
    for attempt in range(retries + 1):
        try:
            with client.messages.stream(**kwargs) as stream:
                return stream.get_final_message().content[0].text
        except anthropic.RateLimitError as e:
            if attempt == retries:
                raise
            retry_after = float(e.response.headers.get("retry-after", 30)) if e.response else 30
            log.warning(f"Rate limited; sleeping {retry_after:.0f}s then retry {attempt + 1}/{retries}...")
            time.sleep(retry_after)
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
            if attempt == retries:
                raise
            log.warning(f"LLM call failed ({type(e).__name__}); retry {attempt + 1}/{retries}...")
            time.sleep(2 ** attempt)
