"""conditions_latest: each user's conditions from their newest check (#220), and the filter that reads it."""
import sqlite3
from pathlib import Path

from patientpunk.db import init_db, query_treatment_outcomes, register_run

SCHEMA_SQL = Path(__file__).parent.parent / "schema.sql"


def _db(tmp_path) -> sqlite3.Connection:
    conn = init_db(tmp_path / "t.db", SCHEMA_SQL)
    conn.executescript("""
        INSERT INTO users VALUES ('a', 'covidlonghaulers', 0);
        INSERT INTO posts (post_id, user_id, body_text, scraped_at) VALUES ('pa', 'a', 'LDN helped', 0);
        INSERT INTO treatment (id, canonical_name) VALUES (1, 'ldn');
        INSERT INTO extraction_runs (run_id, run_at, commit_hash, extraction_type, config) VALUES (1, 0, 'x', 'sentiment', '{}');
        INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength)
            VALUES (1, 'pa', 'a', 1, 'positive', 'strong');
    """)
    return conn


def _conditions(conn, run_type: str, *names: str, checked: bool = True) -> int:
    run_id = register_run(conn, run_type, {})
    if checked:
        conn.execute("INSERT INTO condition_runs (run_id, user_id) VALUES (?, 'a')", (run_id,))
    conn.executemany("INSERT INTO conditions (run_id, user_id, condition_name, condition_type) VALUES (?, 'a', ?, 'illness')",
                     [(run_id, n) for n in names])
    return run_id


def _current(conn) -> set[str]:
    return {n for (n,) in conn.execute("SELECT condition_name FROM conditions_latest")}


def _matches(conn, condition: str) -> int:
    rows = query_treatment_outcomes(conn, drug="ldn", condition=condition)
    return rows[0]["n_reports"] if rows else 0


def test_the_newest_check_wins_and_one_that_finds_nothing_retracts(tmp_path):
    conn = _db(tmp_path)
    _conditions(conn, "demographics", "pots", "me/cfs")
    _conditions(conn, "demographics", "pots")
    assert _current(conn) == {"pots"}
    assert _matches(conn, "pots") == 1 and _matches(conn, "me/cfs") == 0

    _conditions(conn, "demographics")  # checked, found nothing
    assert _current(conn) == set()
    assert _matches(conn, "pots") == 0
    assert conn.execute("SELECT COUNT(*) FROM conditions").fetchone() == (3,)  # retracted, not deleted


def test_csv_rows_never_count(tmp_path):
    conn = _db(tmp_path)
    _conditions(conn, "extraction_pipeline", "ms", checked=False)
    assert _current(conn) == set() and _matches(conn, "ms") == 0
    _conditions(conn, "demographics", "pots")
    _conditions(conn, "extraction_pipeline", "ms", checked=False)
    assert _current(conn) == {"pots"}


def test_rows_from_before_condition_runs_stay_current_until_a_check(tmp_path):
    conn = _db(tmp_path)
    _conditions(conn, "demographics", "ms", checked=False)
    _conditions(conn, "demographics", "pots", checked=False)
    assert _current(conn) == {"pots"}
    _conditions(conn, "demographics")
    assert _current(conn) == set()


def test_init_db_installs_condition_runs_on_an_older_database(tmp_path):
    path = tmp_path / "old.db"
    conn = init_db(path, SCHEMA_SQL)
    conn.executescript("DROP VIEW conditions_latest; DROP TABLE condition_runs;")
    conn.close()

    conn = init_db(path, SCHEMA_SQL)
    names = {n for (n,) in conn.execute("SELECT name FROM sqlite_master")}
    assert {"condition_runs", "conditions_latest", "idx_cr_user"} <= names
