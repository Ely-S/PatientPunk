"""Shared helpers for A1 scripts."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dev.analysis.a0_extraction.comment_context import DEFAULT_DB  # noqa: E402


A1_DIR = REPO_ROOT / "dev" / "analysis" / "a1_coding_research"
SAMPLES_DIR = A1_DIR / "samples"
DERIVED_A1_DIR = DEFAULT_DB.parent / "a1_coding_research"
RUNS_DIR = DERIVED_A1_DIR / "runs"

SAMPLE_FILES = {
    "seed_review": SAMPLES_DIR / "seed_review_ids.jsonl",
    "prompt_dev": SAMPLES_DIR / "prompt_dev_ids.jsonl",
    "gold_holdout": SAMPLES_DIR / "gold_holdout_ids.jsonl",
    "adversarial_context": SAMPLES_DIR / "adversarial_context_ids.jsonl",
}


def utc_now_compact() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    ensure_parent(path)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
            count += 1
    return count


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def sample_path(sample: str, sample_file: Path | None = None) -> Path:
    if sample_file is not None:
        return sample_file
    try:
        return SAMPLE_FILES[sample]
    except KeyError as exc:
        raise SystemExit(f"Unknown sample {sample!r}. Expected one of {sorted(SAMPLE_FILES)}") from exc


def require_file(path: Path, label: str) -> Path:
    if not path.exists():
        raise SystemExit(f"ERROR: {label} not found: {path}")
    return path

