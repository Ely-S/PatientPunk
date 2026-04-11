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
    max_upstream_chars: int | None = None  # None = unlimited; truncate upstream comment text to N chars
    max_upstream_depth: int | None = None  # None = unlimited; max upstream hops for drug context

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

# ── Models ───────────────────────────────────────────────────────────────────
MODEL_FAST = "claude-haiku-4-5-20251001"
MODEL_STRONG = "claude-sonnet-4-6"


# ── Git ──────────────────────────────────────────────────────────────────────
def get_git_commit() -> str:
    """Return current git commit hash, or 'unknown'."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


# ── Client ───────────────────────────────────────────────────────────────────
def get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY not set.")
    return anthropic.Anthropic(api_key=api_key)


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
