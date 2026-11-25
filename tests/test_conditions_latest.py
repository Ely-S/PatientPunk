"""condition_observations and conditions_latest (#220), and the condition filter that reads them. Made-up data."""
from pathlib import Path

import pytest

from patientpunk.db import apply_schema, init_db, query_treatment_outcomes, register_run

SCHEMA = Path(__file__).resolve().parents[1] / "schema.sql"


@pytest.fixture
def conn(tmp_path):
    conn = init_db(tmp_path / "t.db", SCHEMA)
    conn.executemany("INSERT INTO users VALUES (?, 'cfs', 0)", [("a",), ("b",), ("c",)])
    conn.executemany("INSERT INTO posts (post_id, user_id, body_text, post_date, scraped_at) VALUES (?, ?, '', ?, 0)",
                     [("a1", "a", 1), ("a2", "a", 2), ("b1", "b", 1), ("c1", "c", 1)])
    conn.execute("INSERT INTO treatment (id, canonical_name) VALUES (1, 'ldn')")
    return conn


def observe(conn, run_id, post_id, user, name, severity=None):
    conn.execute("INSERT OR IGNORE INTO post_runs VALUES (?, ?)", (run_id, post_id))
    conn.execute("INSERT INTO conditions (run_id, user_id, post_id, condition_name, condition_type, severity, evidence)"
                 " VALUES (?, ?, ?, ?, 'illness', ?, 'quote')", (run_id, user, post_id, name, severity))


def test_latest_keeps_the_newest_stated_severity_and_when_it_was_mentioned(conn):
    r = register_run(conn, "demographics", {})
    observe(conn, r, "a1", "a", "pots", "severe"), observe(conn, r, "a2", "a", "pots")  # a2 doesn't say
    assert conn.execute("SELECT user_id, condition_name, severity, first_seen, last_seen, n_posts "
                        "FROM conditions_latest").fetchall() == [("a", "pots", "severe", 1, 2, 2)]


@pytest.mark.parametrize("severities, latest", [
    (("resolved", None), None),  # gone, then mentioned again: back, severity unknown
    ((None, "resolved"), "resolved"),  # resolved in the newest mention
    (("resolved", "severe"), "severe"),  # back and stated
    (("severe", None), "severe"),
])
def test_a_condition_mentioned_after_it_resolved_is_back(conn, severities, latest):
    r = register_run(conn, "demographics", {})
    for post_id, severity in zip(("a1", "a2"), severities):
        observe(conn, r, post_id, "a", "pots", severity)
    assert conn.execute("SELECT severity, n_posts FROM conditions_latest").fetchall() == [(latest, 2)]


@pytest.mark.parametrize("dates, latest", [
    ((None, 2), None),  # resolved in an undated post, then mentioned in a dated one: back
    ((2, None), "resolved"),  # an undated mention can't be placed after a dated resolution
    ((None, None), "resolved"),  # nothing dated: the stated resolution stands
])
def test_an_undated_resolution_is_superseded_by_a_dated_mention(conn, dates, latest):
    conn.execute("UPDATE posts SET post_date = ? WHERE post_id = 'a1'", (dates[0],))
    conn.execute("UPDATE posts SET post_date = ? WHERE post_id = 'a2'", (dates[1],))
    r = register_run(conn, "demographics", {})
    observe(conn, r, "a1", "a", "pots", "resolved"), observe(conn, r, "a2", "a", "pots")
    assert conn.execute("SELECT severity, n_posts FROM conditions_latest").fetchall() == [(latest, 2)]


def test_only_each_posts_newest_demographics_read_counts(conn):
    r1 = register_run(conn, "demographics", {})
    observe(conn, r1, "a1", "a", "ms")  # a misread, gone on the reread
    r2 = register_run(conn, "demographics", {})
    conn.execute("INSERT INTO post_runs VALUES (?, 'a1')", (r2,))
    other = register_run(conn, "sentiment", {})
    conn.execute("INSERT INTO post_runs VALUES (?, 'a1')", (other,))  # not a demographics run
    assert conn.execute("SELECT COUNT(*) FROM conditions_latest").fetchone() == (0,)


def test_an_older_conditions_latest_view_is_replaced(conn):
    conn.executescript("DROP VIEW conditions_latest; CREATE VIEW conditions_latest AS SELECT * FROM conditions;")
    apply_schema(conn, SCHEMA)
    columns = [d[0] for d in conn.execute("SELECT * FROM conditions_latest").description]
    assert columns == ["user_id", "condition_name", "condition_type", "severity", "first_seen", "last_seen", "n_posts"]


def test_the_condition_filter_reads_current_observations_only(conn):
    r1 = register_run(conn, "demographics", {})
    observe(conn, r1, "a1", "a", "pots")
    observe(conn, r1, "c1", "c", "pots")
    r2 = register_run(conn, "demographics", {})
    conn.execute("INSERT INTO post_runs VALUES (?, 'c1')", (r2,))  # c's reread no longer finds it
    csv = register_run(conn, "extraction_pipeline", {})
    conn.execute("INSERT INTO conditions (run_id, user_id, post_id, condition_name, condition_type) "
                 "VALUES (?, 'b', 'b1', 'pots', 'illness')", (csv,))  # CSV loads never count
    conn.execute("INSERT INTO conditions (run_id, user_id, condition_name, condition_type) "
                 "VALUES (?, 'b', 'pots', 'illness')", (r1,))  # nor do per-user rows without a post
    for i, user in enumerate("abc", 1):
        conn.execute("INSERT INTO treatment_reports (report_id, run_id, post_id, user_id, drug_id, sentiment, "
                     "signal_strength) VALUES (?, ?, ?, ?, 1, 'positive', 'strong')", (i, r1, f"{user}1", user))

    assert [r["n_reports"] for r in query_treatment_outcomes(conn, condition="POTS")] == [1]
    assert [r["n_reports"] for r in query_treatment_outcomes(conn)] == [3]


@pytest.mark.parametrize("asked", ["long covid", "LC", "Long-COVID", "PASC", "covid"])
def test_the_condition_filter_finds_a_condition_by_any_of_its_names(conn, asked):
    r = register_run(conn, "demographics", {})
    observe(conn, r, "a1", "a", "long covid")
    conn.execute("INSERT INTO treatment_reports (report_id, run_id, post_id, user_id, drug_id, sentiment, "
                 "signal_strength) VALUES (1, ?, 'a1', 'a', 1, 'positive', 'strong')", (r,))
    assert [row["n_reports"] for row in query_treatment_outcomes(conn, condition=asked)] == [1]
