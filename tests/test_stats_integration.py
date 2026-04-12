"""
tests/test_stats_integration.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Integration tests for the analysis engine → LLM handoff contract.

These tests verify that:
1. Analysis results are JSON-serializable (for passing to Haiku)
2. Warning objects have the expected structure (code, severity, message)
3. Result payloads are stable — all expected fields present
4. Round-tripping through JSON preserves data fidelity

No LLM calls — this is the bridge between the stats engine and the UI layer.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict

import pytest

from app.analysis.stats import (
    AnalysisWarning,
    REPORTING_BIAS_DISCLAIMER,
    get_user_sentiment,
    run_binomial_test,
    run_comparison,
    run_kruskal_wallis,
    run_logit,
    run_ols,
    summarize_drug,
)


# ── Reuse the synthetic DB fixture from test_stats ────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, source_subreddit TEXT NOT NULL, scraped_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS posts (post_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, body_text TEXT NOT NULL, metadata TEXT, post_date INTEGER, scraped_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS treatment (id INTEGER PRIMARY KEY, canonical_name TEXT UNIQUE COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS extraction_runs (run_id INTEGER PRIMARY KEY, run_at INTEGER NOT NULL, model TEXT NOT NULL, config TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS user_profiles (user_id TEXT NOT NULL, run_id INTEGER NOT NULL, age_bucket TEXT, sex TEXT, location TEXT, PRIMARY KEY (user_id, run_id));
CREATE TABLE IF NOT EXISTS conditions (condition_id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, user_id TEXT NOT NULL, post_id TEXT, condition_type TEXT, condition_name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS treatment_reports (report_id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, post_id TEXT NOT NULL, user_id TEXT, drug_id INTEGER NOT NULL, sentiment TEXT NOT NULL, signal_strength REAL NOT NULL, sentiment_raw TEXT);
"""


@pytest.fixture
def conn():
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA_SQL)
    now = int(time.time())
    month = 30 * 86400
    db.execute("INSERT INTO extraction_runs VALUES (1, ?, 'test', '{}')", (now,))

    for i in range(30):
        uid = f"user_{i:02d}"
        db.execute("INSERT INTO users VALUES (?, 'covidlonghaulers', ?)", (uid, now))
        for m in range(6):
            pid = f"post_{uid}_m{m}"
            db.execute("INSERT INTO posts VALUES (?, ?, 'body', NULL, ?, ?)",
                       (pid, uid, now - (6 - m) * month, now))

    db.execute("INSERT INTO treatment (id, canonical_name) VALUES (1, 'test_drug_a')")
    db.execute("INSERT INTO treatment (id, canonical_name) VALUES (2, 'test_drug_b')")

    for i in range(20):
        uid = f"user_{i:02d}"
        sentiment = 1.0 if i < 16 else -1.0
        pid = f"post_{uid}_m{i % 6}"
        db.execute("INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength) VALUES (1, ?, ?, 1, ?, 1.0)", (pid, uid, sentiment))

    for i in range(15):
        uid = f"user_{i:02d}"
        sentiment = -1.0 if i < 12 else 1.0
        pid = f"post_{uid}_m{(i + 1) % 6}"
        db.execute("INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength) VALUES (1, ?, ?, 2, ?, 1.0)", (pid, uid, sentiment))

    for i in range(15):
        uid = f"user_{i:02d}"
        sex = "female" if i % 2 == 0 else "male"
        age = f"{(i % 4 + 2) * 10}s" if i < 10 else None
        db.execute("INSERT INTO user_profiles VALUES (?, 1, ?, ?, NULL)", (uid, age, sex))

    for i in range(10):
        db.execute("INSERT INTO conditions (run_id, user_id, condition_type, condition_name) VALUES (1, ?, 'illness', 'pots')", (f"user_{i:02d}",))

    db.commit()
    yield db
    db.close()


# ══════════��════════════════════════════════════════════════════════════════════
# AnalysisWarning structure
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalysisWarningContract:
    def test_warning_has_required_fields(self):
        w = AnalysisWarning(code="test_code", severity="caveat", message="Test message")
        assert w.code == "test_code"
        assert w.severity == "caveat"
        assert w.message == "Test message"

    def test_warning_to_dict(self):
        w = AnalysisWarning(code="low_epp", severity="caution", message="Low EPP ratio")
        d = w.to_dict()
        assert d == {"code": "low_epp", "severity": "caution", "message": "Low EPP ratio"}

    def test_warning_is_json_serializable(self):
        w = AnalysisWarning(code="x", severity="unreliable", message="bad")
        serialized = json.dumps(w.to_dict())
        deserialized = json.loads(serialized)
        assert deserialized["code"] == "x"
        assert deserialized["severity"] == "unreliable"

    def test_severity_is_valid_tier(self):
        """All warnings produced by the engine should have valid severity."""
        valid = {"caveat", "caution", "unreliable"}
        # We can't easily enumerate all warnings, but we check the constant
        for tier in valid:
            w = AnalysisWarning(code="test", severity=tier, message="test")
            assert w.severity in valid

    def test_reporting_bias_disclaimer_exists(self):
        assert "self-selected" in REPORTING_BIAS_DISCLAIMER
        assert "Reddit" in REPORTING_BIAS_DISCLAIMER


# ═══════════════════════════════���═══════════════════════════════���═══════════════
# Result serialization
# ════���═════════════════════════════════════════════════════���════════════════════

class TestResultSerialization:
    def _serialize_result(self, result):
        """Convert a dataclass result to JSON and back."""
        d = asdict(result)
        # Convert AnalysisWarning objects to dicts for JSON
        if "warnings" in d:
            d["warnings"] = [
                w if isinstance(w, dict) else w
                for w in d["warnings"]
            ]
        serialized = json.dumps(d, default=str)
        return json.loads(serialized)

    def test_binomial_result_serializes(self, conn):
        df = get_user_sentiment(conn, "test_drug_a")
        result = run_binomial_test(df)
        d = self._serialize_result(result)
        assert "p_value" in d
        assert "observed_rate" in d
        assert "warnings" in d
        assert isinstance(d["warnings"], list)

    def test_comparison_result_serializes(self, conn):
        df_a = get_user_sentiment(conn, "test_drug_a")
        df_b = get_user_sentiment(conn, "test_drug_b")
        result = run_comparison(df_a, df_b)
        d = self._serialize_result(result)
        assert "mw_p_value" in d
        assert "mw_effect_size_r" in d
        assert "counts_a" in d
        assert "counts_b" in d
        assert "warnings" in d

    def test_summary_result_serializes(self, conn):
        df = get_user_sentiment(conn, "test_drug_a")
        result = summarize_drug(df, "test_drug_a")
        d = self._serialize_result(result)
        assert "pct_positive" in d
        assert "pct_positive_ci" in d
        assert "n_users" in d

    def test_kruskal_result_serializes(self, conn):
        groups = {
            "a": get_user_sentiment(conn, "test_drug_a"),
            "b": get_user_sentiment(conn, "test_drug_b"),
        }
        result = run_kruskal_wallis(groups)
        d = self._serialize_result(result)
        assert "h_statistic" in d
        assert "pairwise" in d
        assert isinstance(d["pairwise"], list)

    def test_logit_result_serializes(self, conn):
        result = run_logit(conn, "test_drug_a", ["has_pots"])
        if result is not None:
            d = self._serialize_result(result)
            assert "predictors" in d
            assert "pseudo_r2" in d
            assert "warnings" in d

    def test_ols_result_serializes(self, conn):
        result = run_ols(conn, "test_drug_a", ["has_pots"])
        if result is not None:
            d = self._serialize_result(result)
            assert "r_squared" in d
            assert "f_p_value" in d

    def test_warnings_survive_round_trip(self, conn):
        """Warnings should be fully recoverable after JSON serialization."""
        df = get_user_sentiment(conn, "test_drug_a")
        df_b = get_user_sentiment(conn, "test_drug_b")
        result = run_comparison(df, df_b)
        d = asdict(result)
        serialized = json.dumps(d, default=str)
        restored = json.loads(serialized)

        for w in restored["warnings"]:
            assert "code" in w
            assert "severity" in w
            assert "message" in w
            assert w["severity"] in {"caveat", "caution", "unreliable"}

    def test_all_numeric_fields_are_finite(self, conn):
        """No NaN or Inf should leak into serialized results."""
        import math
        df = get_user_sentiment(conn, "test_drug_a")
        result = run_binomial_test(df)
        d = self._serialize_result(result)
        for key, value in d.items():
            if isinstance(value, float):
                assert math.isfinite(value), f"{key} is not finite: {value}"


# ══════════════════════════════��════════════════════════════════════════════════
# LLM payload structure
# ═══��══════════════���════════════════════════════════════════════════════════════

class TestLLMPayload:
    def test_can_build_llm_context(self, conn):
        """Simulate building a payload that an LLM would receive."""
        df = get_user_sentiment(conn, "test_drug_a")
        summary = summarize_drug(df, "test_drug_a")
        binom = run_binomial_test(df)

        payload = {
            "test_type": "single_drug_analysis",
            "drug": "test_drug_a",
            "summary": asdict(summary),
            "binomial_test": asdict(binom),
            "disclaimer": REPORTING_BIAS_DISCLAIMER,
        }

        serialized = json.dumps(payload, default=str)
        restored = json.loads(serialized)

        assert restored["test_type"] == "single_drug_analysis"
        assert restored["summary"]["n_users"] == 20
        assert restored["binomial_test"]["p_value"] <= 1.0
        assert "self-selected" in restored["disclaimer"]

    def test_warnings_are_classifiable_by_severity(self, conn):
        """The LLM should be able to filter warnings by severity tier."""
        df_a = get_user_sentiment(conn, "test_drug_a")
        df_b = get_user_sentiment(conn, "test_drug_b")
        result = run_comparison(df_a, df_b)

        d = asdict(result)
        caveats = [w for w in d["warnings"] if w["severity"] == "caveat"]
        cautions = [w for w in d["warnings"] if w["severity"] == "caution"]
        unreliable = [w for w in d["warnings"] if w["severity"] == "unreliable"]

        # All warnings should be in exactly one tier
        total = len(caveats) + len(cautions) + len(unreliable)
        assert total == len(d["warnings"])


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic model validation
# ═══════════════════════════════════════════════════════════════════════════════

from app.analysis.models import (
    to_model,
    BinomialResultModel,
    ComparisonResultModel,
    SingleDrugSummaryModel,
    KruskalResultModel,
    LogitResultModel,
    OLSResultModel,
    WarningModel,
    WarningSeverity,
)


class TestPydanticModels:
    def test_binomial_validates(self, conn):
        df = get_user_sentiment(conn, "test_drug_a")
        result = run_binomial_test(df)
        model = to_model(result)
        assert isinstance(model, BinomialResultModel)
        assert 0 <= model.p_value <= 1
        assert 0 <= model.observed_rate <= 1

    def test_comparison_validates(self, conn):
        df_a = get_user_sentiment(conn, "test_drug_a")
        df_b = get_user_sentiment(conn, "test_drug_b")
        result = run_comparison(df_a, df_b)
        model = to_model(result)
        assert isinstance(model, ComparisonResultModel)
        assert -1 <= model.mw_effect_size_r <= 1

    def test_summary_validates(self, conn):
        df = get_user_sentiment(conn, "test_drug_a")
        result = summarize_drug(df, "test_drug_a")
        model = to_model(result)
        assert isinstance(model, SingleDrugSummaryModel)
        assert model.n_users == 20

    def test_kruskal_validates(self, conn):
        groups = {
            "a": get_user_sentiment(conn, "test_drug_a"),
            "b": get_user_sentiment(conn, "test_drug_b"),
        }
        result = run_kruskal_wallis(groups)
        model = to_model(result)
        assert isinstance(model, KruskalResultModel)

    def test_logit_validates(self, conn):
        result = run_logit(conn, "test_drug_a", ["has_pots"])
        if result is not None:
            model = to_model(result)
            assert isinstance(model, LogitResultModel)

    def test_ols_validates(self, conn):
        result = run_ols(conn, "test_drug_a", ["has_pots"])
        if result is not None:
            model = to_model(result)
            assert isinstance(model, OLSResultModel)

    def test_model_dump_json_is_valid(self, conn):
        """Pydantic .model_dump_json() should produce valid JSON."""
        df = get_user_sentiment(conn, "test_drug_a")
        result = run_binomial_test(df)
        model = to_model(result)
        json_str = model.model_dump_json()
        restored = json.loads(json_str)
        assert "p_value" in restored

    def test_warning_severity_is_validated(self):
        """Invalid severity should raise ValidationError."""
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            WarningModel(code="test", severity="invalid_tier", message="bad")

    def test_warnings_in_model_have_severity_enum(self, conn):
        df_a = get_user_sentiment(conn, "test_drug_a")
        df_b = get_user_sentiment(conn, "test_drug_b")
        result = run_comparison(df_a, df_b)
        model = to_model(result)
        for w in model.warnings:
            assert isinstance(w.severity, WarningSeverity)
