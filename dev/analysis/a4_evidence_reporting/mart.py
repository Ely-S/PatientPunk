"""SQLite evidence mart builder for A4."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from dev.analysis.a3_result_analysis.normalization import CLAIM_BASE_COLUMNS
from dev.analysis.a4_evidence_reporting.common import canonical_json, union_columns
from dev.analysis.a4_evidence_reporting.findings import FINDING_CARD_COLUMNS
from dev.analysis.a4_evidence_reporting.quotes import QUOTE_BANK_COLUMNS


CLAIM_COLUMNS = CLAIM_BASE_COLUMNS + [
    "normalized_label_clean",
    "analysis_bucket",
    "normalization_version",
    "normalization_rule",
    "normalization_review_status",
    "normalization_notes",
]


def build_evidence_mart(
    *,
    path: Path,
    report_manifest_rows: list[dict[str, Any]],
    source_a3_rows: list[dict[str, Any]],
    source_file_rows: list[dict[str, Any]],
    data,
    findings: list[dict[str, Any]],
    quote_bank: list[dict[str, Any]],
    caveats: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        _write_table(conn, "report_manifest", report_manifest_rows)
        _write_table(conn, "source_a3_analyses", source_a3_rows)
        _write_table(conn, "source_files", source_file_rows)
        _write_table(conn, "denominators", data.denominators)
        _write_table(conn, "comments", data.comments)
        _write_table(conn, "claims", data.claims, union_columns(data.claims, CLAIM_COLUMNS))
        _write_table(conn, "claim_label_frequency", data.claim_label_frequency)
        _write_table(conn, "reportability", data.reportability)
        _write_table(conn, "quote_bank", quote_bank, QUOTE_BANK_COLUMNS)
        _write_table(conn, "finding_cards", findings, FINDING_CARD_COLUMNS)
        _write_table(conn, "caveats", caveats)
        _create_indexes(conn)
        conn.commit()
    finally:
        conn.close()


def _write_table(conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    columns = columns or union_columns(rows, ["key", "value"])
    safe_cols = [_safe_identifier(column) for column in columns]
    conn.execute(f"DROP TABLE IF EXISTS {_safe_identifier(table)}")
    conn.execute(
        f"CREATE TABLE {_safe_identifier(table)} ("
        + ", ".join(f"{column} TEXT" for column in safe_cols)
        + ")"
    )
    if not rows:
        return
    placeholders = ", ".join("?" for _ in safe_cols)
    sql = f"INSERT INTO {_safe_identifier(table)} ({', '.join(safe_cols)}) VALUES ({placeholders})"
    for row in rows:
        conn.execute(sql, [_cell(row.get(column, "")) for column in columns])


def _create_indexes(conn: sqlite3.Connection) -> None:
    for table, column in [
        ("claims", "claim_id"),
        ("claims", "comment_id"),
        ("claims", "normalized_label_canonical"),
        ("comments", "comment_id"),
        ("quote_bank", "claim_id"),
        ("finding_cards", "finding_id"),
    ]:
        try:
            conn.execute(f"CREATE INDEX idx_{table}_{column} ON {table}({column})")
        except sqlite3.OperationalError:
            pass


def _safe_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        return canonical_json(value)
    return str(value)
