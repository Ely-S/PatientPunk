"""extract_batch must distinguish a genuine "no drugs" ([]) from a parse failure (None).

A batch whose model output could not be parsed used to be returned as [[]] —
indistinguishable from "found nothing" — and then cached as such, so the item was never
retried. extract_batch now returns None for any text it could not parse, and
run_extraction leaves those uncached (so a later run retries them) and logs the count.
"""
import pipeline.extract as extract


def _stub_model_output(monkeypatch, raw):
    """Make the fast-model call return a fixed raw string instead of hitting the API."""
    monkeypatch.setattr(extract, "llm_call", lambda *args, **kwargs: raw)


def test_parsed_empty_is_not_a_failure(monkeypatch):
    # The model correctly reports no drugs -> [] (a real answer), never None.
    _stub_model_output(monkeypatch, "[[]]")
    assert extract.extract_batch(client=None, texts=["no drugs mentioned here"]) == [[]]


def test_unparseable_output_is_marked_none(monkeypatch):
    # The model returns something that isn't a JSON array -> the text is marked unparsed.
    _stub_model_output(monkeypatch, "sorry, I can't help with that")
    assert extract.extract_batch(client=None, texts=["I took LDN 4.5mg and felt better"]) == [None]


def test_success_returns_drug_lists(monkeypatch):
    _stub_model_output(monkeypatch, '[["ldn"], []]')
    assert extract.extract_batch(client=None, texts=["took LDN", "no drugs"]) == [["ldn"], []]
