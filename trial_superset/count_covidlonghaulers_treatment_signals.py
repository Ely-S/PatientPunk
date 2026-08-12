"""Count treatment-name signal in the r/covidlonghaulers corpus.

The output is a raw mention-volume audit for the Long COVID benchmark treatments.
It does not infer sentiment, outcome, dose, or treatment use.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

from benchmark_treatment_aliases import TREATMENT_SIGNAL_SPECS, TreatmentSignalSpec

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_PATIENTPUNK_DATA = PROJECT_ROOT.parent / "PatientPunk_data"
DEFAULT_OUTPUT = PACKAGE_ROOT / "data" / "covidlonghaulers_treatment_signal_counts.csv"
DEFAULT_CT_REPORT_DIRS = (
    PACKAGE_ROOT / "data" / "nikita_ctgov_structured_learnable" / "nct_reports",
    PACKAGE_ROOT / "data" / "nikita_ctgov_structured_8" / "nct_reports",
)
CORPUS_FILES = (
    ("post", "r_covidlonghaulers_posts_all.jsonl"),
    ("comment", "r_covidlonghaulers_comments_all.jsonl"),
)
EXCLUDED_AUTHORS = {"[deleted]", "AutoModerator"}

app = typer.Typer(add_completion=False)
console = Console()


class TrialMeta(BaseModel):
    """Metadata needed to compute pre-results corpus availability."""

    nct_id: str
    title: str = ""
    interventions: str = ""
    results_first_post_date: str = ""
    results_first_post_timestamp: float | None = None


class TreatmentSignalCountRow(BaseModel):
    """Persisted CSV row for treatment mention counts."""

    treatment: str
    nct_id: str
    clean_treatment_specific_signal: bool
    ctgov_title: str
    ctgov_interventions: str
    aliases: str
    sensitivity_aliases: str
    results_first_post_date: str
    all_records: int
    all_posts: int
    all_comments: int
    all_distinct_authors: int
    all_alias_hits: int
    pre_results_records: int
    pre_results_posts: int
    pre_results_comments: int
    pre_results_distinct_authors: int
    sensitivity_only_records: int
    sensitivity_only_posts: int
    sensitivity_only_comments: int
    sensitivity_only_distinct_authors: int
    first_mention_date: str
    last_mention_date: str


class CorpusSummary(BaseModel):
    """Corpus-level audit summary."""

    posts: int = 0
    comments: int = 0
    first_date: str = ""
    last_date: str = ""
    bad_json: int = 0


@dataclass
class TreatmentStats:
    records: int = 0
    posts: int = 0
    comments: int = 0
    alias_hits: int = 0
    authors: set[str] = field(default_factory=set)
    first_ts: float | None = None
    last_ts: float | None = None
    pre_results_records: int = 0
    pre_results_posts: int = 0
    pre_results_comments: int = 0
    pre_results_authors: set[str] = field(default_factory=set)
    sensitivity_only_records: int = 0
    sensitivity_only_posts: int = 0
    sensitivity_only_comments: int = 0
    sensitivity_only_authors: set[str] = field(default_factory=set)


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def get_path(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def parse_date_to_timestamp(value: str) -> float | None:
    text = normalize_text(value)
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(text[: len(datetime.now().strftime(fmt))], fmt).replace(
                tzinfo=timezone.utc
            ).timestamp()
        except ValueError:
            continue
    return None


def format_date(timestamp: float | None) -> str:
    if timestamp is None:
        return ""
    return datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()


def resolve_ct_report_dirs(explicit_dir: Path | None) -> tuple[Path, ...]:
    if explicit_dir:
        if not explicit_dir.exists():
            raise typer.BadParameter(f"CT.gov report directory does not exist: {explicit_dir}")
        return (explicit_dir, *(path for path in DEFAULT_CT_REPORT_DIRS if path.exists() and path != explicit_dir))
    existing = tuple(path for path in DEFAULT_CT_REPORT_DIRS if path.exists())
    if existing:
        return existing
    raise typer.BadParameter(
        "No CT.gov report directory found. Run pull_ctgov_long_covid_structured_learnable.py first."
    )


def load_trial_meta(report_dirs: tuple[Path, ...], spec: TreatmentSignalSpec) -> TrialMeta:
    path = next(
        (
            report_dir / f"{spec.nct_id}.json"
            for report_dir in report_dirs
            if (report_dir / f"{spec.nct_id}.json").exists()
        ),
        None,
    )
    if path is None:
        return TrialMeta(nct_id=spec.nct_id)
    doc = json.loads(path.read_text(encoding="utf-8"))
    title = normalize_text(get_path(doc, "protocolSection", "identificationModule", "briefTitle"))
    result_date = normalize_text(
        get_path(doc, "protocolSection", "statusModule", "resultsFirstPostDateStruct", "date")
        or get_path(doc, "protocolSection", "statusModule", "resultsFirstSubmitDate")
    )
    intervention_labels: list[str] = []
    interventions = get_path(
        doc,
        "protocolSection",
        "armsInterventionsModule",
        "interventions",
        default=[],
    )
    for intervention in interventions or []:
        if not isinstance(intervention, dict):
            continue
        labels = [normalize_text(intervention.get("name"))]
        labels.extend(normalize_text(value) for value in intervention.get("otherNames", []) or [])
        label = "; ".join(value for value in labels if value)
        if label:
            intervention_labels.append(label)
    return TrialMeta(
        nct_id=spec.nct_id,
        title=title,
        interventions=" | ".join(intervention_labels),
        results_first_post_date=result_date,
        results_first_post_timestamp=parse_date_to_timestamp(result_date),
    )


def compile_pattern(patterns: tuple[str, ...]) -> re.Pattern[str] | None:
    if not patterns:
        return None
    return re.compile("|".join(f"(?:{pattern})" for pattern in patterns), re.IGNORECASE)


def corpus_text(kind: str, row: dict[str, Any]) -> str:
    if kind == "post":
        return "\n".join(normalize_text(row.get(field)) for field in ("title", "selftext"))
    return normalize_text(row.get("body"))


def count_treatment_signals(
    data_root: Path,
    ct_report_dirs: tuple[Path, ...],
    output_path: Path,
) -> tuple[list[TreatmentSignalCountRow], CorpusSummary]:
    metas = {spec.treatment: load_trial_meta(ct_report_dirs, spec) for spec in TREATMENT_SIGNAL_SPECS}
    main_patterns = {
        spec.treatment: compile_pattern(spec.aliases) for spec in TREATMENT_SIGNAL_SPECS
    }
    sensitivity_patterns = {
        spec.treatment: compile_pattern(spec.sensitivity_aliases)
        for spec in TREATMENT_SIGNAL_SPECS
    }
    stats = {spec.treatment: TreatmentStats() for spec in TREATMENT_SIGNAL_SPECS}
    corpus_counts = {"post": 0, "comment": 0}
    corpus_first: float | None = None
    corpus_last: float | None = None
    bad_json = 0

    for kind, filename in CORPUS_FILES:
        path = data_root / filename
        if not path.exists():
            raise typer.BadParameter(f"Corpus file does not exist: {path}")
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    bad_json += 1
                    continue
                corpus_counts[kind] += 1
                try:
                    timestamp = float(row["created_utc"]) if row.get("created_utc") is not None else None
                except (TypeError, ValueError):
                    timestamp = None
                if timestamp is not None:
                    corpus_first = timestamp if corpus_first is None else min(corpus_first, timestamp)
                    corpus_last = timestamp if corpus_last is None else max(corpus_last, timestamp)
                text = corpus_text(kind, row)
                if not text:
                    continue
                author = normalize_text(row.get("author"))
                count_author = bool(author and author not in EXCLUDED_AUTHORS)
                for spec in TREATMENT_SIGNAL_SPECS:
                    main_pattern = main_patterns[spec.treatment]
                    sensitivity_pattern = sensitivity_patterns[spec.treatment]
                    main_hits = list(main_pattern.finditer(text)) if main_pattern else []
                    sensitivity_hits = (
                        list(sensitivity_pattern.finditer(text)) if sensitivity_pattern else []
                    )
                    treatment_stats = stats[spec.treatment]
                    if main_hits:
                        treatment_stats.records += 1
                        treatment_stats.alias_hits += len(main_hits)
                        if kind == "post":
                            treatment_stats.posts += 1
                        else:
                            treatment_stats.comments += 1
                        if count_author:
                            treatment_stats.authors.add(author)
                        if timestamp is not None:
                            treatment_stats.first_ts = (
                                timestamp
                                if treatment_stats.first_ts is None
                                else min(treatment_stats.first_ts, timestamp)
                            )
                            treatment_stats.last_ts = (
                                timestamp
                                if treatment_stats.last_ts is None
                                else max(treatment_stats.last_ts, timestamp)
                            )
                            cutoff = metas[spec.treatment].results_first_post_timestamp
                            if cutoff is not None and timestamp < cutoff:
                                treatment_stats.pre_results_records += 1
                                if kind == "post":
                                    treatment_stats.pre_results_posts += 1
                                else:
                                    treatment_stats.pre_results_comments += 1
                                if count_author:
                                    treatment_stats.pre_results_authors.add(author)
                    elif sensitivity_hits:
                        treatment_stats.sensitivity_only_records += 1
                        if kind == "post":
                            treatment_stats.sensitivity_only_posts += 1
                        else:
                            treatment_stats.sensitivity_only_comments += 1
                        if count_author:
                            treatment_stats.sensitivity_only_authors.add(author)

    rows: list[TreatmentSignalCountRow] = []
    for spec in TREATMENT_SIGNAL_SPECS:
        meta = metas[spec.treatment]
        treatment_stats = stats[spec.treatment]
        rows.append(
            TreatmentSignalCountRow(
                treatment=spec.treatment,
                nct_id=spec.nct_id,
                clean_treatment_specific_signal=spec.clean_treatment_specific_signal,
                ctgov_title=meta.title,
                ctgov_interventions=meta.interventions,
                aliases="; ".join(spec.aliases),
                sensitivity_aliases="; ".join(spec.sensitivity_aliases),
                results_first_post_date=meta.results_first_post_date,
                all_records=treatment_stats.records,
                all_posts=treatment_stats.posts,
                all_comments=treatment_stats.comments,
                all_distinct_authors=len(treatment_stats.authors),
                all_alias_hits=treatment_stats.alias_hits,
                pre_results_records=treatment_stats.pre_results_records,
                pre_results_posts=treatment_stats.pre_results_posts,
                pre_results_comments=treatment_stats.pre_results_comments,
                pre_results_distinct_authors=len(treatment_stats.pre_results_authors),
                sensitivity_only_records=treatment_stats.sensitivity_only_records,
                sensitivity_only_posts=treatment_stats.sensitivity_only_posts,
                sensitivity_only_comments=treatment_stats.sensitivity_only_comments,
                sensitivity_only_distinct_authors=len(treatment_stats.sensitivity_only_authors),
                first_mention_date=format_date(treatment_stats.first_ts),
                last_mention_date=format_date(treatment_stats.last_ts),
            )
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TreatmentSignalCountRow.model_fields))
        writer.writeheader()
        writer.writerows(row.model_dump() for row in rows)

    summary = CorpusSummary(
        posts=corpus_counts["post"],
        comments=corpus_counts["comment"],
        first_date=format_date(corpus_first),
        last_date=format_date(corpus_last),
        bad_json=bad_json,
    )
    return rows, summary


def render_summary(rows: list[TreatmentSignalCountRow], summary: CorpusSummary, output_path: Path) -> None:
    table = Table(title="r/covidlonghaulers treatment signal", show_lines=False)
    table.add_column("Treatment")
    table.add_column("Records", justify="right")
    table.add_column("Posts", justify="right")
    table.add_column("Comments", justify="right")
    table.add_column("Authors", justify="right")
    table.add_column("Pre-results", justify="right")
    table.add_column("Sensitivity-only", justify="right")
    for row in rows:
        table.add_row(
            row.treatment,
            str(row.all_records),
            str(row.all_posts),
            str(row.all_comments),
            str(row.all_distinct_authors),
            str(row.pre_results_records),
            str(row.sensitivity_only_records),
        )
    console.print(table)
    console.print(
        f"Corpus: {summary.posts:,} posts, {summary.comments:,} comments, "
        f"{summary.first_date} to {summary.last_date}, bad_json={summary.bad_json}"
    )
    console.print(f"Wrote {output_path}")


@app.command()
def main(
    data_root: Path = typer.Option(
        DEFAULT_PATIENTPUNK_DATA,
        "--data-root",
        help="Directory containing r_covidlonghaulers_posts_all.jsonl and comments_all.jsonl.",
    ),
    ct_report_dir: Path | None = typer.Option(
        None,
        "--ct-report-dir",
        help="Directory containing saved CT.gov NCT JSON reports.",
    ),
    output_path: Path = typer.Option(
        DEFAULT_OUTPUT,
        "--output",
        "-o",
        help="CSV path for treatment signal counts.",
    ),
) -> None:
    """Count raw treatment alias mentions in the covidlonghaulers corpus."""

    resolved_report_dirs = resolve_ct_report_dirs(ct_report_dir)
    try:
        rows, summary = count_treatment_signals(data_root, resolved_report_dirs, output_path)
    except typer.BadParameter:
        raise
    except Exception as exc:
        console.print(f"[red]Failed to count treatment signals:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    render_summary(rows, summary, output_path)


if __name__ == "__main__":
    sys.exit(app())
