"""Tests for the dose step: prompt, response parsing, and the report_doses writer. No API calls."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from pipeline.doses import (
    DoseContext,
    DoseValue,
    extract_batch,
    load_dose_contexts,
    make_batches,
    parse_dose_response,
    run_dose_extraction,
)
from prompts.dose_config import dose_system_prompt
from utilities import LLMParseError

POSTS = [
    ("top", None, "u1", "Dosing thread", "What dose do you all take?"),
    ("reply", "top", "u2", None, "I take 20mg sublingual, it is great. Tried 40 mg once, headache."),
    ("other", "top", "u1", None, "Never tried it."),
]
REPORTS = [("reply", "u2", "positive"), ("other", "u1", "neutral"), ("reply", "u2", "mixed")]  # 'reply' has two runs
REPLY_DOSES = [
    {"low": 20, "high": 20, "unit": "mg", "route": "oral mucosal", "outcome": "positive", "quote": "I take 20mg sublingual, it is great."},
    {"low": 40, "high": 40, "unit": "mg", "outcome": "negative", "quote": "Tried 40 mg once, headache."},
]


def doses_for(items: list[dict], doses: list[dict]) -> list[dict]:
    """Reply with ``doses`` for the 20mg report and nothing for the others."""
    return [{"item_id": it["item_id"], "doses": doses if "20mg" in it["report"] else []} for it in items]


@pytest.fixture
def dose_db(schema_db: Path, seed_reports) -> Path:
    seed_reports(schema_db, POSTS, REPORTS)
    return schema_db


def test_prompt_renders_name_aliases_and_exclusions() -> None:
    prompt = dose_system_prompt("7,8-dhf", ["tropoflavin", "78dhf", "7,8-DHF"], ["4'-DMA-7,8-DHF"])
    assert "doses of 7,8-dhf" in prompt
    assert "7,8-dhf is also written: tropoflavin, 78dhf." in prompt  # the name itself is not repeated
    assert "Do not assign information about 4'-DMA-7,8-DHF to 7,8-dhf" in prompt
    bare = dose_system_prompt("ldn")
    assert "also written" not in bare and "Do not assign information about" not in bare
    assert '"dose_sentences"' in bare and '"quote"' in bare


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"low": "20", "high": 20, "unit": "milligrams"}, (20.0, 20.0, "mg")),
        ({"low": 500, "high": 500, "unit": "ug"}, (500.0, 500.0, "mcg")),
        ({"low": 1, "high": 3, "unit": "grams"}, (1.0, 3.0, "g")),
        ({"low": 50, "high": 50, "unit": "mg/day"}, (50.0, 50.0, "mg")),
    ],
)
def test_dose_value_coerces_units_and_numbers(raw: dict, expected: tuple) -> None:
    dose = DoseValue.model_validate(raw)
    assert (dose.low, dose.high, dose.unit) == expected


def test_dose_value_keeps_known_labels_and_drops_unknown_ones() -> None:
    known = DoseValue.model_validate({"low": 1, "high": 1, "unit": "mg", "route": "oral mucosal", "outcome": "negative", "quote": "  1mg  "})
    assert (known.route, known.outcome, known.quote) == ("oral mucosal", "negative", "1mg")
    unknown = DoseValue.model_validate({"low": 1, "high": 1, "unit": "mg", "route": "snorted", "outcome": "great", "quote": " "})
    assert (unknown.route, unknown.outcome, unknown.quote) == (None, None, None)


@pytest.mark.parametrize(
    "raw",
    [
        {"low": 20, "high": 10, "unit": "mg"},  # high below low
        {"low": 2, "high": 2, "unit": "mg/kg"},  # per-kilogram is not a dose
        {"low": "twenty", "high": 20, "unit": "mg"},
        {"low": 5, "high": 5, "unit": "drops"},
    ],
)
def test_dose_value_rejects_invalid_values(raw: dict) -> None:
    with pytest.raises(ValidationError):
        DoseValue.model_validate(raw)


def test_parse_response_deduplicates_and_drops_invalid_doses() -> None:
    dose = {"low": 10, "high": 20, "unit": "mg", "outcome": "positive", "quote": "10-20mg works"}
    raw = json.dumps([
        {"item_id": 0, "dose_sentences": ["x"], "doses": [dose, dose, {"low": 5, "high": 5, "unit": "drops"}]},
        {"item_id": 1, "doses": []},
    ])
    per_item, dropped = parse_dose_response(raw, [0, 1])
    assert dropped == 1
    assert [d.low for d in per_item[0]] == [10.0] and per_item[1] == []


def test_parse_response_rejects_mismatched_ids_and_non_json() -> None:
    raw = json.dumps([{"item_id": 0, "doses": []}, {"item_id": 1, "doses": []}])
    with pytest.raises(LLMParseError, match="do not match"):
        parse_dose_response(raw, [0, 2])
    with pytest.raises(LLMParseError):
        parse_dose_response("no json here", [0])


def test_contexts_take_latest_report_per_post_with_parent_context(dose_db: Path) -> None:
    with sqlite3.connect(dose_db) as conn:
        contexts = load_dose_contexts(conn, "7,8-DHF", parent_chars=12)
    assert [(c.post_id, c.report_id) for c in contexts] == [("other", 2), ("reply", 3)]
    assert contexts[1].text.startswith("I take 20mg") and contexts[1].replying_to == "Dosing threa"
    assert make_batches(contexts, batch_size=8, solo_above_chars=20) == [[contexts[0]], [contexts[1]]]


def test_run_writes_one_row_per_dose_and_records_the_run(dose_db: Path, stub_llm) -> None:
    stub_llm.reply(lambda items: doses_for(items, REPLY_DOSES))
    summary = run_dose_extraction(None, dose_db, "7,8-dhf", excluded_compounds=["4'-DMA-7,8-DHF"], workers=1)

    assert (summary.reports, summary.reports_with_doses, summary.dose_rows, summary.failed_reports) == (2, 1, 2, 0)
    assert any("replying_to" in item for payload in stub_llm.payloads for item in payload["items"])
    with sqlite3.connect(dose_db) as conn:
        rows = conn.execute(
            "SELECT report_id, ordinal, post_id, user_id, drug_id, low, high, unit, route, outcome, quote "
            "FROM report_doses ORDER BY ordinal"
        ).fetchall()
        run_type, config = conn.execute("SELECT extraction_type, config FROM extraction_runs WHERE run_id = ?", (summary.run_id,)).fetchone()
    assert rows == [
        (3, 1, "reply", "u2", 1, 20.0, 20.0, "mg", "oral mucosal", "positive", "I take 20mg sublingual, it is great."),
        (3, 2, "reply", "u2", 1, 40.0, 40.0, "mg", None, "negative", "Tried 40 mg once, headache."),
    ]
    config = json.loads(config)
    assert run_type == "report_doses" and config["drug"] == "7,8-dhf" and config["aliases"] == ["tropoflavin"]
    assert config["excluded_compounds"] == ["4'-DMA-7,8-DHF"] and len(config["prompt_sha256"]) == 64


def test_rerun_replaces_a_reports_rows_instead_of_appending(dose_db: Path, stub_llm) -> None:
    stub_llm.reply(lambda items: doses_for(items, REPLY_DOSES))
    run_dose_extraction(None, dose_db, "7,8-dhf", workers=1)
    stub_llm.reply(lambda items: doses_for(items, [{"low": 25, "high": 25, "unit": "mg", "quote": "q"}]))
    second = run_dose_extraction(None, dose_db, "7,8-dhf", workers=1)

    with sqlite3.connect(dose_db) as conn:
        rows = conn.execute("SELECT run_id, low FROM report_doses").fetchall()
        runs = conn.execute("SELECT COUNT(*) FROM extraction_runs WHERE extraction_type = 'report_doses'").fetchone()[0]
    assert rows == [(second.run_id, 25.0)] and runs == 2


def test_malformed_batch_is_split_down_to_single_items(stub_llm) -> None:
    stub_llm.reply(lambda items: "garbage" if len(items) > 1 else [{"item_id": 0, "doses": [{"low": 1, "high": 1, "unit": "mg"}]}])
    batch = [DoseContext(i, f"p{i}", None, 1, "1mg", "") for i in range(4)]

    results, dropped = extract_batch(None, batch, "sys", "model")

    assert sorted(results) == [0, 1, 2, 3] and dropped == 0
    assert [len(p["items"]) for p in stub_llm.payloads] == [4, 2, 1, 1, 2, 1, 1]
