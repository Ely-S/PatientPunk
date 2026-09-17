"""Contract tests for the 7,8-DHF comparator cohort workflow."""

from __future__ import annotations

import csv
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from studies.tropoflavin_nootropics.analyze_comparator_cohort import (
    ComparatorAnalysisConfig,
    _comparisons,
    _sentiment_summaries,
    render_comparator_report,
)
from studies.tropoflavin_nootropics.analyze_author_overlap import (
    AuthorOverlapConfig,
    CohortArtifact,
    render_author_overlap,
)
from studies.tropoflavin_nootropics.attribution import (
    corroborates_dose,
    corroborates_route,
)
from studies.tropoflavin_nootropics.build_comparator_corpus import (
    BuildComparatorCorpusConfig,
    build_comparator_corpus,
)
from studies.tropoflavin_nootropics.build_variable_corpus import (
    VariableCorpusConfig,
    build_variable_corpus,
)
from studies.tropoflavin_nootropics.comparator_support import (
    compound_for_treatment,
    load_comparator_cohort,
)
from studies.tropoflavin_nootropics.privacy import scan_aggregate_artifact
from studies.tropoflavin_nootropics.run_variable_pipeline import (
    calculate_missing_author_records,
    write_linked_records,
)
from studies.tropoflavin_nootropics.run_comparator_pipeline import (
    UsageSummary as SentimentUsageSummary,
)
from studies.tropoflavin_nootropics.run_comparator_pipeline import combine_usage


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
            subreddit="Nootropics",
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
    assert manifest.subreddit == "Nootropics"
    assert len(manifest.comments_sha256) == 64
    assert len(manifest.posts_sha256) == 64

    variable_manifest = build_variable_corpus(
        VariableCorpusConfig(
            subreddit="Nootropics",
            source_corpus=output,
            output_directory=tmp_path / "variable",
        )
    )
    assert variable_manifest.selected_authors == 3
    user_files = list((tmp_path / "variable" / "users").glob("*.json"))
    assert len(user_files) == 3
    assert all(path.stem != "deleted" for path in user_files)
    assert "alice" not in "".join(path.read_text(encoding="utf-8") for path in user_files)

    retained_database = tmp_path / "retained.db"
    retained_author = corpus[0]["author_hash"]
    with closing(sqlite3.connect(retained_database)) as connection:
        connection.execute("CREATE TABLE treatment_reports (user_id TEXT)")
        connection.execute(
            "INSERT INTO treatment_reports VALUES (?)",
            (retained_author,),
        )
        connection.commit()
    retained_manifest = build_variable_corpus(
        VariableCorpusConfig(
            subreddit="Nootropics",
            source_corpus=output,
            output_directory=tmp_path / "retained-variable",
            sentiment_database=retained_database,
        )
    )
    assert retained_manifest.selected_authors == 1
    assert retained_manifest.eligibility_basis == "retained comparator sentiment report"


def test_pipeline_b_mapping_covers_the_full_comparator_cohort() -> None:
    cohort = load_comparator_cohort()
    expected = {
        "7,8-DHF": "7,8-DHF",
        "eutropoflavin": "4'-DMA",
        "Semax": "Semax",
        "Cerebrolysin": "Cerebrolysin",
        "Selank": "Selank",
        "NSI-189": "NSI-189",
        "Dihexa": "Dihexa",
        "lion's mane": "Lion's mane",
        "9-MBC": "9-MBC",
        "BPC-157": "BPC-157",
    }
    assert {
        treatment: compound_for_treatment(treatment, cohort)
        for treatment in expected
    } == expected


def test_dose_and_route_require_nearby_same_segment_evidence() -> None:
    target = load_comparator_cohort().by_slug()["78dhf"]
    assert corroborates_dose(
        target,
        "10 mg",
        ("I took 10 mg of 7,8-DHF in the morning.",),
    )
    assert not corroborates_dose(
        target,
        "10 mg",
        ("I took 10 mg of something.", "Later I tried 7,8-DHF."),
    )
    assert corroborates_route(
        target,
        "sublingual",
        ("I used 7,8-DHF sublingually, under my tongue.",),
    )
    assert not corroborates_route(
        target,
        "oral",
        ("I used 7,8-DHF but did not describe the route.",),
    )


def test_parent_attribution_rejects_derivative_only_text() -> None:
    target = load_comparator_cohort().by_slug()["78dhf"]
    assert not corroborates_dose(
        target,
        "10 mg",
        ("I took 10 mg of 4'-DMA-7,8-DHF.",),
    )


def test_author_overlap_counts_global_hashes_and_excludes_deleted(
    tmp_path: Path,
) -> None:
    shared = "a" * 32
    first_only = "b" * 32
    second_only = "c" * 32
    paths = [tmp_path / "first.db", tmp_path / "second.db"]
    for path, authors in zip(
        paths,
        ((shared, first_only, "deleted"), (shared, second_only)),
        strict=True,
    ):
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE treatment_reports (user_id TEXT)")
            connection.executemany(
                "INSERT INTO treatment_reports VALUES (?)",
                [(author,) for author in authors],
            )
            connection.commit()
    report = render_author_overlap(
        AuthorOverlapConfig(
            cohorts=(
                CohortArtifact(subreddit="First", sentiment_database=paths[0]),
                CohortArtifact(subreddit="Second", sentiment_database=paths[1]),
            ),
            output_path=tmp_path / "overlap.md",
        )
    )
    assert "| First | 2 | 1 |" in report
    assert "| Second | 1 | 2 |" in report
    assert shared not in report
    assert "| deleted |" not in report.casefold()


def test_aggregate_artifact_privacy_scan_blocks_paths_and_author_hashes(
    tmp_path: Path,
) -> None:
    safe = tmp_path / "safe.md"
    safe.write_text("# Aggregate\n\nAuthors: 12\n", encoding="utf-8")
    assert scan_aggregate_artifact(safe) == ()

    unsafe = tmp_path / "unsafe.md"
    unsafe.write_text(
        "C:\\Users\\person\\data.db\n" + "a" * 32 + "\n",
        encoding="utf-8",
    )
    findings = scan_aggregate_artifact(unsafe)
    assert {finding.rule for finding in findings} == {
        "Windows user path",
        "author-sized hexadecimal identifier",
    }

    raw_effect = tmp_path / "raw-effect.md"
    raw_effect.write_text(
        "| Compound | Canonical effect | Safety domain | Authors |\n"
        "|---|---|---|---|\n"
        "| 7,8-DHF | unmatched verbatim wording | other | 1 |\n",
        encoding="utf-8",
    )
    assert {finding.rule for finding in scan_aggregate_artifact(raw_effect)} == {
        "noncanonical side-effect wording"
    }


def test_linked_records_export_adds_aligned_dose_and_route_columns(
    tmp_path: Path,
) -> None:
    source = tmp_path / "records.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["author_hash", "dosage", "administration_route"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "author_hash": "a" * 32,
                "dosage": "7,8-DHF: 10 mg",
                "administration_route": "7,8-DHF: sublingual",
            }
        )
    output = tmp_path / "records_linked.csv"
    assert write_linked_records(source, output) == 1
    with output.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["dosage_treatment"] == "7,8-DHF"
    assert row["dosage_value"] == "10 mg"
    assert row["administration_route_treatment"] == "7,8-DHF"
    assert row["administration_route_value"] == "sublingual"


def test_variable_pipeline_requires_exact_retained_author_coverage() -> None:
    assert calculate_missing_author_records(10, 10) == 0
    assert calculate_missing_author_records(8, 10) == 2
    with pytest.raises(ValueError, match="more records than selected"):
        calculate_missing_author_records(11, 10)


def test_sentiment_resume_preserves_prior_provider_usage() -> None:
    combined = combine_usage(
        SentimentUsageSummary(
            requests=4,
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
        ),
        SentimentUsageSummary(
            requests=2,
            prompt_tokens=50,
            completion_tokens=10,
            total_tokens=60,
        ),
    )
    assert combined.model_dump() == {
        "requests": 6,
        "prompt_tokens": 150,
        "completion_tokens": 30,
        "total_tokens": 180,
    }


def test_comparison_direction_and_exclusive_author_sets_are_consistent() -> None:
    cohort = load_comparator_cohort()

    def vote(user: str, drug: str, sentiment: str) -> dict[str, object]:
        return {
            "user_id": user,
            "drug": drug,
            "post_id": f"{drug}-{user}",
            "sentiment": sentiment,
            "signal": "strong",
            "post_date": 1,
            "run_id": 1,
        }

    votes = {
        "78dhf": {
            "shared": vote("shared", "78dhf", "positive"),
            "target-only": vote("target-only", "78dhf", "positive"),
        },
        "semax": {
            "shared": vote("shared", "semax", "negative"),
            "comparator-only": vote("comparator-only", "semax", "negative"),
        },
    }
    summaries = _sentiment_summaries(cohort, votes)  # type: ignore[arg-type]
    comparisons = {row.slug: row for row in _comparisons(cohort, votes, summaries)}  # type: ignore[arg-type]
    semax = comparisons["semax"]

    assert semax.rate_difference == 1.0
    assert semax.odds_ratio == float("inf")
    assert semax.exclusive_target_authors == 1
    assert semax.exclusive_comparator_authors == 1
    assert semax.matched_authors == 1


def _create_sentiment_database(path: Path) -> None:
    schema = Path("schema.sql").read_text(encoding="utf-8")
    with closing(sqlite3.connect(path)) as connection:
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
        connection.commit()


def _create_study_database(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection:
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
            INSERT INTO pipeline_b_dosages VALUES ('u2', '7,8-DHF', '25 to <50 mg', 3);
            INSERT INTO pipeline_b_dosages VALUES ('u3', '7,8-DHF', '25 to <50 mg', 3);
            INSERT INTO pipeline_b_administration_routes
                VALUES ('u1', '7,8-DHF', 'oral mucosal', 'sublingual');
            INSERT INTO pipeline_b_administration_routes
                VALUES ('u2', '7,8-DHF', 'oral mucosal', 'sublingual');
            INSERT INTO pipeline_b_administration_routes
                VALUES ('u3', '7,8-DHF', 'oral mucosal', 'sublingual');
            INSERT INTO pipeline_b_treatment_outcomes
                VALUES ('u1', '7,8-DHF', 'post-exertional malaise', 'helped');
            """
        )
        connection.commit()


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
            subreddit="Nootropics",
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
    assert "| 7,8-DHF | 25 to <50 mg | 3 | 3 | 2/3 | 2/3 (66.7%;" in report
    assert "insomnia or sleep disruption: 1/3 (33.3%)" in report
    assert "cross-report associations" in report
    assert "7,8-DHF minus comparator" in report
    assert "Exclusive 7,8-DHF authors" in report
    assert "Matched BH q" in report
    assert str(tmp_path.resolve()) not in report
    assert "SHA-256" in report
