"""Quote candidate generation for A4-facing review."""

from __future__ import annotations

from typing import Any

from dev.analysis.a3_result_analysis.common import write_csv


QUOTE_COLUMNS = [
    "quote_id",
    "run_id",
    "claim_id",
    "source_line",
    "comment_id",
    "evidence_quote",
    "claim_type",
    "normalized_label_canonical",
    "analysis_bucket",
    "assertion",
    "experiencer",
    "confidence",
    "attribution_confidence",
    "audit_status",
    "contains_sensitive_terms",
    "redaction_status",
    "selection_reason",
]


def quote_candidates(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for claim in claims:
        quote_id = f"quote:{claim.get('claim_id', '')}"
        rows.append(
            {
                "quote_id": quote_id,
                "run_id": claim.get("run_id", ""),
                "claim_id": claim.get("claim_id", ""),
                "source_line": claim.get("source_line", ""),
                "comment_id": claim.get("comment_id", ""),
                "evidence_quote": claim.get("evidence_quote", ""),
                "claim_type": claim.get("claim_type", ""),
                "normalized_label_canonical": claim.get("normalized_label_canonical", ""),
                "analysis_bucket": claim.get("analysis_bucket", ""),
                "assertion": claim.get("assertion", ""),
                "experiencer": claim.get("experiencer", ""),
                "confidence": claim.get("confidence", ""),
                "attribution_confidence": claim.get("attribution_confidence", ""),
                "audit_status": "unaudited",
                "contains_sensitive_terms": "unknown",
                "redaction_status": "not_reviewed",
                "selection_reason": "claim_evidence_quote",
            }
        )
    return rows


def write_quote_candidates(path, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = quote_candidates(claims)
    write_csv(path, rows, QUOTE_COLUMNS)
    return rows

