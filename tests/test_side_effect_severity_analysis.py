from __future__ import annotations

import csv
import sqlite3
from contextlib import closing
from pathlib import Path

from studies.tropoflavin_nootropics.analyze_side_effect_severity import (
    SeverityAnalysisConfig,
    analyze_side_effect_severity,
)


def test_severity_analysis_deduplicates_and_links_exposures(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    community = run_root / "Nootropics"
    community.mkdir(parents=True)
    database = community / "sentiment.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript(
            """
            CREATE TABLE treatment (id INTEGER PRIMARY KEY, canonical_name TEXT);
            CREATE TABLE treatment_reports (
                report_id INTEGER PRIMARY KEY, user_id TEXT, drug_id INTEGER,
                side_effects TEXT
            );
            CREATE TABLE pipeline_b_compound_exposures (
                author_hash TEXT, target_compound TEXT, dose_band TEXT,
                route_bucket TEXT
            );
            INSERT INTO treatment VALUES (1, '7,8-dhf');
            INSERT INTO treatment_reports VALUES
                (1, 'author-a', 1,
                 '[{"side_effect":"headache","severity":"mild"}]'),
                (2, 'author-a', 1,
                 '[{"side_effect":"headaches","severity":"severe"}]'),
                (3, 'author-b', 1,
                 '[{"side_effect":"insomnia","severity":null}]');
            INSERT INTO pipeline_b_compound_exposures VALUES
                ('author-a', '7,8-DHF', '25 to <50 mg', 'oral mucosal'),
                ('author-b', '7,8-DHF', '25 to <50 mg', 'oral mucosal');
            """
        )

    output = tmp_path / "output"
    report = analyze_side_effect_severity(
        SeverityAnalysisConfig(
            run_root=run_root,
            output_directory=output,
            min_stratified_authors=1,
        )
    )

    assert report.is_file()
    with (output / "side_effect_severity_by_compound.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    combined = next(
        row
        for row in rows
        if row["scope"] == "all communities, globally deduplicated"
        and row["compound"] == "7,8-DHF"
    )
    assert combined["authors"] == "2"
    assert combined["authors_with_any_side_effect"] == "2"
    assert combined["authors_with_explicit_severity"] == "1"
    assert combined["authors_with_explicit_severe_or_worse"] == "1"
    dose_route = (output / "side_effect_severity_by_dose_route.csv").read_text()
    assert "25 to <50 mg | oral mucosal" in dose_route


def test_severity_analysis_prefers_normalized_current_pipeline_tables(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    community = run_root / "Nootropics"
    community.mkdir(parents=True)
    database = community / "sentiment.db"
    schema = Path("schema.sql").read_text(encoding="utf-8")
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript(schema)
        connection.executemany(
            "INSERT INTO users VALUES (?, 'Nootropics', 1)",
            [("author-a",), ("author-b",)],
        )
        connection.executemany(
            "INSERT INTO posts VALUES (?, NULL, NULL, ?, '', NULL, 1, 1, NULL)",
            [("post-a", "author-a"), ("post-b", "author-b")],
        )
        connection.execute(
            "INSERT INTO treatment (id, canonical_name) VALUES (1, '7,8-dhf')"
        )
        connection.executemany(
            "INSERT INTO extraction_runs VALUES (?, 1, 'abc', ?, '{}', 2)",
            [
                (1, "treatment_sentiment"),
                (2, "report_doses"),
                (3, "report_effects"),
            ],
        )
        connection.executemany(
            """
            INSERT INTO treatment_reports
                (report_id, run_id, post_id, user_id, drug_id, sentiment,
                 signal_strength, side_effects)
            VALUES (?, 1, ?, ?, 1, 'positive', 'strong', ?)
            """,
            [
                (1, "post-a", "author-a", '["old severe nausea"]'),
                (2, "post-a", "author-a", '["legacy nausea"]'),
                (3, "post-b", "author-b", None),
            ],
        )
        connection.executemany(
            "INSERT INTO report_runs VALUES (?, ?)",
            [(2, 2), (2, 3), (3, 2), (3, 3)],
        )
        connection.executemany(
            """
            INSERT INTO report_doses
                (report_id, run_id, ordinal, low, high, unit, route, outcome, quote)
            VALUES (?, 2, 0, ?, ?, ?, ?, NULL, 'dose quote')
            """,
            [
                (2, 25.0, 25.0, "mg", "oral mucosal"),
                (3, None, None, None, "injection"),
            ],
        )
        connection.executemany(
            """
            INSERT INTO report_effects
                (report_id, run_id, ordinal, domain, symptom, direction,
                 severity, attribution, quote, dose_id)
            VALUES (?, 3, ?, 'other specified effect', ?, ?, ?, ?, 'effect quote', NULL)
            """,
            [
                (2, 0, "headache", "worsened", "moderate", "target"),
                (2, 1, "insomnia", "improved", None, "target"),
                (2, 2, "anxiety", "worsened", "severe", "stack"),
                (3, 0, "insomnia", "worsened", "severe", "target"),
            ],
        )
        connection.commit()

    output = tmp_path / "output"
    analyze_side_effect_severity(
        SeverityAnalysisConfig(
            run_root=run_root,
            output_directory=output,
            min_stratified_authors=1,
        )
    )

    with (output / "side_effect_severity_by_compound.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    combined = next(
        row
        for row in rows
        if row["scope"] == "all communities, globally deduplicated"
        and row["compound"] == "7,8-DHF"
    )
    assert combined["authors"] == "2"
    assert combined["authors_with_any_side_effect"] == "2"
    assert combined["authors_with_explicit_severity"] == "2"
    assert combined["authors_with_explicit_severe_or_worse"] == "1"

    effects = (output / "side_effect_severity_by_effect.csv").read_text(
        encoding="utf-8"
    )
    assert "headache or migraine" in effects
    assert "insomnia or sleep disruption" in effects
    assert "legacy nausea" not in effects
    dose_route = (output / "side_effect_severity_by_dose_route.csv").read_text(
        encoding="utf-8"
    )
    assert "25 to <50 mg | oral mucosal" in dose_route
    assert "parenteral" in dose_route
