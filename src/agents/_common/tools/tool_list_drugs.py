"""Read-only tool: list drugs with >= min_reports reports + deduped-user counts.

Part of the `src/` (sentiment) system. Imports ONLY from `utilities` — never
`patientpunk` / `variable_extraction` (frozen decoupling boundary). Imports are
bare because pyproject sets `pythonpath = ["src"]`.
"""
from __future__ import annotations

from pathlib import Path

from utilities.db import open_db


def list_drugs(min_reports: int, db_path: str | Path) -> dict:
    """List drugs with >= min_reports reports + deduped-user counts, report-count desc."""
    min_reports = max(0, int(min_reports))
    conn = open_db(Path(db_path))
    try:
        rows = conn.execute(
            "SELECT t.canonical_name, COUNT(*) AS n_reports, "
            "       COUNT(DISTINCT tr.user_id) AS n_users "
            "FROM treatment_reports tr "
            "JOIN treatment t ON tr.drug_id = t.id "
            "GROUP BY t.canonical_name "
            "HAVING n_reports >= ? "
            "ORDER BY n_reports DESC, t.canonical_name ASC",
            (min_reports,),
        ).fetchall()
    finally:
        conn.close()
    drugs = [
        {"drug": name, "n_reports": n_reports, "n_users": n_users}
        for name, n_reports, n_users in rows
    ]
    return {"found": bool(drugs), "min_reports": min_reports, "drugs": drugs}
