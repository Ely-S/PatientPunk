"""Publish aggregate-only Markdown and figures from a frozen severity checkpoint."""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from string import Template
from typing import Annotated

import typer
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from rich.console import Console

from studies.tropoflavin_nootropics.comparator_support import REPO_ROOT, sha256_file
from studies.tropoflavin_nootropics.privacy import require_private_aggregate_artifacts
from studies.tropoflavin_nootropics.severity_report_data import (
    BucketEstimate,
    CompoundSummary,
    DoseDefinition,
    FineCoefficient,
    FineEligibility,
    FineStatus,
    FrozenModelManifest,
    LeadingEffect,
    LinearCoefficient,
    LinearEligibility,
    LinearStatus,
    MeanPrediction,
    ModerateCell,
    ModerateCoefficient,
    SeverityPrediction,
    read_aggregate_csv,
    wilson_interval,
)

app = typer.Typer(add_completion=False)
console = Console()
logger = logging.getLogger(__name__)
STUDY = REPO_ROOT / "studies" / "tropoflavin_nootropics"
RUNS = Path("studies/tropoflavin_nootropics/runs")
BASE = RUNS / "2026-09-03-side-effect-severity" / "aggregate"
LINEAR = RUNS / "2026-09-03-side-effect-severity-linear-models" / "aggregate"
FINE = RUNS / "2026-09-03-side-effect-severity-fine-grained" / "aggregate"


class PublishConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    data_root: Path
    output_directory: Path = STUDY / "reports"


class SourceDigest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    relative_path: str = Field(
        pattern=r"^studies/tropoflavin_nootropics/[a-zA-Z0-9_./-]+$"
    )
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)


class PublicationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_id: str = "tropoflavin_frozen_severity_publication_v1"
    mode: str = "validated rendering of saved aggregate outputs; no model refit"
    checkpoint: str = "2026-09-03 (some files finalized 2026-09-04 UTC)"
    sources: tuple[SourceDigest, ...]
    frozen_settings: FrozenModelManifest
    proportion_interval: str = "95% Wilson; independent author binomial model"


class Checkpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    summaries: tuple[CompoundSummary, ...]
    linear_eligibility: tuple[LinearEligibility, ...]
    fine_eligibility: tuple[FineEligibility, ...]
    effects: tuple[LeadingEffect, ...]
    definitions: tuple[DoseDefinition, ...]
    buckets: tuple[BucketEstimate, ...]
    linear_status: tuple[LinearStatus, ...]
    fine_status: tuple[FineStatus, ...]
    linear_coefficients: tuple[LinearCoefficient, ...]
    fine_coefficients: tuple[FineCoefficient, ...]
    moderate_coefficients: tuple[ModerateCoefficient, ...]
    moderate_cells: tuple[ModerateCell, ...]
    mean_predictions: tuple[MeanPrediction, ...]
    severity_predictions: tuple[SeverityPrediction, ...]
    manifest: PublicationManifest


def load_checkpoint(data_root: Path) -> Checkpoint:
    """Read only enumerated aggregate files; never traverse corpus or DB directories."""
    sources: list[SourceDigest] = []

    def source(relative: Path) -> Path:
        path = data_root / relative
        sources.append(
            SourceDigest(
                relative_path=relative.as_posix(),
                sha256=sha256_file(path),
                size_bytes=path.stat().st_size,
            )
        )
        return path

    summaries = read_aggregate_csv(
        source(BASE / "side_effect_severity_by_compound.csv"), CompoundSummary
    )
    linear_eligibility = read_aggregate_csv(
        source(LINEAR / "severity_model_eligibility.csv"), LinearEligibility
    )
    fine_eligibility = read_aggregate_csv(
        source(FINE / "fine_grained_eligibility.csv"), FineEligibility
    )
    effects = read_aggregate_csv(
        source(FINE / "moderate_or_worse_leading_effects.csv"), LeadingEffect
    )
    definitions = read_aggregate_csv(
        source(FINE / "fine_grained_dose_bucket_definitions.csv"), DoseDefinition
    )
    buckets = read_aggregate_csv(
        source(FINE / "fine_grained_bucket_estimates.csv"), BucketEstimate
    )
    linear_status = read_aggregate_csv(
        source(LINEAR / "severity_model_status.csv"), LinearStatus
    )
    fine_status = read_aggregate_csv(
        source(FINE / "fine_grained_model_status.csv"), FineStatus
    )
    linear_coefficients = read_aggregate_csv(
        source(LINEAR / "severity_model_coefficients.csv"), LinearCoefficient
    )
    fine_coefficients = read_aggregate_csv(
        source(FINE / "fine_grained_model_coefficients.csv"), FineCoefficient
    )
    moderate_coefficients = read_aggregate_csv(
        source(FINE / "moderate_or_worse_model_coefficients.csv"), ModerateCoefficient
    )
    moderate_cells = read_aggregate_csv(
        source(FINE / "moderate_or_worse_bpc_dose_route_cells.csv"), ModerateCell
    )
    mean_predictions = read_aggregate_csv(
        source(LINEAR / "severity_model_predictions.csv"), MeanPrediction
    )
    severity_predictions = read_aggregate_csv(
        source(FINE / "fine_grained_severity_probabilities.csv"), SeverityPrediction
    )
    manifest_path = source(FINE / "fine_grained_manifest.json")
    try:
        settings = FrozenModelManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8-sig")
        )
    except ValidationError as exc:
        raise ValueError("Invalid frozen model manifest; content withheld") from exc
    for relative in (
        BASE / "side_effect_severity_manifest.json",
        LINEAR / "severity_model_manifest.json",
        FINE / "moderate_or_worse_manifest.json",
    ):
        source(relative)
    for path in (
        STUDY / "comparator_cohort.json",
        STUDY / "severity_report_template.md",
        STUDY / "severity_report_data.py",
        STUDY / "publish_severity_reports.py",
        STUDY / "severity_report_figures.py",
    ):
        sources.append(
            SourceDigest(
                relative_path=path.relative_to(REPO_ROOT).as_posix(),
                sha256=sha256_file(path),
                size_bytes=path.stat().st_size,
            )
        )
    combined = {
        row.compound: row
        for row in summaries
        if row.scope == "all communities, globally deduplicated"
    }
    if (
        len(combined) != 10
        or len(linear_eligibility) != 10
        or len(fine_eligibility) != 10
        or set(combined) != {row.compound for row in linear_eligibility}
        or set(combined) != {row.compound for row in fine_eligibility}
    ):
        raise ValueError("Frozen checkpoint must contain all ten compounds")
    for row in fine_eligibility:
        summary = combined[row.compound]
        if (
            row.classified_authors,
            row.authors_with_any_side_effect,
            row.authors_with_explicit_severity,
        ) != (
            summary.authors,
            summary.authors_with_any_side_effect,
            summary.authors_with_explicit_severity,
        ):
            raise ValueError(f"Cross-file eligibility mismatch for {row.compound}")
    for linear_row in linear_eligibility:
        if (
            linear_row.explicit_severity_authors
            != combined[linear_row.compound].authors_with_explicit_severity
        ):
            raise ValueError(f"Cross-file severity mismatch for {linear_row.compound}")
    return Checkpoint(
        summaries=summaries,
        linear_eligibility=linear_eligibility,
        fine_eligibility=fine_eligibility,
        effects=effects,
        definitions=definitions,
        buckets=buckets,
        linear_status=linear_status,
        fine_status=fine_status,
        linear_coefficients=linear_coefficients,
        fine_coefficients=fine_coefficients,
        moderate_coefficients=moderate_coefficients,
        moderate_cells=moderate_cells,
        mean_predictions=mean_predictions,
        severity_predictions=severity_predictions,
        manifest=PublicationManifest(sources=tuple(sources), frozen_settings=settings),
    )


def table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    def line(cells: Sequence[object]) -> str:
        return (
            "| "
            + " | ".join(
                "not estimable" if value is None else str(value) for value in cells
            )
            + " |"
        )

    return "\n".join(
        (line(headers), line(["---"] * len(headers)), *(line(row) for row in rows))
    )


def rate(successes: int, total: int) -> str:
    if total == 0:
        return "0/0; not estimable"
    lower, upper = wilson_interval(successes, total)
    return f"{successes}/{total} ({successes / total:.1%}; {lower:.1%} to {upper:.1%})"


def estimate(value: float | None, lower: float | None, upper: float | None) -> str:
    if value is None:
        return "not estimable"
    if lower is None or upper is None:
        return f"{value:.2f}; CI not estimable"

    def formatted(number: float) -> str:
        return f"{number:.2g}" if 0 < abs(number) < 0.005 else f"{number:.2f}"

    suffix = " [identical limits]" if lower == upper else ""
    return f"{formatted(value)} ({formatted(lower)} to {formatted(upper)}){suffix}"


def p_value(value: float) -> str:
    return "<0.0001" if value < 0.0001 else f"{value:.4f}"


def combined_summaries(data: Checkpoint) -> tuple[CompoundSummary, ...]:
    return tuple(
        row
        for row in data.summaries
        if row.scope == "all communities, globally deduplicated"
    )


def render_summary(data: Checkpoint) -> str:
    summaries = combined_summaries(data)
    dhf = next(row for row in summaries if row.compound == "7,8-DHF")
    cerebro = next(row for row in summaries if row.compound == "Cerebrolysin")
    dhf_eligibility = next(
        row for row in data.linear_eligibility if row.compound == "7,8-DHF"
    )
    fine = {row.compound: row for row in data.fine_eligibility}
    summary = table(
        [
            "Compound",
            "Classified authors",
            "Any mapped effect (95% CI)",
            "Graded / effect-reporting authors (95% CI)",
            "Moderate+ / all authors (95% CI)",
            "Moderate+ / graded authors (95% CI)",
        ],
        (
            (
                row.compound,
                row.authors,
                rate(row.authors_with_any_side_effect, row.authors),
                rate(
                    row.authors_with_explicit_severity, row.authors_with_any_side_effect
                ),
                rate(row.authors_with_explicit_moderate_or_worse, row.authors),
                rate(
                    row.authors_with_explicit_moderate_or_worse,
                    row.authors_with_explicit_severity,
                ),
            )
            for row in summaries
        ),
    )
    eligibility = table(
        [
            "Compound",
            "Graded authors",
            "With dose",
            "With route",
            "With both",
            "Distinct graded effects",
            "Graded effects with both",
        ],
        (
            (
                row.compound,
                row.explicit_severity_authors,
                row.dose_model_authors,
                row.route_model_authors,
                row.dose_and_route_model_authors,
                fine[row.compound].distinct_explicitly_graded_effects,
                fine[row.compound].dose_and_route_linked_graded_effects,
            )
            for row in data.linear_eligibility
        ),
    )
    effects = table(
        [
            "Compound",
            "Mapped side effect",
            "Authors moderate+",
            "Moderate",
            "Severe",
            "Life-threatening",
        ],
        (
            (
                row.compound,
                row.side_effect,
                row.authors,
                row.moderate,
                row.severe,
                row.life_threatening,
            )
            for row in data.effects
        ),
    )
    moderate = table(
        ["Compound", "Model", "Term", "Graded authors", "OR (95% CI)", "p"],
        (
            (
                row.compound,
                row.model,
                row.term,
                row.authors,
                estimate(
                    row.odds_ratio, row.odds_ratio_95_ci_low, row.odds_ratio_95_ci_high
                ),
                p_value(row.p_value),
            )
            for row in data.moderate_coefficients
        ),
    )
    joint = table(
        [
            "Outcome",
            "Scope / compound",
            "Term",
            "Authors",
            "Score difference (95% CI)",
            "p",
        ],
        (
            (
                row.outcome,
                row.compound,
                row.term,
                row.author_clusters,
                estimate(row.estimate, row.estimate_95_ci_low, row.estimate_95_ci_high),
                p_value(row.p_value),
            )
            for row in data.fine_coefficients
            if row.model == "dose + route"
            and row.outcome in ("maximum severity", "average severity")
            and (row.term.startswith("log2") or row.term.startswith("route:"))
        ),
    )
    definitions = table(
        ["Compound", "First cut (mg)", "Second cut (mg)"],
        (
            (row.compound, f"{row.first_cut_mg:.6g}", f"{row.second_cut_mg:.6g}")
            for row in data.definitions
        ),
    )
    template = Template(
        (STUDY / "severity_report_template.md").read_text(encoding="utf-8")
    )
    return template.substitute(
        community_count=len(data.manifest.frozen_settings.databases),
        dhf_authors=dhf.authors,
        dhf_graded=dhf.authors_with_explicit_severity,
        dhf_dose=dhf_eligibility.dose_model_authors,
        dhf_joint=dhf_eligibility.dose_and_route_model_authors,
        cerebro_authors=cerebro.authors,
        cerebro_graded=cerebro.authors_with_explicit_severity,
        summary_table=summary,
        eligibility_table=eligibility,
        effects_table=effects,
        moderate_models_table=moderate,
        joint_models_table=joint,
        dose_definitions_table=definitions,
    )


def render_models(data: Checkpoint) -> str:
    parts = [
        "# Frozen September 3 model appendix",
        "Validated saved coefficients and statuses, not a refit. All intervals are 95%. The [main report](severity_checkpoint.md) defines units, scales, linkage, and limitations. Nominal p values are exploratory; this table does not apply an additional multiple-testing correction.",
        "Historical model adequacy has not been revalidated. Some pooled compound terms, including Cerebrolysin and 9-MBC, have near-zero estimates and confidence limits. These are unstable or degenerate nuisance terms in sparse models, not evidence of absent adverse risk. Interpret neither their tiny nominal p values nor their apparent precision as clinical findings.",
    ]
    for outcome in dict.fromkeys(row.outcome for row in data.fine_coefficients):
        parts.extend(
            [
                f"## {outcome}",
                table(
                    [
                        "Scope",
                        "Compound",
                        "Model",
                        "Observations",
                        "Author clusters",
                        "Term",
                        "Scale",
                        "Estimate (95% CI)",
                        "p",
                    ],
                    (
                        (
                            row.scope,
                            row.compound,
                            row.model,
                            row.observations,
                            row.author_clusters,
                            row.term,
                            row.scale,
                            estimate(
                                row.estimate,
                                row.estimate_95_ci_low,
                                row.estimate_95_ci_high,
                            ),
                            p_value(row.p_value),
                        )
                        for row in data.fine_coefficients
                        if row.outcome == outcome
                    ),
                ),
            ]
        )
    parts.extend(
        [
            "## Maximum-severity primary and dose-screen sensitivity coefficients",
            table(
                [
                    "Analysis set",
                    "Scope",
                    "Compound",
                    "Model",
                    "Authors",
                    "Term",
                    "Score difference (95% CI)",
                    "p",
                ],
                (
                    (
                        row.analysis_set,
                        row.scope,
                        row.compound,
                        row.model,
                        row.authors,
                        row.term,
                        estimate(
                            row.estimate,
                            row.estimate_95_ci_low,
                            row.estimate_95_ci_high,
                        ),
                        p_value(row.p_value),
                    )
                    for row in data.linear_coefficients
                ),
            ),
        ]
    )
    parts.extend(
        [
            "## Fine-grained model statuses",
            table(
                [
                    "Outcome",
                    "Scope",
                    "Compound",
                    "Model",
                    "Eligible observations",
                    "Rare-route exclusions",
                    "Status",
                    "Reason",
                ],
                (
                    (
                        row.outcome,
                        row.scope,
                        row.compound,
                        row.model,
                        row.eligible_observations,
                        row.rare_route_records_excluded,
                        row.status,
                        row.reason or "",
                    )
                    for row in data.fine_status
                ),
            ),
        ]
    )
    parts.extend(
        [
            "## Maximum-severity model statuses",
            table(
                [
                    "Analysis set",
                    "Scope",
                    "Compound",
                    "Model",
                    "Linked authors",
                    "Eligible authors",
                    "Rare-route exclusions",
                    "Status",
                    "Reason",
                ],
                (
                    (
                        row.analysis_set,
                        row.scope,
                        row.compound,
                        row.model,
                        row.linked_authors_before_route_filter,
                        row.eligible_authors,
                        row.rare_route_records_excluded,
                        row.status,
                        row.reason or "",
                    )
                    for row in data.linear_status
                ),
            ),
        ]
    )
    return "\n\n".join(parts) + "\n"


def render_exposures(data: Checkpoint) -> str:
    parts = [
        "# Frozen September 3 exposure summaries",
        "These are descriptive author-history groups, not independent treatment episodes. Means use explicit grades only (mild=1 to life-threatening=4). The denominator for mean severity is the graded-author count, not all observations. Saved 95% intervals use 20,000 percentile bootstrap resamples. Missing intervals are not estimable. Collapsed intervals reflect identical observed scores, not certainty. See the [main report](severity_checkpoint.md) for compound-specific cut points and limitations.",
    ]
    for dimension in ("dose bucket", "route", "dose bucket + route"):
        parts.extend(
            [
                f"## {dimension}: author-treatment summaries",
                table(
                    [
                        "Compound",
                        "Dose bucket",
                        "Route",
                        "Authors",
                        "Any mapped effect / authors (95% CI)",
                        "Mean distinct effects",
                        "Graded authors",
                        "Mean maximum (95% CI)",
                        "Mean within-author average (95% CI)",
                    ],
                    (
                        (
                            row.compound,
                            row.dose_bucket or "",
                            row.route or "",
                            row.observations,
                            rate(row.any_side_effect_authors, row.observations)
                            if row.any_side_effect_authors is not None
                            else "not estimable",
                            f"{row.mean_distinct_side_effect_count:.2f}"
                            if row.mean_distinct_side_effect_count is not None
                            else "not estimable",
                            row.graded_authors,
                            estimate(
                                row.mean_maximum_severity,
                                row.maximum_95_ci_low,
                                row.maximum_95_ci_high,
                            ),
                            estimate(
                                row.mean_average_severity,
                                row.average_95_ci_low,
                                row.average_95_ci_high,
                            ),
                        )
                        for row in data.buckets
                        if row.dimension == dimension and row.unit == "author-treatment"
                    ),
                ),
            ]
        )
        parts.extend(
            [
                f"## {dimension}: distinct explicitly graded effects",
                "Each author can contribute several distinct effects; these counts are not independent people. Effect-weighted mean severity differs from the mean of authors' averages.",
                table(
                    [
                        "Compound",
                        "Dose bucket",
                        "Route",
                        "Graded effects",
                        "Authors",
                        "Mean effect grade",
                        "Mild",
                        "Moderate",
                        "Severe",
                        "Life-threatening",
                    ],
                    (
                        (
                            row.compound,
                            row.dose_bucket or "",
                            row.route or "",
                            row.observations,
                            row.graded_authors,
                            f"{row.mean_average_severity:.2f}"
                            if row.mean_average_severity is not None
                            else "not estimable",
                            row.mild_effects,
                            row.moderate_effects,
                            row.severe_effects,
                            row.life_threatening_effects,
                        )
                        for row in data.buckets
                        if row.dimension == dimension
                        and row.unit == "distinct explicitly graded side effect"
                    ),
                ),
            ]
        )
    parts.extend(
        [
            "## BPC-157 conditional moderate+ dose-route cells",
            "The denominator is authors with an explicitly graded effect in the cell. Intervals are recalculated as 95% Wilson intervals and checked against the saved limits. These sparse cells do not provide a stable interaction estimate.",
            table(
                [
                    "Compound",
                    "Dose bucket",
                    "Route",
                    "Moderate+ / graded authors (95% CI)",
                ],
                (
                    (
                        row.compound,
                        row.dose_bucket,
                        row.route,
                        rate(
                            row.moderate_or_worse_numerator,
                            row.moderate_or_worse_denominator,
                        ),
                    )
                    for row in data.moderate_cells
                ),
            ),
        ]
    )
    parts.extend(
        [
            "## Historical adjusted maximum-severity means",
            "Saved in-sample model estimates at each group's representative exposure. The 95% intervals describe an adjusted mean, not an individual prediction interval. Sparse or degenerate historical fits have not been independently revalidated.",
            table(
                [
                    "Scope",
                    "Compound",
                    "Model",
                    "Dose bucket",
                    "Route",
                    "Authors",
                    "Median dose mg",
                    "Observed mean maximum (95% CI)",
                    "Adjusted mean (95% CI)",
                ],
                (
                    (
                        row.scope,
                        row.compound,
                        row.model,
                        row.dose_bucket or "",
                        row.route or "",
                        row.authors,
                        f"{row.median_dose_mg:.6g}"
                        if row.median_dose_mg is not None
                        else "",
                        estimate(
                            row.observed_mean_max_severity,
                            row.observed_mean_95_ci_low,
                            row.observed_mean_95_ci_high,
                        ),
                        estimate(
                            row.adjusted_predicted_mean,
                            row.adjusted_mean_95_ci_low,
                            row.adjusted_mean_95_ci_high,
                        ),
                    )
                    for row in data.mean_predictions
                ),
            ),
            "## Historical ordinal severity probabilities",
            "These are probabilities for an already explicitly graded, distinct reported effect. They do not estimate the probability that a treated person develops an adverse effect. Recorded 95% model intervals and zero-probability categories are historical model outputs, not a claim of zero population risk.",
            table(
                [
                    "Scope",
                    "Compound",
                    "Model",
                    "Dose bucket",
                    "Route",
                    "Effects / authors",
                    "Representative mg",
                    "Moderate+ probability (95% CI)",
                    "Severe+ probability (95% CI)",
                ],
                (
                    (
                        row.scope,
                        row.compound,
                        row.model,
                        row.dose_bucket or "",
                        row.route or "",
                        f"{row.observed_effects_in_stratum}/{row.authors_in_stratum}",
                        f"{row.representative_dose_mg:.6g}"
                        if row.representative_dose_mg is not None
                        else "",
                        estimate(
                            row.moderate_or_worse_probability,
                            row.moderate_or_worse_95_ci_low,
                            row.moderate_or_worse_95_ci_high,
                        ),
                        estimate(
                            row.severe_or_worse_probability,
                            row.severe_or_worse_95_ci_low,
                            row.severe_or_worse_95_ci_high,
                        ),
                    )
                    for row in data.severity_predictions
                ),
            ),
        ]
    )
    return "\n\n".join(parts) + "\n"


def publish_reports(config: PublishConfig) -> tuple[Path, ...]:
    started = time.monotonic()
    data = load_checkpoint(config.data_root)
    config.output_directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, content in (
        ("severity_checkpoint.md", render_summary(data)),
        ("severity_checkpoint_models.md", render_models(data)),
        ("severity_checkpoint_exposures.md", render_exposures(data)),
        (
            "severity_checkpoint_provenance.json",
            data.manifest.model_dump_json(indent=2) + "\n",
        ),
    ):
        path = config.output_directory / name
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    require_private_aggregate_artifacts(tuple(paths))
    from studies.tropoflavin_nootropics.severity_report_figures import render_figures

    paths.extend(render_figures(data, config.output_directory))
    logger.info(
        json.dumps(
            {
                "run_id": "severity-checkpoint-2026-09-03",
                "phase": "aggregate-publication",
                "schema_id": data.manifest.schema_id,
                "duration": round(time.monotonic() - started, 3),
                "status": "complete",
            }
        )
    )
    return tuple(paths)


@app.command()
def main(
    data_root: Annotated[
        Path | None, typer.Option(exists=True, file_okay=False)
    ] = None,
    output_directory: Annotated[Path, typer.Option()] = STUDY / "reports",
) -> None:
    """Validate and publish saved aggregates without database or network access."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        resolved_data = data_root or Path(
            os.environ.get("PATIENTPUNK_DATA") or REPO_ROOT.parent / "PatientPunk_data"
        )
        outputs = publish_reports(
            PublishConfig(data_root=resolved_data, output_directory=output_directory)
        )
    except (OSError, ValueError) as exc:
        console.print(f"[red]Publication failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print(
        f"[green]Published {len(outputs)} aggregate report artifacts.[/green]"
    )


if __name__ == "__main__":
    app()
