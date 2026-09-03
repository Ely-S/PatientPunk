"""Generate an aggregate dose, route, efficacy, and safety planning report."""

from __future__ import annotations

import math
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Iterable, Sequence

import typer
from rich.console import Console

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()
_OUTCOME_RANK = {
    "worsened": 4,
    "no_effect": 3,
    "mixed": 2,
    "helped": 1,
    "unknown": 0,
}


def _percent(numerator: int, denominator: int) -> str:
    return f"{100 * numerator / denominator:.1f}%" if denominator else "n/a"


def _wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if not total:
        return float("nan"), float("nan")
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt((proportion * (1 - proportion) + z * z / (4 * total)) / total)
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def _table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    materialized = [[str(value) for value in row] for row in rows]
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in materialized)
    return "\n".join(lines)


def _dose_rows(connection: sqlite3.Connection) -> list[list[object]]:
    observations = {
        (row[0], row[1]): (row[3], row[4], row[2])
        for row in connection.execute(
            """
            SELECT target_compound, dose_band, dose_band_order,
                   COUNT(*) AS observations, COUNT(DISTINCT author_hash) AS authors
            FROM pipeline_b_dosages
            WHERE target_compound IS NOT NULL
            GROUP BY target_compound, dose_band, dose_band_order
            """
        )
    }
    outcomes = {
        (row[0], row[1]): row[2:]
        for row in connection.execute(
            """
            SELECT target_compound, dose_band, COUNT(*) AS outcome_authors,
                   SUM(conservative_outcome = 'helped') AS helped,
                   SUM(conservative_outcome = 'no_effect') AS no_effect,
                   SUM(conservative_outcome = 'worsened') AS worsened
            FROM pipeline_b_compound_exposures
            WHERE dose_band_order IS NOT NULL
              AND conservative_outcome != 'not reported'
            GROUP BY target_compound, dose_band, dose_band_order
            """
        )
    }
    rows = []
    for key, (observation_count, author_count, order) in sorted(
        observations.items(), key=lambda item: (item[0][0], item[1][2] or 0)
    ):
        outcome_authors, helped, no_effect, worsened = outcomes.get(key, (0, 0, 0, 0))
        rows.append(
            [
                key[0],
                key[1],
                observation_count,
                author_count,
                outcome_authors,
                helped,
                no_effect,
                worsened,
                _percent(helped, outcome_authors),
            ]
        )
    return rows


def _route_rows(connection: sqlite3.Connection) -> list[list[object]]:
    observations = {
        (row[0], row[1]): (row[2], row[3])
        for row in connection.execute(
            """
            SELECT target_compound, route_bucket, COUNT(*) AS observations,
                   COUNT(DISTINCT author_hash) AS authors
            FROM pipeline_b_administration_routes
            WHERE target_compound IS NOT NULL
            GROUP BY target_compound, route_bucket
            """
        )
    }
    outcomes = {
        (row[0], row[1]): row[2:]
        for row in connection.execute(
            """
            SELECT target_compound, route_bucket, COUNT(*) AS outcome_authors,
                   SUM(conservative_outcome = 'helped') AS helped,
                   SUM(conservative_outcome = 'no_effect') AS no_effect,
                   SUM(conservative_outcome = 'worsened') AS worsened
            FROM pipeline_b_compound_exposures
            WHERE route_bucket NOT IN ('not reported', 'multiple route families')
              AND conservative_outcome != 'not reported'
            GROUP BY target_compound, route_bucket
            """
        )
    }
    rows = []
    for key, (observation_count, author_count) in sorted(observations.items()):
        outcome_authors, helped, no_effect, worsened = outcomes.get(key, (0, 0, 0, 0))
        rows.append(
            [
                key[0],
                key[1],
                observation_count,
                author_count,
                outcome_authors,
                helped,
                no_effect,
                worsened,
                _percent(helped, outcome_authors),
            ]
        )
    return rows


def _efficacy_rows(connection: sqlite3.Connection) -> list[list[object]]:
    grouped: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for author, compound, desired_result, outcome in connection.execute(
        """
        SELECT author_hash, target_compound, desired_result_bucket, outcome
        FROM pipeline_b_treatment_outcomes
        WHERE target_compound IS NOT NULL
          AND desired_result_bucket != 'unspecified'
        """
    ):
        grouped[(author, compound, desired_result)].append(outcome)
    summaries: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for (_, compound, desired_result), outcomes in grouped.items():
        conservative = max(outcomes, key=lambda value: _OUTCOME_RANK[value])
        summaries[(compound, desired_result)][conservative] += 1

    rows: list[list[object]] = []
    for (compound, desired_result), counts in sorted(
        summaries.items(), key=lambda item: (item[0][0], -item[1].total(), item[0][1])
    ):
        total = counts.total()
        helped = counts["helped"]
        low, high = _wilson(helped, total)
        rows.append(
            [
                compound,
                desired_result,
                total,
                helped,
                counts["no_effect"],
                counts["worsened"],
                counts["mixed"] + counts["unknown"],
                _percent(helped, total),
                f"{100 * low:.1f}% to {100 * high:.1f}%",
            ]
        )
    return rows


def render_study_design_report(database: Path) -> str:
    """Render aggregate study-planning tables from a combined database."""
    uri = f"{database.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError(f"Database integrity check failed: {integrity}")
        manifest = list(
            connection.execute(
                """
                SELECT pipeline, status, record_count, source_artifact
                FROM combined_pipeline_manifest ORDER BY pipeline
                """
            )
        )
        dose_rows = _dose_rows(connection)
        route_rows = _route_rows(connection)
        pairing_rows = list(
            connection.execute(
                """
                SELECT target_compound, dose_route_status, COUNT(*)
                FROM pipeline_b_compound_exposures
                GROUP BY target_compound, dose_route_status
                ORDER BY target_compound, dose_route_status
                """
            )
        )
        efficacy_rows = _efficacy_rows(connection)
        pipeline_a_users = connection.execute(
            "SELECT COUNT(DISTINCT user_id) FROM treatment_reports"
        ).fetchone()[0]
        pipeline_a_reports = connection.execute(
            "SELECT COUNT(*) FROM treatment_reports"
        ).fetchone()[0]
        side_effect_users = connection.execute(
            "SELECT COUNT(DISTINCT user_id) FROM pipeline_a_side_effects"
        ).fetchone()[0]
        side_effect_reports = connection.execute(
            "SELECT COUNT(DISTINCT report_id) FROM pipeline_a_side_effects"
        ).fetchone()[0]
        side_effect_buckets = list(
            connection.execute(
                """
                SELECT side_effect_bucket, COUNT(DISTINCT user_id), COUNT(*)
                FROM pipeline_a_side_effects
                GROUP BY side_effect_bucket
                ORDER BY COUNT(DISTINCT user_id) DESC, side_effect_bucket
                """
            )
        )
        canonical_side_effects = list(
            connection.execute(
                """
                SELECT canonical_side_effect, side_effect_bucket,
                       COUNT(DISTINCT user_id), COUNT(*)
                FROM pipeline_a_side_effects
                GROUP BY canonical_side_effect, side_effect_bucket
                ORDER BY COUNT(DISTINCT user_id) DESC, COUNT(*) DESC
                LIMIT 15
                """
            )
        )

    generated = datetime.now(UTC).isoformat()
    sections = [
        "# 7,8-DHF and 4'-DMA study-planning analysis",
        "",
        f"Generated from `{database.name}` at {generated}.",
        "",
        "## Interpretation boundary",
        "",
        "These are retrospective self-reports from a healthy-user nootropics community. "
        "They estimate reporting patterns, not incidence, efficacy, safe dose, or causal "
        "dose-response. Dose and route are linked to a compound, but usually not to the "
        "same administration event. The combined exposure table therefore preserves "
        "ambiguity instead of pairing observations by position.",
        "",
        "## Data completeness",
        "",
        _table(["Pipeline", "Status", "Rows", "Source"], manifest),
        "",
        "## Dose",
        "",
        "Quantitative mass doses use midpoint-based bands: <5, 5 to <10, 10 to <25, "
        "25 to <50, 50 to <100, and >=100 mg. Raw values and range endpoints remain in "
        "the database. `Outcome authors` includes only authors with both a dose band and "
        "a compound-specific outcome, so the efficacy columns are exploratory.",
        "",
        _table(
            [
                "Compound",
                "Dose band",
                "Dose observations",
                "Dose authors",
                "Outcome authors",
                "Helped",
                "No effect",
                "Worsened",
                "Helped share",
            ],
            dose_rows,
        ),
        "",
        "## Route",
        "",
        "Routes are grouped by pharmacologically meaningful family while retaining the "
        "exact controlled-vocabulary value. Oral mucosal means sublingual or buccal; "
        "swallowed oral remains separate.",
        "",
        _table(
            [
                "Compound",
                "Route family",
                "Route observations",
                "Route authors",
                "Outcome authors",
                "Helped",
                "No effect",
                "Worsened",
                "Helped share",
            ],
            route_rows,
        ),
        "",
        "## Dose and route co-observation",
        "",
        _table(["Compound", "Status", "Author-compound rows"], pairing_rows),
        "",
        "Only `both single observations` rows have one explicit dose and one explicit "
        "route for the same author and compound. Even there, the source does not prove "
        "they describe the same administration event.",
        "",
        "## Efficacy by explicitly stated desired result",
        "",
        "Each author contributes one conservative vote per compound and result domain. "
        "When several statements exist, worsened outranks no_effect, mixed, helped, and "
        "unknown. Unspecified targets are excluded. This target-label requirement favors "
        "positive reports because people often name what improved but describe nulls as "
        "simply doing nothing.",
        "",
        _table(
            [
                "Compound",
                "Result domain",
                "Authors",
                "Helped",
                "No effect",
                "Worsened",
                "Mixed/unknown",
                "Helped share",
                "95% Wilson CI",
            ],
            efficacy_rows,
        ),
        "",
        "## Side effects",
        "",
        f"Pipeline A contains {pipeline_a_reports:,} reports from {pipeline_a_users:,} "
        f"users. Side effects were explicitly reported in {side_effect_reports:,} reports "
        f"from {side_effect_users:,} users ({_percent(side_effect_users, pipeline_a_users)}). "
        "This is a reporting proportion, not adverse-event incidence. Pipeline A can mix "
        "7,8-DHF with 4'-DMA and context-inherited mentions, so these safety signals are "
        "not compound-specific.",
        "",
        _table(
            [
                "Safety domain",
                "Distinct users",
                "Mentions",
                "Share of Pipeline A users",
            ],
            [
                [bucket, users, mentions, _percent(users, pipeline_a_users)]
                for bucket, users, mentions in side_effect_buckets
            ],
        ),
        "",
        _table(
            ["Canonical side effect", "Safety domain", "Distinct users", "Mentions"],
            canonical_side_effects,
        ),
        "",
        "## Proposed-study implications",
        "",
        "1. Treat the parent and derivative as separate investigational products. Their "
        "reported dose distributions differ materially, and the derivative has only "
        "preclinical pharmacology.",
        "2. Fix formulation and route within an early protocol. Sublingual reports dominate, "
        "but route-specific exposure is unknown and oral transport evidence is preclinical.",
        "3. Use the observed dose bands for case-report forms and stratified recruitment, "
        "not for selecting a starting dose. A regulated first-in-human program needs "
        "toxicology, chemistry and manufacturing controls, pharmacokinetics, sentinel "
        "dosing, and stopping rules.",
        "4. Pre-specify mood/depression, focus/attention, energy/motivation, cognition, "
        "and sleep endpoints. Sleep needs bidirectional measurement because it appears "
        "as both a desired result and the leading safety signal.",
        "5. Safety monitoring should prioritize sleep disruption, activation/anxiety, "
        "headache and cognitive/perceptual effects, fatigue/sedation, appetite, hair/skin, "
        "and cardiovascular/autonomic symptoms. Medication-interaction screening is also "
        "important because in-vitro CYP inhibition has been reported for 7,8-DHF.",
        "",
        "## External evidence boundary",
        "",
        "Searches of ClinicalTrials.gov and PubMed on 2026-08-27 did not identify a human "
        "interventional trial of 7,8-DHF or 4'-DMA-7,8-DHF. The directly relevant literature "
        "located was preclinical or in vitro:",
        "",
        "- 7,8-DHF showed poor transport and active efflux in a human intestinal Caco-2 model: "
        "https://pubmed.ncbi.nlm.nih.gov/31384856/",
        "- 7,8-DHF inhibited CYP2C9, CYP2C19, and CYP3A4 in vitro: "
        "https://pubmed.ncbi.nlm.nih.gov/31731555/",
        "- 7,8-DHF and 4'-DMA were tested in a Huntington disease mouse model, not humans: "
        "https://pubmed.ncbi.nlm.nih.gov/23446639/",
        "",
        "The Reddit data should therefore be used to design measurements and safety "
        "surveillance, not to justify human dosing.",
        "",
    ]
    return "\n".join(sections)


@app.command()
def main(
    database: Annotated[
        Path,
        typer.Option("--database", exists=True, dir_okay=False, readable=True),
    ],
    output: Annotated[Path, typer.Option("--output", dir_okay=False)],
) -> None:
    """Write an aggregate proposed-study analysis as Markdown."""
    report = render_study_design_report(database)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    console.print(f"[green]Wrote[/green] {output}")


if __name__ == "__main__":
    app()
