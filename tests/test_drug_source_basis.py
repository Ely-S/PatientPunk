"""The coreference basis must survive into treatment_reports.

classify unions drugs_direct and drugs_context to build the work queue, which loses whether a
(post, drug) pair came from the text itself or was inherited from an upstream comment. Coreference
is the pipeline's least-validated judgement, so the inherited attributions are exactly the ones an
analysis may want to exclude — or hand to a second model. Recording the basis keeps that choice at
query time.
"""
import inspect
import sqlite3
from pathlib import Path

from utilities.db import ReportWriter

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"


def test_write_one_accepts_drug_source_and_defaults_to_direct():
    params = inspect.signature(ReportWriter.write_one).parameters
    assert "drug_source" in params
    assert params["drug_source"].default == "direct"


def test_schema_has_drug_source_column():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(treatment_reports)")}
    assert "drug_source" in cols
    conn.close()


def test_direct_filter_excludes_context_inherited_rows():
    """The conservative per-drug query an analysis would actually run."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.execute("PRAGMA foreign_keys = OFF")
    insert = ("INSERT INTO treatment_reports "
              "(run_id, post_id, user_id, drug_id, sentiment, signal_strength, side_effects, "
              "attribution, drug_source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)")
    conn.execute(insert, (1, "p1", "u1", 1, "positive", "strong", None, "specific", "direct"))
    conn.execute(insert, (1, "p2", "u2", 1, "positive", "weak", None, "specific", "context"))

    total = conn.execute("SELECT COUNT(*) FROM treatment_reports").fetchone()[0]
    direct = conn.execute(
        "SELECT COUNT(*) FROM treatment_reports WHERE drug_source = 'direct'").fetchone()[0]
    assert (total, direct) == (2, 1)

    # the two bases are independent axes — a row can be specific-but-inherited
    row = conn.execute(
        "SELECT attribution, drug_source FROM treatment_reports WHERE post_id='p2'").fetchone()
    assert row == ("specific", "context")
    conn.close()


def test_empty_side_effects_is_not_collapsed_to_null():
    """`[]` is a real answer ("looked, found none"); NULL means "not captured". The old
    `if side_effects else None` wrote NULL for both."""
    src = inspect.getsource(ReportWriter.write_one)
    assert "side_effects is not None" in src
    assert "json.dumps(side_effects) if side_effects else None" not in src
