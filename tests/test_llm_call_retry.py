"""Retry transient LLM stream failures and fail fast on deterministic errors."""

import os
import time
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import anthropic
import httpx
import pytest

from patientpunk import llm_cache
from patientpunk._utils import LLMResponseError

os.environ["LLM_PROVIDER"] = "anthropic"

from utilities import is_transient_failure, llm_call  # noqa: E402


def _status(status: int) -> Exception:
    exc = Exception("boom")
    exc.status_code = status
    return exc


def _in_band(status: int) -> anthropic.APIStatusError:
    # __new__ skips APIStatusError.__init__, which demands real httpx
    # request/response objects; only the message and status_code matter here.
    exc = anthropic.APIStatusError.__new__(anthropic.APIStatusError)
    Exception.__init__(exc, "provider_unavailable")
    exc.status_code = status
    return exc


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (httpx.RemoteProtocolError("peer closed connection"), True),
        (_status(429), True),
        (_status(503), True),
        (_in_band(200), True),
        (_status(402), False),
        (LLMResponseError("truncated at max_tokens"), False),
        (_in_band(400), False),
    ],
    ids=["transport", "rate-limit", "server", "in-band", "billing", "truncated", "client"],
)
def test_transient_failure_classification(exc, expected):
    assert is_transient_failure(exc) is expected


@pytest.fixture(autouse=True)
def _disable_cache():
    llm_cache.set_cache_enabled(False)
    yield
    llm_cache.set_cache_enabled(None)


@pytest.mark.parametrize(
    ("failure", "drops", "raises", "attempts"),
    [
        (httpx.RemoteProtocolError("peer closed connection"), 2, False, 3),
        (httpx.RemoteProtocolError("peer closed connection"), 5, True, 5),
        (_status(402), 1, True, 1),
    ],
    ids=["recovers", "bounded", "fails-fast"],
)
def test_midstream_failure_retries_the_whole_request(
    monkeypatch, failure, drops, raises, attempts,
):
    message = SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text="ok")],
    )
    read = Mock(side_effect=[failure] * drops + [message])
    stream = Mock(side_effect=lambda **_: nullcontext(
        SimpleNamespace(get_final_message=read),
    ))
    client = SimpleNamespace(messages=SimpleNamespace(stream=stream))
    sleep = Mock()
    monkeypatch.setattr(time, "sleep", sleep)

    if raises:
        with pytest.raises(type(failure)):
            llm_call(client, "prompt", max_tokens=10)
    else:
        assert llm_call(client, "prompt", max_tokens=10) == "ok"

    assert stream.call_count == attempts
    assert sleep.call_count == attempts - 1
