"""Read-only tool: tally reported side effects for one drug, most-common first.

Part of the `src/` (sentiment) system. Imports ONLY from `utilities` and the
sibling `deps` — never `patientpunk` / `variable_extraction` (frozen decoupling
boundary). Imports are bare because pyproject sets `pythonpath = ["src"]`.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from utilities.db import open_db

from agents._common.tools.deps import _resolve_drug


def get_side_effects(drug: str, db_path: str | Path) -> dict:
    """Tally reported side effects for one drug, most-common first."""
    canonical = _resolve_drug(drug, db_path)
    conn = open_db(Path(db_path))
    try:
        rows = conn.execute(
            "SELECT tr.side_effects "
            "FROM treatment_reports tr "
            "JOIN treatment t ON tr.drug_id = t.id "
            "WHERE t.canonical_name = ? COLLATE NOCASE "
            "  AND tr.side_effects IS NOT NULL "
            "  AND tr.side_effects != '' "
            "  AND tr.side_effects != '[]'",
            (canonical,),
        ).fetchall()
    finally:
        conn.close()

    counter: Counter[str] = Counter()
    for (raw,) in rows:
        try:
            effects = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(effects, list):
            continue
        for effect in effects:
            label = str(effect).strip().lower()
            if label:
                counter[label] += 1

    side_effects = [{"effect": effect, "count": count} for effect, count in counter.most_common()]
    return {
        "found": bool(side_effects),
        "drug": canonical,
        "side_effects": side_effects,
    }
