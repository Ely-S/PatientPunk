"""Run one consistent targeted sentiment pipeline over every comparator."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from rich.console import Console

from studies.tropoflavin_nootropics.comparator_support import (
    DEFAULT_COHORT_CONFIG,
    ComparatorSpec,
    load_comparator_cohort,
    sha256_file,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from import_posts import import_reddit_posts
from run_sentiment_pipeline import run_pipeline
from utilities import (
    LLM_PROVIDER,
    MODEL_FAST,
    MODEL_STRONG,
    PipelineConfig,
    get_client,
    get_git_commit,
    get_llm_usage_snapshot,
)
from utilities.db import open_db

console = Console()
app = typer.Typer(add_completion=False, no_args_is_help=True)


class ComparatorPipelineConfig(BaseModel):
    """Validated inputs for a resumable comparator run."""

    model_config = ConfigDict(frozen=True)

    subreddit: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_]+$")
    corpus_path: Path
    cohort_path: Path = DEFAULT_COHORT_CONFIG
    database_path: Path
    output_directory: Path
    workers: int = Field(default=12, ge=1, le=64)
    max_upstream_chars: int = Field(default=1500, ge=0)
    max_upstream_depth: int | None = Field(default=None, ge=1)
    limit: int | None = Field(default=None, ge=1)
    reclassify: bool = False
    only_slugs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_inputs(self) -> ComparatorPipelineConfig:
        for label, path in (
            ("corpus", self.corpus_path),
            ("cohort", self.cohort_path),
        ):
            if not path.is_file():
                raise ValueError(f"{label} input does not exist: {path}")
        if self.database_path.resolve() == self.corpus_path.resolve():
            raise ValueError("Database must not overwrite the corpus")
        return self


class ComparatorRunSummary(BaseModel):
    """Aggregate, privacy-safe completion record for one target."""

    model_config = ConfigDict(frozen=True)

    slug: str
    canonical_name: str
    reports: int = Field(ge=0)
    authors: int = Field(ge=0)
    side_effect_reports: int = Field(ge=0)


class UsageSummary(BaseModel):
    """Provider-reported aggregate token usage for this process."""

    model_config = ConfigDict(frozen=True)

    requests: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class ComparatorPipelineManifest(BaseModel):
    """Aggregate provenance for a complete or resumed cohort run."""

    model_config = ConfigDict(frozen=True)

    schema_id: str = "tropoflavin_comparator_pipeline_manifest_v1"
    subreddit: str
    cohort_schema_id: str
    cohort_sha256: str
    corpus_path: str
    corpus_sha256: str
    database_path: str
    posts: int = Field(ge=0)
    extraction_runs: int = Field(ge=0)
    provider: str
    model_fast: str
    model_strong: str
    code_commit: str
    max_upstream_chars: int
    generated_at: str
    usage: UsageSummary
    results: tuple[ComparatorRunSummary, ...]


def _initialize_database(config: ComparatorPipelineConfig) -> None:
    config.database_path.parent.mkdir(parents=True, exist_ok=True)
    if not config.database_path.exists():
        schema = (REPO_ROOT / "schema.sql").read_text(encoding="utf-8")
        with sqlite3.connect(config.database_path) as connection:
            connection.executescript(schema)

    with closing(open_db(config.database_path)) as connection:
        required = {"posts", "users", "treatment", "treatment_reports"}
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        missing = required - tables
        if missing:
            raise ValueError(
                f"Comparator database is missing schema tables: {sorted(missing)}"
            )
        post_count = connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        if post_count == 0:
            import_reddit_posts(connection, config.corpus_path, subreddit=config.subreddit)
            post_count = connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
            console.print(f"[green]Imported[/green] {post_count:,} posts/comments")
        else:
            console.print(f"[cyan]Reusing[/cyan] {post_count:,} imported posts/comments")


def _selected_compounds(config: ComparatorPipelineConfig) -> tuple[ComparatorSpec, ...]:
    cohort = load_comparator_cohort(config.cohort_path)
    if not config.only_slugs:
        return cohort.compounds
    requested = set(config.only_slugs)
    unknown = requested - set(cohort.by_slug())
    if unknown:
        raise ValueError(f"Unknown comparator slugs: {sorted(unknown)}")
    return tuple(compound for compound in cohort.compounds if compound.slug in requested)


def _run_one(
    config: ComparatorPipelineConfig,
    compound: ComparatorSpec,
    client: Any,
) -> None:
    output_directory = config.output_directory / compound.slug
    output_directory.mkdir(parents=True, exist_ok=True)
    console.rule(f"{compound.display_name} [{compound.analysis_role}]")
    pipeline_config = PipelineConfig(
        client=client,
        output_dir=output_directory,
        db_path=config.database_path,
        limit=config.limit,
        reclassify=config.reclassify,
        max_upstream_chars=config.max_upstream_chars,
        max_upstream_depth=config.max_upstream_depth,
        workers=config.workers,
        drug=compound.canonical_name,
        drug_aliases=list(compound.aliases),
        drug_excluded_aliases=list(compound.excluded_aliases),
    )
    run_pipeline(pipeline_config)


def _manifest(config: ComparatorPipelineConfig) -> ComparatorPipelineManifest:
    cohort = load_comparator_cohort(config.cohort_path)
    with closing(open_db(config.database_path)) as connection:
        summaries: list[ComparatorRunSummary] = []
        for compound in cohort.compounds:
            row = connection.execute(
                """
                SELECT COUNT(tr.report_id), COUNT(DISTINCT tr.user_id),
                       COUNT(DISTINCT CASE
                           WHEN tr.side_effects IS NOT NULL AND tr.side_effects != '[]'
                           THEN tr.report_id END)
                FROM treatment t
                LEFT JOIN treatment_reports tr ON tr.drug_id = t.id
                WHERE lower(t.canonical_name) = lower(?)
                """,
                (compound.canonical_name,),
            ).fetchone()
            summaries.append(
                ComparatorRunSummary(
                    slug=compound.slug,
                    canonical_name=compound.canonical_name,
                    reports=int(row[0]),
                    authors=int(row[1]),
                    side_effect_reports=int(row[2]),
                )
            )
        return ComparatorPipelineManifest(
            subreddit=config.subreddit,
            cohort_schema_id=cohort.schema_id,
            cohort_sha256=sha256_file(config.cohort_path),
            corpus_path=str(config.corpus_path.resolve()),
            corpus_sha256=sha256_file(config.corpus_path),
            database_path=str(config.database_path.resolve()),
            posts=connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0],
            extraction_runs=connection.execute(
                "SELECT COUNT(*) FROM extraction_runs"
            ).fetchone()[0],
            provider=LLM_PROVIDER,
            model_fast=MODEL_FAST,
            model_strong=MODEL_STRONG,
            code_commit=get_git_commit(),
            max_upstream_chars=config.max_upstream_chars,
            generated_at=datetime.now(UTC).isoformat(),
            usage=UsageSummary.model_validate(get_llm_usage_snapshot()),
            results=tuple(summaries),
        )


def run_comparator_cohort(
    config: ComparatorPipelineConfig,
) -> ComparatorPipelineManifest:
    """Import the shared corpus, run selected targets, and write a manifest."""
    _initialize_database(config)
    if LLM_PROVIDER != "openrouter":
        raise ValueError(
            f"This study requires OpenRouter, but the configured provider is {LLM_PROVIDER!r}"
        )
    selected = _selected_compounds(config)
    client = get_client()
    for compound in selected:
        _run_one(config, compound, client)

    manifest = _manifest(config)
    manifest_path = config.output_directory / "comparator_pipeline_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    console.print(f"[green]Manifest[/green] {manifest_path}")
    return manifest


@app.command()
def main(
    subreddit: str = typer.Option(..., help="Subreddit name without the r/ prefix."),
    corpus: Path = typer.Option(..., exists=True, dir_okay=False),
    database: Path = typer.Option(..., dir_okay=False),
    output_dir: Path = typer.Option(..., file_okay=False),
    cohort: Path = typer.Option(DEFAULT_COHORT_CONFIG, exists=True, dir_okay=False),
    workers: int = typer.Option(12, min=1, max=64),
    max_upstream_chars: int = typer.Option(1500, min=0),
    max_upstream_depth: int | None = typer.Option(None, min=1),
    limit: int | None = typer.Option(None, min=1),
    reclassify: bool = typer.Option(False),
    only: list[str] | None = typer.Option(None, help="Repeat to run selected slugs only."),
) -> None:
    """Run resumable, identically configured sentiment analyses for the cohort."""
    try:
        run_comparator_cohort(
            ComparatorPipelineConfig(
                subreddit=subreddit,
                corpus_path=corpus,
                cohort_path=cohort,
                database_path=database,
                output_directory=output_dir,
                workers=workers,
                max_upstream_chars=max_upstream_chars,
                max_upstream_depth=max_upstream_depth,
                limit=limit,
                reclassify=reclassify,
                only_slugs=tuple(only or ()),
            )
        )
    except (OSError, ValueError) as exc:
        console.print(f"[red]Comparator pipeline failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
