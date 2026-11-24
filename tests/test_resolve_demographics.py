"""Per-post claims resolved into one profile per user in code (#206 PR 1). Made-up data, no API calls."""
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from patientpunk.db import init_db, register_run  # noqa: E402
from import_posts import DELETED_USER_ID  # noqa: E402
from resolve_demographics import canonical_place, normalize_sex, resolve_profiles  # noqa: E402

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
    conn.execute("INSERT INTO post_runs VALUES (?, ?)", (run_id, post_id))
    conn.executemany("INSERT INTO demographic_claims VALUES (?, ?, ?, ?, 'quote')",
                     [(run_id, post_id, field, value) for field, value in claims.items()])


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


def test_age_advances_to_the_users_newest_post(conn):
    post(conn, "p1", "a", 2024), post(conn, "p2", "a", 2026), post(conn, "p3", "b", 2030)
    r = run(conn)
    read(conn, r, "p1", age="29"), read(conn, r, "p2"), read(conn, r, "p3")
    resolve_profiles(conn, r)
    assert profile(conn, "a") == ("30s", None, None)
    assert conn.execute("SELECT age FROM user_profiles_latest WHERE user_id = 'a'").fetchone() == (31.0,)


def test_another_users_newer_post_leaves_an_age_alone(conn):
    post(conn, "p1", "a", 2025), post(conn, "p2", "b", 2025)
    r1 = run(conn)
    read(conn, r1, "p1", age="29"), read(conn, r1, "p2")
    resolve_profiles(conn, r1)

    post(conn, "p3", "b", 2030)  # only b posts again
    r2 = run(conn)
    read(conn, r2, "p3")
    assert resolve_profiles(conn, r2)["profiles_written"] == 0
    assert profile(conn, "a") == ("20s", None, None)


@pytest.mark.parametrize("ages, ever_minor", [
    ([(2020, "16"), (2024, None)], 1),  # 20 by their newest post, but a minor when they wrote it
    ([(2020, "15-17")], 1), ([(2020, "17"), (2023, "20")], 1),
    ([(2020, "30")], 0), ([(2020, "18")], 0), ([(2020, None)], None),
])
def test_ever_minor_is_set_by_any_age_claim_under_18_when_written(conn, ages, ever_minor):
    r = run(conn)
    for i, (year, age) in enumerate(ages):
        post(conn, f"p{i}", "a", year)
        read(conn, r, f"p{i}", **({"age": age} if age else {}))
    resolve_profiles(conn, r)
    assert conn.execute("SELECT ever_minor FROM user_profiles_latest WHERE user_id = 'a'").fetchone() == (ever_minor,)


@pytest.mark.parametrize("posts, expected", [  # expected: (location, city)
    ([{"country": "US", "state": "Texas"}, {"country": "US"}], ("United States / Texas", None)),
    ([{"state": "Texas"}, {"country": "US"}], ("United States / Texas", None)),
    ([{"country": "US", "state": "Texas"}, {"country": "UK"}], ("United Kingdom", None)),
    ([{"country": "US"}, {"state": "Texas"}, {"country": "UK"}], ("United Kingdom", None)),
    ([{"country": "UK"}, {"country": "US"}, {"state": "Texas"}], ("United States / Texas", None)),
    ([{"state": "Texas"}], ("United States / Texas", None)),  # a US state names its country
    ([{"state": "TX"}, {"country": "UK"}], ("United Kingdom", None)),
    ([{"state": "Ontario"}], ("Ontario", None)),  # only US states do
    ([{"country": "US", "state": "Texas"}, {"country": "UK"}, {"country": "US"}], ("United States / Texas", None)),
    ([{"state": "Texas"}, {"country": "US"}, {"country": "UK"}], ("United Kingdom", None)),
    ([{"country": "US", "state": "Texas"}, {"country": " "}], ("United States / Texas", None)),  # a blank claim states nothing
    ([{"country": "US", "state": "Texas", "city": "Austin"}, {"country": "US"}], ("United States / Texas", "Austin")),
    ([{"state": "Texas", "city": "Austin"}, {"country": "US", "state": "Ohio"}], ("United States / Ohio", None)),
    ([{"country": "US", "state": "Texas"}, {"city": "Austin"}, {"country": "UK"}], ("United Kingdom", None)),
    ([{"city": "Austin"}, {"country": "US", "state": "Texas"}], ("United States / Texas", "Austin")),
    # Two spellings of one country keep its state and city (#225 review)
    ([{"country": "US", "state": "Texas"}, {"city": "Austin"}, {"country": "USA"}], ("United States / Texas", "Austin")),
    ([{"country": "U.S.", "state": "TX"}, {"country": "the States"}], ("United States / Texas", None)),
    ([{"country": "slovenia"}], ("slovenia", None)),  # a place not in the list is kept as written
])
def test_location_pairs_a_state_only_with_its_country(conn, posts, expected):
    r = run(conn)
    for i, claims in enumerate(posts):
        post(conn, f"p{i}", "a", 2024 + i)
        read(conn, r, f"p{i}", **claims)
    resolve_profiles(conn, r)
    assert conn.execute("SELECT location, city FROM user_profiles_latest WHERE user_id = 'a'"
                        ).fetchone() == expected


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
    ("34.0", "30s", 34.0), ("mid-30s", "30s", 35.0), ("early 40s", "40s", 42.5), ("late 30s", "30s", 37.5),
    ("25-34", "20s", 29.5), ("20s-30s", "30s", 30.0), ("early–30s", "30s", 32.5), ("34 years old", "30s", 34.0),
    ("60s+", None, None),
    ("thirty-ish", None, None), ("1e3", None, None), ("", None, None),
    ("inf", None, None), ("1e400", None, None), ("9", None, None), ("100", None, None), ("-5", None, None),
    ("34.5", None, None),
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


def test_a_blank_claim_does_not_replace_an_earlier_value(conn):
    post(conn, "p1", "a", 2025), post(conn, "p2", "a", 2026)
    r = run(conn)
    read(conn, r, "p1", sex="female"), read(conn, r, "p2", sex="")
    assert resolve_profiles(conn, r)["disagreements"] == {}
    assert profile(conn, "a") == (None, "female", None)


def test_case_differences_are_not_disagreements(conn):
    post(conn, "p1", "a", 2025), post(conn, "p2", "a", 2026)
    r = run(conn)
    read(conn, r, "p1", sex="Female", country="US", state="Texas"), read(conn, r, "p2", sex="female", country="us")
    assert resolve_profiles(conn, r)["disagreements"] == {}
    assert profile(conn, "a")[1:] == ("female", "United States / Texas")


def test_the_deleted_placeholder_never_gets_a_profile(conn):
    conn.execute("INSERT INTO users VALUES (?, 'cfs', 0)", (DELETED_USER_ID,))
    post(conn, "p1", DELETED_USER_ID, 2026), post(conn, "p2", "a", 2026)
    r = run(conn)
    read(conn, r, "p1", age="50", sex="male"), read(conn, r, "p2", sex="female")
    assert resolve_profiles(conn, r)["profiles_written"] == 1
    assert profile(conn, DELETED_USER_ID) is None
    assert profile(conn, "a") == (None, "female", None)


def test_a_stated_age_is_checked_before_it_is_advanced(conn):
    post(conn, "p1", "a", 2016), post(conn, "p2", "a", 2026)
    r = run(conn)
    read(conn, r, "p1", age="9")  # a child then; 19 now, but 9 is outside 10-99
    resolve_profiles(conn, r)
    assert profile(conn, "a") == (None, None, None)


def test_the_same_age_a_year_apart_after_advancing_is_not_a_disagreement(conn):
    for pid, d in [("p1", datetime(2024, 1, 2)), ("p2", datetime(2024, 12, 30)), ("p3", datetime(2026, 6, 1))]:
        conn.execute("INSERT INTO posts (post_id, user_id, body_text, post_date, scraped_at) VALUES (?, ?, '', ?, 0)",
                     (pid, "a" if pid != "p3" else "b", int(d.replace(tzinfo=timezone.utc).timestamp())))
    r = run(conn)
    read(conn, r, "p1", age="29"), read(conn, r, "p2", age="29")  # advance to 31 and 30
    assert resolve_profiles(conn, r)["disagreements"] == {}


def test_text_fields_that_disagree_are_counted(conn):
    post(conn, "p1", "a", 2025), post(conn, "p2", "a", 2026)
    r = run(conn)
    read(conn, r, "p1", sex="female", country="US", state="Texas"), read(conn, r, "p2", sex="male", country="UK")
    assert resolve_profiles(conn, r)["disagreements"] == {"sex": 1, "country": 1}


def test_claims_from_other_run_types_are_ignored(conn):
    post(conn, "p1", "a", 2026)
    r1 = run(conn)
    read(conn, r1, "p1", sex="female")
    other = register_run(conn, "conditions", {})
    read(conn, other, "p1", sex="male")  # newer, but not a demographics run
    resolve_profiles(conn, run(conn))
    assert profile(conn, "a") == (None, "female", None)


def test_posts_without_a_date_still_resolve(conn):
    conn.execute("INSERT INTO posts (post_id, user_id, body_text, post_date, scraped_at) VALUES ('p1', 'a', '', NULL, 0)")
    r = run(conn)
    read(conn, r, "p1", age="34")
    resolve_profiles(conn, r)
    assert profile(conn, "a") == ("30s", None, None)


def test_only_a_demographics_run_can_hold_profiles(conn):
    with pytest.raises(ValueError, match="not a demographics run"):
        resolve_profiles(conn, register_run(conn, "conditions", {}))


def test_a_decade_phrase_advances_from_its_midpoint(conn):
    post(conn, "p1", "a", 2016), post(conn, "p2", "a", 2026)
    r = run(conn)
    read(conn, r, "p1", age="late 30s")  # 37.5 in 2016 is 47.5 by their 2026 post
    resolve_profiles(conn, r)
    assert conn.execute("SELECT age_bucket, age FROM user_profiles_latest WHERE user_id = 'a'").fetchone() == ("40s", 47.5)


def test_a_decade_and_an_exact_age_from_the_same_year_agree_after_advancing(conn):
    post(conn, "p1", "a", 2016), post(conn, "p2", "a", 2016), post(conn, "p3", "b", 2026)
    r = run(conn)
    read(conn, r, "p1", age="mid-30s"), read(conn, r, "p2", age="34")
    assert resolve_profiles(conn, r)["disagreements"] == {}


def test_sex_claims_that_normalize_alike_agree(conn):
    r = run(conn)
    post(conn, "p1", "a", 2024)
    post(conn, "p2", "a", 2025)
    read(conn, r, "p1", sex="F")
    read(conn, r, "p2", sex="female")
    assert resolve_profiles(conn, r)["disagreements"] == {}


@pytest.mark.parametrize("field, value, canonical", [
    ("country", "US", "United States"), ("country", "U.S.", "United States"), ("country", "the States", "United States"),
    ("country", "America", "United States"), ("country", "England", "United Kingdom"), ("country", "Aus", "Australia"),
    ("country", "united states", "United States"), ("country", "Brazil", "Brazil"), ("country", " Slovenia ", "Slovenia"),
    ("state", "TX", "Texas"), ("state", "texas", "Texas"), ("state", "D.C.", "District of Columbia"),
    ("state", "Quebec", "Quebec"),
])
def test_canonical_place(field, value, canonical):
    assert canonical_place(field, value) == canonical


def test_spellings_of_one_place_are_not_disagreements(conn):
    post(conn, "p1", "a", 2025), post(conn, "p2", "a", 2026)
    r = run(conn)
    read(conn, r, "p1", country="US", state="TX"), read(conn, r, "p2", country="USA", state="Texas")
    assert resolve_profiles(conn, r)["disagreements"] == {}
    assert profile(conn, "a")[2] == "United States / Texas"


@pytest.mark.parametrize("stated, sex", [
    ("guy", "male"), ("dude", "male"), ("dad", "male"), ("Lady", "female"), ("mom", "female"), ("f | mom", "female"),
    ("female (she/her)", "female"), ("Female.", "female"), ("female (trans woman)", None), ("female (she/her", "female"),
    ("female | transitioned", None), ("woman (transitioning)", None), ("male | in transit", "male"),
    ("mom | dad", None), ("trans woman | mom", None), ("non-binary | mom", "non-binary"),
    # Trans words leave sex empty; medical words that start with "trans" don't
    ("MTF | female", None), ("FtM", None), ("transmasculine | male", None), ("transfeminine | female", None),
    ("female | kidney transplant", "female"), ("male | transverse myelitis", "male"), ("female | transient", "female"),
])
def test_everyday_sex_words(stated, sex):
    assert normalize_sex(stated) == sex
