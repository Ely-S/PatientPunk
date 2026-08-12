"""Review failed Long COVID candidates for reuse outside the clean NATURAL premise."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_CT_AUDIT = (
    PACKAGE_ROOT
    / "data"
    / "nikita_ctgov_structured_learnable"
    / "long_covid_structured_audit.csv"
)
DEFAULT_NON_CT_AUDIT = (
    PACKAGE_ROOT
    / "data"
    / "non_ctgov_structured_learnable"
    / "long_covid_non_ctgov_structured_audit.csv"
)
DEFAULT_OUTPUT = PACKAGE_ROOT / "data" / "long_covid_non_premise_usability_review.csv"

app = typer.Typer(add_completion=False)
console = Console()


class UsabilityReviewRow(BaseModel):
    """Persisted row for failed-candidate usability review."""

    source: str
    trial_id: str
    title: str
    intervention: str
    intervention_type: str
    endpoint_signal: str
    blinded: str
    single_agent: str
    results_reference_found: str
    reuse_bucket: str
    usable_for: str
    why_not_clean: str


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def ct_reuse_bucket(row: dict[str, str]) -> tuple[str, str]:
    access = normalize_text(row.get("intervention_accessibility"))
    if access == "behavioral_or_device":
        return (
            "medium",
            "Usable for a broader Long COVID intervention benchmark, not for self-obtainable drug corpus signal.",
        )
    if access == "clinical_administered":
        return (
            "medium",
            "Usable only if expanding NATURAL to clinic-administered drugs, biologics, or procedures.",
        )
    if access == "prescription_oral" and normalize_text(row.get("single_agent")) == "False":
        return (
            "high_rework",
            "Potentially usable if fixed-combination or platform arms are represented as one product or decomposed carefully.",
        )
    if access == "prescription_oral" and normalize_text(row.get("endpoint_signal")) == "no":
        return (
            "medium_rework",
            "Potentially usable only if a real patient efficacy endpoint can be selected instead of the administrative primary endpoint.",
        )
    if access == "broad_individualized":
        return (
            "low",
            "Weak treatment-specific signal because the active treatment is individualized, not one named product.",
        )
    return ("low", "Do not use in the clean treatment-specific NATURAL set.")


def non_ct_reuse_bucket(row: dict[str, str]) -> tuple[str, str]:
    reason = normalize_text(row.get("screen_reason"))
    registry = normalize_text(row.get("registry")).lower()
    if registry == "eudract":
        return (
            "not_assessed",
            "Not assessed yet because this project lacks a structured EudraCT fetch adapter.",
        )
    if normalize_text(row.get("passes_structural_screen")) == "True":
        accessibility = normalize_text(row.get("intervention_accessibility"))
        intervention_type = normalize_text(row.get("intervention_type")).lower()
        if accessibility == "behavioral_or_device":
            return (
                "medium",
                "Usable for a broader Long COVID intervention benchmark, not for self-obtainable drug corpus signal.",
            )
        if accessibility == "clinical_administered":
            return (
                "medium",
                "Usable only if expanding NATURAL to clinic-administered drugs, biologics, or procedures.",
            )
        if intervention_type == "drug" and normalize_text(row.get("single_agent")) == "False":
            return (
                "high_rework",
                "Potentially usable if platform or multi-drug arms are decomposed carefully.",
            )
        if intervention_type == "supplement":
            return (
                "medium_rework",
                "Potentially usable if the actual supplement or product can be separated from the diet or program intervention.",
            )
        if normalize_text(row.get("endpoint_signal")) == "no":
            return (
                "medium_rework",
                "Potentially usable only if a real patient efficacy endpoint can be selected.",
            )
    if "no local long covid term" in reason.lower():
        return (
            "not_long_covid",
            "Not usable for the Long COVID benchmark under the local title/condition screen.",
        )
    return ("low", "Do not use in the clean treatment-specific NATURAL set.")


def review_failed_candidates(
    ct_audit_path: Path,
    non_ct_audit_path: Path,
    output_path: Path,
) -> list[UsabilityReviewRow]:
    rows: list[UsabilityReviewRow] = []
    with ct_audit_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if normalize_text(row.get("passes_natural_premise_screen")) == "True":
                continue
            bucket, usable_for = ct_reuse_bucket(row)
            rows.append(
                UsabilityReviewRow(
                    source="ctgov",
                    trial_id=normalize_text(row.get("nct_id")),
                    title=normalize_text(row.get("brief_title")),
                    intervention=normalize_text(row.get("primary_intervention")),
                    intervention_type=normalize_text(row.get("active_intervention_types")),
                    endpoint_signal=normalize_text(row.get("endpoint_signal")),
                    blinded=normalize_text(row.get("blinded")),
                    single_agent=normalize_text(row.get("single_agent")),
                    results_reference_found="True",
                    reuse_bucket=bucket,
                    usable_for=usable_for,
                    why_not_clean=normalize_text(row.get("natural_premise_reason")),
                )
            )
    with non_ct_audit_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if normalize_text(row.get("passes_natural_premise_screen")) == "True":
                continue
            bucket, usable_for = non_ct_reuse_bucket(row)
            rows.append(
                UsabilityReviewRow(
                    source="non_ctgov",
                    trial_id=normalize_text(row.get("trial_id")),
                    title=normalize_text(row.get("title")),
                    intervention=normalize_text(row.get("intervention"))[:500],
                    intervention_type=normalize_text(row.get("intervention_type")),
                    endpoint_signal=normalize_text(row.get("endpoint_signal")),
                    blinded=normalize_text(row.get("blinded")),
                    single_agent=normalize_text(row.get("single_agent")),
                    results_reference_found=normalize_text(row.get("results_reference_found")),
                    reuse_bucket=bucket,
                    usable_for=usable_for,
                    why_not_clean=normalize_text(row.get("screen_reason")),
                )
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(UsabilityReviewRow.model_fields))
        writer.writeheader()
        writer.writerows(row.model_dump() for row in rows)
    return rows


def render_summary(rows: list[UsabilityReviewRow], output_path: Path) -> None:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.reuse_bucket] = counts.get(row.reuse_bucket, 0) + 1
    table = Table(title="Failed-candidate usability buckets")
    table.add_column("Bucket")
    table.add_column("Count", justify="right")
    for bucket, count in sorted(counts.items(), key=lambda item: item[0]):
        table.add_row(bucket, str(count))
    console.print(table)
    console.print(f"Wrote {output_path}")


@app.command()
def main(
    ct_audit_path: Path = typer.Option(
        DEFAULT_CT_AUDIT,
        "--ct-audit",
        help="CT.gov structured audit CSV.",
    ),
    non_ct_audit_path: Path = typer.Option(
        DEFAULT_NON_CT_AUDIT,
        "--non-ct-audit",
        help="Non-CT.gov structured audit CSV.",
    ),
    output_path: Path = typer.Option(
        DEFAULT_OUTPUT,
        "--output",
        "-o",
        help="CSV path for failed-candidate usability review.",
    ),
) -> None:
    """Write a review CSV for candidates excluded from the clean premise set."""

    try:
        rows = review_failed_candidates(ct_audit_path, non_ct_audit_path, output_path)
    except Exception as exc:
        console.print(f"[red]Failed to review excluded candidates:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    render_summary(rows, output_path)


if __name__ == "__main__":
    sys.exit(app())
