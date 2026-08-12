"""Count Reddit signal for Long COVID benchmark rescue candidates.

These candidates are not in the clean CT.gov structured set, but they are useful
for deciding whether rework is worthwhile.
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

import requests
import typer
from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console
from rich.table import Table

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DEFAULT_PATIENTPUNK_DATA = PROJECT_ROOT.parent / "PatientPunk_data"
DEFAULT_NON_CT_AUDIT = (
    PACKAGE_ROOT
    / "data"
    / "non_ctgov_structured_learnable"
    / "long_covid_non_ctgov_structured_audit.csv"
)
DEFAULT_OUTPUT = PACKAGE_ROOT / "data" / "covidlonghaulers_additional_candidate_signal_counts.csv"
CTGOV_API = "https://clinicaltrials.gov/api/v2/studies"
CORPUS_FILES = (
    ("post", "r_covidlonghaulers_posts_all.jsonl"),
    ("comment", "r_covidlonghaulers_comments_all.jsonl"),
)
EXCLUDED_AUTHORS = {"[deleted]", "AutoModerator"}

app = typer.Typer(add_completion=False)
console = Console()


class CandidateSignalSpec(BaseModel):
    """Regex aliases and trial metadata for one rescue candidate."""

    model_config = ConfigDict(frozen=True)

    candidate: str
    trial_id: str
    source: str
    aliases: tuple[str, ...]
    ctgov_ids: tuple[str, ...] = Field(default_factory=tuple)
    isrctn_id: str = ""
    fallback_cutoff_date: str = ""


class CandidateSignalRow(BaseModel):
    """Persisted CSV row for one rescue-candidate count."""

    candidate: str
    trial_id: str
    source: str
    aliases: str
    result_or_cutoff_date: str
    all_records: int
    all_posts: int
    all_comments: int
    all_distinct_authors: int
    pre_cutoff_records: int
    pre_cutoff_posts: int
    pre_cutoff_comments: int
    pre_cutoff_distinct_authors: int
    first_mention_date: str
    last_mention_date: str


@dataclass
class CandidateStats:
    records: int = 0
    posts: int = 0
    comments: int = 0
    authors: set[str] = field(default_factory=set)
    hits: int = 0
    pre_records: int = 0
    pre_posts: int = 0
    pre_comments: int = 0
    pre_authors: set[str] = field(default_factory=set)
    first_ts: float | None = None
    last_ts: float | None = None


CANDIDATE_SIGNAL_SPECS: tuple[CandidateSignalSpec, ...] = (
    CandidateSignalSpec(
        candidate="Ashwagandha",
        trial_id="ISRCTN12368131",
        source="non_ctgov_clean",
        isrctn_id="ISRCTN12368131",
        fallback_cutoff_date="2025-06-18",
        aliases=(
            r"\bashwagandha\b",
            r"\bwithania\s+somnifera\b",
            r"\bwithania\b",
        ),
    ),
    CandidateSignalSpec(
        candidate="Paxlovid / nirmatrelvir",
        trial_id="NCT05576662;NCT05965726",
        source="ctgov_rework",
        ctgov_ids=("NCT05576662", "NCT05965726"),
        aliases=(
            r"\bpaxlovid\b",
            r"\bnirmatrelvir\b",
        ),
    ),
    CandidateSignalSpec(
        candidate="Famotidine",
        trial_id="ISRCTN10665760",
        source="non_ctgov_rework_stimulate_icp",
        isrctn_id="ISRCTN10665760",
        fallback_cutoff_date="2025-08-07",
        aliases=(
            r"\bfamotidine\b",
            r"\bpepcid\b",
        ),
    ),
    CandidateSignalSpec(
        candidate="Loratadine",
        trial_id="ISRCTN10665760",
        source="non_ctgov_rework_stimulate_icp",
        isrctn_id="ISRCTN10665760",
        fallback_cutoff_date="2025-08-07",
        aliases=(
            r"\bloratadine\b",
            r"\bclaritin\b",
        ),
    ),
    CandidateSignalSpec(
        candidate="Colchicine",
        trial_id="ISRCTN10665760",
        source="non_ctgov_rework_stimulate_icp",
        isrctn_id="ISRCTN10665760",
        fallback_cutoff_date="2025-08-07",
        aliases=(r"\bcolchicine\b",),
    ),
    CandidateSignalSpec(
        candidate="Rivaroxaban",
        trial_id="ISRCTN10665760",
        source="non_ctgov_rework_stimulate_icp",
        isrctn_id="ISRCTN10665760",
        fallback_cutoff_date="2025-08-07",
        aliases=(
            r"\brivaroxaban\b",
            r"\bxarelto\b",
        ),
    ),
    CandidateSignalSpec(
        candidate="Remdesivir",
        trial_id="ISRCTN72940450",
        source="non_ctgov_rework_clinic_admin",
        isrctn_id="ISRCTN72940450",
        fallback_cutoff_date="2025-01-01",
        aliases=(
            r"\bremdesivir\b",
            r"\bveklury\b",
        ),
    ),
)


def normalize_text(value: object) -> str:
    return str(value or "").strip()


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


def ctgov_result_date(nct_id: str) -> str:
    response = requests.get(
        f"{CTGOV_API}/{nct_id}",
        headers={"accept": "application/json"},
        timeout=60,
    )
    response.raise_for_status()
    data: dict[str, Any] = response.json()
    status = data.get("protocolSection", {}).get("statusModule", {}) or {}
    return normalize_text(
        (status.get("resultsFirstPostDateStruct") or {}).get("date")
        or status.get("resultsFirstSubmitDate")
    )


def load_isrctn_cutoffs(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {
            row["trial_id"]: normalize_text(row.get("overall_end_date", ""))[:10]
            for row in csv.DictReader(handle)
            if row.get("trial_id")
        }


def cutoff_date_for_spec(spec: CandidateSignalSpec, isrctn_cutoffs: dict[str, str]) -> str:
    if spec.ctgov_ids:
        dates: list[str] = []
        for nct_id in spec.ctgov_ids:
            try:
                date = ctgov_result_date(nct_id)
            except requests.RequestException:
                date = ""
            if date:
                dates.append(date)
        return min(dates) if dates else spec.fallback_cutoff_date
    if spec.isrctn_id and isrctn_cutoffs.get(spec.isrctn_id):
        return isrctn_cutoffs[spec.isrctn_id]
    return spec.fallback_cutoff_date


def compile_pattern(patterns: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{pattern})" for pattern in patterns), re.IGNORECASE)


def corpus_text(kind: str, row: dict[str, Any]) -> str:
    if kind == "post":
        return "\n".join(normalize_text(row.get(field)) for field in ("title", "selftext"))
    return normalize_text(row.get("body"))


def count_candidate_signals(
    data_root: Path,
    non_ct_audit_path: Path,
    output_path: Path,
) -> list[CandidateSignalRow]:
    isrctn_cutoffs = load_isrctn_cutoffs(non_ct_audit_path)
    cutoff_dates = {
        spec.candidate: cutoff_date_for_spec(spec, isrctn_cutoffs)
        for spec in CANDIDATE_SIGNAL_SPECS
    }
    cutoff_timestamps = {
        candidate: parse_date_to_timestamp(cutoff_date)
        for candidate, cutoff_date in cutoff_dates.items()
    }
    patterns = {
        spec.candidate: compile_pattern(spec.aliases)
        for spec in CANDIDATE_SIGNAL_SPECS
    }
    stats = {spec.candidate: CandidateStats() for spec in CANDIDATE_SIGNAL_SPECS}

    for kind, filename in CORPUS_FILES:
        path = data_root / filename
        if not path.exists():
            raise typer.BadParameter(f"Corpus file does not exist: {path}")
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                text = corpus_text(kind, row)
                if not text:
                    continue
                try:
                    timestamp = float(row["created_utc"]) if row.get("created_utc") is not None else None
                except (TypeError, ValueError):
                    timestamp = None
                author = normalize_text(row.get("author"))
                count_author = bool(author and author not in EXCLUDED_AUTHORS)
                for spec in CANDIDATE_SIGNAL_SPECS:
                    hits = list(patterns[spec.candidate].finditer(text))
                    if not hits:
                        continue
                    candidate_stats = stats[spec.candidate]
                    candidate_stats.records += 1
                    candidate_stats.hits += len(hits)
                    if kind == "post":
                        candidate_stats.posts += 1
                    else:
                        candidate_stats.comments += 1
                    if count_author:
                        candidate_stats.authors.add(author)
                    if timestamp is not None:
                        candidate_stats.first_ts = (
                            timestamp
                            if candidate_stats.first_ts is None
                            else min(candidate_stats.first_ts, timestamp)
                        )
                        candidate_stats.last_ts = (
                            timestamp
                            if candidate_stats.last_ts is None
                            else max(candidate_stats.last_ts, timestamp)
                        )
                        cutoff = cutoff_timestamps[spec.candidate]
                        if cutoff is not None and timestamp < cutoff:
                            candidate_stats.pre_records += 1
                            if kind == "post":
                                candidate_stats.pre_posts += 1
                            else:
                                candidate_stats.pre_comments += 1
                            if count_author:
                                candidate_stats.pre_authors.add(author)

    rows: list[CandidateSignalRow] = []
    for spec in CANDIDATE_SIGNAL_SPECS:
        candidate_stats = stats[spec.candidate]
        rows.append(
            CandidateSignalRow(
                candidate=spec.candidate,
                trial_id=spec.trial_id,
                source=spec.source,
                aliases="; ".join(spec.aliases),
                result_or_cutoff_date=cutoff_dates[spec.candidate],
                all_records=candidate_stats.records,
                all_posts=candidate_stats.posts,
                all_comments=candidate_stats.comments,
                all_distinct_authors=len(candidate_stats.authors),
                pre_cutoff_records=candidate_stats.pre_records,
                pre_cutoff_posts=candidate_stats.pre_posts,
                pre_cutoff_comments=candidate_stats.pre_comments,
                pre_cutoff_distinct_authors=len(candidate_stats.pre_authors),
                first_mention_date=format_date(candidate_stats.first_ts),
                last_mention_date=format_date(candidate_stats.last_ts),
            )
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CandidateSignalRow.model_fields))
        writer.writeheader()
        writer.writerows(row.model_dump() for row in rows)
    return rows


def render_summary(rows: list[CandidateSignalRow], output_path: Path) -> None:
    table = Table(title="Additional candidate Reddit signal")
    table.add_column("Candidate")
    table.add_column("Trial")
    table.add_column("Pre-cutoff authors", justify="right")
    table.add_column("Pre-cutoff records", justify="right")
    for row in rows:
        table.add_row(
            row.candidate,
            row.trial_id,
            str(row.pre_cutoff_distinct_authors),
            str(row.pre_cutoff_records),
        )
    console.print(table)
    console.print(f"Wrote {output_path}")


@app.command()
def main(
    data_root: Path = typer.Option(
        DEFAULT_PATIENTPUNK_DATA,
        "--data-root",
        help="Directory containing r_covidlonghaulers_posts_all.jsonl and comments_all.jsonl.",
    ),
    non_ct_audit_path: Path = typer.Option(
        DEFAULT_NON_CT_AUDIT,
        "--non-ct-audit",
        help="Non-CT.gov registry audit CSV used to resolve ISRCTN cutoff dates.",
    ),
    output_path: Path = typer.Option(
        DEFAULT_OUTPUT,
        "--output",
        "-o",
        help="CSV path for additional candidate signal counts.",
    ),
) -> None:
    """Count raw treatment alias mentions for rescue candidates."""

    try:
        rows = count_candidate_signals(data_root, non_ct_audit_path, output_path)
    except typer.BadParameter:
        raise
    except Exception as exc:
        console.print(f"[red]Failed to count additional candidate signals:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    render_summary(rows, output_path)


if __name__ == "__main__":
    sys.exit(app())
