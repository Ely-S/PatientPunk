"""
app/analysis/stats.py
~~~~~~~~~~~~~~~~~~~~~
Statistics engine for PatientPunk analysis app.

Pure Python — no UI, no LLM. Aggregates treatment_reports to the user level
(one data point per user per drug) to achieve independence, then runs
appropriate statistical tests.

Tests available:
    1. Mann-Whitney U        — two-group continuous comparison
    2. Chi-square / Fisher's — two-group categorical comparison
    3. Binomial              — single drug vs baseline rate
    4. Logistic regression   — multivariate predictor analysis
    5. Kruskal-Wallis        — 3+ group comparison with post-hoc
    6. Time trend            — Mann-Kendall / linear regression over calendar time
    7. Survival (Cox PH)     — time-to-positive-outcome with predictors

Usage:
    import sqlite3
    from app.analysis.stats import get_user_sentiment, run_comparison

    conn = sqlite3.connect("patientpunk.db")
    df = get_user_sentiment(conn, "low dose naltrexone")
    result = run_comparison(df, df2)
"""

from __future__ import annotations

import math
import sqlite3
import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats as sp_stats


# ── Sentiment category boundaries ─────────────────────────────────────────────

def categorize_sentiment(score: float) -> str:
    """Map a continuous sentiment score to a category label.

    Boundaries match the encoding used in db.py / load_sentiment():
        positive  >  0.7
        mixed     0.1 – 0.7
        neutral   0.0
        negative  < -0.7  (everything below mixed treated as negative)
    """
    if score > 0.7:
        return "positive"
    if score >= 0.1:
        return "mixed"
    if score > -0.7:
        return "neutral"
    return "negative"


SENTIMENT_CATEGORIES = ["positive", "mixed", "neutral", "negative"]


# ── Wilson score confidence interval ──────────────────────────────────────────

def wilson_ci(n_successes: int, n_total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion.

    Preferred over the normal approximation when n is small or p is near 0/1.
    Returns (lower, upper) as proportions in [0, 1].
    """
    if n_total == 0:
        return 0.0, 0.0
    p = n_successes / n_total
    denominator = 1 + z**2 / n_total
    centre = (p + z**2 / (2 * n_total)) / denominator
    margin = (z * math.sqrt(p * (1 - p) / n_total + z**2 / (4 * n_total**2))) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


# ── Core query: user-level sentiment ──────────────────────────────────────────

def get_user_sentiment(
    conn: sqlite3.Connection,
    drug: str,
    condition: str | None = None,
    sex: str | None = None,
    age_bucket: str | None = None,
) -> pd.DataFrame:
    """Return one row per user for a given drug, aggregated across their posts.

    Filters are AND-combined. Condition is a substring match (case-insensitive).

    Returns DataFrame with columns:
        user_id         str   SHA-256 author hash
        avg_sentiment   float mean sentiment score across user's posts about this drug
        n_posts         int   number of posts/comments contributing
        category        str   categorized sentiment of avg_sentiment
    """
    params: list = [drug]
    condition_join = ""
    condition_clause = ""
    sex_clause = ""
    age_clause = ""

    if condition:
        condition_join = """
            JOIN conditions c ON c.user_id = tr.user_id
        """
        condition_clause = "AND LOWER(c.condition_name) LIKE LOWER(?)"
        params.append(f"%{condition}%")

    if sex:
        sex_clause = """
            AND EXISTS (
                SELECT 1 FROM user_profiles up
                WHERE up.user_id = tr.user_id
                AND LOWER(up.sex) = LOWER(?)
            )
        """
        params.append(sex)

    if age_bucket:
        age_clause = """
            AND EXISTS (
                SELECT 1 FROM user_profiles up
                WHERE up.user_id = tr.user_id
                AND up.age_bucket = ?
            )
        """
        params.append(age_bucket)

    sql = f"""
        SELECT
            tr.user_id,
            AVG(tr.sentiment)   AS avg_sentiment,
            COUNT(*)            AS n_posts
        FROM treatment_reports tr
        JOIN treatment t ON t.id = tr.drug_id
        {condition_join}
        WHERE t.canonical_name = ? COLLATE NOCASE
        {condition_clause}
        {sex_clause}
        {age_clause}
        GROUP BY tr.user_id
    """
    # drug param comes after condition param in the WHERE clause
    # rebuild params in SQL order: condition (if join), then drug, then condition clause, sex, age
    ordered_params: list = []
    if condition:
        ordered_params.append(drug)
        ordered_params.append(f"%{condition}%")
    else:
        ordered_params.append(drug)
    if sex:
        ordered_params.append(sex)
    if age_bucket:
        ordered_params.append(age_bucket)

    rows = conn.execute(sql, ordered_params).fetchall()
    df = pd.DataFrame(rows, columns=["user_id", "avg_sentiment", "n_posts"])
    if not df.empty:
        df["category"] = df["avg_sentiment"].map(categorize_sentiment)
    else:
        df["category"] = pd.Series(dtype=str)
    return df


# ── Sample size checks ─────────────────────────────────────────────────────────

@dataclass
class SampleSizeCheck:
    ok: bool
    warnings: list[str] = field(default_factory=list)


def check_sample_sizes(group_a: pd.Series, group_b: pd.Series) -> SampleSizeCheck:
    """Check whether sample sizes are adequate for the planned tests.

    Flags:
    - Either group has n < 5 (too small for any meaningful test)
    - Either group has n < 20 (results should be interpreted cautiously)
    - Any expected cell count < 5 in the chi-square contingency table
      (triggers fallback to Fisher's exact test)
    """
    warnings = []
    na, nb = len(group_a), len(group_b)

    if na < 5 or nb < 5:
        return SampleSizeCheck(
            ok=False,
            warnings=[
                f"Sample sizes are too small to run a meaningful test "
                f"(Group A: {na} users, Group B: {nb} users). "
                f"At least 5 users per group are needed."
            ],
        )

    if na < 20:
        warnings.append(
            f"Group A has only {na} users — interpret results cautiously."
        )
    if nb < 20:
        warnings.append(
            f"Group B has only {nb} users — interpret results cautiously."
        )

    return SampleSizeCheck(ok=True, warnings=warnings)


# ── Statistical tests ──────────────────────────────────────────────────────────

@dataclass
class ComparisonResult:
    """Full result of a two-group comparison."""

    # Mann-Whitney U (continuous sentiment scores)
    mw_statistic: float
    mw_p_value: float
    mw_effect_size_r: float          # r = Z / sqrt(N), -1 to 1
    mw_significant: bool             # p < 0.05

    # Chi-square or Fisher's exact (sentiment categories)
    cat_test_name: str               # "chi-square" or "fisher's exact"
    cat_statistic: float | None      # None for Fisher's exact
    cat_p_value: float
    cat_effect_size: float           # Cramér's V (chi-sq) or odds ratio (Fisher's)
    cat_significant: bool

    # Category counts for both groups
    counts_a: dict[str, int]
    counts_b: dict[str, int]

    # Sample sizes
    n_a: int
    n_b: int

    # Warnings from sample size check
    warnings: list[str]


def _count_categories(series: pd.Series) -> dict[str, int]:
    """Count each sentiment category, ensuring all 4 are present."""
    counts = series.value_counts().to_dict()
    return {cat: counts.get(cat, 0) for cat in SENTIMENT_CATEGORIES}


def run_comparison(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
) -> ComparisonResult | None:
    """Run Mann-Whitney U + chi-square/Fisher's exact on two user-level DataFrames.

    Returns None if sample sizes are too small (check separately with
    check_sample_sizes before calling).

    df_a, df_b: output of get_user_sentiment() — must have avg_sentiment and category columns.
    """
    scores_a = df_a["avg_sentiment"]
    scores_b = df_b["avg_sentiment"]
    size_check = check_sample_sizes(scores_a, scores_b)
    if not size_check.ok:
        return None

    n_a, n_b = len(scores_a), len(scores_b)

    # ── Mann-Whitney U ────────────────────────────────────────────────────────
    mw_stat, mw_p = sp_stats.mannwhitneyu(scores_a, scores_b, alternative="two-sided")
    # Effect size r = Z / sqrt(N) where Z is the normal approximation
    z = sp_stats.norm.ppf(1 - mw_p / 2)
    mw_r = abs(z) / math.sqrt(n_a + n_b)

    # ── Contingency table ─────────────────────────────────────────────────────
    counts_a = _count_categories(df_a["category"])
    counts_b = _count_categories(df_b["category"])

    # Build observed matrix — only include categories present in at least one group
    # to avoid zero-column failures in chi-square
    active_cats = [cat for cat in SENTIMENT_CATEGORIES
                   if counts_a[cat] > 0 or counts_b[cat] > 0]
    observed = [
        [counts_a[cat] for cat in active_cats],
        [counts_b[cat] for cat in active_cats],
    ]

    # Use Fisher's exact (2×2: positive vs non-positive) when:
    #   - fewer than 3 active categories (not enough for chi-square)
    #   - any observed cell is 0
    #   - any expected cell < 5
    has_zero_observed = any(cell == 0 for row in observed for cell in row)
    if len(active_cats) < 3 or has_zero_observed:
        use_fisher = True
        chi2_stat, chi2_p, expected = None, None, None
    else:
        chi2_stat, chi2_p, _, expected = sp_stats.chi2_contingency(observed)
        use_fisher = any(cell < 5 for row in expected for cell in row)

    if use_fisher:
        # Collapse to 2×2: positive vs non-positive
        pos_a = counts_a["positive"]
        pos_b = counts_b["positive"]
        not_pos_a = n_a - pos_a
        not_pos_b = n_b - pos_b
        _, fisher_p = sp_stats.fisher_exact([[pos_a, not_pos_a], [pos_b, not_pos_b]])
        # Laplace-smoothed odds ratio as effect size
        odds_ratio = ((pos_a + 0.5) * (not_pos_b + 0.5)) / ((not_pos_a + 0.5) * (pos_b + 0.5))
        cat_name = "Fisher's exact"
        cat_stat = None
        cat_p = fisher_p
        cat_effect = round(odds_ratio, 3)
    else:
        # Cramér's V as effect size
        n_total = n_a + n_b
        k = len(active_cats) - 1  # (cols - 1) for 2-row table
        cramers_v = math.sqrt(chi2_stat / (n_total * k)) if n_total > 0 and k > 0 else 0.0
        cat_name = "chi-square"
        cat_stat = round(chi2_stat, 3)
        cat_p = chi2_p
        cat_effect = round(cramers_v, 3)

    return ComparisonResult(
        mw_statistic=round(mw_stat, 3),
        mw_p_value=round(mw_p, 4),
        mw_effect_size_r=round(mw_r, 3),
        mw_significant=mw_p < 0.05,
        cat_test_name=cat_name,
        cat_statistic=cat_stat,
        cat_p_value=round(cat_p, 4),
        cat_effect_size=cat_effect,
        cat_significant=cat_p < 0.05,
        counts_a=counts_a,
        counts_b=counts_b,
        n_a=n_a,
        n_b=n_b,
        warnings=size_check.warnings,
    )


# ── Single-drug summary ────────────────────────────────────────────────────────

@dataclass
class SingleDrugSummary:
    """Descriptive statistics for a single drug."""
    drug: str
    n_users: int
    n_posts: int
    pct_positive: float
    pct_positive_ci: tuple[float, float]  # Wilson 95% CI
    pct_mixed: float
    pct_neutral: float
    pct_negative: float
    mean_sentiment: float
    median_sentiment: float
    std_sentiment: float


def summarize_drug(df: pd.DataFrame, drug_name: str) -> SingleDrugSummary | None:
    """Compute descriptive stats for a single drug's user-level DataFrame."""
    if df.empty:
        return None
    n = len(df)
    n_pos = (df["category"] == "positive").sum()
    return SingleDrugSummary(
        drug=drug_name,
        n_users=n,
        n_posts=int(df["n_posts"].sum()),
        pct_positive=round(n_pos / n * 100, 1),
        pct_positive_ci=tuple(round(v * 100, 1) for v in wilson_ci(n_pos, n)),
        pct_mixed=round((df["category"] == "mixed").sum() / n * 100, 1),
        pct_neutral=round((df["category"] == "neutral").sum() / n * 100, 1),
        pct_negative=round((df["category"] == "negative").sum() / n * 100, 1),
        mean_sentiment=round(df["avg_sentiment"].mean(), 3),
        median_sentiment=round(df["avg_sentiment"].median(), 3),
        std_sentiment=round(df["avg_sentiment"].std(), 3),
    )


# ── Test 3: One-sample binomial ───────────────────────────────────────────────

@dataclass
class BinomialResult:
    """Result of a one-sample binomial test against a baseline proportion."""
    n_users: int
    n_positive: int
    observed_rate: float
    baseline: float
    p_value: float
    significant: bool
    ci_lower: float             # Wilson 95% CI on observed rate
    ci_upper: float


def run_binomial_test(
    df: pd.DataFrame,
    baseline: float = 0.5,
) -> BinomialResult | None:
    """Test whether a drug's positive rate differs from a baseline.

    Default baseline is 0.5 (chance). The test answers: "Does this drug
    have a positive-outcome rate significantly different from 50%?"

    Uses scipy.stats.binomtest (exact binomial, valid at any sample size).
    """
    if df.empty:
        return None

    n = len(df)
    n_pos = int((df["category"] == "positive").sum())
    result = sp_stats.binomtest(n_pos, n, p=baseline, alternative="two-sided")
    ci_lower, ci_upper = wilson_ci(n_pos, n)

    return BinomialResult(
        n_users=n,
        n_positive=n_pos,
        observed_rate=round(n_pos / n, 3),
        baseline=baseline,
        p_value=round(result.pvalue, 4),
        significant=result.pvalue < 0.05,
        ci_lower=round(ci_lower, 3),
        ci_upper=round(ci_upper, 3),
    )


# ── Test 4: Logistic regression ───────────────────────────────────────────────

@dataclass
class LogitPredictor:
    """One row in the logit results table."""
    name: str
    coefficient: float
    odds_ratio: float
    ci_lower: float             # 95% CI on odds ratio
    ci_upper: float
    p_value: float
    significant: bool


@dataclass
class LogitResult:
    """Full result of a logistic regression."""
    predictors: list[LogitPredictor]
    pseudo_r2: float
    aic: float
    n_obs: int
    n_events: int               # count of positive outcomes
    converged: bool
    warnings: list[str] = field(default_factory=list)


def _build_logit_features(
    conn: sqlite3.Connection,
    drug: str,
    predictor_names: list[str],
) -> pd.DataFrame | None:
    """Build a user-level feature matrix for logistic regression.

    Joins treatment_reports (for the outcome) with user_profiles and conditions.
    Returns DataFrame with columns: user_id, positive (0/1), and one column
    per requested predictor.

    Available predictors:
        sex          → 1 = female, 0 = male (drops unknowns)
        age_bucket   → ordinal: 20s=2, 30s=3, 40s=4, etc.
        has_<cond>   → 1 if user has the condition, e.g. "has_pots"
    """
    # Start with user-level sentiment for this drug
    sql = """
        SELECT tr.user_id, AVG(tr.sentiment) AS avg_sentiment
        FROM treatment_reports tr
        JOIN treatment t ON t.id = tr.drug_id
        WHERE t.canonical_name = ? COLLATE NOCASE
        GROUP BY tr.user_id
    """
    df = pd.DataFrame(
        conn.execute(sql, [drug]).fetchall(),
        columns=["user_id", "avg_sentiment"],
    )
    if df.empty:
        return None

    df["positive"] = (df["avg_sentiment"] > 0.7).astype(int)

    # Join demographics if needed
    if "sex" in predictor_names or "age_bucket" in predictor_names:
        profiles = pd.DataFrame(
            conn.execute(
                "SELECT user_id, sex, age_bucket FROM user_profiles"
            ).fetchall(),
            columns=["user_id", "sex", "age_bucket"],
        )
        df = df.merge(profiles, on="user_id", how="left")

        if "sex" in predictor_names:
            sex_map = {"female": 1, "f": 1, "woman": 1,
                       "male": 0, "m": 0, "man": 0}
            df["sex"] = df["sex"].map(sex_map)
            # Drop rows where sex is unknown (NaN after map)

        if "age_bucket" in predictor_names:
            # Convert "20s" -> 2, "30s" -> 3, etc.
            def bucket_to_ordinal(b):
                if pd.isna(b) or not isinstance(b, str):
                    return None
                digits = "".join(c for c in b if c.isdigit())
                return int(digits) // 10 if digits else None
            df["age_bucket"] = df["age_bucket"].map(bucket_to_ordinal)

    # Join conditions if any predictor starts with "has_"
    condition_preds = [p for p in predictor_names if p.startswith("has_")]
    if condition_preds:
        conditions = pd.DataFrame(
            conn.execute(
                "SELECT user_id, condition_name FROM conditions"
            ).fetchall(),
            columns=["user_id", "condition_name"],
        )
        for pred in condition_preds:
            cond_name = pred[4:]  # strip "has_"
            matching_users = set(
                conditions.loc[
                    conditions["condition_name"].str.contains(cond_name, case=False, na=False),
                    "user_id",
                ]
            )
            df[pred] = df["user_id"].isin(matching_users).astype(int)

    return df


def run_logit(
    conn: sqlite3.Connection,
    drug: str,
    predictor_names: list[str],
) -> LogitResult | None:
    """Run logistic regression predicting positive outcome for a drug.

    Parameters
    ----------
    conn:            SQLite connection
    drug:            canonical drug name
    predictor_names: list of predictor column names (see _build_logit_features)

    Returns None if insufficient data. Returns LogitResult with converged=False
    and warnings if the model fails to converge (e.g., perfect separation).
    """
    import statsmodels.api as sm

    df = _build_logit_features(conn, drug, predictor_names)
    if df is None or len(df) < 10:
        return None

    # Keep only columns needed and drop rows with any NaN in predictors
    cols = ["positive"] + [p for p in predictor_names if p in df.columns]
    available_predictors = [p for p in predictor_names if p in df.columns]
    if not available_predictors:
        return LogitResult(
            predictors=[], pseudo_r2=0.0, aic=0.0,
            n_obs=len(df), n_events=int(df["positive"].sum()),
            converged=False,
            warnings=["No valid predictors available (all demographics missing)."],
        )

    result_warnings: list[str] = []

    # Drop predictors where > 80% of values are NaN (e.g., sex with low coverage)
    for pred in available_predictors.copy():
        if pred in df.columns and df[pred].isna().mean() > 0.8:
            result_warnings.append(
                f"Predictor '{pred}' is missing for > 80% of users — dropped."
            )
            available_predictors.remove(pred)

    if not available_predictors:
        return LogitResult(
            predictors=[], pseudo_r2=0.0, aic=0.0,
            n_obs=len(df), n_events=int(df["positive"].sum()),
            converged=False,
            warnings=result_warnings + ["No predictors with sufficient coverage."],
        )

    cols = ["positive"] + available_predictors
    model_df = df[cols].dropna()
    if len(model_df) < 10:
        return None

    y = model_df["positive"]
    X = sm.add_constant(model_df[available_predictors].astype(float))

    # Check events-per-predictor rule (≥ 10 events per predictor)
    n_events = int(y.sum())
    if n_events < 10 * len(available_predictors):
        result_warnings.append(
            f"Low events-per-predictor ratio ({n_events} events / "
            f"{len(available_predictors)} predictors). Results may be unreliable."
        )

    # Check for zero variance in any predictor
    for pred in available_predictors.copy():
        if X[pred].nunique() < 2:
            result_warnings.append(f"Predictor '{pred}' has no variance — dropped.")
            X = X.drop(columns=[pred])
            available_predictors.remove(pred)

    if not available_predictors:
        return LogitResult(
            predictors=[], pseudo_r2=0.0, aic=0.0,
            n_obs=len(model_df), n_events=n_events,
            converged=False,
            warnings=["All predictors had zero variance after filtering."],
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            logit_model = sm.Logit(y, X)
            fit = logit_model.fit(disp=0, maxiter=100)
    except Exception as e:
        return LogitResult(
            predictors=[], pseudo_r2=0.0, aic=0.0,
            n_obs=len(model_df), n_events=n_events,
            converged=False,
            warnings=[f"Model failed to fit: {e}"],
        )

    # Extract results per predictor (skip 'const')
    pred_results = []
    conf = fit.conf_int()
    for pred in available_predictors:
        if pred not in fit.params.index:
            continue
        coef = fit.params[pred]
        ci_lo, ci_hi = conf.loc[pred]
        pred_results.append(LogitPredictor(
            name=pred,
            coefficient=round(float(coef), 3),
            odds_ratio=round(float(np.exp(coef)), 3),
            ci_lower=round(float(np.exp(ci_lo)), 3),
            ci_upper=round(float(np.exp(ci_hi)), 3),
            p_value=round(float(fit.pvalues[pred]), 4),
            significant=float(fit.pvalues[pred]) < 0.05,
        ))

    return LogitResult(
        predictors=pred_results,
        pseudo_r2=round(float(fit.prsquared), 3),
        aic=round(float(fit.aic), 1),
        n_obs=int(fit.nobs),
        n_events=n_events,
        converged=bool(fit.mle_retvals.get("converged", False) if hasattr(fit, "mle_retvals") else True),
        warnings=result_warnings,
    )


# ── Test 4b: OLS linear regression ────────────────────────────────────────────

@dataclass
class OLSPredictor:
    """One row in the OLS results table."""
    name: str
    coefficient: float
    ci_lower: float             # 95% CI on coefficient
    ci_upper: float
    p_value: float
    significant: bool


@dataclass
class OLSResult:
    """Full result of an OLS linear regression on continuous sentiment."""
    predictors: list[OLSPredictor]
    r_squared: float
    adj_r_squared: float
    f_statistic: float
    f_p_value: float
    n_obs: int
    warnings: list[str] = field(default_factory=list)


def run_ols(
    conn: sqlite3.Connection,
    drug: str,
    predictor_names: list[str],
) -> OLSResult | None:
    """Run OLS linear regression predicting continuous sentiment for a drug.

    Unlike logit (binary positive/not), this models the full sentiment score
    as the dependent variable, capturing the gradient between strongly positive
    and strongly negative outcomes.

    Uses the same feature matrix builder as logit (_build_logit_features).

    Returns None if insufficient data (< 10 observations or no valid predictors).
    """
    import statsmodels.api as sm

    df = _build_logit_features(conn, drug, predictor_names)
    if df is None or len(df) < 10:
        return None

    available_predictors = [p for p in predictor_names if p in df.columns]
    result_warnings: list[str] = []

    # Drop predictors where > 80% of values are NaN
    for pred in available_predictors.copy():
        if pred in df.columns and df[pred].isna().mean() > 0.8:
            result_warnings.append(
                f"Predictor '{pred}' is missing for > 80% of users — dropped."
            )
            available_predictors.remove(pred)

    if not available_predictors:
        return OLSResult(
            predictors=[], r_squared=0.0, adj_r_squared=0.0,
            f_statistic=0.0, f_p_value=1.0, n_obs=len(df),
            warnings=result_warnings + ["No predictors with sufficient coverage."],
        )

    model_cols = ["avg_sentiment"] + available_predictors
    model_df = df[model_cols].dropna()
    if len(model_df) < 10:
        return None

    # Drop zero-variance predictors
    for pred in available_predictors.copy():
        if model_df[pred].nunique() < 2:
            result_warnings.append(f"Predictor '{pred}' has no variance — dropped.")
            model_df = model_df.drop(columns=[pred])
            available_predictors.remove(pred)

    if not available_predictors:
        return OLSResult(
            predictors=[], r_squared=0.0, adj_r_squared=0.0,
            f_statistic=0.0, f_p_value=1.0, n_obs=len(model_df),
            warnings=result_warnings + ["All predictors had zero variance."],
        )

    y = model_df["avg_sentiment"]
    X = sm.add_constant(model_df[available_predictors].astype(float))

    try:
        fit = sm.OLS(y, X).fit()
    except Exception as e:
        return OLSResult(
            predictors=[], r_squared=0.0, adj_r_squared=0.0,
            f_statistic=0.0, f_p_value=1.0, n_obs=len(model_df),
            warnings=[f"OLS failed to fit: {e}"],
        )

    # Extract per-predictor results
    pred_results = []
    conf = fit.conf_int()
    for pred in available_predictors:
        if pred not in fit.params.index:
            continue
        ci_lo, ci_hi = conf.loc[pred]
        pred_results.append(OLSPredictor(
            name=pred,
            coefficient=round(float(fit.params[pred]), 3),
            ci_lower=round(float(ci_lo), 3),
            ci_upper=round(float(ci_hi), 3),
            p_value=round(float(fit.pvalues[pred]), 4),
            significant=float(fit.pvalues[pred]) < 0.05,
        ))

    return OLSResult(
        predictors=pred_results,
        r_squared=round(float(fit.rsquared), 3),
        adj_r_squared=round(float(fit.rsquared_adj), 3),
        f_statistic=round(float(fit.fvalue), 3),
        f_p_value=round(float(fit.f_pvalue), 4),
        n_obs=int(fit.nobs),
        warnings=result_warnings,
    )


# ── Test 5: Kruskal-Wallis (3+ group comparison) ─────────────────────────────

@dataclass
class PairwiseResult:
    """One row of post-hoc pairwise comparison."""
    group_a: str
    group_b: str
    p_value: float
    p_adjusted: float           # Bonferroni-corrected
    significant: bool           # p_adjusted < 0.05
    effect_size_r: float


@dataclass
class KruskalResult:
    """Result of Kruskal-Wallis test with optional post-hoc pairwise tests."""
    h_statistic: float
    p_value: float
    significant: bool
    eta_squared: float          # effect size: H / (N - 1)
    group_sizes: dict[str, int]
    pairwise: list[PairwiseResult]
    warnings: list[str] = field(default_factory=list)


def run_kruskal_wallis(groups: dict[str, pd.DataFrame]) -> KruskalResult | None:
    """Compare sentiment across 3+ drug/cohort groups.

    Parameters
    ----------
    groups: dict mapping group name → user-level DataFrame (from get_user_sentiment)

    Returns None if fewer than 2 groups with data. Falls back to Mann-Whitney
    if exactly 2 groups.
    """
    # Filter to groups with at least 3 users
    valid = {k: df for k, df in groups.items() if len(df) >= 3}
    if len(valid) < 2:
        return None

    group_names = list(valid.keys())
    arrays = [valid[k]["avg_sentiment"].values for k in group_names]
    group_sizes = {k: len(valid[k]) for k in group_names}
    N = sum(group_sizes.values())

    result_warnings: list[str] = []
    for name, n in group_sizes.items():
        if n < 20:
            result_warnings.append(f"Group '{name}' has only {n} users.")

    # Kruskal-Wallis H test
    h_stat, kw_p = sp_stats.kruskal(*arrays)
    eta_sq = float(h_stat) / (N - 1) if N > 1 else 0.0

    # Post-hoc pairwise Mann-Whitney with Bonferroni correction
    n_comparisons = len(group_names) * (len(group_names) - 1) // 2
    pairwise: list[PairwiseResult] = []

    for i in range(len(group_names)):
        for j in range(i + 1, len(group_names)):
            a_name, b_name = group_names[i], group_names[j]
            a_vals, b_vals = arrays[i], arrays[j]
            u_stat, mw_p = sp_stats.mannwhitneyu(a_vals, b_vals, alternative="two-sided")
            z = sp_stats.norm.ppf(1 - mw_p / 2) if mw_p < 1.0 else 0.0
            n_pair = len(a_vals) + len(b_vals)
            r = abs(z) / math.sqrt(n_pair) if n_pair > 0 else 0.0
            p_adj = min(mw_p * n_comparisons, 1.0)

            pairwise.append(PairwiseResult(
                group_a=a_name,
                group_b=b_name,
                p_value=round(mw_p, 4),
                p_adjusted=round(p_adj, 4),
                significant=p_adj < 0.05,
                effect_size_r=round(r, 3),
            ))

    return KruskalResult(
        h_statistic=round(float(h_stat), 3),
        p_value=round(float(kw_p), 4),
        significant=float(kw_p) < 0.05,
        eta_squared=round(eta_sq, 3),
        group_sizes=group_sizes,
        pairwise=pairwise,
        warnings=result_warnings,
    )


# ── Test 6: Time trend (Mann-Kendall) ─────────────────────────────────────────

@dataclass
class TimeTrendResult:
    """Result of a temporal trend analysis."""
    tau: float                  # Kendall's tau (-1 to 1)
    p_value: float
    significant: bool
    slope: float                # OLS slope (sentiment units per month)
    direction: str              # "improving" / "declining" / "stable"
    n_months: int
    monthly_data: list[dict]    # [{month: str, avg_sentiment: float, n_reports: int}]
    warnings: list[str] = field(default_factory=list)


def run_time_trend(conn: sqlite3.Connection, drug: str) -> TimeTrendResult | None:
    """Assess whether sentiment toward a drug is changing over calendar time.

    Aggregates to monthly bins, then runs:
    1. Kendall's tau for monotonic trend significance
    2. OLS linear regression for slope + visualization

    Returns None if fewer than 3 months of data.
    """
    sql = """
        SELECT p.post_date, tr.sentiment
        FROM treatment_reports tr
        JOIN treatment t ON t.id = tr.drug_id
        JOIN posts p ON p.post_id = tr.post_id
        WHERE t.canonical_name = ? COLLATE NOCASE
        AND p.post_date IS NOT NULL
        ORDER BY p.post_date
    """
    rows = conn.execute(sql, [drug]).fetchall()
    if not rows:
        return None

    df = pd.DataFrame(rows, columns=["post_date", "sentiment"])
    df["post_date"] = pd.to_datetime(df["post_date"], unit="s", errors="coerce")
    df = df.dropna(subset=["post_date"])
    if df.empty:
        return None

    # Aggregate to monthly bins
    df["month"] = df["post_date"].dt.to_period("M")
    monthly = df.groupby("month").agg(
        avg_sentiment=("sentiment", "mean"),
        n_reports=("sentiment", "count"),
    ).reset_index()
    monthly = monthly.sort_values("month")

    if len(monthly) < 3:
        return TimeTrendResult(
            tau=0.0, p_value=1.0, significant=False, slope=0.0,
            direction="stable", n_months=len(monthly),
            monthly_data=[],
            warnings=["Fewer than 3 months of data — trend analysis not meaningful."],
        )

    y = monthly["avg_sentiment"].values
    x = np.arange(len(y), dtype=float)

    # Kendall's tau
    tau, kendall_p = sp_stats.kendalltau(x, y)

    # OLS slope for visualization
    slope_result = sp_stats.linregress(x, y)
    slope = float(slope_result.slope)

    if kendall_p < 0.05:
        direction = "improving" if tau > 0 else "declining"
    else:
        direction = "stable"

    monthly_data = [
        {
            "month": str(row["month"]),
            "avg_sentiment": round(float(row["avg_sentiment"]), 3),
            "n_reports": int(row["n_reports"]),
        }
        for _, row in monthly.iterrows()
    ]

    return TimeTrendResult(
        tau=round(float(tau), 3),
        p_value=round(float(kendall_p), 4),
        significant=float(kendall_p) < 0.05,
        slope=round(slope, 4),
        direction=direction,
        n_months=len(monthly),
        monthly_data=monthly_data,
    )


# ── Test 7: Survival analysis (Cox PH) ────────────────────────────────────────

@dataclass
class SurvivalPredictor:
    """One covariate in the Cox PH model."""
    name: str
    hazard_ratio: float
    ci_lower: float
    ci_upper: float
    p_value: float
    significant: bool


@dataclass
class SurvivalResult:
    """Result of a Cox proportional hazards survival analysis."""
    predictors: list[SurvivalPredictor]
    concordance: float          # C-index (0.5 = random, 1.0 = perfect)
    n_users: int
    n_events: int               # users who reached positive outcome
    n_censored: int
    median_time_days: float | None  # median time to event (None if > 50% censored)
    warnings: list[str] = field(default_factory=list)


def _build_survival_data(
    conn: sqlite3.Connection,
    drug: str,
    predictor_names: list[str],
) -> pd.DataFrame | None:
    """Build a survival DataFrame for Cox PH.

    Entry:   user's earliest post in the subreddit
    Event:   first treatment_report with sentiment > 0.7 for this drug
    Censor:  users with reports for this drug but no positive → right-censored
             at their last report date
    Duration: days between entry and event/censor
    """
    # Get each user's first post date (entry into cohort)
    entry_sql = """
        SELECT user_id, MIN(post_date) AS entry_date
        FROM posts
        WHERE post_date IS NOT NULL
        GROUP BY user_id
    """
    entries = pd.DataFrame(
        conn.execute(entry_sql).fetchall(),
        columns=["user_id", "entry_date"],
    )

    # Get treatment reports with dates for this drug
    report_sql = """
        SELECT tr.user_id, p.post_date, tr.sentiment
        FROM treatment_reports tr
        JOIN treatment t ON t.id = tr.drug_id
        JOIN posts p ON p.post_id = tr.post_id
        WHERE t.canonical_name = ? COLLATE NOCASE
        AND p.post_date IS NOT NULL
        ORDER BY tr.user_id, p.post_date
    """
    reports = pd.DataFrame(
        conn.execute(report_sql, [drug]).fetchall(),
        columns=["user_id", "post_date", "sentiment"],
    )
    if reports.empty:
        return None

    # Find first positive report per user
    positive_reports = reports[reports["sentiment"] > 0.7]
    first_positive = positive_reports.groupby("user_id")["post_date"].min().reset_index()
    first_positive.columns = ["user_id", "event_date"]

    # Find last report per user (for censoring)
    last_report = reports.groupby("user_id")["post_date"].max().reset_index()
    last_report.columns = ["user_id", "last_report_date"]

    # All users who mentioned this drug
    drug_users = reports[["user_id"]].drop_duplicates()
    df = drug_users.merge(entries, on="user_id", how="inner")
    df = df.merge(first_positive, on="user_id", how="left")
    df = df.merge(last_report, on="user_id", how="left")

    # Calculate duration and event indicator
    df["event"] = df["event_date"].notna().astype(int)
    df["end_date"] = df["event_date"].fillna(df["last_report_date"])
    df["duration_days"] = (df["end_date"] - df["entry_date"]) / 86400  # seconds to days
    df["duration_days"] = df["duration_days"].clip(lower=1)  # minimum 1 day

    # Join predictors
    if "sex" in predictor_names or "age_bucket" in predictor_names:
        profiles = pd.DataFrame(
            conn.execute("SELECT user_id, sex, age_bucket FROM user_profiles").fetchall(),
            columns=["user_id", "sex", "age_bucket"],
        )
        df = df.merge(profiles, on="user_id", how="left")
        if "sex" in predictor_names:
            sex_map = {"female": 1, "f": 1, "woman": 1, "male": 0, "m": 0, "man": 0}
            df["sex"] = df["sex"].map(sex_map)
        if "age_bucket" in predictor_names:
            def bucket_to_ordinal(b):
                if pd.isna(b) or not isinstance(b, str):
                    return None
                digits = "".join(c for c in b if c.isdigit())
                return int(digits) // 10 if digits else None
            df["age_bucket"] = df["age_bucket"].map(bucket_to_ordinal)

    condition_preds = [p for p in predictor_names if p.startswith("has_")]
    if condition_preds:
        conditions = pd.DataFrame(
            conn.execute("SELECT user_id, condition_name FROM conditions").fetchall(),
            columns=["user_id", "condition_name"],
        )
        for pred in condition_preds:
            cond_name = pred[4:]
            matching = set(conditions.loc[
                conditions["condition_name"].str.contains(cond_name, case=False, na=False),
                "user_id",
            ])
            df[pred] = df["user_id"].isin(matching).astype(int)

    return df


def run_survival(
    conn: sqlite3.Connection,
    drug: str,
    predictor_names: list[str],
) -> SurvivalResult | None:
    """Run Cox proportional hazards survival analysis.

    Models time from a user's first subreddit post to their first positive
    treatment report for the given drug. Users who never report positively
    are right-censored at their last report date.

    Returns None if insufficient data (< 10 events).
    """
    from lifelines import CoxPHFitter

    df = _build_survival_data(conn, drug, predictor_names)
    if df is None or df.empty:
        return None

    n_events = int(df["event"].sum())
    n_users = len(df)
    result_warnings: list[str] = []

    if n_events < 10:
        return SurvivalResult(
            predictors=[], concordance=0.0,
            n_users=n_users, n_events=n_events,
            n_censored=n_users - n_events,
            median_time_days=None,
            warnings=[
                f"Only {n_events} events observed (need ≥ 10 for Cox PH). "
                "Cannot run survival analysis reliably."
            ],
        )

    # Prepare model DataFrame
    available_preds = [p for p in predictor_names if p in df.columns]
    model_cols = ["duration_days", "event"] + available_preds
    model_df = df[model_cols].dropna()

    if len(model_df) < 10:
        return None

    # Drop zero-variance predictors
    for pred in available_preds.copy():
        if model_df[pred].nunique() < 2:
            result_warnings.append(f"Predictor '{pred}' has no variance — dropped.")
            model_df = model_df.drop(columns=[pred])
            available_preds.remove(pred)

    # Fit Cox PH
    try:
        cph = CoxPHFitter()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cph.fit(
                model_df,
                duration_col="duration_days",
                event_col="event",
            )
    except Exception as e:
        return SurvivalResult(
            predictors=[], concordance=0.0,
            n_users=n_users, n_events=n_events,
            n_censored=n_users - n_events,
            median_time_days=None,
            warnings=[f"Cox PH failed to fit: {e}"],
        )

    # Extract per-predictor results
    pred_results = []
    summary = cph.summary
    for pred in available_preds:
        if pred not in summary.index:
            continue
        row = summary.loc[pred]
        pred_results.append(SurvivalPredictor(
            name=pred,
            hazard_ratio=round(float(row["exp(coef)"]), 3),
            ci_lower=round(float(row["exp(coef) lower 95%"]), 3),
            ci_upper=round(float(row["exp(coef) upper 95%"]), 3),
            p_value=round(float(row["p"]), 4),
            significant=float(row["p"]) < 0.05,
        ))

    # Median survival time
    median_time = None
    event_durations = model_df.loc[model_df["event"] == 1, "duration_days"]
    if len(event_durations) > 0:
        median_time = round(float(event_durations.median()), 1)

    return SurvivalResult(
        predictors=pred_results,
        concordance=round(float(cph.concordance_index_), 3),
        n_users=len(model_df),
        n_events=int(model_df["event"].sum()),
        n_censored=int((model_df["event"] == 0).sum()),
        median_time_days=median_time,
        warnings=result_warnings,
    )
