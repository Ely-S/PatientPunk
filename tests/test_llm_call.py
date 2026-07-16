"""llm_call is the one src/ call site that talks to cached_completion; unlike
every variable_extraction call site, it built its response from response_text()
without check_response() first. A thinking-only/empty 200-OK reply would
therefore return "" instead of raising -- and cached_completion caches any
string a call_fn returns, so that "" would be replayed forever.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from patientpunk._utils import LLMResponseError  # noqa: E402 -- loads .env with override=True first

# utilities/__init__.py validates LLM_PROVIDER at import time; pin it so this
# module can be collected regardless of the .env's provider setting (patientpunk's
# own dotenv load above runs with override=True, so this must come after it).
os.environ["LLM_PROVIDER"] = "anthropic"

from utilities import llm_call


class _FakeStream:
    def __init__(self, message):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._message


def _client(message):
    stream = lambda **_: _FakeStream(message)
    return SimpleNamespace(messages=SimpleNamespace(stream=stream))


def _msg(*blocks, stop_reason="end_turn"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


@pytest.fixture(autouse=True)
def _cache_root(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    from patientpunk import llm_cache
    llm_cache.set_cache_enabled(None)
    yield
    llm_cache.set_cache_enabled(None)


def test_thinking_only_reply_raises_instead_of_returning_empty():
    thinking = SimpleNamespace(type="thinking", thinking="...", text=None)
    client = _client(_msg(thinking))
    with pytest.raises(LLMResponseError, match="empty"):
        llm_call(client, "prompt")


def test_empty_reply_is_not_cached(tmp_path):
    from patientpunk import llm_cache

    thinking = SimpleNamespace(type="thinking", thinking="...", text=None)
    client = _client(_msg(thinking))
    with pytest.raises(LLMResponseError):
        llm_call(client, "same prompt")

    good_text = SimpleNamespace(type="text", text="hello")
    client2 = _client(_msg(good_text))
    assert llm_call(client2, "same prompt") == "hello"


def test_good_reply_passes_through():
    text = SimpleNamespace(type="text", text="hello")
    client = _client(_msg(text))
    assert llm_call(client, "prompt") == "hello"
