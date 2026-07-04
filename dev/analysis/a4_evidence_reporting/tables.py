"""CSV table views for A4 report packages."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from dev.analysis.a4_evidence_reporting.common import write_csv


def write_table_outputs(output_dir: Path, data, findings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    tables_dir = output_dir / "tables"
    label_rows = _claim_counts_by_label(data.claims, data.reportability)
    type_rows = _claim_counts_by_type(data.claims)
    monthly_rows = _monthly_claim_counts(data.claims)
    reportability_rows = list(data.reportability)
    denominator_rows = list(data.denominators)
    write_csv(tables_dir / "claim_counts_by_label.csv", label_rows)
    write_csv(tables_dir / "claim_counts_by_type.csv", type_rows)
    write_csv(tables_dir / "monthly_claim_counts.csv", monthly_rows)
    write_csv(tables_dir / "reportability_by_label.csv", reportability_rows)
    write_csv(tables_dir / "source_denominators.csv", denominator_rows)
    return {
        "claim_counts_by_label": label_rows,
        "claim_counts_by_type": type_rows,
        "monthly_claim_counts": monthly_rows,
        "reportability_by_label": reportability_rows,
        "source_denominators": denominator_rows,
        "finding_cards": findings,
    }


def _claim_counts_by_label(claims: list[dict[str, str]], reportability: list[dict[str, str]]) -> list[dict[str, Any]]:
    report_lookup = {(row.get("unit"), row.get("key")): row for row in reportability}
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for claim in claims:
        key = (
            claim.get("claim_type", ""),
            claim.get("normalized_label_canonical", ""),
            claim.get("analysis_bucket", ""),
        )
        row = grouped.setdefault(
            key,
            {
                "claim_type": key[0],
                "normalized_label_canonical": key[1],
                "analysis_bucket": key[2],
                "n_claims": 0,
                "comment_ids": set(),
            },
        )
        row["n_claims"] += 1
        if claim.get("comment_id"):
            row["comment_ids"].add(claim["comment_id"])
    out = []
    for row in grouped.values():
        rep = report_lookup.get(("claim_label", f"{row['claim_type']}:{row['normalized_label_canonical']}"), {})
        out.append(
            {
                "claim_type": row["claim_type"],
                "normalized_label_canonical": row["normalized_label_canonical"],
                "analysis_bucket": row["analysis_bucket"],
                "n_claims": row["n_claims"],
                "n_comments": len(row["comment_ids"]),
                "reportability_label": rep.get("reportability_label", ""),
                "reportability_reason": rep.get("reason", ""),
            }
        )
    return sorted(out, key=lambda item: (-item["n_claims"], item["claim_type"], item["normalized_label_canonical"]))


def _claim_counts_by_type(claims: list[dict[str, str]]) -> list[dict[str, Any]]:
    counts = Counter(claim.get("claim_type", "") for claim in claims)
    return [{"claim_type": key, "n_claims": count} for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _monthly_claim_counts(claims: list[dict[str, str]]) -> list[dict[str, Any]]:
    counts = Counter(
        (
            claim.get("year_month", ""),
            claim.get("claim_type", ""),
            claim.get("normalized_label_canonical", ""),
        )
        for claim in claims
    )
    return [
        {
            "year_month": key[0],
            "claim_type": key[1],
            "normalized_label_canonical": key[2],
            "n_claims": count,
        }
        for key, count in sorted(counts.items(), key=lambda item: (item[0][0], item[0][1], item[0][2]))
    ]
