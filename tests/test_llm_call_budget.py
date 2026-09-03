"""Grow the output budget only when an LLM reply is truncated."""

import os
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from patientpunk import llm_cache
from patientpunk._utils import LLMResponseError, LLMTruncationError

os.environ["LLM_PROVIDER"] = "anthropic"

from utilities import llm_call  # noqa: E402


def _client(fits_at: int, budgets: list[int]):
    def stream(**kwargs):
        budget = kwargs["max_tokens"]
        budgets.append(budget)
        truncated = budget < fits_at
        response = SimpleNamespace(
            content=[SimpleNamespace(
                type="text",
                text="partial" if truncated else "complete answer",
            )],
            stop_reason="max_tokens" if truncated else "end_turn",
        )
        return nullcontext(SimpleNamespace(get_final_message=lambda: response))

    return SimpleNamespace(messages=SimpleNamespace(stream=stream))


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    llm_cache.set_cache_enabled(True)
    yield
    llm_cache.set_cache_enabled(None)


@pytest.mark.parametrize(
    ("fits_at", "expected_budgets"),
    [
        (50, [100]),
        (350, [100, 200, 400]),
    ],
    ids=["first-attempt", "grows"],
)
def test_truncation_grows_the_budget_until_the_reply_fits(
    fits_at, expected_budgets,
):
    budgets: list[int] = []
    client = _client(fits_at, budgets)

    assert llm_call(client, "prompt", max_tokens=100) == "complete answer"

    assert budgets == expected_budgets


def test_budget_growth_is_bounded():
    budgets: list[int] = []
    client = _client(10**9, budgets)

    with pytest.raises(LLMTruncationError):
        llm_call(client, "prompt", max_tokens=100)

    assert budgets == [100, 200, 400, 800]


def test_only_the_fitting_budget_is_cached():
    """The budget is part of the cache key: the winning reply must land under
    the grown budget's key, and the truncated attempts must leave nothing."""
    from utilities import LLM_PROVIDER, LLM_REASONING_MODE, MODEL_FAST

    budgets: list[int] = []
    client = _client(350, budgets)
    assert llm_call(client, "prompt", max_tokens=100) == "complete answer"

    def path_for(budget):
        key = llm_cache.make_key(
            provider=LLM_PROVIDER,
            model=MODEL_FAST,
            system=None,
            prompt="prompt",
            temperature=0.0,
            max_tokens=budget,
            request_variant={"reasoning_mode": LLM_REASONING_MODE},
        )
        return llm_cache.cache_path(LLM_PROVIDER, MODEL_FAST, key)

    assert path_for(400).exists()
    assert not path_for(100).exists()
    assert not path_for(200).exists()


def test_empty_reply_is_not_retried():
    response = SimpleNamespace(content=[], stop_reason="end_turn")
    stream = Mock(return_value=nullcontext(
        SimpleNamespace(get_final_message=lambda: response),
    ))
    client = SimpleNamespace(messages=SimpleNamespace(stream=stream))

    with pytest.raises(LLMResponseError, match="empty"):
        llm_call(client, "prompt", max_tokens=100)

    stream.assert_called_once()
