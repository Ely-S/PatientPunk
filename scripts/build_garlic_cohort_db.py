#!/usr/bin/env python3
"""Materialise the garlic FTS cohort as SQL for probes/garlic_pharmacology.

Do not read patientpunk.db / treatment_reports. The first-pass garlic label is
not this study's population. Cohort membership is authors matching the same
FTS query the evidence adapter uses (``TARGETS`` in
``probes/garlic_pharmacology/evidence.py``).

GATE 1 is independent of FTS-versus-SQL agreement:

1. Non-bot FTS author count ≈ 1,928.
2. JSON ∩ FTS ≈ 500 / 502.
3. The 2 JSON-only rows confirmed as no garlic-family tokens in source.

Usage:
    uv run python scripts/build_garlic_cohort_db.py
    uv run python scripts/build_garlic_cohort_db.py --out garlic_cohort.db
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from probes.engine import read_only_connection
from probes.garlic_pharmacology.evidence import (
    HALLUCINATION_TOKEN_RE,
    TARGETS,
    author_hash,
    matching_author_hashes,
)
from probes.psychedelic_pharmacology.evidence import BOT_AUTHORS

DEFAULT_SOURCE = HERE / "reddit_2026-06-13.db"
DEFAULT_JSON = HERE / "data/full_corpus_2026-07-31/records_covidlonghaulers_v2.json"
DEFAULT_OUT = HERE / "garlic_cohort.db"

EXPECTED_FTS_AUTHORS = 1_928
EXPECTED_JSON_GARLIC = 502
EXPECTED_OVERLAP = 500

JSON_GARLIC_RE = re.compile(
    r"\bgarlic\b|\ballicin\b|\bkyolic\b|\ballium sativum\b",
    re.IGNORECASE,
)
JSON_HEALTH_FIELDS = (
    "medications",
    "treatment_outcome",
    "dietary_interventions",
    "alternative_treatments",
    "other_symptoms",
)

SCHEMA = """
CREATE TABLE garlic_cohort (
    author_hash TEXT NOT NULL,
    target      TEXT NOT NULL,
    PRIMARY KEY (author_hash, target)
);
"""

TARGET = "garlic"


def _field_values(fields: dict, name: str) -> list[str]:
    data = fields.get(name) or {}
    values = data.get("values") if isinstance(data, dict) else None
    if not values:
        return []
    if isinstance(values, str):
        return [values]
    return [str(item) for item in values]


def _record_blob(fields: dict, names: tuple[str, ...] | None = None) -> str:
    if names is None:
        names = tuple(fields)
    parts: list[str] = []
    for name in names:
        parts.extend(_field_values(fields, name))
    return "\n".join(parts)


def json_garlic_hashes(records_path: Path) -> tuple[set[str], set[str], set[str]]:
    """Return (all JSON hashes, any-field garlic hashes, health-field garlic hashes)."""

    records = json.loads(records_path.read_text(encoding="utf-8"))
    all_hashes: set[str] = set()
    any_field: set[str] = set()
    health_field: set[str] = set()
    for record in records:
        meta = record.get("record_meta") or {}
        pid = meta.get("author_hash")
        if not pid:
            continue
        all_hashes.add(pid)
        fields = record.get("fields") or {}
        if JSON_GARLIC_RE.search(_record_blob(fields)):
            any_field.add(pid)
        if JSON_GARLIC_RE.search(_record_blob(fields, JSON_HEALTH_FIELDS)):
            health_field.add(pid)
    return all_hashes, any_field, health_field


def source_item_stats(
    source_db: Path, wanted_hashes: set[str]
) -> dict[str, tuple[int, int]]:
    """For each hash: (source item count, items with a hallucination-token hit).

    Scans posts and comments. Does not return text, usernames, or hashes to
    stdout — the caller prints aggregates only.
    """

    stats = {item: [0, 0] for item in wanted_hashes}
    connection = read_only_connection(source_db)
    try:
        queries = (
            (
                "SELECT author, COALESCE(title, '') || char(10) || COALESCE(selftext, '') "
                "FROM posts"
            ),
            ("SELECT author, body FROM comments"),
        )
        for sql in queries:
            for author, text in connection.execute(sql):
                if not author or author in BOT_AUTHORS:
                    continue
                digest = author_hash(author)
                row = stats.get(digest)
                if row is None:
                    continue
                row[0] += 1
                if HALLUCINATION_TOKEN_RE.search(text or ""):
                    row[1] += 1
    finally:
        connection.close()
    return {key: (counts[0], counts[1]) for key, counts in stats.items()}


def write_cohort(path: Path, hashes: set[str]) -> None:
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SCHEMA)
        rows = sorted((digest, TARGET) for digest in hashes)
        connection.executemany(
            "INSERT INTO garlic_cohort (author_hash, target) VALUES (?, ?)",
            rows,
        )
        connection.commit()
    finally:
        connection.close()


def _gate1(
    fts_hashes: set[str],
    json_all: set[str],
    json_any: set[str],
    json_health: set[str],
    json_only_stats: dict[str, tuple[int, int]],
) -> int:
    """Print GATE 1 aggregates. Return 0 if the cohort is usable, else 1.

    Never prints hashes, usernames, or source text.
    """

    overlap = fts_hashes & json_any
    json_only = json_any - fts_hashes
    fts_in_json = fts_hashes & json_all
    fts_no_json = fts_hashes - json_all
    fts_in_json_no_garlic = fts_in_json - json_any
    json_only_with_tokens = sum(1 for _h, (_n, hits) in json_only_stats.items() if hits)
    json_only_items = sum(n for n, _hits in json_only_stats.values())

    print("GATE 1")
    print(f"  FTS non-bot authors     {len(fts_hashes):>6}   (expected {EXPECTED_FTS_AUTHORS})")
    print(f"  JSON garlic any-field   {len(json_any):>6}   (expected {EXPECTED_JSON_GARLIC})")
    print(f"  JSON health-field       {len(json_health):>6}   (design 496)")
    print(f"  JSON ∩ FTS              {len(overlap):>6}   (expected {EXPECTED_OVERLAP} / {EXPECTED_JSON_GARLIC})")
    print(f"  FTS authors in 69k JSON {len(fts_in_json):>6}   (design 1,815)")
    print(f"  FTS authors, no JSON record {len(fts_no_json):>6}   (design 113)")
    print(f"  FTS in 69k, no garlic field {len(fts_in_json_no_garlic):>6}   (design 1,315)")
    print(f"  JSON-only rows          {len(json_only):>6}   (expected 2)")
    print(f"  JSON-only source items  {json_only_items:>6}")
    print(f"  JSON-only with garlic-family tokens {json_only_with_tokens:>6}   (expected 0)")

    fts_query, _term = TARGETS[TARGET]
    print(f"  TARGETS FTS query       {fts_query}")

    if not fts_hashes:
        print("GATE 1 FAIL: empty FTS cohort. Stop.")
        return 1
    if abs(len(json_any) - EXPECTED_JSON_GARLIC) > 100:
        print(
            f"GATE 1 FAIL: JSON garlic count {len(json_any)} is far from "
            f"{EXPECTED_JSON_GARLIC}. The record shape or the field names moved; "
            "the overlap check cannot mean anything. Stop."
        )
        return 1
    if not overlap:
        print("GATE 1 FAIL: JSON ∩ FTS is 0. Hasher or join is wrong. Stop.")
        return 1
    if json_only and not json_only_items:
        print(
            "GATE 1 FAIL: a JSON-only row has no source items at all, so its "
            "absence of garlic tokens confirms nothing. Stop."
        )
        return 1
    if json_only_with_tokens:
        print(
            "GATE 1 FAIL: a JSON-only row has garlic-family tokens in source. "
            "Not a hallucination; the FTS join missed them. Stop."
        )
        return 1
    if abs(len(fts_hashes) - EXPECTED_FTS_AUTHORS) > 100:
        print(
            f"GATE 1 FAIL: FTS author count {len(fts_hashes)} is far from "
            f"{EXPECTED_FTS_AUTHORS}. Stop."
        )
        return 1
    if json_only and len(json_only) != 2:
        print(
            f"GATE 1 note: JSON-only count is {len(json_only)}, not 2. "
            "Cohort is still the FTS set; report this."
        )
    if len(overlap) != EXPECTED_OVERLAP or len(json_any) != EXPECTED_JSON_GARLIC:
        print(
            "GATE 1 note: JSON overlap is not exactly "
            f"{EXPECTED_OVERLAP}/{EXPECTED_JSON_GARLIC}. Report this; do not chase "
            "JSON-only rows into the cohort."
        )
    if json_only and json_only_with_tokens == 0:
        print(
            "GATE 1: JSON-only rows have no garlic/allicin/kyolic/clove/allium "
            "tokens in source. Treat as extractor hallucinations. Do not add them."
        )
    print("GATE 1 pass.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--records-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--skip-gate1-json",
        action="store_true",
        help="Write the FTS cohort without the JSON overlap check (tests).",
    )
    args = parser.parse_args(argv)

    if TARGET not in TARGETS or len(TARGETS) != 1:
        print("TARGETS must be the single canonical garlic target.", file=sys.stderr)
        return 1

    fts_hashes = matching_author_hashes(args.source_db)
    print(f"  members {len(fts_hashes)}")
    print(f"  target  {TARGET}")

    if args.skip_gate1_json:
        if not fts_hashes:
            return 1
        write_cohort(args.out, fts_hashes)
        print(f"wrote {args.out}")
        return 0
    if not args.records_json.is_file():
        print(f"GATE 1 FAIL: records JSON not found: {args.records_json}")
        return 1

    json_all, json_any, json_health = json_garlic_hashes(args.records_json)
    json_only = json_any - fts_hashes
    json_only_stats = source_item_stats(args.source_db, json_only) if json_only else {}
    status = _gate1(fts_hashes, json_all, json_any, json_health, json_only_stats)
    if status:
        # The cohort DB is Stage 2's input. A failed gate must not leave one on
        # disk for the next command to pick up.
        print(f"GATE 1 failed; {args.out} not written.")
        return status

    write_cohort(args.out, fts_hashes)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
