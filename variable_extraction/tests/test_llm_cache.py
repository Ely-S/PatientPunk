"""Tests for patientpunk.llm_cache (content-addressable LLM response cache)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from patientpunk import llm_cache as cache


@pytest.fixture(autouse=True)
def _reset_cache_override():
    cache.set_cache_enabled(None)
    yield
    cache.set_cache_enabled(None)


def test_cache_root_is_cwd_independent(tmp_path, monkeypatch):
    """The root must not move with the cwd.

    main.py is run from variable_extraction/ but the pipeline is also driven
    from the repo root; when the root was cwd-relative each got its own cache
    and the second silently re-paid for every response the first had bought.
    """
    monkeypatch.delenv("LLM_CACHE_DIR", raising=False)

    monkeypatch.chdir(tmp_path)
    from_tmp = cache.cache_root()

    monkeypatch.chdir(Path(__file__).parent)
    from_tests = cache.cache_root()

    # .resolve() is what makes this a real regression test: the old root was the
    # relative Path("cache"), which compares equal to itself from any cwd but
    # resolves to a different directory under each one.
    assert from_tmp.resolve() == from_tests.resolve()
    assert from_tmp.is_absolute()
    # Anchored on the repo, not on wherever the process started.
    assert from_tmp == cache._repo_root() / "cache"
    assert tmp_path not in from_tmp.parents


def test_repo_root_finds_marker():
    root = cache._repo_root()
    assert root.is_absolute()
    assert any((root / m).exists() for m in cache._ROOT_MARKERS)
    # patientpunk/ lives under the located root.
    assert Path(cache.__file__).resolve().is_relative_to(root)


def test_repo_root_falls_back_to_cwd_without_marker(tmp_path, monkeypatch):
    """Installed into site-packages with no marker above: keep old behaviour."""
    monkeypatch.setattr(cache, "_repo_root_cache", None)
    monkeypatch.setattr(cache, "_ROOT_MARKERS", ("__no_such_marker__",))
    monkeypatch.chdir(tmp_path)
    try:
        assert cache._repo_root() == Path.cwd()
    finally:
        cache._repo_root_cache = None


def test_cache_dir_env_override_is_resolved(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path / "sub" / ".." / "sub"))
    root = cache.cache_root()
    assert root.is_absolute()
    assert root == (tmp_path / "sub").resolve()


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

    reasoning_off = cache.make_key(
        **kwargs,
        request_variant={"reasoning_mode": "off"},
    )
    reasoning_on = cache.make_key(
        **kwargs,
        request_variant={"reasoning_mode": "on"},
    )
    assert reasoning_off != reasoning_on
    assert reasoning_off != a


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

    key = cache.make_key(**kwargs)
    log_text = (tmp_path / "log.txt").read_text(encoding="utf-8")
    assert f"M {key[:12]}" in log_text
    assert f"W {key[:12]}" in log_text
    assert f"H {key[:12]}" in log_text
    # miss+write then hit
    assert [ln[0] for ln in log_text.strip().splitlines()] == ["M", "W", "H"]


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
    assert cache.cache_enabled() is True  # opt-out: default on
    monkeypatch.setenv("LLM_CACHE", "1")
    assert cache.cache_enabled() is True
    monkeypatch.setenv("LLM_CACHE", "0")
    assert cache.cache_enabled() is False
    cache.set_cache_enabled(True)
    assert cache.cache_enabled() is True
    cache.set_cache_enabled(False)
    assert cache.cache_enabled() is False
