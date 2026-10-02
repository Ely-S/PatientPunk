"""The classifier's small helpers: the prefilter fallback, the work-queue order, and the entry text.
No model calls: ``llm_call`` is stubbed."""
from __future__ import annotations

import pytest

from patientpunk._utils import LLMResponseError
from pipeline import classify
from pipeline.classify import _entry_drugs, _prefilter_block, format_entry

ENTRY = {"id": "p1", "text": "Took it for a month, it helped."}
REPLY = {"id": "c1", "parent_id": "p1", "text": "Worked for me."}
PARENTS = {"p1": "Anyone tried it? Curious about dosing."}


@pytest.mark.parametrize("reply, expected", [
    ('["yes"]', True), ('["no"]', False), ("yes", True), ("No", False),
    ("garbage", True),                   # unparseable: pass through to the strong classifier
    ('["maybe"]', True),                 # not yes/no: pass through
    ('["yes", "no"]', True),             # wrong count: pass through
    (LLMResponseError("empty"), True),   # provider gave up: pass through
])
def test_prefilter_fallback_reads_the_array_and_passes_through_otherwise(monkeypatch, reply, expected):
    def llm_call(client, prompt, **kwargs):
        if isinstance(reply, Exception):
            raise reply
        return reply
    monkeypatch.setattr(classify, "llm_call", llm_call)
    assert classify._prefilter_one(None, ENTRY, "ldn", {}) is expected


def test_prefilter_batch_falls_back_per_item_on_a_provider_error(monkeypatch):
    items = [({"id": "a", "text": "worked for me"}, "ldn"), ({"id": "b", "text": "what dose?"}, "ldn")]
    def llm_call(client, prompt, **kwargs):
        if "Expecting 2 answers" in prompt:
            raise LLMResponseError("response was empty")
        return '["yes"]' if "worked for me" in prompt else '["no"]'
    monkeypatch.setattr(classify, "llm_call", llm_call)
    assert classify.prefilter_batch(None, items, {}) == [True, False]


def test_entry_drugs_are_sorted_and_deduplicated():
    assert _entry_drugs({"drugs_direct": ["b"], "drugs_context": ["a", "b"]}) == ["a", "b"]
    assert _entry_drugs({}) == []


def test_parent_text_is_shown_when_there_is_any_and_the_header_omitted_otherwise():
    assert format_entry(REPLY, PARENTS, 16) == "Text:\nWorked for me.\n\nReplying to:\nAnyone tried it?"
    assert _prefilter_block(0, REPLY, "ldn", PARENTS, 16) == "--- 1 --- Drug: ldn\nReplying to: Anyone tried it?\n\nComment: Worked for me.\n\n"
    for entry, parents, chars in [(REPLY, PARENTS, 0), (REPLY, {}, None), (ENTRY, PARENTS, None), (REPLY, {"p1": ""}, None)]:
        assert format_entry(entry, parents, chars) == f"Text:\n{entry['text']}"     # context off, parent missing, top-level, parent empty
        assert "Replying to" not in _prefilter_block(0, entry, "ldn", parents, chars)
