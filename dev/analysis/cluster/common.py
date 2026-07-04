"""Shared helpers for comment clustering."""

from __future__ import annotations

import csv
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from dev.analysis.a0_extraction.comment_context import DEFAULT_DB


REPO_ROOT = Path(__file__).resolve().parents[3]
DERIVED_CLUSTER_DIR = DEFAULT_DB.parent / "cluster"
DEFAULT_CLUSTER_ROOT = DERIVED_CLUSTER_DIR / "runs"
CLUSTER_VERSION = "comment_cluster_v0.1"


def utc_now_compact() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def canonical_json_pretty(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(canonical_json_pretty(payload), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    ensure_parent(path)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(canonical_json(row) + "\n")
            count += 1
    return count


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str] | None = None) -> int:
    rows = list(rows)
    if fieldnames is None:
        fieldnames = union_columns(rows)
    ensure_parent(path)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def union_columns(rows: Iterable[dict[str, Any]], fallback: list[str] | None = None) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns or list(fallback or [])


def slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unnamed"


def resolve_evidence_mart(a4_report: Path) -> Path:
    if a4_report.is_dir():
        return a4_report / "evidence_mart.sqlite"
    return a4_report
