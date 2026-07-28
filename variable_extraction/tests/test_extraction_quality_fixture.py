"""The eval fixture must hold exactly the text production feeds the model.

It once held title + body + every comment while its gold labels came from a
title+body-only run, so the harness scored the model on input three to eight
times longer than the text the labels describe -- inflating "the model
hallucinated" by 30 spurious mismatches and inventing a multi-speaker
attribution failure mode that production cannot produce. These tests pin the
invariant so that drift cannot return silently.

Skipped when the source corpus (a 76MB gitignored artifact) is absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from patientpunk._utils import collect_texts_from_post
from patientpunk.llm_extract import build_field_descriptions

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "extraction_quality" / "fixtures"
FIXTURE_PATHS = sorted(FIXTURE_DIR.glob("*.json"))
assert FIXTURE_PATHS, f"no fixtures found in {FIXTURE_DIR}"


@pytest.fixture(params=FIXTURE_PATHS, ids=lambda p: p.name)
def fixture(request) -> dict:
    return json.loads(request.param.read_text())


def _corpus(fixture: dict) -> dict[str, dict]:
    path = PROJECT_ROOT.parent / fixture["source_corpus"]
    if not path.exists():
        pytest.skip(f"source corpus not available: {path}")
    return {p["post_id"]: p for p in json.loads(path.read_text())}


def test_texts_match_the_production_collection_path(fixture):
    """Every record's `texts` is what CorpusLoader would hand the extractor."""
    by_id = _corpus(fixture)
    for rec in fixture["records"]:
        post = by_id[rec["post_id"]]
        expected = [
            t.strip()
            for t in collect_texts_from_post(post, include_comments=False)
            if t and t.strip() not in ("[removed]", "[deleted]")
        ]
        assert rec["texts"] == expected, (
            f"{rec['post_id']}: fixture texts diverge from the production path. "
            "Comments must NOT be included -- they are other users' words."
        )


def test_post_ids_are_unique(fixture):
    ids = [r["post_id"] for r in fixture["records"]]
    assert len(ids) == len(set(ids))


def test_gold_fields_are_all_scoreable(fixture):
    """A gold value in a field outside the fixture's schema is never scored."""
    schema = json.loads((PROJECT_ROOT / fixture["schema"]).read_text())
    known = set(build_field_descriptions(schema))
    for rec in fixture["records"]:
        unknown = set(rec["gold"]) - known
        assert not unknown, f"{rec['post_id']}: gold fields outside the schema: {unknown}"
