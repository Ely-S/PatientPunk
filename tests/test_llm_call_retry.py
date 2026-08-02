"""Transient failures must retry; deterministic ones must not. No API calls.

src/ had no application-level retry at all -- it relied on the SDK's max_retries,
which covers the initial request but not a failure part-way through a stream. An
httpx.RemoteProtocolError ("peer closed connection without sending complete
message body") killed a 19,275-item extraction run at 99.9% completion.
"""

import sys
from pathlib import Path

import anthropic
import httpx
import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from utilities import RETRY_DELAYS, is_transient_failure  # noqa: E402


def _api_error(cls, status=None):
    """Build an SDK error without going near the network."""
    e = cls.__new__(cls)
    Exception.__init__(e, "boom")
    if status is not None:
        e.status_code = status
    return e


class TestWhatCountsAsTransient:
    def test_the_mid_stream_drop_that_killed_the_run(self):
        """RemoteProtocolError is the specific failure this exists for. It is a
        TransportError but its class name contains neither 'Connection' nor
        'Timeout', so substring matching -- what variable_extraction does -- misses it."""
        exc = httpx.RemoteProtocolError("peer closed connection")
        assert is_transient_failure(exc)
        assert "Connection" not in type(exc).__name__
        assert "Timeout" not in type(exc).__name__

    @pytest.mark.parametrize("exc", [
        httpx.ConnectError("refused"),
        httpx.ReadTimeout("slow"),
        httpx.WriteError("broken pipe"),
    ], ids=["connect", "read-timeout", "write"])
    def test_other_transport_failures_retry(self, exc):
        assert is_transient_failure(exc)

    def test_rate_limit_and_server_errors_retry(self):
        assert is_transient_failure(_api_error(anthropic.RateLimitError, 429))
        assert is_transient_failure(_api_error(anthropic.InternalServerError, 503))

    def test_a_plain_502_retries(self):
        exc = Exception("bad gateway")
        exc.status_code = 502
        assert is_transient_failure(exc)


class TestWhatMustNotRetry:
    def test_truncation_is_not_transient(self):
        """The reply did not fit the budget and will not fit on a retry. The
        caller has to shrink the batch; retrying just burns the backoff."""
        from patientpunk._utils import LLMResponseError
        assert not is_transient_failure(LLMResponseError("truncated at max_tokens"))

    def test_an_exhausted_balance_is_not_transient(self):
        """402 is the one that must fail fast -- four backoffs against a dead
        account delays the error by ~52s per call across a whole corpus."""
        exc = Exception("Insufficient credits")
        exc.status_code = 402
        assert not is_transient_failure(exc)

    @pytest.mark.parametrize("status", [400, 401, 403, 404])
    def test_client_errors_are_not_transient(self, status):
        exc = Exception("nope")
        exc.status_code = status
        assert not is_transient_failure(exc)

    def test_a_programming_bug_is_not_transient(self):
        assert not is_transient_failure(TypeError("bad argument"))
        assert not is_transient_failure(KeyError("missing"))


def test_backoff_is_bounded_and_increasing():
    """Four retries at these delays is ~52s of worst-case wait per call. Long
    enough to ride out a blip, short enough not to hide a real outage."""
    assert RETRY_DELAYS == sorted(RETRY_DELAYS)
    assert len(RETRY_DELAYS) == 4
    assert sum(RETRY_DELAYS) < 60
