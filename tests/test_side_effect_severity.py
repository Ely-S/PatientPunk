"""Tests for structured side-effect severity extraction and storage."""

import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from models import ClassificationResult, SideEffectReport
from utilities.db import ReportWriter


def test_side_effect_report_rejects_unknown_severity() -> None:
    with pytest.raises(ValidationError, match="severity"):
        SideEffectReport.model_validate({
            "side_effect": "headache", "severity": "extreme",
        })


def test_classification_side_effects_round_trip_to_database(tmp_path: Path) -> None:
    result = ClassificationResult.model_validate({
        "sentiment": "negative",
        "signal": "strong",
        "side_effects": [
            {"side_effect": "headache", "severity": "mild"},
            {"side_effect": "dizziness", "severity": "severe"},
            {"side_effect": "insomnia", "severity": None},
            {"side_effect": "nausea"},
        ],
    })
    db_path = tmp_path / "reports.db"
    schema_path = Path(__file__).parents[1] / "schema.sql"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO treatment (canonical_name) VALUES (?)",
            ("7,8-dhf",),
        )

    with ReportWriter(db_path, run_config={}, commit_hash="test") as writer:
        assert writer.write_one(
            post_id="post-1",
            drug="7,8-dhf",
            author="author-1",
            sentiment=result.sentiment,
            signal=result.signal,
            side_effects=result.side_effects,
        )

    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            "SELECT side_effects FROM treatment_reports"
        ).fetchone()[0]

    assert json.loads(stored) == [
        {"side_effect": "headache", "severity": "mild"},
        {"side_effect": "dizziness", "severity": "severe"},
        {"side_effect": "insomnia", "severity": None},
        {"side_effect": "nausea", "severity": None},
    ]
