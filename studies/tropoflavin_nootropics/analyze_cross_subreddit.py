"""Create an unpooled summary of independent subreddit analyses."""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

import typer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from rich.console import Console

from studies.tropoflavin_nootropics.analyze_comparator_cohort import (
    _connect_readonly,
    _load_votes,
    _percent,
    _sentiment_summaries,
    _table,
)
from studies.tropoflavin_nootropics.comparator_support import (
    DEFAULT_COHORT_CONFIG,
    load_comparator_cohort,
    sha256_file,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


class SubredditAnalysisArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    subreddit: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_]+$")
    sentiment_database: Path
    report_path: Path

    @model_validator(mode="after")
    def validate_paths(self) -> SubredditAnalysisArtifact:
        for label, path in (
            ("sentiment database", self.sentiment_database),
            ("report", self.report_path),
        ):
            if not path.is_file():
                raise ValueError(f"{label} not found: {path}")
        return self


class CrossSubredditConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    cohorts: tuple[SubredditAnalysisArtifact, ...] = Field(min_length=2)
    cohort_path: Path = DEFAULT_COHORT_CONFIG
    output_path: Path

    @model_validator(mode="after")
    def validate_cohorts(self) -> CrossSubredditConfig:
        names = [cohort.subreddit.casefold() for cohort in self.cohorts]
        if len(names) != len(set(names)):
            raise ValueError("Subreddit cohorts must be unique")
        databases = [cohort.sentiment_database.resolve() for cohort in self.cohorts]
        if len(databases) != len(set(databases)):
            raise ValueError("Each subreddit must retain a separate database")
        if not self.cohort_path.is_file():
            raise ValueError(f"Comparator cohort not found: {self.cohort_path}")
        return self


def render_cross_subreddit_summary(config: CrossSubredditConfig) -> str:
    """Render independent cohort rows without calculating pooled statistics."""
    cohort = load_comparator_cohort(config.cohort_path)
    rows: list[list[object]] = []
    sources: list[list[object]] = []
    for artifact in config.cohorts:
        with closing(_connect_readonly(artifact.sentiment_database)) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise ValueError(
                    f"Database integrity failed for r/{artifact.subreddit}: {integrity}"
                )
            summaries = _sentiment_summaries(
                cohort,
                _load_votes(connection, cohort),
            )
        for compound in cohort.compounds:
            summary = summaries[compound.slug]
            rows.append(
                [
                    f"r/{artifact.subreddit}",
                    compound.display_name,
                    summary.users,
                    summary.positive,
                    _percent(summary.positive_rate),
                    "too sparse for inference"
                    if summary.users < 10
                    else "see cohort report",
                ]
            )
        sources.append(
            [
                f"r/{artifact.subreddit}",
                artifact.report_path.name,
                sha256_file(artifact.report_path),
                artifact.sentiment_database.name,
                sha256_file(artifact.sentiment_database),
            ]
        )
    return (
        "# Unpooled cross-subreddit 7,8-DHF summary\n\n"
        "Each row is an independent subreddit cohort. Counts and denominators are "
        "never added across communities because the same person may post in more than "
        "one subreddit and the communities have different selection mechanisms. Use "
        "the separate overlap matrix to assess possible double counting.\n\n"
        "## Independent author-level sentiment\n\n"
        + _table(
            [
                "Subreddit",
                "Compound",
                "Authors",
                "Positive",
                "Positive share",
                "Inference status",
            ],
            rows,
        )
        + "\n\n## Reproducibility\n\n"
        + _table(
            ["Subreddit", "Report", "Report SHA-256", "Database", "Database SHA-256"],
            sources,
        )
        + "\n"
    )


def analyze_cross_subreddit(config: CrossSubredditConfig) -> str:
    """Write the aggregate unpooled summary."""
    report = render_cross_subreddit_summary(config)
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(report, encoding="utf-8")
    return report


@app.command()
def main(
    config_path: Path = typer.Option(..., exists=True, dir_okay=False),
    output: Path = typer.Option(..., dir_okay=False),
) -> None:
    """Read an external artifact config and write the unpooled summary."""
    payload = CrossSubredditConfig.model_validate_json(
        config_path.read_text(encoding="utf-8")
    )
    analyze_cross_subreddit(payload.model_copy(update={"output_path": output}))
    console.print(f"[green]Wrote[/green] {output}")


if __name__ == "__main__":
    app()
