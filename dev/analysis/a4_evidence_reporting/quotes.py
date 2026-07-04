"""Quote bank generation for A4."""

from __future__ import annotations

from typing import Any

from dev.analysis.a4_evidence_reporting.common import json_cell, write_csv


QUOTE_BANK_COLUMNS = [
    "quote_id",
    "run_id",
    "claim_id",
    "comment_id",
    "source_line",
    "quote_text_original",
    "quote_text_redacted",
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
    "sensitivity_flags_json",
    "public_allowed",
    "reviewer",
    "reviewed_at_utc",
    "review_notes",
    "selection_reason",
    "source_a3_analysis_id",
    "source_a2_run_id",
]


def build_quote_bank(data, *, mode: str) -> list[dict[str, Any]]:
    source_a3_analysis_id = data.analysis_manifest.get("analysis_id", data.paths.analysis_id)
    source_a2_run_id = ",".join(data.analysis_manifest.get("source_a2_run_ids") or [])
    rows: list[dict[str, Any]] = []
    for quote in data.quote_candidates:
        redaction_status = quote.get("redaction_status", "not_reviewed") or "not_reviewed"
        audit_status = quote.get("audit_status", "unaudited") or "unaudited"
        public_allowed = redaction_status == "reviewed_public_ok" and audit_status in {"audited_supported", "reviewed_supported"}
        rows.append(
            {
                "quote_id": quote.get("quote_id", ""),
                "run_id": quote.get("run_id", ""),
                "claim_id": quote.get("claim_id", ""),
                "comment_id": quote.get("comment_id", ""),
                "source_line": quote.get("source_line", ""),
                "quote_text_original": quote.get("evidence_quote", ""),
                "quote_text_redacted": "",
                "claim_type": quote.get("claim_type", ""),
                "normalized_label_canonical": quote.get("normalized_label_canonical", ""),
                "analysis_bucket": quote.get("analysis_bucket", ""),
                "assertion": quote.get("assertion", ""),
                "experiencer": quote.get("experiencer", ""),
                "confidence": quote.get("confidence", ""),
                "attribution_confidence": quote.get("attribution_confidence", ""),
                "audit_status": audit_status,
                "contains_sensitive_terms": quote.get("contains_sensitive_terms", "unknown") or "unknown",
                "redaction_status": redaction_status,
                "sensitivity_flags_json": json_cell([]),
                "public_allowed": "1" if public_allowed else "0",
                "reviewer": "",
                "reviewed_at_utc": "",
                "review_notes": "",
                "selection_reason": quote.get("selection_reason", ""),
                "source_a3_analysis_id": source_a3_analysis_id,
                "source_a2_run_id": source_a2_run_id or quote.get("run_id", ""),
            }
        )
    return rows


def write_quote_outputs(output_dir, quote_bank: list[dict[str, Any]]) -> None:
    quote_dir = output_dir / "quotes"
    write_csv(quote_dir / "quote_bank_private.csv", quote_bank, QUOTE_BANK_COLUMNS)
    write_csv(quote_dir / "quote_review_template.csv", quote_bank, QUOTE_BANK_COLUMNS)
