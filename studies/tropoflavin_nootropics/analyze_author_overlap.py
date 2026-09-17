"""Create a privacy-safe cross-subreddit author-overlap matrix."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path

import typer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from rich.console import Console

from studies.tropoflavin_nootropics.comparator_support import markdown_escape, sha256_file

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()
_AUTHOR_HASH = re.compile(r"^[0-9a-f]{32}$")


class CohortArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    subreddit: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_]+$")
    sentiment_database: Path
    author_hash_algorithm: str = "sha256-128-raw-reddit-username-v1"

    @model_validator(mode="after")
    def validate_database(self) -> CohortArtifact:
        if not self.sentiment_database.is_file():
            raise ValueError(f"Sentiment database not found: {self.sentiment_database}")
        return self


class AuthorOverlapConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    cohorts: tuple[CohortArtifact, ...] = Field(min_length=2)
    output_path: Path

    @model_validator(mode="after")
    def validate_cohorts(self) -> AuthorOverlapConfig:
        names = [cohort.subreddit.casefold() for cohort in self.cohorts]
        if len(names) != len(set(names)):
            raise ValueError("Subreddit cohorts must be unique")
        paths = [cohort.sentiment_database.resolve() for cohort in self.cohorts]
        if len(paths) != len(set(paths)):
            raise ValueError("Each cohort must use a separate sentiment database")
        algorithms = {cohort.author_hash_algorithm for cohort in self.cohorts}
        if len(algorithms) != 1:
            raise ValueError("All cohorts must use the same author-hash algorithm")
        return self


def _author_set(path: Path) -> set[str]:
    with closing(
        sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    ) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"Database integrity check failed for {path.name}: {integrity}")
        authors = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT DISTINCT user_id
                FROM treatment_reports
                WHERE user_id IS NOT NULL AND user_id != 'deleted'
                """
            )
        }
    invalid = sorted(author for author in authors if not _AUTHOR_HASH.fullmatch(author))
    if invalid:
        raise ValueError(
            f"Database {path.name} contains non-global author identifiers"
        )
    return authors


def _table(headers: list[str], rows: list[list[object]]) -> str:
    rendered = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    rendered.extend(
        "| " + " | ".join(markdown_escape(str(value)) for value in row) + " |"
        for row in rows
    )
    return "\n".join(rendered)


def render_author_overlap(config: AuthorOverlapConfig) -> str:
    """Render counts only, without exposing any author hashes."""
    author_sets = {
        cohort.subreddit: _author_set(cohort.sentiment_database)
        for cohort in config.cohorts
    }
    names = [cohort.subreddit for cohort in config.cohorts]
    matrix = [
        [left, *[len(author_sets[left] & author_sets[right]) for right in names]]
        for left in names
    ]
    sources = [
        [
            cohort.subreddit,
            len(author_sets[cohort.subreddit]),
            cohort.sentiment_database.name,
            sha256_file(cohort.sentiment_database),
        ]
        for cohort in config.cohorts
    ]
    algorithm = config.cohorts[0].author_hash_algorithm
    return (
        "# Cross-subreddit author overlap\n\n"
        "This is a diagnostic for possible double counting. The cohorts remain "
        "separate and no denominators are pooled. Deleted or unidentifiable authors "
        "are excluded. An overlap count means the same deterministic author hash had "
        "at least one retained comparator report in both subreddits. Multiple accounts "
        "owned by one person cannot be detected, so measured overlap is a lower bound "
        "on possible double counting.\n\n"
        f"Hash algorithm verified across cohorts: `{algorithm}`.\n\n"
        "## Overlap counts\n\n"
        + _table(["Subreddit", *names], matrix)
        + "\n\n## Source verification\n\n"
        + _table(["Subreddit", "Authors", "Database", "SHA-256"], sources)
        + "\n"
    )


def analyze_author_overlap(config: AuthorOverlapConfig) -> str:
    """Write the aggregate overlap report."""
    report = render_author_overlap(config)
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(report, encoding="utf-8")
    return report


@app.command()
def main(
    config_path: Path = typer.Option(..., exists=True, dir_okay=False),
    output: Path = typer.Option(..., dir_okay=False),
) -> None:
    """Read an external cohort-artifact config and write the overlap matrix."""
    payload = AuthorOverlapConfig.model_validate_json(
        config_path.read_text(encoding="utf-8")
    )
    analyze_author_overlap(payload.model_copy(update={"output_path": output}))
    console.print(f"[green]Wrote[/green] {output}")


if __name__ == "__main__":
    app()
