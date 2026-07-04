from __future__ import annotations

import sqlite3
from pathlib import Path

from dev.analysis.a3_result_analysis.analysis import run_analysis
from dev.analysis.a3_result_analysis.common import file_sha256, read_csv, read_json, write_csv, write_json
from dev.analysis.a3_result_analysis.tests.test_a3_analysis import make_a2_export
from dev.analysis.a4_evidence_reporting.analysis import build_report
from dev.analysis.a4_evidence_reporting.validate import validate_report_package


def make_a3_package(tmp_path: Path, *, zero_claims: bool = False) -> Path:
    run_dir = make_a2_export(tmp_path / "a2")
    if zero_claims:
        _rewrite_a2_as_zero_claim_run(run_dir)
    result = run_analysis(run=run_dir, output_root=tmp_path / "a3")
    assert result["ok"] is True
    return Path(result["analysis_dir"])


def test_build_report_from_a3_package(tmp_path: Path) -> None:
    a3_dir = make_a3_package(tmp_path)
    result = build_report(a3=a3_dir, output_root=tmp_path / "a4", report_id="a4_test")
    assert result["ok"] is True
    report_dir = Path(result["report_dir"])
    assert (report_dir / "report_manifest.json").exists()
    assert (report_dir / "evidence_packet.json").exists()
    assert (report_dir / "evidence_mart.sqlite").exists()

    cards = read_csv(report_dir / "finding_cards.csv")
    quotes = read_csv(report_dir / "quotes" / "quote_bank_private.csv")
    assert any(row["finding_type"] == "claim_label_frequency" for row in cards)
    assert quotes[0]["public_allowed"] == "0"
    assert validate_report_package(report_dir)["ok"] is True

    conn = sqlite3.connect(report_dir / "evidence_mart.sqlite")
    try:
        assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM quote_bank").fetchone()[0] == 1
    finally:
        conn.close()


def test_a3_hash_mismatch_fails_before_report_build(tmp_path: Path) -> None:
    a3_dir = make_a3_package(tmp_path)
    (a3_dir / "claim_rows_normalized.csv").write_text("tampered\n", encoding="utf-8")
    result = build_report(a3=a3_dir, output_root=tmp_path / "a4", report_id="a4_bad_source")
    assert result["ok"] is False
    assert any("A3 hash mismatch" in error for error in result["source_validation"]["errors"])


def test_public_summary_rejects_unreviewed_quotes(tmp_path: Path) -> None:
    a3_dir = make_a3_package(tmp_path)
    result = build_report(a3=a3_dir, output_root=tmp_path / "a4", report_id="a4_public", mode="public_summary")
    assert result["ok"] is False
    assert any("not approved for public use" in error for error in result["validation"]["errors"])


def test_zero_claim_report_still_valid(tmp_path: Path) -> None:
    a3_dir = make_a3_package(tmp_path, zero_claims=True)
    result = build_report(a3=a3_dir, output_root=tmp_path / "a4", report_id="a4_zero")
    assert result["ok"] is True
    report_dir = Path(result["report_dir"])
    cards = read_csv(report_dir / "finding_cards.csv")
    quotes = read_csv(report_dir / "quotes" / "quote_bank_private.csv")
    assert len(cards) >= 2
    assert quotes == []
    conn = sqlite3.connect(report_dir / "evidence_mart.sqlite")
    try:
        assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM quote_bank").fetchone()[0] == 0
    finally:
        conn.close()


def _rewrite_a2_as_zero_claim_run(run_dir: Path) -> None:
    exports = run_dir / "exports"
    comments = read_csv(exports / "comment_rows.csv")
    comments[0]["is_codeable"] = "0"
    comments[0]["skip_reason"] = "no_target_author_claim"
    comments[0]["claim_count"] = "0"
    write_csv(exports / "comment_rows.csv", comments)
    claim_header = [
        "id",
        "result_id",
        "work_item_id",
        "run_id",
        "source_line",
        "comment_id",
        "claim_index",
        "claim_id",
        "claim_stable_id",
        "claim_hash",
        "claim_type",
        "raw_text",
        "normalized_label",
        "normalized_label_canonical",
        "experiencer",
        "assertion",
        "confidence",
        "evidence_quote",
        "evidence_source",
        "evidence_json",
        "used_context",
        "context_comment_ids_used_json",
        "attribution_confidence",
        "date_utc",
        "year_month",
        "parent_kind",
        "body_length",
        "model",
        "schema_version",
        "prompt_version",
    ]
    write_csv(exports / "claim_rows.csv", [], claim_header)
    run_report = read_json(exports / "run_report.json")
    run_report["claim_count"] = 0
    run_report["evidence_source_violations"] = 0
    write_json(exports / "run_report.json", run_report)
    export_manifest = read_json(exports / "export_manifest.json")
    for name, row_count in {
        "comment_rows.csv": len(comments),
        "claim_rows.csv": 0,
        "run_report.json": None,
    }.items():
        path = exports / name
        export_manifest["files"][name] = {
            "sha256": file_sha256(path),
            "bytes": path.stat().st_size,
            "row_count": row_count,
        }
    write_json(exports / "export_manifest.json", export_manifest)
