"""Tests for load_db.py -- the unified-DB builder. No API calls."""

import csv
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

import load_db  # noqa: E402
from patientpunk.db import _bucketize_age  # noqa: E402

SCHEMA_SQL = REPO_ROOT / "schema.sql"


def _make_posts_db(path: Path) -> None:
    """Tiny posts.db: 2 users, 3 posts, 2 drugs, 1 run, 3 TEXT-sentiment reports."""
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
    # meta cols + 1 schema col (conditions) + 2 discovered cols
    _write_csv(
        records,
        ["author_hash", "source", "post_id", "age", "sex_gender",
         "conditions", "dysautonomia_type", "supplement_type_used"],
        [["u1", "subreddit_post", "p1", "34", "female", "pots", "POTS", "magnesium"],
         ["u2", "subreddit_post", "p2", "", "", "long covid", "", "vitamin d"]],
    )

    demo = tmp_path / "demographics_deductive.csv"
    _write_csv(
        demo,
        ["author_hash", "source_type", "age", "sex_gender",
         "location_country", "location_state", "confidence", "evidence"],
        [["u1", "subreddit_post", "34", "female", "US", "CA", "high", "e"]],
    )

    out_db = tmp_path / "patientpunk.db"
    rc = load_db.main([
        "--posts-db", str(posts_db), "--records", str(records),
        "--demographics", str(demo), "--db", str(out_db),
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
    assert len(rows) == 2                       # original + enrichment run
    assert rows[-1][0] == "variable_extraction"
    assert rows[-1][1]                          # non-empty commit hash
    conn.close()


def test_profiles_and_conditions(built):
    conn = sqlite3.connect(built)
    assert _count(conn, "user_profiles") >= 1
    names = {r[0] for r in conn.execute("SELECT condition_name FROM conditions")}
    assert "pots" in names and "long covid" in names
    conn.close()


def test_variables_eav(built):
    conn = sqlite3.connect(built)
    # non-empty, non-meta cells: u1 has 5 (age/sex/conditions/dysautonomia_type/supplement),
    # u2 has 2 (conditions/supplement) -> 7
    assert _count(conn, "variables") == 7
    fields = {r[0] for r in conn.execute("SELECT DISTINCT field FROM variables")}
    assert "dysautonomia_type" in fields        # discovered variable stored
    assert "author_hash" not in fields          # meta column excluded
    conn.close()


def test_unified_table(built):
    conn = sqlite3.connect(built)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(unified)")]
    assert "demo_age" in cols                    # demographics joined
    assert "drugs_mentioned" in cols and "n_drug_reports" in cols
    assert _count(conn, "unified") == 2          # one row per record
    u1 = conn.execute(
        "SELECT drugs_mentioned, n_drug_reports FROM unified WHERE author_hash='u1'"
    ).fetchone()
    assert u1 == ("ldn", 2)
    conn.close()


def test_bucketize_age_handles_missing_and_qualitative_decades():
    assert _bucketize_age(None) is None
    assert _bucketize_age("mid-30s") == "30s"
    assert _bucketize_age("early 40s") == "40s"


class TestSubredditStamping:
    """A multi-community corpus needs each patient stamped with their own
    community. The loader used to write "covidlonghaulers" for everyone."""

    def _load(self, tmp_path, header, rows, *extra_args):
        posts_db = tmp_path / "posts.db"
        _make_posts_db(posts_db)
        records = tmp_path / "records.csv"
        _write_csv(records, header, rows)
        out_db = tmp_path / "out.db"
        assert load_db.main([
            "--posts-db", str(posts_db), "--records", str(records),
            "--db", str(out_db), "--schema-sql", str(SCHEMA_SQL), *extra_args,
        ]) == 0
        conn = sqlite3.connect(out_db)
        return conn.execute(
            "SELECT source_subreddit FROM users WHERE user_id='u3'").fetchone()[0]

    def test_provenance_column_wins(self, tmp_path):
        got = self._load(
            tmp_path,
            ["author_hash", "source", "post_id", "subreddits", "conditions"],
            [["u3", "subreddit_post", "", "cfs:24 covidlonghaulers:11", "pots"]],
        )
        assert got == "cfs"          # the count-ordered leader, not the last seen

    def test_flag_fills_in_when_the_column_is_absent(self, tmp_path):
        got = self._load(
            tmp_path,
            ["author_hash", "source", "post_id", "conditions"],
            [["u3", "subreddit_post", "", "pmdd"]],
            "--subreddit", "PMDD",
        )
        assert got == "PMDD"

    def test_unknown_rather_than_a_guess(self, tmp_path):
        """No provenance and no flag must not silently claim a community."""
        got = self._load(
            tmp_path,
            ["author_hash", "source", "post_id", "conditions"],
            [["u3", "subreddit_post", "", "pots"]],
        )
        assert got == "unknown"
