"""Build clean Long COVID benchmark trials with enough Reddit signal.

This joins the clean NATURAL-premise trial screens to the Reddit mention-count
tables and excludes trials that require rescue or rework.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_CT_CLEAN = (
    PACKAGE_ROOT
    / "data"
    / "nikita_ctgov_structured_learnable"
    / "long_covid_structured_learnable.csv"
)
DEFAULT_NON_CT_CLEAN = (
    PACKAGE_ROOT
    / "data"
    / "non_ctgov_structured_learnable"
    / "long_covid_non_ctgov_structured_learnable.csv"
)
DEFAULT_REDDIT_COUNTS = PACKAGE_ROOT / "data" / "covidlonghaulers_treatment_signal_counts.csv"
DEFAULT_ADDITIONAL_REDDIT_COUNTS = (
    PACKAGE_ROOT / "data" / "covidlonghaulers_additional_candidate_signal_counts.csv"
)
DEFAULT_OUTPUT = PACKAGE_ROOT / "data" / "clean_high_signal_reddit_trials.csv"
REDDIT_CORPUS = "r/covidlonghaulers posts_all + comments_all"

app = typer.Typer(add_completion=False)
console = Console()


class CleanHighSignalTrialRow(BaseModel):
    """Persisted row for a clean trial with sufficient pre-results Reddit signal."""

    source_repository: str
    trial_id: str
    title: str
    condition: str
    treatment_or_intervention: str
    treatment_signal_label: str
    corpus_learnable_tier: str
    intervention_accessibility: str
    endpoint_signal: str
    results_or_cutoff_date: str
    reddit_corpus: str
    reddit_threshold_basis: str
    threshold_value: int
    pre_reddit_records: int
    pre_reddit_posts: int
    pre_reddit_comments: int
    pre_reddit_distinct_authors: int
    all_reddit_records: int
    all_reddit_distinct_authors: int
    needs_rescue_or_rework: bool
    requires_non_ctgov_schema_adaptation: bool
    source_trial_csv: str
    source_reddit_count_csv: str


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def parse_int(value: object) -> int:
    text = normalize_text(value)
    return int(text) if text else 0


def read_csv(path: Path, encoding: str = "utf-8") -> list[dict[str, str]]:
    if not path.exists():
        raise typer.BadParameter(f"Required CSV does not exist: {path}")
    with path.open("r", encoding=encoding, newline="") as handle:
        return list(csv.DictReader(handle))


def build_ct_rows(
    ct_clean_path: Path,
    reddit_counts_path: Path,
    output_threshold: int,
) -> list[CleanHighSignalTrialRow]:
    ct_rows = read_csv(ct_clean_path, encoding="utf-8-sig")
    count_rows = read_csv(reddit_counts_path)
    counts_by_nct = {row["nct_id"]: row for row in count_rows}
    output_rows: list[CleanHighSignalTrialRow] = []

    for trial in ct_rows:
        nct_id = trial["nct_id"]
        counts = counts_by_nct.get(nct_id)
        if not counts:
            continue
        pre_records = parse_int(counts.get("pre_results_records"))
        if pre_records <= output_threshold:
            continue
        output_rows.append(
            CleanHighSignalTrialRow(
                source_repository="ClinicalTrials.gov",
                trial_id=nct_id,
                title=normalize_text(trial.get("brief_title")),
                condition=normalize_text(trial.get("conditions")),
                treatment_or_intervention=normalize_text(trial.get("primary_intervention")),
                treatment_signal_label=normalize_text(counts.get("treatment")),
                corpus_learnable_tier=normalize_text(trial.get("corpus_learnable_tier")),
                intervention_accessibility=normalize_text(trial.get("intervention_accessibility")),
                endpoint_signal=normalize_text(trial.get("endpoint_signal")),
                results_or_cutoff_date=normalize_text(counts.get("results_first_post_date")),
                reddit_corpus=REDDIT_CORPUS,
                reddit_threshold_basis="pre_results_records",
                threshold_value=output_threshold,
                pre_reddit_records=pre_records,
                pre_reddit_posts=parse_int(counts.get("pre_results_posts")),
                pre_reddit_comments=parse_int(counts.get("pre_results_comments")),
                pre_reddit_distinct_authors=parse_int(counts.get("pre_results_distinct_authors")),
                all_reddit_records=parse_int(counts.get("all_records")),
                all_reddit_distinct_authors=parse_int(counts.get("all_distinct_authors")),
                needs_rescue_or_rework=False,
                requires_non_ctgov_schema_adaptation=False,
                source_trial_csv=str(ct_clean_path),
                source_reddit_count_csv=str(reddit_counts_path),
            )
        )
    return output_rows


def build_non_ct_rows(
    non_ct_clean_path: Path,
    additional_counts_path: Path,
    output_threshold: int,
) -> list[CleanHighSignalTrialRow]:
    non_ct_rows = read_csv(non_ct_clean_path)
    count_rows = read_csv(additional_counts_path)
    counts_by_trial_id = {row["trial_id"]: row for row in count_rows}
    output_rows: list[CleanHighSignalTrialRow] = []

    for trial in non_ct_rows:
        trial_id = trial["trial_id"]
        counts = counts_by_trial_id.get(trial_id)
        if not counts:
            continue
        pre_records = parse_int(counts.get("pre_cutoff_records"))
        if pre_records <= output_threshold:
            continue
        output_rows.append(
            CleanHighSignalTrialRow(
                source_repository=normalize_text(trial.get("registry")) or "non-CT.gov",
                trial_id=trial_id,
                title=normalize_text(trial.get("title")),
                condition=normalize_text(trial.get("condition")),
                treatment_or_intervention=normalize_text(trial.get("drug_names"))
                or normalize_text(trial.get("intervention_type")),
                treatment_signal_label=normalize_text(counts.get("candidate")),
                corpus_learnable_tier=normalize_text(trial.get("corpus_learnable_tier")),
                intervention_accessibility=normalize_text(trial.get("intervention_accessibility")),
                endpoint_signal=normalize_text(trial.get("endpoint_signal")),
                results_or_cutoff_date=normalize_text(counts.get("result_or_cutoff_date")),
                reddit_corpus=REDDIT_CORPUS,
                reddit_threshold_basis="pre_cutoff_records",
                threshold_value=output_threshold,
                pre_reddit_records=pre_records,
                pre_reddit_posts=parse_int(counts.get("pre_cutoff_posts")),
                pre_reddit_comments=parse_int(counts.get("pre_cutoff_comments")),
                pre_reddit_distinct_authors=parse_int(counts.get("pre_cutoff_distinct_authors")),
                all_reddit_records=parse_int(counts.get("all_records")),
                all_reddit_distinct_authors=parse_int(counts.get("all_distinct_authors")),
                needs_rescue_or_rework=False,
                requires_non_ctgov_schema_adaptation=True,
                source_trial_csv=str(non_ct_clean_path),
                source_reddit_count_csv=str(additional_counts_path),
            )
        )
    return output_rows


def build_output(
    ct_clean_path: Path,
    non_ct_clean_path: Path,
    reddit_counts_path: Path,
    additional_counts_path: Path,
    output_path: Path,
    threshold: int,
) -> list[CleanHighSignalTrialRow]:
    rows = [
        *build_ct_rows(ct_clean_path, reddit_counts_path, threshold),
        *build_non_ct_rows(non_ct_clean_path, additional_counts_path, threshold),
    ]
    rows.sort(key=lambda row: (-row.pre_reddit_records, row.source_repository, row.trial_id))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CleanHighSignalTrialRow.model_fields))
        writer.writeheader()
        writer.writerows(row.model_dump() for row in rows)
    return rows


def render_summary(rows: list[CleanHighSignalTrialRow], output_path: Path) -> None:
    table = Table(title="Clean high-signal Reddit trials")
    table.add_column("Repository")
    table.add_column("Trial")
    table.add_column("Treatment")
    table.add_column("Pre Reddit records", justify="right")
    table.add_column("Pre Reddit authors", justify="right")
    for row in rows:
        table.add_row(
            row.source_repository,
            row.trial_id,
            row.treatment_signal_label,
            str(row.pre_reddit_records),
            str(row.pre_reddit_distinct_authors),
        )
    console.print(table)
    console.print(f"Wrote {output_path}")


@app.command()
def main(
    ct_clean_path: Path = typer.Option(
        DEFAULT_CT_CLEAN,
        "--ct-clean",
        help="Clean CT.gov NATURAL-premise CSV.",
    ),
    non_ct_clean_path: Path = typer.Option(
        DEFAULT_NON_CT_CLEAN,
        "--non-ct-clean",
        help="Clean non-CT.gov NATURAL-premise CSV.",
    ),
    reddit_counts_path: Path = typer.Option(
        DEFAULT_REDDIT_COUNTS,
        "--reddit-counts",
        help="Reddit count CSV for clean CT.gov treatments.",
    ),
    additional_counts_path: Path = typer.Option(
        DEFAULT_ADDITIONAL_REDDIT_COUNTS,
        "--additional-counts",
        help="Reddit count CSV for clean non-CT.gov and rework candidates.",
    ),
    output_path: Path = typer.Option(
        DEFAULT_OUTPUT,
        "--output",
        "-o",
        help="Output CSV path.",
    ),
    threshold: int = typer.Option(
        100,
        "--threshold",
        help="Require pre-results or pre-cutoff Reddit records to be greater than this value.",
    ),
) -> None:
    """Write clean NATURAL-premise trials with more than threshold Reddit mentions."""

    try:
        rows = build_output(
            ct_clean_path,
            non_ct_clean_path,
            reddit_counts_path,
            additional_counts_path,
            output_path,
            threshold,
        )
    except typer.BadParameter:
        raise
    except Exception as exc:
        console.print(f"[red]Failed to build clean high-signal CSV:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    render_summary(rows, output_path)


if __name__ == "__main__":
    sys.exit(app())
