"""Tests for structured side-effect severity extraction and storage."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from models import ClassificationResult, SideEffectReport
from utilities.db import ReportWriter


def test_classification_result_accepts_explicit_and_unspecified_severity():
    result = ClassificationResult.model_validate({
        "sentiment": "positive",
        "signal": "strong",
        "side_effects": [
            {"side_effect": "headache", "severity": "mild"},
            {"side_effect": "insomnia", "severity": None},
        ],
    })

    assert result.side_effects == [
        SideEffectReport(side_effect="headache", severity="mild"),
        SideEffectReport(side_effect="insomnia", severity=None),
    ]


def test_classification_result_rejects_unknown_severity():
    with pytest.raises(ValidationError):
        ClassificationResult.model_validate({
            "sentiment": "negative",
            "signal": "moderate",
            "side_effects": [
                {"side_effect": "headache", "severity": "extreme"},
            ],
        })


def test_report_writer_stores_structured_side_effects(tmp_path: Path):
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
            sentiment="negative",
            signal="strong",
            side_effects=[
                SideEffectReport(side_effect="headache", severity="severe"),
                SideEffectReport(side_effect="insomnia"),
            ],
        )

    with sqlite3.connect(db_path) as conn:
        stored = conn.execute(
            "SELECT side_effects FROM treatment_reports"
        ).fetchone()[0]

    assert json.loads(stored) == [
        {"side_effect": "headache", "severity": "severe"},
        {"side_effect": "insomnia", "severity": None},
    ]
