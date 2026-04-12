"""Test that a fresh DB can be created from schema.sql and populated with sample data."""
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import NamedTuple

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from import_posts import import_reddit_posts
from run_sentiment_pipeline import run_pipeline
from extract_demographics_conditions import run_demographics
from utilities import PipelineConfig, get_client

SCHEMA = Path(__file__).parent.parent / "schema.sql"
SAMPLE = Path(__file__).parent / "sample_data.json"


class DB(NamedTuple):
    conn: sqlite3.Connection
    path: Path


@pytest.fixture(scope="module")
def db(tmp_path_factory: pytest.TempPathFactory) -> DB:
    """On-disk DB initialised from schema.sql, shared across all tests in this module."""
    path = tmp_path_factory.mktemp("db") / "test.db"
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.read_text())
    return DB(conn=conn, path=path)


def test_schema_creates_all_tables(db: DB):
    tables = {
        row[0]
        for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    }
    assert tables == {
        "conditions",
        "extraction_runs",
        "posts",
        "treatment",
        "treatment_reports",
        "user_profiles",
        "users",
    }


def test_populate_users_and_posts(db: DB):
    import_reddit_posts(db.conn, SAMPLE, subreddit="test_subreddit")

    post_count = db.conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    user_count = db.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert post_count ==  4
    assert user_count == 4

def test_extract_demographic_data(db: DB):
    """Test that the demographic extraction pipeline works."""
    run_demographics(db.path)
    user_profiles = db.conn.execute("SELECT * from user_profiles").fetchall()
    conditions = db.conn.execute("SELECT * FROM conditions").fetchall()
    all_user_ids = ["a", "b", "c", "d"]
    # Every user should have a row, even if demographics are null
    user_ids_in_profiles = sorted(row[0] for row in user_profiles)
    assert user_ids_in_profiles == all_user_ids
    
    user_ids_in_conditions = sorted(row[2] for row in conditions)
    assert set(user_ids_in_conditions).issubset(all_user_ids)

def test_treatment_end2end_pipeline(db: DB):
    """Test that the treatment canonicalization pipeline works."""
    config = PipelineConfig(
        client=get_client(),
        output_dir=db.path.parent,
        db_path=db.path,
    )
    run_pipeline(config)
    treatment_counts = db.conn.execute("SELECT COUNT(*) FROM treatment").fetchone()[0]
    assert treatment_counts >= 1
    treatment_reports = db.conn.execute("SELECT post_id, user_id, sentiment, signal_strength FROM treatment_reports").fetchall()
    assert treatment_reports == [('Comment1', 'b', 'positive', 'strong')]
