"""Recover useful canonicalization results from oversized or malformed batches."""

import json
from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import Mock

from patientpunk._utils import LLMResponseError
import pipeline.canonicalize as canon

NAMES = [f"drug{i}" for i in range(8)]


def _merge_first(names: list[str]) -> str:
    return json.dumps({names[0]: f"canonical_{names[0]}"})


def _fake_llm(
    seen: list[list[str]],
    response_for: Callable[[list[str]], str | Exception],
):
    def fake(_client, prompt, model=None, max_tokens=None):
        names = json.loads(prompt.split("canonicalize:\n")[1])
        seen.append(names)
        response = response_for(names)
        if isinstance(response, Exception):
            raise response
        return response

    return fake


def test_unusable_batch_splits_and_preserves_both_halves(monkeypatch):
    seen: list[list[str]] = []

    def response_for(names):
        return "not json" if len(names) > 4 else _merge_first(names)

    monkeypatch.setattr(canon, "llm_call", _fake_llm(seen, response_for))

    result = canon.canonicalize_batch(object(), NAMES)

    assert [len(names) for names in seen] == [8, 4, 4]
    assert set(result.mapping) == set(NAMES)
    assert sum(raw != canonical for raw, canonical in result.mapping.items()) == 2
    assert result.failed_names == 0
    assert result.split_names == 8


def test_untruncated_batch_makes_one_call(monkeypatch):
    seen: list[list[str]] = []
    monkeypatch.setattr(
        canon,
        "llm_call",
        _fake_llm(seen, _merge_first),
    )

    result = canon.canonicalize_batch(object(), NAMES)

    assert len(seen) == 1
    assert result.failed_names == 0
    assert result.split_names == 0


def test_failed_half_does_not_discard_successful_half(monkeypatch):
    seen: list[list[str]] = []

    def response_for(names):
        if len(names) > 4 or names[0] >= "drug4":
            return LLMResponseError("unusable response")
        return _merge_first(names)

    monkeypatch.setattr(canon, "llm_call", _fake_llm(seen, response_for))

    result = canon.canonicalize_batch(object(), NAMES)

    assert result.mapping["drug0"] == "canonical_drug0"
    assert result.mapping["drug4"] == "drug4"
    assert result.failed_names == 4
    assert result.split_names == 8


def test_split_depth_is_bounded(monkeypatch):
    names = [f"drug{i:02d}" for i in range(32)]
    seen: list[list[str]] = []

    def failure(_):
        return LLMResponseError("always unusable")

    monkeypatch.setattr(canon, "llm_call", _fake_llm(seen, failure))

    result = canon.canonicalize_batch(object(), names)

    assert min(len(batch) for batch in seen) == 2
    assert result.mapping == {name: name for name in names}
    assert result.failed_names == len(names)
    assert result.split_names == len(names)


def test_run_reports_aggregated_split_and_failure_counts(monkeypatch, tmp_path):
    tagged = [{"drugs_direct": ["drug0", "drug1"], "drugs_context": []}]
    (tmp_path / canon.TAGGED_MENTIONS).write_text(
        json.dumps(tagged),
        encoding="utf-8",
    )
    result = canon.CanonicalizationBatchResult(
        mapping={"drug0": "canonical_drug0", "drug1": "drug1"},
        failed_names=1,
        split_names=2,
    )
    config = SimpleNamespace(
        drug=None,
        client=object(),
        db_path=tmp_path / "test.db",
        path=lambda name: tmp_path / name,
    )
    log = Mock()
    monkeypatch.setattr(canon, "canonicalize_batch", Mock(return_value=result))
    monkeypatch.setattr(canon, "upsert_treatments", lambda *_: 2)
    monkeypatch.setattr(canon, "log", log)

    assert canon.run_canonicalization(config) == result.mapping

    log.warning.assert_called_once()
    warning = log.warning.call_args.args
    assert "SPLIT BATCHES" in warning[0]
    assert warning[1:] == (2, 2)

    log.error.assert_called_once()
    error = log.error.call_args.args
    assert "INCOMPLETE" in error[0]
    assert error[1:] == (1, 2, 50.0)
