"""SQLite storage primitives for A2 batch extraction runs."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from dev.analysis.a2_batch_extraction.common import json_dumps_db, json_loads_db, utc_now_iso


RUN_DB_NAME = "run.sqlite"


def db_path_for_run(run_dir: Path) -> Path:
    return run_dir / RUN_DB_NAME


def connect_run_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS run_manifest (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS work_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            source_line INTEGER NOT NULL,
            comment_id TEXT NOT NULL,
            post_id TEXT,
            link_id TEXT,
            parent_kind TEXT,
            parent_comment_id TEXT,
            date_utc TEXT,
            year_month TEXT,
            body_length INTEGER NOT NULL DEFAULT 0,
            is_removed_or_deleted INTEGER NOT NULL DEFAULT 0,
            sample TEXT,
            selection_bucket TEXT,
            selection_source TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            context_available_count INTEGER,
            context_comment_ids_available_json TEXT,
            missing_context_json TEXT,
            render_config_json TEXT,
            context_hash TEXT,
            prompt_message_hash TEXT,
            prompt_message_chars INTEGER,
            result_hash TEXT,
            error_type TEXT,
            error_message TEXT,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            UNIQUE(run_id, source_line)
        );

        CREATE INDEX IF NOT EXISTS idx_work_items_status ON work_items(status, id);
        CREATE INDEX IF NOT EXISTS idx_work_items_comment_id ON work_items(comment_id);
        CREATE INDEX IF NOT EXISTS idx_work_items_source_line ON work_items(source_line);

        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_item_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
            attempt_number INTEGER NOT NULL,
            model TEXT NOT NULL,
            agent_id TEXT,
            started_at_utc TEXT NOT NULL,
            finished_at_utc TEXT,
            latency_seconds REAL,
            status TEXT NOT NULL,
            error_type TEXT,
            error_message TEXT,
            traceback TEXT,
            context_hash TEXT,
            prompt_message_hash TEXT,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            cost_usd REAL,
            metadata_json TEXT,
            UNIQUE(work_item_id, attempt_number)
        );

        CREATE INDEX IF NOT EXISTS idx_attempts_work_item ON attempts(work_item_id);

        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_item_id INTEGER NOT NULL UNIQUE REFERENCES work_items(id) ON DELETE CASCADE,
            run_id TEXT NOT NULL,
            comment_id TEXT NOT NULL,
            source_line INTEGER NOT NULL,
            model TEXT NOT NULL,
            agent_id TEXT,
            prompt_version TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            result_json TEXT NOT NULL,
            result_hash TEXT NOT NULL,
            is_codeable INTEGER NOT NULL,
            skip_reason TEXT,
            claim_count INTEGER NOT NULL,
            used_context INTEGER NOT NULL,
            context_comment_ids_used_json TEXT NOT NULL,
            attribution_confidence TEXT NOT NULL,
            ambiguity_notes TEXT,
            latency_seconds REAL,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            cost_usd REAL,
            deterministic INTEGER NOT NULL DEFAULT 0,
            created_at_utc TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_results_comment_id ON results(comment_id);

        CREATE TABLE IF NOT EXISTS claim_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            result_id INTEGER NOT NULL REFERENCES results(id) ON DELETE CASCADE,
            work_item_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
            run_id TEXT NOT NULL,
            source_line INTEGER NOT NULL,
            comment_id TEXT NOT NULL,
            claim_index INTEGER NOT NULL,
            claim_id TEXT NOT NULL,
            claim_stable_id TEXT NOT NULL,
            claim_hash TEXT NOT NULL,
            claim_type TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            normalized_label TEXT,
            normalized_label_canonical TEXT,
            experiencer TEXT NOT NULL,
            assertion TEXT NOT NULL,
            confidence TEXT NOT NULL,
            evidence_quote TEXT NOT NULL,
            evidence_source TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            used_context INTEGER NOT NULL,
            context_comment_ids_used_json TEXT NOT NULL,
            attribution_confidence TEXT NOT NULL,
            date_utc TEXT,
            year_month TEXT,
            parent_kind TEXT,
            body_length INTEGER,
            model TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            UNIQUE(run_id, source_line, claim_index)
        );

        CREATE INDEX IF NOT EXISTS idx_claim_rows_claim_id ON claim_rows(claim_id);
        CREATE INDEX IF NOT EXISTS idx_claim_rows_type ON claim_rows(claim_type);

        CREATE TABLE IF NOT EXISTS rendered_inputs (
            work_item_id INTEGER PRIMARY KEY REFERENCES work_items(id) ON DELETE CASCADE,
            context_hash TEXT NOT NULL,
            prompt_message_hash TEXT NOT NULL,
            render_config_json TEXT NOT NULL,
            prompt_message_chars INTEGER NOT NULL,
            rendered_context TEXT,
            prompt_message TEXT,
            store_raw INTEGER NOT NULL DEFAULT 0,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_comment_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            work_item_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
            comment_id TEXT NOT NULL,
            source_line INTEGER NOT NULL,
            correct INTEGER,
            wrong_skip INTEGER,
            missed_claim INTEGER,
            over_extracted_claim INTEGER,
            parent_context_leakage INTEGER,
            wrong_experiencer INTEGER,
            wrong_negation INTEGER,
            unsupported_evidence INTEGER,
            context_needed_but_not_used INTEGER,
            context_used_but_not_needed INTEGER,
            confidence_too_high INTEGER,
            ambiguous_not_marked INTEGER,
            notes TEXT,
            reviewer TEXT,
            reviewed_at_utc TEXT,
            UNIQUE(run_id, source_line, reviewer)
        );

        CREATE TABLE IF NOT EXISTS audit_claim_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            claim_id TEXT NOT NULL,
            claim_hash TEXT NOT NULL,
            correct INTEGER,
            wrong_claim_type INTEGER,
            wrong_label INTEGER,
            wrong_experiencer INTEGER,
            wrong_assertion INTEGER,
            unsupported_evidence INTEGER,
            duplicate_claim INTEGER,
            should_be_split INTEGER,
            should_be_merged INTEGER,
            confidence_too_high INTEGER,
            notes TEXT,
            reviewer TEXT,
            reviewed_at_utc TEXT,
            UNIQUE(run_id, claim_id, reviewer)
        );
        """
    )


def put_manifest(conn: sqlite3.Connection, manifest: dict[str, Any]) -> None:
    with conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO run_manifest(key, value_json)
            VALUES (?, ?)
            """,
            [(key, json_dumps_db(value)) for key, value in manifest.items()],
        )


def get_manifest(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute("SELECT key, value_json FROM run_manifest ORDER BY key").fetchall()
    return {row["key"]: json_loads_db(row["value_json"]) for row in rows}


def insert_work_items(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    now = utc_now_iso()
    payload = []
    for row in rows:
        payload.append(
            (
                row["run_id"],
                row["source_line"],
                row["comment_id"],
                row.get("post_id"),
                row.get("link_id"),
                row.get("parent_kind"),
                row.get("parent_comment_id"),
                row.get("date_utc"),
                row.get("year_month"),
                row.get("body_length", 0),
                int(row.get("is_removed_or_deleted", False)),
                row.get("sample"),
                row.get("selection_bucket"),
                row.get("selection_source"),
                now,
                now,
            )
        )

    with conn:
        conn.executemany(
            """
            INSERT INTO work_items(
                run_id, source_line, comment_id, post_id, link_id, parent_kind,
                parent_comment_id, date_utc, year_month, body_length,
                is_removed_or_deleted, sample, selection_bucket, selection_source,
                created_at_utc, updated_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
    return len(payload)


def status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT status, COUNT(*) AS count FROM work_items GROUP BY status ORDER BY status"
    ).fetchall()
    return {row["status"]: row["count"] for row in rows}


def scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None

