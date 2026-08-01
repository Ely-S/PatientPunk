"""A batch the model cannot answer must not end the run. No API calls."""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from patientpunk._utils import LLMResponseError  # noqa: E402
from pipeline import extract  # noqa: E402


def _fails_above(limit: int, calls: list):
    """Stand-in for llm_call: any batch larger than `limit` texts truncates."""
    def fake(client, msg, model=None, max_tokens=None):
        n = msg.count("--- ")
        calls.append(n)
        if n > limit:
            raise LLMResponseError("response truncated at max_tokens")
        return json.dumps([["ldn"] for _ in range(n)])
    return fake


def test_a_truncated_batch_splits_instead_of_raising(monkeypatch):
    calls = []
    monkeypatch.setattr(extract, "llm_call", _fails_above(4, calls))
    got = extract.extract_batch(None, [f"t{i}" for i in range(8)])
    assert got == [["ldn"]] * 8
    assert calls == [8, 4, 4], "one failed call, then both halves"


def test_it_gives_up_on_one_text_rather_than_ending_the_run(monkeypatch):
    """Bottoming out returns empties -- the run continues with a gap in it."""
    calls = []
    monkeypatch.setattr(extract, "llm_call", _fails_above(0, calls))
    got = extract.extract_batch(None, [f"t{i}" for i in range(4)])
    assert got == [[], [], [], []]
