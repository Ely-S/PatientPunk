"""Regression tests for empty streamed responses during classification."""

from __future__ import annotations

import pytest

from patientpunk._utils import LLMResponseError
from pipeline.classify import _retry_empty_response


def test_empty_response_is_retried_within_classification() -> None:
    responses: list[object] = [LLMResponseError("response was empty"), "ok"]

    def call() -> str:
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    assert _retry_empty_response(call, "test") == "ok"
    assert responses == []


def test_nonempty_response_error_is_not_retried() -> None:
    calls = 0

    def call() -> str:
        nonlocal calls
        calls += 1
        raise LLMResponseError("policy rejection")

    with pytest.raises(LLMResponseError, match="policy"):
        _retry_empty_response(call, "test")
    assert calls == 1


def test_empty_response_retry_is_bounded() -> None:
    calls = 0

    def call() -> str:
        nonlocal calls
        calls += 1
        raise LLMResponseError("response was empty")

    with pytest.raises(LLMResponseError, match="empty"):
        _retry_empty_response(call, "test")
    assert calls == 3
