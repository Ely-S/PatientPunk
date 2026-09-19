"""Shared per-report step mechanics: context loading, batching, the split retry, alias lookup. No model calls."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import pipeline.report_context as rc
from pipeline.report_context import (
    ReportContext,
    aliases_from_db,
    extract_with_split,
    load_report_contexts,
    make_batches,
)
from utilities import LLMParseError

SCHEMA_SQL = Path(__file__).parent.parent / "schema.sql"
SEED = """
    INSERT INTO users VALUES ('u1', 'test', 0), ('u2', 'test', 0);
    INSERT INTO posts (post_id, parent_id, user_id, title, body_text, scraped_at) VALUES
        ('top',   NULL,    'u1', 'Dosing thread', 'What dose do you all take?', 0),
        ('reply', 'top',   'u2', NULL, 'I take 20mg sublingual, it is great. Tried 40 mg once, headache.', 0),
        ('deep',  'reply', 'u1', NULL, 'Same here.', 0),
        ('other', 'top',   'u1', NULL, 'Never tried it.', 0);
    INSERT INTO treatment (id, canonical_name, aliases) VALUES (1, '7,8-dhf', '["tropoflavin", " ", "78dhf"]'), (2, 'ldn', NULL);
    INSERT INTO extraction_runs VALUES (1, 0, 'abc', 'treatment_sentiment', '{}');
    INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength) VALUES
        (1, 'reply', 'u2', 1, 'positive', 'strong'), (1, 'other', 'u1', 1, 'neutral', 'strong'),
        (1, 'deep',  'u1', 1, 'positive', 'weak'),   (1, 'reply', 'u2', 1, 'mixed', 'strong');
"""


@pytest.fixture
def seeded(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "study.db")
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.executescript(SEED)
    yield conn
    conn.close()


def test_loader_takes_the_latest_report_per_post_with_the_parent_as_context(seeded: sqlite3.Connection) -> None:
    contexts = load_report_contexts(seeded, "7,8-DHF", parent_chars=12)  # case-insensitive drug lookup
    assert [(c.post_id, c.report_id) for c in contexts] == [("other", 2), ("deep", 3), ("reply", 4)]
    assert contexts[2].text.startswith("I take 20mg") and contexts[2].replying_to == "Dosing threa"
    assert contexts[1].replying_to == "I take 20mg "  # capped at parent_chars
    full = {c.post_id: c for c in load_report_contexts(seeded, "7,8-dhf")}
    assert full["deep"].replying_to == "I take 20mg sublingual, it is great. Tried 40 mg once, headache."  # a reply's parent is body only
    assert all(c.thread_title == "" for c in contexts)  # off unless asked for
    assert load_report_contexts(seeded, "7,8-dhf", parent_chars=12, limit=1) == contexts[:1]
    assert load_report_contexts(seeded, "ldn") == []


def test_loader_adds_the_thread_root_title_only_when_asked(seeded: sqlite3.Connection) -> None:
    by_post = {c.post_id: c for c in load_report_contexts(seeded, "7,8-dhf", thread_chars=6)}
    assert by_post["deep"].thread_title == "Dosing"       # two levels up, capped
    assert by_post["reply"].thread_title == "Dosing"
    assert by_post["other"].thread_title == "Dosing"
    seeded.execute("INSERT INTO posts (post_id, parent_id, user_id, title, body_text, scraped_at) VALUES ('lone', NULL, 'u1', 'Solo', 'x', 0)")
    seeded.execute("INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength) VALUES (1, 'lone', 'u1', 1, 'neutral', 'weak')")
    assert {c.post_id: c.thread_title for c in load_report_contexts(seeded, "7,8-dhf", thread_chars=6)}["lone"] == ""  # top-level: none


def test_batches_short_reports_together_and_long_ones_alone() -> None:
    ctx = [ReportContext(i, f"p{i}", None, 1, "x" * n, "") for i, n in enumerate((5, 50, 5, 5))]
    assert make_batches(ctx, batch_size=2, solo_above_chars=20) == [[ctx[0], ctx[2]], [ctx[3]], [ctx[1]]]
    assert make_batches(ctx, batch_size=8, solo_above_chars=None) == [ctx]
    assert make_batches([], batch_size=8, solo_above_chars=20) == []


def test_split_retries_a_malformed_reply_down_to_single_items(monkeypatch: pytest.MonkeyPatch) -> None:
    sizes: list[int] = []

    def stub(client, prompt, model=None, system=None, max_tokens=0) -> str:
        items = json.loads(prompt)["items"]
        sizes.append(len(items))
        assert max_tokens == 7 * len(items)
        return "garbage" if len(items) > 1 else json.dumps([{"item_id": 0, "value": items[0]["report"]}])

    def parse(raw: str, expected_ids: list[int]) -> tuple[dict[int, str], int]:
        objects = json.loads(raw) if raw.startswith("[") else None
        if objects is None:
            raise LLMParseError("not json")
        return {o["item_id"]: o["value"] for o in objects}, 0

    payload = lambda batch: json.dumps({"items": [{"item_id": i, "report": c.text} for i, c in enumerate(batch)]})  # noqa: E731
    monkeypatch.setattr(rc, "llm_call", stub)  # the default call is looked up at call time
    batch = [ReportContext(i, f"p{i}", None, 1, f"t{i}", "") for i in range(4)]

    results, dropped = extract_with_split(None, batch, "sys", "model", payload, parse, tokens_per_item=7)

    assert results == {0: "t0", 1: "t1", 2: "t2", 3: "t3"} and dropped == 0
    assert sizes == [4, 2, 1, 1, 2, 1, 1]

    def always_bad(client, prompt, model=None, system=None, max_tokens=0) -> str:
        return "garbage"

    results, dropped = extract_with_split(None, batch[:1], "sys", "model", payload, parse, 7, call=always_bad)
    assert results == {} and dropped == 0  # a single item that stays malformed is skipped, not raised


def test_aliases_from_db_reads_the_stored_spellings(seeded: sqlite3.Connection) -> None:
    assert aliases_from_db(seeded, "7,8-DHF") == ["tropoflavin", "78dhf"]  # blank entries dropped
    assert aliases_from_db(seeded, "ldn") == []
    assert aliases_from_db(seeded, "nope") == []
    seeded.execute("UPDATE treatment SET aliases = 'not json' WHERE id = 1")
    assert aliases_from_db(seeded, "7,8-dhf") == []
