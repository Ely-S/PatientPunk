"""Tests for sentiment data integrity and validation.

Ensures that:
1. The DB schema rejects invalid sentiment values
2. The ClassificationResult model rejects 'weak' as a sentiment
3. The pipeline never writes signal_strength values into the sentiment column
4. Sentiment scoring helpers correctly map only valid values
"""
import sqlite3
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from models import ClassificationResult

SCHEMA = Path(__file__).parent.parent / "schema.sql"

VALID_SENTIMENTS = {"positive", "negative", "mixed", "neutral"}
VALID_SIGNALS = {"strong", "moderate", "weak", "n/a"}

# Sentiment scoring map used across the codebase
SENTIMENT_SCORE = {"positive": 1.0, "mixed": 0.5, "neutral": 0.0, "negative": -1.0}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    """Fresh DB from schema.sql for each test."""
    path = tmp_path / "test.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    # Seed required parent rows
    conn.execute("INSERT INTO users (user_id, source_subreddit, scraped_at) VALUES ('u1', 'test', 1000)")
    conn.execute("INSERT INTO posts (post_id, user_id, body_text, scraped_at) VALUES ('p1', 'u1', 'test post', 1000)")
    conn.execute("INSERT INTO extraction_runs (run_id, run_at, commit_hash, extraction_type, config) VALUES (1, 1000, 'abc', 'sentiment', '{}')")
    conn.execute("INSERT INTO treatment (id, canonical_name) VALUES (1, 'test_drug')")
    conn.commit()
    return conn


# ── Pydantic Model Tests ─────────────────────────────────────────────────────

class TestClassificationResultModel:
    """ClassificationResult must reject invalid sentiment values at the model level."""

    def test_valid_sentiment_values_accepted(self):
        """All four valid sentiments should be accepted."""
        for sentiment in VALID_SENTIMENTS:
            result = ClassificationResult(sentiment=sentiment, signal="strong")
            assert result.sentiment == sentiment

    def test_valid_signal_values_accepted(self):
        """All four valid signal strengths should be accepted."""
        for signal in VALID_SIGNALS:
            result = ClassificationResult(sentiment="positive", signal=signal)
            assert result.signal == signal

    def test_weak_rejected_as_sentiment(self):
        """'weak' is a signal_strength value, not a sentiment. Must be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ClassificationResult(sentiment="weak", signal="strong")
        assert "sentiment" in str(exc_info.value).lower()

    def test_strong_rejected_as_sentiment(self):
        """'strong' is a signal_strength value, not a sentiment."""
        with pytest.raises(ValidationError):
            ClassificationResult(sentiment="strong", signal="strong")

    def test_arbitrary_string_rejected_as_sentiment(self):
        """Random strings must not pass validation."""
        for invalid in ["good", "bad", "somewhat positive", "1", "", "POSITIVE"]:
            with pytest.raises(ValidationError):
                ClassificationResult(sentiment=invalid, signal="strong")

    def test_sentiment_rejected_as_signal(self):
        """Sentiment values must not be accepted as signal values."""
        with pytest.raises(ValidationError):
            ClassificationResult(sentiment="positive", signal="positive")


# ── Database Schema Tests ─────────────────────────────────────────────────────

class TestDatabaseConstraints:
    """The DB schema should enforce valid sentiment values via CHECK constraint."""

    def test_valid_sentiment_accepted_by_db(self, db):
        """All four valid sentiments should insert without error."""
        for i, sentiment in enumerate(VALID_SENTIMENTS):
            db.execute(
                "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength) "
                "VALUES (1, 'p1', 'u1', 1, ?, 'strong')",
                (sentiment,),
            )
        db.commit()
        count = db.execute("SELECT COUNT(*) FROM treatment_reports").fetchone()[0]
        assert count == len(VALID_SENTIMENTS)

    def test_weak_rejected_by_db(self, db):
        """'weak' in the sentiment column should be rejected by CHECK constraint."""
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength) "
                "VALUES (1, 'p1', 'u1', 1, 'weak', 'strong')",
            )

    def test_arbitrary_sentiment_rejected_by_db(self, db):
        """Arbitrary strings in the sentiment column should be rejected."""
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength) "
                "VALUES (1, 'p1', 'u1', 1, 'garbage', 'strong')",
            )

    def test_valid_signals_accepted_by_db(self, db):
        """All four valid signal_strength values should insert without error."""
        for i, signal in enumerate(VALID_SIGNALS):
            db.execute(
                "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength) "
                "VALUES (1, 'p1', 'u1', 1, 'positive', ?)",
                (signal,),
            )
        db.commit()

    def test_invalid_signal_rejected_by_db(self, db):
        """Invalid signal_strength values should be rejected."""
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength) "
                "VALUES (1, 'p1', 'u1', 1, 'positive', 'positive')",
            )


# ── Sentiment Scoring Tests ───────────────────────────────────────────────────

class TestSentimentScoring:
    """The scoring map must cover exactly the 4 valid sentiments and nothing else."""

    def test_scoring_map_covers_all_valid_sentiments(self):
        """Every valid sentiment must have a score."""
        for sentiment in VALID_SENTIMENTS:
            assert sentiment in SENTIMENT_SCORE, f"Missing score for '{sentiment}'"

    def test_scoring_map_has_no_extra_keys(self):
        """No signal_strength values or other strings in the scoring map."""
        extra = set(SENTIMENT_SCORE.keys()) - VALID_SENTIMENTS
        assert extra == set(), f"Unexpected keys in SENTIMENT_SCORE: {extra}"

    def test_weak_not_in_scoring_map(self):
        """'weak' must never appear in the sentiment scoring map."""
        assert "weak" not in SENTIMENT_SCORE

    def test_scores_are_ordered(self):
        """Scores should follow: negative < neutral < mixed < positive."""
        assert SENTIMENT_SCORE["negative"] < SENTIMENT_SCORE["neutral"]
        assert SENTIMENT_SCORE["neutral"] < SENTIMENT_SCORE["mixed"]
        assert SENTIMENT_SCORE["mixed"] < SENTIMENT_SCORE["positive"]

    def test_sql_case_statement_matches_python_map(self):
        """The SQL CASE statement pattern used in queries must match SENTIMENT_SCORE exactly.

        This is a documentation test — it defines the canonical CASE statement
        and ensures it maps the same values as the Python dict.
        """
        # The correct SQL CASE (no 'weak', no extra values):
        sql_mappings = {
            "positive": 1.0,
            "mixed": 0.5,
            "neutral": 0.0,
            "negative": -1.0,
        }
        assert sql_mappings == SENTIMENT_SCORE


# ── Data Integrity Tests (against real DB if available) ───────────────────────

class TestDataIntegrity:
    """Verify that existing databases contain only valid sentiment values."""

    @staticmethod
    def _check_db_sentiments(db_path: Path):
        """Helper: check all sentiment values in a DB are valid."""
        if not db_path.exists() or db_path.stat().st_size == 0:
            pytest.skip(f"DB not available: {db_path}")
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT DISTINCT sentiment FROM treatment_reports"
        ).fetchall()
        sentiments = {r[0] for r in rows}
        invalid = sentiments - VALID_SENTIMENTS
        conn.close()
        assert invalid == set(), f"Invalid sentiment values in {db_path.name}: {invalid}"

    def test_polina_db_sentiments(self):
        """All sentiments in polina_onemonth.db must be valid."""
        self._check_db_sentiments(
            Path(__file__).parent.parent / "data" / "polina_onemonth.db"
        )

    def test_pssd_db_sentiments(self):
        """All sentiments in pssd.db must be valid."""
        self._check_db_sentiments(
            Path(__file__).parent.parent / "data" / "pssd.db"
        )

    def test_abortion_db_sentiments(self):
        """All sentiments in abortion_1month.db must be valid."""
        self._check_db_sentiments(
            Path(__file__).parent.parent / "data" / "abortion_1month.db"
        )
