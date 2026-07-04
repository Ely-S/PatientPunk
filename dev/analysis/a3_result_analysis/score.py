"""Audit scoring for A3 reviewed labels."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dev.eval.wilson import rule_of_three, wilson

from dev.analysis.a3_result_analysis.common import boolish, read_csv, write_csv, write_json


COMMENT_ERROR_COLUMNS = [
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
]
CLAIM_ERROR_COLUMNS = [
    "wrong_claim_type",
    "wrong_label",
    "wrong_experiencer",
    "wrong_assertion",
    "unsupported_evidence",
    "duplicate_claim",
    "should_be_split",
    "should_be_merged",
    "confidence_too_high",
]
DISAGREEMENT_COLUMNS = [
    "level",
    "run_id",
    "source_line",
    "comment_id",
    "claim_id",
    "error_type",
    "claim_type",
    "raw_text",
    "normalized_label",
    "assertion",
    "experiencer",
    "evidence_quote",
    "reviewer",
    "notes",
]


def score_audit(
    *,
    audit_comments_path: Path | None,
    audit_claims_path: Path | None,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    comment_rows = read_csv(audit_comments_path) if audit_comments_path and audit_comments_path.exists() else []
    claim_rows = read_csv(audit_claims_path) if audit_claims_path and audit_claims_path.exists() else []

    comment_scores = _score_level(comment_rows, COMMENT_ERROR_COLUMNS, level="comment")
    claim_scores = _score_level(claim_rows, CLAIM_ERROR_COLUMNS, level="claim")
    write_csv(output_dir / "comment_scorecard.csv", comment_scores)
    write_csv(output_dir / "claim_scorecard.csv", claim_scores)
    disagreements = _disagreements(comment_rows, claim_rows)
    write_csv(output_dir / "disagreement_rows.csv", disagreements, DISAGREEMENT_COLUMNS)
    decision = gate_decision(comment_scores + claim_scores)
    summary = {
        "comment_reviewed_rows": _reviewed_count(comment_rows),
        "claim_reviewed_rows": _reviewed_count(claim_rows),
        "gate_decision": decision,
        "metric_count": len(comment_scores) + len(claim_scores),
    }
    write_json(output_dir / "metric_summary.json", summary | {"metrics": comment_scores + claim_scores})
    (output_dir / "metric_summary.md").write_text(_summary_md(summary, comment_scores + claim_scores), encoding="utf-8")
    write_json(output_dir / "gate_decision.json", {"gate_decision": decision})
    return summary


def _score_level(rows: list[dict[str, str]], error_columns: list[str], *, level: str) -> list[dict[str, Any]]:
    reviewed = [row for row in rows if _row_reviewed(row)]
    total = len(reviewed)
    scores = []
    correct_k = sum(1 for row in reviewed if boolish(row.get("correct")) is True)
    scores.append(_metric(f"{level}_correct_rate", level, correct_k, total, "rows with correct=true / reviewed rows"))
    for column in error_columns:
        failures = sum(1 for row in reviewed if boolish(row.get(column)) is True)
        scores.append(_metric(f"{column}_rate", level, failures, total, f"rows with {column}=true / reviewed rows"))
    return scores


def _metric(metric: str, level: str, k: int, n: int, description: str) -> dict[str, Any]:
    rate, low, high = wilson(k, n)
    return {
        "metric": metric,
        "level": level,
        "k": k,
        "n": n,
        "rate": rate,
        "wilson_low": low,
        "wilson_high": high,
        "rule_of_three_upper_if_zero_failures": rule_of_three(n) if k == 0 else "",
        "denominator_description": description,
        "threshold": "",
        "pass_fail": "",
    }


def _row_reviewed(row: dict[str, str]) -> bool:
    for value in row.values():
        if boolish(value) is not None:
            return True
    return bool(row.get("notes") or row.get("reviewer"))


def _reviewed_count(rows: list[dict[str, str]]) -> int:
    return sum(1 for row in rows if _row_reviewed(row))


def _disagreements(comment_rows: list[dict[str, str]], claim_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    out = []
    for row in comment_rows:
        for column in COMMENT_ERROR_COLUMNS:
            if boolish(row.get(column)) is True:
                out.append(_disagreement("comment", column, row))
    for row in claim_rows:
        for column in CLAIM_ERROR_COLUMNS:
            if boolish(row.get(column)) is True:
                out.append(_disagreement("claim", column, row))
    return out


def _disagreement(level: str, error_type: str, row: dict[str, str]) -> dict[str, Any]:
    return {
        "level": level,
        "run_id": row.get("run_id", ""),
        "source_line": row.get("source_line", ""),
        "comment_id": row.get("comment_id", ""),
        "claim_id": row.get("claim_id", ""),
        "error_type": error_type,
        "claim_type": row.get("claim_type", ""),
        "raw_text": row.get("raw_text", ""),
        "normalized_label": row.get("normalized_label", ""),
        "assertion": row.get("assertion", ""),
        "experiencer": row.get("experiencer", ""),
        "evidence_quote": row.get("evidence_quote", ""),
        "reviewer": row.get("reviewer", ""),
        "notes": row.get("notes", ""),
    }


def gate_decision(metrics: list[dict[str, Any]]) -> str:
    if not metrics:
        return "proceed_to_more_audit"
    serious = [
        row
        for row in metrics
        if row["metric"] != f"{row['level']}_correct_rate"
        and row["n"]
        and row["rate"] > 0.05
    ]
    if serious:
        return "revise_a1_prompt"
    return "proceed"


def _summary_md(summary: dict[str, Any], metrics: list[dict[str, Any]]) -> str:
    lines = ["# A3 Audit Metric Summary", ""]
    for key, value in summary.items():
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    lines.append("| Metric | Level | k | n | rate | Wilson high |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for row in metrics:
        lines.append(
            f"| {row['metric']} | {row['level']} | {row['k']} | {row['n']} | "
            f"{row['rate']:.3f} | {row['wilson_high']:.3f} |"
        )
    lines.append("")
    return "\n".join(lines)
