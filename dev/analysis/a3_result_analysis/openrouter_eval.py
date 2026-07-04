"""End-to-end OpenRouter eval for A1 -> A2 -> A3."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dev.analysis.a2_batch_extraction.common import DEFAULT_RUN_ROOT as DEFAULT_A2_RUN_ROOT
from dev.analysis.a2_batch_extraction.runner import (
    context_config_from_values,
    create_run,
    dry_render_run,
    export_run,
    live_run,
    summarize_run,
)
from dev.analysis.a3_result_analysis.analysis import run_analysis
from dev.analysis.a3_result_analysis.common import (
    DEFAULT_A3_OPENROUTER_EVAL_ROOT,
    DEFAULT_A3_RUN_ROOT,
    utc_now_compact,
    utc_now_iso,
    write_json,
)
from dev.analysis.agents.CommentCoderAgent.manifest import DEFAULT_MODEL
from dev.analysis.agents._common.runtime import check_openrouter


def connectivity_eval(
    *,
    model: str = DEFAULT_MODEL,
    output_root: Path = DEFAULT_A3_OPENROUTER_EVAL_ROOT,
) -> dict[str, Any]:
    eval_dir = output_root / f"{utc_now_compact()}_connectivity"
    eval_dir.mkdir(parents=True, exist_ok=True)
    result = check_openrouter(model)
    payload = {
        "ok": True,
        "model": result["model"],
        "content_present": bool(result["content"]),
        "content": result["content"],
        "total_tokens": result["total_tokens"],
        "generated_at_utc": utc_now_iso(),
    }
    write_json(eval_dir / "openrouter_check.json", payload)
    return {"eval_dir": str(eval_dir), "openrouter_check": payload}


def structured_eval(
    *,
    model: str = DEFAULT_MODEL,
    sample: str = "prompt_dev",
    limit: int = 3,
    max_attempts: int = 2,
    output_root: Path = DEFAULT_A3_OPENROUTER_EVAL_ROOT,
    a2_run_root: Path = DEFAULT_A2_RUN_ROOT,
    a3_run_root: Path = DEFAULT_A3_RUN_ROOT,
) -> dict[str, Any]:
    eval_id = f"{utc_now_compact()}_{sample}_{limit}"
    eval_dir = output_root / eval_id
    eval_dir.mkdir(parents=True, exist_ok=True)

    check = check_openrouter(model)
    check_payload = {
        "ok": True,
        "model": check["model"],
        "content_present": bool(check["content"]),
        "content": check["content"],
        "total_tokens": check["total_tokens"],
        "generated_at_utc": utc_now_iso(),
    }
    write_json(eval_dir / "openrouter_check.json", check_payload)

    config = context_config_from_values()
    run_dir = create_run(
        sample=sample,
        limit=limit,
        run_root=a2_run_root,
        run_id=f"a3_openrouter_eval_{eval_id}",
        model=model,
        config=config,
    )
    dry_render_run(run_dir=run_dir, limit=limit, store_raw=True)
    live_status = live_run(
        run_dir=run_dir,
        limit=limit,
        model=model,
        max_attempts=max_attempts,
        workers=1,
        store_raw=True,
        allow_large_live=False,
    )
    a2_report = summarize_run(run_dir=run_dir, write=True)
    export_run(run_dir=run_dir)
    a3_result = run_analysis(run=run_dir, output_root=a3_run_root)

    write_json(eval_dir / "a2_run_pointer.json", {"run_dir": str(run_dir)})
    write_json(eval_dir / "a2_run_report.json", a2_report)
    write_json(eval_dir / "a3_analysis_pointer.json", {"analysis_dir": a3_result["analysis_dir"]})
    write_json(eval_dir / "a3_validation_report.json", a3_result["validation"])
    report = _eval_report(
        eval_id=eval_id,
        eval_dir=eval_dir,
        check=check_payload,
        run_dir=run_dir,
        live_status=live_status,
        a2_report=a2_report,
        a3_result=a3_result,
    )
    write_json(eval_dir / "eval_report.json", report)
    (eval_dir / "eval_report.md").write_text(_eval_report_md(report), encoding="utf-8")
    write_json(
        eval_dir / "eval_manifest.json",
        {
            "eval_id": eval_id,
            "eval_dir": str(eval_dir),
            "model": model,
            "sample": sample,
            "limit": limit,
            "max_attempts": max_attempts,
            "a2_run_dir": str(run_dir),
            "a3_analysis_dir": a3_result["analysis_dir"],
            "generated_at_utc": utc_now_iso(),
        },
    )
    return report


def _eval_report(
    *,
    eval_id: str,
    eval_dir: Path,
    check: dict[str, Any],
    run_dir: Path,
    live_status: int,
    a2_report: dict[str, Any],
    a3_result: dict[str, Any],
) -> dict[str, Any]:
    a3_counts = a3_result.get("row_counts", {})
    pass_conditions = {
        "openrouter_api_reachable": bool(check.get("ok")),
        "a2_selected_rows_at_least_3": a2_report.get("total_work_items", 0) >= 3,
        "a2_live_status_zero": live_status == 0,
        "a2_structured_success_rate_one": a2_report.get("structured_success_rate") == 1.0,
        "a2_evidence_source_violations_zero": a2_report.get("evidence_source_violations") == 0,
        "a3_validation_passes": a3_result.get("validation", {}).get("ok", False),
        "a3_normalized_claim_count_matches": a3_counts.get("claim_rows_normalized") == a2_report.get("claim_count"),
        "a3_quote_candidate_count_matches": a3_counts.get("quote_candidates") == a2_report.get("claim_count"),
    }
    return {
        "eval_id": eval_id,
        "eval_dir": str(eval_dir),
        "model": check.get("model"),
        "openrouter_content_present": check.get("content_present"),
        "a2_run_path": str(run_dir),
        "a2_live_status": live_status,
        "a2_attempted": a2_report.get("attempt_count"),
        "a2_succeeded": a2_report.get("result_count"),
        "a2_failed_attempts": a2_report.get("failed_attempt_count"),
        "structured_success_rate": a2_report.get("structured_success_rate"),
        "evidence_source_violations": a2_report.get("evidence_source_violations"),
        "total_tokens": a2_report.get("total_tokens"),
        "cost_usd": a2_report.get("cost_usd"),
        "a3_validation_ok": a3_result.get("validation", {}).get("ok", False),
        "a3_analysis_path": a3_result.get("analysis_dir"),
        "normalized_claim_row_count": a3_counts.get("claim_rows_normalized"),
        "quote_candidate_count": a3_counts.get("quote_candidates"),
        "pass_conditions": pass_conditions,
        "ok": all(pass_conditions.values()),
    }


def _eval_report_md(report: dict[str, Any]) -> str:
    lines = ["# A3 OpenRouter Eval", ""]
    for key in [
        "eval_id",
        "model",
        "a2_run_path",
        "a3_analysis_path",
        "structured_success_rate",
        "evidence_source_violations",
        "total_tokens",
        "cost_usd",
        "ok",
    ]:
        lines.append(f"- `{key}`: {report.get(key)}")
    lines.append("")
    lines.append("## Pass Conditions")
    for key, value in report.get("pass_conditions", {}).items():
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    return "\n".join(lines)

