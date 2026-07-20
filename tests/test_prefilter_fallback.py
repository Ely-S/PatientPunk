"""The single-item prefilter fallback must never turn a NON-ANSWER into a confident drop.

Three distinct ways this gate silently discarded content, all found while validating judgement 4:

  1. PREFILTER_PROMPT asks for a JSON array, so a compliant model replies ["yes"] — which does not
     start with "yes". _is_yes on the raw reply returned False for every item ever passed to it.
  2. A small max_tokens budget: a reasoning MODEL_FAST spends it internally and returns "".
     Measured: gpt-5-mini and gemini-3.5-flash return "" at 16 tokens and ["yes"] at 400.
  3. An unreadable reply was treated as "no" rather than "don't know".

Since _prefilter_one is the fallback for a failed batch, each of these dropped every pair in that
batch at the gate that admits everything downstream. When the answer can't be read we now FAIL
OPEN: passing a pair on costs one strong-model call, dropping it loses the report for good.
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
