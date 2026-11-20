"""Tests for load_db.py (the unified-DB builder) and cluster-prep's demographics,
which come only from user_profiles_latest. No API calls."""

import argparse
import csv
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

import load_db  # noqa: E402
from patientpunk.db import _bucketize_age  # noqa: E402

SCHEMA_SQL = REPO_ROOT / "schema.sql"
_spec = importlib.util.spec_from_file_location("ve_main", REPO_ROOT / "variable_extraction" / "main.py")
ve_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ve_main)


def _make_posts_db(path: Path) -> None:
    """Tiny posts.db: 2 users, 3 posts, 2 drugs, 3 TEXT-sentiment reports, and two
    demographics runs that give u1 an older "30s" and a current "40s" profile."""
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO users (user_id, source_subreddit, scraped_at) VALUES ('u1','x',0)")
    conn.execute("INSERT INTO users (user_id, source_subreddit, scraped_at) VALUES ('u2','x',0)")
    for pid, uid in [("p1", "u1"), ("p2", "u2"), ("p3", "u1")]:
        conn.execute(
            "INSERT INTO posts (post_id, user_id, body_text, scraped_at) VALUES (?,?,?,0)",
            (pid, uid, "text"),
        )
    conn.execute("INSERT INTO treatment (id, canonical_name) VALUES (1,'ldn')")
    conn.execute("INSERT INTO treatment (id, canonical_name) VALUES (2,'magnesium')")
    conn.execute(
        "INSERT INTO extraction_runs (run_at, commit_hash, extraction_type, config)"
        " VALUES (0,'abc','treatment_sentiment','{}')"
    )
    conn.execute(
        "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength)"
        " VALUES (1,'p1','u1',1,'positive','strong')"
    )
    conn.execute(
        "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength)"
        " VALUES (1,'p2','u2',2,'negative','weak')"
    )
    conn.execute(
        "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength)"
        " VALUES (1,'p3','u1',1,'positive','strong')"
    )
    for run_id, age in [(2, "30s"), (3, "40s")]:
        conn.execute("INSERT INTO extraction_runs (run_id, run_at, commit_hash, extraction_type, config)"
                     " VALUES (?, 0, 'abc', 'demographics', '{}')", (run_id,))
        conn.execute("INSERT INTO user_profiles (user_id, run_id, age_bucket, sex, location)"
                     " VALUES ('u1', ?, ?, 'female', 'US')", (run_id, age))
    conn.commit()
    conn.close()


def _write_csv(path: Path, header, rows) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


@pytest.fixture
def built(tmp_path):
    posts_db = tmp_path / "posts.db"
    _make_posts_db(posts_db)

    records = tmp_path / "records.csv"
    # meta cols + legacy demographic cols + 1 schema col (conditions) + 2 discovered cols
    _write_csv(
        records,
        ["author_hash", "source", "post_id", "age", "sex_gender", "location_country",
         "location_us_state", "conditions", "dysautonomia_type", "supplement_type_used"],
        [["u1", "subreddit_post", "p1", "25", "male", "UK", "Texas", "pots", "POTS", "magnesium"],
         ["u2", "subreddit_post", "p2", "61", "male", "UK", "", "long covid", "", "vitamin d"]],
    )

    out_db = tmp_path / "patientpunk.db"
    rc = load_db.main([
        "--posts-db", str(posts_db), "--records", str(records), "--db", str(out_db),
        "--schema-sql", str(SCHEMA_SQL),
    ])
    assert rc == 0
    return out_db


def _count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_corpus_copied(built):
    conn = sqlite3.connect(built)
    assert _count(conn, "users") == 2
    assert _count(conn, "posts") == 3
    assert _count(conn, "treatment_reports") == 3
    conn.close()


def test_new_run_registered(built):
    conn = sqlite3.connect(built)
    rows = conn.execute(
        "SELECT extraction_type, commit_hash FROM extraction_runs ORDER BY run_id"
    ).fetchall()
    assert len(rows) == 4                       # sentiment + 2 demographics + enrichment run
    assert rows[-1][0] == "variable_extraction"
    assert rows[-1][1]                          # non-empty commit hash
    conn.close()


def test_csv_writes_no_profiles_but_keeps_conditions(built):
    conn = sqlite3.connect(built)
    assert conn.execute("SELECT run_id FROM user_profiles ORDER BY run_id").fetchall() == [(2,), (3,)]
    names = {r[0] for r in conn.execute("SELECT condition_name FROM conditions")}
    assert "pots" in names and "long covid" in names
    conn.close()


def test_variables_eav(built):
    conn = sqlite3.connect(built)
    # non-empty, non-meta, non-demographic cells: u1 has 3, u2 has 2 -> 5
    assert _count(conn, "variables") == 5
    fields = {r[0] for r in conn.execute("SELECT DISTINCT field FROM variables")}
    assert "dysautonomia_type" in fields        # discovered variable stored
    assert "author_hash" not in fields          # meta column excluded
    assert not fields & {"age", "sex_gender", "location_country", "location_us_state"}
    conn.close()


def test_unified_table(built):
    conn = sqlite3.connect(built)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(unified)")]
    assert "drugs_mentioned" in cols and "n_drug_reports" in cols
    assert not set(cols) & {"age", "sex_gender", "location_country", "location_us_state"}
    assert _count(conn, "unified") == 2          # one row per record
    demo = dict(conn.execute("SELECT author_hash, demo_age_bucket || '/' || demo_sex FROM unified"))
    assert demo == {"u1": "40s/female", "u2": "/"}   # current direct profile, never the CSV's
    u1 = conn.execute(
        "SELECT drugs_mentioned, n_drug_reports FROM unified WHERE author_hash='u1'"
    ).fetchone()
    assert u1 == ("ldn", 2)
    conn.close()


def test_unified_warns_without_direct_profiles(built, capsys):
    conn = sqlite3.connect(built)
    conn.execute("DELETE FROM user_profiles")
    load_db.build_unified(conn, built.parent / "records.csv")
    assert "no direct profiles" in capsys.readouterr().out
    conn.close()


def _cluster_prep(records: Path, db: Path | None, out: Path) -> dict[str, dict[str, str]]:
    with pytest.raises(SystemExit, match="0"):  # --no-report exits once the matrix is written
        ve_main._cmd_cluster_prep(argparse.Namespace(
            records=records, db=db, key="author_hash", min_coverage=0.0, encode="multihot",
            top_k=8, fields=None, sep=" | ", out=out, no_report=True))
    return {r["patient_id"]: r for r in csv.DictReader(open(out, encoding="utf-8"))}


def test_cluster_prep_takes_demographics_from_the_db(built):
    matrix = _cluster_prep(built.parent / "records.csv", built, built.parent / "m.csv")
    assert matrix["u1"]["demo_age_bucket=40s"] == "1"     # newest demographics run
    assert "demo_age_bucket=30s" not in matrix["u1"]      # older run ignored
    assert not [c for c in matrix["u1"] if c.split("=")[0] in {"age", "sex_gender", "location_country"}]


def test_cluster_prep_without_db_warns_and_runs(built, capsys):
    matrix = _cluster_prep(built.parent / "records.csv", None, built.parent / "m.csv")
    assert "no --db" in capsys.readouterr().out
    assert set(matrix) == {"u1", "u2"}
    assert not [c for c in matrix["u1"] if c.startswith(("demo_", "age", "sex_gender", "location"))]


def test_bucketize_age_handles_missing_and_qualitative_decades():
    assert _bucketize_age(None) is None
    assert _bucketize_age("mid-30s") == "30s"
    assert _bucketize_age("early 40s") == "40s"
