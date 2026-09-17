"""Publish an aggregate dose-audit correction without inventing episode exclusions."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from string import Template
from time import perf_counter
from typing import Annotated, Literal

import typer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from rich.console import Console
from statsmodels.stats.proportion import proportion_confint

from studies.tropoflavin_nootropics.study_support import STUDY_ROOT

DEFAULT_AUDIT = STUDY_ROOT / "audits" / "78dhf_high_dose_audit.json"
AUDIT_NOTE = STUDY_ROOT / "templates" / "78dhf_high_dose_audit_note.md"
app = typer.Typer(add_completion=False)
console = Console()


class HighDoseAudit(BaseModel):
    """Reviewed counts only; no source text or participant identifiers are stored."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_id: Literal["78dhf_high_dose_aggregate_audit_v1"]
    source_run: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9-]+$")
    source_aggregate: Literal["78dhf_high_dose_audit.csv"]
    source_aggregate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    episode_records_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    database_sha256: dict[
        Annotated[str, Field(pattern=r"^[A-Za-z]+$")],
        Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")],
    ] = Field(min_length=1)
    cohort_episodes: int = Field(gt=0)
    cohort_authors: int = Field(gt=0)
    candidate_episodes: int = Field(gt=0)
    candidate_authors: int = Field(gt=0)
    candidate_positive_reports: int = Field(ge=0)
    candidate_side_effect_reports: int = Field(ge=0)
    excluded_other_compound: int = Field(ge=0)
    excluded_boundary_range: int = Field(ge=0)
    retained_episodes: int = Field(gt=0)
    retained_authors: int = Field(gt=0)
    retained_positive_reports: int = Field(ge=0)
    retained_side_effect_reports: int = Field(ge=0)
    retained_explicit_severity_reports: int = Field(ge=0)

    @model_validator(mode="after")
    def check_counts(self) -> HighDoseAudit:
        excluded = self.excluded_other_compound + self.excluded_boundary_range
        if self.candidate_episodes != excluded + self.retained_episodes:
            raise ValueError("Candidate episodes must equal excluded plus retained episodes")
        if not (
            self.retained_authors <= self.retained_episodes <= self.candidate_episodes
            <= self.cohort_episodes
            and self.retained_authors <= self.candidate_authors <= self.cohort_authors
            <= self.cohort_episodes
            and self.candidate_authors <= self.candidate_episodes
            and self.candidate_authors - self.retained_authors <= excluded
        ):
            raise ValueError("Author and episode counts are inconsistent")
        for retained, candidate in (
            (self.retained_positive_reports, self.candidate_positive_reports),
            (self.retained_side_effect_reports, self.candidate_side_effect_reports),
        ):
            if not (
                retained <= self.retained_episodes
                and retained <= candidate <= self.candidate_episodes
                and candidate - retained <= excluded
            ):
                raise ValueError("Outcome counts exceed their eligible episodes")
        if self.retained_explicit_severity_reports > self.retained_side_effect_reports:
            raise ValueError("Explicit severity exceeds side-effect reports")
        return self


def load_audit(path: Path = DEFAULT_AUDIT) -> HighDoseAudit:
    return HighDoseAudit.model_validate_json(path.read_text(encoding="utf-8"))


def count_rate(successes: int, total: int) -> str:
    """Report episode proportions with 95% Wilson intervals."""
    if not 0 <= successes <= total or total <= 0:
        raise ValueError("A proportion requires 0 <= successes <= total and total > 0")
    low, high = proportion_confint(successes, total, alpha=0.05, method="wilson")
    return (
        f"{successes}/{total} ({100 * successes / total:.1f}%; "
        f"{100 * low:.1f}% to {100 * high:.1f}%)"
    )


def audited_dose_row(audit: HighDoseAudit) -> str:
    return (
        f"| >=100 mg (audited) | {audit.retained_episodes} | "
        f"{audit.retained_authors} | unavailable | "
        f"{count_rate(audit.retained_positive_reports, audit.retained_episodes)} | "
        f"{count_rate(audit.retained_side_effect_reports, audit.retained_episodes)} |"
    )


def audit_note(audit: HighDoseAudit) -> str:
    template = Template(AUDIT_NOTE.read_text(encoding="utf-8"))
    return template.substitute(
        candidate_episodes=audit.candidate_episodes,
        excluded_other_compound=audit.excluded_other_compound,
        excluded_boundary_range=audit.excluded_boundary_range,
        retained_episodes=audit.retained_episodes,
        retained_authors=audit.retained_authors,
        severity_rate=count_rate(
            audit.retained_explicit_severity_reports, audit.retained_episodes
        ),
    ).strip()


def apply_high_dose_audit(report: str, audit: HighDoseAudit) -> str:
    """Correct only a matching historical report; retain and label its old models."""
    provenance = (
        f"| episode_records.jsonl | {audit.episode_records_sha256} |"
    )
    cohort = f"| Combined | {audit.cohort_episodes} | {audit.cohort_authors} |"
    if provenance not in report or cohort not in report:
        raise ValueError("Frozen high-dose audit does not match cohort provenance; re-audit inputs")
    expected_databases = {
        f"| {subreddit} | combined.db | {digest} |"
        for subreddit, digest in audit.database_sha256.items()
    }
    actual_databases = {
        line for line in report.splitlines() if " | combined.db | " in line
    }
    if actual_databases != expected_databases:
        raise ValueError("Frozen high-dose audit does not match source databases; re-audit inputs")
    rows = [line for line in report.splitlines() if line.startswith("| >=100 mg")]
    if len(rows) != 1:
        raise ValueError("Expected exactly one high-dose row for the aggregate correction")
    old_row = rows[0]
    new_row = audited_dose_row(audit)
    note = audit_note(audit)
    if "## High-dose audit correction" in report:
        if old_row != new_row or note not in report:
            raise ValueError("Existing high-dose correction differs from the reviewed audit")
        return report
    cells = [cell.strip() for cell in old_row.strip("|").split("|")]
    if not (
        len(cells) == 6
        and cells[0] == ">=100 mg"
        and cells[1] == str(audit.candidate_episodes)
        and cells[2] == str(audit.candidate_authors)
        and cells[4].startswith(
            f"{audit.candidate_positive_reports}/{audit.candidate_episodes} ("
        )
        and cells[5].startswith(
            f"{audit.candidate_side_effect_reports}/{audit.candidate_episodes} ("
        )
    ):
        raise ValueError("Frozen high-dose audit does not match candidate counts; re-audit inputs")
    title = "# Same-post 7,8-DHF episode analysis\n\n"
    if not report.startswith(title):
        raise ValueError("Unexpected episode report title")
    report = report.replace(old_row, new_row, 1)
    for heading in (
        "Primary design", "Coverage", "Main finding", "Combined primary models",
        "Binary sentiment sensitivity", "Combined route descriptives",
        "Combined explicit-reason descriptives", "Separate subreddit trend estimates",
    ):
        report = report.replace(f"## {heading}\n", f"## {heading} (pre-audit)\n")
    report = report.replace(
        "## Combined dose descriptives\n",
        "## Combined dose descriptives (audited high-dose row only)\n",
    )
    return report.replace(title, title + note + "\n\n", 1)


@app.command()
def main(
    report: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option(dir_okay=False)],
    audit: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = DEFAULT_AUDIT,
) -> None:
    """Apply the reviewed aggregate correction without access to private data."""
    started = perf_counter()
    try:
        reviewed = load_audit(audit)
        corrected = apply_high_dose_audit(report.read_text(encoding="utf-8"), reviewed)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(corrected, encoding="utf-8")
    except (OSError, ValueError) as exc:
        console.print(f"[red]Cannot publish episode audit:[/red] {exc}")
        raise typer.Exit(1) from exc
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info(json.dumps({
        "run_id": reviewed.source_run, "phase": "episode_dose_audit",
        "schema_id": reviewed.schema_id, "duration": perf_counter() - started,
        "status": "complete",
    }))
    console.print(f"[green]Wrote audited report[/green] {output}")


if __name__ == "__main__":
    app()
