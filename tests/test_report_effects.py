"""Effects step: prompt, parsing, the write-time checks, and the report_effects writer. The model call is stubbed."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import pipeline.effects as effects_module
from pipeline.effects import (
    EffectValue,
    apply_effect_checks,
    parse_effects_response,
    run_effects_extraction,
)
from pipeline.report_context import ReportContext, extract_with_split, load_report_contexts, make_batches
from prompts.effects_config import DOMAINS, effects_system_prompt
from utilities import LLMParseError

SCHEMA_SQL = Path(__file__).parent.parent / "schema.sql"
TARGET = frozenset({"7,8-dhf", "tropoflavin"})


def _seed(db_path: Path) -> None:
    """Three-level thread; the reply is classified twice (latest wins) and has one dose row."""
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
        conn.executescript("""
            INSERT INTO users VALUES ('u1', 'test', 0), ('u2', 'test', 0);
            INSERT INTO posts (post_id, parent_id, user_id, title, body_text, scraped_at) VALUES
                ('root', NULL, 'u1', 'Tropoflavin thread', 'What does it do for you?', 0),
                ('mid', 'root', 'u1', NULL, 'Asking for a friend.', 0),
                ('reply', 'mid', 'u2', NULL, 'At 20mg it fixed my brain fog. It also ruins my sleep.', 0),
                ('other', 'root', 'u1', NULL, 'Never tried it.', 0);
            INSERT INTO treatment (id, canonical_name, aliases) VALUES (1, '7,8-dhf', '["tropoflavin"]');
            INSERT INTO extraction_runs VALUES (1, 0, 'abc', 'treatment_sentiment', '{}'), (2, 0, 'abc', 'report_doses', '{}');
            INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength) VALUES
                (1, 'reply', 'u2', 1, 'positive', 'strong'), (1, 'other', 'u1', 1, 'neutral', 'strong'),
                (1, 'reply', 'u2', 1, 'mixed', 'strong');
            INSERT INTO report_doses (dose_id, report_id, run_id, ordinal, post_id, user_id, drug_id, low, high, unit, quote)
                VALUES (7, 3, 2, 1, 'reply', 'u2', 1, 20, 20, 'mg', 'At 20mg it fixed my brain fog.');
        """)


def test_prompt_renders_name_aliases_exclusions_and_domains() -> None:
    prompt = effects_system_prompt("7,8-dhf", ["tropoflavin", "78dhf", "7,8-DHF"], ["4'-DMA-7,8-DHF"], ["mood", "overall"])
    assert "say 7,8-dhf did for them" in prompt
    assert "7,8-dhf is also written: tropoflavin, 78dhf." in prompt  # the name itself is not repeated
    assert "Do not assign information about 4'-DMA-7,8-DHF to 7,8-dhf" in prompt
    assert "\nmood; overall\n" in prompt and "anxiety or stress" not in prompt
    assert '"attribution": "7,8-dhf"' in prompt and '"dose": 1' in prompt
    bare = effects_system_prompt("ldn")
    assert "also written" not in bare and "Do not assign information about" not in bare
    assert all(domain in bare for domain in DOMAINS)


def test_effect_value_coercion_maps_attribution_and_rejects_bad_fields() -> None:
    raw = json.dumps([{"item_id": 0, "effects": [
        {"domain": "Mood or depression", "symptom": " mood ", "direction": "Improved", "attribution": "Tropoflavin", "quote": " it lifted my mood ", "dose": "2"},
        {"domain": "energy or motivation", "symptom": "energy", "direction": "improved", "attribution": "polygala", "quote": "polygala gave me energy"},
        {"domain": "sleep or wakefulness", "symptom": "sleep", "direction": "better", "attribution": "7,8-dhf", "quote": "slept well"},
        {"domain": "vibes", "symptom": "vibes", "direction": "improved", "attribution": "7,8-dhf", "quote": "good vibes"},
        {"domain": "overall", "symptom": "", "direction": "no change", "attribution": "stack", "quote": "did nothing"},
        {"domain": "overall", "direction": "improved", "attribution": "unclear", "quote": ""},
    ]}])
    per_item, dropped = parse_effects_response(raw, [0], TARGET)
    assert dropped == 3  # bad direction, unknown domain, missing quote
    assert [(e.domain, e.symptom, e.direction, e.attribution, e.quote, e.dose) for e in per_item[0]] == [
        ("mood or depression", "mood", "improved", "target", "it lifted my mood", 2),
        ("energy or motivation", "energy", "improved", "other compound", "polygala gave me energy", None),
        ("overall", "overall", "no_change", "stack", "did nothing", None),
    ]


def test_parse_dedupes_and_rejects_mismatched_ids_and_non_json() -> None:
    effect = {"domain": "overall", "symptom": "x", "direction": "improved", "attribution": "unclear", "quote": "it worked"}
    raw = json.dumps([{"item_id": 0, "effects": [effect, dict(effect), "not an object"]}, {"item_id": 1, "effects": []}])
    per_item, dropped = parse_effects_response(raw, [0, 1], TARGET)
    assert dropped == 1 and len(per_item[0]) == 1 and per_item[1] == []
    with pytest.raises(LLMParseError, match="do not match"):
        parse_effects_response(raw, [0, 2], TARGET)
    with pytest.raises(LLMParseError):
        parse_effects_response("no json here", [0], TARGET)


def test_quote_check_drops_foreign_quotes_and_keeps_punctuation_variants() -> None:
    report = "At 20mg it fixed my brain fog. It also ruins my sleep."
    effects = [
        EffectValue(domain="cognition or brain fog", symptom="brain fog", direction="improved", attribution="target", quote="at 20MG, it fixed my brain-fog"),
        EffectValue(domain="mood or depression", symptom="mood", direction="improved", attribution="target", quote="it combines well with tropoflavin"),
    ]
    kept, quote_drops, dose_drops = apply_effect_checks(effects, report, listed_dose_ids=set())
    assert [e.symptom for e in kept] == ["brain fog"] and (quote_drops, dose_drops) == (1, 0)


def test_dose_id_outside_the_listed_doses_becomes_null() -> None:
    report = "At 20mg it fixed my brain fog. It also ruins my sleep."
    effects = [
        EffectValue(domain="cognition or brain fog", symptom="brain fog", direction="improved", attribution="target", quote="At 20mg it fixed my brain fog.", dose=7),
        EffectValue(domain="sleep or wakefulness", symptom="sleep", direction="worsened", attribution="target", quote="It also ruins my sleep.", dose=99),
    ]
    kept, quote_drops, dose_drops = apply_effect_checks(effects, report, listed_dose_ids={7})
    assert [e.dose for e in kept] == [7, None] and (quote_drops, dose_drops) == (0, 1)


def test_contexts_take_latest_report_per_post_with_parent_and_thread_title(tmp_path: Path) -> None:
    db = tmp_path / "study.db"
    _seed(db)
    with sqlite3.connect(db) as conn:
        contexts = load_report_contexts(conn, "7,8-DHF", parent_chars=12, thread_chars=10)
    assert [(c.post_id, c.report_id) for c in contexts] == [("other", 2), ("reply", 3)]
    reply = contexts[1]
    assert reply.text.startswith("At 20mg") and reply.replying_to == "Asking for a" and reply.thread_title == "Tropoflavi"
    assert contexts[0].thread_title == "Tropoflavi"  # a direct reply to the root still gets the title
    assert make_batches(contexts, batch_size=8, solo_above_chars=20) == [[contexts[0]], [contexts[1]]]


def test_run_writes_rows_links_doses_records_config_and_a_rerun_replaces_them(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payloads: list[dict] = []
    respond = {"fn": lambda items: []}

    def stub_llm(client, prompt, model=None, system=None, max_tokens=0) -> str:  # stands in for the model call
        payloads.append(json.loads(prompt))
        return json.dumps(respond["fn"](payloads[-1]["items"]))

    monkeypatch.setattr(effects_module, "llm_call", stub_llm)
    db = tmp_path / "study.db"
    _seed(db)
    reply_effects = [
        {"domain": "cognition or brain fog", "symptom": "brain fog", "direction": "improved", "attribution": "7,8-dhf", "quote": "At 20mg it fixed my brain fog.", "dose": 7},
        {"domain": "sleep or wakefulness", "symptom": "sleep", "direction": "worsened", "attribution": "7,8-dhf", "quote": "It also ruins my sleep.", "dose": 42},
        {"domain": "mood or depression", "symptom": "mood", "direction": "improved", "attribution": "7,8-dhf", "quote": "lifted from the parent post"},
    ]
    respond["fn"] = lambda items: [{"item_id": it["item_id"], "effects": reply_effects if "20mg" in it["report"] else []} for it in items]

    first = run_effects_extraction(None, db, "7,8-dhf", excluded_compounds=["4'-DMA-7,8-DHF"], workers=1)

    assert (first.reports, first.reports_with_effects, first.effect_rows, first.failed_reports) == (2, 1, 2, 0)
    assert (first.dropped_effects, first.quote_drops, first.dose_link_drops) == (0, 1, 1)
    reply_item = next(it for p in payloads for it in p["items"] if "20mg" in it["report"])
    assert reply_item["doses"] == [{"id": 7, "quote": "At 20mg it fixed my brain fog."}]
    assert reply_item["thread"] == "Tropoflavin thread" and reply_item["replying_to"] == "Asking for a friend."
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT report_id, ordinal, post_id, user_id, drug_id, domain, symptom, direction, attribution, quote, dose_id "
            "FROM report_effects ORDER BY ordinal"
        ).fetchall()
        run_type, config = conn.execute("SELECT extraction_type, config FROM extraction_runs WHERE run_id = ?", (first.run_id,)).fetchone()
    assert rows == [
        (3, 1, "reply", "u2", 1, "cognition or brain fog", "brain fog", "improved", "target", "At 20mg it fixed my brain fog.", 7),
        (3, 2, "reply", "u2", 1, "sleep or wakefulness", "sleep", "worsened", "target", "It also ruins my sleep.", None),
    ]
    config = json.loads(config)
    assert run_type == "report_effects" and config["excluded_compounds"] == ["4'-DMA-7,8-DHF"]
    assert config["aliases"] == ["tropoflavin"] and config["domains"] == list(DOMAINS) and config["dose_run_id"] == 2

    respond["fn"] = lambda items: [{"item_id": it["item_id"], "effects": [
        {"domain": "overall", "symptom": "overall", "direction": "no_change", "attribution": "7,8-dhf", "quote": "ruins my sleep"}
    ] if "20mg" in it["report"] else []} for it in items]
    second = run_effects_extraction(None, db, "7,8-dhf", workers=1)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT run_id, domain FROM report_effects").fetchall() == [(second.run_id, "overall")]


def test_malformed_batch_is_split_down_to_single_items() -> None:
    calls: list[int] = []

    def stub_llm(client, prompt, model=None, system=None, max_tokens=0) -> str:
        items = json.loads(prompt)["items"]
        calls.append(len(items))
        if len(items) > 1:
            return "garbage"
        return json.dumps([{"item_id": 0, "effects": [{"domain": "overall", "symptom": "x", "direction": "improved", "attribution": "7,8-dhf", "quote": "q"}]}])

    batch = [ReportContext(i, f"p{i}", None, 1, "q", "") for i in range(4)]
    parse = lambda raw, ids: parse_effects_response(raw, ids, TARGET)  # noqa: E731
    results, dropped = extract_with_split(None, batch, "sys", "model", lambda b: effects_module.request_payload(b, {}), parse, 10, call=stub_llm)

    assert sorted(results) == [0, 1, 2, 3] and dropped == 0
    assert all(len(v) == 1 for v in results.values())
    assert calls == [4, 2, 1, 1, 2, 1, 1]
