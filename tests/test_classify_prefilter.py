"""The prefilter's single-item fallback parses its reply the way the batch path does,
and passes the pair through to the strong classifier on anything it cannot read.
No model calls: ``llm_call`` is stubbed."""

from __future__ import annotations

import pytest

from patientpunk._utils import LLMResponseError
from pipeline import classify

ENTRY = {"id": "p1", "text": "Took it for a month, it helped."}


def _reply_with(reply):
    def llm_call(client, prompt, **kwargs):
        if isinstance(reply, Exception):
            raise reply
        return reply
    return llm_call


@pytest.mark.parametrize(
    "reply, expected",
    [
        ('["yes"]', True),
        ('["no"]', False),
        ("yes", True),
        ("no", False),
        ("Yes", True),
        ('["No"]', False),
        ("garbage", True),                    # unparseable: pass through
        ('["maybe"]', True),                  # not yes/no: pass through
        ('["yes", "no"]', True),              # wrong count: pass through
        (LLMResponseError("empty"), True),    # provider error: pass through
    ],
)
def test_prefilter_one_reads_the_array_and_passes_through_otherwise(monkeypatch, reply, expected):
    monkeypatch.setattr(classify, "llm_call", _reply_with(reply))
    assert classify._prefilter_one(None, ENTRY, "ldn", {}) is expected


def test_prefilter_batch_falls_back_per_item_on_a_provider_error(monkeypatch):
    items = [({"id": "a", "text": "worked for me"}, "ldn"), ({"id": "b", "text": "what dose?"}, "ldn")]
    single = {"worked for me": '["yes"]', "what dose?": '["no"]'}

    def llm_call(client, prompt, **kwargs):
        if "Expecting 2 answers" in prompt:
            raise LLMResponseError("response was empty")
        return next(reply for text, reply in single.items() if text in prompt)

    monkeypatch.setattr(classify, "llm_call", llm_call)
    assert classify.prefilter_batch(None, items, {}) == [True, False]
