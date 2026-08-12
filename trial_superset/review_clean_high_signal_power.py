"""Approximate power review for clean high-signal Long COVID trials."""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = PACKAGE_ROOT / "data" / "clean_high_signal_reddit_trials.csv"
DEFAULT_CT_REPORT_DIR = PACKAGE_ROOT / "data" / "nikita_ctgov_structured_learnable" / "nct_reports"
DEFAULT_NON_CT_CLEAN = (
    PACKAGE_ROOT
    / "data"
    / "non_ctgov_structured_learnable"
    / "long_covid_non_ctgov_structured_learnable.csv"
)
DEFAULT_OUTPUT = PACKAGE_ROOT / "data" / "clean_high_signal_power_review.csv"
Z_ALPHA_TWO_SIDED_05 = 1.959963984540054
Z_POWER_80 = 0.8416212335729143
MDE_MULTIPLIER_80_POWER = Z_ALPHA_TWO_SIDED_05 + Z_POWER_80

app = typer.Typer(add_completion=False)
console = Console()


class PowerReviewRow(BaseModel):
    """Persisted approximate power-review row."""

    source_repository: str
    trial_id: str
    treatment_signal_label: str
    title: str
    clinical_power_basis: str
    n_treatment: int | None
    n_control: int | None
    total_outcome_n: int | None
    mde_smd_80_power_alpha_0_05: float | None
    clinical_power_rating: str
    primary_or_first_outcome: str
    outcome_param_type: str
    outcome_dispersion_type: str
    observed_treatment_value: float | None
    observed_control_value: float | None
    observed_difference_treatment_minus_control: float | None
    approximate_raw_mde_80_power_alpha_0_05: float | None
    observed_difference_to_mde_ratio: float | None
    clinical_power_note: str
    pre_reddit_records: int
    pre_reddit_distinct_authors: int
    reddit_author_moe_worst_case_pp: float
    reddit_signal_rating: str
    reddit_signal_note: str


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def parse_int(value: object) -> int:
    text = normalize_text(value)
    return int(float(text)) if text else 0


def parse_float(value: object) -> float | None:
    text = normalize_text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def read_csv(path: Path, encoding: str = "utf-8") -> list[dict[str, str]]:
    if not path.exists():
        raise typer.BadParameter(f"Required CSV does not exist: {path}")
    with path.open("r", encoding=encoding, newline="") as handle:
        return list(csv.DictReader(handle))


def get_path(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def mde_smd(n_treatment: int | None, n_control: int | None) -> float | None:
    if not n_treatment or not n_control:
        return None
    return MDE_MULTIPLIER_80_POWER * math.sqrt((1 / n_treatment) + (1 / n_control))


def clinical_power_rating(mde: float | None) -> str:
    if mde is None:
        return "unknown"
    if mde <= 0.5:
        return "adequate_for_moderate_effects"
    if mde <= 0.8:
        return "limited_moderate_to_large_only"
    return "low_large_effects_only"


def reddit_author_moe(authors: int) -> float:
    if authors <= 0:
        return 0.0
    return 100 * 0.98 / math.sqrt(authors)


def reddit_signal_rating(authors: int) -> str:
    if authors >= 300:
        return "strong"
    if authors >= 100:
        return "moderate"
    if authors >= 50:
        return "borderline"
    return "weak"


def group_title_by_id(groups: list[dict[str, Any]]) -> dict[str, str]:
    return {normalize_text(group.get("id")): normalize_text(group.get("title")) for group in groups}


def first_measurement_pair(
    outcome: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
    groups = group_title_by_id(outcome.get("groups", []) or [])
    for outcome_class in outcome.get("classes", []) or []:
        class_title = normalize_text(outcome_class.get("title"))
        for category in outcome_class.get("categories", []) or []:
            measurements = category.get("measurements", []) or []
            treatment_measure: dict[str, Any] | None = None
            control_measure: dict[str, Any] | None = None
            for measurement in measurements:
                title = groups.get(normalize_text(measurement.get("groupId")), "").lower()
                if "placebo" in title or "control" in title:
                    control_measure = measurement
                elif treatment_measure is None:
                    treatment_measure = measurement
            if treatment_measure and control_measure:
                return treatment_measure, control_measure, class_title
    return None, None, ""


def outcome_denoms(outcome: dict[str, Any]) -> tuple[int | None, int | None]:
    groups = group_title_by_id(outcome.get("groups", []) or [])
    treatment_n: int | None = None
    control_n: int | None = None
    for denom in outcome.get("denoms", []) or []:
        for count in denom.get("counts", []) or []:
            group_id = normalize_text(count.get("groupId"))
            title = groups.get(group_id, "").lower()
            value = parse_int(count.get("value"))
            if "placebo" in title or "control" in title:
                control_n = value
            elif treatment_n is None:
                treatment_n = value
    return treatment_n, control_n


def raw_mde_from_spread(
    spread_type: str,
    treatment_spread: float | None,
    control_spread: float | None,
    n_treatment: int | None,
    n_control: int | None,
) -> float | None:
    if treatment_spread is None or control_spread is None:
        return None
    spread = spread_type.lower()
    if "standard error" in spread:
        return MDE_MULTIPLIER_80_POWER * math.sqrt(treatment_spread**2 + control_spread**2)
    if "standard deviation" in spread and n_treatment and n_control:
        pooled_sd = math.sqrt(
            ((n_treatment - 1) * treatment_spread**2 + (n_control - 1) * control_spread**2)
            / (n_treatment + n_control - 2)
        )
        return MDE_MULTIPLIER_80_POWER * pooled_sd * math.sqrt((1 / n_treatment) + (1 / n_control))
    return None


def ctgov_power_fields(trial_id: str, report_dir: Path) -> dict[str, Any]:
    path = report_dir / f"{trial_id}.json"
    if not path.exists():
        return {"clinical_power_basis": "missing CT.gov JSON"}
    doc = json.loads(path.read_text(encoding="utf-8"))
    outcome = next(
        iter(get_path(doc, "resultsSection", "outcomeMeasuresModule", "outcomeMeasures", default=[]) or []),
        None,
    )
    if not outcome:
        enrollment = get_path(doc, "protocolSection", "designModule", "enrollmentInfo", "count")
        n_each = parse_int(enrollment) // 2 if enrollment else None
        return {
            "clinical_power_basis": "protocol enrollment, no structured outcome measure",
            "n_treatment": n_each,
            "n_control": n_each,
            "clinical_power_note": "No structured outcome measure found.",
        }

    n_treatment, n_control = outcome_denoms(outcome)
    treatment_measure, control_measure, class_title = first_measurement_pair(outcome)
    treatment_value = parse_float((treatment_measure or {}).get("value"))
    control_value = parse_float((control_measure or {}).get("value"))
    treatment_spread = parse_float((treatment_measure or {}).get("spread"))
    control_spread = parse_float((control_measure or {}).get("spread"))
    spread_type = normalize_text(outcome.get("dispersionType"))
    raw_mde = raw_mde_from_spread(
        spread_type,
        treatment_spread,
        control_spread,
        n_treatment,
        n_control,
    )
    observed_diff = (
        treatment_value - control_value
        if treatment_value is not None and control_value is not None
        else None
    )
    ratio = (
        abs(observed_diff) / raw_mde
        if observed_diff is not None and raw_mde not in (None, 0)
        else None
    )
    outcome_title = normalize_text(outcome.get("title"))
    if class_title:
        outcome_title = f"{outcome_title}: {class_title}"
    return {
        "clinical_power_basis": "actual CT.gov outcome denominators",
        "n_treatment": n_treatment,
        "n_control": n_control,
        "primary_or_first_outcome": outcome_title,
        "outcome_param_type": normalize_text(outcome.get("paramType")),
        "outcome_dispersion_type": spread_type,
        "observed_treatment_value": treatment_value,
        "observed_control_value": control_value,
        "observed_difference_treatment_minus_control": observed_diff,
        "approximate_raw_mde_80_power_alpha_0_05": raw_mde,
        "observed_difference_to_mde_ratio": ratio,
        "clinical_power_note": (
            "Approximate two-arm calculation from first listed primary outcome/result. "
            "For least-squares means and standard errors, covariance is unknown."
        ),
    }


def non_ct_power_fields(trial: dict[str, str], non_ct_rows: dict[str, dict[str, str]]) -> dict[str, Any]:
    row = non_ct_rows.get(trial["trial_id"], {})
    total = parse_int(row.get("total_final_enrolment")) or None
    n_treatment = math.ceil(total / 2) if total else None
    n_control = total // 2 if total else None
    return {
        "clinical_power_basis": "ISRCTN total final enrollment, assumed 1:1 randomization",
        "n_treatment": n_treatment,
        "n_control": n_control,
        "primary_or_first_outcome": normalize_text(row.get("primary_outcome")),
        "outcome_param_type": "unknown",
        "outcome_dispersion_type": "not available in structured registry row",
        "observed_treatment_value": None,
        "observed_control_value": None,
        "observed_difference_treatment_minus_control": None,
        "approximate_raw_mde_80_power_alpha_0_05": None,
        "observed_difference_to_mde_ratio": None,
        "clinical_power_note": (
            "No structured per-arm results were available. Clinical power is based only on "
            "final enrollment and assumed 1:1 allocation."
        ),
    }


def build_power_review(
    input_path: Path,
    ct_report_dir: Path,
    non_ct_clean_path: Path,
    output_path: Path,
) -> list[PowerReviewRow]:
    trial_rows = read_csv(input_path)
    non_ct_rows = {row["trial_id"]: row for row in read_csv(non_ct_clean_path)}
    output_rows: list[PowerReviewRow] = []

    for trial in trial_rows:
        if trial["source_repository"] == "ClinicalTrials.gov":
            clinical = ctgov_power_fields(trial["trial_id"], ct_report_dir)
        else:
            clinical = non_ct_power_fields(trial, non_ct_rows)
        n_treatment = clinical.get("n_treatment")
        n_control = clinical.get("n_control")
        standardized_mde = mde_smd(n_treatment, n_control)
        pre_authors = parse_int(trial["pre_reddit_distinct_authors"])
        output_rows.append(
            PowerReviewRow(
                source_repository=trial["source_repository"],
                trial_id=trial["trial_id"],
                treatment_signal_label=trial["treatment_signal_label"],
                title=trial["title"],
                clinical_power_basis=clinical.get("clinical_power_basis", ""),
                n_treatment=n_treatment,
                n_control=n_control,
                total_outcome_n=(n_treatment + n_control) if n_treatment and n_control else None,
                mde_smd_80_power_alpha_0_05=round(standardized_mde, 3)
                if standardized_mde is not None
                else None,
                clinical_power_rating=clinical_power_rating(standardized_mde),
                primary_or_first_outcome=clinical.get("primary_or_first_outcome", ""),
                outcome_param_type=clinical.get("outcome_param_type", ""),
                outcome_dispersion_type=clinical.get("outcome_dispersion_type", ""),
                observed_treatment_value=clinical.get("observed_treatment_value"),
                observed_control_value=clinical.get("observed_control_value"),
                observed_difference_treatment_minus_control=round(
                    clinical["observed_difference_treatment_minus_control"], 3
                )
                if clinical.get("observed_difference_treatment_minus_control") is not None
                else None,
                approximate_raw_mde_80_power_alpha_0_05=round(
                    clinical["approximate_raw_mde_80_power_alpha_0_05"], 3
                )
                if clinical.get("approximate_raw_mde_80_power_alpha_0_05") is not None
                else None,
                observed_difference_to_mde_ratio=round(
                    clinical["observed_difference_to_mde_ratio"], 3
                )
                if clinical.get("observed_difference_to_mde_ratio") is not None
                else None,
                clinical_power_note=clinical.get("clinical_power_note", ""),
                pre_reddit_records=parse_int(trial["pre_reddit_records"]),
                pre_reddit_distinct_authors=pre_authors,
                reddit_author_moe_worst_case_pp=round(reddit_author_moe(pre_authors), 1),
                reddit_signal_rating=reddit_signal_rating(pre_authors),
                reddit_signal_note=(
                    "Worst-case author-level margin of error assumes a 50% binary rate across "
                    "distinct authors. It measures Reddit signal precision, not trial efficacy."
                ),
            )
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(PowerReviewRow.model_fields))
        writer.writeheader()
        writer.writerows(row.model_dump() for row in output_rows)
    return output_rows


def render_summary(rows: list[PowerReviewRow], output_path: Path) -> None:
    table = Table(title="Clean high-signal power review")
    table.add_column("Trial")
    table.add_column("Treatment")
    table.add_column("n", justify="right")
    table.add_column("MDE SMD", justify="right")
    table.add_column("Clinical")
    table.add_column("Reddit authors", justify="right")
    table.add_column("Reddit")
    for row in rows:
        table.add_row(
            row.trial_id,
            row.treatment_signal_label,
            str(row.total_outcome_n or ""),
            str(row.mde_smd_80_power_alpha_0_05 or ""),
            row.clinical_power_rating,
            str(row.pre_reddit_distinct_authors),
            row.reddit_signal_rating,
        )
    console.print(table)
    console.print(f"Wrote {output_path}")


@app.command()
def main(
    input_path: Path = typer.Option(
        DEFAULT_INPUT,
        "--input",
        "-i",
        help="Clean high-signal Reddit trial CSV.",
    ),
    ct_report_dir: Path = typer.Option(
        DEFAULT_CT_REPORT_DIR,
        "--ct-report-dir",
        help="Directory containing CT.gov NCT JSON reports.",
    ),
    non_ct_clean_path: Path = typer.Option(
        DEFAULT_NON_CT_CLEAN,
        "--non-ct-clean",
        help="Clean non-CT.gov screen CSV.",
    ),
    output_path: Path = typer.Option(
        DEFAULT_OUTPUT,
        "--output",
        "-o",
        help="Output CSV path.",
    ),
) -> None:
    """Write approximate clinical and Reddit signal power checks."""

    try:
        rows = build_power_review(input_path, ct_report_dir, non_ct_clean_path, output_path)
    except typer.BadParameter:
        raise
    except Exception as exc:
        console.print(f"[red]Failed to build power review:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    render_summary(rows, output_path)


if __name__ == "__main__":
    sys.exit(app())
