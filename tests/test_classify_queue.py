"""The classify work queue pairs each entry with its drugs in a fixed order, so the
prefilter and classify batches are the same in every process (set iteration order
varies with PYTHONHASHSEED)."""

from __future__ import annotations

from pipeline.classify import _entry_drugs


def test_entry_drugs_are_sorted_and_deduplicated():
    entry = {"drugs_direct": ["b"], "drugs_context": ["a", "b"]}
    assert _entry_drugs(entry) == ["a", "b"]


def test_entry_drugs_handles_missing_keys():
    assert _entry_drugs({"drugs_direct": ["b", "a"]}) == ["a", "b"]
    assert _entry_drugs({}) == []
