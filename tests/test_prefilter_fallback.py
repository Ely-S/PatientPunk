"""The single-item prefilter fallback must understand the format the prompt asks for.

PREFILTER_PROMPT ends with "Return a JSON array of strings, each 'yes' or 'no'", so a compliant
model replies ["yes"]. _prefilter_one applied _is_yes to the RAW reply, and '["yes"]' does not
start with "yes" — so it returned False for every item. Since _prefilter_one is the fallback for a
failed batch, one unparseable batch silently dropped every pair in it, on the gate that admits
everything downstream.
"""
import pipeline.classify as classify


def _stub(monkeypatch, raw):
    monkeypatch.setattr(classify, "llm_call", lambda *a, **k: raw)


def test_json_array_yes_is_a_keep(monkeypatch):
    """The regression: the compliant reply format used to evaluate as False."""
    _stub(monkeypatch, '["yes"]')
    assert classify._prefilter_one(None, {"text": "I take LDN daily"}, "ldn", {}) is True


def test_json_array_no_is_a_drop(monkeypatch):
    _stub(monkeypatch, '["no"]')
    assert classify._prefilter_one(None, {"text": "has anyone tried LDN?"}, "ldn", {}) is False


def test_bare_yes_still_accepted(monkeypatch):
    """A model that ignores the JSON instruction must still be understood."""
    _stub(monkeypatch, "yes")
    assert classify._prefilter_one(None, {"text": "I take LDN daily"}, "ldn", {}) is True


def test_unparseable_reply_is_a_drop(monkeypatch):
    _stub(monkeypatch, "I'm not sure about that")
    assert classify._prefilter_one(None, {"text": "whatever"}, "ldn", {}) is False
