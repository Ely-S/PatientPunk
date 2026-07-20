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

import pipeline.classify as classify


def _stub(monkeypatch, raw):
    monkeypatch.setattr(classify, "llm_call", lambda *a, **k: raw)


def _call():
    return classify._prefilter_one(None, {"id": "t3_x", "text": "I take LDN daily"}, "ldn", {})


def test_json_array_yes_is_a_keep(monkeypatch):
    """The original regression: the compliant reply format evaluated as False."""
    _stub(monkeypatch, '["yes"]')
    assert _call() is True


def test_json_array_no_is_a_drop(monkeypatch):
    _stub(monkeypatch, '["no"]')
    assert _call() is False


def test_bare_yes_still_accepted(monkeypatch):
    """A model that ignores the JSON instruction must still be understood."""
    _stub(monkeypatch, "yes")
    assert _call() is True


def test_bare_no_still_accepted(monkeypatch):
    _stub(monkeypatch, "no")
    assert _call() is False


def test_empty_reply_fails_open(monkeypatch):
    """A reasoning model that emits no text must not read as a rejection."""
    _stub(monkeypatch, "")
    assert _call() is True


def test_unreadable_reply_fails_open(monkeypatch):
    """We cannot tell keep from drop, so keep — losing a real report is the worse error."""
    _stub(monkeypatch, "I'm not sure about that")
    assert _call() is True
