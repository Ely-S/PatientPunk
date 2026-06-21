"""Read-only tool: methodology caveats for one drug (report/user/subreddit counts).

Part of the `src/` (sentiment) system. Imports ONLY from `utilities` and the
sibling `deps` — never `patientpunk` / `variable_extraction` (frozen decoupling
boundary). Imports are bare because pyproject sets `pythonpath = ["src"]`.
"""
from __future__ import annotations

from pathlib import Path

from utilities.db import open_db

from agents._common.tools.deps import _resolve_drug


def get_caveats(drug: str, db_path: str | Path) -> dict:
    """Methodology caveats for one drug: report/user/subreddit counts; small_n_warning < 30 users."""
    canonical = _resolve_drug(drug, db_path)
    conn = open_db(Path(db_path))
    try:
        n_reports, n_users = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT tr.user_id) "
            "FROM treatment_reports tr "
            "JOIN treatment t ON tr.drug_id = t.id "
            "WHERE t.canonical_name = ? COLLATE NOCASE",
            (canonical,),
        ).fetchone()
        subreddits = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT u.source_subreddit "
                "FROM treatment_reports tr "
                "JOIN treatment t ON tr.drug_id = t.id "
                "JOIN users u ON tr.user_id = u.user_id "
                "WHERE t.canonical_name = ? COLLATE NOCASE "
                "  AND u.source_subreddit IS NOT NULL",
                (canonical,),
            ).fetchall()
        ]
    finally:
        conn.close()

    n_reports = n_reports or 0
    n_users = n_users or 0
    return {
        "found": n_reports > 0,
        "drug": canonical,
        "n_reports": n_reports,
        "n_users": n_users,
        "subreddits": subreddits,
        "small_n_warning": n_users < 30,
        "self_report": True,
        "is_anecdotal": True,
    }
