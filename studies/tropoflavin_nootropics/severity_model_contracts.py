"""Validated inputs and aggregate artifacts for reconstructed severity models."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from studies.tropoflavin_nootropics.comparator_support import DEFAULT_COHORT_CONFIG
from studies.tropoflavin_nootropics.severity_model_data import (
    DatabaseProvenance,
    ExclusionSummary,
)

Outcome = Literal[
    "any_effect",
    "effect_count",
    "ordinal_grade",
    "maximum_grade",
    "mean_grade",
    "moderate_plus",
]
Design = Literal["dose", "route", "dose_route", "dose_route_interaction"]
Scale = Literal["odds_ratio", "count_ratio", "severity_points"]
OUTCOMES: tuple[Outcome, ...] = (
    "any_effect",
    "effect_count",
    "ordinal_grade",
    "maximum_grade",
    "mean_grade",
    "moderate_plus",
)
DESIGNS: tuple[Design, ...] = ("dose", "route", "dose_route", "dose_route_interaction")


class ModelSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    min_authors: int = Field(default=20, ge=5)
    min_route_authors: int = Field(default=5, ge=2)
    min_outcome_authors: int = Field(default=5, ge=2)
    min_interaction_cell_authors: int = Field(default=5, ge=2)
    robust_log_dose_z: float = Field(default=4.0, gt=0)


class RunConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    run_root: Path
    output_directory: Path
    cohort_path: Path = DEFAULT_COHORT_CONFIG
    settings: ModelSettings = Field(default_factory=ModelSettings)


class Observation(BaseModel):
    """Internal validated unit, never serialized to an artifact."""

    author: str
    compound: str
    outcome: float
    dose_mg: float | None
    log2_dose: float | None
    route: str | None
    domain: str = "none"


class Eligibility(BaseModel):
    compound: str
    authors: int
    any_effect_authors: int
    graded_authors: int
    graded_effects: int
    dose_authors: int
    route_authors: int
    dose_route_authors: int
    graded_dose_authors: int
    graded_route_authors: int
    graded_dose_route_authors: int


class ModelStatus(BaseModel):
    outcome: Outcome
    scope: str
    compound: str
    model: Design
    observations: int
    authors: int
    rare_route_records_excluded: int = 0
    status: Literal["fit", "not_estimable", "failed"]
    reason: str
    domain_adjustment: bool = False


class Coefficient(BaseModel):
    outcome: Outcome
    scope: str
    compound: str
    model: Design
    term: str
    estimate: float = Field(allow_inf_nan=False)
    ci_low: float = Field(allow_inf_nan=False)
    ci_high: float = Field(allow_inf_nan=False)
    p: float = Field(ge=0, le=1)
    scale: Scale


class SourceProvenance(BaseModel):
    relative_path: str
    sha256: str


class PackageVersion(BaseModel):
    package: str
    version: str


class _StatusArgs(TypedDict):
    outcome: Outcome
    scope: str
    compound: str
    model: Design
    observations: int
    authors: int
    rare_route_records_excluded: int


class ModelManifest(BaseModel):
    schema_id: str = "tropoflavin_severity_reconstruction_v1"
    generated_at: str
    reconstruction_status: str = "New implementation of saved September 3 methods; not exact historical reproduction"
    settings: ModelSettings
    confidence_level: float = 0.95
    unit: str = "Globally deduplicated author-treatment; distinct canonical effects retain maximum explicit grade across repeats"
    linkage: str = "Author-treatment linkage, not same-episode attribution"
    unknown_severity: str = "Missing, never coded zero; moderate_plus denominator is explicitly graded authors"
    dose: str = "Geometric mean of unique positive numeric mg midpoints within one original dose band; log2 mg; 7,8-DHF >=100 mg excluded from dose models"
    models: str = "Independence-working-correlation GEE with author-robust covariance: binomial occurrence/moderate+, negative-binomial count (alpha=1), proportional-odds effect grade; secondary OLS mean/max with HC3 per compound and author-clustered pooled covariance"
    pooled_adjustment: str = (
        "Compound fixed effects; assumes a common within-compound log-dose slope"
    )
    differences_from_saved_methods: tuple[str, ...] = (
        "Minimum sample uses independent authors, not effect rows",
        "Numeric dose screen is fitted among outcome-classified authors with one unambiguous original band",
        "Ordinal safety-domain adjustment is attempted only when all domains have at least five authors",
        "Every ordinal threshold and binary outcome requires at least five authors per side",
        "Interaction requires two treatment-specific dose strata per route with five authors per stratum",
        "Nonconvergence, rank deficiency, nonfinite inference and degenerate grade variation suppress estimates",
    )
    limits: tuple[str, ...] = (
        "Associations, not validated individual predictions or causal effects",
        "Any-effect zero means no mapped effect reported, not confirmed absence",
        "Only saved numeric mg midpoints are used; no milliliter conversion; upstream unit parsing is inherited and not independently re-audited",
        "Unmapped effect names collapse to the existing other reported effect category",
        "Ordinal proportional-odds assumption is not validated; linear scores assume equally spaced grades",
        "No multiplicity adjustment; intervals and p values are exploratory",
    )
    databases: tuple[DatabaseProvenance, ...]
    exclusions: tuple[ExclusionSummary, ...]
    source_code: tuple[SourceProvenance, ...]
    packages: tuple[PackageVersion, ...]
