"""Shared utilities for the drug mention pipeline."""
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar

import anthropic


# ── Output Files ──────────────────────────────────────────────────────────────
class OutputFiles:
    """Centralized output file names."""
    TAGGED_MENTIONS = "tagged_mentions.json"
    CANONICAL_MAP = "canonical_map.json"
    SENTIMENT_CACHE = "sentiment_cache.json"
    FILTERED_CACHE = "filtered_cache.json"


# ── Pipeline Config ───────────────────────────────────────────────────────────
@dataclass
class PipelineConfig:
    """Shared configuration for all pipeline steps."""
    client: anthropic.Anthropic
    output_dir: Path
    posts_file: Path
    limit: int = 100
    regenerate_cache: bool = False

    def path(self, filename: str) -> Path:
        """Get full path for an output file."""
        return self.output_dir / filename

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


# ── LLM Call Wrapper ──────────────────────────────────────────────────────────
def llm_call(
    client: anthropic.Anthropic,
    prompt: str,
    model: str = MODEL_FAST,
    system: str | None = None,
    max_tokens: int = 100,
) -> str:
    """Make an LLM call and return the text response."""
    kwargs = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    return resp.content[0].text


# ── Batching Helper ───────────────────────────────────────────────────────────
T = TypeVar("T")
R = TypeVar("R")


def process_in_batches(
    items: list[T],
    batch_size: int,
    process_fn: Callable[[list[T]], list[R]],
    fallback_fn: Callable[[T], R] | None = None,
    progress_label: str = "Processed",
    save_fn: Callable[[], None] | None = None,
    save_every: int = 5,
) -> list[R]:
    """
    Process items in batches with progress logging and error handling.
    
    Args:
        items: List of items to process
        batch_size: Number of items per batch
        process_fn: Function to process a batch, returns list of results
        fallback_fn: Optional function to process single item on batch failure
        progress_label: Label for progress logging
        save_fn: Optional function to call periodically to save progress
        save_every: Call save_fn every N batches
    
    Returns:
        List of results in same order as items
    """
    results = []
    batches_since_save = 0
    
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        try:
            batch_results = process_fn(batch)
            results.extend(batch_results)
        except Exception as e:
            if fallback_fn:
                log.warning(f"Batch failed: {e}, retrying individually...")
                for item in batch:
                    try:
                        results.append(fallback_fn(item))
                    except Exception as e2:
                        log.error(f"Item failed: {e2} falling back to empty item")
                        results.append(None)
            else:
                log.error(f"Batch error: {e} falling back to empty batch")
                results.extend([None] * len(batch))
        
        batches_since_save += 1
        if save_fn and batches_since_save >= save_every:
            save_fn()
            batches_since_save = 0
        
        log.info(f"{progress_label} {min(i + batch_size, len(items))}/{len(items)}...")
    
    return results
