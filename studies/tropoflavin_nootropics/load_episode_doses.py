"""Load same-post 7,8-DHF episode doses into a study database: one row per dose per report."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from studies.tropoflavin_nootropics.analyze_78dhf_episodes import load_episode_records
from studies.tropoflavin_nootropics.comparator_support import sha256_file
from studies.tropoflavin_nootropics.extract_78dhf_episodes import (
    EpisodeExtractionManifest,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()

DOSE_TABLE = "pipeline_a_doses"
DOSE_TABLE_DDL = f"""
CREATE TABLE {DOSE_TABLE} (
    report_id        INTEGER NOT NULL REFERENCES treatment_reports(report_id),
    ordinal          INTEGER NOT NULL,
    post_id          TEXT NOT NULL REFERENCES posts(post_id),
    user_id          TEXT NOT NULL REFERENCES users(user_id),
    drug_id          INTEGER NOT NULL REFERENCES treatment(id),
    low              REAL NOT NULL,
    high             REAL NOT NULL,
    unit             TEXT NOT NULL CHECK (unit IN ('mcg', 'mg', 'g')),
    route            TEXT,
    outcome          TEXT CHECK (outcome IN ('positive', 'negative', 'neutral', 'unclear')),
    quote            TEXT,
    PRIMARY KEY (report_id, ordinal)
)
"""
_REQUIRED_TABLES = frozenset({"treatment_reports", "posts", "users", "treatment"})


def load_episode_doses(
    database: Path,
    episode_records: Path,
    subreddit: str,
    episode_manifest: Path | None = None,
) -> int:
    """Replace ``pipeline_a_doses`` with one row per extracted dose per report.

    Rows are keyed on the source ``treatment_reports.report_id``; a record whose report
    is not in this database (or names a different post) aborts the load. When the
    database has a ``combined_pipeline_manifest`` table the load is registered there.
    """
    records = [
        record
        for record in load_episode_records(episode_records).values()
        if record.subreddit.casefold() == subreddit.casefold()
    ]
    if not records:
        raise ValueError(f"No episode records for subreddit {subreddit!r} in {episode_records}")
    details: dict[str, object] = {
        "records_sha256": sha256_file(episode_records),
        "episodes": len(records),
        "episodes_with_doses": sum(bool(record.doses) for record in records),
    }
    if episode_manifest is not None:
        manifest = EpisodeExtractionManifest.model_validate_json(
            episode_manifest.read_text(encoding="utf-8")
        )
        if manifest.records_sha256 != details["records_sha256"]:
            raise ValueError("Episode manifest does not describe this records file")
        details.update(
            prompt_file=manifest.prompt_file,
            prompt_sha256=manifest.prompt_sha256,
            provider=manifest.provider,
            model=manifest.model,
            code_commit=manifest.code_commit,
            max_single_dose_mg=manifest.max_single_dose_mg,
            require_dose_quotes=manifest.require_dose_quotes,
            dose_check_drops=manifest.dose_check_drops,
        )

    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        missing = sorted(_REQUIRED_TABLES - tables)
        if missing:
            raise ValueError(f"Database is missing tables: {', '.join(missing)}")
        reports = {
            int(row[0]): (str(row[1]), row[2], int(row[3]))
            for row in connection.execute(
                "SELECT report_id, post_id, user_id, drug_id FROM treatment_reports"
            )
        }
        rows: list[tuple[object, ...]] = []
        for record in records:
            source = reports.get(record.report_id)
            if source is None or source[0] != record.post_id:
                raise ValueError(
                    f"Episode record for post {record.post_id} (report {record.report_id}) "
                    "does not match a report in this database"
                )
            post_id, user_id, drug_id = source
            for ordinal, dose in enumerate(record.doses, 1):
                rows.append(
                    (
                        record.report_id,
                        ordinal,
                        post_id,
                        user_id or record.author_hash,
                        drug_id,
                        dose.low,
                        dose.high,
                        dose.unit,
                        dose.route,
                        dose.outcome,
                        dose.quote,
                    )
                )
        with connection:
            connection.execute(f"DROP TABLE IF EXISTS {DOSE_TABLE}")
            connection.execute(DOSE_TABLE_DDL)
            connection.execute(
                f"CREATE INDEX {DOSE_TABLE}_drug_idx ON {DOSE_TABLE}(drug_id, unit, low)"
            )
            connection.executemany(
                f"INSERT INTO {DOSE_TABLE} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
            )
            if "combined_pipeline_manifest" in tables:
                connection.execute(
                    "INSERT OR REPLACE INTO combined_pipeline_manifest VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        DOSE_TABLE,
                        "complete",
                        len(rows),
                        episode_records.name,
                        datetime.now(UTC).isoformat(),
                        json.dumps(details, sort_keys=True),
                    ),
                )
    return len(rows)


@app.command()
def main(
    database: Annotated[Path, typer.Option("--database", exists=True, dir_okay=False)],
    episode_records: Annotated[
        Path, typer.Option("--episode-records", exists=True, dir_okay=False)
    ],
    subreddit: Annotated[str, typer.Option("--subreddit")],
    episode_manifest: Annotated[
        Path | None, typer.Option("--episode-manifest", exists=True, dir_okay=False)
    ] = None,
) -> None:
    """Replace pipeline_a_doses with one row per extracted dose per report."""
    count = load_episode_doses(database, episode_records, subreddit, episode_manifest)
    console.print(f"[green]Loaded[/green] {count:,} dose rows into {database} ({DOSE_TABLE})")


if __name__ == "__main__":
    app()
