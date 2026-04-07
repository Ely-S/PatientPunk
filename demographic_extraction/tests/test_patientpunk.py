"""
Tests for the patientpunk library.

Covers the modules introduced during the OOP refactor:
    patientpunk._utils
    patientpunk.corpus
    patientpunk.schema
    patientpunk.extractors.base
    patientpunk.extractors.biomedical / llm / discovery / demographics
    patientpunk.exporters.base / csv_exporter / codebook
    patientpunk.pipeline
    patientpunk.qualitative_standards

No API calls are made — all tests use pure functions, in-memory data, or
mocked subprocesses.

Run with:
    cd Scrapers/demographic_extraction
    python -m pytest tests/ -v
"""

import csv
import json
import sys
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Make the package importable from the test runner's working directory
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent))

from patientpunk._utils import (
    clean_temp_dir,
    csv_fill_rate,
    find_newest_glob,
    get_schema_id,
    load_json,
)
from patientpunk.corpus import CorpusLoader, CorpusRecord
from patientpunk.schema import FieldDefinition, Schema
from patientpunk.extractors.base import BaseExtractor, ExtractorError, ExtractorResult
from patientpunk.extractors.biomedical import BiomedicalExtractor
from patientpunk.extractors.llm import LLMExtractor
from patientpunk.extractors.discovery import FieldDiscoveryExtractor
from patientpunk.extractors.demographics import DemographicsExtractor
from patientpunk.exporters.csv_exporter import CSVExporter
from patientpunk.exporters.codebook import CodebookGenerator
from patientpunk.pipeline import Pipeline, PipelineConfig, PipelineResult, PhaseResult
from patientpunk.qualitative_standards import (
    DEMOGRAPHIC_STANDARDS,
    EXTRACTION_STANDARDS,
    FIELD_DESIGN_STANDARDS,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"
BASE_SCHEMA = SCHEMAS_DIR / "base_schema.json"
EXT_SCHEMA = SCHEMAS_DIR / "covidlonghaulers_schema.json"


@pytest.fixture
def tmp_corpus(tmp_path):
    """Create a minimal corpus directory with posts and a user file."""
    # subreddit_posts.json
    posts = [
        {
            "author_hash": "aaa111",
            "post_id": "post_1",
            "title": "25M with long covid",
            "body": "I have POTS and brain fog.",
            "comments": [
                {"body": "Same here."},
                {"body": ""},
                {"body": "[removed]"},
            ],
        },
        {
            "author_hash": "bbb222",
            "post_id": "post_2",
            "title": "Looking for advice",
            "body": "[deleted]",
            "comments": [],
        },
        {
            "author_hash": None,
            "post_id": "post_3",
            "title": "Removed post",
            "body": "",
            "comments": [],
        },
    ]
    (tmp_path / "subreddit_posts.json").write_text(
        json.dumps(posts), encoding="utf-8"
    )

    # users/
    users_dir = tmp_path / "users"
    users_dir.mkdir()
    user = {
        "author_hash": "ccc333",
        "posts": [
            {"title": "My story", "body": "34F, diagnosed with POTS"},
            {"title": "Update", "body": ""},
        ],
        "comments": [
            {"body": "LDN helped my brain fog"},
            {"body": "[deleted]"},
        ],
    }
    (users_dir / "ccc333.json").write_text(
        json.dumps(user), encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def tmp_schema(tmp_path):
    """Create a minimal extension schema JSON file."""
    schema = {
        "schema_id": "test_v1",
        "_target_subreddit": "r/testsubreddit",
        "include_base_fields": ["dosage"],
        "extension_fields": {
            "test_field": {
                "description": "A test field",
                "confidence": "high",
                "patterns": [r"\btest\b"],
            }
        },
    }
    path = tmp_path / "test_schema.json"
    path.write_text(json.dumps(schema), encoding="utf-8")
    return path


@pytest.fixture
def tmp_csv(tmp_path):
    """Create a minimal CSV file for fill-rate testing."""
    csv_path = tmp_path / "records.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["author_hash", "age", "sex_gender", "conditions"])
        writer.writerow(["aaa111", "25", "male", "POTS"])
        writer.writerow(["bbb222", "", "", ""])
        writer.writerow(["ccc333", "34", "female", "POTS | brain fog"])
    return csv_path


# =============================================================================
# _utils
# =============================================================================

class TestLoadJson:
    def test_valid_json(self, tmp_path):
        p = tmp_path / "data.json"
        p.write_text('{"key": "value"}', encoding="utf-8")
        assert load_json(p) == {"key": "value"}

    def test_valid_json_list(self, tmp_path):
        p = tmp_path / "data.json"
        p.write_text('[1, 2, 3]', encoding="utf-8")
        assert load_json(p) == [1, 2, 3]

    def test_nonexistent_file_returns_none(self, tmp_path):
        assert load_json(tmp_path / "missing.json") is None

    def test_invalid_json_returns_none(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        assert load_json(p) is None

    def test_empty_file_returns_none(self, tmp_path):
        p = tmp_path / "empty.json"
        p.write_text("", encoding="utf-8")
        assert load_json(p) is None


class TestGetSchemaId:
    def test_from_json(self, tmp_path):
        p = tmp_path / "schema.json"
        p.write_text('{"schema_id": "my_schema_v2"}', encoding="utf-8")
        assert get_schema_id(p) == "my_schema_v2"

    def test_fallback_to_stem(self, tmp_path):
        p = tmp_path / "fallback_name.json"
        p.write_text('{"no_id_here": true}', encoding="utf-8")
        assert get_schema_id(p) == "fallback_name"

    def test_nonexistent_file_returns_stem(self, tmp_path):
        p = tmp_path / "nofile.json"
        assert get_schema_id(p) == "nofile"


class TestFindNewestGlob:
    def test_finds_latest(self, tmp_path):
        (tmp_path / "data_001.json").write_text("{}", encoding="utf-8")
        (tmp_path / "data_002.json").write_text("{}", encoding="utf-8")
        (tmp_path / "data_003.json").write_text("{}", encoding="utf-8")
        result = find_newest_glob(tmp_path, "data_*.json")
        assert result is not None
        assert result.name == "data_003.json"

    def test_no_match_returns_none(self, tmp_path):
        assert find_newest_glob(tmp_path, "nothing_*.json") is None

    def test_nonexistent_dir_returns_none(self, tmp_path):
        assert find_newest_glob(tmp_path / "nope", "*.json") is None


class TestCleanTempDir:
    def test_removes_matching_files(self, tmp_path):
        (tmp_path / "records_v1.json").write_text("{}", encoding="utf-8")
        (tmp_path / "records_v2.json").write_text("{}", encoding="utf-8")
        (tmp_path / "keep_me.txt").write_text("safe", encoding="utf-8")
        removed = clean_temp_dir(tmp_path, ["records_*.json"])
        assert len(removed) == 2
        assert (tmp_path / "keep_me.txt").exists()
        assert not (tmp_path / "records_v1.json").exists()

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        assert clean_temp_dir(tmp_path / "nope", ["*.json"]) == []

    def test_no_matches_returns_empty(self, tmp_path):
        (tmp_path / "file.txt").write_text("hi", encoding="utf-8")
        assert clean_temp_dir(tmp_path, ["*.json"]) == []


class TestCsvFillRate:
    def test_basic_fill_rate(self, tmp_csv):
        stats = csv_fill_rate(tmp_csv)
        assert stats["rows"] == 3
        assert stats["columns"] == 4
        assert stats["total_cells"] == 12
        # Row 1: 4/4 filled, Row 2: 1/4 filled, Row 3: 4/4 filled = 9/12
        assert stats["filled_cells"] == 9
        assert stats["fill_rate"] == 75.0

    def test_nonexistent_csv_returns_empty(self, tmp_path):
        assert csv_fill_rate(tmp_path / "no.csv") == {}

    def test_empty_csv_returns_empty(self, tmp_path):
        p = tmp_path / "empty.csv"
        p.write_text("col1,col2\n", encoding="utf-8")
        assert csv_fill_rate(p) == {}


# =============================================================================
# corpus
# =============================================================================

class TestCorpusRecord:
    def test_full_text(self):
        rec = CorpusRecord(
            author_hash="abc",
            source="test",
            post_id="p1",
            texts=["Hello", "World"],
        )
        assert rec.full_text == "Hello\n\nWorld"

    def test_repr(self):
        rec = CorpusRecord(
            author_hash="abcdefghijklmnop",
            source="subreddit_post",
            post_id="p1",
            texts=["a", "b", "c"],
        )
        r = repr(rec)
        assert "subreddit_post" in r
        assert "texts=3" in r
        # Only first 10 chars of hash shown
        assert "abcdefghij" in r


class TestCorpusLoader:
    def test_iter_records_all(self, tmp_corpus):
        loader = CorpusLoader(tmp_corpus)
        records = list(loader.iter_records())
        # 3 posts + 1 user = 4
        assert len(records) == 4

    def test_iter_records_posts_only(self, tmp_corpus):
        loader = CorpusLoader(tmp_corpus)
        records = list(loader.iter_records(include_users=False))
        assert all(r.source == "subreddit_post" for r in records)
        assert len(records) == 3

    def test_iter_records_users_only(self, tmp_corpus):
        loader = CorpusLoader(tmp_corpus)
        records = list(loader.iter_records(include_posts=False))
        assert all(r.source == "user_history" for r in records)
        assert len(records) == 1

    def test_iter_records_limit(self, tmp_corpus):
        loader = CorpusLoader(tmp_corpus)
        records = list(loader.iter_records(limit=2))
        assert len(records) == 2

    def test_load_all(self, tmp_corpus):
        loader = CorpusLoader(tmp_corpus)
        records = loader.load_all()
        assert isinstance(records, list)
        assert len(records) == 4

    def test_post_count(self, tmp_corpus):
        loader = CorpusLoader(tmp_corpus)
        assert loader.post_count == 3

    def test_user_count(self, tmp_corpus):
        loader = CorpusLoader(tmp_corpus)
        assert loader.user_count == 1

    def test_record_count(self, tmp_corpus):
        loader = CorpusLoader(tmp_corpus)
        assert loader.record_count == 4

    def test_empty_corpus(self, tmp_path):
        loader = CorpusLoader(tmp_path)
        assert loader.post_count == 0
        assert loader.user_count == 0
        assert loader.record_count == 0

    def test_texts_from_post_filters_removed(self, tmp_corpus):
        loader = CorpusLoader(tmp_corpus)
        records = list(loader.iter_records(include_users=False))
        first = records[0]
        # Title + body + first comment ("Same here.") but NOT empty or [removed]
        assert "25M with long covid" in first.texts
        assert "I have POTS and brain fog." in first.texts
        assert "Same here." in first.texts
        assert "" not in first.texts
        assert "[removed]" not in first.texts

    def test_texts_from_post_filters_deleted(self, tmp_corpus):
        loader = CorpusLoader(tmp_corpus)
        records = list(loader.iter_records(include_users=False))
        second = records[1]
        # Title only; body is "[deleted]" and should be excluded
        assert "Looking for advice" in second.texts
        assert "[deleted]" not in second.texts

    def test_null_author_hash(self, tmp_corpus):
        loader = CorpusLoader(tmp_corpus)
        records = list(loader.iter_records(include_users=False))
        third = records[2]
        # Null author_hash → empty string
        assert third.author_hash == ""

    def test_texts_from_user(self, tmp_corpus):
        loader = CorpusLoader(tmp_corpus)
        records = list(loader.iter_records(include_posts=False))
        user_rec = records[0]
        assert "My story" in user_rec.texts
        assert "34F, diagnosed with POTS" in user_rec.texts
        assert "LDN helped my brain fog" in user_rec.texts
        assert "[deleted]" not in user_rec.texts
        assert "" not in user_rec.texts

    def test_corrupt_user_file_skipped_with_warning(self, tmp_corpus):
        """A malformed user JSON should be skipped with a warning, not crash."""
        bad_file = tmp_corpus / "users" / "bad_user.json"
        bad_file.write_text("{not valid json", encoding="utf-8")
        loader = CorpusLoader(tmp_corpus)
        # Should still load the one good user file without error
        records = list(loader.iter_records(include_posts=False))
        assert len(records) == 1
        assert records[0].author_hash == "ccc333"


# =============================================================================
# schema
# =============================================================================

class TestFieldDefinition:
    def test_repr(self):
        fd = FieldDefinition(
            name="age",
            description="Patient age",
            confidence="medium",
            source="base",
            patterns=[r"\d+"],
        )
        r = repr(fd)
        assert "age" in r
        assert "base" in r
        assert "medium" in r
        assert "patterns=1" in r

    def test_frozen(self):
        fd = FieldDefinition(
            name="age",
            description="Patient age",
            confidence="medium",
            source="base",
        )
        with pytest.raises(AttributeError):
            fd.name = "new_name"


@pytest.mark.skipif(not EXT_SCHEMA.exists(), reason="Schema file not found")
class TestSchema:
    def test_from_file(self):
        schema = Schema.from_file(EXT_SCHEMA)
        assert schema.schema_id == "covidlonghaulers_v1"
        assert schema.target_subreddit is not None
        assert len(schema.all_fields) > 0

    def test_base_and_extension_counts(self):
        schema = Schema.from_file(EXT_SCHEMA)
        assert len(schema.base_fields) > 0
        assert len(schema.extension_fields) > 0
        assert len(schema.all_fields) == len(schema.base_fields) + len(schema.extension_fields)

    def test_field_names_all(self):
        schema = Schema.from_file(EXT_SCHEMA)
        names = schema.field_names()
        assert isinstance(names, list)
        assert len(names) == len(schema.all_fields)

    def test_field_names_filtered(self):
        schema = Schema.from_file(EXT_SCHEMA)
        ext_names = schema.field_names(source="extension")
        assert all(
            schema.all_fields[n].source == "extension" for n in ext_names
        )

    def test_to_dict(self):
        schema = Schema.from_file(EXT_SCHEMA)
        d = schema.to_dict()
        assert isinstance(d, dict)
        assert "schema_id" in d

    def test_repr(self):
        schema = Schema.from_file(EXT_SCHEMA)
        r = repr(schema)
        assert "covidlonghaulers_v1" in r

    def test_extension_fields_have_patterns(self):
        schema = Schema.from_file(EXT_SCHEMA)
        for name, fd in schema.extension_fields.items():
            # All extension fields in the real schema have patterns
            assert isinstance(fd.patterns, list)


class TestSchemaWarning:
    def test_warns_when_base_schema_missing(self, tmp_schema, tmp_path):
        """Schema.from_file() should warn when base_schema.json is absent."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            schema = Schema.from_file(
                tmp_schema,
                base_path=tmp_path / "nonexistent_base.json",
            )
            assert len(w) == 1
            assert "Base schema not found" in str(w[0].message)
        # Extension fields should still load
        assert "test_field" in schema.extension_fields

    def test_no_warning_when_base_present(self, tmp_schema, tmp_path):
        """No warning when a valid base schema exists."""
        base = tmp_path / "base.json"
        base.write_text('{"fields": {}}', encoding="utf-8")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Schema.from_file(tmp_schema, base_path=base)
            base_warnings = [x for x in w if "Base schema" in str(x.message)]
            assert len(base_warnings) == 0


class TestSchemaFromMinimalFile:
    def test_minimal_extension_schema(self, tmp_schema, tmp_path):
        base = tmp_path / "base.json"
        base.write_text('{"fields": {"age": {"description": "Age", "confidence": "medium"}}}',
                        encoding="utf-8")
        schema = Schema.from_file(tmp_schema, base_path=base)
        assert schema.schema_id == "test_v1"
        assert "age" in schema.base_fields
        assert "test_field" in schema.extension_fields
        assert schema.target_subreddit == "r/testsubreddit"

    def test_base_optional_activation(self, tmp_path):
        """Only base_optional fields listed in include_base_fields are kept."""
        base = tmp_path / "base.json"
        base.write_text(json.dumps({
            "fields": {"age": {"description": "Age", "confidence": "medium"}},
            "base_optional_fields": {
                "dosage": {"description": "Medication dosage", "confidence": "low"},
                "ethnicity": {"description": "Ethnicity", "confidence": "low"},
            },
        }), encoding="utf-8")

        ext = tmp_path / "ext.json"
        ext.write_text(json.dumps({
            "schema_id": "activation_test",
            "include_base_fields": ["dosage"],  # only activate dosage
            "extension_fields": {},
        }), encoding="utf-8")

        schema = Schema.from_file(ext, base_path=base)
        assert "age" in schema.base_fields          # always present
        assert "dosage" in schema.base_fields        # activated
        assert "ethnicity" not in schema.base_fields  # not activated


# =============================================================================
# extractors — base class and argument building
# =============================================================================

class TestExtractorResult:
    def test_ok_property(self):
        assert ExtractorResult(returncode=0, elapsed=1.0).ok is True
        assert ExtractorResult(returncode=1, elapsed=1.0).ok is False

    def test_stdout_stderr_default_none(self):
        r = ExtractorResult(returncode=0, elapsed=1.0)
        assert r.stdout is None
        assert r.stderr is None

    def test_stdout_stderr_populated(self):
        r = ExtractorResult(
            returncode=0, elapsed=1.0,
            stdout="output line\n", stderr="warning\n",
        )
        assert r.stdout == "output line\n"
        assert r.stderr == "warning\n"


class TestExtractorError:
    def test_message_format(self):
        exc = ExtractorError("BiomedicalExtractor", 1)
        assert "BiomedicalExtractor" in str(exc)
        assert "1" in str(exc)
        assert exc.extractor == "BiomedicalExtractor"
        assert exc.returncode == 1


class TestBiomedicalExtractorArgs:
    def test_basic_args(self, tmp_path):
        ext = BiomedicalExtractor(
            input_dir=tmp_path / "input",
            schema_path=tmp_path / "schema.json",
            temp_dir=tmp_path / "temp",
        )
        args = ext._build_args()
        assert "--input-dir" in args
        assert "--schema" in args
        assert "--temp-dir" in args

    def test_no_schema(self, tmp_path):
        ext = BiomedicalExtractor(input_dir=tmp_path)
        args = ext._build_args()
        assert "--schema" not in args

    def test_default_temp_dir(self, tmp_path):
        ext = BiomedicalExtractor(input_dir=tmp_path / "input")
        assert ext.temp_dir == tmp_path / "input" / "temp"


class TestLLMExtractorArgs:
    def test_all_options(self, tmp_path):
        ext = LLMExtractor(
            input_dir=tmp_path,
            schema_path=tmp_path / "s.json",
            workers=5,
            skip_threshold=0.5,
            focus_gaps=False,
            merge=False,
            resume=True,
            limit=20,
        )
        args = ext._build_args()
        assert "--workers" in args
        assert "5" in args
        assert "--skip-threshold" in args
        assert "0.5" in args
        assert "--no-focus-gaps" in args
        assert "--no-merge" in args
        assert "--resume" in args
        assert "--limit" in args
        assert "20" in args

    def test_defaults(self, tmp_path):
        ext = LLMExtractor(input_dir=tmp_path)
        args = ext._build_args()
        # Default focus_gaps=True → no --no-focus-gaps
        assert "--no-focus-gaps" not in args
        # Default merge=True → no --no-merge
        assert "--no-merge" not in args
        assert "--resume" not in args
        assert "--limit" not in args


class TestFieldDiscoveryArgs:
    def test_all_options(self, tmp_path):
        ext = FieldDiscoveryExtractor(
            input_dir=tmp_path,
            schema_path=tmp_path / "s.json",
            workers=3,
            limit=10,
            fill_gaps=False,
            resume=True,
            sample=50,
            per_item_chars=3000,
        )
        args = ext._build_args()
        assert "--workers" in args
        assert "3" in args
        assert "--limit" in args
        assert "10" in args
        assert "--no-fill" in args
        assert "--resume" in args
        assert "--sample" in args
        assert "50" in args
        assert "--per-item-chars" in args
        assert "3000" in args

    def test_auto_candidates_detection(self, tmp_path):
        """If phase1_candidates.json exists in temp_dir, auto-detect it."""
        temp = tmp_path / "temp"
        temp.mkdir()
        cand = temp / "phase1_candidates.json"
        cand.write_text("[]", encoding="utf-8")

        ext = FieldDiscoveryExtractor(
            input_dir=tmp_path,
            temp_dir=temp,
        )
        args = ext._build_args()
        assert "--candidates" in args
        assert str(cand) in args


class TestDemographicsExtractorArgs:
    def test_all_options(self, tmp_path):
        ext = DemographicsExtractor(
            input_dir=tmp_path,
            output_path=tmp_path / "out.csv",
            workers=5,
            include_posts=True,
            include_users=False,
            max_chars=4000,
        )
        args = ext._build_args()
        assert "--output" in args
        assert "--workers" in args
        assert "5" in args
        assert "--max-chars" in args
        assert "4000" in args
        assert "--posts-only" in args
        assert "--users-only" not in args

    def test_users_only(self, tmp_path):
        ext = DemographicsExtractor(
            input_dir=tmp_path,
            include_posts=False,
            include_users=True,
        )
        args = ext._build_args()
        assert "--users-only" in args
        assert "--posts-only" not in args

    def test_both_sources_default(self, tmp_path):
        ext = DemographicsExtractor(input_dir=tmp_path)
        args = ext._build_args()
        assert "--posts-only" not in args
        assert "--users-only" not in args


class TestBaseExtractorRepr:
    def test_repr(self, tmp_path):
        ext = BiomedicalExtractor(
            input_dir=tmp_path / "input",
            schema_path=tmp_path / "schema.json",
        )
        r = repr(ext)
        assert "BiomedicalExtractor" in r
        assert "input" in r


class TestBaseExtractorCaptureOutput:
    """Test that capture_output=True routes stdout/stderr to ExtractorResult."""

    def test_capture_output(self, tmp_path):
        ext = BiomedicalExtractor(input_dir=tmp_path)
        # Mock subprocess.run to avoid running the actual script
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "hello from stdout\n"
        mock_proc.stderr = ""

        with patch("patientpunk.extractors.base.subprocess.run", return_value=mock_proc):
            result = ext.run(capture_output=True)

        assert result.ok
        assert result.stdout == "hello from stdout\n"
        assert result.stderr == ""

    def test_no_capture_default(self, tmp_path):
        ext = BiomedicalExtractor(input_dir=tmp_path)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = None
        mock_proc.stderr = None

        with patch("patientpunk.extractors.base.subprocess.run", return_value=mock_proc):
            result = ext.run(capture_output=False)

        assert result.stdout is None
        assert result.stderr is None

    def test_raise_on_error(self, tmp_path):
        ext = BiomedicalExtractor(input_dir=tmp_path)
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = None
        mock_proc.stderr = None

        with patch("patientpunk.extractors.base.subprocess.run", return_value=mock_proc):
            with pytest.raises(ExtractorError) as exc_info:
                ext.run(raise_on_error=True)
            assert exc_info.value.returncode == 1

    def test_no_raise_on_error(self, tmp_path):
        ext = BiomedicalExtractor(input_dir=tmp_path)
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = None
        mock_proc.stderr = None

        with patch("patientpunk.extractors.base.subprocess.run", return_value=mock_proc):
            result = ext.run(raise_on_error=False)
            assert not result.ok
            assert result.returncode == 1


# =============================================================================
# exporters — argument building
# =============================================================================

class TestCSVExporterArgs:
    def test_basic_args(self, tmp_path):
        f1 = tmp_path / "records1.json"
        f2 = tmp_path / "records2.json"
        exp = CSVExporter(
            input_files=[f1, f2],
            output_path=tmp_path / "out.csv",
            sep=" | ",
            include_provenance=True,
        )
        args = exp._build_args()
        assert "--input" in args
        assert str(f1) in args
        assert str(f2) in args
        assert "--output" in args
        assert "--provenance" in args
        assert "--sep" in args

    def test_requires_input_files(self):
        with pytest.raises(ValueError, match="at least one input"):
            CSVExporter(input_files=[])


class TestCodebookGeneratorArgs:
    def test_all_options(self, tmp_path):
        gen = CodebookGenerator(
            schema_path=tmp_path / "schema.json",
            records_csv=tmp_path / "records.csv",
            fmt="markdown",
            max_examples=10,
            include_discovered=False,
        )
        args = gen._build_args()
        assert "--schema" in args
        assert "--csv" in args
        assert "--format" in args
        assert "markdown" in args
        assert "--examples" in args
        assert "10" in args
        assert "--no-discovered" in args

    def test_default_csv_format(self, tmp_path):
        gen = CodebookGenerator(schema_path=tmp_path / "s.json")
        args = gen._build_args()
        assert "csv" in args
        assert "--no-discovered" not in args


# =============================================================================
# pipeline — config and result
# =============================================================================

class TestPipelineConfig:
    def test_defaults(self, tmp_path):
        cfg = PipelineConfig(schema_path=tmp_path / "s.json")
        assert cfg.start_at == 1
        assert cfg.run_llm is True
        assert cfg.run_discovery is True
        assert cfg.clean is True
        assert cfg.workers == 10
        assert cfg.temp_dir == cfg.input_dir / "temp"

    def test_invalid_start_at(self, tmp_path):
        with pytest.raises(ValueError, match="start_at must be 1"):
            PipelineConfig(schema_path=tmp_path / "s.json", start_at=0)
        with pytest.raises(ValueError, match="start_at must be 1"):
            PipelineConfig(schema_path=tmp_path / "s.json", start_at=6)

    def test_custom_temp_dir(self, tmp_path):
        cfg = PipelineConfig(
            schema_path=tmp_path / "s.json",
            temp_dir=tmp_path / "custom_temp",
        )
        assert cfg.temp_dir == tmp_path / "custom_temp"

    def test_path_coercion(self, tmp_path):
        """String paths should be coerced to Path objects."""
        cfg = PipelineConfig(schema_path=str(tmp_path / "s.json"))
        assert isinstance(cfg.schema_path, Path)


class TestPhaseResult:
    def test_defaults(self):
        pr = PhaseResult(phase=1, label="Test")
        assert pr.ok is True
        assert pr.skipped is False
        assert pr.elapsed == 0.0


class TestPipelineResult:
    def test_ok_all_passed(self):
        result = PipelineResult(
            phases=[
                PhaseResult(phase=1, label="A", ok=True),
                PhaseResult(phase=2, label="B", ok=True),
            ]
        )
        assert result.ok

    def test_ok_with_skipped(self):
        result = PipelineResult(
            phases=[
                PhaseResult(phase=1, label="A", ok=True),
                PhaseResult(phase=2, label="B", skipped=True),
                PhaseResult(phase=3, label="C", ok=True),
            ]
        )
        assert result.ok

    def test_not_ok_when_failed(self):
        result = PipelineResult(
            phases=[
                PhaseResult(phase=1, label="A", ok=True),
                PhaseResult(phase=2, label="B", ok=False, error="1"),
            ]
        )
        assert not result.ok

    def test_summary_contains_phases(self):
        result = PipelineResult(
            phases=[
                PhaseResult(phase=1, label="Regex", ok=True, elapsed=5.0,
                            stats={"records": 100}),
                PhaseResult(phase=2, label="LLM", skipped=True),
            ],
            total_elapsed=5.0,
        )
        summary = result.summary()
        assert "PIPELINE SUMMARY" in summary
        assert "Regex" in summary
        assert "SKIPPED" in summary
        assert "records" in summary


# =============================================================================
# qualitative_standards
# =============================================================================

class TestQualitativeStandards:
    """Verify the shared qualitative standards constants are well-formed."""

    def test_field_design_contains_all_principles(self):
        for keyword in [
            "LEVELS OF MEASUREMENT",
            "MUTUALLY EXCLUSIVE",
            "OPERATIONALIZATION",
            "PARSIMONY",
            "DOUBLE-BARRELED",
            "CONSTRUCT VALIDITY",
            "UNIT OF OBSERVATION",
        ]:
            assert keyword in FIELD_DESIGN_STANDARDS, f"Missing: {keyword}"

    def test_extraction_standards_contains_core_principles(self):
        for keyword in [
            "OPERATIONALIZATION",
            "CONSTRUCT VALIDITY",
            "MUTUALLY EXCLUSIVE",
            "UNIT OF OBSERVATION",
        ]:
            assert keyword in EXTRACTION_STANDARDS, f"Missing: {keyword}"

    def test_demographic_standards_contains_core_principles(self):
        for keyword in [
            "SELF-REFERENCE ONLY",
            "CONSTRUCT VALIDITY",
            "CONFIDENCE CALIBRATION",
            "EVIDENCE CITATION",
        ]:
            assert keyword in DEMOGRAPHIC_STANDARDS, f"Missing: {keyword}"

    def test_standards_are_nonempty_strings(self):
        assert isinstance(FIELD_DESIGN_STANDARDS, str)
        assert isinstance(EXTRACTION_STANDARDS, str)
        assert isinstance(DEMOGRAPHIC_STANDARDS, str)
        assert len(FIELD_DESIGN_STANDARDS) > 500
        assert len(EXTRACTION_STANDARDS) > 300
        assert len(DEMOGRAPHIC_STANDARDS) > 300

    def test_standards_injected_into_llm_extract(self):
        """Verify EXTRACTION_STANDARDS actually appears in the LLM system prompt."""
        from old.llm_extract import build_system_prompt
        prompt = build_system_prompt({"age": "Patient age"})
        assert "OPERATIONALIZATION" in prompt
        assert "CONSTRUCT VALIDITY" in prompt

    def test_standards_injected_into_demographics(self):
        """Verify DEMOGRAPHIC_STANDARDS actually appears in the demographics prompt."""
        from old.extract_demographics_llm import SYSTEM_PROMPT
        assert "SELF-REFERENCE ONLY" in SYSTEM_PROMPT
        assert "CONFIDENCE CALIBRATION" in SYSTEM_PROMPT

    def test_standards_injected_into_discovery(self):
        """Verify FIELD_DESIGN_STANDARDS actually appears in the discovery prompt."""
        from old.discover_fields import build_discovery_prompt
        prompt = build_discovery_prompt(["age", "sex_gender"])
        assert "PARSIMONY" in prompt
        assert "DOUBLE-BARRELED" in prompt
