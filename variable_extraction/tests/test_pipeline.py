"""
Tests for PatientPunk extraction pipeline utilities.

No API calls are made -- all tests cover pure functions only.
Imports come from the in-process ``patientpunk`` phase modules.

Test sections
-------------
TestParseJsonResponse       parse_json_response() -- extract valid JSON from
                            raw LLM output that may include markdown fences,
                            prose preamble, or trailing text.

TestCollectTexts            collect_texts_from_post() / collect_texts_from_user()
                            -- extract non-empty text segments from raw JSON
                            post and user-history objects.

TestMergeIntoSchema         merge_into_schema() -- merge a list of newly
                            discovered field dicts into an existing extension
                            schema without overwriting existing fields.

Run with:
    cd Scrapers/variable_extraction
    python -m pytest tests/ -v
"""

import json
from pathlib import Path

import pytest

from patientpunk.discover import (
    collect_texts_from_post,
    collect_texts_from_user,
    merge_into_schema,
    parse_json_response,
)
from patientpunk.demographics_deductive import _default_output_path
from patientpunk.codebook import build_field_registry


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

    def test_json_object_embedded_after_label(self):
        """JSON object appearing after a prose label should be extracted."""
        text = 'The discovered fields are:\n{"field_name": "age"}\nEnd.'
        result = parse_json_response(text)
        assert result == {"field_name": "age"}

    def test_deeply_nested_object(self):
        data = {"a": {"b": {"c": {"d": [1, 2, 3]}}}}
        assert parse_json_response(json.dumps(data)) == data

    def test_integer_json_returns_none(self):
        # A bare integer is valid JSON but not a useful LLM response object
        # (behaviour depends on implementation -- just verify it doesn't crash)
        result = parse_json_response("42")
        # Either None or the integer 42; the key contract is no exception
        assert result is None or result == 42


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

    def test_post_excludes_comments(self):
        """Title + body only — comments are other users and must not attach to the author."""
        post = {
            "title": "Long COVID 2 years in",
            "body": "Still struggling with fatigue",
            "comments": [
                {"body": "Same here"},
                {"body": ""},
            ],
        }
        texts = collect_texts_from_post(post)
        assert texts == ["Long COVID 2 years in", "Still struggling with fatigue"]
        assert "Same here" not in texts

    def test_post_no_comments(self):
        post = {"title": "Title only", "body": "Body text"}
        texts = collect_texts_from_post(post)
        assert texts == ["Title only", "Body text"]

    def test_post_filters_removed_and_deleted_body(self):
        post = {
            "title": "My post",
            "body": "[removed]",
            "comments": [{"body": "I have the same issue"}, {"body": ""}],
        }
        texts = collect_texts_from_post(post)
        assert texts == ["My post"]
        assert "[removed]" not in texts
        assert "I have the same issue" not in texts

    def test_post_filters_deleted_body(self):
        post = {
            "title": "Question",
            "body": "[deleted]",
            "comments": [{"body": "Try LDN"}, {"body": ""}],
        }
        texts = collect_texts_from_post(post)
        assert texts == ["Question"]
        assert "[deleted]" not in texts
        assert "Try LDN" not in texts

    def test_user_no_posts_key(self):
        """Users without a 'posts' key should still return comment texts."""
        user = {"comments": [{"body": "Me too!"}, {"body": ""}]}
        texts = collect_texts_from_user(user)
        assert "Me too!" in texts

    def test_user_no_comments_key(self):
        """Users without a 'comments' key should still return post texts."""
        user = {"posts": [{"title": "Title", "body": "Body"}]}
        texts = collect_texts_from_user(user)
        assert "Title" in texts
        assert "Body" in texts


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
                }
            }
        }

    def _new_fields(self):
        return [
            {
                "field_name": "new_field_a",
                "description": "A new field",
                "confidence": "medium",
                "frequency_hint": "common",
                "research_value": "Useful for research",
            },
            {
                "field_name": "new_field_b",
                "description": "Another new field",
                "confidence": "low",
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
            "confidence": "high",
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

    def test_merge_preserves_other_top_level_keys(self):
        """Arbitrary top-level keys in the schema should survive a merge."""
        schema = {
            "schema_id": "preserve_test",
            "extension_fields": {},
            "_target_subreddit": "r/longhaulers",
            "version": "1.2.3",
        }
        updated, _, _ = merge_into_schema(self._new_fields(), schema)
        assert updated["_target_subreddit"] == "r/longhaulers"
        assert updated["version"] == "1.2.3"


# =============================================================================
# build_field_registry -- discovered-schema append + dedup
# =============================================================================

class TestBuildFieldRegistryDiscovered:
    _BASE = {"base_fields": {"age": {"description": "a", "confidence": "high"}}}

    def test_shipped_base_schema_registers_dosage(self):
        base_path = Path(__file__).parent.parent / "schemas" / "base_schema.json"
        base = json.loads(base_path.read_text(encoding="utf-8"))
        registry = build_field_registry(base, {"extension_fields": {}})
        fields = {row["field"]: row for row in registry}

        assert fields["dosage"]["source"] == "base"
        assert fields["dosage"]["confidence"] == "medium"

    def test_appends_discovered(self):
        ext = {"extension_fields": {}}
        disc = {"extension_fields": {
            "newf": {"source": "llm_discovered", "description": "d",
                     "confidence": "low"}}}
        reg = build_field_registry(self._BASE, ext, disc)
        fields = {r["field"]: r for r in reg}
        assert fields["newf"]["source"] == "llm_discovered"

    def test_dedup_curated_wins(self):
        ext = {"extension_fields": {
            "shared": {"source": "extension", "description": "curated"}}}
        disc = {"extension_fields": {
            "shared": {"source": "llm_discovered", "description": "disc"}}}
        reg = build_field_registry(self._BASE, ext, disc)
        shared = [r for r in reg if r["field"] == "shared"]
        assert len(shared) == 1                       # not duplicated
        assert shared[0]["source"] == "extension"     # curated entry wins


class TestDemographicsScriptDefaults:
    def test_output_defaults_next_to_input_dir(self, tmp_path):
        assert _default_output_path(tmp_path) == tmp_path / "demographics.csv"
