from __future__ import annotations

from pathlib import Path

from dev.analysis.a3_result_analysis.analysis import run_analysis
from dev.analysis.a3_result_analysis.common import file_sha256, read_csv, read_json, write_csv, write_json, write_jsonl
from dev.analysis.a3_result_analysis.loaders import resolve_a2_paths
from dev.analysis.a3_result_analysis.normalization import clean_label, normalize_claim_rows
from dev.analysis.a3_result_analysis.score import score_audit
from dev.analysis.a3_result_analysis.validate import validate_a2_run


def make_a2_export(tmp_path: Path, *, duplicate_claim: bool = False, bad_evidence: bool = False) -> Path:
    run_dir = tmp_path / "a2_run"
    exports = run_dir / "exports"
    exports.mkdir(parents=True)
    comments = [
        {
            "run_id": "a2_run",
            "source_line": "1",
            "comment_id": "c1",
            "post_id": "p1",
            "link_id": "t3_p1",
            "date_utc": "2020-01-01T00:00:00+00:00",
            "year_month": "2020-01",
            "parent_kind": "post",
            "parent_comment_id": "",
            "body_length": "20",
            "is_removed_or_deleted": "0",
            "status": "succeeded",
            "is_codeable": "1",
            "skip_reason": "",
            "claim_count": "1",
            "used_context": "0",
            "context_available_count": "0",
            "context_comment_ids_used_json": "[]",
            "missing_context_json": "{}",
            "attribution_confidence": "high",
            "ambiguity_notes": "",
            "result_hash": "rh",
            "prompt_message_hash": "ph",
            "context_hash": "ch",
            "model": "test-model",
            "attempt_count": "1",
            "total_tokens": "10",
            "cost_usd": "0.001",
        }
    ]
    claim_id = "a2_run:1:1"
    claims = [
        {
            "id": "1",
            "result_id": "1",
            "work_item_id": "1",
            "run_id": "a2_run",
            "source_line": "1",
            "comment_id": "c1",
            "claim_index": "1",
            "claim_id": claim_id,
            "claim_stable_id": claim_id,
            "claim_hash": "claimhash",
            "claim_type": "symptom",
            "raw_text": "I have chest pain.",
            "normalized_label": "Chest Pain!",
            "normalized_label_canonical": "",
            "experiencer": "self",
            "assertion": "present",
            "confidence": "high",
            "evidence_quote": "I have chest pain",
            "evidence_source": "context_comment" if bad_evidence else "target_comment",
            "evidence_json": "[]",
            "used_context": "0",
            "context_comment_ids_used_json": "[]",
            "attribution_confidence": "high",
            "date_utc": "2020-01-01T00:00:00+00:00",
            "year_month": "2020-01",
            "parent_kind": "post",
            "body_length": "20",
            "model": "test-model",
            "schema_version": "comment_coding_v0.1",
            "prompt_version": "comment_coder_v0.1",
        }
    ]
    if duplicate_claim:
        claims.append(dict(claims[0], id="2"))
    attempts = [
        {
            "id": "1",
            "work_item_id": "1",
            "attempt_number": "1",
            "model": "test-model",
            "agent_id": "agent-1",
            "started_at_utc": "2020-01-01T00:00:00+00:00",
            "finished_at_utc": "2020-01-01T00:00:01+00:00",
            "latency_seconds": "1",
            "status": "succeeded",
            "error_type": "",
            "error_message": "",
            "traceback": "",
            "context_hash": "ch",
            "prompt_message_hash": "ph",
            "prompt_tokens": "5",
            "completion_tokens": "5",
            "total_tokens": "10",
            "cost_usd": "0.001",
            "metadata_json": "{}",
        }
    ]
    results = [{"run_id": "a2_run", "source_line": 1, "comment_id": "c1", "result": {"target_author_claims": [{}]}}]
    run_report = {
        "run_id": "a2_run",
        "total_work_items": 1,
        "attempt_count": 1,
        "result_count": 1,
        "claim_count": len(claims),
        "failed_attempt_count": 0,
        "structured_success_rate": 1.0,
        "evidence_source_violations": 1 if bad_evidence else 0,
    }
    write_csv(exports / "comment_rows.csv", comments)
    write_csv(exports / "claim_rows.csv", claims)
    write_csv(exports / "attempts.csv", attempts)
    write_csv(exports / "failed_items.csv", [])
    write_jsonl(exports / "results.jsonl", results)
    write_json(exports / "run_report.json", run_report)
    write_json(exports / "run_manifest.json", {"run_id": "a2_run", "instrument_hash": "ih", "model": "test-model"})
    files = {}
    for name, row_count in {
        "comment_rows.csv": len(comments),
        "claim_rows.csv": len(claims),
        "attempts.csv": len(attempts),
        "failed_items.csv": 0,
        "results.jsonl": len(results),
        "run_report.json": None,
        "run_manifest.json": None,
    }.items():
        path = exports / name
        files[name] = {"sha256": file_sha256(path), "bytes": path.stat().st_size, "row_count": row_count}
    write_json(exports / "export_manifest.json", {"run_id": "a2_run", "instrument_hash": "ih", "files": files})
    return run_dir


def test_validate_a2_run_passes_and_catches_errors(tmp_path: Path) -> None:
    run_dir = make_a2_export(tmp_path)
    result = validate_a2_run(resolve_a2_paths(run=run_dir))
    assert result["ok"] is True

    bad_dir = make_a2_export(tmp_path / "bad", duplicate_claim=True, bad_evidence=True)
    bad = validate_a2_run(resolve_a2_paths(run=bad_dir))
    assert bad["ok"] is False
    assert any("duplicate claim_id" in error for error in bad["errors"])
    assert any("evidence_source" in error for error in bad["errors"])


def test_normalization_preserves_raw_label() -> None:
    rows = normalize_claim_rows(
        [
            {
                "schema_version": "comment_coding_v0.1",
                "prompt_version": "comment_coder_v0.1",
                "claim_type": "symptom",
                "normalized_label": "Chest Pain!",
                "raw_text": "chest pain",
            }
        ]
    )
    assert clean_label("Chest Pain!") == "chest pain"
    assert rows[0]["normalized_label"] == "Chest Pain!"
    assert rows[0]["normalized_label_clean"] == "chest pain"
    assert rows[0]["normalization_review_status"] == "unreviewed"


def test_run_analysis_writes_a3_package(tmp_path: Path) -> None:
    run_dir = make_a2_export(tmp_path)
    output_root = tmp_path / "a3"
    result = run_analysis(run=run_dir, output_root=output_root)
    assert result["ok"] is True
    analysis_dir = output_root / "a2_run"
    assert (analysis_dir / "analysis_manifest.json").exists()
    assert (analysis_dir / "claim_rows_normalized.csv").exists()
    assert (analysis_dir / "quote_candidates.csv").exists()
    assert len(read_csv(analysis_dir / "claim_rows_normalized.csv")) == 1
    assert len(read_csv(analysis_dir / "quote_candidates.csv")) == 1
    manifest = read_json(analysis_dir / "analysis_manifest.json")
    assert manifest["row_counts"]["claim_rows_normalized"] == 1


def test_score_audit_writes_metrics(tmp_path: Path) -> None:
    comments = tmp_path / "audit_comments.csv"
    claims = tmp_path / "audit_claims.csv"
    write_csv(
        comments,
        [{"run_id": "r", "source_line": "1", "comment_id": "c", "correct": "yes", "wrong_skip": ""}],
    )
    write_csv(
        claims,
        [{"run_id": "r", "claim_id": "cl", "source_line": "1", "comment_id": "c", "correct": "no", "unsupported_evidence": "yes"}],
    )
    result = score_audit(audit_comments_path=comments, audit_claims_path=claims, output_dir=tmp_path / "scores")
    assert result["comment_reviewed_rows"] == 1
    assert result["claim_reviewed_rows"] == 1
    assert (tmp_path / "scores" / "metric_summary.json").exists()
    disagreements = read_csv(tmp_path / "scores" / "disagreement_rows.csv")
    assert disagreements[0]["error_type"] == "unsupported_evidence"

