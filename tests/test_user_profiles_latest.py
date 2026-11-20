"""user_profiles_latest: each user's profile from their newest demographics run, and the filters that read it."""
import sqlite3
from pathlib import Path

from patientpunk.db import init_db, query_treatment_outcomes, register_run

SCHEMA_SQL = Path(__file__).parent.parent / "schema.sql"


def _seed(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        INSERT INTO users VALUES ('a', 'covidlonghaulers', 0), ('b', 'covidlonghaulers', 0);
        INSERT INTO posts (post_id, user_id, body_text, scraped_at) VALUES ('pa', 'a', 'LDN helped', 0), ('pb', 'b', 'LDN helped', 0);
        INSERT INTO treatment (id, canonical_name) VALUES (1, 'ldn');
        INSERT INTO extraction_runs (run_id, run_at, commit_hash, extraction_type, config) VALUES (1, 0, 'x', 'sentiment', '{}');
        INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength)
            VALUES (1, 'pa', 'a', 1, 'positive', 'strong'), (1, 'pb', 'b', 1, 'positive', 'strong');
    """)


def _profile(conn: sqlite3.Connection, run_type: str, user: str, age: str, sex: str = "female") -> int:
    run_id = register_run(conn, run_type, {})
    conn.execute("INSERT INTO user_profiles (user_id, run_id, age_bucket, sex, location) VALUES (?, ?, ?, ?, NULL)",
                 (user, run_id, age, sex))
    return run_id


def _latest(conn: sqlite3.Connection) -> dict[str, tuple]:
    return {u: (r, a) for u, r, a in conn.execute("SELECT user_id, run_id, age_bucket FROM user_profiles_latest")}


def _matches(conn: sqlite3.Connection, **filters) -> int:
    rows = query_treatment_outcomes(conn, drug="ldn", **filters)
    return rows[0]["n_reports"] if rows else 0


def test_newest_demographics_run_wins_and_older_rows_stay(tmp_path):
    conn = init_db(tmp_path / "t.db", SCHEMA_SQL)
    _seed(conn)
    _profile(conn, "demographics", "a", "30s")
    newer = _profile(conn, "demographics", "a", "40s")

    assert _latest(conn) == {"a": (newer, "40s")}
    assert conn.execute("SELECT COUNT(*) FROM user_profiles WHERE user_id = 'a'").fetchone()[0] == 2
    assert _matches(conn, age_bucket="40s") == 1
    assert _matches(conn, age_bucket="30s") == 0


def test_csv_rows_never_replace_a_direct_profile(tmp_path):
    conn = init_db(tmp_path / "t.db", SCHEMA_SQL)
    _seed(conn)
    direct = _profile(conn, "demographics", "a", "30s")
    _profile(conn, "variable_extraction", "a", "50s", sex="male")
    _profile(conn, "extraction_pipeline", "a", "60s", sex="male")

    assert _latest(conn) == {"a": (direct, "30s")}
    assert _matches(conn, age_bucket="30s") == 1
    assert _matches(conn, age_bucket="50s") == 0
    assert _matches(conn, age_bucket="60s") == 0
    assert _matches(conn, sex="male") == 0


def test_user_with_only_csv_profiles_is_excluded(tmp_path):
    conn = init_db(tmp_path / "t.db", SCHEMA_SQL)
    _seed(conn)
    _profile(conn, "variable_extraction", "b", "30s")
    _profile(conn, "extraction_pipeline", "b", "30s")

    assert _latest(conn) == {}
    assert _matches(conn, age_bucket="30s") == 0
    assert _matches(conn, sex="female") == 0
    assert _matches(conn) == 2


def test_init_db_installs_the_view_on_a_pre_view_database(tmp_path):
    path = tmp_path / "old.db"
    conn = init_db(path, SCHEMA_SQL)
    conn.execute("DROP VIEW user_profiles_latest")
    _seed(conn)
    direct = _profile(conn, "demographics", "a", "30s")
    conn.commit()
    conn.close()

    conn = init_db(path, SCHEMA_SQL)
    assert _latest(conn) == {"a": (direct, "30s")}
    assert _matches(conn, age_bucket="30s") == 1
    init_db(path, SCHEMA_SQL).close()  # applying it again is a no-op
