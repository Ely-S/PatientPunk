"""Dose step: prompt, parsing, and the report_doses writer. The model call is stubbed; nothing is sent anywhere."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from pipeline import report_context
from pipeline.doses import DoseValue, normalize_unit, parse_dose_response, run_dose_extraction
from pipeline.report_context import load_report_contexts, make_batches, serialize_batch
from prompts.dose_config import dose_system_prompt
from utilities import LLMParseError
from utilities.db import ReportWriter

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
    for malformed in ('[{"item_id": 0}]', '[{"item_id": 0, "doses": null}]', '[{"item_id": 0, "doses": {}}]'):
        with pytest.raises(LLMParseError, match="must be an array"):  # retried, never written as "no doses"
            parse_dose_response(malformed, [0])


def test_run_writes_one_row_per_dose_and_the_latest_view_follows_the_newest_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payloads: list[dict] = []
    respond = {"fn": lambda items: []}

    def stub_llm(client, prompt, model=None, system=None, max_tokens=0) -> str:  # stands in for the model call
        payloads.append(json.loads(prompt))
        return json.dumps(respond["fn"](payloads[-1]["items"]))

    monkeypatch.setattr(report_context, "llm_call", stub_llm)
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

    assert (first.reports, first.reports_with_rows, first.rows, first.failed, first.dropped) == (2, 1, 2, 0, 0)
    assert all(it["replying_to"] == "Dosing thread What dose do you all take?" for it in payloads[0]["items"])
    assert all("thread" not in it for it in payloads[0]["items"])  # context is one parent up, nothing else
    with sqlite3.connect(schema_db) as conn:
        rows = conn.execute("SELECT report_id, ordinal, low, high, unit, route, outcome, quote FROM report_doses ORDER BY ordinal").fetchall()
        run_type, config = conn.execute("SELECT extraction_type, config FROM extraction_runs WHERE run_id = ?", (first.run_id,)).fetchone()
    assert rows == [
        (3, 0, 20.0, 20.0, "mg", "oral mucosal", "positive", "I take 20mg sublingual, it is great."),
        (3, 1, 40.0, 40.0, "mg", None, "negative", "Tried 40 mg once, headache."),
    ]
    config = json.loads(config)
    assert run_type == "report_doses" and config["excluded_compounds"] == ["4'-DMA-7,8-DHF"] and config["exclusions_source"] == "flags"

    respond["fn"] = lambda items: [{"item_id": it["item_id"], "doses": [{"low": 25, "high": 25, "unit": "mg", "quote": "q"}] if "20mg" in it["report"] else []} for it in items]
    second = run_dose_extraction(None, schema_db, "7,8-dhf", workers=1)
    with sqlite3.connect(schema_db) as conn:  # runs append; the view shows the report's rows from its newest run
        assert conn.execute("SELECT run_id, low FROM report_doses_latest").fetchall() == [(second.run_id, 25.0)]
        assert conn.execute("SELECT COUNT(*) FROM report_doses").fetchone() == (3,)
        second_config = json.loads(conn.execute("SELECT config FROM extraction_runs WHERE run_id = ?", (second.run_id,)).fetchone()[0])
        assert (second_config["excluded_compounds"], second_config["exclusions_source"]) == ([], "none")  # no flags, no sentiment-run list

    respond["fn"] = lambda items: [{"item_id": it["item_id"], "doses": []} for it in items]
    third = run_dose_extraction(None, schema_db, "7,8-dhf", workers=1)
    with sqlite3.connect(schema_db) as conn:  # a rerun that finds nothing retracts the earlier rows from the view; the table keeps them
        assert conn.execute("SELECT COUNT(*) FROM report_doses_latest").fetchone() == (0,)
        assert conn.execute("SELECT COUNT(*) FROM report_doses").fetchone() == (3,)
        assert conn.execute("SELECT report_id FROM report_runs WHERE run_id = ? ORDER BY report_id", (third.run_id,)).fetchall() == [(2,), (3,)]
        # rows written for the post's OLDER treatment report (id 1, superseded by id 3) stay out of the view
        conn.execute("INSERT INTO report_runs VALUES (?, 1)", (second.run_id,))
        conn.execute("INSERT INTO report_doses (report_id, run_id, ordinal, low, high, unit) VALUES (1, ?, 0, 5, 5, 'mg')", (second.run_id,))
        assert conn.execute("SELECT COUNT(*) FROM report_doses WHERE report_id = 1").fetchone() == (1,)
        assert conn.execute("SELECT COUNT(*) FROM report_doses_latest").fetchone() == (0,)

    with sqlite3.connect(schema_db) as conn:  # an effect row linked to a dose row
        conn.execute("INSERT INTO extraction_runs VALUES (9, 0, 'abc', 'report_doses', '{}')")
        conn.execute("INSERT INTO report_doses (dose_id, report_id, run_id, ordinal, low, high, unit) VALUES (7, 3, 9, 0, 20, 20, 'mg')")
        conn.execute("INSERT INTO extraction_runs VALUES (10, 0, 'abc', 'report_effects', '{}')")
        conn.execute("INSERT INTO report_effects (report_id, run_id, ordinal, domain, symptom, direction, attribution, quote, dose_id) "
                     "VALUES (3, 10, 0, 'overall', 'overall', 'improved', 'target', 'q', 7)")
    with ReportWriter(schema_db, {}, "test", extraction_type="report_doses") as writer:  # a dose rerun: the link stays, the view moves on
        writer.write_doses(3, [DoseValue(low=30, high=30, unit="mg")])
        with pytest.raises(ValueError, match="does not exist"):
            writer.write_doses(999, [])
    with sqlite3.connect(schema_db) as conn:
        assert conn.execute("SELECT dose_id FROM report_effects").fetchall() == [(7,)]
        assert conn.execute("SELECT COUNT(*) FROM report_doses WHERE dose_id = 7").fetchone() == (1,)
        assert conn.execute("SELECT run_id, low FROM report_doses_latest WHERE report_id = 3").fetchall() == [(writer.run_id, 30.0)]
    with pytest.raises(ValueError, match="not a canonical treatment"):
        run_dose_extraction(None, schema_db, "no-such-drug", workers=1)


def test_dose_payload_is_unchanged_by_the_shared_context_module(tmp_path: Path) -> None:
    """Pins the exact JSON the dose step sends, so a change to the shared mechanics cannot alter a run silently.

    Expected strings are the pre-refactor payload from origin/main: context is the parent only.
    """
    schema_db = tmp_path / "study.db"
    with sqlite3.connect(schema_db) as conn:
        conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
        conn.executescript("""
            INSERT INTO users VALUES ('u1', 'test', 0), ('u2', 'test', 0);
            INSERT INTO posts (post_id, parent_id, user_id, title, body_text, scraped_at) VALUES
                ('top', NULL, 'u1', 'Dosing thread', 'What dose do you all take?', 0),
                ('reply', 'top', 'u2', NULL, 'I take 20mg sublingual,  it is great.', 0),
                ('long', 'top', 'u1', NULL, 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', 0);
            INSERT INTO treatment (id, canonical_name, aliases) VALUES (1, '7,8-dhf', NULL);
            INSERT INTO extraction_runs VALUES (1, 0, 'abc', 'treatment_sentiment', '{}');
            INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength) VALUES
                (1, 'top', 'u1', 1, 'neutral', 'weak'), (1, 'reply', 'u2', 1, 'positive', 'strong'), (1, 'long', 'u1', 1, 'neutral', 'weak');
        """)
        contexts = load_report_contexts(conn, "7,8-dhf", parent_chars=1500, limit=None)
    batches = make_batches(contexts, batch_size=8, solo_above_chars=50)  # the two 40-char texts batch; the 60-char one goes solo
    assert [serialize_batch(b) for b in batches] == [
        '{"items": [{"item_id": 0, "report": "Dosing thread What dose do you all take?"}, '
        '{"item_id": 1, "report": "I take 20mg sublingual, it is great.", "replying_to": "Dosing thread What dose do you all take?"}]}',
        '{"items": [{"item_id": 0, "report": "' + "x" * 60 + '", "replying_to": "Dosing thread What dose do you all take?"}]}',
    ]


def test_dose_payload_identity_covers_truncation_tiebreak_and_unicode(tmp_path: Path) -> None:
    """The expected strings were generated from origin/main's doses.py (pre-refactor) on this seed, then the
    Context is the parent only (the thread title is off by default), so no "thread" key.

    Exercises what the first identity test does not: the parent cut at parent_chars, the report
    cut at max_text_chars (strip, then slice, so a trailing space survives), the latest-run
    report winning for a post with two reports, non-ASCII kept verbatim, and a two-item batch
    next to two solo items.
    """
    schema_db = tmp_path / "study.db"
    with sqlite3.connect(schema_db) as conn:
        conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
        conn.executescript("""
            INSERT INTO users VALUES ('u1', 'test', 0), ('u2', 'test', 0);
            INSERT INTO posts (post_id, parent_id, user_id, title, body_text, scraped_at) VALUES
                ('top', NULL, 'u1', 'Dosing thread', 'What dose do you all take? Sublingual for me, 20 mg.', 0),
                ('reply', 'top', 'u2', NULL, 'I take 20mg sublingual,  it is great \u2014 tr\u00e8s bien.', 0),
                ('reply2', 'top', 'u1', NULL, 'Same, 20 mg.', 0),
                ('long', 'top', 'u1', NULL, 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', 0);
            INSERT INTO treatment (id, canonical_name, aliases) VALUES (1, '7,8-dhf', NULL);
            INSERT INTO extraction_runs VALUES (1, 0, 'abc', 'treatment_sentiment', '{}'), (2, 0, 'abc', 'treatment_sentiment', '{}');
            INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength) VALUES
                (1, 'top', 'u1', 1, 'neutral', 'weak'), (1, 'reply', 'u2', 1, 'positive', 'strong'),
                (1, 'reply2', 'u1', 1, 'neutral', 'weak'), (1, 'long', 'u1', 1, 'neutral', 'weak'),
                (2, 'reply', 'u2', 1, 'mixed', 'weak');
        """)
        contexts = load_report_contexts(conn, "7,8-dhf", parent_chars=12, limit=None, max_text_chars=60)
    assert [c.report_id for c in contexts] == [1, 3, 4, 5]  # 'reply' resolves to its run-2 report
    batches = make_batches(contexts, batch_size=8, solo_above_chars=55)
    assert [serialize_batch(b) for b in batches] == [
        '{"items": [{"item_id": 0, "report": "Same, 20 mg.", "replying_to": "Dosing threa"}, '
        '{"item_id": 1, "report": "I take 20mg sublingual, it is great \u2014 tr\u00e8s bien.", "replying_to": "Dosing threa"}]}',
        '{"items": [{"item_id": 0, "report": "Dosing thread What dose do you all take? Sublingual for me, "}]}',
        '{"items": [{"item_id": 0, "report": "' + "x" * 60 + '", "replying_to": "Dosing threa"}]}',
    ]
