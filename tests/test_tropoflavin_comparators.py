"""Contract tests for the 7,8-DHF comparator cohort workflow."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from studies.tropoflavin_nootropics.analyze_comparator_cohort import (
    ComparatorAnalysisConfig,
    render_comparator_report,
)
from studies.tropoflavin_nootropics.build_comparator_corpus import (
    BuildComparatorCorpusConfig,
    build_comparator_corpus,
)
from studies.tropoflavin_nootropics.comparator_support import (
    load_comparator_cohort,
)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def test_corpus_builder_separates_parent_from_derivative_and_hashes_authors(
    tmp_path: Path,
) -> None:
    posts_path = tmp_path / "posts.jsonl"
    comments_path = tmp_path / "comments.jsonl"
    _write_jsonl(
        posts_path,
        [
            {
                "id": "p1",
                "title": "My 7,8-DHF experience",
                "selftext": "parent compound only",
                "author": "alice",
                "created_utc": 100,
                "score": 1,
                "permalink": "/r/Nootropics/comments/p1/x/",
                "num_comments": 1,
            },
            {
                "id": "p2",
                "title": "4'-DMA-7,8-DHF report",
                "selftext": "derivative only",
                "author": "bob",
                "created_utc": 200,
                "score": 2,
                "permalink": "/r/Nootropics/comments/p2/x/",
                "num_comments": 1,
            },
        ],
    )
    _write_jsonl(
        comments_path,
        [
            {
                "id": "c1",
                "link_id": "t3_p1",
                "parent_id": "t3_p1",
                "body": "Semax was mentioned in the same thread",
                "author": "carol",
                "created_utc": 101,
                "score": 3,
            },
            {
                "id": "c2",
                "link_id": "t3_p2",
                "parent_id": "t3_p2",
                "body": "I only mean 4'-DMA-7,8-DHF",
                "author": "alice",
                "created_utc": 201,
                "score": 4,
            },
        ],
    )

    output = tmp_path / "corpus.json"
    manifest = build_comparator_corpus(
        BuildComparatorCorpusConfig(
            comments_path=comments_path,
            posts_path=posts_path,
            output_path=output,
        )
    )

    counts = {summary.slug: summary.matching_items for summary in manifest.matches}
    assert counts["78dhf"] == 1
    assert counts["4dma-78dhf"] == 2
    assert counts["semax"] == 1
    corpus = json.loads(output.read_text(encoding="utf-8"))
    assert {post["post_id"] for post in corpus} == {"p1", "p2"}
    serialized = output.read_text(encoding="utf-8")
    assert "alice" not in serialized
    assert "bob" not in serialized
    assert "carol" not in serialized
    assert (tmp_path / "corpus.manifest.json").is_file()


def _create_sentiment_database(path: Path) -> None:
    schema = Path("schema.sql").read_text(encoding="utf-8")
    with sqlite3.connect(path) as connection:
        connection.executescript(schema)
        connection.executemany(
            "INSERT INTO users VALUES (?, 'Nootropics', 1)",
            [("u1",), ("u2",), ("u3",)],
        )
        connection.executemany(
            "INSERT INTO posts VALUES (?, NULL, NULL, ?, '', NULL, ?, 1, NULL)",
            [("p1", "u1", 1), ("p2", "u2", 2), ("p3", "u1", 3), ("p4", "u3", 4)],
        )
        connection.executemany(
            "INSERT INTO treatment (id, canonical_name) VALUES (?, ?)",
            [(1, "7,8-dhf"), (2, "semax"), (3, "4'-dma-7,8-dhf")],
        )
        connection.execute(
            "INSERT INTO extraction_runs VALUES (1, 1, 'abc', 'treatment_sentiment', '{}')"
        )
        connection.executemany(
            """
            INSERT INTO treatment_reports
                (run_id, post_id, user_id, drug_id, sentiment, signal_strength, side_effects)
            VALUES (1, ?, ?, ?, ?, 'strong', ?)
            """,
            [
                ("p1", "u1", 1, "positive", '["insomnia"]'),
                ("p2", "u2", 1, "negative", '["nausea"]'),
                ("p3", "u1", 2, "negative", '["headache"]'),
                ("p4", "u3", 2, "positive", None),
            ],
        )


def _create_study_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE pipeline_b_dosages (
                author_hash TEXT, target_compound TEXT, dose_band TEXT,
                dose_band_order INTEGER
            );
            CREATE TABLE pipeline_b_administration_routes (
                author_hash TEXT, target_compound TEXT, route_bucket TEXT,
                route TEXT
            );
            CREATE TABLE pipeline_b_treatment_outcomes (
                author_hash TEXT, target_compound TEXT,
                desired_result_bucket TEXT, outcome TEXT
            );
            INSERT INTO pipeline_b_dosages VALUES ('u1', '7,8-DHF', '25 to <50 mg', 3);
            INSERT INTO pipeline_b_administration_routes
                VALUES ('u1', '7,8-DHF', 'oral mucosal', 'sublingual');
            INSERT INTO pipeline_b_treatment_outcomes
                VALUES ('u1', '7,8-DHF', 'post-exertional malaise', 'helped');
            """
        )


def test_report_is_aggregate_treatment_linked_and_reproducible(tmp_path: Path) -> None:
    sentiment_database = tmp_path / "sentiment.db"
    study_database = tmp_path / "study.db"
    _create_sentiment_database(sentiment_database)
    _create_study_database(study_database)
    cohort = load_comparator_cohort()
    assert cohort.target.matches("7,8-DHF helped me")
    assert not cohort.target.matches("4'-DMA-7,8-DHF helped me")

    report = render_comparator_report(
        ComparatorAnalysisConfig(
            sentiment_database=sentiment_database,
            study_database=study_database,
            output_path=tmp_path / "report.md",
        )
    )

    assert "| 7,8-DHF | target | target | 2 | 1 | 1 |" in report
    assert "| Semax | BDNF/TrkB related | primary | 2 | 1 | 1 |" in report
    assert "insomnia or sleep disruption" in report
    assert "post-exertional malaise" in report
    assert "Explicit PEM target coverage: 1 treatment-linked outcome entry." in report
    assert "25 to <50 mg" in report
    assert str(tmp_path.resolve()) not in report
    assert "SHA-256" in report
