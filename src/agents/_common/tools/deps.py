"""Shared helpers for the read-only evidence tools over `data/posts.db`.

`_resolve_drug` (free-text -> canonical name) and `SIG_RANK` (signal-strength
ordering) are used by several tool functions and by the packet builder. They
import ONLY from `utilities` — never `patientpunk` / `variable_extraction`
(frozen decoupling boundary). Imports are bare because pyproject sets
`pythonpath = ["src"]`.
"""
from __future__ import annotations

from pathlib import Path

from utilities.db import load_synonyms, open_db

# Order signal strength so "strong" floats to the top of LIMIT-k example pulls.
# Mirrors verify.py's SIG_RANK (higher = stronger).
SIG_RANK: dict[str | None, int] = {"strong": 3, "moderate": 2, "weak": 1, "n/a": 0, None: 0, "": 0}

# Snippet length for verbatim example text. Verbatim only — never paraphrase.
_SNIPPET_CHARS = 400

# The four sentiment buckets we always report (pre-seeded to 0).
SENTIMENTS = ("positive", "negative", "mixed", "neutral")


def _resolve_drug(name: str, db_path: str | Path) -> str:
    """Resolve a free-text drug query to a canonical name (case-insensitive over
    canonical_name + aliases); unmatched -> lowercased passthrough. No LLM."""
    q = (name or "").strip().lower()
    if not q:
        return q
    synonyms = load_synonyms(Path(db_path))  # canonical -> [aliases]

    # Build a flat lookup of every known surface form -> canonical.
    surface_to_canonical: dict[str, str] = {}
    conn = open_db(Path(db_path))
    try:
        for (canonical,) in conn.execute("SELECT canonical_name FROM treatment"):
            surface_to_canonical.setdefault(canonical.strip().lower(), canonical)
    finally:
        conn.close()
    for canonical, aliases in synonyms.items():
        surface_to_canonical.setdefault(canonical.strip().lower(), canonical)
        for alias in aliases or []:
            surface_to_canonical.setdefault(str(alias).strip().lower(), canonical)

    return surface_to_canonical.get(q, q)
