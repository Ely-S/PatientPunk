"""Retry transient LLM stream failures and fail fast on deterministic errors."""

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx
import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from patientpunk._utils import LLMResponseError  # noqa: E402

os.environ["LLM_PROVIDER"] = "anthropic"

from utilities import is_transient_failure, llm_call  # noqa: E402


def _with_status(status: int):
    exc = Exception("boom")
    exc.status_code = status
    return exc


def test_the_remoteprotocolerror():
    """The original failure lacks the class-name substrings used by old logic."""
    exc = httpx.RemoteProtocolError("peer closed connection")
    assert is_transient_failure(exc)
    assert "Connection" not in type(exc).__name__
    assert "Timeout" not in type(exc).__name__


def _in_band(status: int, body: str):
    """Build the APIStatusError raised for an error inside a live stream."""
    exc = anthropic.APIStatusError.__new__(anthropic.APIStatusError)
    Exception.__init__(exc, body)
    exc.status_code = status
    return exc


def test_an_error_injected_into_an_already_200_stream_is_retried():
    """A gateway may report an unavailable provider after returning HTTP 200."""
    exc = _in_band(200, "{'type': 'error', 'error': "
                        "{'message': 'JSON error injected into SSE stream', "
                        "'error_type': 'provider_unavailable'}}")
    assert is_transient_failure(exc)


def test_a_4xx_is_not_rescued_by_what_its_body_happens_to_say():
    """An in-band error marker must not make a client error retryable."""
    assert not is_transient_failure(_in_band(400, "provider_unavailable"))


@pytest.mark.parametrize("exc, retries", [
    (httpx.ConnectError("refused"), True),
    (_with_status(429), True),
    (_with_status(503), True),
    (_with_status(402), False),  # an exhausted balance cannot clear on retry
    (LLMResponseError("truncated at max_tokens"), False),  # shrink the batch instead
])
def test_only_failures_that_can_clear_on_their_own_retry(exc, retries):
    assert is_transient_failure(exc) is retries


class _Stream:
    """Simulate a failure while draining an established stream."""

    def __init__(self, drops: bool):
        self._drops = drops

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        if self._drops:
            raise httpx.RemoteProtocolError("peer closed connection")
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text="ok")])


@pytest.mark.parametrize("drops, reads", [
    (2, 3),  # third attempt succeeds
    (9, 5),  # retries remain bounded
], ids=["recovers", "gives-up-after-five"])
def test_a_drop_while_reading_the_reply_is_retried(monkeypatch, tmp_path, drops, reads):
    """Retry the whole request when draining its stream fails."""
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(time, "sleep", lambda _: None)  # skip backoff in tests
    from patientpunk import llm_cache
    llm_cache.set_cache_enabled(None)

    calls = []

    def stream(**_):
        calls.append(1)
        return _Stream(drops=len(calls) <= drops)

    client = SimpleNamespace(messages=SimpleNamespace(stream=stream))
    if drops >= reads:
        with pytest.raises(httpx.RemoteProtocolError):
            llm_call(client, "prompt", max_tokens=10)
    else:
        assert llm_call(client, "prompt", max_tokens=10) == "ok"
    assert len(calls) == reads

    llm_cache.set_cache_enabled(None)
