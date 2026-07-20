"""extract_batch must return a list PER TEXT, even when the model flattens its reply.

The prompt asks for a list of drug-lists, but a model answering a SINGLE-text batch commonly
replies ["ldn"] rather than [["ldn"]]. The mismatch retry in extract_batch halves batches until
they are one text long, so single-text batches happen routinely, not just at the tail of a run.

Left unnormalised, the caller's flattening in run_extraction iterates the bare string "ldn"
character by character and records "l", "d", "n" as three separate drug mentions — silently
poisoning the corpus with junk drugs. Reported by the Gemini review on PR #66; pre-existing on
main, fixed here because this PR touches that code path.
"""
import pipeline.extract as extract


def _stub(monkeypatch, raw):
    monkeypatch.setattr(extract, "llm_call", lambda *a, **k: raw)


def _flatten(drugs):
    """The exact flattening run_extraction applies to each entry."""
    return [str(d).lower().strip()
            for sublist in drugs
            for d in (sublist if isinstance(sublist, list) else [sublist])
            if d]


def test_flat_single_item_reply_is_normalised(monkeypatch):
    """["ldn"] for one text must become [["ldn"]], not a bare string."""
    _stub(monkeypatch, '["ldn"]')
    assert extract.extract_batch(client=None, texts=["I take LDN"]) == [["ldn"]]


def test_nested_reply_is_unchanged(monkeypatch):
    _stub(monkeypatch, '[["ldn"]]')
    assert extract.extract_batch(client=None, texts=["I take LDN"]) == [["ldn"]]


def test_flat_reply_does_not_split_into_characters(monkeypatch):
    """The actual damage: without normalisation this yields ['l','d','n']."""
    _stub(monkeypatch, '["ldn"]')
    (drugs,) = extract.extract_batch(client=None, texts=["I take LDN"])
    assert _flatten(drugs) == ["ldn"]


def test_parsed_empty_still_means_no_drugs(monkeypatch):
    _stub(monkeypatch, "[[]]")
    (drugs,) = extract.extract_batch(client=None, texts=["no drugs here"])
    assert _flatten(drugs) == []


def test_multi_text_batch_unaffected(monkeypatch):
    _stub(monkeypatch, '[["ldn"], []]')
    assert extract.extract_batch(client=None, texts=["took LDN", "nothing"]) == [["ldn"], []]
