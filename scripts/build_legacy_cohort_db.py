#!/usr/bin/env python3
"""Materialise the legacy psychedelic cohort as SQL for probes/psychedelic_pharmacology.

The probe resolves its cohort with cohort.sql, which reads
``treatment_reports JOIN treatment``. That is the drug-sentiment pipeline's
output, and it has never been run on the full corpus -- data/posts.db carries a
25-row sample with no psychedelics in it, so cohort.sql returns 0 pairs.

The authoritative cohort does exist, as JSON: the legacy extractor resolved it
from data/full_corpus_2026-07-31/records_covidlonghaulers_v2.json and recorded
the result in data/psychedelics_pharmacology/cohort_status.json (1,157
patient-drug pairs). This script copies those pairs into the two columns
cohort.sql actually reads.

It is an import, not a derivation: the pairs are taken on the legacy pipeline's
authority, so GATE 1's "do the two derivations agree" check cannot be answered
with the result. Sentiment, post_id and run_id are NOT synthesised -- those
columns are absent here rather than filled with invented values.

Usage:
    python scripts/build_legacy_cohort_db.py
    python scripts/build_legacy_cohort_db.py --out cohort_legacy.db
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DEFAULT_COHORT_JSON = HERE / "data/psychedelics_pharmacology/cohort_status.json"
DEFAULT_OUT = HERE / "cohort_legacy.db"

SCHEMA = """
CREATE TABLE treatment (
    id             INTEGER PRIMARY KEY,
    canonical_name TEXT NOT NULL COLLATE NOCASE UNIQUE
);
CREATE TABLE treatment_reports (
    report_id INTEGER PRIMARY KEY,
    user_id   TEXT NOT NULL,
    drug_id   INTEGER NOT NULL REFERENCES treatment(id)
);
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort-json", type=Path, default=DEFAULT_COHORT_JSON)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    pairs = json.loads(args.cohort_json.read_text())
    rows = sorted({(r["author_hash"], r["drug_class"].lower()) for r in pairs})
    if len(rows) != len(pairs):
        print(f"note: {len(pairs) - len(rows)} duplicate pair(s) collapsed")

    if args.out.exists():
        args.out.unlink()
    db = sqlite3.connect(args.out)
    db.executescript(SCHEMA)

    drugs = sorted({target for _, target in rows})
    db.executemany("INSERT INTO treatment (canonical_name) VALUES (?)", [(d,) for d in drugs])
    drug_id = dict(db.execute("SELECT canonical_name, id FROM treatment"))
    db.executemany(
        "INSERT INTO treatment_reports (user_id, drug_id) VALUES (?, ?)",
        [(author, drug_id[target]) for author, target in rows],
    )
    db.commit()

    print(f"wrote {args.out}")
    print(f"  pairs    {len(rows)}")
    print(f"  patients {len({a for a, _ in rows})}")
    for drug, n in db.execute(
        "SELECT t.canonical_name, COUNT(*) FROM treatment_reports tr "
        "JOIN treatment t ON t.id = tr.drug_id GROUP BY 1 ORDER BY 2 DESC"
    ):
        print(f"  {drug:12s} {n}")


if __name__ == "__main__":
    main()
