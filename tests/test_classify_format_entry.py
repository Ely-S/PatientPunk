"""The classifier's entry text shows the parent's text under a "Replying to:" header only when
there is parent text to show (issue #150: --max-upstream-chars 0 left an empty header)."""

from __future__ import annotations

import pytest

from pipeline.classify import _prefilter_block, format_entry

REPLY = {"id": "c1", "parent_id": "p1", "text": "Worked for me."}
TOP = {"id": "p1", "text": "Anyone tried it?"}
PARENTS = {"p1": "Anyone tried it? Curious about dosing."}


def test_parent_text_is_shown_and_truncated():
    assert format_entry(REPLY, PARENTS) == "Text:\nWorked for me.\n\nReplying to:\nAnyone tried it? Curious about dosing."
    assert format_entry(REPLY, PARENTS, 16) == "Text:\nWorked for me.\n\nReplying to:\nAnyone tried it?"


@pytest.mark.parametrize("entry, id_to_text, chars", [
    (REPLY, PARENTS, 0),            # context disabled
    (REPLY, {}, None),              # parent not loaded
    (TOP, PARENTS, None),           # no parent
    ({**REPLY, "parent_id": "p1"}, {"p1": ""}, None),  # parent is empty
])
def test_no_header_without_parent_text(entry, id_to_text, chars):
    assert format_entry(entry, id_to_text, chars) == f"Text:\n{entry['text']}"
    assert "Replying to" not in _prefilter_block(0, entry, "ldn", id_to_text, chars)


def test_prefilter_block_shows_parent_text_when_present():
    block = _prefilter_block(0, REPLY, "ldn", PARENTS, 16)
    assert block == "--- 1 --- Drug: ldn\nReplying to: Anyone tried it?\n\nComment: Worked for me.\n\n"
