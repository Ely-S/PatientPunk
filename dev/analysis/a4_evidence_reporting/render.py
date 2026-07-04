"""Deterministic Markdown rendering for A4 reports."""

from __future__ import annotations

from typing import Any

from dev.analysis.a4_evidence_reporting.common import markdown_table


SAFETY_CODA = (
    "These are self-reported comments from one Reddit community. They are useful "
    "for hypothesis generation and lived-experience mapping, not for estimating "
    "clinical prevalence, treatment efficacy, treatment safety, or medical advice."
)


def render_report_md(*, report_id: str, mode: str, data, findings: list[dict[str, Any]], quote_bank: list[dict[str, Any]], packet: dict[str, Any]) -> str:
    denominators = {row.get("name", ""): row.get("value", "") for row in data.denominators}
    label_findings = [row for row in findings if row.get("finding_type") == "claim_label_frequency"]
    top = label_findings[:20]
    lines = [
        "# A4 Claim Distribution Brief",
        "",
        f"- `report_id`: {report_id}",
        f"- `mode`: {mode}",
        f"- `source_a3_analysis`: {data.analysis_manifest.get('analysis_id', data.paths.analysis_id)}",
        f"- `validation_ok`: {data.analysis_manifest.get('validation_ok')}",
        f"- `max_confidence_label`: {packet.get('render_policy', {}).get('max_confidence_label')}",
        "",
        "## Summary",
        "",
        f"- selected comments: {denominators.get('n_work_items_selected', '0')}",
        f"- normalized claims: {denominators.get('n_claims_after_normalization', '0')}",
        f"- audited comments: {denominators.get('n_comments_audited', '0')}",
        f"- audited claims: {denominators.get('n_claims_audited', '0')}",
        f"- private quote candidates: {len(quote_bank)}",
        "",
    ]
    if top:
        lines.extend(
            [
                "## Top Claim Labels",
                "",
                markdown_table(
                    top,
                    [
                        "claim_type",
                        "normalized_label_canonical",
                        "n_claims",
                        "n_comments",
                        "percentage",
                        "reportability_label",
                    ],
                ).rstrip(),
                "",
            ]
        )
    else:
        lines.extend(["## Top Claim Labels", "", "No normalized claim labels were available for this report.", ""])
    lines.extend(
        [
            "## Reportability",
            "",
            "A4 is using A3 reportability labels without upgrading them. Unreviewed normalization or missing audit keeps findings exploratory.",
            "",
            "## Quotes",
            "",
            "Quote candidates are private review artifacts in this package. Public reports must use reviewed and redacted quotes only.",
            "",
            "## Caveats",
            "",
        ]
    )
    for key, caveat in packet.get("caveats", {}).items():
        lines.append(f"- `{key}`: {caveat.get('render', '')}")
    lines.extend(["", SAFETY_CODA, ""])
    return "\n".join(lines)


def render_methods_md(*, report_id: str, mode: str, data, packet: dict[str, Any]) -> str:
    denominators = data.denominators
    lines = [
        "# Methods",
        "",
        f"- `report_id`: {report_id}",
        f"- `mode`: {mode}",
        f"- `a4_version`: {packet.get('provenance', {}).get('a4_version', '')}",
        f"- `source_a3_analysis`: {data.analysis_manifest.get('analysis_id', data.paths.analysis_id)}",
        f"- `analysis_version`: {data.analysis_manifest.get('analysis_version', '')}",
        f"- `normalization_version`: {data.analysis_manifest.get('normalization_version', '')}",
        f"- `audit_score_version`: {data.analysis_manifest.get('audit_score_version', '')}",
        f"- `source_a2_run_ids`: {', '.join(data.analysis_manifest.get('source_a2_run_ids') or [])}",
        "",
        "## Denominators",
        "",
        markdown_table(denominators, ["name", "value", "source_table", "source_filter", "description"]).rstrip(),
        "",
        "## Source Integrity",
        "",
        "A4 verifies A3 analysis file hashes and source A2 export hashes before building this package.",
        "",
    ]
    return "\n".join(lines)


def render_limitations_md(*, data, packet: dict[str, Any]) -> str:
    lines = ["# Limitations", ""]
    for key, caveat in packet.get("caveats", {}).items():
        lines.append(f"- `{key}`: {caveat.get('render', '')}")
    lines.extend(
        [
            "",
            "This report does not provide patient-level prevalence because the current A3 outputs do not expose a validated author/patient denominator.",
            "",
        ]
    )
    return "\n".join(lines)


def render_provenance_md(*, report_id: str, output_dir, data, manifest: dict[str, Any] | None = None) -> str:
    lines = [
        "# Provenance",
        "",
        f"- `report_id`: {report_id}",
        f"- `report_dir`: {output_dir}",
        f"- `source_a3_analysis`: {data.analysis_manifest.get('analysis_id', data.paths.analysis_id)}",
        f"- `source_a3_dir`: {data.paths.analysis_dir}",
        f"- `source_a2_run_ids`: {', '.join(data.analysis_manifest.get('source_a2_run_ids') or [])}",
        "",
        "## A3 Source Files",
        "",
    ]
    for name, digest in sorted((data.analysis_manifest.get("analysis_file_hashes") or {}).items()):
        lines.append(f"- `{name}`: `{digest}`")
    lines.extend(["", "## A2 Source Files", ""])
    for name, digest in sorted((data.analysis_manifest.get("source_file_hashes") or {}).items()):
        lines.append(f"- `{name}`: `{digest}`")
    if manifest:
        lines.extend(["", "## A4 Report Files", ""])
        for name, digest in sorted((manifest.get("report_file_hashes") or {}).items()):
            lines.append(f"- `{name}`: `{digest}`")
    lines.append("")
    return "\n".join(lines)
