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

from utilities import BUDGET_GROWTH, llm_call  # noqa: E402


class _FakeStream:
    def __init__(self, message):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._message


def _text(s):
    return SimpleNamespace(type="text", text=s)


def _client(fits_at: int, budgets: list[int]):
    """A model whose reply needs `fits_at` tokens; records every budget tried."""
    def stream(**kwargs):
        budget = kwargs["max_tokens"]
        budgets.append(budget)
        if budget < fits_at:
            return _FakeStream(SimpleNamespace(content=[_text("partial")],
                                               stop_reason="max_tokens"))
        return _FakeStream(SimpleNamespace(content=[_text("complete answer")],
                                           stop_reason="end_turn"))
    return SimpleNamespace(messages=SimpleNamespace(stream=stream))


@pytest.fixture(autouse=True)
def _cache_root(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    from patientpunk import llm_cache
    llm_cache.set_cache_enabled(None)
    yield
    llm_cache.set_cache_enabled(None)


def test_a_truncated_reply_gets_more_room_and_succeeds():
    """classify.py:75 budgets 10 tokens/item; on 20 items that is 200, and the
    reply needed more. Before this it raised and ended the run."""
    budgets: list[int] = []
    out = llm_call(_client(fits_at=350, budgets=budgets), "prompt", max_tokens=200)
    assert out == "complete answer"
    assert budgets == [200, 400], "doubles once, then fits"


def test_it_keeps_growing_until_the_reply_fits():
    budgets: list[int] = []
    llm_call(_client(fits_at=700, budgets=budgets), "prompt", max_tokens=100)
    assert budgets == [100, 200, 400, 800]


def test_a_reply_that_fits_first_time_makes_one_call():
    """Growth must not cost an extra call on the normal path."""
    budgets: list[int] = []
    llm_call(_client(fits_at=50, budgets=budgets), "prompt", max_tokens=100)
    assert budgets == [100]


def test_growth_is_bounded_and_then_it_raises():
    """A reply that never fits is not a budget problem. Surface it rather than
    doubling forever."""
    budgets: list[int] = []
    with pytest.raises(LLMResponseError):
        llm_call(_client(fits_at=10**9, budgets=budgets), "prompt", max_tokens=100)
    assert budgets == [100 * f for f in BUDGET_GROWTH]


def test_an_empty_reply_is_not_retried_with_more_room():
    """Only truncation is a budget problem. An empty 200-OK reply will still be
    empty at 8x the size, so retrying just burns four calls."""
    calls: list[int] = []

    def stream(**kwargs):
        calls.append(kwargs["max_tokens"])
        return _FakeStream(SimpleNamespace(content=[], stop_reason="end_turn"))

    client = SimpleNamespace(messages=SimpleNamespace(stream=stream))
    with pytest.raises(LLMResponseError):
        llm_call(client, "prompt", max_tokens=100)
    assert calls == [100], "empty is not a budget failure"
