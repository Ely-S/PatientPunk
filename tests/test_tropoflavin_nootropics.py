from __future__ import annotations

import csv
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from studies.tropoflavin_nootropics.analyze_study_design import (
    render_study_design_report,
)
from studies.tropoflavin_nootropics.build_combined_db import (
    CombinedDatabaseConfig,
    build_combined_database,
)
from studies.tropoflavin_nootropics.study_support import (
    PipelineBRecord,
    StudyPaths,
    bind_strict_doses,
    canonical_side_effect,
    compound_for_treatment,
    desired_result_bucket,
    dose_band,
    linked_values,
    load_pipeline_b_records,
    parse_mass_dosage,
    readonly_sqlite_uri,
    route_bucket,
    summarize_target_dosages,
    summarize_target_values,
)


def _record(**updates: str) -> PipelineBRecord:
    values = {
        "author_hash": "author-1",
        "treatment_outcome": "",
        "dosage_treatment": "",
        "dosage_value": "",
        "administration_route_treatment": "",
        "administration_route_value": "",
    }
    values.update(updates)
    return PipelineBRecord.model_validate(values)


def test_loader_rejects_records_from_before_linked_fields(tmp_path: Path) -> None:
    path = tmp_path / "records.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["author_hash", "dosage"])
        writer.writeheader()
        writer.writerow({"author_hash": "author-1", "dosage": "5 mg"})

    with pytest.raises(
        ValueError, match=r"predates the linked dose/route schema.*Rerun pipeline B"
    ):
        load_pipeline_b_records(path)


def test_linked_values_preserve_alignment_and_reject_mismatch() -> None:
    record = _record(
        dosage_treatment="7,8-DHF | magnesium",
        dosage_value="5 mg | 200 mg",
    )
    assert [
        (pair.treatment, pair.value) for pair in linked_values(record, "dosage")
    ] == [
        ("7,8-DHF", "5 mg"),
        ("magnesium", "200 mg"),
    ]

    invalid = _record(dosage_treatment="7,8-DHF | magnesium", dosage_value="5 mg")
    with pytest.raises(ValueError, match="misaligned"):
        linked_values(invalid, "dosage")


def test_linked_values_preserve_empty_alignment_placeholders() -> None:
    record = _record(
        dosage_treatment="BPC-157 | ",
        dosage_value="250 mcg | 500 mcg",
    )

    assert [
        (pair.treatment, pair.value) for pair in linked_values(record, "dosage")
    ] == [("BPC-157", "250 mcg")]


def test_derivative_classification_takes_precedence_over_parent_alias() -> None:
    assert compound_for_treatment("4'-DMA-7,8-DHF") == "4'-DMA"
    assert compound_for_treatment("eutropoflavin") == "4'-DMA"
    assert compound_for_treatment("7,8-DHF") == "7,8-DHF"
    assert compound_for_treatment("magnesium") is None


def test_target_summaries_use_only_explicit_linked_pairs() -> None:
    records = [
        _record(
            author_hash="a",
            dosage_treatment="7,8-DHF | magnesium",
            dosage_value="5 mg | 200 mg",
            administration_route_treatment="7,8-DHF",
            administration_route_value="sublingual",
        ),
        _record(
            author_hash="b",
            dosage_treatment="4'-DMA-7,8-DHF",
            dosage_value="20 mg",
            administration_route_treatment="4'-DMA-7,8-DHF",
            administration_route_value="oral",
        ),
    ]

    doses = summarize_target_values(records, "dosage")
    routes = summarize_target_values(records, "administration_route")

    assert doses.counts["7,8-DHF"] == {"5 mg": 1}
    assert doses.counts["4'-DMA"] == {"20 mg": 1}
    assert doses.authors == {"7,8-DHF": {"a"}, "4'-DMA": {"b"}}
    assert routes.counts["7,8-DHF"] == {"sublingual": 1}
    assert routes.counts["4'-DMA"] == {"oral": 1}


def test_mass_dosages_are_canonicalized_and_non_mass_values_are_audited() -> None:
    assert parse_mass_dosage("50mg daily").label == "50 mg"
    assert parse_mass_dosage("100 mg - 200 mg").label == "100-200 mg"
    assert parse_mass_dosage("250-500 mcg").label == "0.25-0.5 mg"
    assert parse_mass_dosage("250 µg").label == "0.25 mg"
    assert parse_mass_dosage("250 μg").label == "0.25 mg"
    assert parse_mass_dosage("1 month per year") is None

    records = [
        _record(
            author_hash="a",
            dosage_treatment="7,8-DHF | 7,8-DHF",
            dosage_value="50mg daily | unspecified",
        ),
        _record(
            author_hash="b",
            dosage_treatment="4'-DMA-7,8-DHF | 4'-DMA-7,8-DHF",
            dosage_value="10 mg | 2 capsules",
        ),
    ]
    summary = summarize_target_dosages(records)

    assert summary.counts["7,8-DHF"] == {"50 mg": 1}
    assert summary.counts["4'-DMA"] == {"10 mg": 1}
    assert summary.excluded["7,8-DHF"] == {"unspecified": 1}
    assert summary.excluded["4'-DMA"] == {"2 capsules": 1}
    assert summary.midpoints_mg == {"7,8-DHF": [50.0], "4'-DMA": [10.0]}
    assert summary.author_midpoints_mg == {
        "7,8-DHF": {"a": [50.0]},
        "4'-DMA": {"b": [10.0]},
    }


def test_study_design_buckets_are_stable_and_interpretable() -> None:
    assert dose_band(4.99).label == "<5 mg"
    assert dose_band(5).label == "5 to <10 mg"
    assert dose_band(10).label == "10 to <25 mg"
    assert dose_band(25).label == "25 to <50 mg"
    assert dose_band(100).label == ">=100 mg"
    assert route_bucket("sublingual") == "oral mucosal"
    assert route_bucket("oral") == "swallowed oral"
    assert desired_result_bucket("better mood and depression") == "mood or depression"
    assert desired_result_bucket("post-exertional malaise after activity") == (
        "post-exertional malaise"
    )
    assert desired_result_bucket("persistent fatigue") == "general fatigue"
    assert desired_result_bucket("more energy and motivation") == "energy or motivation"
    assert desired_result_bucket("") == "unspecified"
    assert canonical_side_effect("sleep disruption") == (
        "insomnia or sleep disruption",
        "sleep",
    )
    assert canonical_side_effect("hair thinning") == (
        "hair loss or thinning",
        "hair or skin",
    )
    assert canonical_side_effect("PEM after activity") == (
        "post-exertional malaise or exertional crash",
        "fatigue or exertional intolerance",
    )
    assert canonical_side_effect("an unmatched verbatim phrase") == (
        "other reported effect",
        "other",
    )


def test_combined_database_preserves_pipeline_a_and_adds_queryable_pipeline_b(
    tmp_path: Path,
) -> None:
    source = tmp_path / "pipeline_a.db"
    with closing(sqlite3.connect(source)) as connection:
        connection.executescript(
            """
            CREATE TABLE users (
                user_id TEXT PRIMARY KEY,
                source_subreddit TEXT,
                scraped_at INTEGER
            );
            CREATE TABLE extraction_runs (
                run_id INTEGER PRIMARY KEY,
                run_at INTEGER,
                commit_hash TEXT,
                extraction_type TEXT,
                config TEXT
            );
            CREATE TABLE treatment (
                id INTEGER PRIMARY KEY,
                canonical_name TEXT NOT NULL
            );
            CREATE TABLE treatment_reports (
                report_id INTEGER PRIMARY KEY,
                run_id INTEGER,
                post_id TEXT,
                user_id TEXT,
                drug_id INTEGER,
                sentiment TEXT,
                signal_strength TEXT,
                side_effects TEXT
            );
            INSERT INTO users VALUES ('a', 'Nootropics', 1), ('b', 'Nootropics', 1);
            INSERT INTO extraction_runs VALUES (1, 1, 'abc', 'sentiment', '{}');
            INSERT INTO treatment VALUES (1, '7,8-dhf');
            INSERT INTO treatment_reports VALUES
                (1, 1, 'p1', 'a', 1, 'positive', 'strong', '["insomnia", "hair thinning"]');
            """
        )
        connection.commit()

    records = tmp_path / "records_normalized.csv"
    fieldnames = [
        "author_hash",
        "text_count",
        "treatment_outcome",
        "dosage_treatment",
        "dosage_value",
        "administration_route_treatment",
        "administration_route_value",
    ]
    with records.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(
            [
                {
                    "author_hash": "a",
                    "text_count": "3",
                    "treatment_outcome": "7,8-DHF: helped: mood",
                    "dosage_treatment": "7,8-DHF",
                    "dosage_value": "25 mg",
                    "administration_route_treatment": "7,8-DHF",
                    "administration_route_value": "sublingual",
                },
                {
                    "author_hash": "b",
                    "text_count": "2",
                    "treatment_outcome": "4'-DMA-7,8-DHF: no_effect: focus",
                    "dosage_treatment": "4'-DMA-7,8-DHF",
                    "dosage_value": "10 mg",
                    "administration_route_treatment": "4'-DMA-7,8-DHF",
                    "administration_route_value": "oral",
                },
            ]
        )

    output = tmp_path / "combined.db"
    report = build_combined_database(
        CombinedDatabaseConfig(
            source_database=source,
            pipeline_b_records=records,
            output_database=output,
            expected_pipeline_b_records=2,
            pipeline_b_run_name="test-run",
        )
    )

    assert report.pipeline_a_reports == 1
    assert report.pipeline_b_records == 2
    assert report.pipeline_b_compound_exposures == 2
    assert report.pipeline_a_side_effects == 2
    with closing(sqlite3.connect(source)) as connection:
        source_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert "pipeline_b_records" not in source_tables
    with closing(sqlite3.connect(output)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        exposure = connection.execute(
            """
            SELECT dose_band, route_bucket, conservative_outcome,
                   desired_result_buckets_json, dose_route_status
            FROM pipeline_b_compound_exposures
            WHERE author_hash = 'a' AND target_compound = '7,8-DHF'
            """
        ).fetchone()
        assert exposure == (
            "25 to <50 mg",
            "oral mucosal",
            "helped",
            '["mood or depression"]',
            "both single observations",
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM pipeline_a_side_effects"
            ).fetchone()[0]
            == 2
        )
        assert connection.execute(
            "SELECT DISTINCT drug_id, treatment FROM pipeline_a_side_effects"
        ).fetchall() == [(1, "7,8-dhf")]
    analysis = render_study_design_report(output)
    assert "## Dose and route co-observation" in analysis
    assert "25 to <50 mg" in analysis
    assert "oral mucosal" in analysis
    assert "mood or depression" in analysis
    assert "insomnia or sleep disruption" in analysis


def test_strict_binder_rejects_single_letter_intervening_compound() -> None:
    assert bind_strict_doses("I take 7,8-DHF 10 mg each morning") == [10.0]
    assert bind_strict_doses("I take 7,8-DHF and B 10 mg each morning") == []


def test_study_paths_are_absolute_and_sqlite_uri_is_read_only() -> None:
    paths = StudyPaths()
    assert paths.database.is_absolute()
    assert paths.records.is_absolute()
    assert readonly_sqlite_uri(paths.database).startswith("file:")
    assert readonly_sqlite_uri(paths.database).endswith("?mode=ro")
