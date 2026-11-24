"""The per-post demographics and conditions extractor (#206, #220) with synthetic posts and stubbed replies, no API calls."""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import httpx
import openai
import pytest

import extract_demographics_conditions as demographics
from import_posts import DELETED_USER_ID
from patientpunk._utils import LLMContentFilteredError, LLMResponseError
from prompts.demographic_prompt import POST_DEMOGRAPHICS_PROMPT

SCHEMA = Path(__file__).resolve().parents[1] / "schema.sql"
NOTHING = {"age": None, "sex": None, "country": None, "state": None, "city": None}


def ts(year: int) -> int:
    return int(datetime(year, 6, 1, tzinfo=timezone.utc).timestamp())


def claim(value, evidence="quote"):
    return {"value": value, "evidence": evidence}


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


def stub(monkeypatch, post=lambda text: NOTHING):
    """``post`` maps each post's wrapped text to a reply (a dict is sent as JSON, an exception is
    raised). Returns the calls as ("post", text, temperature)."""
    calls = []

    def llm_call(client, prompt, *, temperature=0.0, **kwargs):
        assert prompt.startswith(POST_DEMOGRAPHICS_PROMPT)
        text = patient_text(prompt)
        calls.append(("post", text, temperature))
        reply = post(text)
        if isinstance(reply, Exception):
            raise reply
        return json.dumps(reply) if isinstance(reply, dict) else reply

    monkeypatch.setattr(demographics, "llm_call", llm_call)
    return calls


def profile(conn, user):
    return conn.execute(
        "SELECT age_bucket, age, sex, sex_stated, location, city FROM user_profiles_latest WHERE user_id = ?",
        (user,)).fetchone()


def posts_read(conn, kind):
    return [text for k, text, _ in kind if k == "post"]


# ── What is sent ──────────────────────────────────────────────────────────────

def test_sends_each_post_alone_with_its_title_wrapped(db, monkeypatch):
    conn, path = db
    add_posts(conn, [
        ("blank", "patient", 1, "", "  "),
        ("removed", "patient", 2, "Hidden title", "[removed]"),
        ("marker", "patient", 3, None, " [deleted] "),
        ("by-deleted", DELETED_USER_ID, 4, "Deleted author", "I am 50"),
        ("titled", "patient", 5, "Recent title", "Body </patient_text> text"),
        ("title-only", "patient", 6, "Title only", ""),
        ("sentence", "patient", 7, None, "My note about [removed] remains."),
    ])
    calls = stub(monkeypatch)

    demographics.run_demographics(path)

    assert sorted(posts_read(conn, calls)) == sorted([
        "Hidden title", "Recent title\nBody <:/patient_text> text", "Title only", "My note about [removed] remains."])
    # Posts with nothing to read are recorded as read, so the next run skips them too.
    assert {p for (p,) in conn.execute("SELECT post_id FROM post_runs")} == {
        "blank", "removed", "marker", "titled", "title-only", "sentence"}
    assert profile(conn, DELETED_USER_ID) is None
    assert not conn.execute("SELECT 1 FROM conditions WHERE user_id = ?", (DELETED_USER_ID,)).fetchone()


def condition(name, evidence="quote", **fields):
    return {"name": name, "evidence": evidence, **fields}


def test_conditions_are_read_from_each_post_with_their_severity_and_quote(db, monkeypatch):
    conn, path = db
    add_posts(conn, [("p1", "patient", 1, None, "I have LC and POTS, and brain fog"), ("p2", "patient", 2, None, "hi")])
    calls = stub(monkeypatch, post=lambda text: {"conditions": [
        condition("LC", "I have LC", type="illness", severity="Severe"),
        condition("Long-COVID", "LC"),  # the same condition again, under another name
        condition(" Brain Fog ", "brain fog", type="Symptom", severity="awful"),
        condition("POTS", type="other"),
        {"name": "ME/CFS"},  # no quote
        "POTS",  # a bare name the post says word for word
    ]} if text.startswith("I have") else NOTHING)

    stats = demographics.run_demographics(path)

    assert posts_read(conn, calls) == ["I have LC and POTS, and brain fog", "hi"]  # one call per post
    assert conn.execute("SELECT post_id, condition_name, condition_type, severity, evidence FROM conditions "
                        "ORDER BY condition_name").fetchall() == [
        ("p1", "brain fog", "symptom", None, "brain fog"),
        ("p1", "long covid", "illness", "severe", "I have LC"),
        ("p1", "pots", "illness", None, "quote")]
    assert stats["conditions"] == 3


@pytest.mark.parametrize("conditions", [None, "POTS", {"name": "POTS"}, [None, 3, ["POTS"]]])
def test_badly_shaped_conditions_are_none_and_keep_the_claims(db, monkeypatch, conditions):
    conn, path = db
    add_posts(conn, [("p1", "patient", 1, None, "I'm 34")])
    stub(monkeypatch, post=lambda text: {"age": claim(34), "conditions": conditions})

    demographics.run_demographics(path)

    assert conn.execute("SELECT COUNT(*) FROM conditions").fetchone() == (0,)
    assert conn.execute("SELECT value FROM demographic_claims").fetchall() == [("34",)]


@pytest.mark.parametrize("reread", [{"age": None}, {"age": None, "conditions": "POTS"},
                                    {"age": None, "conditions": None}, {"age": None, "conditions": {"name": "POTS"}}],
                         ids=["missing", "string", "null", "object"])
def test_a_reread_without_a_conditions_list_keeps_the_earlier_conditions(db, monkeypatch, reread):
    conn, path = db
    add_posts(conn, [("p1", "a", ts(2024), None, "I'm 34 and my POTS is severe")])
    stub(monkeypatch, post=lambda text: {"conditions": [condition("POTS", severity="severe")]})
    demographics.run_demographics(path)

    stub(monkeypatch, post=lambda text: {**reread, "age": claim(34)})
    demographics.run_demographics(path, reread=True)

    assert conn.execute("SELECT condition_name, severity FROM conditions_latest").fetchall() == [("pots", "severe")]
    assert conn.execute("SELECT field, value FROM demographic_claims_latest").fetchall() == [("age", "34")]

    stub(monkeypatch, post=lambda text: {"age": claim(34), "conditions": []})  # an explicit [] retracts
    demographics.run_demographics(path, reread=True)
    assert conn.execute("SELECT COUNT(*) FROM condition_observations").fetchone() == (0,)


def test_a_reread_retracts_a_condition_and_newer_posts_update_it(db, monkeypatch):
    conn, path = db
    add_posts(conn, [("p1", "a", ts(2024), None, "my POTS is severe"), ("p2", "a", ts(2025), None, "POTS gone")])
    replies = {"my POTS is severe": [condition("POTS", severity="severe"), condition("migraine")],
               "POTS gone": [condition("POTS", severity="resolved")]}
    stub(monkeypatch, post=lambda text: {"conditions": replies[text]})
    demographics.run_demographics(path)
    latest = "SELECT condition_name, severity, first_seen, last_seen, n_posts FROM conditions_latest ORDER BY 1"
    assert conn.execute(latest).fetchall() == [
        ("migraine", None, ts(2024), ts(2024), 1), ("pots", "resolved", ts(2024), ts(2025), 2)]

    replies["my POTS is severe"] = [condition("POTS", severity="severe")]  # migraine was a misread
    stub(monkeypatch, post=lambda text: {"conditions": replies[text]})
    demographics.run_demographics(path, reread=True)
    assert conn.execute(latest).fetchall() == [("pots", "resolved", ts(2024), ts(2025), 2)]


# ── Claims ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("field", "value", "stored"),
    [
        ("age", 34, "34"), ("age", 34.0, "34"), ("age", "late 30s", "late 30s"), ("age", "25-34", "25-34"),
        ("age", 9, None), ("age", 100, None), ("age", "34.5", None), ("age", "34 | 36", None), ("age", True, None),
        ("sex", "F", "F"), ("sex", "non-binary | female", "non-binary | female"), ("sex", "trans man", "trans man"),
        ("sex", "unknown", None), ("sex", ["M"], None),
        ("country", "Trinidad and Tobago", "Trinidad and Tobago"), ("country", "US or Canada", None),
        ("state", "Texas / Ohio", None), ("state", "Texas, Ohio", None), ("state", "Washington, D.C.", "Washington, D.C."),
        ("country", "Korea, Republic of", "Korea, Republic of"), ("country", "USA, Canada", None),
        ("city", "Portland", "Portland"),
        ("city", "Austin, TX", "Austin, TX"), ("city", "Austin or Dallas", None), ("city", "", None),
    ],
)
def test_checks_each_claim_before_writing_it(db, monkeypatch, field, value, stored):
    conn, path = db
    add_posts(conn, [("post", "patient", 1, None, "A post")])
    stub(monkeypatch, post=lambda text: {field: claim(value, " I said so ")})

    demographics.run_demographics(path)

    expected = [(field, stored, "I said so")] if stored else []
    assert conn.execute("SELECT field, value, evidence FROM demographic_claims").fetchall() == expected
    assert conn.execute("SELECT post_id FROM post_runs").fetchall() == [("post",)]


def test_a_value_without_a_quote_is_not_a_claim(db, monkeypatch):
    conn, path = db
    add_posts(conn, [("post", "patient", 1, None, "A post")])
    stub(monkeypatch, post=lambda text: {"age": {"value": 34}, "sex": claim("female", "  ")})

    demographics.run_demographics(path)

    assert conn.execute("SELECT COUNT(*) FROM demographic_claims").fetchone() == (0,)


@pytest.mark.parametrize(
    ("stated", "sex"),
    [("non-binary | female", "non-binary"), ("female, non-binary", "non-binary"), ("non-binary and female", "non-binary"),
     ("non-binary/female", "non-binary"), ("female | suspected intersex", "female"),
     ("Man", "male"), ("cis woman", "female"), ("cisgender male", "male"), ("cis-female | non-binary", "non-binary"),
     ("trans man", None), ("female | male", None), ("trans woman | female", None), ("trans man | male", None),
     ("woman, trans", None), ("female | transgender", None), ("trans | non-binary", "non-binary")],
)
def test_multi_value_sex_is_kept_and_normalized_by_rule(db, monkeypatch, stated, sex):
    conn, path = db
    add_posts(conn, [("post", "patient", 1, None, "A post")])
    stub(monkeypatch, post=lambda text: {"sex": claim(stated)})

    demographics.run_demographics(path)

    assert profile(conn, "patient")[2:4] == (sex, stated)


def test_resolves_claims_from_several_posts_into_one_profile(db, monkeypatch):
    conn, path = db
    add_posts(conn, [
        ("p2024", "patient", ts(2024), None, "29, US"),
        ("p2025", "patient", ts(2025), None, "Texas, Austin"),
        ("p2026", "patient", ts(2026), None, "I'm 35 now"),
    ])
    replies = {
        "29, US": {"age": claim(29), "country": claim("US")},
        "Texas, Austin": {"state": claim("Texas"), "city": claim("Austin")},
        "I'm 35 now": {"age": claim(35)},
    }
    stub(monkeypatch, post=replies.get)

    stats = demographics.run_demographics(path)

    assert profile(conn, "patient") == ("30s", 35.0, None, None, "United States / Texas", "Austin")
    assert stats["disagreements"] == {"age": 1}


# ── Replies ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw",
    ['Here is the JSON:\n{"age": {"value": 34, "evidence": "34"}}', '{"age": {"value": 34, "evidence": "34"},}',
     '```json\n{"age": {"value": 34, "evidence": "34"}}\n```'],
    ids=["prose-before-object", "trailing-comma", "fenced"],
)
def test_reads_replies_with_text_around_the_object(raw):
    assert demographics.parse_post(raw) == ({"age": ("34", "34")}, None)  # no conditions list: None, not []


def test_an_unreadable_reply_is_retried_hotter_with_the_same_prompt(db, monkeypatch):
    conn, path = db
    add_posts(conn, [("post", "patient", 1, None, "I'm 34")])
    replies = iter([LLMResponseError("empty"), "no JSON here", {"age": claim(34)}])
    calls = stub(monkeypatch, post=lambda text: next(replies))

    demographics.run_demographics(path)

    assert [t for kind, _, t in calls if kind == "post"] == [0.0, 0.7, 1.0]
    assert conn.execute("SELECT value FROM demographic_claims").fetchall() == [("34",)]


@pytest.mark.parametrize(
    "unreadable",
    ['{"error": "private reply text"}', "no JSON here"],
    ids=["unknown-fields", "no-object"],
)
def test_failed_posts_stay_unread_and_keep_previous_profiles(db, monkeypatch, caplog, unreadable):
    conn, path = db
    users = ("empty", "filtered", "transient", "unreadable")
    add_posts(conn, [(user, user, 1, None, user) for user in users])
    stub(monkeypatch, post=lambda text: {"age": claim(34)})
    demographics.run_demographics(path)  # an earlier run gives everyone a 30s profile
    timeout = openai.APITimeoutError(request=httpx.Request("POST", "https://example.invalid"))
    replies = {"empty": NOTHING, "filtered": LLMContentFilteredError("filtered"), "transient": timeout,
               "unreadable": unreadable}
    calls = stub(monkeypatch, post=replies.get)

    with caplog.at_level("INFO", logger="pipeline"):
        stats = demographics.run_demographics(path, reread=True)

    assert [t for kind, text, t in calls if kind == "post" and text == "unreadable"] == [0.0, 0.7, 1.0]
    assert stats["posts_failed"] == 2 and stats["failed_users"] == 2
    assert "private reply text" not in caplog.text
    # An empty reread retracts the age. A filtered one is read but keeps its earlier claim: the filter
    # would block it every time, and says nothing about what the post states. The failed users keep
    # theirs, and their posts stay unread.
    assert {u: profile(conn, u)[0] for u in users} == {
        "empty": None, "filtered": "30s", "transient": "30s", "unreadable": "30s"}
    assert stats["posts_blocked"] == 1
    calls = stub(monkeypatch, post=lambda text: {"age": claim(41)})
    demographics.run_demographics(path)
    assert sorted(posts_read(conn, calls)) == ["transient", "unreadable"]
    assert {u: profile(conn, u)[0] for u in ("transient", "unreadable")} == {"transient": "40s", "unreadable": "40s"}


def test_an_unreadable_reply_is_asked_again_by_the_next_run_through_the_real_cache(db, monkeypatch, tmp_path):
    """The other tests stub llm_call; this one uses it, with the on-disk cache on and a stub client."""
    from types import SimpleNamespace
    from patientpunk import llm_cache
    conn, path = db
    add_posts(conn, [("p1", "a", 1, None, "I'm 34")])
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(llm_cache, "_enabled_override", True)
    post_replies = iter(["not JSON"] * 3 + [json.dumps({**NOTHING, "age": claim(34)})])
    sent = []

    class Stream:
        def __init__(self, prompt):
            self.prompt = prompt
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False
        def get_final_message(self):
            assert self.prompt.startswith(POST_DEMOGRAPHICS_PROMPT)
            sent.append("post")
            text = next(post_replies)
            return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn")

    client = SimpleNamespace(messages=SimpleNamespace(stream=lambda **kw: Stream(kw["messages"][0]["content"])))
    monkeypatch.setattr(demographics, "get_client", lambda: client)

    assert demographics.run_demographics(path)["posts_failed"] == 1
    stats = demographics.run_demographics(path)

    assert sent.count("post") == 4  # the second run asked the model, not the cache
    assert stats["posts_read"] == 1 and stats["posts_failed"] == 0
    assert profile(conn, "a")[0] == "30s"


def test_a_post_the_filter_always_blocks_does_not_freeze_the_profile(db, monkeypatch):
    conn, path = db
    add_posts(conn, [("blocked", "a", 1, None, "graphic text"), ("ok", "a", 2, None, "I'm 34")])
    replies = {"graphic text": LLMContentFilteredError("blocked"), "I'm 34": {"age": claim(34)}}
    calls = stub(monkeypatch, post=replies.get)

    demographics.run_demographics(path)
    demographics.run_demographics(path)

    assert profile(conn, "a")[0] == "30s"
    assert [text for kind, text, _ in calls if kind == "post"].count("graphic text") == 1


def test_a_user_with_an_unread_post_keeps_their_profile_until_it_is_read(db, monkeypatch):
    conn, path = db
    add_posts(conn, [("b1", "b", 1, None, "b"), ("z1", "z", 1, None, "I'm 34")])
    stub(monkeypatch, post=lambda text: {"age": claim(34)} if text == "I'm 34" else NOTHING)
    demographics.run_demographics(path)
    # A reread retracts z1's age while z2 fails, so z keeps 30s with z2 unread.
    add_posts(conn, [("z2", "z", 2, None, "now 41")])
    timeout = openai.APITimeoutError(request=httpx.Request("POST", "https://example.invalid"))
    stub(monkeypatch, post=lambda text: timeout if text == "now 41" else NOTHING)
    demographics.run_demographics(path, reread=True)
    assert profile(conn, "z")[0] == "30s"
    add_posts(conn, [("b2", "b", 3, None, "b again")])
    calls = stub(monkeypatch)

    demographics.run_demographics(path, limit=1)  # reads user b only

    assert posts_read(conn, calls) == ["b again"]
    assert profile(conn, "z")[0] == "30s"  # not rebuilt from z's incomplete claims


def test_reread_cannot_be_limited(db):
    _, path = db
    with pytest.raises(ValueError, match="--reread"):
        demographics.run_demographics(path, reread=True, limit=1)


def test_a_stopped_reread_is_not_resumed_and_the_next_reread_starts_over(db, monkeypatch, caplog):
    conn, path = db
    add_posts(conn, [(f"p{i}", f"u{i}", 1, None, f"post {i}") for i in range(12)])
    stub(monkeypatch)
    demographics.run_demographics(path)
    request = httpx.Request("POST", "https://example.invalid")
    error = anthropic.AuthenticationError("bad key", response=httpx.Response(401, request=request), body=None)
    stub(monkeypatch, post=lambda text: error)  # a bad key: the reread stops having read nothing
    with pytest.raises(anthropic.AuthenticationError):
        demographics.run_demographics(path, reread=True)

    # An ordinary run doesn't pick up the stopped reread: it reads only the new post, and warns.
    add_posts(conn, [("new", "u0", 2, None, "new post")])
    calls = stub(monkeypatch)
    with caplog.at_level("WARNING", logger="pipeline"):
        demographics.run_demographics(path)
    assert posts_read(conn, calls) == ["new post"]
    assert "stopped before finishing" in caplog.text

    # The next --reread starts over and reads every post, the new one included.
    calls = stub(monkeypatch)
    demographics.run_demographics(path, reread=True)
    assert sorted(posts_read(conn, calls)) == sorted([f"post {i}" for i in range(12)] + ["new post"])
    calls = stub(monkeypatch)
    demographics.run_demographics(path)
    assert posts_read(conn, calls) == []


def test_the_post_pass_commits_as_it_goes(db, monkeypatch):
    conn, path = db
    add_posts(conn, [(f"p{i}", f"u{i:02}", 1, None, f"post {i}") for i in range(5)])
    monkeypatch.setattr(demographics, "COMMIT_EVERY", 2)
    other = sqlite3.connect(path, timeout=0, check_same_thread=False)
    seen = []

    def post(text):  # what another connection sees of the pass so far
        seen.append(other.execute("SELECT COUNT(*) FROM conditions").fetchone()[0])
        return {"conditions": [condition("POTS")]}

    monkeypatch.setattr(demographics, "MAX_IN_FLIGHT", 1)
    stub(monkeypatch, post=post)
    demographics.run_demographics(path)
    other.close()

    assert seen == [0, 0, 2, 2, 4]  # committed after every 2nd post read, not once at the end


def test_dry_run_reports_what_a_run_would_send_and_sends_nothing(db, monkeypatch):
    conn, path = db
    add_posts(conn, [("p1", "a", 1, "Title", "x" * 400), ("p2", "a", 2, None, "y"), ("p3", "b", 1, None, "z")])
    calls = stub(monkeypatch)

    plan = demographics.run_demographics(path, dry_run=True)
    limited = demographics.run_demographics(path, limit=1, dry_run=True)

    assert calls == [] and conn.execute("SELECT COUNT(*) FROM extraction_runs").fetchone() == (0,)
    assert {k: plan[k] for k in ("posts", "users", "post_calls")} == {"posts": 3, "users": 2, "post_calls": 3}
    assert plan["approx_input_tokens"] > 3 * len(POST_DEMOGRAPHICS_PROMPT) // 4
    assert (limited["posts"], limited["users"]) == (2, 1)
    demographics.run_demographics(path)
    assert demographics.run_demographics(path, dry_run=True)["posts"] == 0
    assert demographics.run_demographics(path, reread=True, dry_run=True)["posts"] == 3


def test_a_permanent_error_stops_the_run_and_sends_no_queued_posts(db, monkeypatch):
    conn, path = db
    add_posts(conn, [(f"post-{i}", f"user-{i}", 1, None, f"Synthetic post {i}") for i in range(15)])
    request = httpx.Request("POST", "https://example.invalid")
    error = anthropic.AuthenticationError("bad key", response=httpx.Response(401, request=request), body=None)
    calls = stub(monkeypatch, post=lambda text: error)

    with pytest.raises(anthropic.AuthenticationError):
        demographics.run_demographics(path)

    assert len(calls) == demographics.MAX_IN_FLIGHT  # the 5 queued posts were never sent
    assert conn.execute("SELECT COUNT(*) FROM post_runs").fetchone() == (0,)
    assert conn.execute("SELECT finished_at FROM extraction_runs").fetchone() == (None,)


# ── Runs, checkpoints and rereads ────────────────────────────────────────────

def test_the_next_run_reads_only_unread_posts_and_reread_reads_all(db, monkeypatch):
    conn, path = db
    add_posts(conn, [("p1", "a", 1, None, "first"), ("p2", "b", 1, None, "second")])
    stub(monkeypatch)
    demographics.run_demographics(path)  # finds nothing; both posts are still checkpointed

    add_posts(conn, [("p3", "a", 2, None, "third")])
    calls = stub(monkeypatch)
    demographics.run_demographics(path)
    assert posts_read(conn, calls) == ["third"]

    calls = stub(monkeypatch)
    demographics.run_demographics(path, reread=True)
    assert sorted(posts_read(conn, calls)) == ["first", "second", "third"]
    calls = stub(monkeypatch)
    demographics.run_demographics(path)
    assert posts_read(conn, calls) == []


def test_a_reread_that_finds_nothing_retracts_and_a_restart_still_resolves(db, monkeypatch):
    conn, path = db
    add_posts(conn, [("p1", "a", 1, None, "I'm 34")])
    stub(monkeypatch, post=lambda text: {"age": claim(34)})
    demographics.run_demographics(path)
    assert profile(conn, "a")[0] == "30s"

    # A reread whose claims were committed but that stopped before resolving profiles.
    stub(monkeypatch)
    with monkeypatch.context() as m, pytest.raises(KeyboardInterrupt):
        m.setattr(demographics, "resolve_profiles", lambda *args: (_ for _ in ()).throw(KeyboardInterrupt))
        demographics.run_demographics(path, reread=True)
    calls = stub(monkeypatch)

    stats = demographics.run_demographics(path)  # zero unread posts

    assert posts_read(conn, calls) == []
    assert stats["profiles_written"] == 1
    assert profile(conn, "a") == (None, None, None, None, None, None)


def test_an_age_moves_only_with_its_authors_own_posts(db, monkeypatch):
    conn, path = db
    add_posts(conn, [("a-2024", "a", ts(2024), None, "I'm 29"), ("b-2024", "b", ts(2024), None, "hi")])
    stub(monkeypatch, post=lambda text: {"age": claim(29)} if text == "I'm 29" else NOTHING)
    demographics.run_demographics(path)
    assert profile(conn, "a")[:2] == ("20s", 29.0)

    add_posts(conn, [("b-2026", "b", ts(2026), None, "hello again")])
    calls = stub(monkeypatch)
    demographics.run_demographics(path)
    assert posts_read(conn, calls) == ["hello again"]
    assert profile(conn, "a")[:2] == ("20s", 29.0)

    add_posts(conn, [("a-2026", "a", ts(2026), None, "still here")])
    demographics.run_demographics(path)
    assert profile(conn, "a")[:2] == ("30s", 31.0)


@pytest.mark.parametrize("reply, text", [
    ({"sex": "M"}, "I'm 34"), ({"sex": "male"}, "I am female"), ({"age": "34"}, "I take 340 mg"),
    ({"state": "Ohio"}, "my Ohioan friend"),
])
def test_a_bare_value_must_be_whole_words_in_the_post(reply, text):
    assert demographics.parse_post(json.dumps(reply), text) == ({}, None)


@pytest.mark.parametrize("bare, text, name", [
    ("ME", "Can someone help me", None), ("POTS", "pots and pans", None), ("POTS", "POTSy", None),
    ("ME", "I have ME", "me/cfs"), ("POTS", "my POTS flared", "pots"),
])
def test_a_bare_condition_counts_only_when_the_post_names_it_in_that_case(bare, text, name):
    parsed = demographics.parse_conditions({"conditions": [bare]}, text)
    assert parsed == ([(name, "illness", None, bare)] if name else [])


@pytest.mark.parametrize("stated, severity", [
    ("Severe", "severe"), ("moderate to severe", "severe"), ("mild-moderate", "moderate"), ("mostly resolved", "resolved"),
    ("awful", None), ("", None), (3, None), ("not severe", None), ("no longer severe", None), ("isn't mild", None),
])
def test_severity_takes_the_worst_level_a_phrase_names(stated, severity):
    assert demographics.parse_conditions({"conditions": [condition("POTS", severity=stated)]})[0][2] == severity


def test_a_condition_listed_twice_keeps_its_stated_severity():
    reply = {"conditions": [condition("POTS"), condition("pots", severity="severe")]}
    assert demographics.parse_conditions(reply) == [("pots", "illness", "severe", "quote")]


def test_a_bare_value_is_kept_only_when_the_post_says_it_word_for_word(db, monkeypatch):
    conn, path = db
    add_posts(conn, [("post", "patient", 1, None, "I'm 34 and Transgender, in Texas")])
    calls = stub(monkeypatch, post=lambda text: {"age": claim(34), "sex": "transgender", "state": "Ohio"})

    demographics.run_demographics(path)

    assert [t for kind, _, t in calls if kind == "post"] == [0.0]  # read at once, not retried
    assert conn.execute("SELECT field, value, evidence FROM demographic_claims ORDER BY field").fetchall() == [
        ("age", "34", "quote"), ("sex", "transgender", "transgender")]  # Ohio isn't in the post


def test_limit_caps_the_users_read(db, monkeypatch):
    conn, path = db
    add_posts(conn, [("p1", "a", 1, None, "a1"), ("p2", "a", 2, None, "a2"), ("p3", "b", 1, None, "b1")])
    calls = stub(monkeypatch)

    assert demographics.run_demographics(path, limit=1)["users"] == 1

    assert sorted(posts_read(conn, calls)) == ["a1", "a2"]


def test_records_finish_time_and_provider_for_a_clean_run(db, monkeypatch):
    conn, path = db
    add_posts(conn, [("p1", "a", 1, None, "a")])
    stub(monkeypatch)
    demographics.run_demographics(path, reread=True)

    finished, config = conn.execute("SELECT finished_at, config FROM extraction_runs").fetchone()
    assert finished is not None
    config = json.loads(config)
    assert {"provider", "reasoning_mode", "git_dirty"} <= config.keys() and config["reread"] is True


def test_runs_on_a_database_from_before_the_claim_tables(tmp_path, monkeypatch):
    old_schema = SCHEMA.read_text(encoding="utf-8")
    old_schema = old_schema[:old_schema.index("-- A demographics run records here")]
    old_schema = "\n".join(
        line for line in old_schema.splitlines()
        if not line.lstrip().startswith(("age        REAL", "sex_stated TEXT", "city       TEXT", "finished_at INTEGER",
                                          "ever_minor INTEGER", "evidence       TEXT"))
    ).replace("config  TEXT NOT NULL,", "config  TEXT NOT NULL").replace("severity       TEXT,", "severity       TEXT")
    path = tmp_path / "old.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(old_schema)
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'demographic_claims'").fetchone()
        add_posts(conn, [("post", "patient", 1, None, "I'm 34")])
    monkeypatch.setattr(demographics, "get_client", lambda: None)
    stub(monkeypatch, post=lambda text: {"age": claim(34), "sex": claim("female")})

    demographics.run_demographics(path)

    with closing(sqlite3.connect(path)) as conn:
        assert profile(conn, "patient") == ("30s", 34.0, "female", "female", None, None)
        assert conn.execute("SELECT evidence FROM conditions").fetchall() == []  # the column was added


def test_writes_after_another_connection_commits(db, monkeypatch):
    conn, path = db
    add_posts(conn, [(user, user, 1, None, user) for user in ("a", "b", "c", "d")])
    monkeypatch.setattr(demographics, "MAX_IN_FLIGHT", 1)

    def reply(text):
        if text == "a":  # the post stream has started and still has unread rows
            with closing(sqlite3.connect(path)) as other, other:
                other.execute("UPDATE posts SET flair = 'updated' WHERE post_id = 'd'")
        return {"age": claim(34)}

    stub(monkeypatch, post=reply)
    demographics.run_demographics(path)

    assert conn.execute("SELECT COUNT(*) FROM user_profiles WHERE age_bucket = '30s'").fetchone() == (4,)


def test_unnamed_conditions_are_dropped_and_the_rest_kept():
    reply = {"conditions": [condition("ME/CFS"), condition(None), {}, "", condition("  ")]}
    assert demographics.parse_conditions(reply) == [("me/cfs", "illness", None, "quote")]


@pytest.mark.parametrize("name, canonical", [
    ("LC", "long covid"), ("Long-COVID", "long covid"), ("PASC", "long covid"), ("CFS", "me/cfs"),
    ("Myalgic Encephalomyelitis", "me/cfs"), ("Postural Orthostatic Tachycardia Syndrome", "pots"),
    ("Brain  fog.", "brain fog"), ("Hashimoto’s", "hashimoto's"), ("Long-haul COVID", "long covid"),
    ("Long COVID (LC)", "long covid"), ("POTS syndrome", "pots"),
])
def test_canonical_condition(name, canonical):
    assert demographics.canonical_condition(name) == canonical


def test_warns_about_posts_read_before_conditions_were_read_per_post(db, monkeypatch, caplog):
    conn, path = db
    add_posts(conn, [("p1", "a", 1, None, "old"), ("p2", "a", 2, None, "new")])
    conn.execute("INSERT INTO extraction_runs (run_id, run_at, commit_hash, extraction_type, config) "
                 "VALUES (1, 0, 'x', 'demographics', '{}')")
    conn.execute("INSERT INTO post_runs VALUES (1, 'p1')")
    conn.commit()
    calls = stub(monkeypatch)

    with caplog.at_level("WARNING", logger="pipeline"):
        demographics.run_demographics(path)

    assert posts_read(conn, calls) == ["new"]  # no paid reread of the old post
    assert "1 posts were read before conditions were read per post" in caplog.text


@pytest.mark.parametrize("value", ["1e1", "3e1", "inf", "nan"])
def test_age_must_be_written_as_a_number(value):
    assert demographics._claim_value("age", value) is None
