"""One reply parser, one retry rule and one way to gather text, shared by src/ and
variable_extraction/ (#201, #199). No paid calls: every client here is a stub."""

import time
from types import SimpleNamespace

import anthropic
import httpx
import openai
import pytest

from patientpunk import discover, llm_extract
from patientpunk._utils import (
    collect_texts_from_post,
    collect_texts_from_user,
    is_transient_failure,
    parse_json_response,
)

REQUEST = httpx.Request("POST", "https://example.invalid")


@pytest.mark.parametrize(("reply", "kind", "expected"), [
    ('{"a": 1}', None, {"a": 1}),
    ('```json\n{"a": 1}\n```', None, {"a": 1}),
    ('```json{"a": 1}```', None, {"a": 1}),
    ('```\n[1, 2]\n```', None, [1, 2]),
    ('Here it is: {"a": 1} hope that helps', None, {"a": 1}),
    # Prose before a fence, and a bracket after it: only the fenced block is JSON.
    ('Result:\n```json\n[1, 2]\n```\nSee [1] above', list, [1, 2]),
    ('{"a": [1, 2,],}', None, {"a": [1, 2]}),                 # trailing commas (was src/ only)
    ('{"quote": "a ```b``` c"}', None, {"quote": "a ```b``` c"}),  # backticks inside a string
    ('{"quote": "x, }"}', None, {"quote": "x, }"}),            # valid JSON is never comma-repaired
    ('{"results": [1, 2]}', list, [1, 2]),                     # a list asked for is taken from its brackets
    ('[{"a": 1}]', dict, {"a": 1}),
    ('{"key": missing_quotes}', None, None),
    ("", None, None),
    ("no JSON here", dict, None),
])
def test_parse_json_response(reply, kind, expected):
    assert parse_json_response(reply, kind) == expected


def _status(status):
    exc = Exception(f"HTTP {status}")
    exc.status_code = status
    return exc


def _in_band(message):
    return openai.APIError(message, request=REQUEST, body=None)


@pytest.mark.parametrize(("exc", "transient"), [
    (_status(429), True),
    (_status(503), True),
    (httpx.ReadTimeout("timed out"), True),
    (httpx.ConnectError("refused"), True),            # missed by llm_extract's name match (#126)
    (httpx.RemoteProtocolError("peer closed"), True),  # missed by llm_extract and discover (#126)
    (anthropic.APIConnectionError(request=REQUEST), True),
    (openai.APITimeoutError(request=REQUEST), True),
    (ConnectionResetError("reset"), True),
    (_in_band("provider_unavailable"), True),          # missed by llm_extract and discover
    (_status(400), False),
    (_status(401), False),
    (_status(402), False),                             # billing
    (_in_band("something else broke"), False),
    (ValueError("bad JSON"), False),
])
def test_is_transient_failure(exc, transient):
    assert is_transient_failure(exc) is transient


class _Client:
    """Fails with each of ``failures`` in turn, then replies; counts calls."""

    def __init__(self, *failures):
        self.failures, self.calls = list(failures), 0
        self.messages = self

    def create(self, **kwargs):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(text='{"fields": {}}')], stop_reason="end_turn")


@pytest.fixture
def no_cache_no_sleep(monkeypatch):
    for module in (discover, llm_extract):
        monkeypatch.setattr(module, "cached_completion", lambda **kw: kw["call_fn"]())
    sleeps = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    return sleeps


@pytest.mark.parametrize("call", [
    lambda client: discover.call_model(client, "m", "sys", "msg"),
    lambda client: llm_extract.call_haiku(client, "sys", "msg", label="p0"),
], ids=["discover", "llm_extract"])
@pytest.mark.parametrize(("failures", "calls", "raises"), [
    ((), 1, None),
    ((httpx.ConnectError("refused"),), 2, None),     # discover used to fail on the first one
    ((_in_band("overloaded"),), 2, None),
    ((httpx.ConnectError("refused"),) * 5, 5, httpx.ConnectError),
    ((_status(402),), 1, Exception),
], ids=["ok", "transport-then-ok", "in-band-then-ok", "bounded", "billing-fails-fast"])
def test_paid_calls_per_path(no_cache_no_sleep, call, failures, calls, raises):
    client = _Client(*failures)
    if raises:
        with pytest.raises(raises):
            call(client)
    else:
        assert call(client) == '{"fields": {}}'
    assert client.calls == calls
    assert no_cache_no_sleep == [2, 5, 15, 30][:calls - 1]


def test_post_text_is_title_and_body_only_cleaned():
    post = {"title": "  Long COVID 2 years in  ", "body": " [removed] ",
            "comments": [{"author_hash": "someone_else", "body": "I have POTS"}]}
    assert collect_texts_from_post(post) == ["Long COVID 2 years in"]


def test_user_history_puts_chosen_subreddits_first_in_input_order():
    user = {"posts": [{"subreddit": "gaming", "title": "Game", "body": "[deleted]"},
                      {"subreddit": "CFS", "title": "Crash", "body": "  PEM again  "},
                      {"subreddit": None, "title": "No sub", "body": ""}],
            "comments": [{"subreddit": "gaming", "body": "gg"}, {"subreddit": "pots", "body": "Tilt test"}]}
    assert collect_texts_from_user(user) == ["Game", "Crash", "PEM again", "No sub", "gg", "Tilt test"]
    assert collect_texts_from_user(user, first={"cfs", "pots"}) == [
        "Crash", "PEM again", "Tilt test", "Game", "No sub", "gg"]


def test_health_first_text_survives_the_8000_character_cut():
    user = {"posts": [{"subreddit": "gaming", "title": "x" * llm_extract.MAX_TEXT_CHARS, "body": ""},
                      {"subreddit": "cfs", "title": "LDN helped my brain fog", "body": ""}]}
    message = llm_extract.build_user_message(collect_texts_from_user(user, first=llm_extract.HEALTH_SUBREDDITS))
    assert "LDN helped my brain fog" in message and "[TRUNCATED]" in message


def test_removed_markers_match_in_any_case():
    # The demographics extractor casefolded the markers and the rest didn't; now one rule does.
    from extract_demographics_conditions import _post_text

    from patientpunk._utils import clean_text
    assert clean_text(" [Removed] ") == "" and clean_text("[DELETED]") == ""
    assert _post_text("[deleted]", "[Removed]") == "" and _post_text(" Title ", "[DELETED]") == "Title"


_RECORD = '{"fields": {}}'


@pytest.mark.parametrize(("reply", "parsed"), [
    (f"```json\n[{_RECORD}, {_RECORD}]\n```", True),
    (f"Here you go:\n```\n[{_RECORD}, {_RECORD},]\n```", True),
    (f"[{_RECORD}, {_RECORD}", False),   # truncated
    (_RECORD, False),                    # an object, not an array
])
def test_batch_reply_parses_or_splits(monkeypatch, reply, parsed):
    from patientpunk._utils import split_retry_batch
    calls = []

    def fake(client, system, message, temperature=None, label="?"):
        calls.append(message)
        return reply if len(calls) == 1 else _RECORD  # the split falls back to one record per call
    monkeypatch.setattr(llm_extract, "call_haiku", fake)
    items = [{"user_message": "a", "post_id": "p1"}, {"user_message": "b", "post_id": "p2"}]
    out = split_retry_batch(lambda batch: llm_extract._call_batch_raw(None, "sys", batch), items)
    assert out == [{"fields": {}}, {"fields": {}}]
    assert len(calls) == (1 if parsed else 3)
