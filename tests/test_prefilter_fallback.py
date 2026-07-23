"""The single-item prefilter fallback must never turn a NON-ANSWER into a confident drop.

Three ways it did, all found while validating judgement 4: a compliant ["yes"] does not start
with "yes"; a reasoning model given too few tokens returns ""; an unreadable reply was read as
"no". Since this is the fallback for a failed batch, each dropped every pair in that batch.
"""

import pytest

import pipeline.classify as classify


def _stub(monkeypatch, raw):
    monkeypatch.setattr(classify, "llm_call", lambda *a, **k: raw)


def _call():
    return classify._prefilter_one(None, {"id": "t3_x", "text": "I take LDN daily"}, "ldn", {})


@pytest.mark.parametrize("raw,expected", [
    ('["yes"]', True),    # the original regression: the compliant format evaluated as False
    ('["no"]', False),
    ("yes", True),        # a model ignoring the JSON instruction must still be understood
    ("no", False),
])
def test_readable_answers_are_honoured(monkeypatch, raw, expected):
    _stub(monkeypatch, raw)
    assert _call() is expected


@pytest.mark.parametrize("raw", ["", "I'm not sure about that"])
def test_a_non_answer_fails_open(monkeypatch, raw):
    """Empty (a reasoning model spending its budget internally) or unreadable: we cannot tell
    keep from drop, so keep. Losing a real report is the worse error."""
    _stub(monkeypatch, raw)
    assert _call() is True
