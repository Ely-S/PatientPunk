"""A reply that outgrows its max_tokens should get more room, not end the run.

Every src/ stage sizes max_tokens with its own hand-tuned constant -- 250/text in
extract, 15/name in canonicalize, 10/item and 80/item in classify -- each fitted
to a different model. On a more verbose one they all truncate, and check_response
turns that into LLMResponseError, which none of the callers' `except LLMParseError`
handlers catch. Growing the budget fixes every call site at once, and costs
nothing: max_tokens is a ceiling, not a charge.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from patientpunk._utils import LLMResponseError  # noqa: E402 -- loads .env first

os.environ["LLM_PROVIDER"] = "anthropic"

from utilities import llm_call  # noqa: E402


class _FakeStream:
    def __init__(self, message):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._message


def _reply(text, stop_reason):
    return _FakeStream(SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)] if text else [],
        stop_reason=stop_reason))


def _client(fits_at: int, tried: list):
    """A model whose reply needs `fits_at` tokens; records every budget tried."""
    def stream(**kwargs):
        tried.append(kwargs["max_tokens"])
        if kwargs["max_tokens"] < fits_at:
            return _reply("partial", "max_tokens")
        return _reply("complete answer", "end_turn")
    return SimpleNamespace(messages=SimpleNamespace(stream=stream))


@pytest.fixture(autouse=True)
def _cache_root(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    from patientpunk import llm_cache
    llm_cache.set_cache_enabled(None)
    yield
    llm_cache.set_cache_enabled(None)


@pytest.mark.parametrize("fits_at, expected", [
    # Growth must not cost an extra call on the normal path.
    (50, [100]),
    # classify.py budgets 10 tokens/item; on 20 items that is 100, and the reply
    # needed more. Before this it raised and ended the run.
    (350, [100, 200, 400]),
    # A reply that never fits is not a budget problem -- stop, do not double forever.
    (10 ** 9, [100, 200, 400, 800]),
])
def test_a_truncated_reply_gets_more_room_until_it_fits_or_stops(fits_at, expected):
    tried: list[int] = []
    client = _client(fits_at, tried)
    if fits_at > max(expected):
        with pytest.raises(LLMResponseError):
            llm_call(client, "prompt", max_tokens=100)
    else:
        assert llm_call(client, "prompt", max_tokens=100) == "complete answer"
    assert tried == expected


def test_an_empty_reply_is_not_retried_with_more_room():
    """Only truncation is a budget problem. An empty 200-OK reply will still be
    empty at 8x the size, so retrying just burns four calls."""
    tried: list[int] = []

    def stream(**kwargs):
        tried.append(kwargs["max_tokens"])
        return _reply(None, "end_turn")

    with pytest.raises(LLMResponseError):
        llm_call(SimpleNamespace(messages=SimpleNamespace(stream=stream)),
                 "prompt", max_tokens=100)
    assert tried == [100], "empty is not a budget failure"
