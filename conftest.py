"""Repo-wide pytest configuration.

The LLM cache from llm_cache.py replays earlier test runs' responses, so pytest passes once and then fails forever after. 
Tests now get a fresh cache dir each run; production caching is unchanged.
"""
import pytest


@pytest.fixture(autouse=True)
def isolate_llm_cache(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path_factory.mktemp("llm_cache")))
