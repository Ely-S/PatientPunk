"""Transient failures must retry; deterministic ones must not. No API calls.

src/ had no application-level retry at all -- it relied on the SDK's max_retries,
which covers the initial request but not a failure part-way through a stream. An
httpx.RemoteProtocolError ("peer closed connection without sending complete
message body") killed a 19,275-item extraction run at 99.9% completion.
"""

import sys
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from patientpunk._utils import LLMResponseError  # noqa: E402
from utilities import is_transient_failure  # noqa: E402


def _with_status(status: int):
    exc = Exception("boom")
    exc.status_code = status
    return exc


def test_the_mid_stream_drop_that_killed_the_run():
    """RemoteProtocolError is the specific failure this exists for. It is a
    TransportError but its class name contains neither 'Connection' nor
    'Timeout', so substring matching -- what variable_extraction does -- misses
    it. Asserted here so a refactor back to name matching fails loudly."""
    exc = httpx.RemoteProtocolError("peer closed connection")
    assert is_transient_failure(exc)
    assert "Connection" not in type(exc).__name__
    assert "Timeout" not in type(exc).__name__


@pytest.mark.parametrize("exc, retries", [
    (httpx.ConnectError("refused"), True),
    (httpx.ReadTimeout("slow"), True),
    (_with_status(429), True),
    (_with_status(503), True),
    # 402 is the one that must fail fast -- four backoffs against a dead account
    # add ~52s per call across a whole corpus to an error that will not clear.
    (_with_status(402), False),
    (_with_status(401), False),
    # The reply did not fit the budget and will not fit on a retry; the caller
    # has to shrink the batch instead.
    (LLMResponseError("truncated at max_tokens"), False),
    (TypeError("bad argument"), False),
])
def test_only_failures_that_can_clear_on_their_own_retry(exc, retries):
    assert is_transient_failure(exc) is retries
