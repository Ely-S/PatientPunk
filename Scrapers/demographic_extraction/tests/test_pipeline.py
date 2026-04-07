"""
Tests for PatientPunk extraction pipeline utilities.

No API calls are made — all tests cover pure functions only.
All imports come from ``old/discover_fields.py`` (the legacy script) because
that is where the canonical logic lives; the library classes in
``patientpunk/extractors/`` are thin subprocess wrappers around the same code.

Test sections
-------------
TestParseJsonResponse       parse_json_response() — extract valid JSON from
                            raw LLM output that may include markdown fences,
                            prose preamble, or trailing text.

TestPatternsAgainstExamples evaluate_patterns() — run compiled regex patterns
                            against example texts and return a hit/miss report.
                            Used in Phase 3 Stage 2 to validate Sonnet-generated
                            patterns before committing them to the schema.

TestCollectTexts            collect_texts_from_post() / collect_texts_from_user()
                            — extract non-empty text segments from raw JSON
                            post and user-history objects.

TestMergeIntoSchema         merge_into_schema() — merge a list of newly
                            discovered field dicts into an existing extension
                            schema without overwriting existing fields.

TestSchemaPatterns          Smoke-tests against the real
                            schemas/covidlonghaulers_schema.json: verifies
                            every pattern compiles and spot-checks known texts.
                            Skipped automatically if the schema file is absent.

Run with:
    cd Scrapers/demographic_extraction
    python -m pytest tests/ -v
"""

import json
import sys
from pathlib import Path

import pytest

# Insert the demographic_extraction/ directory onto sys.path so that
# ``from old.discover_fields import ...`` resolves correctly regardless of
# the working directory pytest is invoked from.
sys.path.insert(0, str(Path(__file__).parent.parent))

from old.discover_fields import (
    collect_texts_from_post,
    collect_texts_from_user,
    merge_into_schema,
    parse_json_response,
    evaluate_patterns,
)


# =============================================================================
# parse_json_response
# =============================================================================

class TestParseJsonResponse:
    def test_plain_json_object(self):
        assert parse_json_response('{"key": "value"}') == {"key": "value"}

    def test_plain_json_array(self):
        assert parse_json_response('[1, 2, 3]') == [1, 2, 3]

    def test_markdown_fence_json(self):
        text = '```json\n{"patterns": ["foo", "bar"]}\n```'
        result = parse_json_response(text)
        assert result == {"patterns": ["foo", "bar"]}

    def test_markdown_fence_no_lang(self):
        text = '```\n{"key": 1}\n```'
        assert parse_json_response(text) == {"key": 1}

    def test_json_embedded_in_prose(self):
        text = 'Here is the result:\n{"discovered_fields": []}\nThat is all.'
        result = parse_json_response(text)
        assert result == {"discovered_fields": []}

    def test_empty_string_returns_none(self):
        assert parse_json_response("") is None

    def test_plain_text_returns_none(self):
        assert parse_json_response("I found no patterns in this text.") is None

    def test_malformed_json_returns_none(self):
        assert parse_json_response('{"key": missing_quotes}') is None

    def test_nested_json(self):
        data = {"fields": {"age": ["34"], "sex": ["female"]}}
        assert parse_json_response(json.dumps(data)) == data

    def test_whitespace_stripped(self):
        assert parse_json_response('  {"k": 1}  ') == {"k": 1}


# =============================================================================
# evaluate_patterns
# =============================================================================

class TestPatternsAgainstExamples:
    def test_all_match(self):
        patterns = [r"\b(\d+)\s*(?:years?\s+old|y/?o)\b"]
        examples = [
            {"text": "I am 34 years old", "extracted_value": "34"},
            {"text": "She is 27yo", "extracted_value": "27"},
        ]
        report = evaluate_patterns(patterns, examples)
        assert report["hits"] == 2
        assert report["misses"] == 0
        assert report["hit_rate"] == 1.0

    def test_all_miss(self):
        patterns = [r"\bPOTS\b"]
        examples = [
            {"text": "I have fibromyalgia", "extracted_value": "fibromyalgia"},
        ]
        report = evaluate_patterns(patterns, examples)
        assert report["hits"] == 0
        assert report["misses"] == 1
        assert report["hit_rate"] == 0.0

    def test_partial_match(self):
        patterns = [r"\bfemale\b"]
        examples = [
            {"text": "I am a 34 year old female", "extracted_value": "female"},
            {"text": "27 year old male patient", "extracted_value": "male"},
        ]
        report = evaluate_patterns(patterns, examples)
        assert report["hits"] == 1
        assert report["misses"] == 1
        assert report["hit_rate"] == 0.5

    def test_compile_error_reported(self):
        patterns = [r"(unclosed", r"\bvalid\b"]
        examples = [{"text": "valid text", "extracted_value": "valid"}]
        report = evaluate_patterns(patterns, examples)
        assert len(report["compile_errors"]) == 1
        assert report["compile_errors"][0]["pattern"] == r"(unclosed"
        # valid pattern still matches
        assert report["hits"] == 1

    def test_empty_examples(self):
        report = evaluate_patterns([r"\bfoo\b"], [])
        assert report["hit_rate"] == 0
        assert report["total_examples"] == 0

    def test_captured_group_returned(self):
        patterns = [r"(\d+)\s*years?\s+old"]
        examples = [{"text": "I am 42 years old", "extracted_value": "42"}]
        report = evaluate_patterns(patterns, examples)
        assert report["hit_details"][0]["captured_value"] == "42"

    def test_case_insensitive(self):
        # Patterns are compiled with re.IGNORECASE
        patterns = [r"\bpots\b"]
        examples = [{"text": "Diagnosed with POTS last year", "extracted_value": "POTS"}]
        report = evaluate_patterns(patterns, examples)
        assert report["hits"] == 1

    def test_missed_examples_in_report(self):
        patterns = [r"\bPOTS\b"]
        examples = [{"text": "I have fibromyalgia", "extracted_value": "fibromyalgia"}]
        report = evaluate_patterns(patterns, examples)
        assert len(report["missed_examples"]) == 1
        assert report["missed_examples"][0]["text"] == "I have fibromyalgia"


# =============================================================================
# collect_texts_from_user / collect_texts_from_post
# =============================================================================

class TestCollectTexts:
    def test_user_posts_and_comments(self):
        user = {
            "posts": [
                {"title": "My POTS story", "body": "I was diagnosed last year"},
                {"title": "Update", "body": ""},
            ],
            "comments": [
                {"body": "LDN really helped me"},
                {"body": ""},
            ],
        }
        texts = collect_texts_from_user(user)
        assert "My POTS story" in texts
        assert "I was diagnosed last year" in texts
        assert "LDN really helped me" in texts
        # Empty strings not included
        assert "" not in texts

    def test_user_empty(self):
        assert collect_texts_from_user({}) == []

    def test_post_with_comments(self):
        post = {
            "title": "Long COVID 2 years in",
            "body": "Still struggling with fatigue",
            "comments": [
                {"body": "Same here"},
                {"body": ""},
            ],
        }
        texts = collect_texts_from_post(post)
        assert "Long COVID 2 years in" in texts
        assert "Still struggling with fatigue" in texts
        assert "Same here" in texts
        assert "" not in texts

    def test_post_no_comments(self):
        post = {"title": "Title only", "body": "Body text"}
        texts = collect_texts_from_post(post)
        assert texts == ["Title only", "Body text"]


# =============================================================================
# merge_into_schema
# =============================================================================

class TestMergeIntoSchema:
    def _base_schema(self):
        return {
            "schema_id": "test_schema",
            "extension_fields": {
                "existing_field": {
                    "description": "Already here",
                    "patterns": [r"\bexisting\b"],
                }
            }
        }

    def _new_fields(self):
        return [
            {
                "field_name": "new_field_a",
                "description": "A new field",
                "patterns": [r"\bnew_a\b"],
                "confidence": "medium",
                "hit_rate": 0.75,
                "frequency_hint": "common",
                "research_value": "Useful for research",
            },
            {
                "field_name": "new_field_b",
                "description": "Another new field",
                "patterns": [r"\bnew_b\b"],
                "confidence": "low",
                "hit_rate": 0.6,
                "frequency_hint": "occasional",
                "research_value": "",
            },
        ]

    def test_new_fields_added(self):
        schema = self._base_schema()
        updated, added, skipped = merge_into_schema(self._new_fields(), schema)
        assert added == 2
        assert skipped == 0
        assert "new_field_a" in updated["extension_fields"]
        assert "new_field_b" in updated["extension_fields"]

    def test_existing_field_not_overwritten(self):
        schema = self._base_schema()
        fields = self._new_fields() + [{
            "field_name": "existing_field",
            "description": "Should NOT overwrite",
            "patterns": [r"\boverwritten\b"],
            "confidence": "high",
            "hit_rate": 1.0,
            "frequency_hint": "common",
            "research_value": "",
        }]
        updated, added, skipped = merge_into_schema(fields, schema)
        assert added == 2
        assert skipped == 1
        # Original description preserved
        assert updated["extension_fields"]["existing_field"]["description"] == "Already here"

    def test_discovered_at_timestamp_added(self):
        schema = self._base_schema()
        updated, _, _ = merge_into_schema(self._new_fields(), schema)
        assert "_discovered_at" in updated["extension_fields"]["new_field_a"]
        assert "_discovered_at" in updated["extension_fields"]["new_field_b"]

    def test_existing_field_has_no_timestamp_added(self):
        schema = self._base_schema()
        merge_into_schema(self._new_fields(), schema)
        # The pre-existing field should not get a timestamp injected
        assert "_discovered_at" not in schema["extension_fields"]["existing_field"]

    def test_empty_validated_fields(self):
        schema = self._base_schema()
        updated, added, skipped = merge_into_schema([], schema)
        assert added == 0
        assert skipped == 0
        assert list(updated["extension_fields"].keys()) == ["existing_field"]

    def test_schema_without_extension_fields_key(self):
        schema = {"schema_id": "bare"}
        updated, added, skipped = merge_into_schema(self._new_fields(), schema)
        assert added == 2
        assert "extension_fields" in updated

    def test_patterns_stored_correctly(self):
        schema = self._base_schema()
        fields = [{
            "field_name": "pattern_check",
            "description": "Test",
            "patterns": [r"\bfoo\b", r"\bbar\b"],
            "confidence": "medium",
            "hit_rate": 0.8,
            "frequency_hint": "common",
            "research_value": "",
        }]
        updated, _, _ = merge_into_schema(fields, schema)
        stored = updated["extension_fields"]["pattern_check"]["patterns"]
        assert stored == [r"\bfoo\b", r"\bbar\b"]


# =============================================================================
# Schema pattern smoke tests — loads the real schema file and checks patterns
# compile and match their embedded example values
# =============================================================================

SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "covidlonghaulers_schema.json"


@pytest.mark.skipif(not SCHEMA_PATH.exists(), reason="Schema file not found")
class TestSchemaPatterns:
    @pytest.fixture(scope="class")
    def schema(self):
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            return json.load(f)

    def test_all_patterns_compile(self, schema):
        import re
        errors = []
        for field_name, field in schema.get("extension_fields", {}).items():
            for pattern in field.get("patterns", []):
                try:
                    re.compile(pattern, re.IGNORECASE)
                except re.error as e:
                    errors.append(f"{field_name}: {pattern!r} → {e}")
        assert not errors, "Compile errors:\n" + "\n".join(errors)

    def test_override_patterns_compile(self, schema):
        import re
        errors = []
        for field_name, override in schema.get("override_base_patterns", {}).items():
            for pattern in override.get("patterns", []):
                try:
                    re.compile(pattern, re.IGNORECASE)
                except re.error as e:
                    errors.append(f"override {field_name}: {pattern!r} → {e}")
        assert not errors, "Compile errors:\n" + "\n".join(errors)

    # Spot-check a few fields with known example texts
    @pytest.mark.parametrize("field,text,should_match", [
        ("covid_wave",       "I got sick during the Delta wave",          True),
        ("covid_wave",       "My cat knocked over a glass of water",      False),
        ("vaccination_status", "I am fully vaccinated with Pfizer",       True),
        ("vaccination_status", "I am unvaccinated",                       True),
        ("functional_status_tier", "I've been mostly bedbound for months", True),
        ("functional_status_tier", "I went for a 5km run this morning",   False),
        ("infection_count",  "I've been reinfected twice now",            True),
        ("biomarker_results", "I had elevated ferritin and low cortisol",  True),
    ])
    def test_spot_check(self, schema, field, text, should_match):
        import re
        patterns = schema.get("extension_fields", {}).get(field, {}).get("patterns", [])
        assert patterns, f"No patterns found for field '{field}'"
        matched = any(re.search(p, text, re.IGNORECASE) for p in patterns)
        if should_match:
            assert matched, f"Expected '{field}' to match: {text!r}"
        else:
            assert not matched, f"Expected '{field}' NOT to match: {text!r}"
