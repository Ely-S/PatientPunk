"""Regression tests for the KG claim contract.

`parse_claims` is a pure function of (response JSON, post text), so the whole
validation contract is testable without DSPy, a network, or a database.
"""

from __future__ import annotations

import json
from collections import Counter

import pytest

from kg_extract import parse_claims
from kg_prompts import CLAIM_TYPES, build_instructions

POST = "I have terrible brain fog. I take LDN 4.5mg and it helped my fatigue."


def run(claims: list, edges: list | None = None, post: str = POST):
    stats: Counter = Counter()
    parsed, parsed_edges = parse_claims(
        json.dumps({"claims": claims, "edges": edges or []}), post, stats)
    return parsed, parsed_edges, stats


def test_valid_claim_round_trips():
    claims, _, stats = run([{
        "local_id": "c1", "claim_type": "symptom", "symptom_text": "brain fog",
        "severity": "severe", "source_span": "terrible brain fog", "confidence": "0.9",
    }])
    assert len(claims) == 1
    assert claims[0] == {
        "local_id": "c1", "claim_type": "symptom",
        "source_span": "terrible brain fog", "confidence": 0.9,
        "payload": {"symptom_text": "brain fog", "severity": "severe"},
        "span_grounded": 1,
    }
    assert not stats


@pytest.mark.parametrize("placeholder", ["unknown", "Not Specified", "none mentioned", "n/a"])
def test_placeholder_values_are_dropped_not_stored(placeholder):
    claims, _, _ = run([{
        "claim_type": "symptom", "symptom_text": "brain fog", "severity": placeholder,
        "source_span": "terrible brain fog",
    }])
    assert claims[0]["payload"] == {"symptom_text": "brain fog"}


def test_placeholder_in_the_required_field_rejects_the_claim():
    claims, _, stats = run([{"claim_type": "symptom", "symptom_text": "unknown"}])
    assert claims == []
    assert stats["invalid:symptom.symptom_text"] == 1


def test_missing_required_field_rejects_the_claim():
    claims, _, stats = run([{"claim_type": "symptom", "severity": "severe"}])
    assert claims == []
    assert stats["invalid:symptom.symptom_text"] == 1


def test_unknown_claim_type_is_rejected_and_counted():
    claims, _, stats = run([{"claim_type": "vibes", "vibe_text": "off"}])
    assert claims == []
    assert stats["bad_claim_type:vibes"] == 1


def test_unknown_payload_keys_are_kept_but_counted():
    claims, _, stats = run([{
        "claim_type": "symptom", "symptom_text": "brain fog", "novel_key": "signal",
        "source_span": "terrible brain fog",
    }])
    assert claims[0]["payload"]["novel_key"] == "signal"
    assert stats["extra_key:symptom.novel_key"] == 1


def test_span_grounding_flags_paraphrase():
    claims, _, _ = run([
        {"local_id": "a", "claim_type": "symptom", "symptom_text": "brain fog",
         "source_span": "terrible brain fog"},
        {"local_id": "b", "claim_type": "symptom", "symptom_text": "fog",
         "source_span": "the author reports cognitive difficulty"},
    ])
    assert [c["span_grounded"] for c in claims] == [1, 0]


def test_grounding_ignores_whitespace_and_case():
    claims, _, _ = run([{
        "claim_type": "symptom", "symptom_text": "brain fog",
        "source_span": "Terrible   Brain\n Fog",
    }])
    assert claims[0]["span_grounded"] == 1


def test_unparseable_confidence_is_dropped_without_losing_the_claim():
    claims, _, _ = run([{
        "claim_type": "symptom", "symptom_text": "brain fog", "confidence": "high",
        "source_span": "terrible brain fog",
    }])
    assert claims[0]["confidence"] is None


def test_one_bad_claim_does_not_take_down_the_rest():
    claims, _, stats = run([
        {"claim_type": "symptom", "symptom_text": "brain fog"},
        {"claim_type": "symptom"},                 # missing required
        "not an object",                           # not even a dict
        {"claim_type": "insight", "belief_text": "LDN is the reason"},
    ])
    assert [c["claim_type"] for c in claims] == ["symptom", "insight"]
    assert stats["claim_not_object"] == 1
    assert stats["invalid:symptom.symptom_text"] == 1


def test_local_ids_are_assigned_when_the_model_omits_them():
    claims, _, _ = run([
        {"claim_type": "symptom", "symptom_text": "brain fog"},
        {"claim_type": "symptom", "symptom_text": "fatigue"},
    ])
    assert [c["local_id"] for c in claims] == ["c1", "c2"]


def test_edges_normalize_and_survive():
    _, edges, stats = run(
        [{"local_id": "c1", "claim_type": "symptom", "symptom_text": "brain fog"},
         {"local_id": "c2", "claim_type": "treatment_response", "treatment_text": "LDN"}],
        [{"from": "c2", "to": "c1", "relation": " treats ", "confidence": 0.6}])
    assert edges == [{"from": "c2", "to": "c1", "relation": "TREATS", "confidence": 0.6}]
    assert not stats


@pytest.mark.parametrize("edge,expected_stat", [
    ({"from": "c1", "to": "c99", "relation": "TREATS"}, "dangling_edge"),
    ({"from": "c1", "to": "c1", "relation": "TREATS"}, "dangling_edge"),
    ({"from": "c1", "to": "c2", "relation": "MADE_UP"}, "bad_relation:MADE_UP"),
])
def test_bad_edges_are_dropped_and_counted(edge, expected_stat):
    _, edges, stats = run(
        [{"local_id": "c1", "claim_type": "symptom", "symptom_text": "brain fog"},
         {"local_id": "c2", "claim_type": "treatment_response", "treatment_text": "LDN"}],
        [edge])
    assert edges == []
    assert stats[expected_stat] == 1


def test_non_object_response_raises_so_the_caller_can_retry():
    # A ValueError is what triggers cmd_run's hotter-temperature retry.
    with pytest.raises(ValueError):
        parse_claims(json.dumps(["not", "an", "object"]), POST, Counter())


def test_instructions_list_every_claim_type_and_its_required_key():
    text = build_instructions()
    for ctype, model in CLAIM_TYPES.items():
        assert f'"{ctype}"' in text
        assert f"{model.primary_field()} (REQUIRED)" in text
