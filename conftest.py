"""Repo-wide pytest configuration.

Tests drive fake LLM clients, but llm_call() routes every request through the on-disk
response cache, which defaults to on and is rooted at the repo's `cache/`. So the first
pytest run stores the fakes' replies and every later run replays them from disk without
ever calling the fake. The pipeline still produces correct rows -- from the cache -- so
the data assertions keep passing and only an assertion about what the pipeline *asked*
the model fails. That is how populate_db_test::test_6 came to fail on the second run of
unchanged code, and it read as a code regression for a while.

Point the cache at a per-run temporary directory so every run starts cold. This keeps the
cached code path exercised rather than switching it off. It lives at the repo root so it
covers both testpaths -- the trap is in llm_call, not in any one suite, and it catches
whichever suite happens to assert on a fake's calls next.

Tests that exercise the cache itself set LLM_CACHE_DIR (or delete it) for their own case;
those assignments run after this fixture and win.
"""
import pytest


@pytest.fixture(autouse=True)
def isolate_llm_cache(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path_factory.mktemp("llm_cache")))
