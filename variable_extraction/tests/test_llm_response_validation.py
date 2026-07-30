"""Unusable 200-OK responses must raise, so retries fire and the cache stays clean.

A provider can return HTTP 200 with a body that is empty or cut off at the token
limit. Those are failures, but they arrive as ordinary return values, so nothing
retries them and -- once the response cache is on -- they get stored and replayed
forever. The fix is to raise: llm_cache only ever persists a successful return.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from patientpunk import llm_cache as cache
from patientpunk._utils import LLMResponseError, _OpenAIMessages, check_response, response_text


@pytest.fixture(autouse=True)
def _cache_root(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    cache.set_cache_enabled(None)
    yield
    cache.set_cache_enabled(None)


def _client(choices):
    create = lambda **_: SimpleNamespace(choices=choices)
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def _choice(content, finish_reason="stop"):
    return [SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)]


def _create(choices):
    return _OpenAIMessages(_client(choices)).create(
        model="m", messages=[{"role": "user", "content": "p"}]
    )


def _msg(*blocks, stop_reason="end_turn"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


def test_adapter_raises_on_empty_choices():
    with pytest.raises(LLMResponseError, match="no choices"):
        _create([])


def test_adapter_raises_on_null_content():
    with pytest.raises(LLMResponseError, match="null content"):
        _create(_choice(None))


def test_adapter_propagates_truncation_as_max_tokens():
    # OpenAI's "length" must survive as Anthropic's "max_tokens"; hardcoding
    # end_turn here is what made truncation invisible.
    assert _create(_choice("{partial", "length")).stop_reason == "max_tokens"
    assert _create(_choice("{}", "stop")).stop_reason == "end_turn"


def test_check_response_raises_on_truncated_and_empty():
    with pytest.raises(LLMResponseError, match="truncated"):
        check_response(_create(_choice("{partial", "length")), "m")
    with pytest.raises(LLMResponseError, match="empty"):
        check_response(_create(_choice("   ")), "m")


def test_check_response_passes_good_reply():
    resp = _create(_choice('{"ok": 1}'))
    assert response_text(check_response(resp, "m")) == '{"ok": 1}'


def test_response_text_skips_thinking_blocks():
    thinking = SimpleNamespace(type="thinking", thinking="internal reason...")
    text = SimpleNamespace(type="text", text='{"ok": 1}')
    assert response_text(_msg(thinking, text)) == '{"ok": 1}'
    assert response_text(_msg(text)) == '{"ok": 1}'
    assert response_text(_msg(thinking)) == ""


def test_check_response_thinking_then_text_passes():
    thinking = SimpleNamespace(type="thinking", thinking="...")
    text = SimpleNamespace(type="text", text='{"ok": 1}')
    resp = check_response(_msg(thinking, text), "m")
    assert response_text(resp) == '{"ok": 1}'


def test_check_response_thinking_only_is_empty():
    thinking = SimpleNamespace(type="thinking", thinking="no visible output")
    with pytest.raises(LLMResponseError, match="empty"):
        check_response(_msg(thinking), "m")


def test_response_error_is_retried_not_cached():
    calls = {"n": 0}

    def failing():
        calls["n"] += 1
        raise LLMResponseError("truncated")

    kwargs = dict(provider="openai", model="m", system="s", prompt="p",
                  temperature=0.0, max_tokens=1024)
    for _ in range(2):
        with pytest.raises(LLMResponseError):
            cache.cached_completion(**kwargs, call_fn=failing)

    assert calls["n"] == 2, "second run must retry, not replay a cached failure"
    assert not cache.cache_path("openai", "m", cache.make_key(**kwargs)).exists()


def test_split_retry_batch_absorbs_llm_response_error():
    """Truncated/empty replies must split-and-retry, not abort the whole batch."""
    from patientpunk._utils import split_retry_batch

    calls: list[int] = []

    def call_fn(items):
        calls.append(len(items))
        if len(items) > 1:
            raise LLMResponseError("truncated")
        return [{"ok": True} for _ in items]

    results = split_retry_batch(call_fn, [{"a": 1}, {"a": 2}])
    assert results == [{"ok": True}, {"ok": True}]
    # Full batch fails, then halves (or individuals) succeed.
    assert 2 in calls
    assert any(n == 1 for n in calls)


def test_split_retry_batch_gives_none_when_single_item_still_truncated():
    from patientpunk._utils import split_retry_batch

    def call_fn(items):
        raise LLMResponseError("truncated")

    assert split_retry_batch(call_fn, [{"a": 1}]) == [None]