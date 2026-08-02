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

NAMES = [f"drug{i}" for i in range(8)]


def _truncates_above(limit: int, seen: list):
    """Stand-in for llm_call: batches larger than `limit` names truncate. A batch
    that fits merges its first name, so each half leaves a distinguishable mark."""
    def fake(client, msg, model=None, max_tokens=None):
        names = json.loads(msg.split("canonicalize:\n")[1])
        seen.append(len(names))
        if len(names) > limit:
            raise LLMResponseError("response truncated at max_tokens")
        return json.dumps({names[0]: f"canon_{names[0]}"})
    return fake


def test_a_truncated_batch_splits_and_keeps_both_halves(monkeypatch):
    seen = []
    monkeypatch.setattr(canon, "llm_call", _truncates_above(4, seen))
    out = canon.canonicalize_batch(object(), NAMES)

    assert seen[0] == 8 and 4 in seen, "whole batch first, then halved"
    assert set(out) == set(NAMES), "every name still gets a mapping"
    assert len({k: v for k, v in out.items() if k != v}) == 2, \
        "one merge recovered from each half -- a split must not lose either side"


def test_an_untruncated_batch_makes_exactly_one_call(monkeypatch):
    seen = []
    monkeypatch.setattr(canon, "llm_call", _truncates_above(99, seen))
    canon.canonicalize_batch(object(), NAMES)
    assert seen == [8]


def test_the_split_is_depth_bounded(monkeypatch):
    """A reply that truncates however small is not a size problem, so surface it
    rather than recursing forever."""
    monkeypatch.setattr(canon, "llm_call", _truncates_above(0, []))
    with pytest.raises(LLMResponseError):
        canon.canonicalize_batch(object(), NAMES)
