"""
patientpunk._utils
~~~~~~~~~~~~~~~~~~
Internal shared helpers.  Not part of the public API.

These are small, stateless utility functions used by multiple modules inside
the ``patientpunk`` package.  Nothing here should import from the rest of the
package — this module sits at the bottom of the dependency graph so that
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
from pathlib import Path


def load_json(path: Path) -> dict | list | None:
    """Load a JSON file, returning *None* on any filesystem or parse error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # JSONDecodeError — file exists but is not valid JSON.
        # OSError — file not found, permission denied, etc.
        return None


def get_schema_id(schema_path: Path) -> str:
    """Return the schema_id from a schema JSON file, falling back to the stem."""
    data = load_json(schema_path)
    if isinstance(data, dict):
        return data.get("schema_id", schema_path.stem)
    return schema_path.stem


def find_newest_glob(directory: Path, pattern: str) -> Path | None:
    """Return the most recently modified file matching *pattern* in *directory*."""
    matches = sorted(directory.glob(pattern))
    return matches[-1] if matches else None


def clean_temp_dir(temp_dir: Path, patterns: list[str]) -> list[str]:
    """
    Delete intermediate files matching any of *patterns* inside *temp_dir*.

    Returns the list of filenames removed.
    """
    if not temp_dir.exists():
        return []
    removed: list[str] = []
    for pattern in patterns:
        for f in temp_dir.glob(pattern):
            f.unlink()
            removed.append(f.name)
    return sorted(removed)


def csv_fill_rate(csv_path: Path) -> dict:
    """
    Return basic fill-rate statistics for a CSV file without re-running
    any extraction step.
    """
    if not csv_path.exists():
        return {}
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        cols = reader.fieldnames or []
    if not rows:
        return {}
    total_cells = len(rows) * len(cols)
    filled_cells = sum(
        1 for row in rows for v in row.values() if v and v.strip()
    )
    return {
        "rows": len(rows),
        "columns": len(cols),
        "fill_rate": round(filled_cells / total_cells * 100, 1) if total_cells else 0,
        "total_cells": total_cells,
        "filled_cells": filled_cells,
    }
