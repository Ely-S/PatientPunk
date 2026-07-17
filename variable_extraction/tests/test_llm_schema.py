"""Malformed model output is data, not an exception.

The shapes here are not hypothetical: they were counted across 987 cached
deepseek-v4-flash replies. Field values arrived as null (31768x), list (1788x),
bare str (50x) and bare int (14x), and 5 replies sent "suggested_fields": null
where Claude sends []. That null aborted a 1000-record run at record 47.
"""

from __future__ import annotations

import pytest

from patientpunk.llm_schema import LLMExtraction, parse_extraction


def _fields(payload):
    result = parse_extraction(payload)
    assert result is not None, f"expected {payload!r} to validate"
    return result[0].fields


# --- the shapes that actually crashed / leaked -------------------------------

def test_null_suggested_fields_is_empty_not_a_crash():
    result = parse_extraction({"fields": {"age": ["24"]}, "suggested_fields": None})
    assert result is not None
    assert result[0].suggested_fields == []


def test_int_value_is_coerced_not_passed_through():
    """14 raw ints reached records.csv where every other value is list|None."""
    assert _fields({"fields": {"age": 24}}) == {"age": ["24"]}


def test_str_value_is_wrapped():
    assert _fields({"fields": {"age": "24"}}) == {"age": ["24"]}


def test_float_value_is_coerced():
    assert _fields({"fields": {"long_covid_duration_months": 12.5}}) == {
        "long_covid_duration_months": ["12.5"]
    }


# --- empty vs malformed: the distinction that drives retries ------------------

def test_null_fields_is_an_empty_extraction():
    """~47% of records legitimately extract nothing; that must not retry."""
    assert _fields({"fields": None}) == {}


def test_missing_fields_key_is_malformed():
    """No 'fields' key at all is a broken reply, not an empty one."""
    assert parse_extraction({"suggested_fields": []}) is None


def test_non_object_fields_is_malformed():
    assert parse_extraction({"fields": ["age"]}) is None
    assert parse_extraction({"fields": "age"}) is None


@pytest.mark.parametrize("payload", [None, [], ["a"], "text", 42])
def test_non_dict_reply_is_malformed(payload):
    assert parse_extraction(payload) is None


# --- value normalisation ------------------------------------------------------

def test_empty_and_all_falsy_lists_collapse_to_none():
    # Must match the old `[v for v in val if v] or None` exactly: coverage
    # percentages are computed off this.
    assert _fields({"fields": {"a": [], "b": ["", None], "c": ["ME/CFS"]}}) == {
        "a": None, "b": None, "c": ["ME/CFS"],
    }


def test_falsy_members_are_dropped_from_mixed_lists():
    assert _fields({"fields": {"c": ["", None, "ME/CFS", "  "]}}) == {"c": ["ME/CFS"]}


def test_list_members_are_stringified():
    assert _fields({"fields": {"infection_count": [1, 2]}}) == {"infection_count": ["1", "2"]}


def test_values_are_stripped():
    assert _fields({"fields": {"age": ["  24  "]}}) == {"age": ["24"]}


def test_bool_is_dropped_rather_than_stringified():
    # "True" is not a plausible clinical value; silently recording it is worse
    # than recording nothing.
    assert _fields({"fields": {"age": True}}) == {"age": None}


def test_nested_junk_values_are_dropped():
    assert _fields({"fields": {"a": {"nested": 1}, "b": [["x"]], "c": [{"k": "v"}]}}) == {
        "a": None, "b": None, "c": None,
    }


def test_explicit_null_value_survives_as_none():
    assert _fields({"fields": {"age": None}}) == {"age": None}


# --- suggested_fields ---------------------------------------------------------

def test_suggestion_missing_name_is_dropped():
    result = parse_extraction({"fields": {}, "suggested_fields": [{"description": "no name"}]})
    assert result is not None and result[0].suggested_fields == []


def test_junk_suggestion_members_are_dropped_not_fatal():
    result = parse_extraction(
        {"fields": {}, "suggested_fields": ["bare string", None, 7, {"name": "symptoms"}]}
    )
    assert result is not None
    assert [s.name for s in result[0].suggested_fields] == ["symptoms"]


def test_lone_suggestion_dict_is_wrapped():
    result = parse_extraction({"fields": {}, "suggested_fields": {"name": "symptoms"}})
    assert result is not None
    assert [s.name for s in result[0].suggested_fields] == ["symptoms"]


def test_suggestion_extra_keys_are_kept_for_discovery():
    result = parse_extraction(
        {"fields": {}, "suggested_fields": [{"name": "x", "example_value": "v"}]}
    )
    assert result is not None
    assert result[0].suggested_fields[0].model_dump()["example_value"] == "v"


def test_non_list_suggested_fields_is_empty_not_fatal():
    result = parse_extraction({"fields": {}, "suggested_fields": "symptoms"})
    assert result is not None and result[0].suggested_fields == []


# --- hallucinated field names -------------------------------------------------

def test_unknown_fields_are_dropped_and_reported():
    result = parse_extraction(
        {"fields": {"age": ["24"], "vibe": ["bad"], "aura": ["x"]}},
        allowed_fields={"age"},
    )
    assert result is not None
    extraction, dropped = result
    assert extraction.fields == {"age": ["24"]}
    assert dropped == ["aura", "vibe"]  # sorted, so the report is stable


def test_no_allowed_fields_means_no_filtering():
    extraction, dropped = parse_extraction({"fields": {"anything": ["x"]}})
    assert extraction.fields == {"anything": ["x"]}
    assert dropped == []


# --- the invariant everything downstream depends on ---------------------------

@pytest.mark.parametrize("payload", [
    {"fields": {"a": 1, "b": "s", "c": [1, "2"], "d": None, "e": True, "f": {}, "g": []}},
    {"fields": None},
    {"fields": {}, "suggested_fields": None},
])
def test_validated_values_are_always_list_or_none(payload):
    extraction, _ = parse_extraction(payload)
    for value in extraction.fields.values():
        assert value is None or (
            isinstance(value, list) and all(isinstance(v, str) for v in value)
        ), f"{value!r} is not list[str] | None"


def test_extra_top_level_keys_are_ignored():
    result = parse_extraction({"fields": {"age": ["24"]}, "commentary": "here you go"})
    assert result is not None
    assert not hasattr(result[0], "commentary")


def test_model_rejects_unvalidated_construction():
    """fields has no default: constructing without it is a programming error."""
    with pytest.raises(Exception):
        LLMExtraction()
