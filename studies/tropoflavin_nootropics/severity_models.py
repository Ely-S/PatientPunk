"""Reconstruct exploratory severity associations without exporting participant rows."""

from __future__ import annotations

import csv
import json
import logging
import math
import time
import warnings
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm
import typer
from pydantic import BaseModel
from rich.console import Console
from statsmodels.genmod.generalized_estimating_equations import OrdinalGEE

from studies.tropoflavin_nootropics.comparator_support import (
    DEFAULT_COHORT_CONFIG,
    REPO_ROOT,
    load_comparator_cohort,
    sha256_file,
)
from studies.tropoflavin_nootropics.severity_model_contracts import (
    DESIGNS,
    OUTCOMES,
    Coefficient,
    Design,
    Eligibility,
    ModelManifest,
    ModelSettings,
    ModelStatus,
    Observation,
    Outcome,
    PackageVersion,
    RunConfig,
    Scale,
    SourceProvenance,
    _StatusArgs,
)
from studies.tropoflavin_nootropics.severity_model_data import (
    AuthorUnit,
    load_model_data,
)

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)
console = Console()
logger = logging.getLogger(__name__)


def observations(
    units: tuple[AuthorUnit, ...], outcome: Outcome
) -> tuple[Observation, ...]:
    rows = []
    for unit in units:
        grades = [effect.grade for effect in unit.effects if effect.grade is not None]
        values: list[tuple[float, str]]
        if outcome == "ordinal_grade":
            values = [
                (float(e.grade), e.domain) for e in unit.effects if e.grade is not None
            ]
        elif outcome in {"maximum_grade", "mean_grade", "moderate_plus"}:
            if not grades:
                continue
            value = {
                "maximum_grade": max(grades),
                "mean_grade": float(np.mean(grades)),
                "moderate_plus": int(max(grades) >= 2),
            }[outcome]
            values = [(float(value), "none")]
        else:
            values = [
                (
                    float(bool(unit.effects))
                    if outcome == "any_effect"
                    else float(len(unit.effects)),
                    "none",
                )
            ]
        dose = None if unit.dose_excluded else unit.dose_mg
        for value, domain in values:
            rows.append(
                Observation(
                    author=unit.author,
                    compound=unit.compound,
                    outcome=value,
                    dose_mg=dose,
                    log2_dose=math.log2(dose) if dose else None,
                    route=unit.route,
                    domain=domain,
                )
            )
    return tuple(rows)


def eligibility(units: tuple[AuthorUnit, ...]) -> tuple[Eligibility, ...]:
    result = []
    for compound in sorted({unit.compound for unit in units}):
        members = [unit for unit in units if unit.compound == compound]
        graded = [
            unit for unit in members if any(e.grade is not None for e in unit.effects)
        ]

        def dose(unit: AuthorUnit) -> bool:
            return unit.dose_mg is not None and not unit.dose_excluded

        result.append(
            Eligibility(
                compound=compound,
                authors=len(members),
                any_effect_authors=sum(bool(u.effects) for u in members),
                graded_authors=len(graded),
                graded_effects=sum(
                    e.grade is not None for u in members for e in u.effects
                ),
                dose_authors=sum(dose(u) for u in members),
                route_authors=sum(u.route is not None for u in members),
                dose_route_authors=sum(
                    dose(u) and u.route is not None for u in members
                ),
                graded_dose_authors=sum(dose(u) for u in graded),
                graded_route_authors=sum(u.route is not None for u in graded),
                graded_dose_route_authors=sum(
                    dose(u) and u.route is not None for u in graded
                ),
            )
        )
    return tuple(result)


def _filter_data(
    rows: tuple[Observation, ...], design: Design, settings: ModelSettings
) -> tuple[pd.DataFrame, int]:
    frame = pd.DataFrame(
        [row.model_dump() for row in rows], columns=list(Observation.model_fields)
    )
    if design != "route":
        frame = frame.dropna(subset=["log2_dose"])
    removed = 0
    if design != "dose":
        frame = frame.dropna(subset=["route"])
        counts = frame.groupby("route")["author"].nunique()
        keep = counts[counts >= settings.min_route_authors].index
        removed = int((~frame.route.isin(keep)).sum())
        frame = frame[frame.route.isin(keep)]
    return frame.reset_index(drop=True), removed


def _support_reason(
    frame: pd.DataFrame, outcome: Outcome, design: Design, settings: ModelSettings
) -> str | None:
    if frame.author.nunique() < settings.min_authors:
        return f"fewer than {settings.min_authors} independent authors"
    if frame.outcome.nunique() < 2:
        return "outcome has no variation"
    if design != "route" and frame.log2_dose.nunique() < 2:
        return "dose has no variation"
    if design != "dose" and frame.route.nunique() < 2:
        return "fewer than two supported route levels"
    if outcome in {"any_effect", "moderate_plus", "ordinal_grade"}:
        for threshold in sorted(frame.outcome.unique())[:-1]:
            counts = frame.groupby(frame.outcome > threshold).author.nunique()
            if len(counts) < 2 or int(counts.min()) < settings.min_outcome_authors:
                return "too few authors on one side of an outcome threshold"
    if design == "dose_route_interaction":
        # Compare dose support within compounds: their mg scales are not interchangeable.
        frame = frame.copy()
        medians = frame.groupby("compound").log2_dose.transform("median")
        frame["high_dose"] = frame.log2_dose > medians
        for _, subset in frame.groupby(["compound", "route"]):
            counts = subset.groupby("high_dose").author.nunique()
            if (
                len(counts) < 2
                or int(counts.min()) < settings.min_interaction_cell_authors
            ):
                return "insufficient within-compound dose variation in a route cell"
    return None


def fit_model(
    rows: tuple[Observation, ...],
    outcome: Outcome,
    design: Design,
    compound: str,
    settings: ModelSettings,
) -> tuple[ModelStatus, tuple[Coefficient, ...]]:
    pooled = compound == "all compounds"
    scope = "pooled with compound fixed effects" if pooled else "treatment-specific"
    frame, removed = _filter_data(rows, design, settings)
    shared: _StatusArgs = {
        "outcome": outcome,
        "scope": scope,
        "compound": compound,
        "model": design,
        "observations": len(frame),
        "authors": frame.author.nunique(),
        "rare_route_records_excluded": removed,
    }
    reason = _support_reason(frame, outcome, design, settings)
    if reason:
        return ModelStatus(**shared, status="not_estimable", reason=reason), ()
    formula = {
        "dose": "log2_dose",
        "route": "C(route)",
        "dose_route": "log2_dose + C(route)",
        "dose_route_interaction": "log2_dose * C(route)",
    }[design]
    if pooled and frame.compound.nunique() > 1:
        formula += " + C(compound)"
    domains = frame.groupby("domain").author.nunique()
    adjusted = (
        outcome == "ordinal_grade"
        and len(domains) > 1
        and domains.min() >= settings.min_route_authors
    )
    if adjusted:
        formula += " + C(domain)"
    x = patsy.dmatrix(formula, frame, return_type="dataframe")
    if outcome == "ordinal_grade":
        x = x.drop(columns="Intercept")
    if (
        np.linalg.matrix_rank(x) < x.shape[1]
        or frame.author.nunique() <= x.shape[1] + 2
    ):
        return ModelStatus(
            **shared,
            status="not_estimable",
            reason="rank-deficient design or insufficient residual author degrees of freedom",
            domain_adjustment=adjusted,
        ), ()
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            if outcome in {"maximum_grade", "mean_grade"}:
                model = sm.OLS(frame.outcome, x)
                result = (
                    model.fit(cov_type="cluster", cov_kwds={"groups": frame.author})
                    if pooled
                    else model.fit(cov_type="HC3")
                )
            elif outcome == "ordinal_grade":
                result = OrdinalGEE(
                    frame.outcome,
                    x,
                    groups=frame.author,
                    cov_struct=sm.cov_struct.Independence(),
                ).fit(maxiter=200)
            else:
                family = (
                    sm.families.NegativeBinomial(alpha=1.0)
                    if outcome == "effect_count"
                    else sm.families.Binomial()
                )
                result = sm.GEE(
                    frame.outcome,
                    x,
                    groups=frame.author,
                    family=family,
                    cov_struct=sm.cov_struct.Independence(),
                ).fit(maxiter=200)
        if not getattr(result, "converged", True) or any(
            "converg" in str(w.message).lower()
            or "separation" in str(w.message).lower()
            for w in caught
        ):
            return ModelStatus(
                **shared,
                status="failed",
                reason="nonconvergence or separation",
                domain_adjustment=adjusted,
            ), ()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            intervals = result.conf_int(alpha=0.05)
            pvalues = result.pvalues
        params = result.params
        if not np.isfinite(
            np.concatenate(
                [np.asarray(params), np.asarray(intervals).ravel(), np.asarray(pvalues)]
            )
        ).all():
            return ModelStatus(
                **shared,
                status="failed",
                reason="nonfinite estimate or covariance",
                domain_adjustment=adjusted,
            ), ()
        coefficients = []
        linear = outcome in {"maximum_grade", "mean_grade"}
        scale: Scale = (
            "severity_points"
            if linear
            else "count_ratio"
            if outcome == "effect_count"
            else "odds_ratio"
        )
        for term in params.index:
            if term == "Intercept" or term.startswith("I(y>"):
                continue
            estimate, low, high = (
                float(params[term]),
                float(intervals.loc[term, 0]),
                float(intervals.loc[term, 1]),
            )
            if not linear:
                estimate, low, high = math.exp(estimate), math.exp(low), math.exp(high)
            coefficients.append(
                Coefficient(
                    outcome=outcome,
                    scope=scope,
                    compound=compound,
                    model=design,
                    term=term,
                    estimate=estimate,
                    ci_low=low,
                    ci_high=high,
                    p=float(pvalues[term]),
                    scale=scale,
                )
            )
        return ModelStatus(
            **shared,
            status="fit",
            reason="exploratory association with robust 95% confidence interval",
            domain_adjustment=adjusted,
        ), tuple(coefficients)
    except (ValueError, np.linalg.LinAlgError, OverflowError, ZeroDivisionError) as exc:
        return ModelStatus(
            **shared,
            status="failed",
            reason=f"numerical failure: {type(exc).__name__}",
            domain_adjustment=adjusted,
        ), ()


def _write_csv(
    path: Path, rows: tuple[BaseModel, ...], schema: type[BaseModel]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(schema.model_fields))
        writer.writeheader()
        writer.writerows(row.model_dump() for row in rows)


def run_models(config: RunConfig) -> Path:
    """Publish aggregate-only reconstruction artifacts; leave historical reports intact."""
    started, run_id = time.monotonic(), str(uuid4())
    output = config.output_directory.resolve()
    if output.is_relative_to(REPO_ROOT):
        raise ValueError("Model run outputs must be outside the repository")
    if not config.run_root.is_dir():
        raise ValueError("Run root does not exist")
    data = load_model_data(
        config.run_root,
        load_comparator_cohort(config.cohort_path),
        config.settings.robust_log_dose_z,
    )
    statuses: list[ModelStatus] = []
    coefficients: list[Coefficient] = []
    compounds = sorted({unit.compound for unit in data.units})
    for outcome in OUTCOMES:
        rows = observations(data.units, outcome)
        for compound in [*compounds, "all compounds"]:
            subset = (
                rows
                if compound == "all compounds"
                else tuple(row for row in rows if row.compound == compound)
            )
            for design in DESIGNS:
                status, fitted = fit_model(
                    subset, outcome, design, compound, config.settings
                )
                statuses.append(status)
                coefficients.extend(fitted)
    output.mkdir(parents=True, exist_ok=True)
    _write_csv(
        output / "severity_reconstructed_eligibility.csv",
        eligibility(data.units),
        Eligibility,
    )
    _write_csv(
        output / "severity_reconstructed_status.csv", tuple(statuses), ModelStatus
    )
    _write_csv(
        output / "severity_reconstructed_coefficients.csv",
        tuple(coefficients),
        Coefficient,
    )
    source_paths = tuple(
        REPO_ROOT / "studies" / "tropoflavin_nootropics" / name
        for name in (
            "severity_models.py",
            "severity_model_data.py",
            "severity_model_contracts.py",
            "analyze_side_effect_severity.py",
            "study_support.py",
            "comparator_support.py",
        )
    )
    manifest = ModelManifest(
        generated_at=datetime.now(UTC).isoformat(),
        settings=config.settings,
        databases=data.databases,
        exclusions=data.exclusions,
        source_code=tuple(
            SourceProvenance(
                relative_path=str(path.relative_to(REPO_ROOT).as_posix()),
                sha256=sha256_file(path),
            )
            for path in source_paths
        )
        + (
            SourceProvenance(
                relative_path="cohort configuration",
                sha256=sha256_file(config.cohort_path),
            ),
        ),
        packages=tuple(
            PackageVersion(package=package, version=version(package))
            for package in (
                "numpy",
                "pandas",
                "scipy",
                "statsmodels",
                "patsy",
                "pydantic",
            )
        ),
    )
    path = output / "severity_reconstructed_manifest.json"
    path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    logger.info(
        json.dumps(
            {
                "run_id": run_id,
                "phase": "severity_models",
                "schema_id": manifest.schema_id,
                "duration": round(time.monotonic() - started, 3),
                "status": "complete",
                "models": len(statuses),
                "fitted": sum(s.status == "fit" for s in statuses),
            }
        )
    )
    return path


@app.command()
def main(
    run_root: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    output_dir: Annotated[Path, typer.Option(file_okay=False)],
    cohort: Annotated[
        Path, typer.Option(exists=True, dir_okay=False)
    ] = DEFAULT_COHORT_CONFIG,
) -> None:
    """Fit offline associations with aggregate outputs outside the repository."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        manifest = run_models(
            RunConfig(
                run_root=run_root, output_directory=output_dir, cohort_path=cohort
            )
        )
    except (ValueError, OSError) as exc:
        # Validation errors may include raw private boundary values. Never echo them.
        console.print(
            f"[red]Analysis failed ({type(exc).__name__}). Check input schema and external output paths.[/red]"
        )
        raise typer.Exit(code=1) from None
    console.print(f"[green]Wrote aggregate model artifacts:[/green] {manifest}")


if __name__ == "__main__":
    app()
