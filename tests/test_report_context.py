"""Shared per-report step mechanics: the loader, batching, the split retry, alias lookup, the runner's counting, the CLI flags. No model calls."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from pipeline.report_context import (
    ReportContext,
    Step,
    add_step_arguments,
    aliases_from_db,
    extract_with_split,
    load_report_contexts,
    make_batches,
    request_items,
    response_items,
    run_report_step,
    serialize_batch,
    step_kwargs,
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
def seeded_db(tmp_path: Path) -> Path:
    db = tmp_path / "study.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
        conn.executescript(SEED)
    return db


@pytest.fixture
def seeded(seeded_db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(seeded_db)
    yield conn
    conn.close()


def parse(raw: str, expected_ids: list[int], dropped: int = 0) -> tuple[dict[int, str], int]:
    """A step's parse_fn for these tests: each reply object's ``value`` by item id, plus how many reply objects the
    step threw away. This parser validates nothing, so the caller says; the runner sums it into StepSummary.dropped."""
    return {i: obj["value"] for i, obj in response_items(raw, expected_ids).items()}, dropped


def test_loader_takes_the_latest_report_per_post_with_the_parent_as_context(seeded: sqlite3.Connection) -> None:
    contexts = load_report_contexts(seeded, "7,8-DHF", parent_chars=12)  # case-insensitive drug lookup
    assert [(c.post_id, c.report_id) for c in contexts] == [("other", 2), ("deep", 3), ("reply", 4)]
    assert contexts[2].text.startswith("I take 20mg") and contexts[2].replying_to == "Dosing threa"
    assert contexts[1].replying_to == "I take 20mg "  # capped at parent_chars
    full = {c.post_id: c for c in load_report_contexts(seeded, "7,8-dhf")}
    assert full["deep"].replying_to == "I take 20mg sublingual, it is great. Tried 40 mg once, headache."  # a reply's parent is body only
    assert load_report_contexts(seeded, "7,8-dhf", parent_chars=12, limit=1) == contexts[:1]
    assert load_report_contexts(seeded, "ldn") == []


def test_batches_short_reports_together_and_long_ones_alone() -> None:
    ctx = [ReportContext(i, f"p{i}", None, 1, "x" * n, "") for i, n in enumerate((5, 50, 5, 5))]
    assert make_batches(ctx, batch_size=2, solo_above_chars=20) == [[ctx[0], ctx[2]], [ctx[3]], [ctx[1]]]
    assert make_batches(ctx, batch_size=8, solo_above_chars=None) == [ctx]
    assert make_batches([], batch_size=8, solo_above_chars=20) == []


def test_items_are_numbered_by_position_and_the_reply_must_answer_them_in_order() -> None:
    batch = [ReportContext(7, "p7", None, 1, "t7", "What dose?"), ReportContext(9, "p9", None, 1, "t9", "")]
    assert request_items(batch) == [{"item_id": 0, "report": "t7", "replying_to": "What dose?"}, {"item_id": 1, "report": "t9"}]
    assert response_items('[{"item_id": "0", "v": 1}, {"item_id": 1}]', [0, 1]) == {0: {"item_id": "0", "v": 1}, 1: {"item_id": 1}}
    for bad in ('[{"item_id": 1}, {"item_id": 0}]', '[{"item_id": 0}]', '[{"item_id": "x"}, {}]', '[1, 2]'):
        with pytest.raises(LLMParseError):
            response_items(bad, [0, 1])


def test_split_retries_a_malformed_reply_down_to_single_items() -> None:
    sizes: list[int] = []
    budgets: list[int] = []

    def stub(client, prompt, model=None, system=None, max_tokens=0) -> str:
        items = json.loads(prompt)["items"]
        sizes.append(len(items))
        budgets.append(max_tokens)
        return "garbage" if len(items) > 1 else json.dumps([{"item_id": 0, "value": items[0]["report"]}])

    step = Step("sys", serialize_batch, parse, write_fn=None, tokens_per_item=7)
    batch = [ReportContext(i, f"p{i}", None, 1, f"t{i}", "") for i in range(4)]

    results, dropped = extract_with_split(None, batch, step, "model", stub)

    assert results == {0: "t0", 1: "t1", 2: "t2", 3: "t3"} and dropped == 0
    assert sizes == [4, 2, 1, 1, 2, 1, 1] and budgets == [7 * n for n in sizes]

    always_bad = lambda *a, **k: "garbage"  # noqa: E731
    assert extract_with_split(None, batch[:1], step, "model", always_bad) == ({}, 0)  # a single item that stays malformed is skipped


def test_aliases_from_db_reads_the_stored_spellings_and_rejects_corrupt_json(seeded: sqlite3.Connection) -> None:
    assert aliases_from_db(seeded, "7,8-DHF") == ["tropoflavin", "78dhf"]  # blank entries dropped
    assert aliases_from_db(seeded, "ldn") == []
    assert aliases_from_db(seeded, "nope") == []
    seeded.execute("UPDATE treatment SET aliases = 'not json' WHERE id = 1")
    with pytest.raises(ValueError, match="not a JSON list"):
        aliases_from_db(seeded, "7,8-dhf")


def test_runner_counts_answered_failed_and_dropped_reports(seeded_db: Path) -> None:
    """Three reports, batches of two: the two-item batch's transient transport error fails both; the solo report answers with one row and one dropped object."""
    written: list[tuple[int, str]] = []

    def call(client, prompt, model=None, system=None, max_tokens=0) -> str:
        items = json.loads(prompt)["items"]
        if len(items) > 1:
            raise httpx.ConnectError("transport down")
        return json.dumps([{"item_id": 0, "value": "row"}])

    def setup(conn, aliases, excluded):
        assert conn.execute("SELECT 1").fetchone() and aliases == ["tropoflavin", "78dhf"] and excluded == ["x"]
        return Step("sys", serialize_batch, lambda raw, ids: parse(raw, ids, dropped=1), write, tokens_per_item=7, run_config={"extra": 1})

    def write(writer, context, value):
        written.append((context.report_id, value))
        return 1

    summary = run_report_step(None, seeded_db, "7,8-dhf", extraction_type="report_doses", setup_fn=setup,
                              excluded_compounds=["x"], workers=1, batch_size=2, solo_above_chars=None, call=call)

    assert (summary.reports, summary.reports_with_rows, summary.rows, summary.failed, summary.dropped) == (1, 1, 1, 2, 1)
    assert written == [(4, "row")]
    with sqlite3.connect(seeded_db) as conn:
        config = json.loads(conn.execute("SELECT config FROM extraction_runs WHERE run_id = ?", (summary.run_id,)).fetchone()[0])
    assert config["excluded_compounds"] == ["x"] and config["aliases"] == ["tropoflavin", "78dhf"] and config["extra"] == 1


def test_a_bug_in_a_step_aborts_the_run_instead_of_counting_as_failed(seeded_db: Path) -> None:
    """Only what llm_call gives up on (a transient failure after its retries, truncation at the largest budget) is a failed batch."""
    setup = lambda conn, aliases, excluded: Step("sys", serialize_batch, lambda raw, ids: {}["missing"], None, tokens_per_item=7)  # noqa: E731
    with pytest.raises(KeyError, match="missing"):
        run_report_step(None, seeded_db, "7,8-dhf", extraction_type="report_doses", setup_fn=setup, workers=1, call=lambda *a, **k: "[]")


def test_an_error_stops_the_queued_model_calls_and_drops_the_uncommitted_rows(seeded_db: Path) -> None:
    """workers=1 keeps at most two batches in flight: a write_fn that raises on the first report ends the run before
    the rest are called, and the rows written since the writer's last periodic commit are rolled back."""
    with sqlite3.connect(seeded_db) as conn:
        conn.executescript("".join(
            f"INSERT INTO posts (post_id, parent_id, user_id, title, body_text, scraped_at) VALUES ('x{i}', 'top', 'u1', NULL, 'Report {i}.', 0);"
            f"INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength) VALUES (1, 'x{i}', 'u1', 1, 'neutral', 'weak');"
            for i in range(8)
        ))
    calls: list[int] = []

    def call(client, prompt, model=None, system=None, max_tokens=0) -> str:
        calls.append(len(json.loads(prompt)["items"]))
        return json.dumps([{"item_id": 0, "value": "row"}])

    def write(writer, context, value) -> int:
        writer.insert_report_rows("report_doses", ("low", "high", "unit", "route", "outcome", "quote"), context.report_id, [(1.0, 1.0, "mg", None, None, "q")])
        raise RuntimeError("disk full")

    setup = lambda conn, aliases, excluded: Step("sys", serialize_batch, parse, write, tokens_per_item=7)  # noqa: E731
    with pytest.raises(RuntimeError, match="disk full"):
        run_report_step(None, seeded_db, "7,8-dhf", extraction_type="report_doses", setup_fn=setup, workers=1, batch_size=1, call=call)
    assert 1 <= len(calls) <= 3  # eleven batches: the one that failed plus at most workers * 2 already submitted
    with sqlite3.connect(seeded_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM report_doses").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM extraction_runs WHERE extraction_type = 'report_doses'").fetchone()[0] == 1  # the run row stays


def test_a_step_cannot_override_the_shared_run_config_keys(seeded_db: Path) -> None:
    setup = lambda conn, aliases, excluded: Step("sys", serialize_batch, parse, None, tokens_per_item=7, run_config={"model": "x", "extra": 1})  # noqa: E731
    with pytest.raises(ValueError, match=r"shared keys: \['model'\]"):
        run_report_step(None, seeded_db, "7,8-dhf", extraction_type="report_doses", setup_fn=setup, workers=1)


def test_step_flags_read_list_files_and_reject_empty_ones(tmp_path: Path) -> None:
    parser = argparse.ArgumentParser()
    add_step_arguments(parser)
    names = tmp_path / "names.txt"
    names.write_text(" a \n\nb\n", encoding="utf-8")
    kwargs = step_kwargs(parser, parser.parse_args(["--db", "x", "--drug", "d", "--exclude-compound", "c", "--exclude-file", str(names)]))
    assert kwargs["aliases"] is None and kwargs["excluded_compounds"] == ["c", "a", "b"] and kwargs["limit"] is None
    assert step_kwargs(parser, parser.parse_args(["--db", "x", "--drug", "d"]))["excluded_compounds"] is None
    names.write_text("\n \n", encoding="utf-8")
    with pytest.raises(SystemExit):
        step_kwargs(parser, parser.parse_args(["--db", "x", "--drug", "d", "--drug-file", str(names)]))
