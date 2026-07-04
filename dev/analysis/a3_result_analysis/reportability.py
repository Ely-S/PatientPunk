"""A4-facing reportability labels for A3 outputs."""

from __future__ import annotations

from collections import Counter
from typing import Any

from dev.analysis.a3_result_analysis.common import write_csv


REPORTABILITY_COLUMNS = [
    "unit",
    "key",
    "reportability_label",
    "reason",
    "source_metric",
    "source_metric_rate",
    "source_metric_wilson_high",
    "normalization_review_status",
    "audit_status",
    "gate_decision",
]


def reportability_rows(
    *,
    validation: dict[str, Any],
    normalized_claims: list[dict[str, Any]],
    gate_decision: str | None = None,
) -> list[dict[str, Any]]:
    gate = gate_decision or "proceed_to_more_audit"
    if not validation.get("ok"):
        return [
            {
                "unit": "run",
                "key": validation.get("run_id", ""),
                "reportability_label": "not_reportable",
                "reason": "a3_validation_failed",
                "source_metric": "validation",
                "source_metric_rate": "",
                "source_metric_wilson_high": "",
                "normalization_review_status": "",
                "audit_status": "unknown",
                "gate_decision": "stop",
            }
        ]

    counts: Counter[tuple[str, str, str]] = Counter()
    for claim in normalized_claims:
        counts[
            (
                claim.get("claim_type", ""),
                claim.get("normalized_label_canonical", ""),
                claim.get("normalization_review_status", "unreviewed"),
            )
        ] += 1

    rows: list[dict[str, Any]] = [
        {
            "unit": "run",
            "key": validation.get("run_id", ""),
            "reportability_label": "exploratory",
            "reason": "unaudited_run",
            "source_metric": "validation",
            "source_metric_rate": "",
            "source_metric_wilson_high": "",
            "normalization_review_status": "",
            "audit_status": "unaudited",
            "gate_decision": gate,
        }
    ]
    for (claim_type, label, review_status), count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        reportability = "exploratory"
        reason = "normalization_unreviewed" if review_status != "accepted" else "no_audit_labels"
        if gate in {"stop", "revise_a1_prompt", "revise_a1_schema", "revise_a2_runner", "revise_a3_audit"}:
            reportability = "not_reportable"
            reason = f"gate_decision_{gate}"
        rows.append(
            {
                "unit": "claim_label",
                "key": f"{claim_type}:{label}",
                "reportability_label": reportability,
                "reason": reason,
                "source_metric": "n_claims",
                "source_metric_rate": count,
                "source_metric_wilson_high": "",
                "normalization_review_status": review_status,
                "audit_status": "unaudited",
                "gate_decision": gate,
            }
        )
    return rows


def write_reportability(path, *, validation: dict[str, Any], normalized_claims: list[dict[str, Any]], gate_decision: str | None = None) -> list[dict[str, Any]]:
    rows = reportability_rows(validation=validation, normalized_claims=normalized_claims, gate_decision=gate_decision)
    write_csv(path, rows, REPORTABILITY_COLUMNS)
    return rows

