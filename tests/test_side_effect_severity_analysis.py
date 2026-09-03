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
