"""Transient failures must retry; deterministic ones must not. 

src/ had no application-level retry at all -- it relied on the SDK's max_retries,
which covers the initial request but not a failure part-way through a stream.
"""

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

from patientpunk._utils import LLMResponseError  # noqa: E402 -- loads .env first

os.environ["LLM_PROVIDER"] = "anthropic"

from utilities import is_transient_failure, llm_call  # noqa: E402


def _with_status(status: int):
    exc = Exception("boom")
    exc.status_code = status
    return exc


def test_the_remoteprotocolerror():
    """RemoteProtocolError is the specific failure this exists for. It is a
    TransportError but its class name contains neither 'Connection' nor
    'Timeout', so substring matching misses it. This is to test something
    that actually killed a run"""
    exc = httpx.RemoteProtocolError("peer closed connection")
    assert is_transient_failure(exc)
    assert "Connection" not in type(exc).__name__
    assert "Timeout" not in type(exc).__name__


def _in_band(status: int, body: str):
    """An APIStatusError as the SDK raises it for an error inside a live stream:
    built against the stream's own response, so it carries that response's status
    rather than one describing the failure."""
    exc = anthropic.APIStatusError.__new__(anthropic.APIStatusError)
    Exception.__init__(exc, body)
    exc.status_code = status
    return exc


def test_an_error_injected_into_an_already_200_stream_is_retried():
    """OpenRouter signals a dead upstream in the SSE body, after the 200 is sent.
    It reaches us as a bare APIStatusError carrying 200, so neither the exception
    type nor the status says 'transient'. This aborted a classify run part-way
    through a corpus."""
    exc = _in_band(200, "{'type': 'error', 'error': "
                        "{'message': 'JSON error injected into SSE stream', "
                        "'error_type': 'provider_unavailable'}}")
    assert is_transient_failure(exc)


def test_a_4xx_is_not_rescued_by_what_its_body_happens_to_say():
    """The body match must not reach client errors: a 400 is wrong about the
    request, and retrying sends the same bad request four more times."""
    assert not is_transient_failure(_in_band(400, "provider_unavailable"))


@pytest.mark.parametrize("exc, retries", [
    (httpx.ConnectError("refused"), True),
    (_with_status(429), True),
    (_with_status(503), True),
    # 402 is the one that must fail fast -- five attempts against a dead account
    # add ~52s per call across a whole corpus to an error that will not clear.
    (_with_status(402), False),
    # The reply did not fit the budget and will not fit on a retry; the caller
    # has to shrink the batch instead.
    (LLMResponseError("truncated at max_tokens"), False),
])
def test_only_failures_that_can_clear_on_their_own_retry(exc, retries):
    assert is_transient_failure(exc) is retries


class _Stream:
    """Raises from get_final_message, never from stream(). That is the case the
    SDK's max_retries cannot see: it has returned 200 and handed the stream back
    before the body is read."""

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
    (2, 3),   # recovers on the third read
    (9, 5),   # never recovers: bounded at len(RETRY_DELAYS) + 1, then raises
], ids=["recovers", "gives-up-after-five"])
def test_a_drop_while_reading_the_reply_is_retried(monkeypatch, tmp_path, drops, reads):
    """Proves the retried unit spans the request AND the read: the failure is
    raised during the drain, and the whole call is redone rather than resumed."""
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(time, "sleep", lambda _: None)   # skip ~52s of backoff
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
