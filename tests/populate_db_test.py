"""Test that a fresh DB can be created from schema.sql and populated with sample data."""
import json
import re
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple

import pytest

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
    # Route by post body content so user "b" (who posts "I love it so much!!!")
    # gets a populated profile + condition, exercising the non-null path.
    if "Given these Reddit posts by a single user" in prompt:
        if "I love it so much" in prompt:
            return json.dumps({
                "age_bucket": "25-34",
                "sex": "F",
                "location": "US",
                "conditions": [
                    {"condition_name": "fibromyalgia", "condition_type": "illness"}
                ],
            })
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

    raise AssertionError(
        f"FakeAnthropic got unrecognized prompt (first 300 chars): {prompt[:300]!r}"
    )


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
    def __init__(self, calls):
        self._calls = calls

    def create(self, *, messages, system=None, **_):
        self._calls.append((messages, system))
        return SimpleNamespace(
            content=[SimpleNamespace(text=_stub_response(messages, system))]
        )

    def stream(self, *, messages, system=None, **_):
        self._calls.append((messages, system))
        return _FakeStream(_stub_response(messages, system))


class FakeAnthropic:
    """Stand-in for anthropic.Anthropic — no network, deterministic, records calls."""

    def __init__(self):
        self.calls: list[tuple[list, object]] = []
        self.messages = _FakeMessages(self.calls)

    def prompts_matching(self, needle: str) -> list[str]:
        return [m[0]["content"] for m, _ in self.calls if needle in m[0]["content"]]


SCHEMA = Path(__file__).parent.parent / "schema.sql"
SAMPLE = Path(__file__).parent / "sample_data.json"

# Derive expectations from the fixture file so adding/removing posts in
# sample_data.json surfaces as a clear failure rather than a magic-number mismatch.
SAMPLE_POSTS = json.loads(SAMPLE.read_text())
EXPECTED_POST_IDS = {p["post_id"] for p in SAMPLE_POSTS} | {
    c["comment_id"] for p in SAMPLE_POSTS for c in p["comments"]
}
EXPECTED_USERS = {p["author_hash"] for p in SAMPLE_POSTS} | {
    c["author_hash"] for p in SAMPLE_POSTS for c in p["comments"]
}


class DB(NamedTuple):
    conn: sqlite3.Connection
    path: Path


@pytest.fixture(scope="class")
def db(tmp_path_factory: pytest.TempPathFactory) -> DB:
    """On-disk DB initialised from schema.sql, shared across the test class."""
    path = tmp_path_factory.mktemp("db") / "test.db"
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.read_text())
    return DB(conn=conn, path=path)


class TestPopulateDbEndToEnd:
    """Sequential end-to-end: schema → import → demographics → sentiment pipeline.

    Grouped in a class so pytest runs methods in definition order — these steps
    share state via the class-scoped `db` fixture and must run in sequence.
    """

    def test_1_schema_creates_all_tables(self, db: DB):
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

    def test_2_foreign_keys_enforced(self, db: DB):
        """Schema PRAGMA aside, verify FKs actually fire on this connection."""
        with pytest.raises(sqlite3.IntegrityError):
            db.conn.execute(
                "INSERT INTO posts (post_id, user_id, body_text, scraped_at) "
                "VALUES ('orphan', 'nonexistent_user', 'x', 0)"
            )
        db.conn.rollback()

    def test_3_populate_users_and_posts(self, db: DB):
        import_reddit_posts(db.conn, SAMPLE, subreddit="test_subreddit")

        post_count = db.conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        user_count = db.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        assert post_count == len(EXPECTED_POST_IDS)
        assert user_count == len(EXPECTED_USERS)

    def test_4_import_is_idempotent(self, db: DB):
        """Re-importing the same sample must not duplicate rows."""
        import_reddit_posts(db.conn, SAMPLE, subreddit="test_subreddit")
        post_count = db.conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        user_count = db.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        assert post_count == len(EXPECTED_POST_IDS)
        assert user_count == len(EXPECTED_USERS)

    def test_5_extract_demographic_data(self, db: DB, monkeypatch):
        fake = FakeAnthropic()
        monkeypatch.setattr(
            extract_demographics_conditions, "get_client", lambda: fake
        )
        run_demographics(db.path)

        # Every user gets a profile row (even all-null ones).
        profile_ids = {
            row[0] for row in db.conn.execute("SELECT user_id FROM user_profiles")
        }
        assert profile_ids == EXPECTED_USERS

        # User "b" should have the populated demographics via the stub's routing.
        populated = db.conn.execute(
            "SELECT age_bucket, sex, location FROM user_profiles WHERE user_id = 'b'"
        ).fetchone()
        assert populated == ("25-34", "F", "US")

        # And the condition from user b's extraction should be recorded.
        conditions = db.conn.execute(
            "SELECT user_id, condition_name, condition_type FROM conditions"
        ).fetchall()
        assert conditions == [("b", "fibromyalgia", "illness")]

    def test_6_sentiment_pipeline(self, db: DB):
        fake = FakeAnthropic()
        config = PipelineConfig(
            client=fake,
            output_dir=db.path.parent,
            db_path=db.path,
        )
        run_pipeline(config)

        # Exactly one canonical treatment was written.
        treatments = db.conn.execute(
            "SELECT canonical_name FROM treatment"
        ).fetchall()
        assert treatments == [("ldn",)]

        # Only Comment1/ldn makes it through to a treatment_report.
        reports = db.conn.execute(
            "SELECT post_id, user_id, sentiment, signal_strength "
            "FROM treatment_reports ORDER BY post_id"
        ).fetchall()
        assert reports == [("Comment1", "b", "positive", "strong")]

        # Negative space: Post1 (question), Post2 (article, prefilter=no),
        # and Comment2 (question) must NOT have reports.
        filtered_out = db.conn.execute(
            "SELECT post_id FROM treatment_reports "
            "WHERE post_id IN ('Post1', 'Post2', 'Comment2')"
        ).fetchall()
        assert filtered_out == []

        # Prove classify was only called for the surviving (Comment1, ldn) pair.
        # Parent-post text ("Do you like LDN") may appear as upstream context,
        # so we assert on entry count — the prompt batches one Entry per pair.
        classify_prompts = fake.prompts_matching("Classify each entry separately")
        assert len(classify_prompts) == 1
        assert classify_prompts[0].count("--- Entry ") == 1
        assert "I love it so much" in classify_prompts[0]
