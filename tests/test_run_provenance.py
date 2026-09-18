from __future__ import annotations

from utilities import run_provenance
from utilities.run_provenance import (
    PipelineOptions,
    build_run_provenance,
    hash_aliases,
)


def _options(**changes: object) -> PipelineOptions:
    values = {
        "limit": 0,
        "reclassify": False,
        "skip_extract": False,
        "skip_canonicalize": False,
        "skip_prefilter": False,
        "max_upstream_chars": None,
        "max_upstream_depth": None,
        "workers": 20,
        "drug": "ldn",
        "configured_drug_aliases_sha256": hash_aliases(
            ["ldn", "low dose naltrexone"]
        ),
    }
    values.update(changes)
    return PipelineOptions.model_validate(values)


def _build(monkeypatch, options: PipelineOptions):
    monkeypatch.setattr(
        run_provenance,
        "read_git_state",
        lambda: ("a" * 40, False),
    )
    return build_run_provenance(
        provider="openrouter",
        fast_model="fast-model",
        strong_model="strong-model",
        reasoning_mode="disabled",
        options=options,
    )


def test_run_fingerprint_is_deterministic_and_sensitive_to_options(monkeypatch) -> None:
    first = _build(monkeypatch, _options())
    repeated = _build(monkeypatch, _options())
    changed = _build(monkeypatch, _options(skip_prefilter=True))

    assert first.fingerprint == repeated.fingerprint
    assert first.fingerprint != changed.fingerprint
    assert first.schema_id == "treatment_sentiment_run_provenance_v1"
    assert first.git_commit == "a" * 40
    assert first.git_dirty is False
    assert first.reasoning_mode == "disabled"
    assert len(first.prompt_bundle_sha256) == 64
    assert first.model_dump(mode="json")["fingerprint"] == first.fingerprint


def test_alias_hash_ignores_case_order_and_duplicates() -> None:
    assert hash_aliases(["LDN", "low dose naltrexone", "ldn"]) == hash_aliases(
        ["low dose naltrexone", "ldn"]
    )
