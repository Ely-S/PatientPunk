"""A batch the model cannot answer must not end the run. No API calls."""

import json

import pytest

from patientpunk._utils import LLMResponseError
from pipeline import extract


def _fits_at(limit: int):
    """Stand-in for llm_call: a batch of more than `limit` texts truncates."""
    def fake(client, msg, model=None, max_tokens=None):
        n = msg.count("--- ")
        if n > limit:
            raise LLMResponseError("response truncated at max_tokens")
        return json.dumps([["ldn"] for _ in range(n)])
    return fake


@pytest.mark.parametrize("limit, expected", [
    # 8 results out of a model that refuses batches above 4 can only mean it split.
    (4, [["ldn"]] * 8),
    # Nothing ever fits: the run continues with gaps rather than raising.
    (0, [[]] * 8),
], ids=["splits-until-they-fit", "gives-up-without-raising"])
def test_a_truncated_batch_does_not_end_the_run(monkeypatch, limit, expected):
    monkeypatch.setattr(extract, "llm_call", _fits_at(limit))
    assert extract.extract_batch(None, [f"t{i}" for i in range(8)]) == expected
