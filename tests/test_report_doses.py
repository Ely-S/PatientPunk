"""Dose step: prompt, parsing, and the report_doses writer. The model call is stubbed; nothing is sent anywhere."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import pipeline.doses as doses_module
from pipeline.doses import normalize_unit, parse_dose_response, run_dose_extraction
from prompts.dose_config import dose_system_prompt
from utilities import LLMParseError

SCHEMA_SQL = Path(__file__).parent.parent / "schema.sql"

REPLY_DOSES = [
    {"low": 20, "high": 20, "unit": "mg", "route": "oral mucosal", "outcome": "positive", "quote": "I take 20mg sublingual, it is great."},
    {"low": 40, "high": 40, "unit": "mg", "outcome": "negative", "quote": "Tried 40 mg once, headache."},
]


def test_prompt_and_response_parsing() -> None:
    prompt = dose_system_prompt("7,8-dhf", ["tropoflavin", "78dhf", "7,8-DHF"], ["4'-DMA-7,8-DHF"])
    assert "doses of 7,8-dhf" in prompt
    assert "7,8-dhf is also written: tropoflavin, 78dhf." in prompt  # the name itself is not repeated
    assert "Do not assign information about 4'-DMA-7,8-DHF to 7,8-dhf" in prompt
    assert "also written" not in dose_system_prompt("ldn")

    raw = json.dumps([
        {"item_id": 0, "dose_sentences": ["x"], "doses": [
            {"low": "20", "high": 20, "unit": "milligrams", "route": "snorted", "outcome": "great", "quote": " 20mg "},
            {"low": 1.5, "high": 1.5, "unit": None},         # bare number, unit unknown
            {"low": 2, "high": 2, "unit": "capsules"},       # any unit is kept as written
            {"low": 2, "high": 2, "unit": "mg/kg"},
            {"low": 1, "high": 3, "unit": "grams"},
            {"low": 1, "high": 3, "unit": "grams"},          # duplicate
            {"low": 20, "high": 10, "unit": "mg"},           # high below low
            {"low": "twenty", "high": 20, "unit": "mg"},     # not a number
        ]},
        {"item_id": 1, "doses": []},
    ])
    per_item, dropped = parse_dose_response(raw, [0, 1])
    assert dropped == 2 and per_item[1] == []
    assert [(d.low, d.high, d.unit, d.route, d.outcome, d.quote) for d in per_item[0]] == [
        (20.0, 20.0, "milligrams", None, None, "20mg"),
        (1.5, 1.5, None, None, None, None),
        (2.0, 2.0, "capsules", None, None, None),
        (2.0, 2.0, "mg/kg", None, None, None),
        (1.0, 3.0, "grams", None, None, None),
    ]
    assert [normalize_unit(u) for u in ("milligrams", "mL", "IU", "capsules", None)] == ["mg", "ml", "iu", None, None]
    with pytest.raises(LLMParseError, match="do not match"):
        parse_dose_response(raw, [0, 2])


def test_run_writes_one_row_per_dose_and_a_rerun_replaces_them(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payloads: list[dict] = []
    respond = {"fn": lambda items: []}

    def stub_llm(client, prompt, model=None, system=None, max_tokens=0) -> str:  # stands in for the model call
        payloads.append(json.loads(prompt))
        return json.dumps(respond["fn"](payloads[-1]["items"]))

    monkeypatch.setattr(doses_module, "llm_call", stub_llm)
    schema_db = tmp_path / "study.db"
    with sqlite3.connect(schema_db) as conn:
        conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
        conn.executescript("""
            INSERT INTO users VALUES ('u1', 'test', 0), ('u2', 'test', 0);
            INSERT INTO posts (post_id, parent_id, user_id, title, body_text, scraped_at) VALUES
                ('top', NULL, 'u1', 'Dosing thread', 'What dose do you all take?', 0),
                ('reply', 'top', 'u2', NULL, 'I take 20mg sublingual, it is great. Tried 40 mg once, headache.', 0),
                ('other', 'top', 'u1', NULL, 'Never tried it.', 0);
            INSERT INTO treatment (id, canonical_name, aliases) VALUES (1, '7,8-dhf', '["tropoflavin"]');
            INSERT INTO extraction_runs VALUES (1, 0, 'abc', 'treatment_sentiment', '{}');
            INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength) VALUES
                (1, 'reply', 'u2', 1, 'positive', 'strong'), (1, 'other', 'u1', 1, 'neutral', 'strong'),
                (1, 'reply', 'u2', 1, 'mixed', 'strong');  -- 'reply' classified twice; the latest report wins
        """)
    respond["fn"] = lambda items: [{"item_id": it["item_id"], "doses": REPLY_DOSES if "20mg" in it["report"] else []} for it in items]

    first = run_dose_extraction(None, schema_db, "7,8-dhf", excluded_compounds=["4'-DMA-7,8-DHF"], workers=1)

    assert (first.reports, first.reports_with_doses, first.dose_rows, first.failed_reports) == (2, 1, 2, 0)
    assert all(it["replying_to"] == "Dosing thread What dose do you all take?" for it in payloads[0]["items"])
    with sqlite3.connect(schema_db) as conn:
        rows = conn.execute("SELECT report_id, ordinal, post_id, user_id, drug_id, low, high, unit, route, outcome, quote FROM report_doses ORDER BY ordinal").fetchall()
        run_type, config = conn.execute("SELECT extraction_type, config FROM extraction_runs WHERE run_id = ?", (first.run_id,)).fetchone()
    assert rows == [
        (3, 1, "reply", "u2", 1, 20.0, 20.0, "mg", "oral mucosal", "positive", "I take 20mg sublingual, it is great."),
        (3, 2, "reply", "u2", 1, 40.0, 40.0, "mg", None, "negative", "Tried 40 mg once, headache."),
    ]
    assert run_type == "report_doses" and json.loads(config)["excluded_compounds"] == ["4'-DMA-7,8-DHF"]

    respond["fn"] = lambda items: [{"item_id": it["item_id"], "doses": [{"low": 25, "high": 25, "unit": "mg", "quote": "q"}] if "20mg" in it["report"] else []} for it in items]
    second = run_dose_extraction(None, schema_db, "7,8-dhf", workers=1)
    with sqlite3.connect(schema_db) as conn:
        assert conn.execute("SELECT run_id, low FROM report_doses").fetchall() == [(second.run_id, 25.0)]
