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


# ── Pipeline Config ──────────────────────────────────────────────────────────
@dataclass
class PipelineConfig:
    """Shared configuration for all pipeline steps."""
    client: anthropic.Anthropic
    output_dir: Path
    db_path: Path
    limit: int = 100
    reclassify: bool = False

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
_explicit_provider = os.environ.get("LLM_PROVIDER")
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

    log.info(f"LLM provider: {LLM_PROVIDER} | fast: {MODEL_FAST} | strong: {MODEL_STRONG}")

    kwargs: dict = {"api_key": api_key}
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
    return client.messages.create(**kwargs).content[0].text
