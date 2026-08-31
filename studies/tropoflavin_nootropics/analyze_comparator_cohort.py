"""Generate the aggregate comparator, safety, dose, and symptom report."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from contextlib import closing
from pathlib import Path
from typing import Any, TypedDict

import typer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from rich.console import Console
from scipy.stats import binomtest, fisher_exact
from statsmodels.stats.multitest import multipletests

from studies.tropoflavin_nootropics.comparator_support import (
    DEFAULT_COHORT_CONFIG,
    ComparatorCohort,
    load_comparator_cohort,
    markdown_escape,
    sha256_file,
)
from studies.tropoflavin_nootropics.study_support import canonical_side_effect

console = Console()
app = typer.Typer(add_completion=False, no_args_is_help=True)

SIGNAL_RANK = {"strong": 3, "moderate": 2, "weak": 1, "n/a": 0, None: 0}
SENTIMENTS = ("positive", "negative", "mixed", "neutral")


class ComparatorAnalysisConfig(BaseModel):
    """Validated inputs for the aggregate analysis."""

    model_config = ConfigDict(frozen=True)

    sentiment_database: Path
    study_database: Path | None = None
    cohort_path: Path = DEFAULT_COHORT_CONFIG
    output_path: Path

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
        return self


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
    """Independent and matched comparison against the target compound."""

    model_config = ConfigDict(frozen=True)

    slug: str
    odds_ratio: float
    p_value: float = Field(ge=0, le=1)
    q_value: float = Field(ge=0, le=1)
    rate_difference: float
    matched_authors: int = Field(ge=0)
    target_only_positive: int = Field(ge=0)
    comparator_only_positive: int = Field(ge=0)
    matched_p_value: float | None = Field(default=None, ge=0, le=1)


class SideEffectSummary(BaseModel):
    """Treatment-linked, author-deduplicated side-effect count."""

    model_config = ConfigDict(frozen=True)

    slug: str
    canonical_side_effect: str
    safety_domain: str
    users: int = Field(ge=0)
    mentions: int = Field(ge=0)


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
        if target.users and comparator.users:
            odds_ratio, p_value = fisher_exact(
                [
                    [target.positive, target.users - target.positive],
                    [comparator.positive, comparator.users - comparator.positive],
                ]
            )
        else:
            odds_ratio, p_value = math.nan, 1.0

        comparator_votes = votes.get(compound.slug, {})
        matched = set(target_votes) & set(comparator_votes)
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
                "rate_difference": comparator.positive_rate - target.positive_rate,
                "matched_authors": len(matched),
                "target_only_positive": target_only_positive,
                "comparator_only_positive": comparator_only_positive,
                "matched_p_value": matched_p,
            }
        )

    q_values = multipletests(
        [row["p_value"] for row in provisional], method="fdr_bh"
    )[1]
    return tuple(
        ComparatorResult(**row, q_value=float(q_value))
        for row, q_value in zip(provisional, q_values, strict=True)
    )


def _side_effects(
    connection: sqlite3.Connection,
    cohort: ComparatorCohort,
) -> tuple[SideEffectSummary, ...]:
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

    mentions: dict[tuple[str, str, str], int] = defaultdict(int)
    authors: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for (_, slug), row in latest.items():
        try:
            values = json.loads(row["side_effects"] or "[]")
        except json.JSONDecodeError:
            continue
        if not isinstance(values, list):
            continue
        for raw_value in values:
            canonical, domain = canonical_side_effect(str(raw_value))
            key = (slug, canonical, domain)
            mentions[key] += 1
            if row["user_id"]:
                authors[key].add(row["user_id"])
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


def _study_sections(path: Path | None) -> str:
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
        dose_rows = connection.execute(
            """
            SELECT target_compound, dose_band, COUNT(*), COUNT(DISTINCT author_hash)
            FROM pipeline_b_dosages
            WHERE target_compound IS NOT NULL
            GROUP BY target_compound, dose_band, dose_band_order
            ORDER BY target_compound, COALESCE(dose_band_order, -1)
            """
        ).fetchall()
        route_rows = connection.execute(
            """
            SELECT target_compound, route_bucket, COUNT(*), COUNT(DISTINCT author_hash)
            FROM pipeline_b_administration_routes
            WHERE target_compound IS NOT NULL
            GROUP BY target_compound, route_bucket
            ORDER BY target_compound, COUNT(*) DESC
            """
        ).fetchall()
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

    return "\n\n".join(
        [
            "## Treatment-linked dosage\n\n"
            + _table(
                ["Compound", "Dose band", "Observations", "Authors"],
                [list(row) for row in dose_rows],
            ),
            "## Treatment-linked administration route\n\n"
            + _table(
                ["Compound", "Route family", "Observations", "Authors"],
                [list(row) for row in route_rows],
            ),
            "## Symptom-linked outcomes\n\n"
            + _table(
                ["Compound", "Target symptom", "Authors", "Helped", "No effect", "Worsened"],
                [list(row) for row in outcome_rows],
            ),
        ]
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
        side_effects = _side_effects(connection, cohort)

    by_slug = cohort.by_slug()
    sentiment_rows = []
    for compound in cohort.compounds:
        summary = summaries[compound.slug]
        sentiment_rows.append(
            [
                compound.display_name,
                compound.tier,
                compound.analysis_role,
                summary.users,
                summary.positive,
                summary.negative,
                summary.mixed,
                summary.neutral,
                _percent(summary.positive_rate),
                f"{_percent(summary.ci_low)} to {_percent(summary.ci_high)}",
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
                result.matched_authors,
                f"{result.target_only_positive}/{result.comparator_only_positive}",
                f"{result.matched_p_value:.4f}" if result.matched_p_value is not None else "n/a",
            ]
        )

    side_effect_rows = []
    grouped_side_effects: dict[str, list[SideEffectSummary]] = defaultdict(list)
    for summary in side_effects:
        grouped_side_effects[summary.slug].append(summary)
    for compound in cohort.compounds:
        for summary in grouped_side_effects[compound.slug][:8]:
            side_effect_rows.append(
                [
                    compound.display_name,
                    summary.canonical_side_effect,
                    summary.safety_domain,
                    summary.users,
                    summary.mentions,
                ]
            )

    sections = [
        "# 7,8-DHF comparator-cohort analysis",
        (
            "This report answers the OMF collaboration questions with aggregate "
            "r/Nootropics self-reports. It measures reporting patterns, not efficacy, "
            "adverse-event incidence, causal dose-response, or medical safety. Every "
            "comparator uses the same source population, classifier, context handling, "
            "and one-vote-per-author rule."
        ),
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
            ],
            sentiment_rows,
        ),
        (
            "## Comparisons with 7,8-DHF\n\n"
            "Independent Fisher tests compare positive versus all other labels. "
            "The q-value is Benjamini-Hochberg corrected across comparators. Matched "
            "results use authors who reported both compounds; the discordant column "
            "is 7,8-DHF-only positive / comparator-only positive.\n\n"
            + _table(
                [
                    "Comparator",
                    "Positive-rate difference",
                    "Odds ratio",
                    "p",
                    "BH q",
                    "Matched authors",
                    "Discordant",
                    "Matched p",
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
                ["Compound", "Canonical effect", "Safety domain", "Users", "Mentions"],
                side_effect_rows,
            )
        ),
    ]
    study_sections = _study_sections(config.study_database)
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
    sentiment_database: Path = typer.Option(..., exists=True, dir_okay=False),
    output: Path = typer.Option(..., dir_okay=False),
    study_database: Path | None = typer.Option(None, exists=True, dir_okay=False),
    cohort: Path = typer.Option(DEFAULT_COHORT_CONFIG, exists=True, dir_okay=False),
) -> None:
    """Write the privacy-safe aggregate report."""
    try:
        analyze_comparator_cohort(
            ComparatorAnalysisConfig(
                sentiment_database=sentiment_database,
                study_database=study_database,
                cohort_path=cohort,
                output_path=output,
            )
        )
        console.print(f"[green]Wrote[/green] {output}")
    except (OSError, ValueError, sqlite3.Error) as exc:
        console.print(f"[red]Comparator analysis failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
