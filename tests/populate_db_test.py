"""Test that a fresh DB can be created from schema.sql and populated with sample data."""
import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import extract_demographics_conditions
from import_posts import import_reddit_posts
from run_sentiment_pipeline import run_pipeline
from extract_demographics_conditions import run_demographics
from utilities import PipelineConfig


# ---------------------------------------------------------------------------
# Fake Anthropic client for deterministic pipeline testing
# ---------------------------------------------------------------------------
#
# The sentiment pipeline makes three kinds of LLM calls (extract, canonicalize,
# prefilter+classify). Instead of hitting the real API in CI, we route by
# prompt-content fingerprint and return canned JSON.
#
# Expected flow over sample_data.json (LDN discussion):
#   extract     → Post1/Post2 mention LDN directly; comments don't.
#                 Upstream context propagates LDN from Post1 to Comment1/2.
#   is_only_questions() drops Post1 ("Do you like LDN?") and Comment2
#                 ("Have you tried the gym?").
#   canonicalize→ {"ldn": "ldn"} (only one drug).
#   prefilter   → Post2 is an article (no personal experience) → no;
#                 Comment1 ("I love it so much") → yes.
#   classify    → one pair reaches classify: (Comment1, ldn)
#                 → positive / strong.

def _stub_response(messages, system):
    prompt = messages[0]["content"] if messages else ""

    # Demographics: fingerprint from DEMOGRAPHICS_PROMPT.
    if "Given these Reddit posts by a single user" in prompt:
        return json.dumps({
            "age_bucket": None,
            "sex": None,
            "location": None,
            "conditions": [],
        })

    # Canonicalize: "identify true synonyms" is in CANONICALIZE_COMPOUND_PROMPT.
    if "identify true synonyms" in prompt:
        end = prompt.rindex("]") + 1
        start = prompt.rindex("[", 0, end)
        names = json.loads(prompt[start:end])
        return json.dumps({n: n for n in names})

    # Prefilter: "Does the AUTHOR express personal experience" is in PREFILTER_PROMPT.
    if "Does the AUTHOR express personal experience" in prompt:
        blocks = re.split(r"--- \d+ ---", prompt)[1:]
        return json.dumps(["yes" if "I love it" in b else "no" for b in blocks])

    # Classify (batch): per classify_batch() in src/pipeline/classify.py.
    if "Classify each entry separately" in prompt:
        n = prompt.count("--- Entry ")
        return json.dumps([{"sentiment": "positive", "signal": "strong"}] * n)

    # Classify (per-item fallback): system prompt identifies it.
    if system and "Classify Reddit posts/comments" in (
        system if isinstance(system, str) else json.dumps(system)
    ):
        return json.dumps({"sentiment": "positive", "signal": "strong"})

    # Extract: EXTRACT_PROMPT text fingerprint.
    if "list all drugs, medications, supplements" in prompt:
        blocks = re.split(r"--- \d+ ---", prompt)[1:]
        return json.dumps([["ldn"] if "ldn" in b.lower() else [] for b in blocks])

    return "[]"


class _FakeStream:
    def __init__(self, text):
        self._text = text

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get_final_message(self):
        return SimpleNamespace(content=[SimpleNamespace(text=self._text)])


class _FakeMessages:
    def create(self, *, messages, system=None, **_):
        return SimpleNamespace(
            content=[SimpleNamespace(text=_stub_response(messages, system))]
        )

    def stream(self, *, messages, system=None, **_):
        return _FakeStream(_stub_response(messages, system))


class FakeAnthropic:
    """Stand-in for anthropic.Anthropic — no network, deterministic responses."""

    def __init__(self):
        self.messages = _FakeMessages()

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

def test_extract_demographic_data(db: DB, monkeypatch):
    """Test that the demographic extraction pipeline works."""
    monkeypatch.setattr(extract_demographics_conditions, "get_client", FakeAnthropic)
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
        client=FakeAnthropic(),
        output_dir=db.path.parent,
        db_path=db.path,
    )
    run_pipeline(config)
    treatment_counts = db.conn.execute("SELECT COUNT(*) FROM treatment").fetchone()[0]
    assert treatment_counts >= 1
    treatment_reports = db.conn.execute("SELECT post_id, user_id, sentiment, signal_strength FROM treatment_reports").fetchall()
    assert treatment_reports == [('Comment1', 'b', 'positive', 'strong')]
