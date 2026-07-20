"""Pytest configuration for the top-level test suite.

These tests drive fake LLM clients, but llm_call() routes every request through the
on-disk response cache, which defaults to on and is rooted at the repo's `cache/`.
So the first run stores the fakes' replies and every later run replays them from
disk without ever calling the fake -- the pipeline still produces correct rows, but
any assertion about what it *asked* the model sees zero prompts and fails. That made
populate_db_test look like a code regression when it was only cache warmth.

Point the cache at a per-run temporary directory so each run starts cold. This keeps
the cached code path exercised (rather than switching it off) and mirrors what
test_llm_call.py already does for itself.
"""
import pytest


@pytest.fixture(autouse=True)
def isolate_llm_cache(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path_factory.mktemp("llm_cache")))
    from patientpunk import llm_cache

    llm_cache.set_cache_enabled(None)  # clear any override left by another test
