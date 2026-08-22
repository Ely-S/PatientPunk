"""Recover useful canonicalization results from oversized or malformed batches."""

import json
import sys
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path[:0] = [
    str(REPO_ROOT / "src"),
    str(REPO_ROOT / "variable_extraction"),
]

from patientpunk._utils import LLMResponseError  # noqa: E402
import pipeline.canonicalize as canon  # noqa: E402

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
