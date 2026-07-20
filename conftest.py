"""Repo-wide pytest configuration.

llm_call routes through an on-disk response cache that defaults to ON, so the first run stores
the fake client's replies and every later run replays them without calling the fake. Point it at
a per-run temp dir so each run starts cold. The trap is in llm_call, not in any one suite, hence
the repo root.
"""
import pytest


@pytest.fixture(autouse=True)
def isolate_llm_cache(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path_factory.mktemp("llm_cache")))
