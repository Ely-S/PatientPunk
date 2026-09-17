"""Allowlisted aggregate boundaries for the frozen September 3 severity reports."""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from statistics import NormalDist
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from studies.tropoflavin_nootropics.study_support import CANONICAL_SIDE_EFFECT_LABELS

Count = Annotated[int, Field(ge=0)]
Compound = Literal[
    "4'-DMA",
    "7,8-DHF",
    "9-MBC",
    "BPC-157",
    "Cerebrolysin",
    "Dihexa",
    "Lion's mane",
    "NSI-189",
    "Selank",
    "Semax",
    "all compounds",
]


class AggregateRecord(BaseModel):
    """Reject unexpected source columns rather than silently publishing them."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def normalize_missing_values(cls, value: object) -> object:
        if isinstance(value, dict):
            return {key: None if item == "" else item for key, item in value.items()}
        return value

    @field_validator("*", mode="after")
    @classmethod
    def reject_private_or_multiline_text(cls, value: object) -> object:
        if isinstance(value, str) and re.search(
            r"[\r\n|]|https?://|(?i:[A-Z]:[\\/]|/Users/|/home/)|"
            r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])",
            value,
        ):
            raise ValueError(
                "Aggregate text contains unsupported or identifying content"
            )
        return value


class CompoundSummary(AggregateRecord):
    scope: str
    compound: Compound
    authors: Count
    authors_with_any_side_effect: Count
    any_side_effect_percent: str
    authors_with_explicit_severity: Count
    severity_coverage_of_side_effect_authors: str
    authors_with_explicit_moderate_or_worse: Count
    authors_with_explicit_severe_or_worse: Count

    @model_validator(mode="after")
    def validate_counts(self) -> CompoundSummary:
        counts = (
            self.authors,
            self.authors_with_any_side_effect,
            self.authors_with_explicit_severity,
            self.authors_with_explicit_moderate_or_worse,
            self.authors_with_explicit_severe_or_worse,
        )
        if tuple(sorted(counts, reverse=True)) != counts:
            raise ValueError("Severity counts must nest inside their denominators")
        return self


class LinearEligibility(AggregateRecord):
    compound: Compound
    explicit_severity_authors: Count
    dose_model_authors: Count
    route_model_authors: Count
    dose_and_route_model_authors: Count
    dose_and_route_routes: Count
    dose_and_route_unique_doses: Count

    @model_validator(mode="after")
    def validate_eligibility(self) -> LinearEligibility:
        if max(
            self.dose_model_authors, self.route_model_authors
        ) > self.explicit_severity_authors or self.dose_and_route_model_authors > min(
            self.dose_model_authors, self.route_model_authors
        ):
            raise ValueError("Dose/route eligibility exceeds its severity denominator")
        return self


class FineEligibility(AggregateRecord):
    compound: Compound
    classified_authors: Count
    authors_with_any_side_effect: Count
    authors_with_explicit_severity: Count
    distinct_explicitly_graded_effects: Count
    dose_linked_authors: Count
    route_linked_authors: Count
    dose_and_route_linked_authors: Count
    dose_linked_graded_effects: Count
    route_linked_graded_effects: Count
    dose_and_route_linked_graded_effects: Count

    @model_validator(mode="after")
    def validate_eligibility(self) -> FineEligibility:
        if (
            not self.authors_with_explicit_severity
            <= self.authors_with_any_side_effect
            <= self.classified_authors
        ):
            raise ValueError("Fine-grained severity counts do not nest")
        if (
            self.distinct_explicitly_graded_effects
            < self.authors_with_explicit_severity
        ):
            raise ValueError("Each graded author must have at least one graded effect")
        if self.dose_and_route_linked_authors > min(
            self.dose_linked_authors, self.route_linked_authors
        ):
            raise ValueError("Joint exposure count exceeds its exposure denominator")
        return self


class LeadingEffect(AggregateRecord):
    compound: Compound
    side_effect: str
    authors: Count
    moderate: Count
    severe: Count
    life_threatening: Count

    @field_validator("side_effect")
    @classmethod
    def require_canonical_effect(cls, value: str) -> str:
        if value not in CANONICAL_SIDE_EFFECT_LABELS:
            raise ValueError("Only canonical side-effect labels may be published")
        return value

    @model_validator(mode="after")
    def validate_grade_counts(self) -> LeadingEffect:
        if self.authors != self.moderate + self.severe + self.life_threatening:
            raise ValueError("Leading-effect grades do not total the author count")
        return self


class DoseDefinition(AggregateRecord):
    compound: Compound
    first_cut_mg: Annotated[float, Field(gt=0)]
    second_cut_mg: Annotated[float, Field(gt=0)]
    basis: str

    @model_validator(mode="after")
    def validate_cutpoints(self) -> DoseDefinition:
        if self.first_cut_mg > self.second_cut_mg:
            raise ValueError("Dose cut points must be ordered")
        return self


class BucketEstimate(AggregateRecord):
    unit: Literal["author-treatment", "distinct explicitly graded side effect"]
    dimension: Literal["dose bucket", "route", "dose bucket + route"]
    compound: Compound
    dose_bucket: str | None
    route: str | None
    observations: Count
    any_side_effect_percent: float | None
    mean_distinct_side_effect_count: float | None
    graded_authors: Count | None
    mean_maximum_severity: float | None
    maximum_95_ci_low: float | None
    maximum_95_ci_high: float | None
    mean_average_severity: float | None
    average_95_ci_low: float | None
    average_95_ci_high: float | None
    mild_effects: Count | None
    moderate_effects: Count | None
    severe_effects: Count | None
    life_threatening_effects: Count | None

    @property
    def any_side_effect_authors(self) -> int | None:
        if self.any_side_effect_percent is None:
            return None
        return round(self.any_side_effect_percent * self.observations / 100)

    @model_validator(mode="after")
    def validate_intervals(self) -> BucketEstimate:
        if self.graded_authors is not None and self.graded_authors > self.observations:
            raise ValueError("Graded-author count exceeds observations")
        if self.any_side_effect_percent is not None and (
            not 0 <= self.any_side_effect_percent <= 100
            or not math.isclose(
                self.any_side_effect_percent * self.observations / 100,
                self.any_side_effect_authors or 0,
                abs_tol=1e-6,
            )
        ):
            raise ValueError(
                "Bucket percentage does not represent an integer author count"
            )
        for mean, lower, upper in (
            (
                self.mean_maximum_severity,
                self.maximum_95_ci_low,
                self.maximum_95_ci_high,
            ),
            (
                self.mean_average_severity,
                self.average_95_ci_low,
                self.average_95_ci_high,
            ),
        ):
            if mean is not None and not 1 <= mean <= 4:
                raise ValueError("Mean severity must be on the 1-4 scale")
            if (lower is None) != (upper is None):
                raise ValueError("Both confidence limits must be supplied together")
            if (
                lower is not None
                and upper is not None
                and (mean is None or not 1 <= lower <= mean <= upper <= 4)
            ):
                raise ValueError("Descriptive severity interval is inconsistent")
        return self


class LinearStatus(AggregateRecord):
    analysis_set: str
    scope: str
    compound: Compound
    model: str
    linked_authors_before_route_filter: Count
    eligible_authors: Count
    rare_route_records_excluded: Count
    status: str
    reason: str | None


class FineStatus(AggregateRecord):
    outcome: str
    scope: str
    compound: Compound
    model: str
    observations_before_filters: Count
    eligible_observations: Count
    rare_route_records_excluded: Count
    status: str
    reason: str | None


class LinearCoefficient(AggregateRecord):
    analysis_set: str
    scope: str
    compound: Compound
    model: str
    authors: Count
    term: str
    estimate: float
    estimate_95_ci_low: float
    estimate_95_ci_high: float
    p_value: Annotated[float, Field(ge=0, le=1)]
    route_reference: str | None
    compound_reference: str | None
    r_squared: float
    adjusted_r_squared: float

    @model_validator(mode="after")
    def validate_interval(self) -> LinearCoefficient:
        if not self.estimate_95_ci_low <= self.estimate <= self.estimate_95_ci_high:
            raise ValueError("Coefficient interval does not contain its estimate")
        return self


class FineCoefficient(AggregateRecord):
    outcome: str
    scope: str
    compound: Compound
    model: str
    observations: Count
    author_clusters: Count
    term: str
    scale: str
    estimate: float
    estimate_95_ci_low: float
    estimate_95_ci_high: float
    p_value: Annotated[float, Field(ge=0, le=1)]
    route_reference: str | None
    compound_reference: str | None
    safety_bucket_reference: str | None

    @model_validator(mode="after")
    def validate_interval(self) -> FineCoefficient:
        if not self.estimate_95_ci_low <= self.estimate <= self.estimate_95_ci_high:
            raise ValueError("Coefficient interval does not contain its estimate")
        return self


class ModerateCoefficient(AggregateRecord):
    compound: Compound
    outcome: str
    analysis_population: str
    model: str
    term: str
    authors: Count
    moderate_or_worse_authors: Count
    odds_ratio: float
    odds_ratio_95_ci_low: float
    odds_ratio_95_ci_high: float
    p_value: Annotated[float, Field(ge=0, le=1)]
    route_reference: str | None

    @model_validator(mode="after")
    def validate_interval(self) -> ModerateCoefficient:
        if (
            not 0
            <= self.odds_ratio_95_ci_low
            <= self.odds_ratio
            <= self.odds_ratio_95_ci_high
        ):
            raise ValueError("Odds-ratio interval does not contain its estimate")
        if self.moderate_or_worse_authors > self.authors:
            raise ValueError("Moderate+ count exceeds its author denominator")
        return self


class ModerateCell(AggregateRecord):
    compound: Compound
    dose_bucket: str
    route: str
    graded_authors: Count
    moderate_or_worse_numerator: Count
    moderate_or_worse_denominator: Count
    moderate_or_worse_rate: float
    moderate_or_worse_95_ci_low: float
    moderate_or_worse_95_ci_high: float

    @model_validator(mode="after")
    def validate_rate(self) -> ModerateCell:
        numerator, denominator = (
            self.moderate_or_worse_numerator,
            self.moderate_or_worse_denominator,
        )
        lower, upper = wilson_interval(numerator, denominator)
        if self.graded_authors != denominator or not all(
            (
                math.isclose(
                    self.moderate_or_worse_rate, numerator / denominator, abs_tol=1e-10
                ),
                math.isclose(self.moderate_or_worse_95_ci_low, lower, abs_tol=1e-6),
                math.isclose(self.moderate_or_worse_95_ci_high, upper, abs_tol=1e-6),
            )
        ):
            raise ValueError("Saved moderate-or-worse cell fails Wilson/count checks")
        return self


class MeanPrediction(AggregateRecord):
    scope: str
    model: str
    compound: Compound
    dose_bucket: str | None
    route: str | None
    authors: Count
    median_dose_mg: float | None
    observed_mean_max_severity: float
    observed_mean_95_ci_low: float | None
    observed_mean_95_ci_high: float | None
    adjusted_predicted_mean: float
    adjusted_mean_95_ci_low: float
    adjusted_mean_95_ci_high: float

    @model_validator(mode="after")
    def validate_adjusted_limits(self) -> MeanPrediction:
        if (
            not self.adjusted_mean_95_ci_low
            <= self.adjusted_predicted_mean
            <= self.adjusted_mean_95_ci_high
        ):
            raise ValueError("Predicted-mean interval does not contain its estimate")
        return self


class SeverityPrediction(AggregateRecord):
    scope: str
    model: str
    compound: Compound
    dose_bucket: str | None
    route: str | None
    observed_effects_in_stratum: Count
    authors_in_stratum: Count
    representative_dose_mg: float | None
    moderate_or_worse_probability: float
    moderate_or_worse_95_ci_low: float
    moderate_or_worse_95_ci_high: float
    severe_or_worse_probability: float
    severe_or_worse_95_ci_low: float
    severe_or_worse_95_ci_high: float
    mild_probability: float
    mild_95_ci_low: float
    mild_95_ci_high: float
    moderate_probability: float
    moderate_95_ci_low: float
    moderate_95_ci_high: float
    severe_probability: float
    severe_95_ci_low: float
    severe_95_ci_high: float
    life_threatening_probability: float
    life_threatening_95_ci_low: float
    life_threatening_95_ci_high: float

    @model_validator(mode="after")
    def validate_probabilities(self) -> SeverityPrediction:
        levels = ("mild", "moderate", "severe", "life_threatening")
        for level in (*levels, "moderate_or_worse", "severe_or_worse"):
            if (
                not 0
                <= getattr(self, f"{level}_95_ci_low")
                <= getattr(self, f"{level}_probability")
                <= getattr(self, f"{level}_95_ci_high")
                <= 1
            ):
                raise ValueError("Probability interval is inconsistent")
        if not math.isclose(
            sum(getattr(self, f"{level}_probability") for level in levels),
            1,
            abs_tol=1e-6,
        ):
            raise ValueError("Severity probabilities must total one")
        return self


class DatabaseDigest(AggregateRecord):
    community: str
    filename: Literal["combined.db", "sentiment.db"]
    size_bytes: Count
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class FrozenModelManifest(AggregateRecord):
    schema_id: Literal["tropoflavin_side_effect_fine_grained_models_v1"]
    generated_at: str
    author_unit: str
    effect_unit: str
    occurrence_model: str
    burden_model: str
    severity_model: str
    summary_models: str
    dose_definition: str
    route_definition: str
    confidence_interval: str
    min_model_n: Count
    min_route_level_n: Count
    min_interaction_cell_n: Count
    robust_log_dose_z: float
    exclude_78dhf_at_or_above_mg: float
    databases: tuple[DatabaseDigest, ...]


def read_aggregate_csv[Record: AggregateRecord](
    path: Path, model: type[Record]
) -> tuple[Record, ...]:
    """Check the full header, including duplicate/empty columns, before parsing rows."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        if len(header) != len(set(header)) or set(header) != set(model.model_fields):
            raise ValueError(f"Unexpected aggregate schema in {path.name}")
        records: list[Record] = []
        for number, row in enumerate(reader, start=2):
            try:
                records.append(model.model_validate(row))
            except ValidationError as exc:
                raise ValueError(
                    f"Invalid aggregate row in {path.name}:{number}; content withheld"
                ) from exc
        return tuple(records)


def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    """Two-sided 95% binomial Wilson limits, for independent author proportions."""
    if total <= 0 or not 0 <= successes <= total:
        raise ValueError(
            "Wilson intervals require 0 <= successes <= total and total > 0"
        )
    z = NormalDist().inv_cdf(0.975)
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    half = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total**2))
        / denominator
    )
    return max(0.0, center - half), min(1.0, center + half)
