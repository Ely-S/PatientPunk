"""Analyze same-post 7,8-DHF exposure episodes with author-clustered models."""

from __future__ import annotations

import math
import sqlite3
import statistics
import warnings
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Sequence, cast

import numpy as np
import pandas as pd
import typer
from pydantic import BaseModel, ConfigDict, Field, model_validator
from rich.console import Console
from statsmodels.genmod.cov_struct import Independence
from statsmodels.genmod.families import Binomial
from statsmodels.genmod.generalized_estimating_equations import GEE, OrdinalGEE
from statsmodels.stats.multitest import multipletests

from studies.tropoflavin_nootropics.analyze_78dhf_predictors import (
    CohortInput,
    ReasonCategory,
    Sentiment,
)
from studies.tropoflavin_nootropics.comparator_support import (
    markdown_escape,
    sha256_file,
)
from studies.tropoflavin_nootropics.extract_78dhf_episodes import (
    EpisodeExtractionManifest,
    EpisodeRecord,
    RouteCategory,
)
from studies.tropoflavin_nootropics.study_support import dose_band

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()
_SENTIMENT_LEVEL: dict[Sentiment, int] = {
    "negative": 0,
    "mixed": 1,
    "neutral": 1,
    "positive": 2,
}


class EpisodeAnalysisConfig(BaseModel):
    """Validated inputs for the aggregate same-post report."""

    model_config = ConfigDict(frozen=True)

    cohorts: tuple[CohortInput, ...] = Field(min_length=2)
    episode_records: Path
    episode_manifest: Path
    output_path: Path
    minimum_model_episodes: int = Field(default=30, ge=10)
    minimum_model_authors: int = Field(default=20, ge=10)
    minimum_community_episodes: int = Field(default=5, ge=2)

    @model_validator(mode="after")
    def validate_inputs(self) -> EpisodeAnalysisConfig:
        if not self.episode_records.is_file():
            raise ValueError(f"Episode records not found: {self.episode_records}")
        if not self.episode_manifest.is_file():
            raise ValueError(f"Episode manifest not found: {self.episode_manifest}")
        names = [cohort.subreddit.casefold() for cohort in self.cohorts]
        if len(names) != len(set(names)):
            raise ValueError("Subreddit cohorts must be unique")
        return self


@dataclass(frozen=True)
class Episode:
    subreddit: str
    author_hash: str
    post_id: str
    report_id: int
    sentiment: Sentiment
    side_effects: frozenset[str]
    explicit_personal_use: bool
    dose_status: str
    dose_midpoints_mg: tuple[float, ...]
    route_status: str
    routes: tuple[RouteCategory, ...]
    reasons: tuple[ReasonCategory, ...]

    @property
    def sentiment_level(self) -> int:
        return _SENTIMENT_LEVEL[self.sentiment]

    @property
    def positive(self) -> bool:
        return self.sentiment == "positive"

    @property
    def side_effect_reported(self) -> bool:
        return bool(self.side_effects)

    @property
    def single_dose_mg(self) -> float | None:
        if self.dose_status == "single" and len(self.dose_midpoints_mg) == 1:
            return self.dose_midpoints_mg[0]
        return None

    @property
    def single_route(self) -> str | None:
        if self.route_status == "single" and len(self.routes) == 1:
            return self.routes[0]
        return None


@dataclass(frozen=True)
class TrendEstimate:
    outcome: str
    episodes: int
    authors: int
    coefficient: float | None
    odds_ratio: float | None
    confidence_interval: tuple[float, float] | None
    p_value: float | None
    q_value: float | None
    status: str
    communities: tuple[tuple[str, int], ...]


def _connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def load_episode_records(path: Path) -> dict[tuple[str, str, str], EpisodeRecord]:
    """Load private episode records with duplicate-key validation."""
    records: dict[tuple[str, str, str], EpisodeRecord] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = EpisodeRecord.model_validate_json(line)
        except ValueError as exc:
            raise ValueError(f"Invalid episode record at line {line_number}") from exc
        key = (
            record.subreddit.casefold(),
            record.author_hash,
            record.post_id,
        )
        if key in records:
            raise ValueError(f"Duplicate episode record at line {line_number}")
        records[key] = record
    return records


def _load_cohort_episodes(
    cohort: CohortInput,
    records: dict[tuple[str, str, str], EpisodeRecord],
) -> tuple[Episode, ...]:
    cohort_records = tuple(
        record
        for key, record in records.items()
        if key[0] == cohort.subreddit.casefold()
    )
    with closing(_connect_readonly(cohort.database)) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError(f"Database integrity check failed: {cohort.database.name}")
        rows = connection.execute(
            """
            SELECT tr.report_id, tr.post_id, tr.user_id, tr.sentiment,
                   lower(t.canonical_name) AS treatment
            FROM treatment_reports tr
            JOIN treatment t ON t.id = tr.drug_id
            WHERE lower(t.canonical_name) = '7,8-dhf'
            """
        ).fetchall()
        by_report = {int(row["report_id"]): row for row in rows}
        effect_rows = connection.execute(
            """
            SELECT report_id, canonical_side_effect
            FROM pipeline_a_side_effects
            """
        ).fetchall()
    effects: dict[int, set[str]] = {}
    for row in effect_rows:
        label = str(row["canonical_side_effect"] or "").strip()
        if label:
            effects.setdefault(int(row["report_id"]), set()).add(label)

    episodes: list[Episode] = []
    for record in cohort_records:
        row = by_report.get(record.report_id)
        if row is None:
            raise ValueError("Episode record does not resolve to its source report")
        sentiment = str(row["sentiment"] or "")
        if (
            str(row["user_id"] or "").strip().lower() != record.author_hash
            or str(row["post_id"]) != record.post_id
            or str(row["treatment"]) != "7,8-dhf"
            or sentiment not in _SENTIMENT_LEVEL
        ):
            raise ValueError("Episode record does not match its source report")
        episodes.append(
            Episode(
                subreddit=cohort.subreddit,
                author_hash=record.author_hash,
                post_id=record.post_id,
                report_id=record.report_id,
                sentiment=sentiment,  # type: ignore[arg-type]
                side_effects=frozenset(effects.get(record.report_id, set())),
                explicit_personal_use=record.explicit_personal_use,
                dose_status=record.dose_status,
                dose_midpoints_mg=tuple(dose.midpoint_mg for dose in record.doses),
                route_status=record.route_status,
                routes=record.routes,
                reasons=record.reasons,
            )
        )
    return tuple(sorted(episodes, key=lambda item: (item.author_hash, item.post_id)))


def _model_frame(
    episodes: Sequence[Episode], minimum_community_episodes: int
) -> tuple[pd.DataFrame, tuple[tuple[str, int], ...]]:
    dose_episodes: list[tuple[Episode, float]] = []
    for episode in episodes:
        dose = episode.single_dose_mg
        if (
            episode.explicit_personal_use
            and dose is not None
            and math.isfinite(dose)
            and dose > 0
        ):
            dose_episodes.append((episode, dose))
    community_counts = Counter(episode.subreddit for episode, _ in dose_episodes)
    communities = tuple(sorted(community_counts.items()))
    rows = []
    for episode, dose in dose_episodes:
        community = (
            episode.subreddit
            if community_counts[episode.subreddit] >= minimum_community_episodes
            else "Other"
        )
        rows.append(
            {
                "author": episode.author_hash,
                "sentiment": episode.sentiment_level,
                "positive": int(episode.positive),
                "side_effect": int(episode.side_effect_reported),
                "dose_mg": dose,
                "log2_dose": math.log2(dose),
                "community": community,
            }
        )
    frame = pd.DataFrame.from_records(rows)
    if not frame.empty:
        frame["log2_dose_centered"] = frame["log2_dose"] - float(
            frame["log2_dose"].median()
        )
    return frame, communities


def _design_matrix(frame: pd.DataFrame, ordinal: bool) -> pd.DataFrame:
    design = pd.DataFrame(
        {"log2_dose": frame["log2_dose_centered"].astype(float)},
        index=frame.index,
    )
    communities = sorted(frame["community"].unique())
    if len(communities) > 1:
        reference = frame["community"].value_counts().index[0]
        for community in communities:
            if community == reference:
                continue
            design[f"community_{community}"] = (
                frame["community"] == community
            ).astype(float)
    if not ordinal:
        design.insert(0, "intercept", 1.0)
    return design


def _safe_exp(value: float) -> float:
    return math.exp(max(-700.0, min(700.0, value)))


def fit_trend_model(
    episodes: Sequence[Episode],
    outcome: Literal["ordinal sentiment", "side-effect reporting"],
    minimum_episodes: int,
    minimum_authors: int,
    minimum_community_episodes: int,
) -> TrendEstimate:
    """Fit an author-clustered GEE trend per doubling of same-post dose."""
    frame, communities = _model_frame(episodes, minimum_community_episodes)
    authors = int(frame["author"].nunique()) if not frame.empty else 0
    if len(frame) < minimum_episodes or authors < minimum_authors:
        return TrendEstimate(
            outcome=outcome,
            episodes=len(frame),
            authors=authors,
            coefficient=None,
            odds_ratio=None,
            confidence_interval=None,
            p_value=None,
            q_value=None,
            status="too sparse for the prespecified model",
            communities=communities,
        )
    endog_name = "sentiment" if outcome == "ordinal sentiment" else "side_effect"
    if frame[endog_name].nunique() < 2:
        return TrendEstimate(
            outcome=outcome,
            episodes=len(frame),
            authors=authors,
            coefficient=None,
            odds_ratio=None,
            confidence_interval=None,
            p_value=None,
            q_value=None,
            status="outcome has no variation",
            communities=communities,
        )
    ordinal = outcome == "ordinal sentiment"
    design = _design_matrix(frame, ordinal=ordinal)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if ordinal:
                model = OrdinalGEE(
                    frame[endog_name].astype(int),
                    design,
                    frame["author"],
                    cov_struct=Independence(),
                )
            else:
                model = GEE(
                    frame[endog_name].astype(int),
                    design,
                    frame["author"],
                    family=Binomial(),
                    cov_struct=Independence(),
                )
            result = model.fit(cov_type="robust", maxiter=100)
        coefficient = float(result.params["log2_dose"])
        standard_error = float(result.bse["log2_dose"])
        p_value = float(result.pvalues["log2_dose"])
        if not all(math.isfinite(value) for value in (coefficient, standard_error, p_value)):
            raise ValueError("Model estimate was not finite")
        low = coefficient - 1.96 * standard_error
        high = coefficient + 1.96 * standard_error
        status = "estimated" if bool(result.converged) else "did not converge"
        return TrendEstimate(
            outcome=outcome,
            episodes=len(frame),
            authors=authors,
            coefficient=coefficient,
            odds_ratio=_safe_exp(coefficient),
            confidence_interval=(_safe_exp(low), _safe_exp(high)),
            p_value=p_value,
            q_value=None,
            status=status,
            communities=communities,
        )
    except (ValueError, TypeError, np.linalg.LinAlgError) as exc:
        return TrendEstimate(
            outcome=outcome,
            episodes=len(frame),
            authors=authors,
            coefficient=None,
            odds_ratio=None,
            confidence_interval=None,
            p_value=None,
            q_value=None,
            status=f"model failed: {type(exc).__name__}",
            communities=communities,
        )


def _correct_primary(estimates: tuple[TrendEstimate, ...]) -> tuple[TrendEstimate, ...]:
    indexes = [
        index for index, estimate in enumerate(estimates) if estimate.p_value is not None
    ]
    if not indexes:
        return estimates
    p_values: list[float] = []
    for index in indexes:
        p_value = estimates[index].p_value
        if p_value is None:
            raise AssertionError("Eligible primary estimate is missing its p-value")
        p_values.append(p_value)
    q_values = multipletests(p_values, method="fdr_bh")[1]
    corrected = list(estimates)
    for index, q_value in zip(indexes, q_values, strict=True):
        corrected[index] = replace(corrected[index], q_value=float(q_value))
    return tuple(corrected)


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


def _percent(value: float) -> str:
    return f"{100 * value:.1f}%"


def _count_rate(successes: int, total: int) -> str:
    if total == 0:
        return "0/0"
    low, high = _wilson(successes, total)
    return (
        f"{successes}/{total} ({_percent(successes / total)}; "
        f"{_percent(low)} to {_percent(high)})"
    )


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


def _estimate_row(estimate: TrendEstimate) -> list[object]:
    interval = (
        f"{estimate.confidence_interval[0]:.2f} to "
        f"{estimate.confidence_interval[1]:.2f}"
        if estimate.confidence_interval is not None
        else "n/a"
    )
    return [
        estimate.outcome,
        estimate.episodes,
        estimate.authors,
        f"{estimate.odds_ratio:.2f}" if estimate.odds_ratio is not None else "n/a",
        interval,
        f"{estimate.p_value:.4f}" if estimate.p_value is not None else "n/a",
        f"{estimate.q_value:.4f}" if estimate.q_value is not None else "n/a",
        estimate.status,
    ]


def _dose_rows(episodes: Sequence[Episode]) -> list[list[object]]:
    groups: dict[str, list[Episode]] = {}
    for episode in episodes:
        dose = episode.single_dose_mg
        if not episode.explicit_personal_use or dose is None or dose <= 0:
            continue
        groups.setdefault(dose_band(dose).label, []).append(episode)
    rows: list[list[object]] = []
    for label in sorted(groups, key=lambda value: dose_band(
        statistics.median(
            episode.single_dose_mg or 0 for episode in groups[value]
        )
    ).order):
        selected = groups[label]
        positive = sum(episode.positive for episode in selected)
        effects = sum(episode.side_effect_reported for episode in selected)
        doses = [cast(float, episode.single_dose_mg) for episode in selected]
        rows.append(
            [
                label,
                len(selected),
                len({episode.author_hash for episode in selected}),
                f"{statistics.median(doses):.1f} mg",
                _count_rate(positive, len(selected)),
                _count_rate(effects, len(selected)),
            ]
        )
    return rows


def _category_rows(
    episodes: Sequence[Episode], category_type: Literal["route", "reason"]
) -> list[list[object]]:
    groups: dict[str, list[Episode]] = {}
    for episode in episodes:
        if not episode.explicit_personal_use:
            continue
        categories: Sequence[str]
        if category_type == "route":
            categories = (episode.single_route,) if episode.single_route else ()
        else:
            categories = episode.reasons
        for category in categories:
            groups.setdefault(category, []).append(episode)
    rows = []
    for category, selected in sorted(groups.items()):
        positive = sum(episode.positive for episode in selected)
        effects = sum(episode.side_effect_reported for episode in selected)
        rows.append(
            [
                category,
                len(selected),
                len({episode.author_hash for episode in selected}),
                _count_rate(positive, len(selected)),
                _count_rate(effects, len(selected)),
            ]
        )
    return rows


def render_episode_report(config: EpisodeAnalysisConfig) -> str:
    """Render a privacy-safe same-post episode analysis."""
    records = load_episode_records(config.episode_records)
    manifest = EpisodeExtractionManifest.model_validate_json(
        config.episode_manifest.read_text(encoding="utf-8")
    )
    if manifest.provider != "openrouter" or manifest.missing_episodes:
        raise ValueError("Episode extraction provenance is incomplete")
    if sha256_file(config.episode_records) != manifest.records_sha256:
        raise ValueError("Episode records do not match their manifest hash")
    if len(records) != manifest.completed_episodes:
        raise ValueError("Episode record count does not match its manifest")

    by_subreddit = {
        cohort.subreddit: _load_cohort_episodes(cohort, records)
        for cohort in config.cohorts
    }
    combined = tuple(
        episode for episodes in by_subreddit.values() for episode in episodes
    )
    if len({(episode.author_hash, episode.post_id) for episode in combined}) != len(
        combined
    ):
        raise ValueError("Combined episodes are not globally unique")

    coverage_rows = []
    for subreddit, episodes in (*by_subreddit.items(), ("Combined", combined)):
        personal = sum(episode.explicit_personal_use for episode in episodes)
        dose = sum(episode.single_dose_mg is not None for episode in episodes)
        route = sum(episode.single_route is not None for episode in episodes)
        reasons = sum(bool(episode.reasons) for episode in episodes)
        effects = sum(episode.side_effect_reported for episode in episodes)
        coverage_rows.append(
            [
                subreddit,
                len(episodes),
                len({episode.author_hash for episode in episodes}),
                _count_rate(personal, len(episodes)),
                _count_rate(dose, len(episodes)),
                _count_rate(route, len(episodes)),
                _count_rate(reasons, len(episodes)),
                _count_rate(effects, len(episodes)),
            ]
        )

    primary = _correct_primary(
        (
            fit_trend_model(
                combined,
                "ordinal sentiment",
                config.minimum_model_episodes,
                config.minimum_model_authors,
                config.minimum_community_episodes,
            ),
            fit_trend_model(
                combined,
                "side-effect reporting",
                config.minimum_model_episodes,
                config.minimum_model_authors,
                config.minimum_community_episodes,
            ),
        )
    )
    significant = [
        estimate for estimate in primary if estimate.q_value is not None and estimate.q_value < 0.05
    ]
    dose_complete = [
        episode for episode in combined if episode.single_dose_mg is not None
    ]
    repeated = Counter(episode.author_hash for episode in dose_complete)
    main_finding = (
        f"The primary model used {len(dose_complete):,} same-post, single-dose "
        f"episodes from {len(repeated):,} authors; "
        f"{sum(count > 1 for count in repeated.values()):,} authors contributed "
        "more than one dose-complete episode. "
        + (
            "Neither primary outcome passed Benjamini-Hochberg correction at "
            "q < 0.05."
            if not significant
            else f"{len(significant)} primary outcome(s) passed Benjamini-Hochberg "
            "correction at q < 0.05."
        )
    )

    sections = [
        "# Same-post 7,8-DHF episode analysis",
        (
            "This analysis requires dose, route, reason, sentiment, and side-effect "
            "reporting to be attributable within the same Reddit post. Each globally "
            "unique author-post pair is an episode. Repeated episodes are retained and "
            "standard errors are clustered by author. A missing mapped side effect "
            "means not reported in that episode, not that no side effect occurred."
        ),
        (
            "## Primary design\n\n"
            "The primary exposure is log2 quantitative dose, so its odds ratio is the "
            "change associated with a dose doubling. Ordinal sentiment is coded "
            "negative < neutral/mixed < positive. The second outcome is any mapped "
            "same-report side-effect mention. Both use generalized estimating "
            "equations with author-clustered robust covariance and subreddit fixed "
            "effects. Subreddits with fewer than "
            f"{config.minimum_community_episodes} dose-complete episodes are pooled "
            "as Other. The two primary p-values receive Benjamini-Hochberg correction."
        ),
        "## Coverage\n\n"
        + _table(
            [
                "Cohort",
                "Episodes",
                "Authors",
                "Explicit personal use",
                "Single quantitative dose",
                "Single route",
                "Explicit reason",
                "Mapped side effect reported",
            ],
            coverage_rows,
        ),
        "## Main finding\n\n" + main_finding,
        "## Combined primary models\n\n"
        + _table(
            [
                "Outcome",
                "Episodes",
                "Authors",
                "OR per dose doubling",
                "95% CI",
                "p",
                "BH q",
                "Status",
            ],
            [_estimate_row(estimate) for estimate in primary],
        ),
        "## Combined dose descriptives\n\n"
        + _table(
            [
                "Dose band",
                "Episodes",
                "Authors",
                "Median dose",
                "Positive sentiment",
                "Mapped side effect reported",
            ],
            _dose_rows(combined),
        ),
        "## Combined route descriptives\n\n"
        + _table(
            [
                "Route",
                "Episodes",
                "Authors",
                "Positive sentiment",
                "Mapped side effect reported",
            ],
            _category_rows(combined, "route"),
        ),
        "## Combined explicit-reason descriptives\n\n"
        + _table(
            [
                "Reason",
                "Episodes",
                "Authors",
                "Positive sentiment",
                "Mapped side effect reported",
            ],
            _category_rows(combined, "reason"),
        ),
        "## Separate subreddit trend estimates",
    ]

    separate_rows = []
    for subreddit, episodes in by_subreddit.items():
        for outcome in ("ordinal sentiment", "side-effect reporting"):
            estimate = fit_trend_model(
                episodes,
                outcome,  # type: ignore[arg-type]
                config.minimum_model_episodes,
                config.minimum_model_authors,
                config.minimum_community_episodes,
            )
            separate_rows.append(
                [subreddit, *_estimate_row(estimate)[:-2], estimate.status]
            )
    sections.append(
        _table(
            [
                "Subreddit",
                "Outcome",
                "Episodes",
                "Authors",
                "OR per dose doubling",
                "95% CI",
                "p",
                "Status",
            ],
            separate_rows,
        )
        + "\n\nThese subreddit-specific models are secondary and report raw p-values only."
    )

    source_rows = [
        [cohort.subreddit, cohort.database.name, sha256_file(cohort.database)]
        for cohort in config.cohorts
    ]
    sections.extend(
        [
            (
                "## Interpretation boundaries\n\n"
                "This is an observational reporting analysis. Dose is self-reported, "
                "and formulation, frequency, treatment duration, co-treatments, reason "
                "for use, indication severity, and selective posting remain potential "
                "confounders. Same-post attribution removes cross-report exposure and "
                "outcome mismatch but does not establish timing within the post. The "
                "between-compound sentiment mean is not used in the primary regression; "
                "subreddit fixed effects address community-level sentiment differences "
                "without mixing comparator compounds into the within-7,8-DHF dose test."
            ),
            "## Reproducibility\n\n"
            + f"Generated at `{datetime.now(UTC).isoformat()}`. Private episode records "
            "and caches remain external. No source text, post identifier, or author "
            "identifier is included.\n\n"
            + _table(["Subreddit", "Database", "SHA-256"], source_rows)
            + "\n\n"
            + _table(
                ["Episode artifact", "SHA-256"],
                [
                    [config.episode_records.name, sha256_file(config.episode_records)],
                    [config.episode_manifest.name, sha256_file(config.episode_manifest)],
                ],
            )
            + "\n\n"
            + (
                f"Episode extraction: provider `{manifest.provider}`; model "
                f"`{manifest.model}`; code commit `{manifest.code_commit}`; prompt "
                f"`{manifest.prompt_file}` with SHA-256 `{manifest.prompt_sha256}`; "
                "batch sizes used "
                f"{', '.join(str(size) for size in manifest.batch_sizes_used)}; "
                f"completed {manifest.completed_episodes:,}/{manifest.source_episodes:,} "
                f"episodes; {manifest.personal_use_episodes:,} explicit personal-use "
                f"episodes; {manifest.single_dose_episodes:,} single-dose episodes; "
                f"{manifest.single_route_episodes:,} single-route episodes; "
                f"{manifest.usage.total_tokens:,} provider-reported tokens; completed "
                f"at `{manifest.completed_at}`."
            ),
        ]
    )
    return "\n\n".join(sections) + "\n"


def analyze_episodes(config: EpisodeAnalysisConfig) -> str:
    """Write the aggregate same-post analysis report."""
    report = render_episode_report(config)
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(report, encoding="utf-8")
    return report


@app.command()
def main(
    config_path: Path = typer.Option(..., exists=True, dir_okay=False),
    output: Path = typer.Option(..., dir_okay=False),
) -> None:
    """Generate the same-post 7,8-DHF episode report."""
    config = EpisodeAnalysisConfig.model_validate_json(
        config_path.read_text(encoding="utf-8")
    )
    analyze_episodes(config.model_copy(update={"output_path": output}))
    console.print(f"[green]Wrote[/green] {output}")


if __name__ == "__main__":
    app()
