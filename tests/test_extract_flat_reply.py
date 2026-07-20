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


def test_multi_text_batch_unaffected(monkeypatch):
    _stub(monkeypatch, '[["ldn"], []]')
    assert extract.extract_batch(client=None, texts=["took LDN", "nothing"]) == [["ldn"], []]


def test_flat_multi_drug_reply_on_single_text(monkeypatch):
    """["ldn","aspirin"] for ONE text used to fail the length check and be marked unparsed
    forever — never cached, re-sent every run, drugs never recorded."""
    _stub(monkeypatch, '["ldn", "aspirin"]')
    result = extract.extract_batch(client=None, texts=["I take LDN and aspirin"])
    assert result == [["ldn", "aspirin"]]
    (drugs,) = result
    assert _flatten(drugs) == ["ldn", "aspirin"]


def test_genuine_count_mismatch_is_still_unparsed(monkeypatch):
    """Two texts, three answers: still an honest parse failure, not silently reshaped."""
    _stub(monkeypatch, '[["ldn"], ["aspirin"], ["b12"]]')
    assert extract.extract_batch(client=None, texts=["a", "b"], _depth=2) == [None, None]


def test_object_shaped_reply_is_a_parse_failure_not_a_drug(monkeypatch):
    """A dict entry must come back None, not coerce into a drug name.

    The caller flattens with str(d).lower(), so an unguarded dict is written to the
    treatment table as the literal drug "{'drug': 'ldn'}". An unreadable shape is a parse
    failure — the same distinction this module already draws for bad JSON. Raised by the
    gpt-5.1 review panel.
    """
    _stub(monkeypatch, '[{"drug": "ldn"}]')
    assert extract.extract_batch(client=None, texts=["I take LDN"]) == [None]


def test_a_list_with_a_non_string_member_is_a_parse_failure(monkeypatch):
    _stub(monkeypatch, '[["ldn", {"x": 1}]]')
    assert extract.extract_batch(client=None, texts=["I take LDN"]) == [None]
