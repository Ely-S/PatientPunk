"""extract_batch must return a list PER TEXT, even when the model flattens its reply.

The prompt asks for a list of drug-lists, but a model answering a SINGLE-text batch commonly
replies ["ldn"] rather than [["ldn"]]. The mismatch retry in extract_batch halves batches until
they are one text long, so single-text batches happen routinely, not just at the tail of a run.

Left unnormalised, the caller's flattening in run_extraction iterates the bare string "ldn"
character by character and records "l", "d", "n" as three separate drug mentions — silently
poisoning the corpus with junk drugs. Reported by the Gemini review on PR #66; pre-existing on
main, fixed here because this PR touches that code path.
"""
import pytest

import pipeline.extract as extract


def _stub(monkeypatch, raw):
    monkeypatch.setattr(extract, "llm_call", lambda *a, **k: raw)


def _flatten(drugs):
    """The exact flattening run_extraction applies to each entry."""
    return [drug.lower().strip() for drug in drugs if drug.strip()]


@pytest.mark.parametrize("raw,expected", [
    ('["ldn"]', [["ldn"]]),                        # the original regression: flat, one drug
    ('[["ldn"]]', [["ldn"]]),                      # already nested -- must be left alone
    ('["ldn", "aspirin"]', [["ldn", "aspirin"]]),  # flat, several drugs, one text
])
def test_single_text_reply_shapes_normalise(monkeypatch, raw, expected):
    _stub(monkeypatch, raw)
    assert extract.extract_batch(client=None, texts=["I take LDN"]) == expected


def test_multi_text_batch_is_unaffected(monkeypatch):
    _stub(monkeypatch, '[["ldn"], []]')
    assert extract.extract_batch(client=None, texts=["took LDN", "nothing"]) == [["ldn"], []]


def test_genuine_count_mismatch_is_still_unparsed(monkeypatch):
    """Normalising must not swallow a real mismatch once splitting is exhausted."""
    _stub(monkeypatch, '[["ldn"], ["aspirin"], ["b12"]]')
    assert extract.extract_batch(client=None, texts=["a", "b"], _depth=2) == [None, None]


@pytest.mark.parametrize("raw", ['[{"drug": "ldn"}]', '[["ldn", {"x": 1}]]'])
def test_a_shape_that_is_not_strings_is_a_parse_failure(monkeypatch, raw):
    """The caller flattens with str(d).lower(), so an unguarded dict is written to the treatment
    table as the drug "{'drug': 'ldn'}". An unreadable shape is a parse failure."""
    _stub(monkeypatch, raw)
    assert extract.extract_batch(client=None, texts=["I take LDN"]) == [None]


def test_a_whitespace_only_entry_does_not_become_an_empty_drug(monkeypatch):
    """`if d` passed "  ", which then stripped to "" and was written as a drug name."""
    _stub(monkeypatch, '[["ldn", "  "]]')
    assert _flatten(extract.extract_batch(client=None, texts=["x"])[0]) == ["ldn"]
