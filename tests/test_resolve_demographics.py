"""Per-post claims resolved into one profile per user in code (#206 PR 1). Made-up data, no API calls."""
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from patientpunk.db import init_db, register_run  # noqa: E402
from import_posts import DELETED_USER_ID  # noqa: E402
from resolve_demographics import resolve_profiles  # noqa: E402

SCHEMA_SQL = Path(__file__).parent.parent / "schema.sql"


def ts(year: int) -> int:
    return int(datetime(year, 6, 1, tzinfo=timezone.utc).timestamp())


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    conn = init_db(tmp_path / "t.db", SCHEMA_SQL)
    conn.executemany("INSERT INTO users VALUES (?, 'cfs', 0)", [("a",), ("b",)])
    return conn


def post(conn, post_id: str, user: str, year: int) -> None:
    conn.execute("INSERT INTO posts (post_id, user_id, body_text, post_date, scraped_at) VALUES (?, ?, '', ?, 0)",
                 (post_id, user, ts(year)))


def read(conn, run_id: int, post_id: str, **claims) -> None:
    """Record that ``run_id`` read ``post_id`` and found ``claims``."""
    user = conn.execute("SELECT user_id FROM posts WHERE post_id = ?", (post_id,)).fetchone()[0]
    conn.execute("INSERT INTO post_runs VALUES (?, ?)", (run_id, post_id))
    conn.executemany("INSERT INTO demographic_claims VALUES (?, ?, ?, ?, ?, 'quote')",
                     [(run_id, post_id, user, field, value) for field, value in claims.items()])


def profile(conn, user: str):
    return conn.execute("SELECT age_bucket, sex, location FROM user_profiles_latest WHERE user_id = ?",
                        (user,)).fetchone()


def run(conn) -> int:
    return register_run(conn, "demographics", {})


def test_conflicting_ages_take_the_most_recent_and_are_counted(conn):
    post(conn, "p1", "a", 2024), post(conn, "p2", "a", 2026)
    r = run(conn)
    read(conn, r, "p1", age="45", sex="female"), read(conn, r, "p2", age="33")
    stats = resolve_profiles(conn, r)
    assert profile(conn, "a") == ("30s", "female", None)
    assert stats["disagreements"] == {"age": 1}


def test_age_advances_to_the_reference_date(conn):
    post(conn, "p1", "a", 2024), post(conn, "p2", "b", 2026)
    r = run(conn)
    read(conn, r, "p1", age="29"), read(conn, r, "p2")
    assert resolve_profiles(conn, r)["reference_date"] == ts(2026)
    assert profile(conn, "a") == ("30s", None, None)
    assert conn.execute("SELECT age FROM user_profiles_latest WHERE user_id = 'a'").fetchone() == (31,)


def test_a_newer_reference_date_refreshes_a_user_without_new_posts(conn):
    post(conn, "p1", "a", 2025), post(conn, "p2", "b", 2025)
    r1 = run(conn)
    read(conn, r1, "p1", age="29"), read(conn, r1, "p2")
    resolve_profiles(conn, r1)
    assert profile(conn, "a") == ("20s", None, None)

    post(conn, "p3", "b", 2026)  # only b posts again
    r2 = run(conn)
    read(conn, r2, "p3")
    resolve_profiles(conn, r2)
    assert profile(conn, "a") == ("30s", None, None)


@pytest.mark.parametrize("posts, expected", [
    ([{"country": "US", "state": "Texas"}, {"country": "US"}], "US / Texas"),
    ([{"state": "Texas"}, {"country": "US"}], "US / Texas"),
    ([{"country": "US", "state": "Texas"}, {"country": "UK"}], "UK"),
])
def test_location_pairs_a_state_only_with_its_country(conn, posts, expected):
    r = run(conn)
    for i, claims in enumerate(posts):
        post(conn, f"p{i}", "a", 2024 + i)
        read(conn, r, f"p{i}", **claims)
    resolve_profiles(conn, r)
    assert profile(conn, "a")[2] == expected


def test_a_user_with_no_claims_gets_an_empty_row(conn):
    post(conn, "p1", "a", 2026)
    r = run(conn)
    read(conn, r, "p1")
    resolve_profiles(conn, r)
    assert profile(conn, "a") == (None, None, None)


def test_a_reread_that_finds_nothing_retracts_and_restart_resolves_it(conn):
    post(conn, "p1", "a", 2026)
    r1 = run(conn)
    read(conn, r1, "p1", age="34", sex="male")
    resolve_profiles(conn, r1)
    assert profile(conn, "a") == ("30s", "male", None)

    r2 = run(conn)
    read(conn, r2, "p1")  # the reread is committed, then the run stops before resolving
    assert conn.execute("SELECT COUNT(*) FROM demographic_claims_latest").fetchone()[0] == 0

    r3 = run(conn)  # a restart with no unread posts
    assert resolve_profiles(conn, r3)["profiles_written"] == 1
    assert profile(conn, "a") == (None, None, None)


def test_a_failed_user_keeps_the_previous_profile(conn):
    post(conn, "p1", "a", 2025), post(conn, "p2", "a", 2026)
    r1 = run(conn)
    read(conn, r1, "p1", age="34")
    resolve_profiles(conn, r1)

    r2 = run(conn)
    read(conn, r2, "p1", age="51")  # p2 failed this run
    resolve_profiles(conn, r2, failed_users={"a"})
    assert profile(conn, "a") == ("30s", None, None)


def test_an_unchanged_profile_writes_no_row(conn):
    post(conn, "p1", "a", 2026)
    r1 = run(conn)
    read(conn, r1, "p1", sex="female")
    resolve_profiles(conn, r1)
    r2 = run(conn)
    read(conn, r2, "p1", sex="female")
    assert resolve_profiles(conn, r2)["profiles_written"] == 0


def test_resolution_creates_its_tables_on_an_older_database(tmp_path):
    conn = init_db(tmp_path / "old.db", SCHEMA_SQL)
    conn.executescript("DROP VIEW demographic_claims_latest; DROP TABLE demographic_claims; DROP TABLE post_runs;")
    resolve_profiles(conn, run(conn))
    names = {n for (n,) in conn.execute("SELECT name FROM sqlite_master")}
    assert {"post_runs", "demographic_claims", "demographic_claims_latest"} <= names


@pytest.mark.parametrize("stated, bucket, age", [
    ("34.0", "30s", 34), ("mid-30s", "30s", 35), ("early 40s", "40s", 42), ("25-34", "30s", 30),
    ("thirty-ish", None, None), ("1e3", None, None), ("", None, None),
])
def test_ages_the_model_may_write_never_crash(conn, stated, bucket, age):
    post(conn, "p1", "a", 2026)
    r = run(conn)
    read(conn, r, "p1", age=stated)
    resolve_profiles(conn, r)
    assert conn.execute("SELECT age_bucket, age FROM user_profiles_latest WHERE user_id = 'a'").fetchone() == (bucket, age)


def test_an_unparseable_age_does_not_hide_an_earlier_one(conn):
    post(conn, "p1", "a", 2025), post(conn, "p2", "a", 2026)
    r = run(conn)
    read(conn, r, "p1", age="34"), read(conn, r, "p2", age="old enough")
    assert resolve_profiles(conn, r)["disagreements"] == {}
    assert profile(conn, "a")[0] == "30s"


def test_a_decade_and_an_age_in_it_agree(conn):
    post(conn, "p1", "a", 2026), post(conn, "p2", "a", 2026)
    r = run(conn)
    read(conn, r, "p1", age="mid-30s"), read(conn, r, "p2", age="34")
    assert resolve_profiles(conn, r)["disagreements"] == {}


def test_case_differences_are_not_disagreements(conn):
    post(conn, "p1", "a", 2025), post(conn, "p2", "a", 2026)
    r = run(conn)
    read(conn, r, "p1", sex="Female", country="US", state="Texas"), read(conn, r, "p2", sex="female", country="us")
    assert resolve_profiles(conn, r)["disagreements"] == {}
    assert profile(conn, "a")[1:] == ("female", "us / Texas")


def test_the_deleted_placeholder_never_gets_a_profile(conn):
    conn.execute("INSERT INTO users VALUES (?, 'cfs', 0)", (DELETED_USER_ID,))
    post(conn, "p1", DELETED_USER_ID, 2026), post(conn, "p2", "a", 2026)
    r = run(conn)
    read(conn, r, "p1", age="50", sex="male"), read(conn, r, "p2", sex="female")
    assert resolve_profiles(conn, r)["profiles_written"] == 1
    assert profile(conn, DELETED_USER_ID) is None
    assert profile(conn, "a") == (None, "female", None)
