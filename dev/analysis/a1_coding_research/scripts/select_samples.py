"""Select deterministic ID-only samples for A1 prompt engineering."""

from __future__ import annotations

import argparse
import hashlib
import random
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common import SAMPLE_FILES, SAMPLES_DIR, require_file, write_jsonl
from dev.analysis.a0_extraction.comment_context import DEFAULT_DB


DEFAULT_SEED = 20260703
DEFAULT_CANDIDATE_LIMIT = 6000


@dataclass(frozen=True)
class Bucket:
    name: str


@dataclass(frozen=True)
class SampleSpec:
    name: str
    total: int
    quotas: dict[str, int]


BUCKETS = {
    "top_level": Bucket("top_level"),
    "reply_with_parent": Bucket("reply_with_parent"),
    "missing_parent": Bucket("missing_parent"),
    "short": Bucket("short"),
    "long": Bucket("long"),
    "removed_deleted": Bucket("removed_deleted"),
    "likely_symptom": Bucket("likely_symptom"),
    "likely_treatment": Bucket("likely_treatment"),
    "question_only": Bucket("question_only"),
    "context_reference": Bucket("context_reference"),
    "other_person": Bucket("other_person"),
    "advice_meta": Bucket("advice_meta"),
    "fallback_general": Bucket("fallback_general"),
}


SAMPLE_SPECS = {
    "seed_review": SampleSpec(
        "seed_review",
        75,
        {
            "top_level": 8,
            "reply_with_parent": 10,
            "missing_parent": 5,
            "short": 8,
            "long": 8,
            "removed_deleted": 6,
            "likely_symptom": 8,
            "likely_treatment": 8,
            "question_only": 6,
            "context_reference": 8,
        },
    ),
    "prompt_dev": SampleSpec(
        "prompt_dev",
        200,
        {
            "top_level": 20,
            "reply_with_parent": 30,
            "missing_parent": 8,
            "short": 20,
            "long": 20,
            "removed_deleted": 15,
            "likely_symptom": 30,
            "likely_treatment": 25,
            "question_only": 15,
            "context_reference": 17,
        },
    ),
    "gold_holdout": SampleSpec(
        "gold_holdout",
        150,
        {
            "top_level": 16,
            "reply_with_parent": 24,
            "missing_parent": 7,
            "short": 15,
            "long": 15,
            "removed_deleted": 12,
            "likely_symptom": 22,
            "likely_treatment": 18,
            "question_only": 10,
            "context_reference": 11,
        },
    ),
    "adversarial_context": SampleSpec(
        "adversarial_context",
        50,
        {
            "context_reference": 15,
            "question_only": 8,
            "other_person": 8,
            "advice_meta": 8,
            "missing_parent": 5,
            "short": 3,
            "removed_deleted": 3,
        },
    ),
}


def connect(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def stable_seed(seed: int, label: str) -> int:
    digest = hashlib.sha256(f"{seed}:{label}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def scan_candidates(
    conn: sqlite3.Connection,
    *,
    candidate_limit: int,
    seed: int,
) -> dict[str, list[dict[str, Any]]]:
    reservoirs: dict[str, list[dict[str, Any]]] = {name: [] for name in BUCKETS}
    seen: Counter[str] = Counter()
    rngs = {name: random.Random(stable_seed(seed, f"reservoir:{name}")) for name in BUCKETS}

    sql = """
        SELECT
            c.id AS comment_id,
            c.source_line,
            c.date_utc,
            c.parent_kind,
            c.parent_comment_id,
            c.body_length,
            c.is_removed_or_deleted,
            c.link_id,
            c.score,
            c.has_body,
            c.body,
            CASE WHEN p.id IS NULL THEN 0 ELSE 1 END AS parent_available
        FROM comments c
        LEFT JOIN comments p ON p.id = c.parent_comment_id
        WHERE c.has_body = 1
        ORDER BY c.source_line
    """
    for row in conn.execute(sql):
        payload = dict(row)
        bucket_names = classify_row(payload)
        if not bucket_names:
            continue
        sample_row = strip_body(payload)
        for bucket_name in bucket_names:
            reservoir_add(
                reservoirs[bucket_name],
                sample_row,
                seen=seen,
                rng=rngs[bucket_name],
                bucket_name=bucket_name,
                limit=candidate_limit,
            )

    return reservoirs


def reservoir_add(
    reservoir: list[dict[str, Any]],
    row: dict[str, Any],
    *,
    seen: Counter[str],
    rng: random.Random,
    bucket_name: str,
    limit: int,
) -> None:
    seen[bucket_name] += 1
    if len(reservoir) < limit:
        reservoir.append(row)
        return
    index = rng.randrange(seen[bucket_name])
    if index < limit:
        reservoir[index] = row


def strip_body(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "comment_id": row["comment_id"],
        "source_line": row["source_line"],
        "date_utc": row["date_utc"],
        "parent_kind": row["parent_kind"],
        "parent_comment_id": row["parent_comment_id"],
        "body_length": row["body_length"],
        "is_removed_or_deleted": row["is_removed_or_deleted"],
        "link_id": row["link_id"],
        "score": row["score"],
    }


def classify_row(row: dict[str, Any]) -> list[str]:
    body = row.get("body") or ""
    lower = body.lower()
    removed = bool(row["is_removed_or_deleted"])
    length = int(row["body_length"] or 0)
    parent_kind = row["parent_kind"]
    has_parent_comment_id = bool(row["parent_comment_id"])
    parent_available = bool(row["parent_available"])

    buckets = []
    if parent_kind == "post" and not removed and length >= 80:
        buckets.append("top_level")
    if parent_kind == "comment" and has_parent_comment_id and parent_available and not removed and length >= 40:
        buckets.append("reply_with_parent")
    if parent_kind == "comment" and has_parent_comment_id and not parent_available:
        buckets.append("missing_parent")
    if not removed and 1 <= length <= 40:
        buckets.append("short")
    if not removed and length >= 1000:
        buckets.append("long")
    if removed:
        buckets.append("removed_deleted")
    if not removed and any(
        token in lower
        for token in (
            "fatigue",
            "pain",
            "pots",
            "tachycardia",
            "brain fog",
            "shortness of breath",
        )
    ):
        buckets.append("likely_symptom")
    if not removed and any(
        token in lower
        for token in (
            "ldn",
            "antihistamine",
            "paxlovid",
            "ivermectin",
            "supplement",
            "medication",
            "electrolyte",
        )
    ):
        buckets.append("likely_treatment")
    if not removed and "?" in body and length < 300:
        buckets.append("question_only")
    if parent_kind == "comment" and not removed and any(
        token in lower for token in ("same", "me too", "this", "that", "it")
    ):
        buckets.append("context_reference")
    if not removed and any(
        token in lower
        for token in (
            "my husband",
            "my wife",
            "my friend",
            "my mom",
            "my dad",
            "my son",
            "my daughter",
        )
    ):
        buckets.append("other_person")
    if not removed and any(
        token in lower
        for token in (
            "you should",
            "people should",
            "try ",
            "doctor",
            "does anyone",
        )
    ):
        buckets.append("advice_meta")
    if length > 0:
        buckets.append("fallback_general")

    return buckets


def choose_rows(
    candidates: list[dict[str, Any]],
    *,
    count: int,
    seed: int,
    bucket_name: str,
    sample_name: str,
    used: set[str],
) -> list[dict[str, Any]]:
    pool = [row for row in candidates if row["comment_id"] not in used]
    rng = random.Random(stable_seed(seed, f"{sample_name}:{bucket_name}"))
    rng.shuffle(pool)
    selected = []
    for row in pool[:count]:
        used.add(row["comment_id"])
        selected.append(format_sample_row(row, sample_name, bucket_name, seed))
    return selected


def format_sample_row(
    row: dict[str, Any],
    sample_name: str,
    bucket_name: str,
    seed: int,
) -> dict[str, Any]:
    return {
        "sample": sample_name,
        "selection_bucket": bucket_name,
        "selection_seed": seed,
        "comment_id": row["comment_id"],
        "source_line": row["source_line"],
        "date_utc": row["date_utc"],
        "parent_kind": row["parent_kind"],
        "parent_comment_id": row["parent_comment_id"],
        "body_length": row["body_length"],
        "is_removed_or_deleted": bool(row["is_removed_or_deleted"]),
        "link_id": row["link_id"],
        "score": row["score"],
    }


def build_sample(
    candidates: dict[str, list[dict[str, Any]]],
    spec: SampleSpec,
    *,
    seed: int,
) -> list[dict[str, Any]]:
    used: set[str] = set()
    rows: list[dict[str, Any]] = []

    for bucket_name, count in spec.quotas.items():
        rows.extend(
            choose_rows(
                candidates[bucket_name],
                count=count,
                seed=seed,
                bucket_name=bucket_name,
                sample_name=spec.name,
                used=used,
            )
        )

    if len(rows) < spec.total:
        rows.extend(
            choose_rows(
                candidates["fallback_general"],
                count=spec.total - len(rows),
                seed=seed,
                bucket_name="fallback_general",
                sample_name=spec.name,
                used=used,
            )
        )

    rows = rows[: spec.total]
    rows.sort(key=lambda row: (row["date_utc"] or "", row["source_line"]))
    return rows


def write_samples(
    *,
    db: Path,
    output_dir: Path,
    samples: list[str],
    seed: int,
    candidate_limit: int,
    replace: bool,
) -> None:
    require_file(db, "context database")
    output_dir.mkdir(parents=True, exist_ok=True)

    with connect(db) as conn:
        print("scanning comments once to build sample reservoirs...", flush=True)
        candidates = scan_candidates(conn, candidate_limit=candidate_limit, seed=seed)
        for bucket_name in sorted(candidates):
            print(f"  candidates[{bucket_name}]={len(candidates[bucket_name])}", flush=True)
        for sample_name in samples:
            spec = SAMPLE_SPECS[sample_name]
            rows = build_sample(candidates, spec, seed=seed)
            path = output_dir / SAMPLE_FILES[sample_name].name
            if path.exists() and not replace:
                raise SystemExit(f"ERROR: sample already exists, pass --replace: {path}")
            count = write_jsonl(path, rows)
            by_bucket = Counter(row["selection_bucket"] for row in rows)
            print(f"wrote {count} rows to {path}")
            for bucket_name, bucket_count in sorted(by_bucket.items()):
                print(f"  {bucket_name}: {bucket_count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select deterministic ID-only A1 sample manifests.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=SAMPLES_DIR)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--candidate-limit", type=int, default=DEFAULT_CANDIDATE_LIMIT)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument(
        "--sample",
        action="append",
        choices=sorted(SAMPLE_SPECS),
        help="Sample to generate. Repeatable. Defaults to all.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    write_samples(
        db=args.db,
        output_dir=args.output_dir,
        samples=args.sample or list(SAMPLE_SPECS),
        seed=args.seed,
        candidate_limit=args.candidate_limit,
        replace=args.replace,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
