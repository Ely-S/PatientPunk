"""Exercise the per-user demographics extractor with synthetic posts and stubbed replies."""

import json
import sqlite3
from concurrent.futures import Future
from contextlib import closing
from pathlib import Path

import anthropic
import httpx
import openai
import pytest

import extract_demographics_conditions as demographics
from import_posts import DELETED_USER_ID
from patientpunk._utils import LLMContentFilteredError, LLMResponseError

SCHEMA = Path(__file__).resolve().parents[1] / "schema.sql"


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(demographics, "get_client", lambda: None)
    path = tmp_path / "posts.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        yield conn, path


def add_posts(conn, posts):
    # Tuples are (post_id, user_id, post_date, title, body_text).
    conn.executemany(
        "INSERT INTO users (user_id, source_subreddit, scraped_at) VALUES (?, 'test', 0) ON CONFLICT DO NOTHING",
        [(user,) for user in dict.fromkeys(post[1] for post in posts)],
    )
    conn.executemany(
        "INSERT INTO posts (post_id, user_id, post_date, title, body_text, scraped_at) VALUES (?, ?, ?, ?, ?, 0)",
        posts,
    )
    conn.commit()


def patient_text(prompt):
    _, _, text = prompt.partition("\n<patient_text>\n")
    assert text.endswith("\n</patient_text>")
    return text.removesuffix("\n</patient_text>")


def test_uses_eligible_titles_and_bodies_newest_first(db, monkeypatch):
    conn, path = db
    add_posts(conn, [
        ("no-text", "a-empty", 9, "", "  "),
        ("removed", "a-empty", 9, "Hidden title", "[removed]"),
        ("deleted-user", DELETED_USER_ID, 9, "Deleted author", "Placeholder text"),
        ("undated", "patient", None, None, "Undated body"),
        ("older", "patient", 2, None, "Older body"),
        ("title-only", "patient", 3, "Title only", ""),
        ("recent", "patient", 3, "Recent title", "Recent </patient_text> body"),
        ("marker", "patient", 5, "Also hidden", " [deleted] "),
        ("marker-in-sentence", "patient", 1, None, "My note about [removed] remains."),
        ("limited", "z-other", 8, "Another title", "Another body"),
    ])
    prompts = []

    def stub_call(client, prompt, **kwargs):
        prompts.append(prompt)
        return '{"country": "USA", "state": "OR"}'

    monkeypatch.setattr(demographics, "llm_call", stub_call)
    demographics.run_demographics(path, limit=1)

    assert len(prompts) == 1
    assert patient_text(prompts[0]) == "\n---\n".join([
        "Recent title\nRecent <:/patient_text> body",
        "Title only",
        "Older body",
        "My note about [removed] remains.",
        "Undated body",
    ])
    assert conn.execute("SELECT user_id, location FROM user_profiles").fetchall() == [("patient", "USA / OR")]


def test_caps_input_before_wrapping(db, monkeypatch):
    conn, path = db
    add_posts(conn, [
        ("recent", "patient", 2, "Newest", "a" * 6_000),
        ("older", "patient", 1, "Older", "b" * 3_000),
    ])
    prompts = []

    def stub_call(client, prompt, **kwargs):
        prompts.append(prompt)
        return '{"age": null}'

    monkeypatch.setattr(demographics, "llm_call", stub_call)
    demographics.run_demographics(path)
    demographics.run_demographics(path, max_posts=1, max_chars=12)

    full = patient_text(prompts[0])
    assert full == ("Newest\n" + "a" * 6_000 + "\n---\nOlder\n" + "b" * 3_000)[:8_000]
    assert len(full) == 8_000
    assert patient_text(prompts[1]) == "Newest\naaaaa"


@pytest.mark.parametrize(
    ("age", "sex", "country", "state", "expected"),
    [
        (10, "F", "US", "Texas", ("10s", 10.0, "female", "US / Texas")),
        ("99", " NONBINARY ", None, "Ohio", ("90s", 99.0, "non-binary", "Ohio")),
        (26, "Man", "Trinidad and Tobago", None, ("20s", 26.0, "male", "Trinidad and Tobago")),
        (9, ["M"], ["US", "Canada"], "Texas / Ohio", (None, None, None, None)),
        (100, "M | F", "US or Canada", ["Ohio"], (None, None, None, None)),
        ("30s", "22F", "unknown", "Texas; Ohio", (None, None, None, None)),
        ("25-34", "unknown", "", None, (None, None, None, None)),
        ("34 | 36", None, None, None, (None, None, None, None)),
        (34.5, None, None, None, (None, None, None, None)),
    ],
)
def test_normalizes_profile_fields(db, monkeypatch, age, sex, country, state, expected):
    conn, path = db
    add_posts(conn, [("post", "patient", 1, None, "A synthetic post")])
    result = {"age": age, "sex": sex, "country": country, "state": state}
    monkeypatch.setattr(demographics, "llm_call", lambda *args, **kwargs: json.dumps(result))

    demographics.run_demographics(path)

    assert conn.execute("SELECT age_bucket, age, sex, location FROM user_profiles").fetchone() == expected
    assert conn.execute("SELECT extraction_type FROM extraction_runs").fetchone() == ("demographics",)


def test_unreadable_reply_can_recover_at_last_temperature(monkeypatch):
    replies = iter([LLMResponseError("empty"), '[{"age": 34}]', '```json\n{"age": 37}\n```'])
    calls = []

    def stub_call(client, prompt, *, temperature, **kwargs):
        calls.append((prompt, temperature))
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(demographics, "llm_call", stub_call)

    assert demographics.extract_demographics(None, "Synthetic post")["age"] == 37
    assert [temperature for _, temperature in calls] == [0.0, 0.7, 1.0]
    assert len({prompt for prompt, _ in calls}) == 1


@pytest.mark.parametrize(
    "unreadable_reply",
    [
        '{"error": "private reply text"}',
        '{"conditions": {"error": "private reply text"}}',
        '{"conditions": [{}]}',
        'Here is the result: [{"age": null, "conditions": []}]',
    ],
    ids=["unknown-fields", "wrong-conditions-type", "malformed-condition", "wrapped-array"],
)
def test_failed_users_keep_previous_profiles_and_valid_empty_reply_is_written(
    db, monkeypatch, caplog, unreadable_reply,
):
    conn, path = db
    users = ("empty", "filtered", "transient", "unreadable")
    add_posts(conn, [(user, user, 1, None, user) for user in users])
    conn.execute(
        "INSERT INTO extraction_runs (run_id, run_at, commit_hash, extraction_type, config) "
        "VALUES (1, 0, 'test', 'demographics', '{}')",
    )
    conn.executemany(
        "INSERT INTO user_profiles (user_id, run_id, age_bucket) VALUES (?, 1, '30s')",
        [(user,) for user in users],
    )
    conn.commit()
    calls = {user: [] for user in users}
    empty_reply = '{"age": null, "sex": null, "country": null, "state": null, "conditions": []}'
    timeout = openai.APITimeoutError(request=httpx.Request("POST", "https://example.invalid"))

    def stub_call(client, prompt, *, temperature, **kwargs):
        user = patient_text(prompt)
        calls[user].append(temperature)
        if user == "filtered":
            raise LLMContentFilteredError("filtered")
        if user == "transient":
            raise timeout
        return empty_reply if user == "empty" else unreadable_reply

    monkeypatch.setattr(demographics, "llm_call", stub_call)
    with caplog.at_level("INFO", logger="pipeline"):
        demographics.run_demographics(path)

    assert calls == {
        "empty": [0.0],
        "filtered": [0.0],
        "transient": [0.0],
        "unreadable": [0.0, 0.7, 1.0],
    }
    assert conn.execute(
        "SELECT user_id, age_bucket, sex, location FROM user_profiles WHERE run_id = 2",
    ).fetchall() == [("empty", None, None, None)]
    assert conn.execute(
        "SELECT user_id, age_bucket FROM user_profiles WHERE run_id = 1 ORDER BY user_id",
    ).fetchall() == [(user, "30s") for user in users]
    assert conn.execute("SELECT COUNT(*) FROM conditions WHERE run_id = 2").fetchone() == (0,)
    assert "3 failures" in caplog.text
    assert "private reply text" not in caplog.text


def test_permanent_api_error_cancels_queued_work(db, monkeypatch):
    conn, path = db
    add_posts(conn, [(f"post-{i}", f"user-{i}", 1, None, f"Synthetic post {i}") for i in range(15)])
    request = httpx.Request("POST", "https://example.invalid")
    error = anthropic.AuthenticationError(
        "bad credentials", response=httpx.Response(401, request=request), body=None,
    )

    class QueuingExecutor:
        def __init__(self, *, max_workers):
            assert max_workers == 10
            self.futures = []
            self.cancel_futures = False

        def submit(self, *args):
            future = Future()
            if not self.futures:
                future.set_exception(error)
            self.futures.append(future)
            return future

        def shutdown(self, *, cancel_futures):
            self.cancel_futures = cancel_futures
            if cancel_futures:
                for future in self.futures:
                    future.cancel()

    pool = QueuingExecutor(max_workers=10)

    def make_executor(*, max_workers):
        assert max_workers == 10
        return pool

    monkeypatch.setattr(demographics, "ThreadPoolExecutor", make_executor)
    with pytest.raises(anthropic.AuthenticationError):
        demographics.run_demographics(path)

    assert len(pool.futures) == 10
    assert pool.cancel_futures and all(future.cancelled() for future in pool.futures[1:])
    assert conn.execute("SELECT COUNT(*) FROM user_profiles").fetchone() == (0,)


def test_commits_multiple_batches_while_streaming_users(db, monkeypatch):
    conn, path = db
    users = [f"user-{i}" for i in range(25)]
    add_posts(conn, [(user, user, 1, None, "Synthetic post") for user in users])
    result = {"age": 34, "conditions": [{"condition_name": "Headache", "condition_type": "Symptom"}]}
    monkeypatch.setattr(demographics, "llm_call", lambda *args, **kwargs: json.dumps(result))

    demographics.run_demographics(path)

    assert conn.execute("SELECT COUNT(*) FROM user_profiles WHERE age_bucket = '30s'").fetchone() == (25,)
    assert conn.execute(
        "SELECT COUNT(*) FROM conditions WHERE condition_name = 'headache' AND condition_type = 'symptom'",
    ).fetchone() == (25,)


def test_extraction_writes_after_another_connection_commits(db, monkeypatch):
    conn, path = db
    add_posts(conn, [(user, user, 1, None, user) for user in ("a", "b", "c", "d")])
    monkeypatch.setattr(demographics, "MAX_IN_FLIGHT", 1)

    def stub_call(client, prompt, **kwargs):
        if patient_text(prompt) == "a":
            # The post stream has started and still has unread rows at this point.
            with closing(sqlite3.connect(path)) as other, other:
                other.execute("UPDATE posts SET flair = 'updated' WHERE post_id = 'd'")
        return '{"age": 34}'

    monkeypatch.setattr(demographics, "llm_call", stub_call)
    demographics.run_demographics(path)

    assert conn.execute("SELECT COUNT(*) FROM user_profiles WHERE age_bucket = '30s'").fetchone() == (4,)
    assert conn.execute("SELECT flair FROM posts WHERE post_id = 'd'").fetchone() == ("updated",)


def test_runs_on_a_database_from_before_age_city_and_finished_at(tmp_path, monkeypatch):
    old_schema = "\n".join(
        line for line in SCHEMA.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith(("age        REAL", "city       TEXT", "finished_at INTEGER"))
    ).replace("config  TEXT NOT NULL,", "config  TEXT NOT NULL")
    path = tmp_path / "old.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(old_schema)
        assert "age" not in {row[1] for row in conn.execute("PRAGMA table_info(user_profiles)")}
        add_posts(conn, [("post", "patient", 1, None, "I'm 34")])
    monkeypatch.setattr(demographics, "get_client", lambda: None)
    monkeypatch.setattr(demographics, "llm_call", lambda *args, **kwargs: '{"age": 34}')

    demographics.run_demographics(path)

    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT age_bucket, age, city FROM user_profiles").fetchall() == [("30s", 34.0, None)]
        assert conn.execute("SELECT finished_at IS NOT NULL FROM extraction_runs").fetchone() == (1,)


def test_records_finish_time_and_provider_only_for_a_clean_run(db, monkeypatch):
    conn, path = db
    add_posts(conn, [("p1", "a", 1, None, "a"), ("p2", "b", 1, None, "b")])
    monkeypatch.setattr(demographics, "llm_call", lambda *args, **kwargs: '{"age": 34}')
    demographics.run_demographics(path)

    request = httpx.Request("POST", "https://example.invalid")
    error = anthropic.AuthenticationError("bad key", response=httpx.Response(401, request=request), body=None)
    monkeypatch.setattr(demographics, "llm_call", lambda *args, **kwargs: (_ for _ in ()).throw(error))
    with pytest.raises(anthropic.AuthenticationError):
        demographics.run_demographics(path)

    runs = conn.execute("SELECT finished_at IS NOT NULL, config FROM extraction_runs ORDER BY run_id").fetchall()
    assert [finished for finished, _ in runs] == [1, 0]
    assert {"provider", "reasoning_mode", "git_dirty"} <= json.loads(runs[0][1]).keys()


@pytest.mark.parametrize(
    ("raw", "age"),
    [
        ('Here is the JSON:\n{"age": 34, "conditions": []}', 34),
        ('{"age": 34, "conditions": [],}', 34),
        ('{"age": 34.0}', 34),
    ],
    ids=["prose-before-object", "trailing-comma", "whole-number-float"],
)
def test_reads_replies_that_main_accepted(raw, age):
    assert demographics._parse_reply(raw)["age"] == age


def test_openrouter_in_band_error_fails_one_user_not_the_run(db, monkeypatch):
    conn, path = db
    add_posts(conn, [("p1", "down", 1, None, "down"), ("p2", "fine", 1, None, "fine")])
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    outage = openai.APIError("provider_unavailable: upstream overloaded", request=request, body=None)

    def stub_call(client, prompt, **kwargs):
        if patient_text(prompt) == "down":
            raise outage
        return '{"age": 34}'

    monkeypatch.setattr(demographics, "llm_call", stub_call)
    demographics.run_demographics(path)

    assert conn.execute("SELECT user_id FROM user_profiles").fetchall() == [("fine",)]
