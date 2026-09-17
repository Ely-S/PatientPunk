"""Read-only author and effect units for reconstructed severity models."""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from studies.tropoflavin_nootropics.analyze_side_effect_severity import (
    DatabaseProvenance,
    _connect,
    _discover_artifacts,
)
from studies.tropoflavin_nootropics.comparator_support import (
    ComparatorCohort,
    compound_for_treatment,
    sha256_file,
)
from studies.tropoflavin_nootropics.study_support import canonical_side_effect

Grade = Literal["mild", "moderate", "severe", "life_threatening"]
GRADE_SCORE = {"mild": 1, "moderate": 2, "severe": 3, "life_threatening": 4}


class StoredEffect(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    side_effect: str
    severity: Grade | None = None


class StoredReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    user_id: str = Field(min_length=1)
    canonical_name: str
    side_effects: str | None


class StoredExposure(BaseModel):
    model_config = ConfigDict(frozen=True)
    author_hash: str = Field(min_length=1)
    target_compound: str
    dose_band: str
    route_bucket: str
    quantitative_dose_midpoints_mg_json: str


_EFFECT_LIST = TypeAdapter(list[StoredEffect | str])
_DOSE_LIST = TypeAdapter(list[float])


class ExclusionSummary(BaseModel):
    compound: str
    numeric_dose_authors: int
    primary_dose_exclusions: int
    log2_lower_bound: float | None = None
    log2_upper_bound: float | None = None


@dataclass(frozen=True, slots=True)
class EffectUnit:
    effect: str
    domain: str
    grade: int | None


@dataclass(frozen=True, slots=True)
class AuthorUnit:
    author: str
    compound: str
    effects: tuple[EffectUnit, ...]
    dose_mg: float | None
    route: str | None
    dose_excluded: bool = False


@dataclass(slots=True)
class _Accumulator:
    effects: dict[str, EffectUnit] = field(default_factory=dict)
    doses: set[float] = field(default_factory=set)
    dose_bands: set[str] = field(default_factory=set)
    routes: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class ModelData:
    units: tuple[AuthorUnit, ...]
    databases: tuple[DatabaseProvenance, ...]
    exclusions: tuple[ExclusionSummary, ...]


def route_family(value: str) -> str | None:
    """Preserve ambiguity; an unsupported route is not an oral exposure."""
    if value in {"", "not reported"}:
        return None
    return {
        "oral mucosal": "oral",
        "swallowed oral": "oral",
        "nasal mucosal": "nasal",
    }.get(value, value)


def decode_effects(raw: str | None) -> tuple[EffectUnit, ...]:
    values = _EFFECT_LIST.validate_json(raw or "[]")
    effects = []
    for value in values:
        name = value if isinstance(value, str) else value.side_effect
        if not name.strip():
            continue
        canonical, domain = canonical_side_effect(name)
        grade = (
            None
            if isinstance(value, str) or value.severity is None
            else GRADE_SCORE[value.severity]
        )
        effects.append(EffectUnit(canonical, domain, grade))
    return tuple(effects)


def _read_database(
    connection: sqlite3.Connection,
    cohort: ComparatorCohort,
    authors: dict[tuple[str, str], _Accumulator],
    exposures: dict[tuple[str, str], _Accumulator],
) -> None:
    mapped_names: dict[str, str | None] = {}
    for raw in connection.execute(
        "SELECT user_id, canonical_name, side_effects FROM treatment_reports "
        "JOIN treatment ON treatment.id = treatment_reports.drug_id"
    ):
        report = StoredReport.model_validate(dict(raw))
        if report.canonical_name not in mapped_names:
            mapped_names[report.canonical_name] = compound_for_treatment(
                report.canonical_name, cohort
            )
        compound = mapped_names[report.canonical_name]
        if compound is None:
            continue
        slot = authors.setdefault((report.user_id, compound), _Accumulator())
        for effect in decode_effects(report.side_effects):
            previous = slot.effects.get(effect.effect)
            if previous is None or (effect.grade or 0) > (previous.grade or 0):
                slot.effects[effect.effect] = effect
    has_exposures = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='pipeline_b_compound_exposures'"
    ).fetchone()
    if not has_exposures:
        return
    for raw in connection.execute(
        "SELECT author_hash, target_compound, dose_band, route_bucket, "
        "quantitative_dose_midpoints_mg_json FROM pipeline_b_compound_exposures"
    ):
        exposure = StoredExposure.model_validate(dict(raw))
        slot = exposures.setdefault(
            (exposure.author_hash, exposure.target_compound), _Accumulator()
        )
        doses = _DOSE_LIST.validate_json(exposure.quantitative_dose_midpoints_mg_json)
        slot.doses.update(
            value for value in doses if math.isfinite(value) and value > 0
        )
        if exposure.dose_band not in {"", "not reported", "non-quantitative only"}:
            slot.dose_bands.add(exposure.dose_band)
        route = route_family(exposure.route_bucket)
        if route:
            slot.routes.add(route)


def _units(
    authors: dict[tuple[str, str], _Accumulator],
    exposures: dict[tuple[str, str], _Accumulator],
) -> tuple[AuthorUnit, ...]:
    units = []
    for (author, compound), slot in sorted(authors.items()):
        exposure = exposures.get((author, compound), _Accumulator())
        valid_band = (
            len(exposure.dose_bands) == 1
            and "multiple bands" not in exposure.dose_bands
        )
        dose = (
            math.exp(
                sum(math.log(dose) for dose in exposure.doses) / len(exposure.doses)
            )
            if exposure.doses and valid_band
            else None
        )
        route = next(iter(exposure.routes)) if len(exposure.routes) == 1 else None
        if route == "multiple route families":
            route = None
        units.append(
            AuthorUnit(author, compound, tuple(slot.effects.values()), dose, route)
        )
    return tuple(units)


def screen_doses(
    units: tuple[AuthorUnit, ...], robust_z: float = 4.0, dhf_ceiling: float = 100.0
) -> tuple[tuple[AuthorUnit, ...], tuple[ExclusionSummary, ...]]:
    """Screen numeric doses only; excluded authors still enter route-only analyses."""
    from dataclasses import replace

    grouped: dict[str, list[AuthorUnit]] = defaultdict(list)
    for unit in units:
        grouped[unit.compound].append(unit)
    summaries, screened = [], []
    for compound, members in sorted(grouped.items()):
        doses = np.array([math.log2(u.dose_mg) for u in members if u.dose_mg])
        lower, upper = None, None
        if len(doses) >= 20:
            median = float(np.median(doses))
            mad = float(np.median(np.abs(doses - median)))
            if mad > 0:
                lower = median - robust_z * 1.4826 * mad
                upper = median + robust_z * 1.4826 * mad
        exclusions = 0
        for unit in members:
            excluded = bool(
                unit.dose_mg is not None
                and (
                    (compound == "7,8-DHF" and unit.dose_mg >= dhf_ceiling - 1e-10)
                    or (lower is not None and math.log2(unit.dose_mg) < lower)
                    or (upper is not None and math.log2(unit.dose_mg) > upper)
                )
            )
            exclusions += excluded
            screened.append(replace(unit, dose_excluded=excluded))
        summaries.append(
            ExclusionSummary(
                compound=compound,
                numeric_dose_authors=len(doses),
                primary_dose_exclusions=exclusions,
                log2_lower_bound=lower,
                log2_upper_bound=upper,
            )
        )
    return tuple(screened), tuple(summaries)


def load_model_data(
    run_root: Path, cohort: ComparatorCohort, robust_z: float = 4.0
) -> ModelData:
    authors: dict[tuple[str, str], _Accumulator] = {}
    exposures: dict[tuple[str, str], _Accumulator] = {}
    provenance = []
    for artifact in _discover_artifacts(run_root):
        with closing(_connect(artifact.path)) as connection:
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Source database failed its integrity check")
            _read_database(connection, cohort, authors, exposures)
        provenance.append(
            DatabaseProvenance(
                group=artifact.group,
                community=artifact.community,
                filename=artifact.path.name,
                size_bytes=artifact.path.stat().st_size,
                sha256=sha256_file(artifact.path),
            )
        )
    units, exclusions = screen_doses(_units(authors, exposures), robust_z)
    return ModelData(units, tuple(provenance), exclusions)
