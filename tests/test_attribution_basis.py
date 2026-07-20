"""The attribution basis must be recorded, not decided in the prompt.

Judgement 5 measured that crediting a collective outcome ("this stack helped") to every named
treatment inflates the per-drug positive rate ~5%. Suppressing it instead (the group guard) loses
the outcome entirely. Recording WHY the outcome is attached to the drug keeps both readings
available, so the group/no-group choice happens at query time.
"""
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from models import ClassificationResult
from prompts.intervention_config import system_prompt

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"


def test_attribution_defaults_to_specific():
    # a model that omits the field must behave exactly as before
    r = ClassificationResult(sentiment="positive", signal="strong")
    assert r.attribution == "specific"


def test_attribution_accepts_collective():
    r = ClassificationResult(sentiment="positive", signal="weak", attribution="collective")
    assert r.attribution == "collective"


def test_attribution_rejects_unknown_values():
    with pytest.raises(ValidationError):
        ClassificationResult(sentiment="positive", signal="weak", attribution="maybe")


def test_prompt_defines_both_attribution_values():
    p = system_prompt("ldn")
    assert "attribution: specific | collective" in p
    # the model must still report the sentiment — the field records the basis, it does not suppress
    assert "do NOT downgrade or suppress a collective" in p


def test_schema_has_attribution_column():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(treatment_reports)")}
    assert "attribution" in cols
    conn.close()


def test_attribution_round_trips_through_the_real_insert():
    """The exact INSERT ReportWriter.write_one issues must persist and be filterable.

    Foreign keys are disabled so the test targets the attribution column rather than
    reconstructing the whole users/posts/treatment graph.
    """
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.execute("PRAGMA foreign_keys = OFF")
    insert = ("INSERT INTO treatment_reports "
              "(run_id, post_id, user_id, drug_id, sentiment, signal_strength, side_effects, attribution) "
              "VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
    conn.execute(insert, (1, "p1", "u1", 1, "positive", "weak", None, "collective"))
    conn.execute(insert, (1, "p2", "u2", 1, "positive", "strong", None, "specific"))

    assert conn.execute("SELECT attribution FROM treatment_reports WHERE post_id='p1'").fetchone()[0] == "collective"
    # the per-drug filter an analysis would actually use: the collective row is excluded
    n_specific = conn.execute(
        "SELECT COUNT(*) FROM treatment_reports WHERE attribution = 'specific'").fetchone()[0]
    assert n_specific == 1
    conn.close()


def test_trailing_response_schema_includes_attribution():
    """Models mirror the final schema line; omitting attribution there means the key is dropped
    and ClassificationResult silently defaults it to "specific" — re-baking the bias the field
    exists to expose."""
    tail = system_prompt("ldn").rsplit("Respond ONLY with JSON:", 1)[-1]
    assert "attribution" in tail
