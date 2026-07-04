"""Core A2 batch extraction operations."""

from __future__ import annotations

import csv
import inspect
import json
import sqlite3
import statistics
import traceback
from pathlib import Path
from typing import Any, Iterable

from dev.analysis.a0_extraction.comment_context import DEFAULT_DB, Comment, CommentStore
from dev.analysis.a2_batch_extraction.common import (
    DEFAULT_RUN_ROOT,
    canonical_json,
    file_sha256,
    json_dumps_db,
    json_loads_db,
    read_jsonl,
    require_file,
    row_dict,
    sample_path,
    sha256_json,
    utc_now_compact,
    utc_now_iso,
    write_json,
)
from dev.analysis.a2_batch_extraction.storage import (
    connect_run_db,
    create_schema,
    db_path_for_run,
    get_manifest,
    insert_work_items,
    put_manifest,
    scalar,
    status_counts,
)
from dev.analysis.agents.CommentCoderAgent.api import code_comment_with_metadata
from dev.analysis.agents.CommentCoderAgent.brain.prompts import PROMPT_PATH, PROMPT_VERSION, build_message
from dev.analysis.agents.CommentCoderAgent.manifest import DEFAULT_MODEL, TASK_NAME, manifest as agent_manifest
from dev.analysis.agents.CommentCoderAgent.schemas import CommentCodingResult
from dev.analysis.agents._common.render_context import (
    CONTEXT_RENDERER_VERSION,
    ContextRenderConfig,
    context_comment_ids,
    render_context_for_prompt,
    stable_text_hash,
)
from dev.analysis.agents._common.runtime import analysis_world


MAX_LIVE_LIMIT_WITHOUT_OVERRIDE = 25
COMMENT_AUDIT_COLUMNS = [
    "run_id",
    "source_line",
    "comment_id",
    "status",
    "is_codeable",
    "skip_reason",
    "claim_count",
    "correct",
    "wrong_skip",
    "missed_claim",
    "over_extracted_claim",
    "parent_context_leakage",
    "wrong_experiencer",
    "wrong_negation",
    "unsupported_evidence",
    "context_needed_but_not_used",
    "context_used_but_not_needed",
    "confidence_too_high",
    "ambiguous_not_marked",
    "notes",
    "reviewer",
]
CLAIM_AUDIT_COLUMNS = [
    "run_id",
    "claim_id",
    "source_line",
    "comment_id",
    "claim_type",
    "raw_text",
    "normalized_label",
    "experiencer",
    "assertion",
    "confidence",
    "evidence_quote",
    "correct",
    "wrong_claim_type",
    "wrong_label",
    "wrong_experiencer",
    "wrong_assertion",
    "unsupported_evidence",
    "duplicate_claim",
    "should_be_split",
    "should_be_merged",
    "confidence_too_high",
    "notes",
    "reviewer",
]


def context_config_from_values(
    *,
    ancestor_depth: int = 2,
    previous_sibling_limit: int = 2,
    previous_thread_limit: int = 3,
    max_body_chars: int = 1200,
    max_total_chars: int = 16000,
) -> ContextRenderConfig:
    return ContextRenderConfig(
        ancestor_depth=ancestor_depth,
        previous_sibling_limit=previous_sibling_limit,
        previous_thread_limit=previous_thread_limit,
        max_body_chars=max_body_chars,
        max_total_chars=max_total_chars,
    )


def context_config_from_manifest(manifest: dict[str, Any]) -> ContextRenderConfig:
    config = dict(manifest["context_render_config"])
    config.pop("renderer_version", None)
    return ContextRenderConfig(**config)


def build_instrument_hashes(*, model: str, config: ContextRenderConfig) -> dict[str, str]:
    schema_payload = CommentCodingResult.model_json_schema()
    schema_hash = sha256_json(schema_payload)
    prompt_payload = {
        "prompt_version": PROMPT_VERSION,
        "prompt_path": str(PROMPT_PATH),
        "prompt_text": PROMPT_PATH.read_text(encoding="utf-8"),
        "build_message_source": inspect.getsource(build_message),
        "schema_hash": schema_hash,
        "context_renderer_version": CONTEXT_RENDERER_VERSION,
    }
    prompt_hash = sha256_json(prompt_payload)
    instrument_payload = {
        "agent_manifest": agent_manifest(),
        "model": model,
        "context_render_config": config.as_dict(),
        "schema_hash": schema_hash,
        "prompt_hash": prompt_hash,
    }
    return {
        "schema_hash": schema_hash,
        "prompt_hash": prompt_hash,
        "instrument_hash": sha256_json(instrument_payload),
    }


def create_run(
    *,
    db: Path = DEFAULT_DB,
    sample: str | None = "prompt_dev",
    sample_file: Path | None = None,
    where_sql: str = "",
    order: str = "created_utc, id",
    limit: int | None = None,
    run_root: Path = DEFAULT_RUN_ROOT,
    run_id: str | None = None,
    model: str = DEFAULT_MODEL,
    config: ContextRenderConfig | None = None,
    allow_large_selection: bool = False,
) -> Path:
    require_file(db, "context database")
    config = config or ContextRenderConfig()

    selection_name = sample if sample or sample_file else "sql"
    if limit is None and not sample_file and not sample:
        raise SystemExit("ERROR: --limit is required for SQL selections.")
    if limit is not None and limit <= 0:
        raise SystemExit("ERROR: --limit must be positive.")
    if limit is not None and limit > 1000 and not allow_large_selection:
        raise SystemExit("ERROR: selections over 1000 rows require --allow-large-selection.")

    run_id = run_id or f"{utc_now_compact()}_{selection_name}_{limit or 'all'}"
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    run_db = db_path_for_run(run_dir)

    hashes = build_instrument_hashes(model=model, config=config)
    selection_definition = {
        "sample": sample,
        "sample_file": str(sample_file) if sample_file else None,
        "where_sql": where_sql,
        "order": order,
        "limit": limit,
    }
    manifest = agent_manifest() | {
        "run_id": run_id,
        "task_name": TASK_NAME,
        "mode": "created",
        "created_at_utc": utc_now_iso(),
        "db": str(db),
        "model": model,
        "selection_definition": selection_definition,
        "context_render_config": config.as_dict(),
        **hashes,
    }

    conn = connect_run_db(run_db)
    try:
        create_schema(conn)
        put_manifest(conn, manifest)
        rows = select_work_items(
            db=db,
            run_id=run_id,
            sample=sample,
            sample_file=sample_file,
            where_sql=where_sql,
            order=order,
            limit=limit,
        )
        count = insert_work_items(conn, rows)
        put_manifest(conn, manifest | {"selected_count": count})
    finally:
        conn.close()

    write_json(run_dir / "manifest.json", manifest | {"selected_count": len(rows)})
    print(f"created A2 run: {run_dir}")
    print(f"selected work items: {len(rows)}")
    return run_dir


def select_work_items(
    *,
    db: Path,
    run_id: str,
    sample: str | None,
    sample_file: Path | None,
    where_sql: str,
    order: str,
    limit: int | None,
) -> list[dict[str, Any]]:
    with CommentStore(db) as store:
        if sample or sample_file:
            path = require_file(sample_path(sample or "custom", sample_file), "sample file")
            sample_rows = read_jsonl(path)
            rows = sample_rows if limit is None else sample_rows[:limit]
            selected: list[dict[str, Any]] = []
            for row in rows:
                comment = None
                if row.get("source_line") is not None:
                    comment = store.get_comment_by_source_line(int(row["source_line"]))
                if comment is None and row.get("comment_id"):
                    comment = store.get_comment(str(row["comment_id"]))
                if comment is None:
                    raise RuntimeError(f"Comment not found for sample row: {row}")
                selected.append(
                    comment_to_work_item(
                        comment,
                        run_id=run_id,
                        selection_source=str(path),
                        sample=row.get("sample") or sample,
                        selection_bucket=row.get("selection_bucket"),
                    )
                )
            return selected

        selected = []
        for comment in store.iter_comments(limit=limit, where_sql=where_sql, order=order):
            selected.append(
                comment_to_work_item(
                    comment,
                    run_id=run_id,
                    selection_source="comments.sqlite",
                    sample=None,
                    selection_bucket="sql_selection",
                )
            )
        return selected


def comment_to_work_item(
    comment: Comment,
    *,
    run_id: str,
    selection_source: str,
    sample: str | None,
    selection_bucket: str | None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "source_line": comment.source_line,
        "comment_id": comment.id,
        "post_id": comment.post_id,
        "link_id": comment.link_id,
        "parent_kind": comment.parent_kind,
        "parent_comment_id": comment.parent_comment_id,
        "date_utc": comment.date_utc,
        "year_month": comment.date_utc[:7] if comment.date_utc else "",
        "body_length": comment.body_length,
        "is_removed_or_deleted": is_removed_or_deleted_body(comment.body),
        "sample": sample,
        "selection_bucket": selection_bucket,
        "selection_source": selection_source,
    }


def dry_render_run(
    *,
    run_dir: Path,
    limit: int | None = None,
    store_raw: bool = True,
) -> int:
    conn = connect_run_db(db_path_for_run(run_dir))
    try:
        manifest = get_manifest(conn)
        config = context_config_from_manifest(manifest)
        rows = eligible_rows(conn, statuses=("pending", "dry_rendered", "failed"), limit=limit)
        rendered = 0
        with CommentStore(Path(manifest["db"])) as store:
            for row in rows:
                render = render_for_work_item(store, row, config)
                save_rendered_input(conn, row, render, store_raw=store_raw)
                status = "dry_rendered" if row["status"] in {"pending", "failed"} else row["status"]
                update_work_item_status(conn, row["id"], status, clear_error=True)
                rendered += 1
        print(f"dry-rendered rows: {rendered}")
        return rendered
    finally:
        conn.close()


def live_run(
    *,
    run_dir: Path,
    limit: int | None = None,
    model: str | None = None,
    max_attempts: int = 2,
    workers: int = 1,
    store_raw: bool = True,
    allow_large_live: bool = False,
    deterministic_skips: bool = True,
) -> int:
    if workers != 1:
        raise SystemExit("ERROR: A2 first-slice live runner supports --workers 1 only.")
    if max_attempts <= 0:
        raise SystemExit("ERROR: --max-attempts must be positive.")
    if limit is None:
        raise SystemExit("ERROR: live runs require --limit.")
    if limit > MAX_LIVE_LIMIT_WITHOUT_OVERRIDE and not allow_large_live:
        raise SystemExit(
            f"ERROR: live runs over {MAX_LIVE_LIMIT_WITHOUT_OVERRIDE} rows require --allow-large-live."
        )

    conn = connect_run_db(db_path_for_run(run_dir))
    try:
        manifest = get_manifest(conn)
        config = context_config_from_manifest(manifest)
        run_model = model or manifest["model"]
        rows = eligible_rows(
            conn,
            statuses=("pending", "dry_rendered", "failed"),
            limit=limit,
            max_attempts=max_attempts,
        )
        world = analysis_world(data_dir=run_dir / "rumi")
        successes = 0
        failures = 0
        deterministic = 0
        with CommentStore(Path(manifest["db"])) as store:
            for index, row in enumerate(rows, start=1):
                print(
                    f"[{index}/{len(rows)}] coding comment_id={row['comment_id']} "
                    f"source_line={row['source_line']}",
                    flush=True,
                )
                render = render_for_work_item(store, row, config)
                save_rendered_input(conn, row, render, store_raw=store_raw)

                if deterministic_skips and row["is_removed_or_deleted"]:
                    result = deterministic_skip_result(row)
                    save_result(
                        conn,
                        row,
                        result=result,
                        model="deterministic",
                        agent_id=None,
                        metadata={},
                        latency_seconds=0.0,
                        deterministic=True,
                    )
                    update_work_item_status(conn, row["id"], "deterministic_skipped", clear_error=True)
                    deterministic += 1
                    continue

                row_success = False
                attempt_start = int(row["attempt_count"] or 0) + 1
                for attempt_number in range(attempt_start, max_attempts + 1):
                    agent_id = f"{manifest['run_id']}-{row['source_line']}-a{attempt_number}"
                    started = utc_now_iso()
                    mark_running(conn, row["id"], attempt_number)
                    try:
                        response = code_comment_with_metadata(
                            render["rendered_context"],
                            target_comment_id=row["comment_id"],
                            source_line=row["source_line"],
                            model=run_model,
                            world=world,
                            agent_id=agent_id,
                        )
                        insert_attempt(
                            conn,
                            row,
                            attempt_number=attempt_number,
                            model=response.model,
                            agent_id=response.agent_id,
                            started_at_utc=started,
                            status="succeeded",
                            latency_seconds=response.latency_seconds,
                            metadata=response.metadata,
                            context_hash=render["context_hash"],
                            prompt_message_hash=render["prompt_message_hash"],
                        )
                        save_result(
                            conn,
                            row,
                            result=response.result,
                            model=response.model,
                            agent_id=response.agent_id,
                            metadata=response.metadata,
                            latency_seconds=response.latency_seconds,
                            deterministic=False,
                        )
                        update_work_item_status(conn, row["id"], "succeeded", clear_error=True)
                        successes += 1
                        row_success = True
                        break
                    except Exception as exc:
                        err_traceback = traceback.format_exc(limit=8)
                        insert_attempt(
                            conn,
                            row,
                            attempt_number=attempt_number,
                            model=run_model,
                            agent_id=agent_id,
                            started_at_utc=started,
                            status="failed",
                            latency_seconds=None,
                            metadata={},
                            context_hash=render["context_hash"],
                            prompt_message_hash=render["prompt_message_hash"],
                            error_type=type(exc).__name__,
                            error_message=str(exc),
                            error_traceback=err_traceback,
                        )
                        set_work_item_error(conn, row["id"], type(exc).__name__, str(exc))
                        if attempt_number < max_attempts:
                            print(
                                f"  attempt {attempt_number} failed: {type(exc).__name__}: {exc}; retrying",
                                flush=True,
                            )
                        else:
                            print(f"  FAILED: {type(exc).__name__}: {exc}", flush=True)
                if not row_success:
                    update_work_item_status(conn, row["id"], "failed", clear_error=False)
                    failures += 1

        print(
            f"live run complete: successes={successes} deterministic_skips={deterministic} failures={failures}",
            flush=True,
        )
        return 0 if failures == 0 else 1
    finally:
        conn.close()


def eligible_rows(
    conn: sqlite3.Connection,
    *,
    statuses: tuple[str, ...],
    limit: int | None,
    max_attempts: int | None = None,
) -> list[sqlite3.Row]:
    params: list[Any] = list(statuses)
    sql = f"""
        SELECT *
        FROM work_items
        WHERE status IN ({",".join("?" for _ in statuses)})
          AND id NOT IN (SELECT work_item_id FROM results)
    """
    if max_attempts is not None:
        sql += " AND attempt_count < ?"
        params.append(max_attempts)
    sql += " ORDER BY id"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return conn.execute(sql, tuple(params)).fetchall()


def render_for_work_item(
    store: CommentStore,
    row: sqlite3.Row,
    config: ContextRenderConfig,
) -> dict[str, Any]:
    comment = store.get_comment_by_source_line(int(row["source_line"]))
    if comment is None:
        raise RuntimeError(f"Comment not found for source_line={row['source_line']}")
    context = store.get_context(
        comment,
        ancestor_depth=config.ancestor_depth,
        previous_sibling_limit=config.previous_sibling_limit,
        previous_thread_limit=config.previous_thread_limit,
    )
    rendered_context = render_context_for_prompt(context, config)
    prompt_message = build_message(rendered_context)
    ids = context_comment_ids(context)
    return {
        "rendered_context": rendered_context,
        "prompt_message": prompt_message,
        "context_hash": stable_text_hash(rendered_context),
        "prompt_message_hash": stable_text_hash(prompt_message),
        "prompt_message_chars": len(prompt_message),
        "render_config": config.as_dict(),
        "context_comment_ids_available": ids,
        "missing_context": context.missing,
    }


def save_rendered_input(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    render: dict[str, Any],
    *,
    store_raw: bool,
) -> None:
    now = utc_now_iso()
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO rendered_inputs(
                work_item_id, context_hash, prompt_message_hash, render_config_json,
                prompt_message_chars, rendered_context, prompt_message, store_raw, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                render["context_hash"],
                render["prompt_message_hash"],
                json_dumps_db(render["render_config"]),
                render["prompt_message_chars"],
                render["rendered_context"] if store_raw else None,
                render["prompt_message"] if store_raw else None,
                int(store_raw),
                now,
            ),
        )
        conn.execute(
            """
            UPDATE work_items
            SET context_available_count = ?,
                context_comment_ids_available_json = ?,
                missing_context_json = ?,
                render_config_json = ?,
                context_hash = ?,
                prompt_message_hash = ?,
                prompt_message_chars = ?,
                updated_at_utc = ?
            WHERE id = ?
            """,
            (
                len(render["context_comment_ids_available"]),
                json_dumps_db(render["context_comment_ids_available"]),
                json_dumps_db(render["missing_context"]),
                json_dumps_db(render["render_config"]),
                render["context_hash"],
                render["prompt_message_hash"],
                render["prompt_message_chars"],
                now,
                row["id"],
            ),
        )


def update_work_item_status(
    conn: sqlite3.Connection,
    work_item_id: int,
    status: str,
    *,
    clear_error: bool,
) -> None:
    now = utc_now_iso()
    with conn:
        if clear_error:
            conn.execute(
                """
                UPDATE work_items
                SET status = ?, error_type = NULL, error_message = NULL, updated_at_utc = ?
                WHERE id = ?
                """,
                (status, now, work_item_id),
            )
        else:
            conn.execute(
                "UPDATE work_items SET status = ?, updated_at_utc = ? WHERE id = ?",
                (status, now, work_item_id),
            )


def mark_running(conn: sqlite3.Connection, work_item_id: int, attempt_number: int) -> None:
    with conn:
        conn.execute(
            """
            UPDATE work_items
            SET status = 'running', attempt_count = ?, updated_at_utc = ?
            WHERE id = ?
            """,
            (attempt_number, utc_now_iso(), work_item_id),
        )


def set_work_item_error(
    conn: sqlite3.Connection,
    work_item_id: int,
    error_type: str,
    error_message: str,
) -> None:
    with conn:
        conn.execute(
            """
            UPDATE work_items
            SET error_type = ?, error_message = ?, updated_at_utc = ?
            WHERE id = ?
            """,
            (error_type, truncate(error_message, 2000), utc_now_iso(), work_item_id),
        )


def insert_attempt(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    attempt_number: int,
    model: str,
    agent_id: str | None,
    started_at_utc: str,
    status: str,
    latency_seconds: float | None,
    metadata: dict[str, Any],
    context_hash: str,
    prompt_message_hash: str,
    error_type: str | None = None,
    error_message: str | None = None,
    error_traceback: str | None = None,
) -> None:
    usage = usage_from_metadata(metadata)
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO attempts(
                work_item_id, attempt_number, model, agent_id, started_at_utc, finished_at_utc,
                latency_seconds, status, error_type, error_message, traceback,
                context_hash, prompt_message_hash, prompt_tokens, completion_tokens,
                total_tokens, cost_usd, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                attempt_number,
                model,
                agent_id,
                started_at_utc,
                utc_now_iso(),
                latency_seconds,
                status,
                error_type,
                truncate(error_message or "", 2000) if error_message else None,
                error_traceback,
                context_hash,
                prompt_message_hash,
                usage["prompt_tokens"],
                usage["completion_tokens"],
                usage["total_tokens"],
                usage["cost_usd"],
                json_dumps_db(metadata),
            ),
        )


def save_result(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    result: CommentCodingResult,
    model: str,
    agent_id: str | None,
    metadata: dict[str, Any],
    latency_seconds: float,
    deterministic: bool,
) -> None:
    result_payload = result.model_dump(mode="json")
    result_hash = sha256_json(result_payload)
    usage = usage_from_metadata(metadata)
    now = utc_now_iso()
    with conn:
        conn.execute("DELETE FROM claim_rows WHERE work_item_id = ?", (row["id"],))
        conn.execute("DELETE FROM results WHERE work_item_id = ?", (row["id"],))
        cursor = conn.execute(
            """
            INSERT INTO results(
                work_item_id, run_id, comment_id, source_line, model, agent_id,
                prompt_version, schema_version, result_json, result_hash,
                is_codeable, skip_reason, claim_count, used_context,
                context_comment_ids_used_json, attribution_confidence, ambiguity_notes,
                latency_seconds, prompt_tokens, completion_tokens, total_tokens, cost_usd,
                deterministic, created_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["run_id"],
                result.comment_id,
                result.source_line,
                model,
                agent_id,
                result.prompt_version,
                result.schema_version,
                json_dumps_db(result_payload),
                result_hash,
                int(result.is_codeable),
                result.skip_reason.value if result.skip_reason else None,
                len(result.target_author_claims),
                int(result.used_context),
                json_dumps_db(result.context_comment_ids_used),
                result.attribution_confidence.value,
                result.ambiguity_notes,
                latency_seconds,
                usage["prompt_tokens"],
                usage["completion_tokens"],
                usage["total_tokens"],
                usage["cost_usd"],
                int(deterministic),
                now,
            ),
        )
        result_id = cursor.lastrowid
        insert_claim_rows(conn, row, result_id, result_payload, model)
        conn.execute(
            """
            UPDATE work_items
            SET result_hash = ?, updated_at_utc = ?
            WHERE id = ?
            """,
            (result_hash, now, row["id"]),
        )


def insert_claim_rows(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    result_id: int,
    result_payload: dict[str, Any],
    model: str,
) -> None:
    claims = result_payload.get("target_author_claims") or []
    payload = []
    for index, claim in enumerate(claims, start=1):
        evidence = claim.get("evidence") or []
        first_evidence = evidence[0] if evidence else {"quote": "", "source": ""}
        claim_id = f"{row['run_id']}:{row['source_line']}:{index}"
        claim_hash = sha256_json(
            {
                "source_line": row["source_line"],
                "claim_type": claim.get("claim_type"),
                "raw_text": claim.get("raw_text"),
                "normalized_label": claim.get("normalized_label"),
                "assertion": claim.get("assertion"),
                "evidence_quote": first_evidence.get("quote"),
            }
        )
        payload.append(
            (
                result_id,
                row["id"],
                row["run_id"],
                row["source_line"],
                row["comment_id"],
                index,
                claim_id,
                claim_id,
                claim_hash,
                claim.get("claim_type"),
                claim.get("raw_text"),
                claim.get("normalized_label"),
                None,
                claim.get("experiencer"),
                claim.get("assertion"),
                claim.get("confidence"),
                first_evidence.get("quote", ""),
                first_evidence.get("source", ""),
                json_dumps_db(evidence),
                int(result_payload.get("used_context", False)),
                json_dumps_db(result_payload.get("context_comment_ids_used") or []),
                result_payload.get("attribution_confidence"),
                row["date_utc"],
                row["year_month"],
                row["parent_kind"],
                row["body_length"],
                model,
                result_payload.get("schema_version"),
                result_payload.get("prompt_version"),
            )
        )

    if payload:
        conn.executemany(
            """
            INSERT INTO claim_rows(
                result_id, work_item_id, run_id, source_line, comment_id, claim_index,
                claim_id, claim_stable_id, claim_hash, claim_type, raw_text,
                normalized_label, normalized_label_canonical, experiencer, assertion,
                confidence, evidence_quote, evidence_source, evidence_json,
                used_context, context_comment_ids_used_json, attribution_confidence,
                date_utc, year_month, parent_kind, body_length, model,
                schema_version, prompt_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )


def deterministic_skip_result(row: sqlite3.Row) -> CommentCodingResult:
    return CommentCodingResult(
        schema_version="comment_coding_v0.1",
        prompt_version=PROMPT_VERSION,
        comment_id=row["comment_id"],
        source_line=int(row["source_line"]),
        is_codeable=False,
        skip_reason="removed_deleted",
        target_author_claims=[],
        used_context=False,
        context_comment_ids_used=[],
        attribution_confidence="high",
        ambiguity_notes="Target comment body is exactly [removed] or [deleted].",
    )


def summarize_run(*, run_dir: Path, write: bool = True) -> dict[str, Any]:
    conn = connect_run_db(db_path_for_run(run_dir))
    try:
        manifest = get_manifest(conn)
        counts = status_counts(conn)
        total = scalar(conn, "SELECT COUNT(*) FROM work_items") or 0
        attempt_count = scalar(conn, "SELECT COUNT(*) FROM attempts") or 0
        result_count = scalar(conn, "SELECT COUNT(*) FROM results") or 0
        claim_count = scalar(conn, "SELECT COUNT(*) FROM claim_rows") or 0
        failed_attempts = scalar(conn, "SELECT COUNT(*) FROM attempts WHERE status = 'failed'") or 0
        total_tokens = scalar(conn, "SELECT SUM(total_tokens) FROM attempts") or 0
        cost_usd = scalar(conn, "SELECT SUM(cost_usd) FROM attempts") or 0.0
        latencies = [
            row["latency_seconds"]
            for row in conn.execute(
                "SELECT latency_seconds FROM attempts WHERE latency_seconds IS NOT NULL"
            )
        ]
        claim_distribution = {
            str(row["claim_count"]): row["count"]
            for row in conn.execute(
                "SELECT claim_count, COUNT(*) AS count FROM results GROUP BY claim_count ORDER BY claim_count"
            )
        }
        error_counts = {
            row["error_type"]: row["count"]
            for row in conn.execute(
                """
                SELECT COALESCE(error_type, 'unknown') AS error_type, COUNT(*) AS count
                FROM attempts
                WHERE status = 'failed'
                GROUP BY COALESCE(error_type, 'unknown')
                ORDER BY count DESC
                """
            )
        }
        evidence_violations = (
            scalar(conn, "SELECT COUNT(*) FROM claim_rows WHERE evidence_source != 'target_comment'")
            or 0
        )
        non_deterministic_attempted = scalar(
            conn,
            """
            SELECT COUNT(DISTINCT work_item_id)
            FROM attempts
            """,
        ) or 0
        non_deterministic_successes = scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM results
            WHERE deterministic = 0
            """,
        ) or 0
        structured_success_rate = (
            non_deterministic_successes / non_deterministic_attempted
            if non_deterministic_attempted
            else None
        )
        report = {
            "run_id": manifest["run_id"],
            "run_dir": str(run_dir),
            "model": manifest["model"],
            "instrument_hash": manifest["instrument_hash"],
            "status_counts": counts,
            "total_work_items": total,
            "attempt_count": attempt_count,
            "failed_attempt_count": failed_attempts,
            "result_count": result_count,
            "claim_count": claim_count,
            "structured_success_rate": structured_success_rate,
            "total_tokens": total_tokens,
            "cost_usd": cost_usd,
            "median_latency_seconds": statistics.median(latencies) if latencies else None,
            "claim_count_distribution": claim_distribution,
            "error_counts": error_counts,
            "evidence_source_violations": evidence_violations,
            "generated_at_utc": utc_now_iso(),
        }
    finally:
        conn.close()

    if write:
        write_json(run_dir / "exports" / "run_report.json", report)
    return report


def inspect_run(*, run_dir: Path) -> dict[str, Any]:
    conn = connect_run_db(db_path_for_run(run_dir))
    try:
        manifest = get_manifest(conn)
        counts = status_counts(conn)
        summary = {
            "run_id": manifest["run_id"],
            "run_dir": str(run_dir),
            "model": manifest["model"],
            "instrument_hash": manifest["instrument_hash"],
            "status_counts": counts,
            "work_items": scalar(conn, "SELECT COUNT(*) FROM work_items") or 0,
            "attempts": scalar(conn, "SELECT COUNT(*) FROM attempts") or 0,
            "results": scalar(conn, "SELECT COUNT(*) FROM results") or 0,
            "claims": scalar(conn, "SELECT COUNT(*) FROM claim_rows") or 0,
        }
    finally:
        conn.close()
    return summary


def export_run(*, run_dir: Path) -> dict[str, Any]:
    exports_dir = run_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    conn = connect_run_db(db_path_for_run(run_dir))
    try:
        manifest = get_manifest(conn)
        write_json(exports_dir / "run_manifest.json", manifest)
        report = summarize_run(run_dir=run_dir, write=True)
        row_counts = {
            "comment_rows.csv": export_comment_rows(conn, exports_dir / "comment_rows.csv"),
            "claim_rows.csv": export_query(conn, "SELECT * FROM claim_rows ORDER BY source_line, claim_index", exports_dir / "claim_rows.csv"),
            "failed_items.csv": export_query(
                conn,
                "SELECT * FROM work_items WHERE status = 'failed' ORDER BY id",
                exports_dir / "failed_items.csv",
            ),
            "attempts.csv": export_query(conn, "SELECT * FROM attempts ORDER BY work_item_id, attempt_number", exports_dir / "attempts.csv"),
            "results.jsonl": export_results_jsonl(conn, exports_dir / "results.jsonl"),
        }
    finally:
        conn.close()

    audit_counts = select_audit_sample(run_dir=run_dir, limit_comments=25, limit_claims=50)
    row_counts["audit_comment_template.csv"] = audit_counts["comment_rows"]
    row_counts["audit_claim_template.csv"] = audit_counts["claim_rows"]
    export_paths = sorted(exports_dir.iterdir())
    manifest_payload = {
        "run_id": manifest["run_id"],
        "instrument_hash": manifest["instrument_hash"],
        "exported_at_utc": utc_now_iso(),
        "run_report": report,
        "files": {
            path.name: {
                "sha256": file_sha256(path),
                "bytes": path.stat().st_size,
                "row_count": row_counts.get(path.name),
            }
            for path in export_paths
            if path.is_file() and path.name != "export_manifest.json"
        },
    }
    write_json(exports_dir / "export_manifest.json", manifest_payload)
    return manifest_payload


def export_comment_rows(conn: sqlite3.Connection, path: Path) -> int:
    sql = """
        SELECT
            w.run_id,
            w.source_line,
            w.comment_id,
            w.post_id,
            w.link_id,
            w.date_utc,
            w.year_month,
            w.parent_kind,
            w.parent_comment_id,
            w.body_length,
            w.is_removed_or_deleted,
            w.status,
            r.is_codeable,
            r.skip_reason,
            COALESCE(r.claim_count, 0) AS claim_count,
            r.used_context,
            w.context_available_count,
            r.context_comment_ids_used_json,
            w.missing_context_json,
            r.attribution_confidence,
            r.ambiguity_notes,
            r.result_hash,
            w.prompt_message_hash,
            w.context_hash,
            r.model,
            w.attempt_count,
            r.total_tokens,
            r.cost_usd
        FROM work_items w
        LEFT JOIN results r ON r.work_item_id = w.id
        ORDER BY w.id
    """
    return export_query(conn, sql, path)


def export_query(conn: sqlite3.Connection, sql: str, path: Path) -> int:
    cursor = conn.execute(sql)
    rows = cursor.fetchall()
    fieldnames = [description[0] for description in cursor.description]
    write_csv_rows(path, rows, fieldnames=fieldnames)
    return len(rows)


def export_results_jsonl(conn: sqlite3.Connection, path: Path) -> int:
    rows = conn.execute(
        """
        SELECT r.*, w.sample, w.selection_bucket
        FROM results r
        JOIN work_items w ON w.id = r.work_item_id
        ORDER BY w.id
        """
    ).fetchall()
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            payload = row_dict(row)
            payload["result"] = json.loads(payload.pop("result_json"))
            handle.write(canonical_json(payload) + "\n")
    return len(rows)


def write_csv_rows(
    path: Path,
    rows: Iterable[sqlite3.Row],
    *,
    fieldnames: list[str] | None = None,
) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        if fieldnames is None:
            if not rows:
                handle.write("")
                return
            fieldnames = list(rows[0].keys())
        if not fieldnames:
            handle.write("")
            return
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row_dict(row))


def select_audit_sample(
    *,
    run_dir: Path,
    limit_comments: int = 25,
    limit_claims: int = 50,
) -> dict[str, int]:
    exports_dir = run_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    conn = connect_run_db(db_path_for_run(run_dir))
    try:
        comment_rows = conn.execute(
            """
            SELECT
                w.run_id, w.source_line, w.comment_id, w.status,
                r.is_codeable, r.skip_reason, COALESCE(r.claim_count, 0) AS claim_count
            FROM work_items w
            LEFT JOIN results r ON r.work_item_id = w.id
            WHERE w.status IN ('succeeded', 'deterministic_skipped', 'failed')
            ORDER BY
                CASE WHEN w.status = 'failed' THEN 0 ELSE 1 END,
                COALESCE(r.claim_count, 0) DESC,
                w.id
            LIMIT ?
            """,
            (limit_comments,),
        ).fetchall()
        claim_rows = conn.execute(
            """
            SELECT
                run_id, claim_id, source_line, comment_id, claim_type, raw_text,
                normalized_label, experiencer, assertion, confidence, evidence_quote
            FROM claim_rows
            ORDER BY source_line, claim_index
            LIMIT ?
            """,
            (limit_claims,),
        ).fetchall()
    finally:
        conn.close()

    write_audit_template(exports_dir / "audit_comment_template.csv", COMMENT_AUDIT_COLUMNS, comment_rows)
    write_audit_template(exports_dir / "audit_claim_template.csv", CLAIM_AUDIT_COLUMNS, claim_rows)
    return {"comment_rows": len(comment_rows), "claim_rows": len(claim_rows)}


def write_audit_template(path: Path, columns: list[str], rows: Iterable[sqlite3.Row]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            payload = {column: "" for column in columns}
            payload.update({key: row[key] for key in row.keys() if key in payload})
            writer.writerow(payload)


def usage_from_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt_tokens": metadata.get("prompt_tokens"),
        "completion_tokens": metadata.get("completion_tokens"),
        "total_tokens": metadata.get("total_tokens"),
        "cost_usd": metadata.get("cost_usd"),
    }


def is_removed_or_deleted_body(body: str) -> bool:
    return (body or "").strip().lower() in {"[removed]", "[deleted]"}


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 15)].rstrip() + "\n[TRUNCATED]"
