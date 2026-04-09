"""
patientpunk._utils
~~~~~~~~~~~~~~~~~~
Internal shared helpers.  Not part of the public API.

These are small, stateless utility functions used by multiple modules inside
the ``patientpunk`` package.  Nothing here should import from the rest of the
package -- this module sits at the bottom of the dependency graph so that
corpus.py, schema.py, and pipeline.py can all import from it without creating
circular imports.

Functions
---------
load_json           Safe JSON file loader; returns None on any error instead
                    of raising.  Used wherever we need to read a file that
                    might not exist yet (e.g. intermediate temp files).

get_schema_id       Extract the ``schema_id`` string from a schema JSON file.
                    Falls back to the filename stem so callers always get a
                    usable string even if the schema is malformed.

find_newest_glob    Return the most recently modified file matching a glob
                    pattern.  Used to locate the latest discovered_records_*
                    file in temp/ without knowing the exact schema_id timestamp.

clean_temp_dir      Delete intermediate files by glob pattern.  Called at the
                    start of a full pipeline run to ensure stale results from
                    a prior run don't contaminate the new one.

csv_fill_rate       Compute basic fill-rate statistics for a CSV file.  Used
                    by Pipeline._run_phase_4() to report coverage after export.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

# Root of the variable_extraction package tree.
# All path resolution should reference this constant instead of
# repeating Path(__file__).parent.parent... chains.
PACKAGE_ROOT: Path = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# LLM client configuration (OpenRouter by default)
# ---------------------------------------------------------------------------
# OpenRouter is a proxy that lets you switch models without code changes.
# Set OPENROUTER_API_KEY in .env. Falls back to ANTHROPIC_API_KEY if set.
#
# To use Anthropic directly instead, set LLM_PROVIDER=anthropic in .env.

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openrouter")

# Model names differ between providers
if LLM_PROVIDER == "openrouter":
    MODEL_FAST = "anthropic/claude-haiku-4.5"
    MODEL_STRONG = "anthropic/claude-sonnet-4.6"
    _API_BASE = "https://openrouter.ai/api"
else:
    MODEL_FAST = "claude-haiku-4-5-20251001"
    MODEL_STRONG = "claude-sonnet-4-6"
    _API_BASE = None  # use Anthropic default


def get_llm_client():
    """Return a configured Anthropic client (direct or via OpenRouter).

    Reads API key from environment: OPENROUTER_API_KEY (preferred) or
    ANTHROPIC_API_KEY (fallback). Exits with a clear message if neither is set.
    """
    try:
        import anthropic
    except ImportError:
        sys.exit("anthropic package required: pip install anthropic")

    api_key = (
        os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or ""
    )
    if not api_key or api_key.startswith("sk-ant-your-"):
        sys.exit(
            "API key not set. Add OPENROUTER_API_KEY or ANTHROPIC_API_KEY to .env"
        )

    kwargs: dict = {"api_key": api_key}
    if _API_BASE:
        kwargs["base_url"] = _API_BASE
    return anthropic.Anthropic(**kwargs)


def load_json(path: Path) -> dict | list | None:
    """Load a JSON file, returning *None* on any filesystem or parse error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # JSONDecodeError -- file exists but is not valid JSON.
        # OSError -- file not found, permission denied, etc.
        return None


def get_schema_id(schema_path: Path) -> str:
    """Return the schema_id from a schema JSON file, falling back to the stem."""
    data = load_json(schema_path)
    if isinstance(data, dict):
        return data.get("schema_id", schema_path.stem)
    return schema_path.stem


def find_newest_glob(directory: Path, pattern: str) -> Path | None:
    """Return the most recently modified file matching *pattern* in *directory*."""
    newest: Path | None = None
    newest_mtime = float("-inf")

    for path in directory.glob(pattern):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > newest_mtime:
            newest = path
            newest_mtime = mtime

    return newest


def clean_temp_dir(temp_dir: Path, patterns: list[str]) -> list[str]:
    """
    Delete intermediate files matching any of *patterns* inside *temp_dir*.

    Returns the list of filenames removed.
    """
    if not temp_dir.exists():
        return []
    removed: list[str] = []
    for pattern in patterns:
        for matching_file in temp_dir.glob(pattern):
            try:
                matching_file.unlink()
                removed.append(matching_file.name)
            except OSError:
                # File may be locked or permission-restricted; skip it
                pass
    return sorted(removed)


def csv_fill_rate(csv_path: Path) -> dict:
    """
    Return basic fill-rate statistics for a CSV file.

    Streams rows instead of materialising the entire CSV, so memory
    usage stays constant regardless of corpus size.
    """
    if not csv_path.exists():
        return {}
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        if not columns:
            return {}
        col_count = len(columns)
        row_count = 0
        filled_cells = 0
        for row in reader:
            row_count += 1
            filled_cells += sum(
                1 for value in row.values() if value and value.strip()
            )
    if row_count == 0:
        return {}
    total_cells = row_count * col_count
    return {
        "rows": row_count,
        "columns": col_count,
        "fill_rate": round(filled_cells / total_cells * 100, 1) if total_cells else 0,
        "total_cells": total_cells,
        "filled_cells": filled_cells,
    }
