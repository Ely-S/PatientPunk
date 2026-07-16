"""Tests for patientpunk.llm_cache (content-addressable LLM response cache)."""

from __future__ import annotations

import json

import pytest

from patientpunk import llm_cache as cache


@pytest.fixture(autouse=True)
def _reset_cache_override():
    cache.set_cache_enabled(None)
    yield
    cache.set_cache_enabled(None)


def test_make_key_stable_and_sensitive():
    kwargs = dict(
        provider="openrouter",
        model="anthropic/claude-haiku-4.5",
        system="sys",
        prompt="hello",
        temperature=0.0,
        max_tokens=100,
    )
    a = cache.make_key(**kwargs)
    b = cache.make_key(**kwargs)
    assert a == b
    assert len(a) == 64

    different_temp = cache.make_key(**{**kwargs, "temperature": 0.7})
    assert different_temp != a

    different_model = cache.make_key(**{**kwargs, "model": "other-model"})
    assert different_model != a


def test_cache_path_layout_and_sanitization(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    key = "abcdef0123456789" + "0" * 48
    path = cache.cache_path("openrouter", "anthropic/claude-haiku-4.5", key)
    assert path == tmp_path / "openrouter" / "anthropic--claude-haiku-4.5" / "abc" / f"{key}.json"
    assert path.parts[-2] == key[:3]


def test_put_get_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_CACHE", "1")
    key = cache.make_key(
        provider="anthropic",
        model="claude-haiku",
        system=None,
        prompt="ping",
        temperature=0.0,
        max_tokens=50,
    )
    path = cache.cache_path("anthropic", "claude-haiku", key)
    assert cache.get(path) is None

    cache.put(
        path,
        key=key,
        provider="anthropic",
        model="claude-haiku",
        temperature=0.0,
        max_tokens=50,
        response_text='["metformin"]',
    )
    assert cache.get(path) == '["metformin"]'
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["key"] == key
    assert "prompt" not in data
    assert "response_text" in data


def test_cached_completion_hit_skips_call(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    cache.set_cache_enabled(True)

    calls = {"n": 0}

    def call_fn():
        calls["n"] += 1
        return "RESPONSE"

    kwargs = dict(
        provider="openrouter",
        model="m",
        system="s",
        prompt="p",
        temperature=0.0,
        max_tokens=10,
    )
    assert cache.cached_completion(**kwargs, call_fn=call_fn) == "RESPONSE"
    assert cache.cached_completion(**kwargs, call_fn=call_fn) == "RESPONSE"
    assert calls["n"] == 1


def test_cached_completion_disabled_always_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    cache.set_cache_enabled(False)
    calls = {"n": 0}

    def call_fn():
        calls["n"] += 1
        return "X"

    kwargs = dict(
        provider="p", model="m", system="", prompt="q",
        temperature=0.0, max_tokens=1,
    )
    cache.cached_completion(**kwargs, call_fn=call_fn)
    cache.cached_completion(**kwargs, call_fn=call_fn)
    assert calls["n"] == 2


def test_exceptions_not_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    cache.set_cache_enabled(True)

    def boom():
        raise RuntimeError("api down")

    kwargs = dict(
        provider="p", model="m", system="", prompt="q",
        temperature=0.0, max_tokens=1,
    )
    with pytest.raises(RuntimeError, match="api down"):
        cache.cached_completion(**kwargs, call_fn=boom)

    # No file written
    key = cache.make_key(**kwargs)
    assert not cache.cache_path("p", "m", key).exists()


def test_normalize_system_blocks():
    assert cache.normalize_system(None) == ""
    assert cache.normalize_system("hi") == "hi"
    assert cache.normalize_system([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]) == "a\nb"


def test_cache_enabled_env(monkeypatch):
    cache.set_cache_enabled(None)
    monkeypatch.delenv("LLM_CACHE", raising=False)
    assert cache.cache_enabled() is False
    monkeypatch.setenv("LLM_CACHE", "1")
    assert cache.cache_enabled() is True
    monkeypatch.setenv("LLM_CACHE", "0")
    assert cache.cache_enabled() is False
    cache.set_cache_enabled(True)
    assert cache.cache_enabled() is True
