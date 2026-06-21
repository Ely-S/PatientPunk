"""Read-only tool: raw sentiment counts for one drug over `data/posts.db`.

Part of the `src/` (sentiment) system. Imports ONLY from `utilities` and the
sibling `deps` — never `patientpunk` / `variable_extraction` (frozen decoupling
boundary). Imports are bare because pyproject sets `pythonpath = ["src"]`.
"""
from __future__ import annotations

from pathlib import Path

from utilities.db import open_db

from agents._common.tools.deps import SENTIMENTS, _resolve_drug


def get_sentiment_breakdown(drug: str, db_path: str | Path) -> dict:
    """Raw sentiment counts for one drug -> {found, drug, n_reports, counts{4 buckets}}."""
    canonical = _resolve_drug(drug, db_path)
    counts: dict[str, int] = {s: 0 for s in SENTIMENTS}
    conn = open_db(Path(db_path))
    try:
        rows = conn.execute(
            "SELECT tr.sentiment, COUNT(*) "
            "FROM treatment_reports tr "
            "JOIN treatment t ON tr.drug_id = t.id "
            "WHERE t.canonical_name = ? COLLATE NOCASE "
            "GROUP BY tr.sentiment",
            (canonical,),
        ).fetchall()
    finally:
        conn.close()
    n_reports = 0
    for sentiment, c in rows:
        n_reports += c
        if sentiment in counts:
            counts[sentiment] += c
        else:  # unexpected label — surface it under its own key rather than drop
            counts[sentiment] = counts.get(sentiment, 0) + c
    return {
        "found": n_reports > 0,
        "drug": canonical,
        "n_reports": n_reports,
        "counts": counts,
    }
