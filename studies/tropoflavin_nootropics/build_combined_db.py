"""Build one queryable SQLite artifact from completed Pipelines A and B."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from rich.console import Console

from patientpunk.normalize import normalize_value
from studies.tropoflavin_nootropics.attribution import (
    corroborates_dose,
    corroborates_route,
    load_author_segments,
)
from studies.tropoflavin_nootropics.comparator_support import (
    DEFAULT_COHORT_CONFIG,
    ComparatorCohort,
    analysis_compound_name,
    compound_for_treatment as comparator_for_treatment,
    load_comparator_cohort,
    sha256_file,
)
from studies.tropoflavin_nootropics.study_support import (
    PipelineBRecord,
    canonical_side_effect,
    desired_result_bucket,
    dose_band,
    linked_values,
    load_pipeline_b_records,
    parse_mass_dosage,
    route_bucket,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()
_SAFE_COLUMN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_OUTCOME_LABELS = {"helped", "no_effect", "worsened", "mixed", "unknown"}


class CombinedDatabaseConfig(BaseModel):
    """Validated inputs for one atomic combined-database build."""

    model_config = ConfigDict(frozen=True)

    source_database: Path
    pipeline_b_records: Path
    output_database: Path
    cohort_path: Path = DEFAULT_COHORT_CONFIG
    pipeline_b_corpus_directory: Path | None = None
    expected_pipeline_b_records: int = Field(default=752, ge=1)
    pipeline_b_run_name: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_paths(self) -> CombinedDatabaseConfig:
        if not self.source_database.is_file():
            raise ValueError(f"Pipeline A database not found: {self.source_database}")
        if not self.pipeline_b_records.is_file():
            raise ValueError(f"Pipeline B records not found: {self.pipeline_b_records}")
        if not self.cohort_path.is_file():
            raise ValueError(f"Comparator cohort not found: {self.cohort_path}")
        if self.pipeline_b_corpus_directory is not None and not (
            self.pipeline_b_corpus_directory / "users"
        ).is_dir():
            raise ValueError(
                "Pipeline B source corpus is missing its users directory: "
                f"{self.pipeline_b_corpus_directory}"
            )
        if self.source_database.resolve() == self.output_database.resolve():
            raise ValueError(
                "Output database must differ from the Pipeline A source database"
            )
        return self


class PipelineBDosageRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    author_hash: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    treatment: str = Field(min_length=1)
    value: str = Field(min_length=1)
    target_compound: str | None
    attribution_status: str
    mass_low_mg: float | None
    mass_high_mg: float | None
    mass_midpoint_mg: float | None
    quantitative_mass: bool
    dose_band: str
    dose_band_order: int | None


class PipelineBRouteRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    author_hash: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    treatment: str = Field(min_length=1)
    route: str = Field(min_length=1)
    route_bucket: str = Field(min_length=1)
    target_compound: str | None
    attribution_status: str


class PipelineBOutcomeRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    author_hash: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    treatment: str
    outcome: str
    symptom: str
    desired_result_bucket: str = Field(min_length=1)
    target_compound: str | None
    raw_value: str = Field(min_length=1)


class PipelineASideEffectRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_id: int = Field(ge=1)
    user_id: str = Field(min_length=1)
    drug_id: int = Field(ge=1)
    treatment: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    raw_value: str = Field(min_length=1)
    canonical_side_effect: str = Field(min_length=1)
    side_effect_bucket: str = Field(min_length=1)


class PipelineBCompoundExposureRow(BaseModel):
    """One author-compound row without inventing dose-to-route pairings."""

    model_config = ConfigDict(frozen=True)

    author_hash: str = Field(min_length=1)
    target_compound: str = Field(min_length=1)
    dose_values_json: str
    quantitative_dose_midpoints_mg_json: str
    dose_band: str = Field(min_length=1)
    dose_band_order: int | None
    route_values_json: str
    route_buckets_json: str
    route_bucket: str = Field(min_length=1)
    outcome_values_json: str
    conservative_outcome: str = Field(min_length=1)
    desired_result_buckets_json: str
    dose_observation_count: int = Field(ge=0)
    route_observation_count: int = Field(ge=0)
    outcome_observation_count: int = Field(ge=0)
    dose_route_status: str = Field(min_length=1)


class CombinedDatabaseReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    output_database: Path
    pipeline_a_reports: int
    pipeline_a_users: int
    pipeline_b_records: int
    pipeline_b_dosages: int
    pipeline_b_routes: int
    pipeline_b_outcomes: int
    pipeline_b_compound_exposures: int
    pipeline_a_side_effects: int


def _quote_identifier(value: str) -> str:
    if not _SAFE_COLUMN.fullmatch(value):
        raise ValueError(f"Unsafe CSV column name: {value!r}")
    return f'"{value}"'


def _csv_columns(path: Path) -> list[str]:
    with path.open(encoding="utf-8", newline="") as handle:
        columns = list(csv.DictReader(handle).fieldnames or ())
    if not columns:
        raise ValueError(f"Pipeline B CSV has no header: {path}")
    if len(columns) != len(set(columns)):
        raise ValueError(f"Pipeline B CSV has duplicate columns: {path}")
    for column in columns:
        _quote_identifier(column)
    return columns


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _outcome_rows(
    record: PipelineBRecord,
    cohort: ComparatorCohort,
) -> list[PipelineBOutcomeRow]:
    rows: list[PipelineBOutcomeRow] = []
    for ordinal, raw_entry in enumerate(record.treatment_outcome.split(" | ")):
        raw_entry = raw_entry.strip()
        if not raw_entry:
            continue
        parts = [part.strip() for part in raw_entry.split(":")]
        if len(parts) >= 2:
            treatment, raw_outcome = parts[0], parts[1]
            symptom = ":".join(parts[2:]).strip()
        else:
            treatment, raw_outcome, symptom = "", parts[0], ""
        outcome = normalize_value("treatment_outcome", raw_outcome)
        if outcome not in _OUTCOME_LABELS:
            outcome = "unknown"
        rows.append(
            PipelineBOutcomeRow(
                author_hash=record.author_hash,
                ordinal=ordinal,
                treatment=treatment,
                outcome=outcome,
                symptom=symptom,
                desired_result_bucket=desired_result_bucket(symptom),
                target_compound=comparator_for_treatment(treatment, cohort),
                raw_value=raw_entry,
            )
        )
    return rows


def _dosage_rows(
    record: PipelineBRecord,
    cohort: ComparatorCohort,
    author_segments: dict[str, tuple[str, ...]] | None = None,
) -> list[PipelineBDosageRow]:
    rows: list[PipelineBDosageRow] = []
    compounds_by_name = {
        analysis_compound_name(compound): compound for compound in cohort.compounds
    }
    for ordinal, pair in enumerate(linked_values(record, "dosage")):
        mass = parse_mass_dosage(pair.value)
        band = dose_band(mass.midpoint_mg) if mass else None
        target = comparator_for_treatment(pair.treatment, cohort)
        if target is None:
            attribution_status = "unmapped treatment"
        elif author_segments is None:
            attribution_status = "not checked"
        else:
            corroborated = corroborates_dose(
                compounds_by_name[target],
                pair.value,
                author_segments.get(record.author_hash, ()),
            )
            attribution_status = "corroborated" if corroborated else "unsupported"
        rows.append(
            PipelineBDosageRow(
                author_hash=record.author_hash,
                ordinal=ordinal,
                treatment=pair.treatment,
                value=pair.value,
                target_compound=target,
                attribution_status=attribution_status,
                mass_low_mg=mass.low_mg if mass else None,
                mass_high_mg=mass.high_mg if mass else None,
                mass_midpoint_mg=mass.midpoint_mg if mass else None,
                quantitative_mass=mass is not None,
                dose_band=band.label if band else "non-quantitative",
                dose_band_order=band.order if band else None,
            )
        )
    return rows


def _route_rows(
    record: PipelineBRecord,
    cohort: ComparatorCohort,
    author_segments: dict[str, tuple[str, ...]] | None = None,
) -> list[PipelineBRouteRow]:
    compounds_by_name = {
        analysis_compound_name(compound): compound for compound in cohort.compounds
    }
    rows: list[PipelineBRouteRow] = []
    for ordinal, pair in enumerate(linked_values(record, "administration_route")):
        target = comparator_for_treatment(pair.treatment, cohort)
        if target is None:
            attribution_status = "unmapped treatment"
        elif author_segments is None:
            attribution_status = "not checked"
        else:
            corroborated = corroborates_route(
                compounds_by_name[target],
                pair.value,
                author_segments.get(record.author_hash, ()),
            )
            attribution_status = "corroborated" if corroborated else "unsupported"
        rows.append(
            PipelineBRouteRow(
                author_hash=record.author_hash,
                ordinal=ordinal,
                treatment=pair.treatment,
                route=pair.value,
                route_bucket=route_bucket(pair.value),
                target_compound=target,
                attribution_status=attribution_status,
            )
        )
    return rows


def _side_effect_rows(connection: sqlite3.Connection) -> list[PipelineASideEffectRow]:
    rows: list[PipelineASideEffectRow] = []
    reports = connection.execute(
        """
        SELECT reports.report_id,
               reports.user_id,
               reports.drug_id,
               treatment.canonical_name,
               reports.side_effects
        FROM treatment_reports AS reports
        JOIN treatment ON treatment.id = reports.drug_id
        """
    ).fetchall()
    for report_id, user_id, drug_id, treatment, raw_side_effects in reports:
        if not raw_side_effects:
            continue
        try:
            values = json.loads(raw_side_effects)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid side_effects JSON in report {report_id}"
            ) from exc
        if not isinstance(values, list):
            raise ValueError(f"side_effects must be a list in report {report_id}")
        for ordinal, value in enumerate(values):
            raw_value = str(value).strip()
            if not raw_value:
                continue
            canonical, bucket = canonical_side_effect(raw_value)
            rows.append(
                PipelineASideEffectRow(
                    report_id=report_id,
                    user_id=user_id,
                    drug_id=drug_id,
                    treatment=treatment,
                    ordinal=ordinal,
                    raw_value=raw_value,
                    canonical_side_effect=canonical,
                    side_effect_bucket=bucket,
                )
            )
    return rows


_OUTCOME_RANK = {
    "worsened": 4,
    "no_effect": 3,
    "mixed": 2,
    "helped": 1,
    "unknown": 0,
}


def _compound_exposure_rows(
    dosages: list[PipelineBDosageRow],
    routes: list[PipelineBRouteRow],
    outcomes: list[PipelineBOutcomeRow],
) -> list[PipelineBCompoundExposureRow]:
    dosage_groups: dict[tuple[str, str], list[PipelineBDosageRow]] = defaultdict(list)
    route_groups: dict[tuple[str, str], list[PipelineBRouteRow]] = defaultdict(list)
    outcome_groups: dict[tuple[str, str], list[PipelineBOutcomeRow]] = defaultdict(list)
    for row in dosages:
        if row.target_compound and row.attribution_status in {"corroborated", "not checked"}:
            dosage_groups[(row.author_hash, row.target_compound)].append(row)
    for row in routes:
        if row.target_compound and row.attribution_status in {"corroborated", "not checked"}:
            route_groups[(row.author_hash, row.target_compound)].append(row)
    for row in outcomes:
        if row.target_compound:
            outcome_groups[(row.author_hash, row.target_compound)].append(row)

    keys = set(dosage_groups) | set(route_groups) | set(outcome_groups)
    exposures: list[PipelineBCompoundExposureRow] = []
    for author_hash, target_compound in sorted(keys):
        dose_rows = dosage_groups[(author_hash, target_compound)]
        route_rows = route_groups[(author_hash, target_compound)]
        outcome_rows = outcome_groups[(author_hash, target_compound)]
        midpoints = sorted(
            row.mass_midpoint_mg
            for row in dose_rows
            if row.mass_midpoint_mg is not None
        )
        dose_bands = sorted(
            {
                (row.dose_band_order, row.dose_band)
                for row in dose_rows
                if row.dose_band_order
            }
        )
        if not dose_rows:
            combined_dose_band, combined_dose_order = "not reported", None
        elif not dose_bands:
            combined_dose_band, combined_dose_order = "non-quantitative only", None
        elif len(dose_bands) == 1:
            combined_dose_order, combined_dose_band = dose_bands[0]
        else:
            combined_dose_band, combined_dose_order = "multiple bands", None

        exact_routes = sorted({row.route for row in route_rows})
        route_buckets = sorted({row.route_bucket for row in route_rows})
        if not route_rows:
            combined_route_bucket = "not reported"
        elif len(route_buckets) == 1:
            combined_route_bucket = route_buckets[0]
        else:
            combined_route_bucket = "multiple route families"

        if dose_rows and route_rows:
            dose_route_status = (
                "both single observations"
                if len(dose_rows) == 1 and len(route_rows) == 1
                else "both reported; pairing ambiguous"
            )
        elif dose_rows:
            dose_route_status = "dose only"
        elif route_rows:
            dose_route_status = "route only"
        else:
            dose_route_status = "neither dose nor route"

        outcome_values = [row.outcome for row in outcome_rows]
        conservative_outcome = (
            max(outcome_values, key=lambda value: _OUTCOME_RANK[value])
            if outcome_values
            else "not reported"
        )
        desired_results = sorted(
            {
                row.desired_result_bucket
                for row in outcome_rows
                if row.desired_result_bucket != "unspecified"
            }
        )
        exposures.append(
            PipelineBCompoundExposureRow(
                author_hash=author_hash,
                target_compound=target_compound,
                dose_values_json=json.dumps(
                    sorted({row.value for row in dose_rows}), ensure_ascii=False
                ),
                quantitative_dose_midpoints_mg_json=json.dumps(midpoints),
                dose_band=combined_dose_band,
                dose_band_order=combined_dose_order,
                route_values_json=json.dumps(exact_routes, ensure_ascii=False),
                route_buckets_json=json.dumps(route_buckets, ensure_ascii=False),
                route_bucket=combined_route_bucket,
                outcome_values_json=json.dumps(outcome_values),
                conservative_outcome=conservative_outcome,
                desired_result_buckets_json=json.dumps(desired_results),
                dose_observation_count=len(dose_rows),
                route_observation_count=len(route_rows),
                outcome_observation_count=len(outcome_rows),
                dose_route_status=dose_route_status,
            )
        )
    return exposures


def _prepare_staging_path(output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name(f".{output.name}.building")
    if staging.exists():
        staging.unlink()
    return staging


def _copy_pipeline_a(source: Path, staging: Path) -> None:
    source_uri = f"{source.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as source_connection:
        with closing(sqlite3.connect(staging)) as destination_connection:
            source_connection.backup(destination_connection)


def _insert_pipeline_b(
    connection: sqlite3.Connection,
    records: list[PipelineBRecord],
    columns: list[str],
    config: CombinedDatabaseConfig,
) -> CombinedDatabaseReport:
    cohort = load_comparator_cohort(config.cohort_path)
    required_source_tables = {
        "users",
        "treatment",
        "treatment_reports",
        "extraction_runs",
    }
    source_tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    missing = sorted(required_source_tables - source_tables)
    if missing:
        raise ValueError(f"Pipeline A database is missing tables: {', '.join(missing)}")

    connection.execute("PRAGMA foreign_keys = ON")
    for table in (
        "pipeline_b_compound_exposures",
        "pipeline_b_treatment_outcomes",
        "pipeline_b_administration_routes",
        "pipeline_b_dosages",
        "pipeline_b_records",
        "pipeline_a_side_effects",
        "combined_pipeline_manifest",
    ):
        connection.execute(f"DROP TABLE IF EXISTS {_quote_identifier(table)}")

    definitions = []
    for column in columns:
        sql_type = "INTEGER" if column == "text_count" else "TEXT"
        constraints = (
            " PRIMARY KEY REFERENCES users(user_id)" if column == "author_hash" else ""
        )
        definitions.append(f"{_quote_identifier(column)} {sql_type}{constraints}")
    connection.execute(f"CREATE TABLE pipeline_b_records ({', '.join(definitions)})")
    connection.executescript(
        """
        CREATE TABLE pipeline_b_dosages (
            author_hash TEXT NOT NULL REFERENCES pipeline_b_records(author_hash),
            ordinal INTEGER NOT NULL,
            treatment TEXT NOT NULL,
            value TEXT NOT NULL,
            target_compound TEXT,
            attribution_status TEXT NOT NULL,
            mass_low_mg REAL,
            mass_high_mg REAL,
            mass_midpoint_mg REAL,
            quantitative_mass INTEGER NOT NULL CHECK (quantitative_mass IN (0, 1)),
            dose_band TEXT NOT NULL,
            dose_band_order INTEGER,
            PRIMARY KEY (author_hash, ordinal)
        );
        CREATE TABLE pipeline_b_administration_routes (
            author_hash TEXT NOT NULL REFERENCES pipeline_b_records(author_hash),
            ordinal INTEGER NOT NULL,
            treatment TEXT NOT NULL,
            route TEXT NOT NULL,
            route_bucket TEXT NOT NULL,
            target_compound TEXT,
            attribution_status TEXT NOT NULL,
            PRIMARY KEY (author_hash, ordinal)
        );
        CREATE TABLE pipeline_b_treatment_outcomes (
            author_hash TEXT NOT NULL REFERENCES pipeline_b_records(author_hash),
            ordinal INTEGER NOT NULL,
            treatment TEXT NOT NULL,
            outcome TEXT NOT NULL,
            symptom TEXT NOT NULL,
            desired_result_bucket TEXT NOT NULL,
            target_compound TEXT,
            raw_value TEXT NOT NULL,
            PRIMARY KEY (author_hash, ordinal)
        );
        CREATE TABLE pipeline_b_compound_exposures (
            author_hash TEXT NOT NULL REFERENCES pipeline_b_records(author_hash),
            target_compound TEXT NOT NULL,
            dose_values_json TEXT NOT NULL,
            quantitative_dose_midpoints_mg_json TEXT NOT NULL,
            dose_band TEXT NOT NULL,
            dose_band_order INTEGER,
            route_values_json TEXT NOT NULL,
            route_buckets_json TEXT NOT NULL,
            route_bucket TEXT NOT NULL,
            outcome_values_json TEXT NOT NULL,
            conservative_outcome TEXT NOT NULL,
            desired_result_buckets_json TEXT NOT NULL,
            dose_observation_count INTEGER NOT NULL,
            route_observation_count INTEGER NOT NULL,
            outcome_observation_count INTEGER NOT NULL,
            dose_route_status TEXT NOT NULL,
            PRIMARY KEY (author_hash, target_compound)
        );
        CREATE TABLE pipeline_a_side_effects (
            report_id INTEGER NOT NULL REFERENCES treatment_reports(report_id),
            user_id TEXT NOT NULL REFERENCES users(user_id),
            drug_id INTEGER NOT NULL REFERENCES treatment(id),
            treatment TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            raw_value TEXT NOT NULL,
            canonical_side_effect TEXT NOT NULL,
            side_effect_bucket TEXT NOT NULL,
            PRIMARY KEY (report_id, ordinal)
        );
        CREATE TABLE combined_pipeline_manifest (
            pipeline TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            record_count INTEGER NOT NULL,
            source_artifact TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            details_json TEXT NOT NULL
        );
        CREATE INDEX pipeline_b_dosages_compound_idx
            ON pipeline_b_dosages(target_compound, dose_band_order, quantitative_mass);
        CREATE INDEX pipeline_b_routes_compound_idx
            ON pipeline_b_administration_routes(target_compound, route_bucket, route);
        CREATE INDEX pipeline_b_outcomes_compound_idx
            ON pipeline_b_treatment_outcomes(target_compound, desired_result_bucket, outcome);
        CREATE INDEX pipeline_b_exposures_design_idx
            ON pipeline_b_compound_exposures(
                target_compound, dose_band_order, route_bucket, conservative_outcome
            );
        CREATE INDEX pipeline_a_side_effects_bucket_idx
            ON pipeline_a_side_effects(
                treatment, side_effect_bucket, canonical_side_effect
            );
        """
    )

    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(_quote_identifier(column) for column in columns)
    raw_rows = []
    for record in records:
        values = record.model_dump()
        raw_rows.append(
            tuple(
                int(values.get(column) or 0)
                if column == "text_count"
                else str(values.get(column) or "")
                for column in columns
            )
        )
    connection.executemany(
        f"INSERT INTO pipeline_b_records ({column_sql}) VALUES ({placeholders})",
        raw_rows,
    )

    author_segments = (
        load_author_segments(config.pipeline_b_corpus_directory)
        if config.pipeline_b_corpus_directory is not None
        else None
    )
    dosages = [
        row for record in records for row in _dosage_rows(record, cohort, author_segments)
    ]
    routes = [
        row for record in records for row in _route_rows(record, cohort, author_segments)
    ]
    outcomes = [row for record in records for row in _outcome_rows(record, cohort)]
    exposures = _compound_exposure_rows(dosages, routes, outcomes)
    side_effects = _side_effect_rows(connection)
    connection.executemany(
        """
        INSERT INTO pipeline_b_dosages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row.author_hash,
                row.ordinal,
                row.treatment,
                row.value,
                row.target_compound,
                row.attribution_status,
                row.mass_low_mg,
                row.mass_high_mg,
                row.mass_midpoint_mg,
                int(row.quantitative_mass),
                row.dose_band,
                row.dose_band_order,
            )
            for row in dosages
        ],
    )
    connection.executemany(
        "INSERT INTO pipeline_b_administration_routes VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                row.author_hash,
                row.ordinal,
                row.treatment,
                row.route,
                row.route_bucket,
                row.target_compound,
                row.attribution_status,
            )
            for row in routes
        ],
    )
    connection.executemany(
        "INSERT INTO pipeline_b_treatment_outcomes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                row.author_hash,
                row.ordinal,
                row.treatment,
                row.outcome,
                row.symptom,
                row.desired_result_bucket,
                row.target_compound,
                row.raw_value,
            )
            for row in outcomes
        ],
    )
    connection.executemany(
        "INSERT INTO pipeline_b_compound_exposures VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                row.author_hash,
                row.target_compound,
                row.dose_values_json,
                row.quantitative_dose_midpoints_mg_json,
                row.dose_band,
                row.dose_band_order,
                row.route_values_json,
                row.route_buckets_json,
                row.route_bucket,
                row.outcome_values_json,
                row.conservative_outcome,
                row.desired_result_buckets_json,
                row.dose_observation_count,
                row.route_observation_count,
                row.outcome_observation_count,
                row.dose_route_status,
            )
            for row in exposures
        ],
    )
    connection.executemany(
        "INSERT INTO pipeline_a_side_effects VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                row.report_id,
                row.user_id,
                row.drug_id,
                row.treatment,
                row.ordinal,
                row.raw_value,
                row.canonical_side_effect,
                row.side_effect_bucket,
            )
            for row in side_effects
        ],
    )

    pipeline_a_reports = connection.execute(
        "SELECT COUNT(*) FROM treatment_reports"
    ).fetchone()[0]
    pipeline_a_users = connection.execute(
        "SELECT COUNT(DISTINCT user_id) FROM treatment_reports"
    ).fetchone()[0]
    imported_at = datetime.now(UTC).isoformat()
    pipeline_a_details = {
        "users_in_database": connection.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0],
        "extraction_runs": connection.execute(
            "SELECT COUNT(*) FROM extraction_runs"
        ).fetchone()[0],
    }
    pipeline_b_details = {
        "run_name": config.pipeline_b_run_name,
        "columns": len(columns),
        "dosage_pairs": len(dosages),
        "route_pairs": len(routes),
        "outcome_entries": len(outcomes),
        "compound_exposures": len(exposures),
        "records_sha256": _sha256(config.pipeline_b_records),
        "cohort_schema_id": cohort.schema_id,
        "cohort_sha256": sha256_file(config.cohort_path),
        "attribution_checked": author_segments is not None,
        "dose_attribution": dict(
            sorted(Counter(row.attribution_status for row in dosages).items())
        ),
        "route_attribution": dict(
            sorted(Counter(row.attribution_status for row in routes).items())
        ),
    }
    connection.executemany(
        "INSERT INTO combined_pipeline_manifest VALUES (?, ?, ?, ?, ?, ?)",
        [
            (
                "pipeline_a",
                "complete",
                pipeline_a_reports,
                config.source_database.name,
                imported_at,
                json.dumps(pipeline_a_details, sort_keys=True),
            ),
            (
                "pipeline_b",
                "complete",
                len(records),
                config.pipeline_b_records.name,
                imported_at,
                json.dumps(pipeline_b_details, sort_keys=True),
            ),
        ],
    )
    return CombinedDatabaseReport(
        output_database=config.output_database,
        pipeline_a_reports=pipeline_a_reports,
        pipeline_a_users=pipeline_a_users,
        pipeline_b_records=len(records),
        pipeline_b_dosages=len(dosages),
        pipeline_b_routes=len(routes),
        pipeline_b_outcomes=len(outcomes),
        pipeline_b_compound_exposures=len(exposures),
        pipeline_a_side_effects=len(side_effects),
    )


def build_combined_database(config: CombinedDatabaseConfig) -> CombinedDatabaseReport:
    """Atomically copy Pipeline A and add normalized Pipeline B tables."""
    columns = _csv_columns(config.pipeline_b_records)
    records = load_pipeline_b_records(config.pipeline_b_records)
    if len(records) != config.expected_pipeline_b_records:
        raise ValueError(
            f"Expected {config.expected_pipeline_b_records} Pipeline B records, "
            f"found {len(records)}"
        )
    authors = [record.author_hash for record in records]
    if len(authors) != len(set(authors)):
        raise ValueError("Pipeline B records contain duplicate author_hash values")

    staging = _prepare_staging_path(config.output_database)
    try:
        _copy_pipeline_a(config.source_database, staging)
        with closing(sqlite3.connect(staging)) as connection:
            with connection:
                report = _insert_pipeline_b(connection, records, columns, config)
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Combined database failed SQLite integrity_check")
            foreign_key_errors = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            if foreign_key_errors:
                raise ValueError(
                    f"Combined database has {len(foreign_key_errors)} foreign-key errors"
                )
            connection.execute("PRAGMA journal_mode = DELETE")
            connection.execute("PRAGMA optimize")
        os.replace(staging, config.output_database)
        return report
    except Exception:
        if staging.exists():
            staging.unlink()
        raise


@app.command()
def main(
    source_database: Annotated[
        Path,
        typer.Option("--source-db", exists=True, dir_okay=False, readable=True),
    ],
    pipeline_b_records: Annotated[
        Path,
        typer.Option(
            "--pipeline-b-records", exists=True, dir_okay=False, readable=True
        ),
    ],
    output_database: Annotated[
        Path,
        typer.Option("--output", dir_okay=False),
    ],
    cohort: Annotated[
        Path,
        typer.Option(exists=True, dir_okay=False, readable=True),
    ] = DEFAULT_COHORT_CONFIG,
    pipeline_b_corpus: Annotated[
        Path | None,
        typer.Option(exists=True, file_okay=False, readable=True),
    ] = None,
    expected_records: Annotated[int, typer.Option(min=1)] = 752,
    run_name: Annotated[str, typer.Option()] = "2026-08-27-linked-dose-route",
) -> None:
    """Copy Pipeline A and import a completed normalized Pipeline B run."""
    config = CombinedDatabaseConfig(
        source_database=source_database,
        pipeline_b_records=pipeline_b_records,
        output_database=output_database,
        cohort_path=cohort,
        pipeline_b_corpus_directory=pipeline_b_corpus,
        expected_pipeline_b_records=expected_records,
        pipeline_b_run_name=run_name,
    )
    report = build_combined_database(config)
    console.print(f"[green]Built[/green] {report.output_database}")
    console.print(
        f"Pipeline A: {report.pipeline_a_reports:,} reports from "
        f"{report.pipeline_a_users:,} users"
    )
    console.print(
        f"Pipeline B: {report.pipeline_b_records:,} records, "
        f"{report.pipeline_b_dosages:,} dosage pairs, "
        f"{report.pipeline_b_routes:,} route pairs, "
        f"{report.pipeline_b_outcomes:,} outcome entries, "
        f"{report.pipeline_b_compound_exposures:,} author-compound exposures"
    )
    console.print(
        f"Safety: {report.pipeline_a_side_effects:,} canonicalized side-effect mentions"
    )


if __name__ == "__main__":
    app()
