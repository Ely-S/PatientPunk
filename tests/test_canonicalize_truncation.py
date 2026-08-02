"""A truncated canonicalization reply must split, not end the run. No API calls.

canonicalize_batch sends every unique drug name in one call and budgets
~15 output tokens per name. When that reply truncates, check_response raises
LLMResponseError out of llm_call -- which the caller's `except LLMParseError`
never caught, so the run died on its first batch of 3,380 names.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from patientpunk._utils import LLMResponseError  # noqa: E402
import pipeline.canonicalize as canon  # noqa: E402


@pytest.fixture
def names():
    return [f"drug{i}" for i in range(8)]


def test_a_truncated_batch_splits_and_succeeds(monkeypatch, names):
    """Halving the names halves the merges the reply has to carry."""
    seen = []

    def fake_llm_call(client, msg, model=None, max_tokens=None):
        n = json.loads(msg.split("canonicalize:\n")[1])
        seen.append(len(n))
        if len(n) > 4:
            raise LLMResponseError("response truncated at max_tokens")
        return json.dumps({n[0]: "canonical"})

    monkeypatch.setattr(canon, "llm_call", fake_llm_call)
    out = canon.canonicalize_batch(object(), names)

    assert seen[0] == 8, "first attempt uses the whole batch"
    assert 4 in seen, "then halves it"
    assert set(out) == set(names), "every name still gets a mapping"


def test_the_split_is_depth_bounded(monkeypatch, names):
    """A reply that truncates no matter how small is not a size problem, so
    stop splitting and surface it rather than recursing forever."""
    def always_truncates(client, msg, model=None, max_tokens=None):
        raise LLMResponseError("response truncated at max_tokens")

    monkeypatch.setattr(canon, "llm_call", always_truncates)
    with pytest.raises(LLMResponseError):
        canon.canonicalize_batch(object(), names)


def test_merges_from_both_halves_are_kept(monkeypatch, names):
    """A split must not lose the results of either side."""
    def fake_llm_call(client, msg, model=None, max_tokens=None):
        n = json.loads(msg.split("canonicalize:\n")[1])
        if len(n) > 4:
            raise LLMResponseError("truncated")
        return json.dumps({n[0]: f"canon_{n[0]}"})

    monkeypatch.setattr(canon, "llm_call", fake_llm_call)
    out = canon.canonicalize_batch(object(), names)
    merged = {k: v for k, v in out.items() if k != v}
    assert len(merged) == 2, "one merge recovered from each half"


def test_an_untruncated_batch_does_not_split(monkeypatch, names):
    calls = []

    def fake_llm_call(client, msg, model=None, max_tokens=None):
        calls.append(1)
        return json.dumps({"drug0": "canonical"})

    monkeypatch.setattr(canon, "llm_call", fake_llm_call)
    canon.canonicalize_batch(object(), names)
    assert len(calls) == 1
