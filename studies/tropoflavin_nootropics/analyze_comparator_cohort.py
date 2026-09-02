"""Generate the aggregate comparator, safety, dose, and symptom report."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from contextlib import closing
from pathlib import Path
from typing import Any, Literal, TypedDict

import typer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from rich.console import Console
from scipy.stats import binomtest, fisher_exact
from statsmodels.stats.multitest import multipletests

from studies.tropoflavin_nootropics.attribution import corroborated_masses
from studies.tropoflavin_nootropics.comparator_support import (
    DEFAULT_COHORT_CONFIG,
    ComparatorCohort,
    analysis_compound_name,
    load_comparator_cohort,
    markdown_escape,
    sha256_file,
)
from studies.tropoflavin_nootropics.study_support import canonical_side_effect, dose_band

console = Console()
app = typer.Typer(add_completion=False, no_args_is_help=True)

SIGNAL_RANK = {"strong": 3, "moderate": 2, "weak": 1, "n/a": 0, None: 0}
SENTIMENTS = ("positive", "negative", "mixed", "neutral")
class ComparatorAnalysisConfig(BaseModel):
    """Validated inputs for the aggregate analysis."""

    model_config = ConfigDict(frozen=True)

    subreddit: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_]+$")
    sentiment_database: Path
    study_database: Path | None = None
    cohort_path: Path = DEFAULT_COHORT_CONFIG
    output_path: Path
    require_corroborated_attribution: bool = False
    corpus_manifest: Path | None = None
    sentiment_manifest: Path | None = None
    variable_corpus_manifest: Path | None = None
    variable_pipeline_manifest: Path | None = None

    @model_validator(mode="after")
    def validate_inputs(self) -> ComparatorAnalysisConfig:
        for label, path in (
            ("sentiment database", self.sentiment_database),
            ("cohort", self.cohort_path),
        ):
            if not path.is_file():
                raise ValueError(f"{label} does not exist: {path}")
        if self.study_database is not None and not self.study_database.is_file():
            raise ValueError(f"study database does not exist: {self.study_database}")
        for label, optional_path in (
            ("corpus manifest", self.corpus_manifest),
            ("sentiment manifest", self.sentiment_manifest),
            ("variable corpus manifest", self.variable_corpus_manifest),
            ("variable pipeline manifest", self.variable_pipeline_manifest),
        ):
            if optional_path is not None and not optional_path.is_file():
                raise ValueError(f"{label} does not exist: {optional_path}")
        return self


class CorpusMatchEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    matching_items: int = Field(ge=0)
    distinct_authors: int = Field(ge=0)


class CorpusEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    subreddit: str
    comments_sha256: str
    posts_sha256: str
    author_hash_algorithm: str
    matches: tuple[CorpusMatchEvidence, ...]


class SentimentResultEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    reports: int = Field(ge=0)
    authors: int = Field(ge=0)


class SentimentRunEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    subreddit: str
    provider: str
    model_fast: str
    model_strong: str
    code_commit: str
    max_upstream_chars: int = Field(ge=0)
    usage: dict[str, int]
    results: tuple[SentimentResultEvidence, ...]


class VariableCorpusEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    subreddit: str
    selected_authors: int = Field(ge=0)
    text_segments: int = Field(ge=0)


class VariableRunEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    subreddit: str
    provider: str
    model: str
    code_commit: str | None
    max_text_chars: int = Field(ge=1)
    max_output_tokens: int = Field(default=8192, ge=1)
    record_count: int = Field(ge=0)
    missing_author_records: int = Field(default=0, ge=0)
    status: Literal["complete", "incomplete"] = "complete"
    usage: dict[str, int]


class Vote(TypedDict):
    user_id: str
    drug: str
    post_id: str
    sentiment: str
    signal: str
    post_date: int
    run_id: int


class SentimentSummary(BaseModel):
    """One-vote-per-author outcome summary."""

    model_config = ConfigDict(frozen=True)

    slug: str
    users: int = Field(ge=0)
    positive: int = Field(ge=0)
    negative: int = Field(ge=0)
    mixed: int = Field(ge=0)
    neutral: int = Field(ge=0)
    positive_rate: float = Field(ge=0, le=1)
    ci_low: float = Field(ge=0, le=1)
    ci_high: float = Field(ge=0, le=1)


class ComparatorResult(BaseModel):
    """Mutually exclusive and matched comparison against the target compound."""

    model_config = ConfigDict(frozen=True)

    slug: str
    odds_ratio: float
    p_value: float = Field(ge=0, le=1)
    q_value: float = Field(ge=0, le=1)
    rate_difference: float
    exclusive_target_authors: int = Field(ge=0)
    exclusive_comparator_authors: int = Field(ge=0)
    matched_authors: int = Field(ge=0)
    target_only_positive: int = Field(ge=0)
    comparator_only_positive: int = Field(ge=0)
    matched_p_value: float | None = Field(default=None, ge=0, le=1)
    matched_q_value: float | None = Field(default=None, ge=0, le=1)


class SideEffectSummary(BaseModel):
    """Treatment-linked, author-deduplicated side-effect count."""

    model_config = ConfigDict(frozen=True)

    slug: str
    canonical_side_effect: str
    safety_domain: str
    users: int = Field(ge=0)
    mentions: int = Field(ge=0)


class CanonicalSideEffectRecord(BaseModel):
    """One internally normalized, treatment-linked side-effect record."""

    model_config = ConfigDict(frozen=True)

    slug: str
    user_id: str
    canonical_side_effect: str
    safety_domain: str


class LeadingEffectSummary(BaseModel):
    """Author-deduplicated effect within one dose or route stratum."""

    model_config = ConfigDict(frozen=True)

    canonical_side_effect: str
    authors: int = Field(ge=1)


class StratifiedSideEffectSummary(BaseModel):
    """Cross-report side-effect coverage for one dose or route bucket."""

    model_config = ConfigDict(frozen=True)

    compound: str
    bucket: str
    observations: int = Field(ge=1)
    authors: int = Field(ge=1)
    classified_authors: int = Field(ge=0)
    side_effect_authors: int = Field(ge=0)
    side_effect_rate: float = Field(ge=0, le=1)
    ci_low: float = Field(ge=0, le=1)
    ci_high: float = Field(ge=0, le=1)
    leading_effects: tuple[LeadingEffectSummary, ...] = ()

    @model_validator(mode="after")
    def validate_author_counts(self) -> StratifiedSideEffectSummary:
        if self.classified_authors > self.authors:
            raise ValueError("classified authors exceed stratum authors")
        if self.side_effect_authors > self.classified_authors:
            raise ValueError("side-effect authors exceed classified authors")
        return self


class PostDoseSummary(BaseModel):
    """Same-report compound, dose, sentiment, and side-effect summary."""

    model_config = ConfigDict(frozen=True)

    slug: str
    dose_band: str
    dose_band_order: int = Field(ge=1)
    posts: int = Field(ge=1)
    authors: int = Field(ge=1)
    positive_authors: int = Field(ge=0)
    side_effect_authors: int = Field(ge=0)


def _connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


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


def _load_votes(
    connection: sqlite3.Connection,
    cohort: ComparatorCohort,
) -> dict[str, dict[str, Vote]]:
    canonical_to_slug = {
        compound.canonical_name.lower(): compound.slug for compound in cohort.compounds
    }
    rows = connection.execute(
        """
        SELECT tr.user_id, lower(t.canonical_name) AS drug, tr.post_id,
               tr.sentiment, tr.signal_strength, COALESCE(p.post_date, 0) AS post_date,
               tr.run_id
        FROM treatment_reports tr
        JOIN treatment t ON t.id = tr.drug_id
        JOIN posts p ON p.post_id = tr.post_id
        """
    ).fetchall()

    latest_classification: dict[tuple[str, str, str], Vote] = {}
    for row in rows:
        slug = canonical_to_slug.get(row["drug"])
        if slug is None or not row["user_id"]:
            continue
        vote = Vote(
            user_id=row["user_id"],
            drug=slug,
            post_id=row["post_id"],
            sentiment=row["sentiment"],
            signal=row["signal_strength"],
            post_date=int(row["post_date"] or 0),
            run_id=int(row["run_id"]),
        )
        key = (vote["user_id"], slug, vote["post_id"])
        existing = latest_classification.get(key)
        if existing is None or vote["run_id"] > existing["run_id"]:
            latest_classification[key] = vote

    by_author: dict[str, dict[str, Vote]] = defaultdict(dict)
    for vote in latest_classification.values():
        existing = by_author[vote["drug"]].get(vote["user_id"])
        rank = (vote["post_date"], SIGNAL_RANK.get(vote["signal"], 0), vote["run_id"])
        if existing is None:
            by_author[vote["drug"]][vote["user_id"]] = vote
            continue
        existing_rank = (
            existing["post_date"],
            SIGNAL_RANK.get(existing["signal"], 0),
            existing["run_id"],
        )
        if rank > existing_rank:
            by_author[vote["drug"]][vote["user_id"]] = vote
    return by_author


def _sentiment_summaries(
    cohort: ComparatorCohort,
    votes: dict[str, dict[str, Vote]],
) -> dict[str, SentimentSummary]:
    summaries: dict[str, SentimentSummary] = {}
    for compound in cohort.compounds:
        compound_votes = list(votes.get(compound.slug, {}).values())
        counts = {
            sentiment: sum(vote["sentiment"] == sentiment for vote in compound_votes)
            for sentiment in SENTIMENTS
        }
        users = len(compound_votes)
        ci_low, ci_high = _wilson(counts["positive"], users)
        summaries[compound.slug] = SentimentSummary(
            slug=compound.slug,
            users=users,
            positive=counts["positive"],
            negative=counts["negative"],
            mixed=counts["mixed"],
            neutral=counts["neutral"],
            positive_rate=counts["positive"] / users if users else 0.0,
            ci_low=ci_low,
            ci_high=ci_high,
        )
    return summaries


def _post_level_dose_summaries(
    connection: sqlite3.Connection,
    cohort: ComparatorCohort,
) -> tuple[PostDoseSummary, ...]:
    """Summarize reports with one unambiguous nearby dose in the same post."""
    canonical_to_compound = {
        compound.canonical_name.casefold(): compound for compound in cohort.compounds
    }
    rows = connection.execute(
        """
        SELECT tr.user_id, tr.post_id, tr.sentiment, tr.signal_strength,
               tr.side_effects, tr.run_id, lower(t.canonical_name) AS drug,
               COALESCE(p.title, '') AS title, p.body_text,
               COALESCE(p.post_date, 0) AS post_date
        FROM treatment_reports tr
        JOIN treatment t ON t.id = tr.drug_id
        JOIN posts p ON p.post_id = tr.post_id
        WHERE tr.user_id IS NOT NULL
        """
    ).fetchall()
    latest: dict[tuple[str, str], sqlite3.Row] = {}
    for row in rows:
        compound = canonical_to_compound.get(row["drug"])
        if compound is None:
            continue
        key = (compound.slug, row["post_id"])
        existing = latest.get(key)
        if existing is None or row["run_id"] > existing["run_id"]:
            latest[key] = row

    posts: dict[tuple[str, str], set[str]] = defaultdict(set)
    votes: dict[tuple[str, str], dict[str, Vote]] = defaultdict(dict)
    side_effect_authors: dict[tuple[str, str], set[str]] = defaultdict(set)
    orders: dict[tuple[str, str], int] = {}
    for (slug, _post_id), row in latest.items():
        compound = cohort.by_slug()[slug]
        text = f"{row['title']} {row['body_text']}".strip()
        masses = corroborated_masses(compound, (text,))
        if len(masses) != 1:
            continue
        band = dose_band(masses[0].midpoint_mg)
        key = (slug, band.label)
        orders[key] = band.order
        posts[key].add(row["post_id"])
        vote = Vote(
            user_id=row["user_id"],
            drug=slug,
            post_id=row["post_id"],
            sentiment=row["sentiment"],
            signal=row["signal_strength"],
            post_date=int(row["post_date"]),
            run_id=int(row["run_id"]),
        )
        existing_vote = votes[key].get(vote["user_id"])
        rank = (vote["post_date"], SIGNAL_RANK.get(vote["signal"], 0), vote["run_id"])
        if existing_vote is None:
            votes[key][vote["user_id"]] = vote
        else:
            existing_rank = (
                existing_vote["post_date"],
                SIGNAL_RANK.get(existing_vote["signal"], 0),
                existing_vote["run_id"],
            )
            if rank > existing_rank:
                votes[key][vote["user_id"]] = vote
        try:
            effects = json.loads(row["side_effects"] or "[]")
        except json.JSONDecodeError:
            effects = []
        if isinstance(effects, list) and effects:
            side_effect_authors[key].add(row["user_id"])

    return tuple(
        PostDoseSummary(
            slug=slug,
            dose_band=band,
            dose_band_order=orders[(slug, band)],
            posts=len(posts[(slug, band)]),
            authors=len(author_votes),
            positive_authors=sum(
                vote["sentiment"] == "positive" for vote in author_votes.values()
            ),
            side_effect_authors=len(side_effect_authors[(slug, band)]),
        )
        for (slug, band), author_votes in sorted(
            votes.items(), key=lambda item: (item[0][0], orders[item[0]], item[0][1])
        )
    )


def _comparisons(
    cohort: ComparatorCohort,
    votes: dict[str, dict[str, Vote]],
    summaries: dict[str, SentimentSummary],
) -> tuple[ComparatorResult, ...]:
    target_slug = cohort.target_slug
    target = summaries[target_slug]
    target_votes = votes.get(target_slug, {})
    provisional: list[dict[str, Any]] = []
    for compound in cohort.compounds:
        if compound.slug == target_slug:
            continue
        comparator = summaries[compound.slug]
        comparator_votes = votes.get(compound.slug, {})
        matched = set(target_votes) & set(comparator_votes)
        exclusive_target = set(target_votes) - matched
        exclusive_comparator = set(comparator_votes) - matched
        target_positive = sum(
            target_votes[user]["sentiment"] == "positive" for user in exclusive_target
        )
        comparator_positive = sum(
            comparator_votes[user]["sentiment"] == "positive"
            for user in exclusive_comparator
        )
        if exclusive_target and exclusive_comparator:
            odds_ratio, p_value = fisher_exact(
                [
                    [target_positive, len(exclusive_target) - target_positive],
                    [
                        comparator_positive,
                        len(exclusive_comparator) - comparator_positive,
                    ],
                ]
            )
        else:
            odds_ratio, p_value = math.nan, 1.0

        target_only_positive = sum(
            target_votes[user]["sentiment"] == "positive"
            and comparator_votes[user]["sentiment"] != "positive"
            for user in matched
        )
        comparator_only_positive = sum(
            target_votes[user]["sentiment"] != "positive"
            and comparator_votes[user]["sentiment"] == "positive"
            for user in matched
        )
        discordant = target_only_positive + comparator_only_positive
        matched_p = (
            float(binomtest(target_only_positive, discordant, 0.5).pvalue)
            if discordant
            else None
        )
        provisional.append(
            {
                "slug": compound.slug,
                "odds_ratio": float(odds_ratio),
                "p_value": float(p_value),
                "rate_difference": target.positive_rate - comparator.positive_rate,
                "exclusive_target_authors": len(exclusive_target),
                "exclusive_comparator_authors": len(exclusive_comparator),
                "matched_authors": len(matched),
                "target_only_positive": target_only_positive,
                "comparator_only_positive": comparator_only_positive,
                "matched_p_value": matched_p,
            }
        )

    q_values = multipletests(
        [row["p_value"] for row in provisional], method="fdr_bh"
    )[1]
    matched_q_values = multipletests(
        [row["matched_p_value"] or 1.0 for row in provisional], method="fdr_bh"
    )[1]
    return tuple(
        ComparatorResult(
            **row,
            q_value=float(q_value),
            matched_q_value=(
                float(matched_q_value)
                if row["matched_p_value"] is not None
                else None
            ),
        )
        for row, q_value, matched_q_value in zip(
            provisional, q_values, matched_q_values, strict=True
        )
    )


def _canonical_side_effect_records(
    connection: sqlite3.Connection,
    cohort: ComparatorCohort,
) -> tuple[CanonicalSideEffectRecord, ...]:
    canonical_to_slug = {
        compound.canonical_name.lower(): compound.slug for compound in cohort.compounds
    }
    rows = connection.execute(
        """
        SELECT tr.report_id, tr.run_id, tr.post_id, tr.user_id,
               lower(t.canonical_name) AS drug, tr.side_effects
        FROM treatment_reports tr
        JOIN treatment t ON t.id = tr.drug_id
        WHERE tr.side_effects IS NOT NULL AND tr.side_effects != '[]'
        """
    ).fetchall()
    latest: dict[tuple[str, str], sqlite3.Row] = {}
    for row in rows:
        slug = canonical_to_slug.get(row["drug"])
        if slug is None:
            continue
        key = (row["post_id"], slug)
        if key not in latest or row["run_id"] > latest[key]["run_id"]:
            latest[key] = row

    records: list[CanonicalSideEffectRecord] = []
    for (_, slug), row in latest.items():
        try:
            values = json.loads(row["side_effects"] or "[]")
        except json.JSONDecodeError:
            continue
        if not isinstance(values, list):
            continue
        for raw_value in values:
            canonical, domain = canonical_side_effect(str(raw_value))
            if row["user_id"]:
                records.append(
                    CanonicalSideEffectRecord(
                        slug=slug,
                        user_id=row["user_id"],
                        canonical_side_effect=canonical,
                        safety_domain=domain,
                    )
                )
    return tuple(records)


def _side_effects(
    records: tuple[CanonicalSideEffectRecord, ...],
) -> tuple[SideEffectSummary, ...]:
    mentions: dict[tuple[str, str, str], int] = defaultdict(int)
    authors: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for record in records:
        key = (
            record.slug,
            record.canonical_side_effect,
            record.safety_domain,
        )
        mentions[key] += 1
        authors[key].add(record.user_id)
    return tuple(
        SideEffectSummary(
            slug=slug,
            canonical_side_effect=canonical,
            safety_domain=domain,
            users=len(authors[(slug, canonical, domain)]),
            mentions=count,
        )
        for (slug, canonical, domain), count in sorted(
            mentions.items(), key=lambda item: (item[0][0], -len(authors[item[0]]), item[0][1])
        )
    )


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    rendered = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    rendered.extend(
        "| " + " | ".join(markdown_escape(str(value)) for value in row) + " |"
        for row in rows
    )
    return "\n".join(rendered)


def _percent(value: float) -> str:
    return f"{100 * value:.1f}%"


def _stratified_side_effects(
    connection: sqlite3.Connection,
    *,
    table: str,
    bucket_column: str,
    order_column: str,
    classified_authors: dict[str, set[str]],
    side_effect_records: tuple[CanonicalSideEffectRecord, ...],
    treatment_to_slug: dict[str, str],
    require_corroborated: bool,
) -> tuple[StratifiedSideEffectSummary, ...]:
    """Summarize author-level side-effect reporting within dose or route strata."""
    allowed = {
        (
            "pipeline_b_dosages",
            "dose_band",
            "dose_band_order",
        ),
        (
            "pipeline_b_administration_routes",
            "route_bucket",
            "route_bucket",
        ),
    }
    if (table, bucket_column, order_column) not in allowed:
        raise ValueError("Unsupported side-effect stratum")

    authors_by_bucket: dict[tuple[str, str], set[str]] = defaultdict(set)
    observations: dict[tuple[str, str], int] = defaultdict(int)
    order_by_bucket: dict[tuple[str, str], int | str] = {}
    attribution_filter = (
        " AND attribution_status = 'corroborated'" if require_corroborated else ""
    )
    rows = connection.execute(
        f"""
        SELECT author_hash, target_compound, {bucket_column}, {order_column}
        FROM {table}
        WHERE target_compound IS NOT NULL AND {bucket_column} IS NOT NULL
        {attribution_filter}
        """
    ).fetchall()
    for row in rows:
        if row["target_compound"] not in treatment_to_slug:
            continue
        key = (row["target_compound"], row[bucket_column])
        authors_by_bucket[key].add(row["author_hash"])
        observations[key] += 1
        order_by_bucket[key] = row[order_column]

    any_side_effect_authors: dict[str, set[str]] = defaultdict(set)
    mapped_effect_authors: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for record in side_effect_records:
        any_side_effect_authors[record.slug].add(record.user_id)
        if record.safety_domain != "other":
            mapped_effect_authors[record.slug][record.canonical_side_effect].add(
                record.user_id
            )

    summaries: list[StratifiedSideEffectSummary] = []
    for (compound, bucket), authors in authors_by_bucket.items():
        slug = treatment_to_slug[compound]
        side_effect_authors = authors & any_side_effect_authors.get(slug, set())
        covered_authors = authors & classified_authors.get(slug, set())
        effect_counts = sorted(
            (
                len(authors & effect_authors),
                canonical_effect,
            )
            for canonical_effect, effect_authors in mapped_effect_authors.get(
                slug, {}
            ).items()
            if authors & effect_authors
        )
        effect_counts.sort(key=lambda item: (-item[0], item[1]))
        ci_low, ci_high = _wilson(len(side_effect_authors), len(authors))
        summaries.append(
            StratifiedSideEffectSummary(
                compound=compound,
                bucket=bucket,
                observations=observations[(compound, bucket)],
                authors=len(authors),
                classified_authors=len(covered_authors),
                side_effect_authors=len(side_effect_authors),
                side_effect_rate=len(side_effect_authors) / len(authors),
                ci_low=ci_low,
                ci_high=ci_high,
                leading_effects=tuple(
                    LeadingEffectSummary(
                        canonical_side_effect=canonical_effect,
                        authors=count,
                    )
                    for count, canonical_effect in effect_counts[:3]
                ),
            )
        )

    return tuple(
        sorted(
            summaries,
            key=lambda summary: (
                summary.compound,
                order_by_bucket[(summary.compound, summary.bucket)]
                if order_by_bucket[(summary.compound, summary.bucket)] is not None
                else -1,
                summary.bucket,
            ),
        )
    )


def _stratified_rows(
    summaries: tuple[StratifiedSideEffectSummary, ...],
) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for summary in summaries:
        leading = "; ".join(
            f"{effect.canonical_side_effect}: {effect.authors}/{summary.authors} "
            f"({_percent(effect.authors / summary.authors)})"
            for effect in summary.leading_effects
        ) or "none mapped"
        rows.append(
            [
                summary.compound,
                summary.bucket,
                summary.observations,
                summary.authors,
                f"{summary.classified_authors}/{summary.authors}",
                (
                    f"{summary.side_effect_authors}/{summary.authors} "
                    f"({_percent(summary.side_effect_rate)}; 95% CI "
                    f"{_percent(summary.ci_low)} to {_percent(summary.ci_high)})"
                ),
                leading,
            ]
        )
    return rows


def _study_sections(
    path: Path | None,
    *,
    classified_authors: dict[str, set[str]],
    side_effect_records: tuple[CanonicalSideEffectRecord, ...],
    cohort: ComparatorCohort,
    require_corroborated: bool,
) -> str:
    if path is None:
        return ""
    with closing(_connect_readonly(path)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        required = {
            "pipeline_b_dosages",
            "pipeline_b_administration_routes",
            "pipeline_b_treatment_outcomes",
        }
        if not required <= tables:
            raise ValueError(
                f"Study database is missing tables: {sorted(required - tables)}"
            )
        treatment_to_slug = {
            analysis_compound_name(compound): compound.slug
            for compound in cohort.compounds
        }
        if require_corroborated:
            for table in ("pipeline_b_dosages", "pipeline_b_administration_routes"):
                columns = {
                    row[1] for row in connection.execute(f"PRAGMA table_info({table})")
                }
                if "attribution_status" not in columns:
                    raise ValueError(
                        f"{table} cannot enforce source corroboration because it lacks "
                        "attribution_status"
                    )
        dose_summaries = _stratified_side_effects(
            connection,
            table="pipeline_b_dosages",
            bucket_column="dose_band",
            order_column="dose_band_order",
            classified_authors=classified_authors,
            side_effect_records=side_effect_records,
            treatment_to_slug=treatment_to_slug,
            require_corroborated=require_corroborated,
        )
        route_summaries = _stratified_side_effects(
            connection,
            table="pipeline_b_administration_routes",
            bucket_column="route_bucket",
            order_column="route_bucket",
            classified_authors=classified_authors,
            side_effect_records=side_effect_records,
            treatment_to_slug=treatment_to_slug,
            require_corroborated=require_corroborated,
        )
        outcome_rows = connection.execute(
            """
            SELECT target_compound, desired_result_bucket,
                   COUNT(DISTINCT author_hash),
                   SUM(outcome = 'helped'), SUM(outcome = 'no_effect'),
                   SUM(outcome = 'worsened')
            FROM pipeline_b_treatment_outcomes
            WHERE target_compound IS NOT NULL AND desired_result_bucket != 'unspecified'
            GROUP BY target_compound, desired_result_bucket
            ORDER BY target_compound, COUNT(DISTINCT author_hash) DESC
            """
        ).fetchall()
        outcome_coverage = dict(
            connection.execute(
                """
                SELECT desired_result_bucket, COUNT(*)
                FROM pipeline_b_treatment_outcomes
                WHERE target_compound IS NOT NULL
                  AND desired_result_bucket != 'unspecified'
                GROUP BY desired_result_bucket
                """
            ).fetchall()
        )
        attribution_rows: list[list[object]] = []
        if require_corroborated:
            for label, table in (
                ("Dose", "pipeline_b_dosages"),
                ("Route", "pipeline_b_administration_routes"),
            ):
                attribution_rows.extend(
                    [label, status, count]
                    for status, count in connection.execute(
                        f"""
                        SELECT attribution_status, COUNT(*)
                        FROM {table}
                        WHERE target_compound IS NOT NULL
                        GROUP BY attribution_status
                        ORDER BY attribution_status
                        """
                    ).fetchall()
                )

    pem_entries = int(outcome_coverage.get("post-exertional malaise", 0))
    pem_note = (
        f"Explicit PEM target coverage: {pem_entries} treatment-linked outcome "
        f"{'entry' if pem_entries == 1 else 'entries'}. General fatigue remains a "
        "separate endpoint bucket."
    )
    stratification_note = (
        "Side-effect reporting is joined by hashed author and compound across all "
        "of that author's reports. The denominator is every distinct author in the "
        "dose or route bucket. Classifier coverage shows how many denominator authors "
        "also had a retained comparator report. These are cross-report associations, "
        "not administration-event links, incidence estimates, or dose-response evidence."
    )
    if require_corroborated:
        stratification_note += (
            " Dose and route rows are included only when the extracted value and "
            "compound were found near each other in the same source segment."
        )

    return "\n\n".join(
        [
            (
                "## Dose and route attribution checks\n\n"
                + _table(["Field", "Status", "Rows"], attribution_rows)
            )
            if require_corroborated
            else "",
            "## Dose-stratified side-effect reporting\n\n"
            + stratification_note
            + "\n\n"
            + _table(
                [
                    "Compound",
                    "Dose band",
                    "Observations",
                    "Authors",
                    "Classifier coverage",
                    "Any side effect",
                    "Leading mapped effects",
                ],
                _stratified_rows(dose_summaries),
            ),
            "## Route-stratified side-effect reporting\n\n"
            + stratification_note
            + "\n\n"
            + _table(
                [
                    "Compound",
                    "Route family",
                    "Observations",
                    "Authors",
                    "Classifier coverage",
                    "Any side effect",
                    "Leading mapped effects",
                ],
                _stratified_rows(route_summaries),
            ),
            "## Symptom-linked outcomes\n\n"
            + pem_note
            + "\n\n"
            + _table(
                ["Compound", "Target symptom", "Authors", "Helped", "No effect", "Worsened"],
                [list(row) for row in outcome_rows],
            ),
        ]
    )


def _quality_section(
    config: ComparatorAnalysisConfig,
    cohort: ComparatorCohort,
) -> str:
    paths = (
        config.corpus_manifest,
        config.sentiment_manifest,
        config.variable_corpus_manifest,
        config.variable_pipeline_manifest,
    )
    if not all(paths):
        return (
            "## Extraction coverage and provenance\n\n"
            "Detailed run manifests were not supplied for this legacy analysis."
        )
    corpus_path, sentiment_path, variable_corpus_path, variable_run_path = paths
    assert corpus_path is not None
    assert sentiment_path is not None
    assert variable_corpus_path is not None
    assert variable_run_path is not None
    corpus = CorpusEvidence.model_validate_json(corpus_path.read_text(encoding="utf-8"))
    sentiment = SentimentRunEvidence.model_validate_json(
        sentiment_path.read_text(encoding="utf-8")
    )
    variable_corpus = VariableCorpusEvidence.model_validate_json(
        variable_corpus_path.read_text(encoding="utf-8")
    )
    variable_run = VariableRunEvidence.model_validate_json(
        variable_run_path.read_text(encoding="utf-8")
    )
    observed_subreddits = {
        corpus.subreddit,
        sentiment.subreddit,
        variable_corpus.subreddit,
        variable_run.subreddit,
    }
    if observed_subreddits != {config.subreddit}:
        raise ValueError(
            "Run manifests do not all match the requested subreddit: "
            f"{sorted(observed_subreddits)}"
        )
    if sentiment.provider != "openrouter" or variable_run.provider != "openrouter":
        raise ValueError("All new model runs must use OpenRouter")
    if variable_run.status != "complete" or variable_run.missing_author_records:
        raise ValueError("Pipeline B manifest is incomplete; resume missing authors first")

    match_by_slug = {row.slug: row for row in corpus.matches}
    result_by_slug = {row.slug: row for row in sentiment.results}
    coverage_rows: list[list[object]] = []
    for compound in cohort.compounds:
        source = match_by_slug[compound.slug]
        result = result_by_slug[compound.slug]
        retention = (
            result.authors / source.distinct_authors if source.distinct_authors else 0.0
        )
        coverage_rows.append(
            [
                compound.display_name,
                source.matching_items,
                source.distinct_authors,
                result.reports,
                result.authors,
                _percent(retention) if source.distinct_authors else "n/a",
                "too sparse for inference" if result.authors < 10 else "adequate for description",
            ]
        )
    variable_coverage = (
        variable_run.record_count / variable_corpus.selected_authors
        if variable_corpus.selected_authors
        else 0.0
    )
    return (
        "## Extraction coverage and recall checks\n\n"
        "The retention column compares retained classified authors with authors found "
        "by deterministic alias matching. It is a recall proxy, not gold-standard "
        "sensitivity, because model eligibility and alias matching are different "
        "measurement stages.\n\n"
        + _table(
            [
                "Compound",
                "Alias-matched items",
                "Alias-matched authors",
                "Reports",
                "Classified authors",
                "Observed retention",
                "Sample warning",
            ],
            coverage_rows,
        )
        + "\n\n"
        f"Pipeline B produced {variable_run.record_count:,} records from "
        f"{variable_corpus.selected_authors:,} selected authors "
        f"({_percent(variable_coverage) if variable_corpus.selected_authors else 'n/a'}) "
        f"and {variable_corpus.text_segments:,} source segments.\n\n"
        f"OpenRouter models: sentiment `{sentiment.model_fast}` / "
        f"`{sentiment.model_strong}`; variables `{variable_run.model}`. "
        f"Provider-reported token totals: sentiment "
        f"{int(sentiment.usage.get('total_tokens', 0)):,}; variables "
        f"{int(variable_run.usage.get('total_tokens', 0)):,}. Text caps were "
        f"{sentiment.max_upstream_chars:,} upstream characters and "
        f"{variable_run.max_text_chars:,} Pipeline B characters, with a "
        f"{variable_run.max_output_tokens:,}-token Pipeline B output ceiling.\n\n"
        f"Source SHA-256 values: comments `{corpus.comments_sha256}`; posts "
        f"`{corpus.posts_sha256}`. Code commits: sentiment "
        f"`{sentiment.code_commit}`; variables `{variable_run.code_commit}`."
    )


def render_comparator_report(config: ComparatorAnalysisConfig) -> str:
    """Render an aggregate report without source text or author identifiers."""
    cohort = load_comparator_cohort(config.cohort_path)
    with closing(_connect_readonly(config.sentiment_database)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"Sentiment database integrity check failed: {integrity}")
        votes = _load_votes(connection, cohort)
        summaries = _sentiment_summaries(cohort, votes)
        comparisons = _comparisons(cohort, votes, summaries)
        side_effect_records = _canonical_side_effect_records(connection, cohort)
        side_effects = _side_effects(side_effect_records)
        post_dose_summaries = _post_level_dose_summaries(connection, cohort)

    by_slug = cohort.by_slug()
    post_dose_rows = [
        [
            by_slug[summary.slug].display_name,
            summary.dose_band,
            summary.posts,
            summary.authors,
            f"{summary.positive_authors}/{summary.authors} "
            f"({_percent(summary.positive_authors / summary.authors)})",
            f"{summary.side_effect_authors}/{summary.authors} "
            f"({_percent(summary.side_effect_authors / summary.authors)})",
            "too sparse for inference" if summary.authors < 10 else "descriptive only",
        ]
        for summary in post_dose_summaries
    ]
    sentiment_rows = []
    for compound in cohort.compounds:
        sentiment_summary = summaries[compound.slug]
        sentiment_rows.append(
            [
                compound.display_name,
                compound.tier,
                compound.analysis_role,
                sentiment_summary.users,
                sentiment_summary.positive,
                sentiment_summary.negative,
                sentiment_summary.mixed,
                sentiment_summary.neutral,
                _percent(sentiment_summary.positive_rate),
                (
                    f"{_percent(sentiment_summary.ci_low)} to "
                    f"{_percent(sentiment_summary.ci_high)}"
                ),
                (
                    "too sparse for inference"
                    if sentiment_summary.users < 10
                    else "descriptive only"
                ),
            ]
        )

    comparison_rows = []
    for result in comparisons:
        compound = by_slug[result.slug]
        comparison_rows.append(
            [
                compound.display_name,
                f"{100 * result.rate_difference:+.1f} points",
                f"{result.odds_ratio:.2f}",
                f"{result.p_value:.4f}",
                f"{result.q_value:.4f}",
                result.exclusive_target_authors,
                result.exclusive_comparator_authors,
                result.matched_authors,
                f"{result.target_only_positive}/{result.comparator_only_positive}",
                f"{result.matched_p_value:.4f}" if result.matched_p_value is not None else "n/a",
                f"{result.matched_q_value:.4f}" if result.matched_q_value is not None else "n/a",
                (
                    "too sparse for inference"
                    if min(
                        result.exclusive_target_authors,
                        result.exclusive_comparator_authors,
                    )
                    < 10
                    else "sensitivity analysis"
                ),
            ]
        )

    side_effect_rows = []
    grouped_side_effects: dict[str, list[SideEffectSummary]] = defaultdict(list)
    for side_effect_summary in side_effects:
        grouped_side_effects[side_effect_summary.slug].append(side_effect_summary)
    for compound in cohort.compounds:
        denominator = summaries[compound.slug].users
        for side_effect_summary in grouped_side_effects[compound.slug][:8]:
            side_effect_rows.append(
                [
                    compound.display_name,
                    side_effect_summary.canonical_side_effect,
                    side_effect_summary.safety_domain,
                    side_effect_summary.users,
                    (
                        f"{_percent(side_effect_summary.users / denominator)}"
                        if denominator
                        else "n/a"
                    ),
                    side_effect_summary.mentions,
                ]
            )

    sections = [
        f"# 7,8-DHF comparator-cohort analysis: r/{config.subreddit}",
        (
            "This report answers the OMF collaboration questions with aggregate "
            f"r/{config.subreddit} self-reports. It measures reporting patterns, not efficacy, "
            "adverse-event incidence, causal dose-response, or medical safety. Every "
            "comparator uses the same source population, classifier, context handling, "
            "and one-vote-per-author rule."
        ),
        _quality_section(config, cohort),
        "## Comparator definitions\n\n"
        + _table(
            ["Compound", "Tier", "Role", "Mechanistic rationale"],
            [
                [
                    compound.display_name,
                    compound.tier,
                    compound.analysis_role,
                    compound.mechanism_note,
                ]
                for compound in cohort.compounds
            ],
        ),
        "## Author-level sentiment\n\n"
        + _table(
            [
                "Compound",
                "Tier",
                "Role",
                "Users",
                "Positive",
                "Negative",
                "Mixed",
                "Neutral",
                "Positive share",
                "95% Wilson CI",
                "Inference status",
            ],
            sentiment_rows,
        ),
        (
            "## Comparisons with 7,8-DHF\n\n"
            "The positive-rate difference is 7,8-DHF minus comparator, so positive values "
            "favor a higher 7,8-DHF positive-reporting share. Fisher tests use mutually "
            "exclusive authors and report 7,8-DHF/comparator odds ratios. BH q-values are "
            "corrected across comparators. Matched results use authors who reported both "
            "compounds; the discordant column is 7,8-DHF-only positive / comparator-only "
            "positive. Matched q-values are corrected separately.\n\n"
            + _table(
                [
                    "Comparator",
                    "7,8-DHF minus comparator",
                    "Exclusive OR",
                    "Exclusive p",
                    "Exclusive BH q",
                    "Exclusive 7,8-DHF authors",
                    "Exclusive comparator authors",
                    "Matched authors",
                    "Discordant",
                    "Matched p",
                    "Matched BH q",
                    "Inference status",
                ],
                comparison_rows,
            )
        ),
        (
            "## Treatment-linked side-effect signals\n\n"
            "These are the eight most frequently reported canonical effects per "
            "compound, deduplicated by author within each effect. Because every "
            "pipeline row is linked to one target treatment, the former 7,8-DHF / "
            "4'-DMA blending is removed. Counts remain reporting proportions, not "
            "incidence.\n\n"
            + _table(
                [
                    "Compound",
                    "Canonical effect",
                    "Safety domain",
                    "Authors",
                    "Share of classified authors",
                    "Mentions",
                ],
                side_effect_rows,
            )
        ),
        (
            "## Post-level compound, dose, and outcome links\n\n"
            "This stricter view keeps only treatment-specific sentiment reports where "
            "exactly one quantitative mass dose appears near that compound in the same "
            "post or comment. Authors receive one vote per compound and dose band. It is "
            "descriptive and does not establish a dose-response relationship.\n\n"
            + _table(
                [
                    "Compound",
                    "Dose band",
                    "Posts",
                    "Authors",
                    "Positive authors",
                    "Side-effect authors",
                    "Inference status",
                ],
                post_dose_rows,
            )
        ),
    ]
    study_sections = _study_sections(
        config.study_database,
        classified_authors={slug: set(author_votes) for slug, author_votes in votes.items()},
        side_effect_records=side_effect_records,
        cohort=cohort,
        require_corroborated=config.require_corroborated_attribution,
    )
    if study_sections:
        sections.append(study_sections)
    sections.extend(
        [
            (
                "## Interpretation boundaries\n\n"
                "- Keep 7,8-DHF and 4'-DMA-7,8-DHF separate.\n"
                "- Treat PEM as distinct from general fatigue when it is explicitly stated.\n"
                "- Do not infer that dose, route, outcome, and side effect belong to one "
                "administration event unless the source explicitly links them.\n"
                "- Use matched-author results as a sensitivity analysis, not as the primary "
                "estimand, because overlap can be sparse.\n"
                "- The direct TrkB-agonist interpretation of 7,8-DHF remains disputed; the "
                "cohort is tiered rather than presented as one homogeneous mechanism class."
            ),
            (
                "## Reproducibility\n\n"
                f"- Sentiment database: `{config.sentiment_database.name}`; SHA-256 "
                f"`{sha256_file(config.sentiment_database)}`\n"
                + (
                    f"- Study database: `{config.study_database.name}`; SHA-256 "
                    f"`{sha256_file(config.study_database)}`\n"
                    if config.study_database
                    else "- Study database: not supplied\n"
                )
                + f"- Cohort configuration: `{config.cohort_path.name}`; SHA-256 "
                f"`{sha256_file(config.cohort_path)}`"
            ),
        ]
    )
    return "\n\n".join(sections) + "\n"


def analyze_comparator_cohort(config: ComparatorAnalysisConfig) -> str:
    """Render and write the comparator analysis."""
    report = render_comparator_report(config)
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(report, encoding="utf-8")
    return report


@app.command()
def main(
    subreddit: str = typer.Option(..., help="Subreddit name without the r/ prefix."),
    sentiment_database: Path = typer.Option(..., exists=True, dir_okay=False),
    output: Path = typer.Option(..., dir_okay=False),
    study_database: Path | None = typer.Option(None, exists=True, dir_okay=False),
    cohort: Path = typer.Option(DEFAULT_COHORT_CONFIG, exists=True, dir_okay=False),
    require_corroborated_attribution: bool = typer.Option(False),
    corpus_manifest: Path | None = typer.Option(None, exists=True, dir_okay=False),
    sentiment_manifest: Path | None = typer.Option(None, exists=True, dir_okay=False),
    variable_corpus_manifest: Path | None = typer.Option(
        None, exists=True, dir_okay=False
    ),
    variable_pipeline_manifest: Path | None = typer.Option(
        None, exists=True, dir_okay=False
    ),
) -> None:
    """Write the privacy-safe aggregate report."""
    try:
        analyze_comparator_cohort(
            ComparatorAnalysisConfig(
                subreddit=subreddit,
                sentiment_database=sentiment_database,
                study_database=study_database,
                cohort_path=cohort,
                output_path=output,
                require_corroborated_attribution=require_corroborated_attribution,
                corpus_manifest=corpus_manifest,
                sentiment_manifest=sentiment_manifest,
                variable_corpus_manifest=variable_corpus_manifest,
                variable_pipeline_manifest=variable_pipeline_manifest,
            )
        )
        console.print(f"[green]Wrote[/green] {output}")
    except (OSError, ValueError, sqlite3.Error) as exc:
        console.print(f"[red]Comparator analysis failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
