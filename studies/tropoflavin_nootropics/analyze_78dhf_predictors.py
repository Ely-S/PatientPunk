"""Analyze dose, route, and treatment-target associations for 7,8-DHF."""

from __future__ import annotations

import json
import math
import re
import sqlite3
import statistics
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Sequence

import typer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from rich.console import Console
from scipy.stats import chi2, fisher_exact
from statsmodels.stats.multitest import multipletests

from studies.tropoflavin_nootropics.comparator_support import (
    DEFAULT_COHORT_CONFIG,
    ComparatorCohort,
    load_comparator_cohort,
    markdown_escape,
    sha256_file,
)
from studies.tropoflavin_nootropics.study_support import dose_band

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()

Sentiment = Literal["positive", "negative", "mixed", "neutral"]
Predictor = Literal["dose", "route", "reason"]
ReasonCategory = Literal[
    "anxiety or stress",
    "sleep or wakefulness",
    "mood or depression",
    "focus or attention",
    "memory or learning",
    "cognition or brain fog",
    "energy or motivation",
    "neuroprotection or recovery",
    "pain or neurologic symptoms",
    "stimulant recovery or reduction",
    "cardiovascular or autonomic",
    "hair or skin",
    "gastrointestinal",
    "social functioning",
    "sexual function",
    "other explicit reason",
]
_AUTHOR_HASH = re.compile(r"^[0-9a-f]{32}$")
_SIGNAL_RANK = {"strong": 3, "moderate": 2, "weak": 1, "n/a": 0, None: 0}
_SENTIMENT_SCORE: dict[Sentiment, float] = {
    "negative": -1.0,
    "mixed": 0.0,
    "neutral": 0.0,
    "positive": 1.0,
}
_TARGET_COMPOUND = "7,8-DHF"


class ReasonRecord(BaseModel):
    """One private, author-level result from the dedicated reason extractor."""

    model_config = ConfigDict(frozen=True)

    schema_id: str = "tropoflavin_78dhf_reason_record_v1"
    subreddit: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_]+$")
    author_hash: str = Field(pattern=r"^[0-9a-f]{32}$")
    explicit_reason_found: bool
    reasons: tuple[ReasonCategory, ...]
    source_report_count: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_reasons(self) -> ReasonRecord:
        if self.explicit_reason_found != bool(self.reasons):
            raise ValueError("explicit_reason_found must match whether reasons exist")
        if len(self.reasons) != len(set(self.reasons)):
            raise ValueError("Reason categories must be unique")
        return self


class ReasonUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    requests: int = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class ReasonManifestSummary(BaseModel):
    """Fields required to verify and describe the private reason extraction."""

    model_config = ConfigDict(frozen=True)

    provider: str
    model: str
    code_commit: str
    prompt_file: str
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    max_text_chars: int = Field(ge=1)
    max_output_tokens: int = Field(ge=1)
    batch_size: int = Field(ge=1)
    source_author_cohorts: int = Field(ge=0)
    completed_author_cohorts: int = Field(ge=0)
    explicit_reason_author_cohorts: int = Field(ge=0)
    missing_author_cohorts: int = Field(ge=0)
    records_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    usage: ReasonUsage
    completed_at: str


class CohortInput(BaseModel):
    """One external combined study database."""

    model_config = ConfigDict(frozen=True)

    subreddit: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_]+$")
    database: Path

    @model_validator(mode="after")
    def validate_database(self) -> CohortInput:
        if not self.database.is_file():
            raise ValueError(f"Study database not found: {self.database}")
        return self


class PredictorAnalysisConfig(BaseModel):
    """Validated configuration for the focused predictor analysis."""

    model_config = ConfigDict(frozen=True)

    cohorts: tuple[CohortInput, ...] = Field(min_length=2)
    cohort_path: Path = DEFAULT_COHORT_CONFIG
    reason_records: Path
    reason_manifest: Path
    output_path: Path
    minimum_baseline_authors: int = Field(default=10, ge=2)
    minimum_inference_authors: int = Field(default=10, ge=2)

    @model_validator(mode="after")
    def validate_inputs(self) -> PredictorAnalysisConfig:
        if not self.cohort_path.is_file():
            raise ValueError(f"Comparator cohort not found: {self.cohort_path}")
        if not self.reason_records.is_file():
            raise ValueError(f"Reason records not found: {self.reason_records}")
        if not self.reason_manifest.is_file():
            raise ValueError(f"Reason manifest not found: {self.reason_manifest}")
        names = [cohort.subreddit.casefold() for cohort in self.cohorts]
        if len(names) != len(set(names)):
            raise ValueError("Subreddit cohorts must be unique")
        paths = [cohort.database.resolve() for cohort in self.cohorts]
        if len(paths) != len(set(paths)):
            raise ValueError("Each subreddit must use a separate database")
        return self


@dataclass(frozen=True)
class Vote:
    author_hash: str
    subreddit: str
    compound_slug: str
    report_id: int
    post_id: str
    sentiment: Sentiment
    signal: str | None
    post_date: int
    run_id: int

    @property
    def positive(self) -> bool:
        return self.sentiment == "positive"

    @property
    def score(self) -> float:
        return _SENTIMENT_SCORE[self.sentiment]


@dataclass(frozen=True)
class TargetAuthor:
    author_hash: str
    subreddit: str
    vote: Vote
    side_effects: frozenset[str]
    dose_bands: frozenset[str]
    route_buckets: frozenset[str]
    reasons: frozenset[str]

    @property
    def any_side_effect(self) -> bool:
        return bool(self.side_effects)

    @property
    def dose_category(self) -> str | None:
        if len(self.dose_bands) == 1:
            return next(iter(self.dose_bands))
        if len(self.dose_bands) > 1:
            return "multiple dose bands"
        return None

    @property
    def route_category(self) -> str | None:
        if len(self.route_buckets) == 1:
            return next(iter(self.route_buckets))
        if len(self.route_buckets) > 1:
            return "multiple route families"
        return None


@dataclass(frozen=True)
class CohortDataset:
    subreddit: str
    database: Path
    votes: dict[str, dict[str, Vote]]
    target_authors: dict[str, TargetAuthor]


@dataclass(frozen=True)
class CompoundMetric:
    slug: str
    display_name: str
    authors: int
    positive_rate: float
    mean_score: float
    eligible: bool


@dataclass(frozen=True)
class CrossCompoundBaseline:
    metrics: tuple[CompoundMetric, ...]
    mean_positive_rate: float | None
    mean_score: float | None
    score_sd: float | None

    @property
    def eligible_compounds(self) -> int:
        return sum(metric.eligible for metric in self.metrics)


@dataclass(frozen=True)
class GroupSummary:
    category: str
    authors: int
    positive: int
    positive_rate: float
    positive_ci: tuple[float, float]
    normalized_positive_points: float | None
    community_normalized_points: float | None
    mean_sentiment_score: float
    standardized_sentiment: float | None
    side_effect_authors: int
    side_effect_rate: float
    side_effect_ci: tuple[float, float]
    leading_side_effects: tuple[tuple[str, int], ...]
    positive_odds_ratio: float | None
    positive_p: float | None
    positive_q: float | None
    side_effect_odds_ratio: float | None
    side_effect_p: float | None
    side_effect_q: float | None
    adjusted_positive_odds_ratio: float | None
    adjusted_positive_p: float | None
    adjusted_side_effect_odds_ratio: float | None
    adjusted_side_effect_p: float | None
    comparison_authors: int
    status: str


def _connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _vote_rank(vote: Vote) -> tuple[int, int, int, str, str]:
    return (
        vote.post_date,
        _SIGNAL_RANK.get(vote.signal, 0),
        vote.run_id,
        vote.post_id,
        vote.subreddit.casefold(),
    )


def _valid_author(value: object) -> str | None:
    author = str(value or "").strip().lower()
    return author if _AUTHOR_HASH.fullmatch(author) else None


def _load_votes(
    connection: sqlite3.Connection,
    subreddit: str,
    cohort: ComparatorCohort,
) -> dict[str, dict[str, Vote]]:
    canonical_to_slug = {
        compound.canonical_name.casefold(): compound.slug
        for compound in cohort.compounds
    }
    rows = connection.execute(
        """
        SELECT tr.report_id, tr.user_id, lower(t.canonical_name) AS drug,
               tr.post_id, tr.sentiment, tr.signal_strength,
               COALESCE(p.post_date, 0) AS post_date, tr.run_id
        FROM treatment_reports tr
        JOIN treatment t ON t.id = tr.drug_id
        JOIN posts p ON p.post_id = tr.post_id
        """
    ).fetchall()
    latest_per_post: dict[tuple[str, str, str], Vote] = {}
    for row in rows:
        author = _valid_author(row["user_id"])
        slug = canonical_to_slug.get(str(row["drug"]).casefold())
        sentiment = str(row["sentiment"])
        if author is None or slug is None or sentiment not in _SENTIMENT_SCORE:
            continue
        vote = Vote(
            author_hash=author,
            subreddit=subreddit,
            compound_slug=slug,
            report_id=int(row["report_id"]),
            post_id=str(row["post_id"]),
            sentiment=sentiment,  # type: ignore[arg-type]
            signal=str(row["signal_strength"]) if row["signal_strength"] else None,
            post_date=int(row["post_date"] or 0),
            run_id=int(row["run_id"]),
        )
        key = (author, slug, vote.post_id)
        previous = latest_per_post.get(key)
        if previous is None or vote.run_id > previous.run_id:
            latest_per_post[key] = vote

    by_compound: dict[str, dict[str, Vote]] = defaultdict(dict)
    for vote in latest_per_post.values():
        previous = by_compound[vote.compound_slug].get(vote.author_hash)
        if previous is None or _vote_rank(vote) > _vote_rank(previous):
            by_compound[vote.compound_slug][vote.author_hash] = vote
    return dict(by_compound)


def _load_side_effects(
    connection: sqlite3.Connection,
    target_canonical_name: str,
) -> dict[str, set[str]]:
    effects: dict[str, set[str]] = defaultdict(set)
    rows = connection.execute(
        """
        SELECT tr.user_id, se.canonical_side_effect
        FROM pipeline_a_side_effects se
        JOIN treatment_reports tr ON tr.report_id = se.report_id
        JOIN treatment t ON t.id = tr.drug_id
        WHERE lower(t.canonical_name) = ?
        """,
        (target_canonical_name.casefold(),),
    ).fetchall()
    for row in rows:
        author = _valid_author(row["user_id"])
        effect = str(row["canonical_side_effect"] or "").strip()
        if author and effect:
            effects[author].add(effect)
    return effects


def _json_strings(value: object) -> set[str]:
    try:
        decoded = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return set()
    if not isinstance(decoded, list):
        return set()
    return {str(item).strip() for item in decoded if str(item).strip()}


def _json_numbers(value: object) -> tuple[float, ...]:
    try:
        decoded = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return ()
    if not isinstance(decoded, list):
        return ()
    numbers: list[float] = []
    for item in decoded:
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number) and number >= 0:
            numbers.append(number)
    return tuple(numbers)


def _load_exposure_predictors(
    connection: sqlite3.Connection,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    doses: dict[str, set[str]] = defaultdict(set)
    routes: dict[str, set[str]] = defaultdict(set)
    exposure_rows = connection.execute(
        """
        SELECT author_hash, quantitative_dose_midpoints_mg_json,
               route_buckets_json
        FROM pipeline_b_compound_exposures
        WHERE target_compound = ?
        """,
        (_TARGET_COMPOUND,),
    ).fetchall()
    for row in exposure_rows:
        author = _valid_author(row["author_hash"])
        if author is None:
            continue
        doses[author].update(
            dose_band(midpoint).label
            for midpoint in _json_numbers(row["quantitative_dose_midpoints_mg_json"])
        )
        routes[author].update(_json_strings(row["route_buckets_json"]))
    return doses, routes


def load_reason_records(path: Path) -> dict[tuple[str, str], ReasonRecord]:
    """Load private reason records without exposing their author identifiers."""
    records: dict[tuple[str, str], ReasonRecord] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = ReasonRecord.model_validate_json(line)
        except ValueError as exc:
            raise ValueError(f"Invalid reason record at line {line_number}") from exc
        key = (record.subreddit.casefold(), record.author_hash)
        if key in records:
            raise ValueError(f"Duplicate reason record at line {line_number}")
        records[key] = record
    return records


def load_cohort_dataset(
    cohort_input: CohortInput,
    cohort: ComparatorCohort,
    reason_records: dict[tuple[str, str], ReasonRecord],
) -> CohortDataset:
    """Load aggregate author features from one read-only study database."""
    with closing(_connect_readonly(cohort_input.database)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(
                f"Database integrity check failed for {cohort_input.database.name}: "
                f"{integrity}"
            )
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError(
                f"Foreign-key check failed for {cohort_input.database.name}"
            )
        votes = _load_votes(connection, cohort_input.subreddit, cohort)
        effects = _load_side_effects(
            connection,
            cohort.by_slug()[cohort.target_slug].canonical_name,
        )
        doses, routes = _load_exposure_predictors(connection)

    target_votes = votes.get(cohort.target_slug, {})
    target_authors = {
        author: TargetAuthor(
            author_hash=author,
            subreddit=cohort_input.subreddit,
            vote=vote,
            side_effects=frozenset(effects.get(author, set())),
            dose_bands=frozenset(doses.get(author, set())),
            route_buckets=frozenset(routes.get(author, set())),
            reasons=frozenset(
                reason_records[(cohort_input.subreddit.casefold(), author)].reasons
                if (cohort_input.subreddit.casefold(), author) in reason_records
                else ()
            ),
        )
        for author, vote in target_votes.items()
    }
    return CohortDataset(
        subreddit=cohort_input.subreddit,
        database=cohort_input.database,
        votes=votes,
        target_authors=target_authors,
    )


def cross_compound_baseline(
    votes: dict[str, dict[str, Vote]],
    cohort: ComparatorCohort,
    minimum_authors: int,
) -> CrossCompoundBaseline:
    """Calculate an equal-compound-weight, leave-target-out sentiment baseline."""
    metrics: list[CompoundMetric] = []
    for compound in cohort.compounds:
        compound_votes = tuple(votes.get(compound.slug, {}).values())
        authors = len(compound_votes)
        positive_rate = (
            sum(vote.positive for vote in compound_votes) / authors if authors else 0.0
        )
        mean_score = (
            statistics.fmean(vote.score for vote in compound_votes)
            if authors
            else 0.0
        )
        metrics.append(
            CompoundMetric(
                slug=compound.slug,
                display_name=compound.display_name,
                authors=authors,
                positive_rate=positive_rate,
                mean_score=mean_score,
                eligible=(
                    compound.slug != cohort.target_slug
                    and authors >= minimum_authors
                ),
            )
        )
    eligible = [metric for metric in metrics if metric.eligible]
    if not eligible:
        return CrossCompoundBaseline(tuple(metrics), None, None, None)
    mean_positive = statistics.fmean(metric.positive_rate for metric in eligible)
    mean_score = statistics.fmean(metric.mean_score for metric in eligible)
    score_sd = (
        statistics.stdev(metric.mean_score for metric in eligible)
        if len(eligible) >= 2
        else None
    )
    return CrossCompoundBaseline(
        metrics=tuple(metrics),
        mean_positive_rate=mean_positive,
        mean_score=mean_score,
        score_sd=score_sd,
    )


def merge_datasets(
    datasets: tuple[CohortDataset, ...],
    cohort: ComparatorCohort,
) -> CohortDataset:
    """Globally deduplicate authors while retaining all reported predictors."""
    global_votes: dict[str, dict[str, Vote]] = defaultdict(dict)
    target_features: dict[str, list[TargetAuthor]] = defaultdict(list)
    for dataset in datasets:
        for slug, votes in dataset.votes.items():
            for author, vote in votes.items():
                previous = global_votes[slug].get(author)
                if previous is None or _vote_rank(vote) > _vote_rank(previous):
                    global_votes[slug][author] = vote
        for author, target in dataset.target_authors.items():
            target_features[author].append(target)

    merged_targets: dict[str, TargetAuthor] = {}
    for author, features in target_features.items():
        selected_vote = global_votes[cohort.target_slug][author]
        merged_targets[author] = TargetAuthor(
            author_hash=author,
            subreddit=selected_vote.subreddit,
            vote=selected_vote,
            side_effects=frozenset(
                effect for feature in features for effect in feature.side_effects
            ),
            dose_bands=frozenset(
                band for feature in features for band in feature.dose_bands
            ),
            route_buckets=frozenset(
                route for feature in features for route in feature.route_buckets
            ),
            reasons=frozenset(
                reason for feature in features for reason in feature.reasons
            ),
        )
    return CohortDataset(
        subreddit="Globally deduplicated",
        database=Path("combined external cohort databases"),
        votes={slug: dict(votes) for slug, votes in global_votes.items()},
        target_authors=merged_targets,
    )


def _wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    proportion = successes / total
    denominator = 1 + z**2 / total
    center = (proportion + z**2 / (2 * total)) / denominator
    margin = z * math.sqrt(
        (proportion * (1 - proportion) + z**2 / (4 * total)) / total
    ) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def _fisher(
    selected: tuple[TargetAuthor, ...],
    comparison: tuple[TargetAuthor, ...],
    outcome: Literal["positive", "side_effect"],
) -> tuple[float | None, float | None]:
    if not selected or not comparison:
        return None, None
    selected_successes = sum(
        author.vote.positive if outcome == "positive" else author.any_side_effect
        for author in selected
    )
    comparison_successes = sum(
        author.vote.positive if outcome == "positive" else author.any_side_effect
        for author in comparison
    )
    result = fisher_exact(
        [
            [selected_successes, len(selected) - selected_successes],
            [comparison_successes, len(comparison) - comparison_successes],
        ]
    )
    return float(result.statistic), float(result.pvalue)


def _stratified(
    selected: tuple[TargetAuthor, ...],
    comparison: tuple[TargetAuthor, ...],
    outcome: Literal["positive", "side_effect"],
) -> tuple[float | None, float | None]:
    numerator = 0.0
    denominator = 0.0
    observed_minus_expected = 0.0
    variance = 0.0
    names = sorted(
        {author.subreddit for author in selected}
        | {author.subreddit for author in comparison}
    )
    for name in names:
        selected_rows = tuple(row for row in selected if row.subreddit == name)
        comparison_rows = tuple(row for row in comparison if row.subreddit == name)
        if not selected_rows or not comparison_rows:
            continue
        selected_successes = sum(
            row.vote.positive if outcome == "positive" else row.any_side_effect
            for row in selected_rows
        )
        comparison_successes = sum(
            row.vote.positive if outcome == "positive" else row.any_side_effect
            for row in comparison_rows
        )
        a = selected_successes
        b = len(selected_rows) - selected_successes
        c = comparison_successes
        d = len(comparison_rows) - comparison_successes
        total = a + b + c + d
        if total <= 1:
            continue
        numerator += a * d / total
        denominator += b * c / total
        selected_total = a + b
        comparison_total = c + d
        success_total = a + c
        failure_total = b + d
        expected = selected_total * success_total / total
        stratum_variance = (
            selected_total
            * comparison_total
            * success_total
            * failure_total
            / (total**2 * (total - 1))
        )
        observed_minus_expected += a - expected
        variance += stratum_variance
    if numerator == 0 and denominator == 0:
        return None, None
    odds_ratio = numerator / denominator if denominator else math.inf
    p_value = (
        float(chi2.sf(observed_minus_expected**2 / variance, df=1))
        if variance > 0
        else None
    )
    return odds_ratio, p_value


def _categories(
    authors: tuple[TargetAuthor, ...],
    predictor: Predictor,
) -> tuple[str, ...]:
    if predictor == "dose":
        return tuple(
            sorted(
                {
                    author.dose_category
                    for author in authors
                    if author.dose_category is not None
                },
                key=lambda value: (
                    value == "multiple dose bands",
                    next(
                        (
                            dose_band(midpoint).order
                            for midpoint in (0.0, 5.0, 10.0, 25.0, 50.0, 100.0)
                            if dose_band(midpoint).label == value
                        ),
                        99,
                    ),
                    value,
                ),
            )
        )
    if predictor == "route":
        return tuple(
            sorted(
                {
                    author.route_category
                    for author in authors
                    if author.route_category is not None
                }
            )
        )
    return tuple(sorted({reason for author in authors for reason in author.reasons}))


def _has_category(author: TargetAuthor, predictor: Predictor, category: str) -> bool:
    if predictor == "dose":
        return author.dose_category == category
    if predictor == "route":
        return author.route_category == category
    return category in author.reasons


def _valid_comparison_author(author: TargetAuthor, predictor: Predictor) -> bool:
    if predictor == "dose":
        return author.dose_category not in (None, "multiple dose bands")
    if predictor == "route":
        return author.route_category not in (None, "multiple route families")
    return bool(author.reasons)


def summarize_predictor(
    authors: tuple[TargetAuthor, ...],
    predictor: Predictor,
    baseline: CrossCompoundBaseline,
    minimum_inference_authors: int,
    community_baselines: dict[str, CrossCompoundBaseline] | None = None,
    adjust_for_subreddit: bool = False,
) -> tuple[GroupSummary, ...]:
    """Summarize one predictor against sentiment and side-effect outcomes."""
    categories = _categories(authors, predictor)
    summaries: list[GroupSummary] = []
    for category in categories:
        selected = tuple(
            author for author in authors if _has_category(author, predictor, category)
        )
        comparison_pool = tuple(
            author
            for author in authors
            if _valid_comparison_author(author, predictor)
            and not _has_category(author, predictor, category)
        )
        positive = sum(author.vote.positive for author in selected)
        side_effect_authors = sum(author.any_side_effect for author in selected)
        positive_rate = positive / len(selected)
        side_effect_rate = side_effect_authors / len(selected)
        mean_score = statistics.fmean(author.vote.score for author in selected)
        normalized_points = (
            100 * (positive_rate - baseline.mean_positive_rate)
            if baseline.mean_positive_rate is not None
            else None
        )
        standardized = (
            (mean_score - baseline.mean_score) / baseline.score_sd
            if baseline.mean_score is not None
            and baseline.score_sd is not None
            and baseline.score_sd > 0
            else None
        )
        community_deltas = []
        for author in selected:
            author_baseline = (
                community_baselines.get(author.subreddit)
                if community_baselines
                else None
            )
            if author_baseline and author_baseline.mean_positive_rate is not None:
                community_deltas.append(
                    float(author.vote.positive) - author_baseline.mean_positive_rate
                )
        community_points = (
            100 * statistics.fmean(community_deltas) if community_deltas else None
        )
        positive_or, positive_p = _fisher(selected, comparison_pool, "positive")
        side_effect_or, side_effect_p = _fisher(
            selected, comparison_pool, "side_effect"
        )
        adjusted_positive_or, adjusted_positive_p = (
            _stratified(selected, comparison_pool, "positive")
            if adjust_for_subreddit
            else (None, None)
        )
        adjusted_side_effect_or, adjusted_side_effect_p = (
            _stratified(selected, comparison_pool, "side_effect")
            if adjust_for_subreddit
            else (None, None)
        )
        effect_counts = Counter(
            effect for author in selected for effect in author.side_effects
        )
        ambiguous = category in {"multiple dose bands", "multiple route families"}
        if ambiguous:
            status = "descriptive only; multiple reported values"
        elif min(len(selected), len(comparison_pool)) < minimum_inference_authors:
            status = "too sparse for inference"
        else:
            status = "estimable association; not causal"
        summaries.append(
            GroupSummary(
                category=category,
                authors=len(selected),
                positive=positive,
                positive_rate=positive_rate,
                positive_ci=_wilson(positive, len(selected)),
                normalized_positive_points=normalized_points,
                community_normalized_points=community_points,
                mean_sentiment_score=mean_score,
                standardized_sentiment=standardized,
                side_effect_authors=side_effect_authors,
                side_effect_rate=side_effect_rate,
                side_effect_ci=_wilson(side_effect_authors, len(selected)),
                leading_side_effects=tuple(effect_counts.most_common(3)),
                positive_odds_ratio=positive_or,
                positive_p=positive_p,
                positive_q=None,
                side_effect_odds_ratio=side_effect_or,
                side_effect_p=side_effect_p,
                side_effect_q=None,
                adjusted_positive_odds_ratio=adjusted_positive_or,
                adjusted_positive_p=adjusted_positive_p,
                adjusted_side_effect_odds_ratio=adjusted_side_effect_or,
                adjusted_side_effect_p=adjusted_side_effect_p,
                comparison_authors=len(comparison_pool),
                status=status,
            )
        )

    for outcome in ("positive", "side_effect"):
        eligible_indexes = [
            index
            for index, summary in enumerate(summaries)
            if summary.status == "estimable association; not causal"
            and (
                summary.positive_p if outcome == "positive" else summary.side_effect_p
            )
            is not None
        ]
        p_values = [
            (
                summaries[index].positive_p
                if outcome == "positive"
                else summaries[index].side_effect_p
            )
            for index in eligible_indexes
        ]
        if not p_values:
            continue
        q_values = multipletests(p_values, method="fdr_bh")[1]
        for index, q_value in zip(eligible_indexes, q_values, strict=True):
            if outcome == "positive":
                summaries[index] = replace(
                    summaries[index], positive_q=float(q_value)
                )
            else:
                summaries[index] = replace(
                    summaries[index], side_effect_q=float(q_value)
                )
    return tuple(summaries)


def _table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    rendered = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    rendered.extend(
        "| " + " | ".join(markdown_escape(str(value)) for value in row) + " |"
        for row in rows
    )
    return "\n".join(rendered)


def _percent(value: float) -> str:
    return f"{100 * value:.1f}%"


def _optional_number(value: float | None, digits: int = 2) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{value:.{digits}f}"


def _odds_ratio(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "n/a"
    if math.isinf(value):
        return "inf"
    return f"{value:.2f}"


def _effects(summary: GroupSummary) -> str:
    if not summary.leading_side_effects:
        return "none mapped"
    return "; ".join(
        f"{label}: {count}/{summary.authors} ({_percent(count / summary.authors)})"
        for label, count in summary.leading_side_effects
    )


def _summary_tables(
    summaries: tuple[GroupSummary, ...],
    combined: bool,
) -> str:
    if not summaries:
        return "No eligible 7,8-DHF authors had this predictor extracted."
    outcome_headers = [
        "Level",
        "Authors",
        "Positive",
        "Positive share",
        "Versus compound mean",
    ]
    if combined:
        outcome_headers.append("Community-standardized")
    outcome_headers.extend(
        ["Sentiment z", "Any side effect", "Leading mapped effects", "Status"]
    )
    outcome_rows: list[list[object]] = []
    contrast_rows: list[list[object]] = []
    for summary in summaries:
        row: list[object] = [
            summary.category,
            summary.authors,
            f"{summary.positive}/{summary.authors}",
            (
                f"{_percent(summary.positive_rate)} "
                f"({_percent(summary.positive_ci[0])} to "
                f"{_percent(summary.positive_ci[1])})"
            ),
            (
                f"{summary.normalized_positive_points:+.1f} points"
                if summary.normalized_positive_points is not None
                else "n/a"
            ),
        ]
        if combined:
            row.append(
                f"{summary.community_normalized_points:+.1f} points"
                if summary.community_normalized_points is not None
                else "n/a"
            )
        row.extend(
            [
                _optional_number(summary.standardized_sentiment),
                (
                    f"{summary.side_effect_authors}/{summary.authors} "
                    f"({_percent(summary.side_effect_rate)}; "
                    f"{_percent(summary.side_effect_ci[0])} to "
                    f"{_percent(summary.side_effect_ci[1])})"
                ),
                _effects(summary),
                summary.status,
            ]
        )
        outcome_rows.append(row)
        contrast_row: list[object] = [
            summary.category,
            summary.comparison_authors,
            _odds_ratio(summary.positive_odds_ratio),
            _optional_number(summary.positive_p, 4),
            _optional_number(summary.positive_q, 4),
            _odds_ratio(summary.side_effect_odds_ratio),
            _optional_number(summary.side_effect_p, 4),
            _optional_number(summary.side_effect_q, 4),
        ]
        if combined:
            contrast_row.extend(
                [
                    _odds_ratio(summary.adjusted_positive_odds_ratio),
                    _optional_number(summary.adjusted_positive_p, 4),
                    _odds_ratio(summary.adjusted_side_effect_odds_ratio),
                    _optional_number(summary.adjusted_side_effect_p, 4),
                ]
            )
        contrast_rows.append(contrast_row)
    contrast_headers = [
        "Level",
        "Other eligible authors",
        "Positive OR",
        "Positive p",
        "Positive BH q",
        "Side-effect OR",
        "Side-effect p",
        "Side-effect BH q",
    ]
    if combined:
        contrast_headers.extend(
            [
                "Subreddit-adjusted positive OR",
                "Adjusted p",
                "Subreddit-adjusted side-effect OR",
                "Adjusted SE p",
            ]
        )
    return (
        _table(outcome_headers, outcome_rows)
        + "\n\nContrast each level with all other eligible levels for that predictor. "
        "Reason levels are multi-label, so the comparison is reason present versus "
        "reason absent among authors with at least one explicit reason.\n\n"
        + _table(contrast_headers, contrast_rows)
    )


def _overall_row(
    name: str,
    dataset: CohortDataset,
    baseline: CrossCompoundBaseline,
) -> list[object]:
    authors = tuple(dataset.target_authors.values())
    positive = sum(author.vote.positive for author in authors)
    effects = sum(author.any_side_effect for author in authors)
    single_dose = sum(
        author.dose_category not in (None, "multiple dose bands")
        for author in authors
    )
    single_route = sum(
        author.route_category not in (None, "multiple route families")
        for author in authors
    )
    reasons = sum(bool(author.reasons) for author in authors)
    rate = positive / len(authors) if authors else 0.0
    normalized = (
        100 * (rate - baseline.mean_positive_rate)
        if authors and baseline.mean_positive_rate is not None
        else None
    )
    return [
        name,
        len(authors),
        f"{positive}/{len(authors)} ({_percent(rate)})" if authors else "0/0",
        effects,
        single_dose,
        single_route,
        reasons,
        baseline.eligible_compounds,
        (
            _percent(baseline.mean_positive_rate)
            if baseline.mean_positive_rate is not None
            else "n/a"
        ),
        f"{normalized:+.1f} points" if normalized is not None else "n/a",
    ]


def render_predictor_report(config: PredictorAnalysisConfig) -> str:
    """Render the privacy-safe separate and globally deduplicated analysis."""
    cohort = load_comparator_cohort(config.cohort_path)
    reason_records = load_reason_records(config.reason_records)
    reason_manifest = ReasonManifestSummary.model_validate_json(
        config.reason_manifest.read_text(encoding="utf-8")
    )
    if reason_manifest.provider != "openrouter":
        raise ValueError("Reason extraction provenance is not OpenRouter")
    if reason_manifest.missing_author_cohorts:
        raise ValueError("Reason extraction manifest is incomplete")
    if sha256_file(config.reason_records) != reason_manifest.records_sha256:
        raise ValueError("Reason records do not match their manifest hash")
    if len(reason_records) != reason_manifest.completed_author_cohorts:
        raise ValueError("Reason record count does not match its manifest")
    if (
        sum(record.explicit_reason_found for record in reason_records.values())
        != reason_manifest.explicit_reason_author_cohorts
    ):
        raise ValueError("Explicit-reason count does not match its manifest")
    datasets = tuple(
        load_cohort_dataset(cohort_input, cohort, reason_records)
        for cohort_input in config.cohorts
    )
    baselines = {
        dataset.subreddit: cross_compound_baseline(
            dataset.votes, cohort, config.minimum_baseline_authors
        )
        for dataset in datasets
    }
    merged = merge_datasets(datasets, cohort)
    global_baseline = cross_compound_baseline(
        merged.votes, cohort, config.minimum_baseline_authors
    )

    coverage_rows: list[list[object]] = [
        _overall_row(dataset.subreddit, dataset, baselines[dataset.subreddit])
        for dataset in datasets
    ]
    coverage_rows.append(_overall_row("Combined, deduplicated", merged, global_baseline))

    sections = [
        "# 7,8-DHF dose, route, reason, sentiment, and side-effect analysis",
        (
            "This focused analysis treats dose, administration route, and a "
            "an explicit reason for use as predictors. Outcomes are author-level "
            "sentiment and whether the author ever reported at least one mapped "
            "7,8-DHF side effect. It is observational and estimates reporting "
            "associations, not efficacy, incidence, causation, or a dose-response "
            "relationship."
        ),
        (
            "## Cross-compound normalization\n\n"
            "Normalization is between compounds. Within each subreddit, the "
            "baseline is the unweighted mean of the author-level positive rates "
            "for the other nine compounds that have at least "
            f"{config.minimum_baseline_authors} authors. 7,8-DHF is excluded. "
            "Giving each eligible compound one vote prevents high-volume compounds "
            "from defining the mean. `Versus compound mean` is the 7,8-DHF subgroup "
            "positive rate minus that baseline in percentage points. `Sentiment z` "
            "uses negative = -1, mixed/neutral = 0, and positive = +1, then expresses "
            "the subgroup mean relative to the mean and standard deviation across "
            "eligible comparator-compound means. This z-score is a sensitivity "
            "analysis because sentiment categories are not a validated interval scale."
        ),
        (
            "## Explicit reason for use\n\n"
            "Reason categories come from a dedicated extraction pass over retained "
            "7,8-DHF report text. The extractor records only a directly stated purpose "
            "or indication. It does not infer a reason from a reported benefit, adverse "
            "effect, mechanism discussion, or another compound. Authors may explicitly "
            "state more than one reason."
        ),
        "## Coverage\n\n"
        + _table(
            [
                "Cohort",
                "7,8-DHF authors",
                "Positive",
                "Any mapped side effect",
                "Single dose band",
                "Single route",
                "Explicit reason",
                "Baseline compounds",
                "Comparator mean positive",
                "7,8-DHF versus mean",
            ],
            coverage_rows,
        ),
    ]

    global_metric_rows = [
        [
            metric.display_name,
            metric.authors,
            _percent(metric.positive_rate),
            f"{metric.mean_score:+.3f}",
            "yes" if metric.eligible else "no",
        ]
        for metric in global_baseline.metrics
    ]
    sections.append(
        "## Combined cross-compound baseline\n\n"
        + _table(
            [
                "Compound",
                "Globally distinct authors",
                "Positive share",
                "Mean sentiment score",
                "In comparator mean",
            ],
            global_metric_rows,
        )
    )

    sections.append(
        "## Combined analysis, globally deduplicated\n\n"
        "Only identifiable hashed authors are included, and each contributes once. "
        "When an author appears in multiple cohorts, "
        "the latest 7,8-DHF sentiment report is selected and their dose, route, reason, "
        "and mapped side-effect sets are combined. `Community-standardized` subtracts "
        "the selected report's subreddit-specific cross-compound mean before averaging. "
        "The Mantel-Haenszel odds ratios are stratified by that selected subreddit."
    )
    merged_authors = tuple(merged.target_authors.values())
    for predictor, label in (
        ("dose", "Dosage"),
        ("route", "Administration route"),
        ("reason", "Explicit reason for use"),
    ):
        summaries = summarize_predictor(
            merged_authors,
            predictor,  # type: ignore[arg-type]
            global_baseline,
            config.minimum_inference_authors,
            community_baselines=baselines,
            adjust_for_subreddit=True,
        )
        sections.append(
            f"### Combined: {label}\n\n" + _summary_tables(summaries, combined=True)
        )

    sections.append("## Separate subreddit analyses")
    for dataset in datasets:
        baseline = baselines[dataset.subreddit]
        authors = tuple(dataset.target_authors.values())
        target_positive = sum(author.vote.positive for author in authors)
        target_rate = target_positive / len(authors) if authors else 0.0
        sections.append(
            f"### r/{dataset.subreddit}\n\n"
            + (
                f"7,8-DHF has {len(authors)} classified authors and a raw positive "
                f"share of {_percent(target_rate)}. The leave-target-out comparator "
                f"mean uses {baseline.eligible_compounds} compounds and is "
                f"{_percent(baseline.mean_positive_rate)}."
                if authors and baseline.mean_positive_rate is not None
                else "No 7,8-DHF author-level outcome is available for this cohort."
            )
        )
        for predictor, label in (
            ("dose", "Dosage"),
            ("route", "Administration route"),
            ("reason", "Explicit reason for use"),
        ):
            summaries = summarize_predictor(
                authors,
                predictor,  # type: ignore[arg-type]
                baseline,
                config.minimum_inference_authors,
                community_baselines={dataset.subreddit: baseline},
            )
            sections.append(
                f"#### {label}\n\n" + _summary_tables(summaries, combined=False)
            )

    source_rows = [
        [
            cohort_input.subreddit,
            cohort_input.database.name,
            sha256_file(cohort_input.database),
        ]
        for cohort_input in config.cohorts
    ]
    sections.extend(
        [
            (
                "## Interpretation boundaries\n\n"
                "Dose and route values are included only when the value and 7,8-DHF "
                "were found near each other in the same source segment, but the "
                "author-level sentiment and side-effect outcomes may come from another "
                "report by that author. Multi-band and multi-route histories are "
                "descriptive only. Reasons are multi-label. Concomitant drugs, "
                "formulation, duration, year, community selection, indication severity, "
                "and reporting behavior can confound every association. Sparse rows "
                "should not be interpreted inferentially."
            ),
            "## Reproducibility\n\n"
            + f"Generated at `{datetime.now(UTC).isoformat()}`. Dose, route, sentiment, "
            "and side-effect inputs are the external combined databases from the "
            "completed subreddit runs. Reason records and their model provenance remain "
            "external. No record-level text or author identifier is included.\n\n"
            + _table(["Subreddit", "Database", "SHA-256"], source_rows)
            + "\n\n"
            + _table(
                ["Reason artifact", "SHA-256"],
                [
                    [config.reason_records.name, sha256_file(config.reason_records)],
                    [config.reason_manifest.name, sha256_file(config.reason_manifest)],
                ],
            )
            + "\n\n"
            + (
                f"Reason extraction: provider `{reason_manifest.provider}`; model "
                f"`{reason_manifest.model}`; code commit `{reason_manifest.code_commit}`; "
                f"prompt `{reason_manifest.prompt_file}` with SHA-256 "
                f"`{reason_manifest.prompt_sha256}`; {reason_manifest.max_text_chars:,} "
                "input characters per author cohort; "
                f"{reason_manifest.max_output_tokens:,} output-token ceiling; batch size "
                f"{reason_manifest.batch_size}; completed "
                f"{reason_manifest.completed_author_cohorts:,}/"
                f"{reason_manifest.source_author_cohorts:,} author cohorts; "
                f"{reason_manifest.explicit_reason_author_cohorts:,} with an explicit "
                f"reason; {reason_manifest.usage.total_tokens:,} provider-reported "
                f"tokens; completed at `{reason_manifest.completed_at}`."
            ),
        ]
    )
    return "\n\n".join(sections) + "\n"


def analyze_predictors(config: PredictorAnalysisConfig) -> str:
    """Write the focused aggregate report."""
    report = render_predictor_report(config)
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(report, encoding="utf-8")
    return report


@app.command()
def main(
    config_path: Path = typer.Option(..., exists=True, dir_okay=False),
    output: Path = typer.Option(..., dir_okay=False),
) -> None:
    """Generate the focused 7,8-DHF predictor analysis."""
    config = PredictorAnalysisConfig.model_validate_json(
        config_path.read_text(encoding="utf-8")
    )
    analyze_predictors(config.model_copy(update={"output_path": output}))
    console.print(f"[green]Wrote[/green] {output}")


if __name__ == "__main__":
    app()
