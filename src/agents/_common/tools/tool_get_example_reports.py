"""Read-only tool: up to k verbatim example reports for one drug+sentiment.

Part of the `src/` (sentiment) system. Imports ONLY from `utilities` and the
sibling `deps` — never `patientpunk` / `variable_extraction` (frozen decoupling
boundary). Imports are bare because pyproject sets `pythonpath = ["src"]`.
"""
from __future__ import annotations

from pathlib import Path

from utilities.db import open_db, post_text

from agents._common.tools.deps import _SNIPPET_CHARS, _resolve_drug


def get_example_reports(drug: str, sentiment: str, k: int, db_path: str | Path) -> dict:
    """Up to k verbatim example reports of one sentiment, strongest signal first."""
    canonical = _resolve_drug(drug, db_path)
    k = max(0, int(k))
    conn = open_db(Path(db_path))
    try:
        rows = conn.execute(
            "SELECT tr.post_id, tr.user_id, tr.signal_strength, "
            "       p.title, p.body_text, p.parent_id "
            "FROM treatment_reports tr "
            "JOIN treatment t ON tr.drug_id = t.id "
            "JOIN posts p ON tr.post_id = p.post_id "
            "WHERE t.canonical_name = ? COLLATE NOCASE "
            "  AND tr.sentiment = ? "
            "ORDER BY CASE tr.signal_strength "
            "           WHEN 'strong' THEN 0 WHEN 'moderate' THEN 1 "
            "           WHEN 'weak' THEN 2 ELSE 3 END",
            (canonical, sentiment),
        ).fetchall()
    finally:
        conn.close()

    examples = []
    for post_id, user_id, signal, title, body_text, parent_id in rows[:k]:
        text = post_text(title, body_text, parent_id)
        snippet = text[:_SNIPPET_CHARS].strip()
        examples.append(
            {
                "post_id": post_id,
                "user_id": user_id,
                "signal": signal or "n/a",
                "sentiment": sentiment,
                "text": snippet,
            }
        )
    return {
        "found": bool(examples),
        "drug": canonical,
        "sentiment": sentiment,
        "examples": examples,
    }
