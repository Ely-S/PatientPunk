"""Validation for A2 outputs consumed by A3."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from dev.analysis.a3_result_analysis.common import (
    count_csv_rows,
    count_jsonl_rows,
    file_sha256,
    int_value,
    read_json,
    write_json,
)
from dev.analysis.a3_result_analysis.loaders import A2RunPaths, load_a2_export_data


REQUIRED_EXPORTS = [
    "export_manifest.json",
    "run_manifest.json",
    "run_report.json",
    "comment_rows.csv",
    "claim_rows.csv",
    "attempts.csv",
    "failed_items.csv",
    "results.jsonl",
]


def validate_a2_run(paths: A2RunPaths, *, output_path: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    exports = paths.exports_dir

    if not exports.exists():
        errors.append(f"exports directory not found: {exports}")
        result = _result(paths, errors, warnings, {})
        _maybe_write(output_path, result)
        return result

    for name in REQUIRED_EXPORTS:
        if not (exports / name).exists():
            errors.append(f"required export missing: {name}")

    if errors:
        result = _result(paths, errors, warnings, {})
        _maybe_write(output_path, result)
        return result

    export_manifest = read_json(exports / "export_manifest.json")
    files = export_manifest.get("files") or {}
    row_counts: dict[str, int] = {}
    hash_checks: dict[str, str] = {}
    for name, info in files.items():
        path = exports / name
        if not path.exists():
            errors.append(f"manifest-listed file missing: {name}")
            continue
        actual_hash = file_sha256(path)
        expected_hash = info.get("sha256")
        hash_checks[name] = actual_hash
        if expected_hash and actual_hash != expected_hash:
            errors.append(f"hash mismatch for {name}: expected {expected_hash}, got {actual_hash}")
        expected_rows = info.get("row_count")
        if expected_rows is not None:
            actual_rows = _count_rows(path)
            row_counts[name] = actual_rows
            if actual_rows != int(expected_rows):
                errors.append(f"row count mismatch for {name}: expected {expected_rows}, got {actual_rows}")

    data = load_a2_export_data(paths)
    comment_count = len(data.comments)
    claim_count = len(data.claims)
    attempt_count = len(data.attempts)
    result_count = len(data.results)
    failed_count = len(data.failed_items)

    if data.run_report.get("total_work_items") is not None and comment_count != int_value(data.run_report["total_work_items"]):
        errors.append(
            "comment_rows.csv row count does not match run_report.total_work_items: "
            f"{comment_count} vs {data.run_report['total_work_items']}"
        )
    if data.run_report.get("claim_count") is not None and claim_count != int_value(data.run_report["claim_count"]):
        errors.append(
            "claim_rows.csv row count does not match run_report.claim_count: "
            f"{claim_count} vs {data.run_report['claim_count']}"
        )
    if data.run_report.get("attempt_count") is not None and attempt_count != int_value(data.run_report["attempt_count"]):
        errors.append(
            "attempts.csv row count does not match run_report.attempt_count: "
            f"{attempt_count} vs {data.run_report['attempt_count']}"
        )
    if data.run_report.get("result_count") is not None and result_count != int_value(data.run_report["result_count"]):
        errors.append(
            "results.jsonl row count does not match run_report.result_count: "
            f"{result_count} vs {data.run_report['result_count']}"
        )

    claim_ids = [row.get("claim_id", "") for row in data.claims if row.get("claim_id")]
    if len(claim_ids) != len(set(claim_ids)):
        errors.append("duplicate claim_id values found in claim_rows.csv")

    evidence_violations = [row for row in data.claims if row.get("evidence_source") != "target_comment"]
    if evidence_violations:
        errors.append(f"{len(evidence_violations)} claim rows have evidence_source other than target_comment")

    codeable_zero_claim = [
        row
        for row in data.comments
        if str(row.get("is_codeable", "")).strip() in {"1", "true", "True"}
        and int_value(row.get("claim_count")) == 0
        and row.get("status") == "succeeded"
    ]
    if codeable_zero_claim:
        errors.append(f"{len(codeable_zero_claim)} codeable succeeded comments have zero claims")

    if comment_count and claim_count == 0 and result_count == 0:
        warnings.append("dry-only or no-result run: no result or claim rows found")

    db_counts = _db_counts(paths.run_db) if paths.run_db is not None else {}
    if db_counts:
        if db_counts.get("work_items") != comment_count:
            errors.append(f"DB work_items count {db_counts.get('work_items')} != exported comment rows {comment_count}")
        if db_counts.get("claim_rows") != claim_count:
            errors.append(f"DB claim_rows count {db_counts.get('claim_rows')} != exported claim rows {claim_count}")
        if db_counts.get("attempts") != attempt_count:
            errors.append(f"DB attempts count {db_counts.get('attempts')} != exported attempt rows {attempt_count}")
        if db_counts.get("results") != result_count:
            errors.append(f"DB results count {db_counts.get('results')} != exported result rows {result_count}")

    details = {
        "row_counts": {
            "comment_rows.csv": comment_count,
            "claim_rows.csv": claim_count,
            "attempts.csv": attempt_count,
            "failed_items.csv": failed_count,
            "results.jsonl": result_count,
        },
        "manifest_row_counts": row_counts,
        "db_counts": db_counts,
        "hash_checks": hash_checks,
    }
    result = _result(paths, errors, warnings, details)
    _maybe_write(output_path, result)
    return result


def _count_rows(path: Path) -> int:
    if path.suffix.lower() == ".jsonl":
        return count_jsonl_rows(path)
    if path.suffix.lower() == ".csv":
        return count_csv_rows(path)
    return 0


def _db_counts(path: Path | None) -> dict[str, int]:
    if path is None or not path.exists():
        return {}
    conn = sqlite3.connect(path)
    try:
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ["work_items", "results", "claim_rows", "attempts"]
        }
    finally:
        conn.close()


def _result(paths: A2RunPaths, errors: list[str], warnings: list[str], details: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": not errors,
        "run_id": paths.run_id,
        "run_dir": str(paths.run_dir) if paths.run_dir is not None else None,
        "exports_dir": str(paths.exports_dir),
        "errors": errors,
        "warnings": warnings,
        "details": details,
    }


def _maybe_write(path: Path | None, result: dict[str, Any]) -> None:
    if path is not None:
        write_json(path, result)

