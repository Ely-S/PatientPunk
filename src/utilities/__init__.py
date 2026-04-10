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
CANONICAL_MAP = "canonical_map.json"


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

# ── Models ───────────────────────────────────────────────────────────────────
MODEL_FAST = "claude-haiku-4-5-20251001"
MODEL_STRONG = "claude-sonnet-4-6"


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


def parse_json_array(raw: str) -> list:
    raw = _strip_markdown(raw)
    start, end = raw.find("["), raw.rfind("]") + 1
    if start < 0 or end <= start:
        return []
    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError:
        return []


def parse_json_object(raw: str) -> dict:
    raw = _strip_markdown(raw)
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start < 0 or end <= start:
        return {}
    try:
        return json.loads(raw[start:end])
    except json.JSONDecodeError:
        return {}


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
