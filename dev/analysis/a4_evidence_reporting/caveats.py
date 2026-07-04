"""Standing caveats for A4 reports."""

from __future__ import annotations

from typing import Any


def build_caveats(*, mode: str, data) -> list[dict[str, Any]]:
    denominators = {row.get("name", ""): row.get("value", "") for row in data.denominators}
    return [
        {
            "caveat_id": "C1",
            "kind": "source_scope",
            "text": "Single-community Reddit self-reports; not a clinical or population sample.",
            "required": "yes",
        },
        {
            "caveat_id": "C2",
            "kind": "platform_selection_bias",
            "text": "Rows exist only when people posted comments available in this corpus.",
            "required": "yes",
        },
        {
            "caveat_id": "C3",
            "kind": "comment_only_or_missing_root_posts",
            "text": "The current comment corpus can lack root submission text for top-level comments.",
            "required": "yes",
        },
        {
            "caveat_id": "C4",
            "kind": "model_extraction_error",
            "text": "A1/A2 model extraction can miss, split, merge, or misattribute claims.",
            "required": "yes",
        },
        {
            "caveat_id": "C5",
            "kind": "audit_sample_size",
            "text": f"Audited claim rows in this A3 package: {denominators.get('n_claims_audited', '0')}.",
            "required": "yes",
        },
        {
            "caveat_id": "C6",
            "kind": "no_patient_denominator",
            "text": "This A4 package reports comment and claim counts, not patient-level prevalence.",
            "required": "yes",
        },
        {
            "caveat_id": "C7",
            "kind": "no_clinical_verification",
            "text": "Self-reported claims are not clinically verified outcomes, diagnoses, safety findings, or efficacy findings.",
            "required": "yes",
        },
        {
            "caveat_id": "C8",
            "kind": "quote_redaction_status",
            "text": "Quote candidates are private review artifacts unless separately reviewed for public use.",
            "required": "yes" if mode == "public_summary" else "recommended",
        },
    ]
