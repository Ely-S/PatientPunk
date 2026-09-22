"""Effects step: prompt, parsing, the write-time checks, and the report_effects writer. The model call is stubbed."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from pipeline import report_context
from pipeline.effects import EffectValue, apply_effect_checks, parse_effects_response, run_effects_extraction
from prompts.effects_config import DOMAINS, effects_system_prompt
from utilities import LLMParseError

SCHEMA_SQL = Path(__file__).parent.parent / "schema.sql"
TARGET = frozenset({"target", "7,8-dhf", "tropoflavin"})
REPORT = "At 20mg it fixed my brain fog. It also ruins my sleep. This stack helped my focus."


def test_prompt_renders_name_aliases_exclusions_and_domains() -> None:
    prompt = effects_system_prompt("7,8-dhf", ["tropoflavin", "78dhf", "7,8-DHF"], ["4'-DMA-7,8-DHF"], ["mood", "overall"])
    assert "say 7,8-dhf did for them" in prompt
    assert "7,8-dhf is also written: tropoflavin, 78dhf." in prompt  # the name itself is not repeated
    assert "Do not assign information about 4'-DMA-7,8-DHF to 7,8-dhf" in prompt
    assert "\nmood; overall\n" in prompt and "anxiety or stress" not in prompt
    bare = effects_system_prompt("ldn")
    assert "also written" not in bare and "Do not assign" not in bare and all(d in bare for d in DOMAINS)


def test_parse_coerces_attribution_drops_bad_objects_dedupes_and_checks_ids() -> None:
    effect = {"domain": "overall", "symptom": "x", "direction": "improved", "attribution": "unclear", "quote": "it worked"}
    raw = json.dumps([{"item_id": 0, "effects": [
        {"domain": "Mood or depression", "symptom": " mood ", "direction": "Improved", "attribution": "Tropoflavin", "quote": " it lifted my mood ", "dose": "2"},
        {"domain": "energy or motivation", "symptom": "energy", "direction": "improved", "attribution": "polygala", "quote": "polygala gave me energy"},
        {"domain": "sleep or wakefulness", "symptom": "sleep", "direction": "better", "attribution": "7,8-dhf", "quote": "slept well"},  # bad direction
        {"domain": "vibes", "symptom": "vibes", "direction": "improved", "attribution": "7,8-dhf", "quote": "good vibes"},  # unknown domain
        {"domain": "overall", "symptom": "", "direction": "no change", "attribution": "stack", "quote": "did nothing"},
        {"domain": "overall", "direction": "improved", "attribution": "unclear", "quote": ""},  # no quote
        {"domain": "overall", "symptom": "y", "direction": "improved", "attribution": "", "quote": "it worked"},  # no attribution
        {"domain": "pain or neurologic symptoms", "symptom": "headache", "direction": "worsened", "severity": "Mild", "attribution": "7,8-dhf", "quote": "a mild headache and severe dizziness"},
        {"domain": "pain or neurologic symptoms", "symptom": "dizziness", "direction": "worsened", "severity": "severe", "attribution": "7,8-dhf", "quote": "a mild headache and severe dizziness"},  # same domain, quote: kept apart
        {"domain": "gastrointestinal", "symptom": "nausea", "direction": "worsened", "severity": "brutal", "attribution": "7,8-dhf", "quote": "nausea"},  # not a severity: unspecified
        effect, dict(effect), "not an object",
    ]}, {"item_id": 1, "effects": []}])
    per_item, dropped = parse_effects_response(raw, [0, 1], TARGET)
    assert dropped == 5 and per_item[1] == []
    assert [(e.domain, e.symptom, e.direction, e.severity, e.attribution, e.quote, e.dose) for e in per_item[0]] == [
        ("mood or depression", "mood", "improved", None, "target", "it lifted my mood", 2),
        ("energy or motivation", "energy", "improved", None, "other compound", "polygala gave me energy", None),
        ("overall", "overall", "no_change", None, "stack", "did nothing", None),
        ("pain or neurologic symptoms", "headache", "worsened", "mild", "target", "a mild headache and severe dizziness", None),
        ("pain or neurologic symptoms", "dizziness", "worsened", "severe", "target", "a mild headache and severe dizziness", None),
        ("gastrointestinal", "nausea", "worsened", None, "target", "nausea", None),
        ("overall", "x", "improved", None, "unclear", "it worked", None),
    ]
    with pytest.raises(LLMParseError, match="do not match"):
        parse_effects_response(raw, [0, 2], TARGET)
    with pytest.raises(LLMParseError):
        parse_effects_response("no json here", [0], TARGET)
    for malformed in ('[{"item_id": 0}]', '[{"item_id": 0, "effects": null}]', '[{"item_id": 0, "effects": {}}]'):
        with pytest.raises(LLMParseError, match="must be an array"):  # retried, never written as "no effects"
            parse_effects_response(malformed, [0], TARGET)


def test_write_time_checks_drop_foreign_quotes_and_null_unlisted_dose_ids() -> None:
    effects = [
        EffectValue(domain="cognition or brain fog", symptom="brain fog", direction="improved", attribution="target", quote="at 20MG, it fixed my brain-fog", dose=7),
        EffectValue(domain="sleep or wakefulness", symptom="sleep", direction="worsened", attribution="target", quote="It also ruins my sleep.", dose=99),
        EffectValue(domain="mood or depression", symptom="mood", direction="improved", attribution="target", quote="it combines well with tropoflavin"),
    ]
    kept, quote_drops, dose_drops = apply_effect_checks(effects, REPORT, listed_dose_ids={7})
    assert [(e.symptom, e.dose) for e in kept] == [("brain fog", 7), ("sleep", None)] and (quote_drops, dose_drops) == (1, 1)


def test_run_writes_rows_links_doses_records_config_and_a_rerun_replaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payloads: list[dict] = []
    respond = {"fn": lambda items: []}

    def stub_llm(client, prompt, model=None, system=None, max_tokens=0) -> str:  # stands in for the model call
        payloads.append(json.loads(prompt))
        return json.dumps(respond["fn"](payloads[-1]["items"]))

    monkeypatch.setattr(report_context, "llm_call", stub_llm)
    db = tmp_path / "study.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
        conn.executescript(f"""
            INSERT INTO users VALUES ('u1', 'test', 0), ('u2', 'test', 0);
            INSERT INTO posts (post_id, parent_id, user_id, title, body_text, scraped_at) VALUES
                ('root', NULL, 'u1', 'Tropoflavin thread', 'What does it do for you?', 0),
                ('mid', 'root', 'u1', NULL, 'Asking for a friend.', 0),
                ('reply', 'mid', 'u2', NULL, '{REPORT}', 0),
                ('other', 'root', 'u1', NULL, 'Never tried it.', 0);
            INSERT INTO treatment (id, canonical_name, aliases) VALUES (1, '7,8-dhf', '["tropoflavin"]');
            INSERT INTO extraction_runs VALUES (1, 0, 'abc', 'treatment_sentiment', '{{}}'), (2, 0, 'abc', 'report_doses', '{{}}');
            INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength) VALUES
                (1, 'reply', 'u2', 1, 'positive', 'strong'), (1, 'other', 'u1', 1, 'neutral', 'strong'),
                (1, 'reply', 'u2', 1, 'mixed', 'strong');  -- 'reply' classified twice; the latest report wins
            INSERT INTO report_doses (dose_id, report_id, run_id, ordinal, low, high, unit, quote)
                VALUES (7, 3, 2, 0, 20, 20, 'mg', 'At 20mg it fixed my brain fog.');
        """)
    reply_effects = [
        {"domain": "cognition or brain fog", "symptom": "brain fog", "direction": "improved", "attribution": "7,8-dhf", "quote": "At 20mg it fixed my brain fog.", "dose": 7},
        {"domain": "sleep or wakefulness", "symptom": "sleep", "direction": "worsened", "attribution": "7,8-dhf", "quote": "It also ruins my sleep.", "dose": 42},
        {"domain": "mood or depression", "symptom": "mood", "direction": "improved", "attribution": "7,8-dhf", "quote": "lifted from the parent post"},
        {"domain": "focus or attention", "symptom": "focus", "direction": "improved", "attribution": "stack", "quote": "This stack helped my focus."},
    ]
    respond["fn"] = lambda items: [{"item_id": it["item_id"], "effects": reply_effects if "20mg" in it["report"] else []} for it in items]

    first = run_effects_extraction(None, db, "7,8-dhf", excluded_compounds=["4'-DMA-7,8-DHF"], workers=1)

    assert (first.reports, first.reports_with_rows, first.rows, first.failed) == (2, 1, 3, 0)
    assert (first.dropped, first.quote_drops, first.dose_link_drops) == (0, 1, 1)
    reply_item = next(it for p in payloads for it in p["items"] if "20mg" in it["report"])
    assert reply_item["doses"] == [{"id": 7, "quote": "At 20mg it fixed my brain fog."}]
    assert reply_item["replying_to"] == "Asking for a friend." and "thread" not in reply_item  # one parent up, nothing else
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT report_id, ordinal, domain, symptom, direction, severity, attribution, quote, dose_id FROM report_effects ORDER BY ordinal").fetchall()
        run_type, config = conn.execute("SELECT extraction_type, config FROM extraction_runs WHERE run_id = ?", (first.run_id,)).fetchone()
    assert rows == [
        (3, 0, "cognition or brain fog", "brain fog", "improved", None, "target", "At 20mg it fixed my brain fog.", 7),
        (3, 1, "sleep or wakefulness", "sleep", "worsened", None, "target", "It also ruins my sleep.", None),
        (3, 2, "focus or attention", "focus", "improved", None, "stack", "This stack helped my focus.", None),  # a stack credit stays "stack"
    ]
    config = json.loads(config)
    assert run_type == "report_effects" and config["excluded_compounds"] == ["4'-DMA-7,8-DHF"]
    assert config["aliases"] == ["tropoflavin"] and config["domains"] == list(DOMAINS) and config["dose_run_id"] == 2

    respond["fn"] = lambda items: [{"item_id": it["item_id"], "effects": [
        {"domain": "sleep or wakefulness", "symptom": "sleep", "direction": "worsened", "severity": "severe", "attribution": "7,8-dhf", "quote": "ruins my sleep"}
    ] if "20mg" in it["report"] else []} for it in items]
    second = run_effects_extraction(None, db, "7,8-dhf", workers=1)
    with sqlite3.connect(db) as conn:  # a rerun replaces the report's rows; a stated severity is stored
        assert conn.execute("SELECT run_id, domain, severity FROM report_effects").fetchall() == [(second.run_id, "sleep or wakefulness", "severe")]
    respond["fn"] = lambda items: [{"item_id": it["item_id"], "effects": []} for it in items]
    run_effects_extraction(None, db, "7,8-dhf", workers=1)
    with sqlite3.connect(db) as conn:  # a rerun that finds nothing retracts the earlier rows
        assert conn.execute("SELECT COUNT(*) FROM report_effects").fetchone() == (0,)
    with pytest.raises(ValueError, match="not a canonical treatment"):
        run_effects_extraction(None, db, "no-such-drug", workers=1)
