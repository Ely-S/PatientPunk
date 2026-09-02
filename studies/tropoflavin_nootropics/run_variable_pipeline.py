"""Run Pipeline B for one private subreddit comparator corpus."""

from __future__ import annotations

import csv
import sys
from datetime import UTC, datetime
from pathlib import Path

import typer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from rich.console import Console

from studies.tropoflavin_nootropics.comparator_support import safe_json_dump, sha256_file

REPO_ROOT = Path(__file__).resolve().parents[2]
VARIABLE_ROOT = REPO_ROOT / "variable_extraction"
if str(VARIABLE_ROOT) not in sys.path:
    sys.path.insert(0, str(VARIABLE_ROOT))

from patientpunk import Pipeline, PipelineConfig
from patientpunk._utils import (
    MODEL_FAST,
    get_llm_usage_snapshot,
    llm_config,
)
from patientpunk.llm_extract import MAX_TEXT_CHARS, MAX_TOKENS
from patientpunk.normalize import (
    ADMINISTRATION_ROUTE_DERIVED,
    DOSAGE_DERIVED,
    TREATMENT_OUTCOME_DERIVED,
    normalize_records,
)
from patientpunk.pipeline import _git_commit

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()
DEFAULT_SCHEMA = VARIABLE_ROOT / "schemas" / "nootropics_schema.json"


class VariablePipelineConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    subreddit: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_]+$")
    input_directory: Path
    schema_path: Path = DEFAULT_SCHEMA
    workers: int = Field(default=12, ge=1, le=64)
    resume: bool = False

    @model_validator(mode="after")
    def validate_inputs(self) -> VariablePipelineConfig:
        if not (self.input_directory / "users").is_dir():
            raise ValueError(f"Author corpus not found: {self.input_directory / 'users'}")
        if not self.schema_path.is_file():
            raise ValueError(f"Schema not found: {self.schema_path}")
        return self


class UsageSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    requests: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class VariablePipelineManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_id: str = "tropoflavin_variable_pipeline_manifest_v1"
    subreddit: str
    provider: str
    model: str
    code_commit: str | None
    extraction_schema_sha256: str
    prompt_implementation_sha256: str
    source_corpus_manifest_sha256: str
    max_text_chars: int = Field(ge=1)
    max_output_tokens: int = Field(default=8192, ge=1)
    record_count: int = Field(ge=0)
    records_sha256: str
    usage: UsageSummary
    completed_at: str


def write_linked_records(source: Path, output: Path) -> int:
    """Normalize records and emit aligned treatment, dose, and route columns."""
    with source.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        source_fields = list(reader.fieldnames or ())
        rows = list(reader)
    normalized = normalize_records(rows)
    present = set().union(*(row.keys() for row in normalized)) if normalized else set()
    derived = TREATMENT_OUTCOME_DERIVED + DOSAGE_DERIVED + ADMINISTRATION_ROUTE_DERIVED
    fields = source_fields + [
        field for field in derived if field not in source_fields and field in present
    ]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(normalized)
    return len(normalized)


def run_variable_pipeline(config: VariablePipelineConfig) -> VariablePipelineManifest:
    """Run the importable variable-extraction service and record provenance."""
    provider = str(llm_config()["provider"])
    if provider != "openrouter":
        raise ValueError(
            f"This study requires OpenRouter, but the configured provider is {provider!r}"
        )
    source_manifest = config.input_directory / "variable_corpus.manifest.json"
    if not source_manifest.is_file():
        raise ValueError(f"Variable corpus manifest not found: {source_manifest}")
    manifest_path = config.input_directory / "variable_pipeline_manifest.json"
    previous_usage = UsageSummary(
        requests=0,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
    )
    if config.resume and manifest_path.is_file():
        previous_usage = VariablePipelineManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        ).usage

    result = Pipeline(
        PipelineConfig(
            schema_path=config.schema_path,
            input_dir=config.input_directory,
            temp_dir=config.input_directory / "temp",
            workers=config.workers,
            run_llm=True,
            discovery_mode=None,
            clean=not config.resume,
            resume=config.resume,
        )
    ).run()
    if not result.ok:
        raise RuntimeError("Variable extraction pipeline did not complete successfully")

    base_records_path = config.input_directory / "records.csv"
    if not base_records_path.is_file():
        raise RuntimeError(
            f"Variable extraction did not create {base_records_path.name}"
        )
    records_path = config.input_directory / "records_linked.csv"
    record_count = write_linked_records(base_records_path, records_path)
    current_usage = UsageSummary.model_validate(get_llm_usage_snapshot())
    usage = UsageSummary(
        requests=previous_usage.requests + current_usage.requests,
        prompt_tokens=previous_usage.prompt_tokens + current_usage.prompt_tokens,
        completion_tokens=(
            previous_usage.completion_tokens + current_usage.completion_tokens
        ),
        total_tokens=previous_usage.total_tokens + current_usage.total_tokens,
    )
    manifest = VariablePipelineManifest(
        subreddit=config.subreddit,
        provider=provider,
        model=MODEL_FAST,
        code_commit=_git_commit(),
        extraction_schema_sha256=sha256_file(config.schema_path),
        prompt_implementation_sha256=sha256_file(
            VARIABLE_ROOT / "patientpunk" / "llm_extract.py"
        ),
        source_corpus_manifest_sha256=sha256_file(source_manifest),
        max_text_chars=MAX_TEXT_CHARS,
        max_output_tokens=MAX_TOKENS,
        record_count=record_count,
        records_sha256=sha256_file(records_path),
        usage=usage,
        completed_at=datetime.now(UTC).isoformat(),
    )
    safe_json_dump(manifest, manifest_path)
    console.print(
        f"[green]Completed[/green] Pipeline B for r/{config.subreddit}: "
        f"{manifest.record_count:,} author records, {usage.total_tokens:,} tokens"
    )
    return manifest


@app.command()
def main(
    subreddit: str = typer.Option(..., help="Subreddit name without the r/ prefix."),
    input_directory: Path = typer.Option(..., exists=True, file_okay=False),
    schema: Path = typer.Option(DEFAULT_SCHEMA, exists=True, dir_okay=False),
    workers: int = typer.Option(12, min=1, max=64),
    resume: bool = typer.Option(False),
) -> None:
    """Run Pipeline B for one subreddit."""
    run_variable_pipeline(
        VariablePipelineConfig(
            subreddit=subreddit,
            input_directory=input_directory,
            schema_path=schema,
            workers=workers,
            resume=resume,
        )
    )


if __name__ == "__main__":
    app()
