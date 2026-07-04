"""Finding-card construction for A4."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from dev.analysis.a4_evidence_reporting.common import int_value, json_cell, percent, stable_hash, utc_now_iso, write_csv, write_jsonl
from dev.analysis.a4_evidence_reporting.confidence import reportability_lookup, run_reportability


FINDING_CARD_COLUMNS = [
    "finding_id",
    "report_id",
    "finding_type",
    "title",
    "plain_language_summary",
    "claim_type",
    "normalized_label_canonical",
    "analysis_bucket",
    "cohort_filter_json",
    "time_filter_json",
    "n_claims",
    "n_comments",
    "n_source_runs",
    "n_audited_claims",
    "n_audited_comments",
    "denominator_name",
    "denominator_value",
    "percentage",
    "normalization_review_status",
    "audit_status",
    "reportability_label",
    "reportability_reason",
    "gate_decision",
    "representative_quote_ids_json",
    "source_claim_ids_json",
    "source_comment_ids_json",
    "source_a3_analysis_ids_json",
    "source_a2_run_ids_json",
    "limitations_json",
    "created_at_utc",
]


def build_finding_cards(data, *, report_id: str, quote_bank: list[dict[str, Any]]) -> list[dict[str, Any]]:
    denominator_values = {row.get("name", ""): int_value(row.get("value")) for row in data.denominators}
    reportability = reportability_lookup(data.reportability)
    run_id = (data.analysis_manifest.get("source_a2_run_ids") or [data.paths.analysis_dir.name])[0]
    run_report = run_reportability(data.reportability, run_id)
    source_a3_ids = [data.analysis_manifest.get("analysis_id", data.paths.analysis_id)]
    source_a2_ids = data.analysis_manifest.get("source_a2_run_ids") or []
    cards: list[dict[str, Any]] = []

    cards.append(
        _card(
            report_id=report_id,
            finding_type="run_quality_overview",
            title="Run quality overview",
            summary=(
                f"{denominator_values.get('n_claims_after_normalization', 0)} normalized claims were extracted "
                f"from {denominator_values.get('n_work_items_selected', 0)} selected comments. "
                f"This run is {run_report.get('reportability_label', 'exploratory')} because "
                f"{run_report.get('reason', 'reportability is conservative')}."
            ),
            claim_type="",
            label="",
            analysis_bucket="",
            n_claims=denominator_values.get("n_claims_after_normalization", 0),
            n_comments=denominator_values.get("n_work_items_selected", 0),
            n_source_runs=len(source_a2_ids),
            n_audited_claims=denominator_values.get("n_claims_audited", 0),
            n_audited_comments=denominator_values.get("n_comments_audited", 0),
            denominator_name="n_work_items_selected",
            denominator_value=denominator_values.get("n_work_items_selected", 0),
            percentage="",
            normalization_review_status="",
            audit_status=run_report.get("audit_status", "unaudited"),
            reportability_label=run_report.get("reportability_label", "exploratory"),
            reportability_reason=run_report.get("reason", ""),
            gate_decision=run_report.get("gate_decision", "proceed_to_more_audit"),
            representative_quote_ids=[],
            source_claim_ids=[],
            source_comment_ids=[row.get("comment_id", "") for row in data.comments if row.get("comment_id")],
            source_a3_ids=source_a3_ids,
            source_a2_ids=source_a2_ids,
            limitations=["no_patient_denominator", "private_review_only"],
        )
    )

    cards.append(
        _card(
            report_id=report_id,
            finding_type="audit_readiness",
            title="Audit readiness",
            summary=(
                f"{denominator_values.get('n_claims_audited', 0)} claims and "
                f"{denominator_values.get('n_comments_audited', 0)} comments have reviewed audit labels."
            ),
            claim_type="",
            label="",
            analysis_bucket="",
            n_claims=0,
            n_comments=0,
            n_source_runs=len(source_a2_ids),
            n_audited_claims=denominator_values.get("n_claims_audited", 0),
            n_audited_comments=denominator_values.get("n_comments_audited", 0),
            denominator_name="n_claims_after_normalization",
            denominator_value=denominator_values.get("n_claims_after_normalization", 0),
            percentage="",
            normalization_review_status="",
            audit_status=run_report.get("audit_status", "unaudited"),
            reportability_label="exploratory",
            reportability_reason="audit_status_summary",
            gate_decision=run_report.get("gate_decision", "proceed_to_more_audit"),
            representative_quote_ids=[],
            source_claim_ids=[],
            source_comment_ids=[],
            source_a3_ids=source_a3_ids,
            source_a2_ids=source_a2_ids,
            limitations=["audit_required_before_public_reporting"],
        )
    )

    quote_ids_by_claim = defaultdict(list)
    for quote in quote_bank:
        quote_ids_by_claim[quote.get("claim_id", "")].append(quote.get("quote_id", ""))

    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for claim in data.claims:
        key = (
            claim.get("claim_type", ""),
            claim.get("normalized_label_canonical", ""),
            claim.get("analysis_bucket", ""),
        )
        groups[key].append(claim)

    denominator_name = "n_claims_after_normalization"
    denominator_value = denominator_values.get(denominator_name, len(data.claims))
    for (claim_type, label, analysis_bucket), claims in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        claim_ids = [row.get("claim_id", "") for row in claims if row.get("claim_id")]
        comment_ids = sorted({row.get("comment_id", "") for row in claims if row.get("comment_id")})
        run_ids = sorted({row.get("run_id", "") for row in claims if row.get("run_id")})
        review_status_counts = Counter(row.get("normalization_review_status", "unreviewed") for row in claims)
        review_status = review_status_counts.most_common(1)[0][0] if review_status_counts else ""
        reportability_row = reportability.get(("claim_label", f"{claim_type}:{label}"), {})
        report_label = reportability_row.get("reportability_label", "exploratory")
        reason = reportability_row.get("reason", "not_in_reportability_summary")
        representative_quote_ids = _representative_quote_ids(claim_ids, quote_ids_by_claim)
        n_claims = len(claims)
        pct = percent(n_claims, denominator_value)
        cards.append(
            _card(
                report_id=report_id,
                finding_type="claim_label_frequency",
                title=f"{claim_type}: {label or '(blank label)'}",
                summary=(
                    f"{n_claims} of {denominator_value} normalized claims"
                    + (f" ({pct}%)" if pct else "")
                    + f" were coded as {claim_type}: {label or '(blank label)'}. "
                    f"This finding is {report_label} because {reason}."
                ),
                claim_type=claim_type,
                label=label,
                analysis_bucket=analysis_bucket,
                n_claims=n_claims,
                n_comments=len(comment_ids),
                n_source_runs=len([run_id for run_id in run_ids if run_id]),
                n_audited_claims=denominator_values.get("n_claims_audited", 0),
                n_audited_comments=denominator_values.get("n_comments_audited", 0),
                denominator_name=denominator_name,
                denominator_value=denominator_value,
                percentage=pct,
                normalization_review_status=review_status,
                audit_status=reportability_row.get("audit_status", "unaudited"),
                reportability_label=report_label,
                reportability_reason=reason,
                gate_decision=reportability_row.get("gate_decision", run_report.get("gate_decision", "proceed_to_more_audit")),
                representative_quote_ids=representative_quote_ids,
                source_claim_ids=claim_ids,
                source_comment_ids=comment_ids,
                source_a3_ids=source_a3_ids,
                source_a2_ids=source_a2_ids,
                limitations=_limitations(review_status, denominator_values),
            )
        )

    context_claims = [
        row
        for row in data.claims
        if str(row.get("used_context", "")).strip() in {"1", "true", "True"} or row.get("attribution_confidence") != "high"
    ]
    if context_claims:
        cards.append(_context_card(report_id, context_claims, denominator_values, source_a3_ids, source_a2_ids, run_report))

    return cards


def write_finding_outputs(output_dir, cards: list[dict[str, Any]]) -> None:
    write_csv(output_dir / "finding_cards.csv", cards, FINDING_CARD_COLUMNS)
    write_jsonl(output_dir / "finding_cards.jsonl", cards)


def _card(**kwargs) -> dict[str, Any]:
    key_payload = {
        "report_id": kwargs["report_id"],
        "finding_type": kwargs["finding_type"],
        "claim_type": kwargs["claim_type"],
        "label": kwargs["label"],
        "analysis_bucket": kwargs["analysis_bucket"],
        "cohort_filter_json": kwargs.get("cohort_filter_json", {}),
        "time_filter_json": kwargs.get("time_filter_json", {}),
    }
    finding_id = f"finding:{kwargs['report_id']}:{kwargs['finding_type']}:{stable_hash(key_payload)}"
    return {
        "finding_id": finding_id,
        "report_id": kwargs["report_id"],
        "finding_type": kwargs["finding_type"],
        "title": kwargs["title"],
        "plain_language_summary": kwargs["summary"],
        "claim_type": kwargs["claim_type"],
        "normalized_label_canonical": kwargs["label"],
        "analysis_bucket": kwargs["analysis_bucket"],
        "cohort_filter_json": json_cell(kwargs.get("cohort_filter_json", {})),
        "time_filter_json": json_cell(kwargs.get("time_filter_json", {})),
        "n_claims": kwargs["n_claims"],
        "n_comments": kwargs["n_comments"],
        "n_source_runs": kwargs["n_source_runs"],
        "n_audited_claims": kwargs["n_audited_claims"],
        "n_audited_comments": kwargs["n_audited_comments"],
        "denominator_name": kwargs["denominator_name"],
        "denominator_value": kwargs["denominator_value"],
        "percentage": kwargs["percentage"],
        "normalization_review_status": kwargs["normalization_review_status"],
        "audit_status": kwargs["audit_status"],
        "reportability_label": kwargs["reportability_label"],
        "reportability_reason": kwargs["reportability_reason"],
        "gate_decision": kwargs["gate_decision"],
        "representative_quote_ids_json": json_cell(kwargs["representative_quote_ids"]),
        "source_claim_ids_json": json_cell(kwargs["source_claim_ids"]),
        "source_comment_ids_json": json_cell(kwargs["source_comment_ids"]),
        "source_a3_analysis_ids_json": json_cell(kwargs["source_a3_ids"]),
        "source_a2_run_ids_json": json_cell(kwargs["source_a2_ids"]),
        "limitations_json": json_cell(kwargs["limitations"]),
        "created_at_utc": utc_now_iso(),
    }


def _representative_quote_ids(claim_ids: list[str], quote_ids_by_claim) -> list[str]:
    out: list[str] = []
    for claim_id in claim_ids:
        for quote_id in quote_ids_by_claim.get(claim_id, []):
            if quote_id and quote_id not in out:
                out.append(quote_id)
            if len(out) >= 3:
                return out
    return out


def _limitations(review_status: str, denominators: dict[str, int]) -> list[str]:
    limitations = ["no_patient_denominator", "private_review_only"]
    if review_status != "accepted":
        limitations.append("normalization_not_accepted")
    if denominators.get("n_claims_audited", 0) == 0:
        limitations.append("unaudited_claims")
    return limitations


def _context_card(report_id: str, claims: list[dict[str, str]], denominators: dict[str, int], source_a3_ids: list[str], source_a2_ids: list[str], run_report: dict[str, str]) -> dict[str, Any]:
    claim_ids = [row.get("claim_id", "") for row in claims if row.get("claim_id")]
    comment_ids = sorted({row.get("comment_id", "") for row in claims if row.get("comment_id")})
    return _card(
        report_id=report_id,
        finding_type="context_sensitive_claim_queue",
        title="Context-sensitive claim queue",
        summary=f"{len(claims)} claims used context or had attribution confidence below high.",
        claim_type="",
        label="",
        analysis_bucket="",
        n_claims=len(claims),
        n_comments=len(comment_ids),
        n_source_runs=len(source_a2_ids),
        n_audited_claims=denominators.get("n_claims_audited", 0),
        n_audited_comments=denominators.get("n_comments_audited", 0),
        denominator_name="n_claims_after_normalization",
        denominator_value=denominators.get("n_claims_after_normalization", 0),
        percentage=percent(len(claims), denominators.get("n_claims_after_normalization", 0)),
        normalization_review_status="",
        audit_status=run_report.get("audit_status", "unaudited"),
        reportability_label="exploratory",
        reportability_reason="context_sensitive_review_queue",
        gate_decision=run_report.get("gate_decision", "proceed_to_more_audit"),
        representative_quote_ids=[],
        source_claim_ids=claim_ids,
        source_comment_ids=comment_ids,
        source_a3_ids=source_a3_ids,
        source_a2_ids=source_a2_ids,
        limitations=["requires_manual_context_review"],
    )
