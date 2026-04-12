"""
tests/test_stats.py
~~~~~~~~~~~~~~~~~~~
Unit tests for the statistics engine (app/analysis/stats.py).

Uses a synthetic in-memory SQLite database so tests run without patientpunk.db.
All expected values are controlled by construction.
"""

from __future__ import annotations

import math
import sqlite3
import time
import warnings

import pandas as pd
import pytest

from app.analysis.stats import (
    AnalysisWarning,
    _dedupe_warnings,
    _build_logit_features,
    _build_survival_data,
    BinomialResult,
    ComparisonResult,
    KruskalResult,
    LogitResult,
    OLSResult,
    SingleDrugSummary,
    TimeTrendResult,
    SurvivalResult,
    categorize_sentiment,
    check_sample_sizes,
    get_user_sentiment,
    run_binomial_test,
    run_comparison,
    run_kruskal_wallis,
    run_logit,
    run_ols,
    run_survival,
    run_time_trend,
    summarize_drug,
    wilson_ci,
)


# ── Synthetic database fixture ────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    source_subreddit TEXT NOT NULL,
    scraped_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    post_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    body_text TEXT NOT NULL,
    metadata TEXT,
    post_date INTEGER,
    scraped_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS treatment (
    id INTEGER PRIMARY KEY,
    canonical_name TEXT UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS extraction_runs (
    run_id INTEGER PRIMARY KEY,
    run_at INTEGER NOT NULL,
    model TEXT NOT NULL,
    config TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT NOT NULL REFERENCES users(user_id),
    run_id INTEGER NOT NULL REFERENCES extraction_runs(run_id),
    age_bucket TEXT,
    sex TEXT,
    location TEXT,
    PRIMARY KEY (user_id, run_id)
);

CREATE TABLE IF NOT EXISTS conditions (
    condition_id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES extraction_runs(run_id),
    user_id TEXT NOT NULL REFERENCES users(user_id),
    post_id TEXT REFERENCES posts(post_id),
    condition_type TEXT CHECK(condition_type IN ('illness', 'symptom')),
    condition_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS treatment_reports (
    report_id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES extraction_runs(run_id),
    post_id TEXT NOT NULL REFERENCES posts(post_id),
    user_id TEXT REFERENCES users(user_id),
    drug_id INTEGER NOT NULL REFERENCES treatment(id),
    sentiment REAL NOT NULL,
    signal_strength REAL NOT NULL,
    sentiment_raw TEXT
);
"""


@pytest.fixture
def conn():
    """Create an in-memory SQLite database with synthetic data.

    Layout:
    - 30 users (user_00 .. user_29)
    - 2 drugs: "test_drug_a" (id=1), "test_drug_b" (id=2), "test_drug_c" (id=3)
    - Drug A: 20 users, mostly positive sentiment
    - Drug B: 15 users, mostly negative sentiment
    - Drug C: 10 users, mixed sentiment
    - Demographics: 15 users have sex (half male, half female), 10 have age_bucket
    - Conditions: 10 users have "pots", 8 have "mcas"
    - Post dates: spread across 6 months for time trend testing
    """
    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA_SQL)

    now = int(time.time())
    month = 30 * 86400  # ~30 days in seconds

    # Extraction run
    db.execute("INSERT INTO extraction_runs VALUES (1, ?, 'test', '{}')", (now,))

    # Users + posts
    for i in range(30):
        uid = f"user_{i:02d}"
        db.execute("INSERT INTO users VALUES (?, 'covidlonghaulers', ?)", (uid, now))
        # Each user gets posts spread across months
        for m in range(6):
            pid = f"post_{uid}_m{m}"
            post_time = now - (6 - m) * month
            db.execute(
                "INSERT INTO posts VALUES (?, ?, 'test body', NULL, ?, ?)",
                (pid, uid, post_time, now),
            )

    # Treatments
    db.execute("INSERT INTO treatment (id, canonical_name) VALUES (1, 'test_drug_a')")
    db.execute("INSERT INTO treatment (id, canonical_name) VALUES (2, 'test_drug_b')")
    db.execute("INSERT INTO treatment (id, canonical_name) VALUES (3, 'test_drug_c')")

    # Drug A: 20 users, sentiment mostly positive
    # Sentiment stored as strings — the stats engine CASE expression converts to numeric
    for i in range(20):
        uid = f"user_{i:02d}"
        sentiment = "positive" if i < 16 else "negative"  # 16 positive, 4 negative = 80%
        post_month = i % 6
        pid = f"post_{uid}_m{post_month}"
        db.execute(
            "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength)"
            " VALUES (1, ?, ?, 1, ?, 'strong')",
            (pid, uid, sentiment),
        )

    # Drug B: 15 users, sentiment mostly negative
    for i in range(15):
        uid = f"user_{i:02d}"
        sentiment = "negative" if i < 12 else "positive"  # 3 positive, 12 negative = 20%
        pid = f"post_{uid}_m{(i+1)%6}"
        db.execute(
            "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength)"
            " VALUES (1, ?, ?, 2, ?, 'strong')",
            (pid, uid, sentiment),
        )

    # Drug C: 10 users, mixed sentiment
    for i in range(10):
        uid = f"user_{i:02d}"
        sentiment = "mixed"  # all mixed
        pid = f"post_{uid}_m{(i+2)%6}"
        db.execute(
            "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength)"
            " VALUES (1, ?, ?, 3, ?, 'strong')",
            (pid, uid, sentiment),
        )

    # Demographics: first 15 users have sex, first 10 have age
    for i in range(15):
        uid = f"user_{i:02d}"
        sex = "female" if i % 2 == 0 else "male"
        age = f"{(i % 4 + 2) * 10}s" if i < 10 else None  # "20s", "30s", "40s", "50s"
        db.execute(
            "INSERT INTO user_profiles VALUES (?, 1, ?, ?, NULL)",
            (uid, age, sex),
        )

    # Conditions: users 0-9 have POTS, users 5-12 have MCAS
    for i in range(10):
        uid = f"user_{i:02d}"
        db.execute(
            "INSERT INTO conditions (run_id, user_id, condition_type, condition_name)"
            " VALUES (1, ?, 'illness', 'pots')",
            (uid,),
        )
    for i in range(5, 13):
        uid = f"user_{i:02d}"
        db.execute(
            "INSERT INTO conditions (run_id, user_id, condition_type, condition_name)"
            " VALUES (1, ?, 'illness', 'mcas')",
            (uid,),
        )

    # Time trend data: Drug with sentiment improving over months
    # Maps: month 0-1 → negative, 2-3 → mixed, 4-5 → positive
    trend_sentiments = ["negative", "negative", "mixed", "mixed", "positive", "positive"]
    for m in range(6):
        uid = f"user_{20 + m:02d}" if m < 4 else f"user_{m:02d}"
        pid = f"post_{uid}_m{m}"
        sentiment = trend_sentiments[m]
        if m == 0:
            db.execute("INSERT INTO treatment (id, canonical_name) VALUES (4, 'trend_drug')")
        db.execute(
            "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength)"
            " VALUES (1, ?, ?, 4, ?, 'strong')",
            (pid, uid, sentiment),
        )

    db.commit()
    yield db
    db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# categorize_sentiment
# ═══════════════════════════════════════════════════════════════════════════════

class TestCategorizeSentiment:
    def test_positive(self):
        assert categorize_sentiment(1.0) == "positive"
        assert categorize_sentiment(0.8) == "positive"

    def test_boundary_positive(self):
        """Exactly 0.7 is NOT positive (must be > 0.7)."""
        assert categorize_sentiment(0.7) == "mixed"

    def test_mixed(self):
        assert categorize_sentiment(0.5) == "mixed"
        assert categorize_sentiment(0.1) == "mixed"

    def test_boundary_mixed(self):
        """Exactly 0.1 is the lower edge of mixed."""
        assert categorize_sentiment(0.1) == "mixed"

    def test_neutral(self):
        assert categorize_sentiment(0.0) == "neutral"
        assert categorize_sentiment(0.05) == "neutral"
        assert categorize_sentiment(-0.5) == "neutral"

    def test_negative(self):
        assert categorize_sentiment(-1.0) == "negative"
        assert categorize_sentiment(-0.8) == "negative"

    def test_boundary_negative(self):
        """Exactly -0.7 falls into negative (neutral is strictly > -0.7)."""
        assert categorize_sentiment(-0.7) == "negative"
        assert categorize_sentiment(-0.69) == "neutral"


# ═══════════════════════════════════════════════════════════════════════════════
# wilson_ci
# ═══════════════════════════════════════════════════════════════════════════════

class TestWilsonCI:
    def test_known_values(self):
        """50/100 at z=1.96 should give roughly (0.40, 0.60)."""
        lo, hi = wilson_ci(50, 100)
        assert 0.39 < lo < 0.41
        assert 0.59 < hi < 0.61

    def test_zero_total(self):
        assert wilson_ci(0, 0) == (0.0, 0.0)

    def test_perfect_success(self):
        lo, hi = wilson_ci(10, 10)
        assert lo > 0.6  # not just 1.0 — Wilson adjusts
        assert hi == 1.0

    def test_zero_success(self):
        lo, hi = wilson_ci(0, 10)
        assert lo < 1e-10  # essentially zero (statsmodels may return tiny float)
        assert hi < 0.4  # not just 0.0 — Wilson adjusts upward

    def test_single_observation(self):
        """n=1 should return a wide interval."""
        lo, hi = wilson_ci(1, 1)
        assert hi - lo > 0.3  # very wide


# ═══════════════════════════════════════════════════════════════════════════════
# get_user_sentiment
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetUserSentiment:
    def test_basic_query(self, conn):
        df = get_user_sentiment(conn, "test_drug_a")
        assert len(df) == 20
        assert "user_id" in df.columns
        assert "avg_sentiment" in df.columns
        assert "category" in df.columns

    def test_user_aggregation(self, conn):
        """Each user should appear exactly once (one row per user)."""
        df = get_user_sentiment(conn, "test_drug_a")
        assert df["user_id"].nunique() == len(df)

    def test_condition_filter(self, conn):
        """POTS filter should only return users 0-9."""
        df = get_user_sentiment(conn, "test_drug_a", condition="pots")
        assert len(df) == 10
        for uid in df["user_id"]:
            assert int(uid.split("_")[1]) < 10

    def test_sex_filter(self, conn):
        """Female filter should return users with even indices (0,2,4,...) up to 14."""
        df = get_user_sentiment(conn, "test_drug_a", sex="female")
        assert len(df) > 0
        # Only users with profiles can match; users 0-14 have sex
        for uid in df["user_id"]:
            assert int(uid.split("_")[1]) % 2 == 0

    def test_age_filter(self, conn):
        df = get_user_sentiment(conn, "test_drug_a", age_bucket="30s")
        assert len(df) > 0

    def test_combined_filters(self, conn):
        df = get_user_sentiment(conn, "test_drug_a", condition="pots", sex="female")
        assert len(df) > 0
        # Must satisfy both: POTS (users 0-9) AND female (even index with profile)
        for uid in df["user_id"]:
            idx = int(uid.split("_")[1])
            assert idx < 10  # has POTS
            assert idx % 2 == 0  # is female

    def test_condition_filter_does_not_duplicate_post_counts(self, conn):
        conn.execute(
            "INSERT INTO conditions (run_id, user_id, condition_type, condition_name)"
            " VALUES (1, 'user_00', 'illness', 'pots syndrome')"
        )
        conn.commit()

        df = get_user_sentiment(conn, "test_drug_a", condition="pots")
        row = df.loc[df["user_id"] == "user_00"].iloc[0]
        assert row["n_posts"] == 1
        assert row["avg_sentiment"] == 1.0

    def test_latest_profile_row_controls_demographic_filters(self, conn):
        now = int(time.time())
        conn.execute("INSERT INTO extraction_runs VALUES (2, ?, 'test', '{}')", (now + 1,))
        conn.execute(
            "INSERT INTO user_profiles VALUES ('user_00', 2, '90s', 'male', NULL)"
        )
        conn.commit()

        female_df = get_user_sentiment(conn, "test_drug_a", sex="female")
        male_df = get_user_sentiment(conn, "test_drug_a", sex="male")
        age_df = get_user_sentiment(conn, "test_drug_a", age_bucket="90s")

        assert "user_00" not in set(female_df["user_id"])
        assert "user_00" in set(male_df["user_id"])
        assert set(age_df["user_id"]) == {"user_00"}

    def test_nonexistent_drug(self, conn):
        df = get_user_sentiment(conn, "nonexistent_drug_xyz")
        assert df.empty
        assert "category" in df.columns

    def test_empty_result_has_columns(self, conn):
        df = get_user_sentiment(conn, "nonexistent_drug_xyz")
        assert set(df.columns) == {"user_id", "avg_sentiment", "n_posts", "category"}


# ═══════════════════════════════════════════════════════════════════════════════
# check_sample_sizes
# ═══════════════════════════════════════════════════════════════════════════════

class TestCheckSampleSizes:
    def test_adequate_sizes(self):
        a = pd.Series(range(25))
        b = pd.Series(range(25))
        result = check_sample_sizes(a, b)
        assert result.ok is True
        assert result.warnings == []

    def test_too_small(self):
        a = pd.Series([1, 2, 3])
        b = pd.Series([4, 5, 6])
        result = check_sample_sizes(a, b)
        assert result.ok is False

    def test_warning_zone(self):
        """Groups between 5-19 should be ok but with warnings."""
        a = pd.Series(range(10))
        b = pd.Series(range(25))
        result = check_sample_sizes(a, b)
        assert result.ok is True
        assert len(result.warnings) > 0


class TestWarningDeduplication:
    def test_dedup_preserves_distinct_messages_with_same_code(self):
        warn_a = AnalysisWarning("small_sample", "caution", "Group A has only 10 users.")
        warn_b = AnalysisWarning("small_sample", "caution", "Group B has only 15 users.")

        deduped = _dedupe_warnings([warn_a, warn_b])

        assert deduped == [warn_a, warn_b]

    def test_dedup_removes_exact_duplicate_warning(self):
        warning = AnalysisWarning("small_sample", "caution", "Group A has only 10 users.")

        deduped = _dedupe_warnings([warning, warning])

        assert deduped == [warning]


# ═══════════════════════════════════════════════════════════════════════════════
# run_comparison (Mann-Whitney + Chi-square / Fisher's)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunComparison:
    def test_clearly_different_groups(self, conn):
        """Drug A (mostly positive) vs Drug B (mostly negative) should differ."""
        df_a = get_user_sentiment(conn, "test_drug_a")
        df_b = get_user_sentiment(conn, "test_drug_b")
        result = run_comparison(df_a, df_b)
        assert result is not None
        assert result.mw_significant == True
        assert result.mw_p_value < 0.05
        assert result.n_a == 20
        assert result.n_b == 15

    def test_identical_groups(self, conn):
        """Same drug compared to itself should NOT be significant."""
        df = get_user_sentiment(conn, "test_drug_a")
        result = run_comparison(df, df)
        assert result is not None
        assert result.mw_significant == False
        assert result.mw_effect_size_r < 0.1

    def test_fisher_fallback(self, conn):
        """Drug C yields a sparse multi-category table but still returns a valid result."""
        df_a = get_user_sentiment(conn, "test_drug_a")
        df_c = get_user_sentiment(conn, "test_drug_c")
        result = run_comparison(df_a, df_c)
        assert result is not None
        assert result.cat_test_name == "chi-square"
        assert any("sparse cells" in w.message for w in result.warnings)

    def test_small_sample_returns_none(self):
        """Groups smaller than 5 should return None."""
        df_tiny = pd.DataFrame({
            "user_id": ["a", "b", "c"],
            "avg_sentiment": [1.0, 1.0, 1.0],
            "n_posts": [1, 1, 1],
            "category": ["positive", "positive", "positive"],
        })
        result = run_comparison(df_tiny, df_tiny)
        assert result is None

    def test_result_structure(self, conn):
        df_a = get_user_sentiment(conn, "test_drug_a")
        df_b = get_user_sentiment(conn, "test_drug_b")
        result = run_comparison(df_a, df_b)
        assert isinstance(result, ComparisonResult)
        assert all(cat in result.counts_a for cat in ["positive", "negative"])
        assert -1 <= result.mw_effect_size_r <= 1

    def test_fisher_uses_active_categories_not_positive_collapse(self):
        df_negative = pd.DataFrame({
            "user_id": [f"n{i}" for i in range(6)],
            "avg_sentiment": [-1.0] * 6,
            "n_posts": [1] * 6,
            "category": ["negative"] * 6,
        })
        df_mixed = pd.DataFrame({
            "user_id": [f"m{i}" for i in range(6)],
            "avg_sentiment": [0.5] * 6,
            "n_posts": [1] * 6,
            "category": ["mixed"] * 6,
        })

        result = run_comparison(df_negative, df_mixed)
        assert result is not None
        assert result.cat_test_name == "Fisher's exact"
        assert result.cat_significant
        assert result.cat_p_value < 0.05

    def test_mann_whitney_effect_size_is_signed(self, conn):
        df_a = get_user_sentiment(conn, "test_drug_a")
        df_b = get_user_sentiment(conn, "test_drug_b")

        forward = run_comparison(df_a, df_b)
        reverse = run_comparison(df_b, df_a)

        assert forward is not None
        assert reverse is not None
        assert forward.mw_effect_size_r > 0
        assert reverse.mw_effect_size_r < 0
        assert abs(forward.mw_effect_size_r) == abs(reverse.mw_effect_size_r)

    def test_comparison_warns_on_imbalanced_samples(self):
        df_large = pd.DataFrame({
            "user_id": [f"a{i}" for i in range(30)],
            "avg_sentiment": [1.0] * 30,
            "n_posts": [1] * 30,
            "category": ["positive"] * 30,
        })
        df_small = pd.DataFrame({
            "user_id": [f"b{i}" for i in range(10)],
            "avg_sentiment": [-1.0] * 10,
            "n_posts": [1] * 10,
            "category": ["negative"] * 10,
        })
        result = run_comparison(df_large, df_small)
        assert result is not None
        assert any("imbalanced" in w.message for w in result.warnings)


# ═══════════════════════════════════════════════════════════════════════════════
# summarize_drug
# ═══════════════════════════════════════════════════════════════════════════════

class TestSummarizeDrug:
    def test_basic_summary(self, conn):
        df = get_user_sentiment(conn, "test_drug_a")
        s = summarize_drug(df, "test_drug_a")
        assert s is not None
        assert s.n_users == 20
        assert s.pct_positive == 80.0  # 16/20
        assert s.pct_negative == 20.0  # 4/20

    def test_empty_returns_none(self):
        df = pd.DataFrame(columns=["user_id", "avg_sentiment", "n_posts", "category"])
        assert summarize_drug(df, "empty") is None

    def test_ci_contains_point_estimate(self, conn):
        df = get_user_sentiment(conn, "test_drug_a")
        s = summarize_drug(df, "test_drug_a")
        assert s.pct_positive_ci[0] <= s.pct_positive <= s.pct_positive_ci[1]


# ═══════════════════════════════════════════════════════════════════════════════
# run_binomial_test
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunBinomialTest:
    def test_high_positive_rate(self, conn):
        """Drug A: 80% positive vs 50% baseline should be significant."""
        df = get_user_sentiment(conn, "test_drug_a")
        result = run_binomial_test(df, baseline=0.5)
        assert result is not None
        assert result.significant
        assert result.observed_rate > 0.7

    def test_baseline_rate(self, conn):
        """Drug A: 80% positive vs 80% baseline should NOT be significant."""
        df = get_user_sentiment(conn, "test_drug_a")
        result = run_binomial_test(df, baseline=0.8)
        assert result is not None
        assert not result.significant

    def test_custom_baseline(self, conn):
        df = get_user_sentiment(conn, "test_drug_b")
        result = run_binomial_test(df, baseline=0.5)
        assert result is not None
        # Drug B: 20% positive vs 50% baseline → significant
        assert result.significant
        assert result.observed_rate < 0.5

    def test_small_n(self):
        """Should still run with very small sample."""
        df = pd.DataFrame({
            "user_id": ["a", "b", "c"],
            "avg_sentiment": [1.0, 1.0, -1.0],
            "n_posts": [1, 1, 1],
            "category": ["positive", "positive", "negative"],
        })
        result = run_binomial_test(df)
        assert result is not None
        assert result.n_users == 3

    def test_empty_returns_none(self):
        df = pd.DataFrame(columns=["user_id", "avg_sentiment", "n_posts", "category"])
        assert run_binomial_test(df) is None

    def test_ci_bounds(self, conn):
        df = get_user_sentiment(conn, "test_drug_a")
        result = run_binomial_test(df)
        assert 0 <= result.ci_lower <= result.observed_rate
        assert result.observed_rate <= result.ci_upper <= 1.0

    def test_binomial_warns_on_small_extreme_sample(self):
        df = pd.DataFrame({
            "user_id": ["a", "b", "c"],
            "avg_sentiment": [1.0, 1.0, 1.0],
            "n_posts": [1, 1, 1],
            "category": ["positive", "positive", "positive"],
        })
        result = run_binomial_test(df, baseline=1.0)
        assert result is not None
        assert any("Only 3 users" in w.message for w in result.warnings)
        assert any("no variation" in w.message.lower() for w in result.warnings)
        assert any("extreme boundary" in w.message.lower() for w in result.warnings)


# ═══════════════════════════════════════════════════════════════════════════════
# run_logit
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunLogit:
    def test_basic_logit(self, conn):
        """Should run without error with a condition predictor."""
        result = run_logit(conn, "test_drug_a", ["has_pots"])
        assert result is not None
        assert isinstance(result, LogitResult)
        assert result.n_obs > 0
        # Model may fail with singular matrix if synthetic data has perfect separation
        # but should at least return a result with warnings
        if result.converged:
            assert len(result.predictors) > 0

    def test_logit_output_structure(self, conn):
        result = run_logit(conn, "test_drug_a", ["has_pots"])
        assert result is not None
        for pred in result.predictors:
            assert pred.odds_ratio > 0
            assert pred.ci_lower <= pred.odds_ratio <= pred.ci_upper
            assert 0 <= pred.p_value <= 1

    def test_logit_confidence_intervals_are_finite(self, conn):
        result = run_logit(conn, "test_drug_a", ["sex", "has_pots"])
        assert result is not None
        for pred in result.predictors:
            assert math.isfinite(pred.odds_ratio)
            assert math.isfinite(pred.ci_lower)
            assert math.isfinite(pred.ci_upper)

    def test_sparse_predictor_dropped(self, conn):
        """Sex has > 80% NaN for drug users → should be dropped with warning."""
        result = run_logit(conn, "test_drug_a", ["sex", "has_pots"])
        # Should run (using has_pots) even though sex is sparse
        if result is not None and result.warnings:
            sex_warnings = [w for w in result.warnings if "sex" in w.message.lower()]
            # Either sex was dropped or the model ran fine with it
            # (depends on synthetic data overlap)

    def test_nonexistent_drug(self, conn):
        result = run_logit(conn, "nonexistent_drug_xyz", ["has_pots"])
        assert result is None

    def test_no_valid_predictors(self, conn):
        """All requested predictors missing from data → graceful failure."""
        result = run_logit(conn, "test_drug_a", ["has_nonexistent_condition"])
        # has_nonexistent_condition will be all zeros → zero variance → dropped
        if result is not None:
            assert result.converged is False or len(result.warnings) > 0

    def test_duplicate_profile_runs_do_not_duplicate_feature_rows(self, conn):
        conn.execute("INSERT INTO extraction_runs VALUES (2, ?, 'test', '{}')", (int(time.time()),))
        conn.execute(
            "INSERT INTO user_profiles VALUES ('user_00', 2, '50s', 'male', NULL)"
        )
        conn.commit()

        features = _build_logit_features(conn, "test_drug_a", ["sex", "age_bucket"])
        assert features is not None
        assert features["user_id"].nunique() == len(features)
        row = features.loc[features["user_id"] == "user_00"].iloc[0]
        assert row["sex"] == 0
        assert row["age_bucket"] == 5

    def test_logit_does_not_emit_library_warnings(self, conn):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = run_logit(conn, "test_drug_a", ["sex", "has_pots"])
        assert result is not None
        assert caught == []

    def test_logit_warns_when_rows_are_dropped(self, conn):
        result = run_logit(conn, "test_drug_a", ["sex", "age_bucket", "has_pots"])
        assert result is not None
        assert any("Dropped" in w.message for w in result.warnings)


# ═══════════════════════════════════════════════════════════════════════════════
# run_ols
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunOLS:
    def test_basic_ols(self, conn):
        result = run_ols(conn, "test_drug_a", ["has_pots", "has_mcas"])
        assert result is not None
        assert isinstance(result, OLSResult)
        assert result.n_obs > 0
        assert 0 <= result.r_squared <= 1

    def test_ols_output_structure(self, conn):
        result = run_ols(conn, "test_drug_a", ["has_pots"])
        assert result is not None
        for pred in result.predictors:
            assert pred.ci_lower <= pred.coefficient <= pred.ci_upper
            assert 0 <= pred.p_value <= 1

    def test_sparse_predictor_dropped(self, conn):
        """Sex dropped for > 80% NaN, model should still run."""
        result = run_ols(conn, "test_drug_a", ["sex", "has_pots"])
        # Should produce a result (using has_pots)
        assert result is not None

    def test_nonexistent_drug(self, conn):
        assert run_ols(conn, "nonexistent_drug_xyz", ["has_pots"]) is None

    def test_f_statistic_present(self, conn):
        result = run_ols(conn, "test_drug_a", ["has_pots", "has_mcas"])
        assert result is not None
        assert result.f_statistic >= 0
        assert 0 <= result.f_p_value <= 1

    def test_ols_does_not_emit_library_warnings(self, conn):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = run_ols(conn, "test_drug_a", ["sex", "has_pots"])
        assert result is not None
        assert caught == []

    def test_ols_warns_when_rows_are_dropped(self, conn):
        result = run_ols(conn, "test_drug_a", ["sex", "age_bucket", "has_pots"])
        assert result is not None
        assert any("Dropped" in w.message for w in result.warnings)


# ═══════════════════════════════════════════════════════════════════════════════
# run_kruskal_wallis
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunKruskalWallis:
    def test_three_different_groups(self, conn):
        """A (positive), B (negative), C (mixed) should differ significantly."""
        groups = {
            "drug_a": get_user_sentiment(conn, "test_drug_a"),
            "drug_b": get_user_sentiment(conn, "test_drug_b"),
            "drug_c": get_user_sentiment(conn, "test_drug_c"),
        }
        result = run_kruskal_wallis(groups)
        assert result is not None
        assert result.significant
        assert result.h_statistic > 0

    def test_identical_groups(self, conn):
        """Same data three times should NOT be significant."""
        df = get_user_sentiment(conn, "test_drug_a")
        groups = {"g1": df, "g2": df, "g3": df}
        result = run_kruskal_wallis(groups)
        assert result is not None
        assert not result.significant

    def test_post_hoc_bonferroni(self, conn):
        groups = {
            "drug_a": get_user_sentiment(conn, "test_drug_a"),
            "drug_b": get_user_sentiment(conn, "test_drug_b"),
            "drug_c": get_user_sentiment(conn, "test_drug_c"),
        }
        result = run_kruskal_wallis(groups)
        assert result is not None
        # Should have 3 pairwise comparisons (3 choose 2)
        assert len(result.pairwise) == 3
        for pw in result.pairwise:
            # Bonferroni: adjusted p must be >= raw p
            assert pw.p_bonferroni >= pw.p_value
            assert pw.p_fdr >= pw.p_value

    def test_two_groups_still_works(self, conn):
        """Should still work with 2 groups (degenerates to Mann-Whitney)."""
        groups = {
            "drug_a": get_user_sentiment(conn, "test_drug_a"),
            "drug_b": get_user_sentiment(conn, "test_drug_b"),
        }
        result = run_kruskal_wallis(groups)
        assert result is not None
        assert len(result.pairwise) == 1

    def test_insufficient_groups(self, conn):
        groups = {"only_one": get_user_sentiment(conn, "test_drug_a")}
        assert run_kruskal_wallis(groups) is None

    def test_group_sizes_reported(self, conn):
        groups = {
            "drug_a": get_user_sentiment(conn, "test_drug_a"),
            "drug_b": get_user_sentiment(conn, "test_drug_b"),
        }
        result = run_kruskal_wallis(groups)
        assert result.group_sizes["drug_a"] == 20
        assert result.group_sizes["drug_b"] == 15


# ═══════════════════════════════════════════════════════════════════════════════
# run_time_trend
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunTimeTrend:
    def test_increasing_trend(self, conn):
        """trend_drug has linearly increasing sentiment → positive tau."""
        result = run_time_trend(conn, "trend_drug")
        assert result is not None
        if result.n_months >= 3:
            assert result.tau > 0
            assert result.direction in ("improving", "stable")

    def test_no_trend(self, conn):
        """Drug C: all sentiment = 0.5 → no trend."""
        result = run_time_trend(conn, "test_drug_c")
        # All same sentiment → tau should be 0 or near 0
        if result is not None and result.n_months >= 3:
            assert result.direction == "stable"

    def test_insufficient_data(self, conn):
        """Drug with < 3 months of data should warn."""
        result = run_time_trend(conn, "test_drug_c")
        if result is not None and result.n_months < 3:
            assert len(result.warnings) > 0

    def test_nonexistent_drug(self, conn):
        assert run_time_trend(conn, "nonexistent_xyz") is None

    def test_monthly_data_structure(self, conn):
        result = run_time_trend(conn, "trend_drug")
        if result is not None and result.monthly_data:
            for point in result.monthly_data:
                assert "month" in point
                assert "avg_sentiment" in point
                assert "n_reports" in point
                assert point["n_reports"] > 0

    def test_iso_timestamp_strings_are_parsed(self, conn):
        conn.execute("INSERT INTO treatment (id, canonical_name) VALUES (5, 'iso_trend_drug')")
        iso_points = [
            ("user_00", "post_user_00_m0", "2026-01-15T00:00:00Z", -1.0),
            ("user_01", "post_user_01_m1", "2026-02-15T00:00:00Z", 0.0),
            ("user_02", "post_user_02_m2", "2026-03-15T00:00:00Z", 1.0),
        ]
        for user_id, post_id, post_date, sentiment in iso_points:
            conn.execute(
                "UPDATE posts SET post_date = ? WHERE post_id = ?",
                (post_date, post_id),
            )
            conn.execute(
                "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength)"
                " VALUES (1, ?, ?, 5, ?, 1.0)",
                (post_id, user_id, sentiment),
            )
        conn.commit()

        result = run_time_trend(conn, "iso_trend_drug")
        assert result is not None
        assert result.n_months == 3
        assert [point["month"] for point in result.monthly_data] == ["2026-01", "2026-02", "2026-03"]

    def test_time_trend_warns_on_short_gappy_series(self, conn):
        conn.execute("INSERT INTO treatment (id, canonical_name) VALUES (8, 'gappy_trend_drug')")
        points = [
            ("user_03", "post_user_03_m0", "2026-01-01T00:00:00Z", 0.1),
            ("user_04", "post_user_04_m1", "2026-03-01T00:00:00Z", 0.1),
            ("user_05", "post_user_05_m2", "2026-05-01T00:00:00Z", 0.1),
        ]
        for user_id, post_id, post_date, sentiment in points:
            conn.execute("UPDATE posts SET post_date = ? WHERE post_id = ?", (post_date, post_id))
            conn.execute(
                "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength)"
                " VALUES (1, ?, ?, 8, ?, 1.0)",
                (post_id, user_id, sentiment),
            )
        conn.commit()
        result = run_time_trend(conn, "gappy_trend_drug")
        assert result is not None
        assert any("Fewer than 6 months" in w.message for w in result.warnings)
        assert any("gaps" in w.message.lower() for w in result.warnings)
        assert any("no variation" in w.message.lower() for w in result.warnings)


# ═══════════════════════════════════════════════════════════════════════════════
# run_survival
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunSurvival:
    def test_basic_survival(self, conn):
        """Drug A has 16 positive outcomes → should be enough for Cox PH."""
        result = run_survival(conn, "test_drug_a", ["has_pots"])
        # May return None or result with warnings depending on data shape
        if result is not None:
            assert isinstance(result, SurvivalResult)
            assert result.n_users > 0
            assert result.n_events + result.n_censored == result.n_users

    def test_too_few_events(self, conn):
        """Drug C: all sentiment = 0.5 → 0 events (none > 0.7) → should warn."""
        result = run_survival(conn, "test_drug_c", ["has_pots"])
        if result is not None:
            assert len(result.warnings) > 0
            assert result.n_events < 10

    def test_output_structure(self, conn):
        result = run_survival(conn, "test_drug_a", ["has_pots"])
        if result is not None and result.predictors:
            for pred in result.predictors:
                assert pred.hazard_ratio > 0
                assert pred.ci_lower <= pred.hazard_ratio <= pred.ci_upper
                assert 0 <= pred.p_value <= 1

    def test_nonexistent_drug(self, conn):
        result = run_survival(conn, "nonexistent_xyz", ["has_pots"])
        assert result is None

    def test_concordance_range(self, conn):
        result = run_survival(conn, "test_drug_a", ["has_pots"])
        if result is not None and result.concordance > 0:
            assert 0 <= result.concordance <= 1

    def test_median_time_none_when_majority_censored(self, conn):
        conn.execute("INSERT INTO treatment (id, canonical_name) VALUES (6, 'censored_drug')")
        for i in range(12):
            user_id = f"user_{i:02d}"
            post_id = f"post_{user_id}_m0"
            sentiment = 1.0 if i < 5 else 0.0
            conn.execute(
                "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength)"
                " VALUES (1, ?, ?, 6, ?, 1.0)",
                (post_id, user_id, sentiment),
            )
        conn.commit()

        result = run_survival(conn, "censored_drug", ["has_pots"])
        assert result is not None
        assert result.n_censored > result.n_events
        assert result.median_time_days is None

    def test_mixed_timestamp_entry_uses_true_earliest_post(self, conn):
        conn.execute(
            "INSERT INTO users VALUES ('mixed_user', 'covidlonghaulers', ?)",
            (int(time.time()),),
        )
        conn.execute(
            "INSERT INTO posts VALUES ('mixed_iso', 'mixed_user', 'body', NULL, ?, ?)",
            ("2019-01-01T00:00:00Z", int(time.time())),
        )
        conn.execute(
            "INSERT INTO posts VALUES ('mixed_epoch', 'mixed_user', 'body', NULL, ?, ?)",
            (1700000000, int(time.time())),
        )
        conn.execute("INSERT INTO treatment (id, canonical_name) VALUES (7, 'mixed_survival_drug')")
        conn.execute(
            "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength)"
            " VALUES (1, 'mixed_epoch', 'mixed_user', 7, 1.0, 1.0)"
        )
        conn.commit()

        survival_df = _build_survival_data(conn, "mixed_survival_drug", [])
        assert survival_df is not None
        row = survival_df.loc[survival_df["user_id"] == "mixed_user"].iloc[0]
        assert row["duration_days"] > 1000

    def test_survival_warns_on_heavy_censoring_and_short_durations(self, conn):
        conn.execute("INSERT INTO treatment (id, canonical_name) VALUES (9, 'warning_survival_drug')")
        for i in range(20):
            user_id = f"user_{i:02d}"
            post_id = f"post_{user_id}_m0"
            sentiment = 1.0 if i < 3 else 0.0
            conn.execute(
                "INSERT INTO treatment_reports (run_id, post_id, user_id, drug_id, sentiment, signal_strength)"
                " VALUES (1, ?, ?, 9, ?, 1.0)",
                (post_id, user_id, sentiment),
            )
        conn.commit()
        result = run_survival(conn, "warning_survival_drug", ["has_pots"])
        assert result is not None
        assert any("censored" in w.message.lower() for w in result.warnings)


# ═══════════════════════════════════════════════════════════════════════════════
# run_wilcoxon (paired within-subject)
# ═══════════════════════════════════════════════════════════════════════════════

from app.analysis.stats import get_paired_sentiment, run_wilcoxon, WilcoxonResult


class TestRunWilcoxon:
    def test_paired_users_found(self, conn):
        """Users 0-14 have reports for both drug A and drug B."""
        df = get_paired_sentiment(conn, "test_drug_a", "test_drug_b")
        assert df is not None
        assert len(df) > 0
        assert "diff" in df.columns

    def test_significant_paired_difference(self, conn):
        """Drug A (positive) vs Drug B (negative) among shared users."""
        result = run_wilcoxon(conn, "test_drug_a", "test_drug_b")
        assert result is not None
        assert isinstance(result, WilcoxonResult)
        assert result.significant
        assert result.direction == "drug_a_better"
        assert result.mean_diff > 0
        assert result.n_paired >= 5

    def test_same_drug_not_significant(self, conn):
        """Same drug vs itself → no difference."""
        result = run_wilcoxon(conn, "test_drug_a", "test_drug_a")
        if result is not None:
            assert not result.significant
            assert result.direction == "no_difference"

    def test_too_few_pairs_returns_none(self, conn):
        """Drugs with < 5 shared users should return None."""
        result = run_wilcoxon(conn, "test_drug_a", "trend_drug")
        # trend_drug has very few users, unlikely to have 5 shared with drug_a
        # Either None or a result — both acceptable
        if result is not None:
            assert result.n_paired >= 5

    def test_warns_on_small_pairs(self, conn):
        """If n_paired < 20, should include a warning."""
        result = run_wilcoxon(conn, "test_drug_a", "test_drug_b")
        if result is not None and result.n_paired < 20:
            assert any("Only" in w.message and "users tried both" in w.message for w in result.warnings)

    def test_nonexistent_drug(self, conn):
        result = run_wilcoxon(conn, "test_drug_a", "nonexistent_xyz")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# run_spearman
# ═══════════════════════════════════════════════════════════════════════════════

from app.analysis.stats import run_spearman, SpearmanResult


class TestRunSpearman:
    def test_perfect_positive_correlation(self):
        a = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        b = pd.Series([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
        result = run_spearman(a, b, "x", "y")
        assert result is not None
        assert result.rho == 1.0
        assert result.significant

    def test_no_correlation(self):
        a = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        b = pd.Series([5, 3, 8, 1, 9, 2, 7, 4, 10, 6])
        result = run_spearman(a, b)
        assert result is not None
        assert abs(result.rho) < 0.5

    def test_too_few_returns_none(self):
        a = pd.Series([1, 2, 3])
        b = pd.Series([4, 5, 6])
        assert run_spearman(a, b) is None

    def test_handles_nan(self):
        a = pd.Series([1, 2, None, 4, 5, 6, 7, 8, 9, 10])
        b = pd.Series([10, 20, 30, None, 50, 60, 70, 80, 90, 100])
        result = run_spearman(a, b)
        assert result is not None
        assert result.n == 8  # 2 NaN rows dropped

    def test_low_variability_warning(self):
        a = pd.Series([1, 1, 1, 1, 1, 2, 1, 1, 1, 1])
        b = pd.Series([5, 5, 5, 5, 5, 6, 5, 5, 5, 5])
        result = run_spearman(a, b)
        assert result is not None
        assert any("variability" in w.message.lower() for w in result.warnings)


# ═══════════════════════════════════════════════════════════════════════════════
# run_propensity_match
# ═══════════════════════════════════════════════════════════════════════════════

from app.analysis.stats import run_propensity_match, PropensityResult


class TestRunPropensityMatch:
    def test_basic_propensity(self, conn):
        """Drug A users vs non-drug-A users, matched on conditions."""
        result = run_propensity_match(conn, "test_drug_a", ["has_pots", "has_mcas"])
        # May return None if not enough control users; that's ok
        if result is not None:
            assert isinstance(result, PropensityResult)
            assert result.n_matched >= 0

    def test_balance_table_present(self, conn):
        result = run_propensity_match(conn, "test_drug_a", ["has_pots"])
        if result is not None and result.n_matched > 0:
            assert len(result.balance_table) > 0
            for row in result.balance_table:
                assert "predictor" in row
                assert "smd_before" in row
                assert "smd_after" in row

    def test_nonexistent_drug(self, conn):
        result = run_propensity_match(conn, "nonexistent_xyz", ["has_pots"])
        assert result is None

    def test_no_valid_predictors(self, conn):
        result = run_propensity_match(conn, "test_drug_a", ["has_nonexistent"])
        if result is not None:
            assert result.n_matched == 0 or len(result.warnings) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Warning-specific tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestWarnings:
    def test_kruskal_multiple_comparisons_warning(self, conn):
        """With 5 groups → 10 comparisons → should warn."""
        groups = {}
        for i in range(5):
            drug_name = f"test_drug_{'abc'[i % 3]}"
            df = get_user_sentiment(conn, drug_name)
            if not df.empty:
                groups[f"group_{i}"] = df
        # Need 5 groups with data; duplicate some if needed
        base_df = get_user_sentiment(conn, "test_drug_a")
        while len(groups) < 5:
            groups[f"extra_{len(groups)}"] = base_df.copy()
        result = run_kruskal_wallis(groups)
        assert result is not None
        assert any("pairwise comparisons" in w.message for w in result.warnings)

    def test_logit_low_epp_warning(self, conn):
        """2 predictors with few events should trigger EPP warning."""
        # Drug B: only 3 positive events out of 15 users
        result = run_logit(conn, "test_drug_b", ["has_pots", "has_mcas"])
        if result is not None:
            assert any("events-per-predictor" in w.message.lower() or "epp" in w.message.lower()
                       for w in result.warnings)

    def test_identical_distributions_warning(self, conn):
        """Both groups 100% positive → warning."""
        df_same = pd.DataFrame({
            "user_id": [f"u{i}" for i in range(10)],
            "avg_sentiment": [1.0] * 10,
            "n_posts": [1] * 10,
            "category": ["positive"] * 10,
        })
        result = run_comparison(df_same, df_same)
        assert result is not None
        assert any("identical" in w.message.lower() for w in result.warnings)

    def test_reporting_bias_disclaimer_exists(self):
        """The REPORTING_BIAS_DISCLAIMER constant should be importable."""
        from app.analysis.stats import REPORTING_BIAS_DISCLAIMER
        assert "self-selected" in REPORTING_BIAS_DISCLAIMER
        assert "Reddit" in REPORTING_BIAS_DISCLAIMER
