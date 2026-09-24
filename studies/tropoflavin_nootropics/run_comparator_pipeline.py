"""Run the current sentiment, dose, and effect pipeline over every comparator."""

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
from pipeline.doses import run_dose_extraction
from pipeline.effects import run_effects_extraction
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
    run_doses: bool = True
    run_effects: bool = True
    report_batch_size: int = Field(default=8, ge=1, le=64)

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
        if self.run_effects and not self.run_doses:
            raise ValueError("Effect extraction requires dose extraction in the same run")
        return self


class ComparatorRunIdentity(BaseModel):
    """Stable inputs that make a database safe to resume."""

    model_config = ConfigDict(frozen=True)

    schema_id: str = "tropoflavin_comparator_run_identity_v2"
    subreddit: str
    corpus_file: str
    corpus_sha256: str
    cohort_file: str
    cohort_sha256: str
    database_file: str


class ComparatorRunSummary(BaseModel):
    """Aggregate, privacy-safe completion record for one target."""

    model_config = ConfigDict(frozen=True)

    slug: str
    canonical_name: str
    reports: int = Field(ge=0)
    authors: int = Field(ge=0)
    side_effect_reports: int = Field(ge=0)
    side_effect_authors: int = Field(ge=0)
    explicit_severity_authors: int = Field(ge=0)
    dose_or_route_reports: int = Field(ge=0)
    dose_rows: int = Field(ge=0)
    effect_rows: int = Field(ge=0)


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

    schema_id: str = "tropoflavin_comparator_pipeline_manifest_v2"
    subreddit: str
    cohort_schema_id: str
    cohort_sha256: str
    corpus_file: str
    corpus_sha256: str
    database_file: str
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


def _run_identity(config: ComparatorPipelineConfig) -> ComparatorRunIdentity:
    return ComparatorRunIdentity(
        subreddit=config.subreddit,
        corpus_file=config.corpus_path.name,
        corpus_sha256=sha256_file(config.corpus_path),
        cohort_file=config.cohort_path.name,
        cohort_sha256=sha256_file(config.cohort_path),
        database_file=config.database_path.name,
    )


def _database_has_posts(path: Path) -> bool:
    if not path.is_file():
        return False
    with closing(sqlite3.connect(path)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        return "posts" in tables and bool(
            connection.execute("SELECT 1 FROM posts LIMIT 1").fetchone()
        )


def _prepare_run_identity(config: ComparatorPipelineConfig) -> ComparatorRunIdentity:
    """Write or verify the immutable corpus identity before touching the database."""
    identity = _run_identity(config)
    path = config.output_directory / "comparator_run_identity.json"
    if path.is_file():
        existing = ComparatorRunIdentity.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        if existing != identity:
            raise ValueError(
                "Run inputs do not match comparator_run_identity.json. "
                "Use a fresh database and output directory for a different corpus, "
                "cohort, subreddit, or database filename."
            )
        return identity
    if _database_has_posts(config.database_path):
        raise ValueError(
            "The database already contains posts but has no comparator run identity. "
            "Use a fresh database and output directory for this rerun."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(identity.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return identity


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


def _exclusions(
    cohort: tuple[ComparatorSpec, ...],
    compound: ComparatorSpec,
) -> tuple[list[str], list[str]]:
    """Return prompt names and matching aliases, with canonical names first."""
    by_slug = {candidate.slug: candidate for candidate in cohort}
    excluded = [by_slug[slug] for slug in compound.excluded_compounds]
    names = [candidate.canonical_name for candidate in excluded]
    aliases = list(
        dict.fromkeys(
            [
                *names,
                *compound.excluded_aliases,
                *(alias for candidate in excluded for alias in candidate.aliases),
            ]
        )
    )
    return names, aliases


def _run_one(
    config: ComparatorPipelineConfig,
    compound: ComparatorSpec,
    cohort: tuple[ComparatorSpec, ...],
    client: Any,
) -> None:
    output_directory = config.output_directory / compound.slug
    output_directory.mkdir(parents=True, exist_ok=True)
    console.rule(f"{compound.display_name} [{compound.analysis_role}]")
    excluded_names, excluded_aliases = _exclusions(cohort, compound)
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
        drug_excluded_aliases=excluded_aliases,
    )
    run_pipeline(pipeline_config)
    if config.run_doses:
        run_dose_extraction(
            client,
            config.database_path,
            compound.canonical_name,
            aliases=list(compound.aliases),
            excluded_compounds=excluded_names,
            workers=config.workers,
            batch_size=config.report_batch_size,
            parent_chars=config.max_upstream_chars,
            limit=config.limit,
        )
    if config.run_effects:
        run_effects_extraction(
            client,
            config.database_path,
            compound.canonical_name,
            aliases=list(compound.aliases),
            excluded_compounds=excluded_names,
            workers=config.workers,
            batch_size=config.report_batch_size,
            parent_chars=config.max_upstream_chars,
            limit=config.limit,
        )


def combine_usage(left: UsageSummary, right: UsageSummary) -> UsageSummary:
    """Add provider usage from successive resumable process invocations."""
    return UsageSummary(
        requests=left.requests + right.requests,
        prompt_tokens=left.prompt_tokens + right.prompt_tokens,
        completion_tokens=left.completion_tokens + right.completion_tokens,
        total_tokens=left.total_tokens + right.total_tokens,
    )


def _manifest(
    config: ComparatorPipelineConfig,
    *,
    code_commit: str,
    previous_usage: UsageSummary,
) -> ComparatorPipelineManifest:
    cohort = load_comparator_cohort(config.cohort_path)
    with closing(open_db(config.database_path)) as connection:
        summaries: list[ComparatorRunSummary] = []
        for compound in cohort.compounds:
            row = connection.execute(
                """
                WITH latest_reports AS (
                    SELECT tr.*
                    FROM treatment_reports tr
                    WHERE tr.report_id = (
                        SELECT MAX(tr2.report_id)
                        FROM treatment_reports tr2
                        WHERE tr2.post_id = tr.post_id AND tr2.drug_id = tr.drug_id
                    )
                ), adverse_effects AS (
                    SELECT e.*
                    FROM report_effects_latest e
                    WHERE e.attribution = 'target'
                      AND e.direction = 'worsened'
                )
                SELECT COUNT(DISTINCT tr.report_id),
                       COUNT(DISTINCT tr.user_id),
                       COUNT(DISTINCT ae.report_id),
                       COUNT(DISTINCT CASE WHEN ae.report_id IS NOT NULL THEN tr.user_id END),
                       COUNT(DISTINCT CASE WHEN ae.severity IS NOT NULL THEN tr.user_id END),
                       COUNT(DISTINCT d.report_id),
                       COUNT(DISTINCT d.dose_id),
                       COUNT(DISTINCT e.effect_id)
                FROM treatment t
                LEFT JOIN latest_reports tr ON tr.drug_id = t.id
                LEFT JOIN adverse_effects ae ON ae.report_id = tr.report_id
                LEFT JOIN report_doses_latest d ON d.report_id = tr.report_id
                LEFT JOIN report_effects_latest e ON e.report_id = tr.report_id
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
                    side_effect_authors=int(row[3]),
                    explicit_severity_authors=int(row[4]),
                    dose_or_route_reports=int(row[5]),
                    dose_rows=int(row[6]),
                    effect_rows=int(row[7]),
                )
            )
        return ComparatorPipelineManifest(
            subreddit=config.subreddit,
            cohort_schema_id=cohort.schema_id,
            cohort_sha256=sha256_file(config.cohort_path),
            corpus_file=config.corpus_path.name,
            corpus_sha256=sha256_file(config.corpus_path),
            database_file=config.database_path.name,
            posts=connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0],
            extraction_runs=connection.execute(
                "SELECT COUNT(*) FROM extraction_runs"
            ).fetchone()[0],
            provider=LLM_PROVIDER,
            model_fast=MODEL_FAST,
            model_strong=MODEL_STRONG,
            code_commit=code_commit,
            max_upstream_chars=config.max_upstream_chars,
            generated_at=datetime.now(UTC).isoformat(),
            usage=combine_usage(
                previous_usage,
                UsageSummary.model_validate(get_llm_usage_snapshot()),
            ),
            results=tuple(summaries),
        )


def run_comparator_cohort(
    config: ComparatorPipelineConfig,
) -> ComparatorPipelineManifest:
    """Import the shared corpus, run selected targets, and write a manifest."""
    manifest_path = config.output_directory / "comparator_pipeline_manifest.json"
    previous_usage = UsageSummary(
        requests=0,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
    )
    if manifest_path.is_file():
        previous_usage = ComparatorPipelineManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        ).usage
    code_commit = get_git_commit()
    _prepare_run_identity(config)
    _initialize_database(config)
    if LLM_PROVIDER != "openrouter":
        raise ValueError(
            f"This study requires OpenRouter, but the configured provider is {LLM_PROVIDER!r}"
        )
    selected = _selected_compounds(config)
    cohort = load_comparator_cohort(config.cohort_path)
    client = get_client()
    for compound in selected:
        _run_one(config, compound, cohort.compounds, client)

    manifest = _manifest(
        config,
        code_commit=code_commit,
        previous_usage=previous_usage,
    )
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
    skip_doses: bool = typer.Option(False, help="Run sentiment only; skip dose extraction."),
    skip_effects: bool = typer.Option(False, help="Skip normalized effect extraction."),
    report_batch_size: int = typer.Option(8, min=1, max=64),
) -> None:
    """Run resumable sentiment, dose, and effect extraction for the cohort."""
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
                run_doses=not skip_doses,
                run_effects=not skip_effects,
                report_batch_size=report_batch_size,
            )
        )
    except (OSError, ValueError) as exc:
        console.print(f"[red]Comparator pipeline failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
