"""Shared paths, JSON, and hashing helpers for A2 batch extraction."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from dev.analysis.a0_extraction.comment_context import DEFAULT_DB
from dev.analysis.a1_coding_research.scripts.common import SAMPLE_FILES
from dev.analysis.agents.CommentCoderAgent.manifest import TASK_NAME


REPO_ROOT = Path(__file__).resolve().parents[3]
A2_DIR = REPO_ROOT / "dev" / "analysis" / "a2_batch_extraction"
DERIVED_A2_DIR = DEFAULT_DB.parent / "a2_batch_extraction"
DEFAULT_RUN_ROOT = DERIVED_A2_DIR / "runs" / TASK_NAME


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def utc_now_compact() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def require_file(path: Path, label: str) -> Path:
    if not path.exists():
        raise SystemExit(f"ERROR: {label} not found: {path}")
    return path


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


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


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def canonical_json_pretty(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_text(canonical_json(value))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sample_path(sample: str, sample_file: Path | None = None) -> Path:
    if sample_file is not None:
        return sample_file
    try:
        return SAMPLE_FILES[sample]
    except KeyError as exc:
        raise SystemExit(f"Unknown sample {sample!r}. Expected one of {sorted(SAMPLE_FILES)}") from exc


def json_dumps_db(value: Any) -> str:
    return canonical_json(value)


def json_loads_db(value: str | None, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    return json.loads(value)


def row_dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}

