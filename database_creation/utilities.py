"""Shared utilities for the drug mention pipeline."""
import json
import logging
import os
import sys
from pathlib import Path

import anthropic

# Load .env from project root (same as Shaun's pipeline)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
except ImportError:
    pass  # python-dotenv not installed -- rely on shell environment

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
log = logging.getLogger("pipeline")

# Suppress noisy HTTP logs from anthropic/httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)

# ── Paths ────────────────────────────────────────────────────────────────────
# DATA_DIR points to the shared corpus directory (../data relative to this file).
# Scripts use this to resolve subreddit_posts.json and output directories.
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

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
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

def save_cache(cache: dict, path: Path):
    path.write_text(encoding="utf-8", data=json.dumps(cache, indent=2))

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
    return json.loads(raw[start:end]) if start >= 0 else []

def parse_json_object(raw: str) -> dict:
    """Extract JSON object from LLM response."""
    raw = _strip_markdown(raw)
    start, end = raw.find("{"), raw.rfind("}") + 1
    return json.loads(raw[start:end]) if start >= 0 else {}
