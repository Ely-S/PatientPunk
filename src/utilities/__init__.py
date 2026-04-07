"""Shared utilities for the drug mention pipeline."""
import json
import logging
import os
import sys
from pathlib import Path

import anthropic

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
log = logging.getLogger("pipeline")

# Suppress noisy HTTP logs from anthropic/httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)

# ── Models ───────────────────────────────────────────────────────────────────
MODEL_FAST = "claude-haiku-4-5-20251001"
MODEL_STRONG = "claude-sonnet-4-6"

# ── Client ───────────────────────────────────────────────────────────────────
def get_client() -> anthropic.Anthropic:
    """Get Anthropic client, exit if API key not set."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY not set.")
    return anthropic.Anthropic(api_key=api_key)

# ── Cache helpers ────────────────────────────────────────────────────────────
def load_cache(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}

def save_cache(cache: dict, path: Path):
    path.write_text(json.dumps(cache, indent=2))

# ── LLM response parsing ─────────────────────────────────────────────────────
def _strip_markdown(raw: str) -> str:
    """Strip markdown code blocks from LLM response."""
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()

def parse_json_array(raw: str) -> list:
    """Extract JSON array from LLM response."""
    raw = _strip_markdown(raw)
    start, end = raw.find("["), raw.rfind("]") + 1
    return json.loads(raw[start:end]) if start >= 0 and end > start else []

def parse_json_object(raw: str) -> dict:
    """Extract JSON object from LLM response."""
    raw = _strip_markdown(raw)
    start, end = raw.find("{"), raw.rfind("}") + 1
    return json.loads(raw[start:end]) if start >= 0 else {}
