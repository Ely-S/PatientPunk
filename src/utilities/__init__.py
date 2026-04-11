"""Shared utilities for the drug mention pipeline."""
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

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
# OpenRouter is the default — set OPENROUTER_API_KEY in .env.
# To use Anthropic directly, set LLM_PROVIDER=anthropic in .env.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openrouter")

if LLM_PROVIDER == "openrouter":
    MODEL_FAST = "anthropic/claude-haiku-4.5"
    MODEL_STRONG = "anthropic/claude-sonnet-4.6"
    _API_BASE = "https://openrouter.ai/api"
else:
    MODEL_FAST = "claude-haiku-4-5-20251001"
    MODEL_STRONG = "claude-sonnet-4-6"
    _API_BASE = None


# ── Client ───────────────────────────────────────────────────────────────────
def get_client() -> anthropic.Anthropic:
    """Return a configured Anthropic client (direct or via OpenRouter).

    Reads API key from environment: OPENROUTER_API_KEY (preferred) or
    ANTHROPIC_API_KEY (fallback). Exits with a clear message if neither is set.
    """
    api_key = (
        os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or ""
    )
    if not api_key or api_key.startswith("sk-ant-your-"):
        sys.exit(
            "API key not set. Add OPENROUTER_API_KEY or ANTHROPIC_API_KEY to .env\n"
            "  export OPENROUTER_API_KEY=your_key_here\n"
            "  # or: export ANTHROPIC_API_KEY=your_key_here"
        )
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
