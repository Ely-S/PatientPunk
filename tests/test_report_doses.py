"""Tests for the dose step: prompt, response parsing, and the report_doses writer. No API calls."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

import pipeline.doses as doses_module
from pipeline.doses import (
    DoseValue,
    load_dose_contexts,
    make_batches,
    parse_dose_response,
    run_dose_extraction,
)
from prompts.dose_config import dose_system_prompt
from utilities import LLMParseError

SCHEMA_SQL = Path(__file__).parent.parent / "schema.sql"


def test_prompt_renders_name_aliases_and_exclusions() -> None:
    prompt = dose_system_prompt("7,8-dhf", ["tropoflavin", "78dhf", "7,8-DHF"], ["4'-DMA-7,8-DHF"])
    assert "doses of 7,8-dhf" in prompt
    assert "7,8-dhf is also written: tropoflavin, 78dhf." in prompt  # the name itself is not repeated
    assert "Do not assign information about 4'-DMA-7,8-DHF to 7,8-dhf" in prompt
    bare = dose_system_prompt("ldn")
    assert "also written" not in bare and "Do not assign information about" not in bare
    assert '"dose_sentences"' in bare and '"quote"' in bare


def test_dose_value_coerces_units_and_labels_and_rejects_bad_values() -> None:
    dose = DoseValue.model_validate({"low": "20", "high": 20, "unit": "milligrams", "route": "snorted", "outcome": "great", "quote": "  20mg  "})
    assert (dose.low, dose.high, dose.unit, dose.route, dose.outcome, dose.quote) == (20.0, 20.0, "mg", None, None, "20mg")
    assert DoseValue.model_validate({"low": 500, "high": 500, "unit": "ug"}).unit == "mcg"
    assert DoseValue.model_validate({"low": 1, "high": 3, "unit": "grams", "outcome": "negative"}).outcome == "negative"
    with pytest.raises(ValidationError):
        DoseValue.model_validate({"low": 20, "high": 10, "unit": "mg"})
    with pytest.raises(ValidationError):
        DoseValue.model_validate({"low": 2, "high": 2, "unit": "mg/kg"})
    with pytest.raises(ValidationError):
        DoseValue.model_validate({"low": "twenty", "high": 20, "unit": "mg"})


def test_parse_response_checks_item_ids_and_drops_invalid_doses() -> None:
    raw = json.dumps([
        {"item_id": 0, "dose_sentences": ["x"], "doses": [
            {"low": 10, "high": 20, "unit": "mg", "outcome": "positive", "quote": "10-20mg works"},
            {"low": 10, "high": 20, "unit": "mg", "outcome": "positive", "quote": "10-20mg works"},
            {"low": 5, "high": 5, "unit": "drops"},
        ]},
        {"item_id": 1, "doses": []},
    ])
    per_item, dropped = parse_dose_response(raw, [0, 1])
    assert dropped == 1
    assert [d.low for d in per_item[0]] == [10.0] and per_item[1] == []
    with pytest.raises(LLMParseError, match="do not match"):
        parse_dose_response(raw, [0, 2])
    with pytest.raises(LLMParseError):
        parse_dose_response("no json here", [0])


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO users VALUES ('u1', 'Nootropics', 0)")
    conn.execute("INSERT INTO users VALUES ('u2', 'Nootropics', 0)")
    conn.execute(
        "INSERT INTO posts (post_id, title, parent_id, user_id, body_text, scraped_at) VALUES "
        "('top', 'Dosing thread', NULL, 'u1', 'What dose do you all take?', 0)"
    )
    conn.execute(
        "INSERT INTO posts (post_id, title, parent_id, user_id, body_text, scraped_at) VALUES "
        "('reply', NULL, 'top', 'u2', 'I take 20mg sublingual, it is great. Tried 40 mg once, headache.', 0)"
    )
    conn.execute(
        "INSERT INTO posts (post_id, title, parent_id, user_id, body_text, scraped_at) VALUES "
        "('other', NULL, 'top', 'u1', 'Never tried it.', 0)"
    )
    conn.execute("INSERT INTO treatment (id, canonical_name, aliases) VALUES (1, '7,8-dhf', '[\"tropoflavin\"]')")
    conn.execute("INSERT INTO extraction_runs VALUES (1, 0, 'abc', 'treatment_sentiment', '{}')")
    conn.executemany(
        "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength) VALUES (1, ?, ?, 1, ?, 'strong')",
        [("reply", "u2", "positive"), ("other", "u1", "neutral"), ("reply", "u2", "mixed")],  # two runs for 'reply'
    )
    conn.commit()
    conn.close()


def test_contexts_take_latest_report_per_post_with_parent_context(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    _make_db(db)
    conn = sqlite3.connect(db)
    contexts = load_dose_contexts(conn, "7,8-DHF", parent_chars=12)
    conn.close()
    assert [(c.post_id, c.report_id) for c in contexts] == [("other", 2), ("reply", 3)]
    reply = contexts[1]
    assert reply.text.startswith("I take 20mg") and reply.replying_to == "Dosing threa"
    assert make_batches(contexts, batch_size=8, solo_above_chars=20) == [[contexts[0]], [contexts[1]]]


def test_round_trip_writes_rows_and_rerun_replaces_them(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "t.db"
    _make_db(db)
    seen_payloads: list[dict] = []

    def fake_llm_call(client, prompt, model=None, system=None, max_tokens=0):
        payload = json.loads(prompt)
        seen_payloads.append(payload)
        out = []
        for item in payload["items"]:
            doses = []
            if "20mg" in item["report"]:
                doses = [
                    {"low": 20, "high": 20, "unit": "mg", "route": "oral mucosal", "outcome": "positive", "quote": "I take 20mg sublingual, it is great."},
                    {"low": 40, "high": 40, "unit": "mg", "outcome": "negative", "quote": "Tried 40 mg once, headache."},
                ]
            out.append({"item_id": item["item_id"], "dose_sentences": [], "doses": doses})
        return json.dumps(out)

    monkeypatch.setattr(doses_module, "llm_call", fake_llm_call)
    summary = run_dose_extraction(None, db, "7,8-dhf", excluded_compounds=["4'-DMA-7,8-DHF"], workers=1)
    assert (summary.reports, summary.reports_with_doses, summary.dose_rows, summary.failed_reports) == (2, 1, 2, 0)
    assert any("replying_to" in item for payload in seen_payloads for item in payload["items"])

    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT report_id, ordinal, post_id, user_id, drug_id, low, high, unit, route, outcome, quote "
            "FROM report_doses ORDER BY ordinal"
        ).fetchall()
        run = conn.execute("SELECT extraction_type, config FROM extraction_runs WHERE run_id = ?", (summary.run_id,)).fetchone()
    assert rows == [
        (3, 1, "reply", "u2", 1, 20.0, 20.0, "mg", "oral mucosal", "positive", "I take 20mg sublingual, it is great."),
        (3, 2, "reply", "u2", 1, 40.0, 40.0, "mg", None, "negative", "Tried 40 mg once, headache."),
    ]
    config = json.loads(run[1])
    assert run[0] == "report_doses" and config["drug"] == "7,8-dhf" and config["aliases"] == ["tropoflavin"]
    assert config["excluded_compounds"] == ["4'-DMA-7,8-DHF"] and len(config["prompt_sha256"]) == 64

    # A second run replaces the report's rows instead of appending to them.
    monkeypatch.setattr(
        doses_module, "llm_call",
        lambda client, prompt, model=None, system=None, max_tokens=0: json.dumps([
            {"item_id": item["item_id"], "doses": [{"low": 25, "high": 25, "unit": "mg", "quote": "q"}] if "20mg" in item["report"] else []}
            for item in json.loads(prompt)["items"]
        ]),
    )
    second = run_dose_extraction(None, db, "7,8-dhf", workers=1)
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT run_id, low FROM report_doses").fetchall()
        runs = conn.execute("SELECT COUNT(*) FROM extraction_runs WHERE extraction_type = 'report_doses'").fetchone()[0]
    assert rows == [(second.run_id, 25.0)] and runs == 2


def test_malformed_batch_is_split_down_to_single_items(monkeypatch: pytest.MonkeyPatch) -> None:
    from pipeline.doses import DoseContext, extract_batch

    calls: list[int] = []

    def fake_llm_call(client, prompt, model=None, system=None, max_tokens=0):
        items = json.loads(prompt)["items"]
        calls.append(len(items))
        if len(items) > 1:
            return "garbage"
        return json.dumps([{"item_id": 0, "doses": [{"low": 1, "high": 1, "unit": "mg"}]}])

    monkeypatch.setattr(doses_module, "llm_call", fake_llm_call)
    batch = [DoseContext(i, f"p{i}", None, 1, "1mg", "") for i in range(4)]
    results, dropped = extract_batch(None, batch, "sys", "model")
    assert sorted(results) == [0, 1, 2, 3] and dropped == 0 and calls == [4, 2, 1, 1, 2, 1, 1]
