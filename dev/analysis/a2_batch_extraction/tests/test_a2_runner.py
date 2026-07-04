from __future__ import annotations

from pathlib import Path

from dev.analysis.a2_batch_extraction.runner import (
    deterministic_skip_result,
    export_run,
    save_result,
    summarize_run,
)
from dev.analysis.a2_batch_extraction.storage import (
    connect_run_db,
    create_schema,
    db_path_for_run,
    get_manifest,
    insert_work_items,
    put_manifest,
)
from dev.analysis.agents.CommentCoderAgent.schemas import CommentCodingResult


def make_run(tmp_path: Path) -> tuple[Path, int]:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    conn = connect_run_db(db_path_for_run(run_dir))
    try:
        create_schema(conn)
        put_manifest(
            conn,
            {
                "run_id": "test_run",
                "model": "test-model",
                "instrument_hash": "abc123",
                "schema_version": "comment_coding_v0.1",
                "prompt_version": "comment_coder_v0.1",
                "context_render_config": {
                    "ancestor_depth": 2,
                    "previous_sibling_limit": 2,
                    "previous_thread_limit": 3,
                    "max_body_chars": 1200,
                    "max_total_chars": 16000,
                    "renderer_version": "comment_context_prompt_v0.1",
                },
                "db": "comments.sqlite",
            },
        )
        insert_work_items(
            conn,
            [
                {
                    "run_id": "test_run",
                    "source_line": 10,
                    "comment_id": "abc",
                    "post_id": "post1",
                    "link_id": "t3_post1",
                    "parent_kind": "post",
                    "parent_comment_id": None,
                    "date_utc": "2020-01-02T03:04:05+00:00",
                    "year_month": "2020-01",
                    "body_length": 9,
                    "is_removed_or_deleted": False,
                    "sample": "unit",
                    "selection_bucket": "unit",
                    "selection_source": "unit",
                }
            ],
        )
        work_item_id = conn.execute("SELECT id FROM work_items").fetchone()["id"]
    finally:
        conn.close()
    return run_dir, work_item_id


def test_deterministic_skip_result_validates(tmp_path: Path) -> None:
    run_dir, _ = make_run(tmp_path)
    conn = connect_run_db(db_path_for_run(run_dir))
    try:
        row = conn.execute("SELECT * FROM work_items").fetchone()
        result = deterministic_skip_result(row)
    finally:
        conn.close()

    assert isinstance(result, CommentCodingResult)
    assert result.is_codeable is False
    assert result.skip_reason == "removed_deleted"
    assert result.target_author_claims == []


def test_save_result_expands_claim_rows_and_exports(tmp_path: Path) -> None:
    run_dir, _ = make_run(tmp_path)
    result = CommentCodingResult(
        schema_version="comment_coding_v0.1",
        prompt_version="comment_coder_v0.1",
        comment_id="abc",
        source_line=10,
        is_codeable=True,
        skip_reason=None,
        target_author_claims=[
            {
                "claim_type": "symptom",
                "raw_text": "I still have chest pain.",
                "normalized_label": "chest pain",
                "experiencer": "self",
                "assertion": "present",
                "confidence": "high",
                "evidence": [{"quote": "I still have chest pain", "source": "target_comment"}],
            }
        ],
        used_context=False,
        context_comment_ids_used=[],
        attribution_confidence="high",
        ambiguity_notes=None,
    )

    conn = connect_run_db(db_path_for_run(run_dir))
    try:
        row = conn.execute("SELECT * FROM work_items").fetchone()
        save_result(
            conn,
            row,
            result=result,
            model="test-model",
            agent_id="agent-1",
            metadata={"total_tokens": 12, "cost_usd": 0.001},
            latency_seconds=1.2,
            deterministic=False,
        )
        claim_count = conn.execute("SELECT COUNT(*) FROM claim_rows").fetchone()[0]
        manifest = get_manifest(conn)
    finally:
        conn.close()

    assert manifest["run_id"] == "test_run"
    assert claim_count == 1

    report = summarize_run(run_dir=run_dir, write=True)
    assert report["claim_count"] == 1

    export_manifest = export_run(run_dir=run_dir)
    exports = run_dir / "exports"
    assert (exports / "comment_rows.csv").exists()
    assert (exports / "claim_rows.csv").exists()
    assert export_manifest["files"]["claim_rows.csv"]["row_count"] == 1

