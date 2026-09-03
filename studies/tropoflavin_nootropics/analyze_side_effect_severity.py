"""Summarize explicit side-effect severity across independent community runs."""

from __future__ import annotations

import csv
import json
import sqlite3
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import typer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from rich.console import Console

from studies.tropoflavin_nootropics.comparator_support import (
    DEFAULT_COHORT_CONFIG,
    ComparatorCohort,
    analysis_compound_name,
    compound_for_treatment,
    load_comparator_cohort,
    sha256_file,
)
from studies.tropoflavin_nootropics.study_support import canonical_side_effect

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()

Severity = Literal["mild", "moderate", "severe", "life_threatening"]
SEVERITY_ORDER: dict[Severity, int] = {
    "mild": 1,
    "moderate": 2,
    "severe": 3,
    "life_threatening": 4,
}


class SeverityAnalysisConfig(BaseModel):
    """Validated boundary for a privacy-safe aggregate analysis."""

    model_config = ConfigDict(frozen=True)

    run_root: Path
    output_directory: Path
    cohort_path: Path = DEFAULT_COHORT_CONFIG
    min_stratified_authors: int = Field(default=5, ge=1)

    @model_validator(mode="after")
    def validate_inputs(self) -> SeverityAnalysisConfig:
        if not self.run_root.is_dir():
            raise ValueError(f"Run root not found: {self.run_root}")
        if not self.cohort_path.is_file():
            raise ValueError(f"Comparator cohort not found: {self.cohort_path}")
        return self


class DatabaseProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    group: str
    community: str
    filename: str
    size_bytes: int = Field(ge=0)
    sha256: str


class SeverityAnalysisManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_id: str = "tropoflavin_side_effect_severity_analysis_v1"
    generated_at: str
    explicit_severity_only: bool = True
    min_stratified_authors: int
    databases: tuple[DatabaseProvenance, ...]


@dataclass(frozen=True, slots=True)
class Artifact:
    group: str
    community: str
    path: Path


@dataclass(frozen=True, slots=True)
class EffectObservation:
    group: str
    community: str
    author: str
    compound: str
    canonical_effect: str
    severity: Severity | None


@dataclass(frozen=True, slots=True)
class AuthorObservation:
    group: str
    community: str
    author: str
    compound: str


@dataclass(frozen=True, slots=True)
class ExposureObservation:
    group: str
    community: str
    author: str
    compound: str
    dose_band: str | None
    route_bucket: str | None


@dataclass(slots=True)
class ScopeData:
    authors: set[tuple[str, str]] = field(default_factory=set)
    effects: dict[tuple[str, str, str], Severity | None] = field(default_factory=dict)
    exposures: dict[tuple[str, str], tuple[set[str], set[str]]] = field(
        default_factory=dict
    )


def _discover_artifacts(run_root: Path) -> tuple[Artifact, ...]:
    artifacts: list[Artifact] = []
    for path in sorted(run_root.rglob("sentiment.db")):
        relative = path.relative_to(run_root)
        if "patient-communities" in relative.parts:
            group = "patient communities"
            community = path.parent.name
        else:
            group = "nootropic-adjacent communities"
            community = path.parent.name
        combined = path.with_name("combined.db")
        artifacts.append(
            Artifact(
                group=group,
                community=community,
                path=combined if combined.is_file() else path,
            )
        )
    if not artifacts:
        raise ValueError(f"No sentiment databases found under {run_root}")
    return tuple(artifacts)


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _compound_name(treatment: str, cohort: ComparatorCohort) -> str | None:
    return compound_for_treatment(treatment, cohort)


def _decode_effects(raw: str | None) -> tuple[tuple[str, Severity | None], ...]:
    if not raw:
        return ()
    values = json.loads(raw)
    if not isinstance(values, list):
        raise ValueError("side_effects must be a JSON list")
    effects: list[tuple[str, Severity | None]] = []
    for value in values:
        if isinstance(value, str):
            effect = value.strip()
            severity: Severity | None = None
        elif isinstance(value, dict):
            effect = str(value.get("side_effect") or "").strip()
            raw_severity = value.get("severity")
            if raw_severity is not None and raw_severity not in SEVERITY_ORDER:
                raise ValueError(f"Invalid explicit severity: {raw_severity!r}")
            severity = raw_severity
        else:
            raise ValueError("side_effects entries must be strings or objects")
        if effect:
            effects.append((effect, severity))
    return tuple(effects)


def _max_severity(left: Severity | None, right: Severity | None) -> Severity | None:
    if left is None:
        return right
    if right is None:
        return left
    return left if SEVERITY_ORDER[left] >= SEVERITY_ORDER[right] else right


def _load_artifact(
    artifact: Artifact,
    cohort: ComparatorCohort,
) -> tuple[list[AuthorObservation], list[EffectObservation], list[ExposureObservation]]:
    authors: list[AuthorObservation] = []
    effects: list[EffectObservation] = []
    exposures: list[ExposureObservation] = []
    with closing(_connect(artifact.path)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"Integrity check failed for {artifact.path}: {integrity}")
        rows = connection.execute(
            """
            SELECT reports.user_id, treatment.canonical_name, reports.side_effects
            FROM treatment_reports AS reports
            JOIN treatment ON treatment.id = reports.drug_id
            """
        ).fetchall()
        seen_authors: set[tuple[str, str]] = set()
        for row in rows:
            compound = _compound_name(str(row["canonical_name"]), cohort)
            if compound is None:
                continue
            author_key = (str(row["user_id"]), compound)
            if author_key not in seen_authors:
                seen_authors.add(author_key)
                authors.append(
                    AuthorObservation(
                        group=artifact.group,
                        community=artifact.community,
                        author=author_key[0],
                        compound=compound,
                    )
                )
            for raw_effect, severity in _decode_effects(row["side_effects"]):
                canonical, _bucket = canonical_side_effect(raw_effect)
                effects.append(
                    EffectObservation(
                        group=artifact.group,
                        community=artifact.community,
                        author=author_key[0],
                        compound=compound,
                        canonical_effect=canonical,
                        severity=severity,
                    )
                )

        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if "pipeline_b_compound_exposures" in tables:
            for row in connection.execute(
                """
                SELECT author_hash, target_compound, dose_band, route_bucket
                FROM pipeline_b_compound_exposures
                """
            ):
                exposures.append(
                    ExposureObservation(
                        group=artifact.group,
                        community=artifact.community,
                        author=str(row["author_hash"]),
                        compound=str(row["target_compound"]),
                        dose_band=(
                            None
                            if row["dose_band"] in {None, "not reported"}
                            else str(row["dose_band"])
                        ),
                        route_bucket=(
                            None
                            if row["route_bucket"] in {None, "not reported"}
                            else str(row["route_bucket"])
                        ),
                    )
                )
    return authors, effects, exposures


def _scope_specs(artifacts: tuple[Artifact, ...]) -> list[tuple[str, set[tuple[str, str]]]]:
    specs: list[tuple[str, set[tuple[str, str]]]] = []
    for artifact in artifacts:
        specs.append(
            (
                f"r/{artifact.community}",
                {(artifact.group, artifact.community)},
            )
        )
    groups = sorted({artifact.group for artifact in artifacts})
    for group in groups:
        specs.append(
            (
                f"{group}, globally deduplicated",
                {
                    (artifact.group, artifact.community)
                    for artifact in artifacts
                    if artifact.group == group
                },
            )
        )
    specs.append(
        (
            "all communities, globally deduplicated",
            {(artifact.group, artifact.community) for artifact in artifacts},
        )
    )
    return specs


def _build_scope(
    members: set[tuple[str, str]],
    authors: list[AuthorObservation],
    effects: list[EffectObservation],
    exposures: list[ExposureObservation],
) -> ScopeData:
    scope = ScopeData()
    for author_observation in authors:
        if (author_observation.group, author_observation.community) in members:
            scope.authors.add(
                (author_observation.author, author_observation.compound)
            )
    for effect_observation in effects:
        if (effect_observation.group, effect_observation.community) not in members:
            continue
        key = (
            effect_observation.author,
            effect_observation.compound,
            effect_observation.canonical_effect,
        )
        scope.effects[key] = _max_severity(
            scope.effects.get(key), effect_observation.severity
        )
    exposure_values: dict[tuple[str, str], tuple[set[str], set[str]]] = defaultdict(
        lambda: (set(), set())
    )
    for exposure_observation in exposures:
        if (exposure_observation.group, exposure_observation.community) not in members:
            continue
        exposure_key = (exposure_observation.author, exposure_observation.compound)
        dose_values, route_values = exposure_values[exposure_key]
        if exposure_observation.dose_band:
            dose_values.add(exposure_observation.dose_band)
        if exposure_observation.route_bucket:
            route_values.add(exposure_observation.route_bucket)
    scope.exposures = dict(exposure_values)
    return scope


def _percent(numerator: int, denominator: int) -> str:
    return "n/a" if not denominator else f"{100 * numerator / denominator:.1f}%"


def _author_effect_summary(
    scope: ScopeData,
) -> tuple[set[tuple[str, str]], dict[tuple[str, str], Severity]]:
    affected: set[tuple[str, str]] = set()
    graded: dict[tuple[str, str], Severity] = {}
    for (author, compound, _effect), severity in scope.effects.items():
        key = (author, compound)
        affected.add(key)
        if severity is not None:
            maximum = _max_severity(graded.get(key), severity)
            if maximum is not None:
                graded[key] = maximum
    return affected, graded


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _overview_rows(
    scope_name: str,
    scope: ScopeData,
    compound_order: list[str],
) -> list[dict[str, object]]:
    affected, graded = _author_effect_summary(scope)
    rows: list[dict[str, object]] = []
    for compound in compound_order:
        cohort = {key for key in scope.authors if key[1] == compound}
        side_effect = {key for key in affected if key[1] == compound}
        explicit = {key: value for key, value in graded.items() if key[1] == compound}
        moderate = sum(SEVERITY_ORDER[value] >= 2 for value in explicit.values())
        severe = sum(SEVERITY_ORDER[value] >= 3 for value in explicit.values())
        rows.append(
            {
                "scope": scope_name,
                "compound": compound,
                "authors": len(cohort),
                "authors_with_any_side_effect": len(side_effect),
                "any_side_effect_percent": _percent(len(side_effect), len(cohort)),
                "authors_with_explicit_severity": len(explicit),
                "severity_coverage_of_side_effect_authors": _percent(
                    len(explicit), len(side_effect)
                ),
                "authors_with_explicit_moderate_or_worse": moderate,
                "authors_with_explicit_severe_or_worse": severe,
            }
        )
    return rows


def _effect_rows(
    scope_name: str,
    scope: ScopeData,
    compound_order: list[str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for compound in compound_order:
        categories = sorted(
            {
                effect
                for _author, value_compound, effect in scope.effects
                if value_compound == compound
            }
        )
        for category in categories:
            values = [
                severity
                for (_author, value_compound, effect), severity in scope.effects.items()
                if value_compound == compound and effect == category
            ]
            rows.append(
                {
                    "scope": scope_name,
                    "compound": compound,
                    "side_effect": category,
                    "authors": len(values),
                    "explicit_severity_authors": sum(value is not None for value in values),
                    "mild": values.count("mild"),
                    "moderate": values.count("moderate"),
                    "severe": values.count("severe"),
                    "life_threatening": values.count("life_threatening"),
                }
            )
    return rows


def _dose_route_rows(
    scope_name: str,
    scope: ScopeData,
    min_authors: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    affected, graded = _author_effect_summary(scope)
    feasibility: list[dict[str, object]] = []
    strata: dict[tuple[str, str, str], set[tuple[str, str]]] = defaultdict(set)
    compounds = sorted({compound for _author, compound in scope.authors})
    for compound in compounds:
        cohort = {key for key in scope.authors if key[1] == compound}
        dose_linked = 0
        route_linked = 0
        both_linked = 0
        both_graded = 0
        for key in cohort:
            dose_values, route_values = scope.exposures.get(key, (set(), set()))
            dose = next(iter(dose_values)) if len(dose_values) == 1 else None
            route = next(iter(route_values)) if len(route_values) == 1 else None
            if dose:
                dose_linked += 1
                strata[(compound, "dose", dose)].add(key)
            if route:
                route_linked += 1
                strata[(compound, "route", route)].add(key)
            if dose and route:
                both_linked += 1
                strata[(compound, "dose + route", f"{dose} | {route}")].add(key)
                if key in graded:
                    both_graded += 1
        feasibility.append(
            {
                "scope": scope_name,
                "compound": compound,
                "classified_authors": len(cohort),
                "authors_with_any_side_effect": len(cohort & affected),
                "single_dose_band": dose_linked,
                "single_route": route_linked,
                "single_dose_and_route": both_linked,
                "dose_and_route_with_explicit_severity": both_graded,
            }
        )

    rows: list[dict[str, object]] = []
    for (compound, dimension, level), members in sorted(strata.items()):
        if len(members) < min_authors:
            continue
        values = [graded[key] for key in members if key in graded]
        rows.append(
            {
                "scope": scope_name,
                "compound": compound,
                "dimension": dimension,
                "level": level,
                "linked_authors": len(members),
                "authors_with_any_side_effect": len(members & affected),
                "any_side_effect_percent": _percent(len(members & affected), len(members)),
                "authors_with_explicit_severity": len(values),
                "explicit_moderate_or_worse": sum(
                    SEVERITY_ORDER[value] >= 2 for value in values
                ),
                "explicit_severe_or_worse": sum(
                    SEVERITY_ORDER[value] >= 3 for value in values
                ),
            }
        )
    return feasibility, rows


def _markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    def clean(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(clean(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def _render_report(
    overview: list[dict[str, object]],
    feasibility: list[dict[str, object]],
    artifacts: tuple[Artifact, ...],
) -> str:
    aggregate_scopes = {
        "nootropic-adjacent communities, globally deduplicated",
        "patient communities, globally deduplicated",
        "all communities, globally deduplicated",
    }
    aggregate = [row for row in overview if row["scope"] in aggregate_scopes]
    overview_table = _markdown_table(
        [
            "Scope",
            "Compound",
            "Authors",
            "Any side effect",
            "Explicit severity",
            "Severity coverage",
            "Moderate+",
            "Severe+",
        ],
        [
            [
                row["scope"],
                row["compound"],
                row["authors"],
                f"{row['authors_with_any_side_effect']} ({row['any_side_effect_percent']})",
                row["authors_with_explicit_severity"],
                row["severity_coverage_of_side_effect_authors"],
                row["authors_with_explicit_moderate_or_worse"],
                row["authors_with_explicit_severe_or_worse"],
            ]
            for row in aggregate
        ],
    )
    combined_scope = "all communities, globally deduplicated"
    combined_feasibility = [row for row in feasibility if row["scope"] == combined_scope]
    feasibility_table = _markdown_table(
        [
            "Compound",
            "Classified authors",
            "Any side effect",
            "Dose",
            "Route",
            "Dose + route",
            "Dose + route + explicit severity",
        ],
        [
            [
                row["compound"],
                row["classified_authors"],
                row["authors_with_any_side_effect"],
                row["single_dose_band"],
                row["single_route"],
                row["single_dose_and_route"],
                row["dose_and_route_with_explicit_severity"],
            ]
            for row in combined_feasibility
        ],
    )
    return (
        "# Side-effect severity rerun\n\n"
        "## What changed\n\n"
        "Pipeline A was rerun with each side effect stored as an effect and an "
        "optional explicit severity. Severity is recorded only when the author "
        "directly grades it. Symptom names are never used to infer severity.\n\n"
        f"This report covers {len(artifacts)} independent community databases. "
        "Community results remain separate, and the aggregate scopes deduplicate the "
        "same hashed author across communities.\n\n"
        "## Aggregate results by compound\n\n"
        + overview_table
        + "\n\n## Can dose and route predict severity?\n\n"
        "The last column is the usable sample for the proposed dose-by-route severity "
        "model. It requires one linked dose band, one linked route, and at least one "
        "explicitly graded side effect for the same author and compound. These are "
        "author-level links, not necessarily same-episode links.\n\n"
        + feasibility_table
        + "\n\nA predictive model should be fit only where this final sample is large enough "
        "to support multiple dose-route cells. The accompanying stratified CSV keeps "
        "only cells meeting the configured minimum author count.\n\n"
        "## Files\n\n"
        "- `side_effect_severity_by_compound.csv`: community-specific and deduplicated "
        "compound summaries\n"
        "- `side_effect_severity_by_effect.csv`: standardized side effects with explicit "
        "severity counts\n"
        "- `side_effect_severity_feasibility.csv`: usable dose, route, and severity counts\n"
        "- `side_effect_severity_by_dose_route.csv`: aggregate strata that meet the "
        "minimum cell size\n"
        "- `side_effect_severity_manifest.json`: database hashes and analysis settings\n\n"
        "These are observational online-community reports, not clinical incidence or "
        "causal treatment effects.\n"
    )


def analyze_side_effect_severity(config: SeverityAnalysisConfig) -> Path:
    """Write aggregate severity and dose-route feasibility artifacts."""
    cohort = load_comparator_cohort(config.cohort_path)
    compound_order = [analysis_compound_name(compound) for compound in cohort.compounds]
    artifacts = _discover_artifacts(config.run_root)
    authors: list[AuthorObservation] = []
    effects: list[EffectObservation] = []
    exposures: list[ExposureObservation] = []
    for artifact in artifacts:
        artifact_authors, artifact_effects, artifact_exposures = _load_artifact(
            artifact, cohort
        )
        authors.extend(artifact_authors)
        effects.extend(artifact_effects)
        exposures.extend(artifact_exposures)

    overview: list[dict[str, object]] = []
    effect_rows: list[dict[str, object]] = []
    feasibility: list[dict[str, object]] = []
    dose_route: list[dict[str, object]] = []
    for scope_name, members in _scope_specs(artifacts):
        scope = _build_scope(members, authors, effects, exposures)
        overview.extend(_overview_rows(scope_name, scope, compound_order))
        effect_rows.extend(_effect_rows(scope_name, scope, compound_order))
        scope_feasibility, scope_dose_route = _dose_route_rows(
            scope_name, scope, config.min_stratified_authors
        )
        feasibility.extend(scope_feasibility)
        dose_route.extend(scope_dose_route)

    config.output_directory.mkdir(parents=True, exist_ok=True)
    _write_csv(config.output_directory / "side_effect_severity_by_compound.csv", overview)
    _write_csv(config.output_directory / "side_effect_severity_by_effect.csv", effect_rows)
    _write_csv(
        config.output_directory / "side_effect_severity_feasibility.csv", feasibility
    )
    _write_csv(
        config.output_directory / "side_effect_severity_by_dose_route.csv", dose_route
    )
    report_path = config.output_directory / "side_effect_severity_report.md"
    report_path.write_text(
        _render_report(overview, feasibility, artifacts), encoding="utf-8"
    )
    manifest = SeverityAnalysisManifest(
        generated_at=datetime.now(UTC).isoformat(),
        min_stratified_authors=config.min_stratified_authors,
        databases=tuple(
            DatabaseProvenance(
                group=artifact.group,
                community=artifact.community,
                filename=artifact.path.name,
                size_bytes=artifact.path.stat().st_size,
                sha256=sha256_file(artifact.path),
            )
            for artifact in artifacts
        ),
    )
    (config.output_directory / "side_effect_severity_manifest.json").write_text(
        manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return report_path


@app.command()
def main(
    run_root: Path = typer.Option(..., exists=True, file_okay=False),
    output_dir: Path = typer.Option(..., file_okay=False),
    cohort: Path = typer.Option(DEFAULT_COHORT_CONFIG, exists=True, dir_okay=False),
    min_stratified_authors: int = typer.Option(5, min=1),
) -> None:
    """Create aggregate explicit-severity reports without exporting author records."""
    report = analyze_side_effect_severity(
        SeverityAnalysisConfig(
            run_root=run_root,
            output_directory=output_dir,
            cohort_path=cohort,
            min_stratified_authors=min_stratified_authors,
        )
    )
    console.print(f"[green]Wrote[/green] {report}")


if __name__ == "__main__":
    app()
