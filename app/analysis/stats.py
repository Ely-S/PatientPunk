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


# ── Structured warnings ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class AnalysisWarning:
    """Structured warning attached to statistical results.

    Attributes
    ----------
    code     : machine-readable identifier (e.g. "small_sample", "low_epp")
    severity : "caveat" | "caution" | "unreliable"
        caveat     — minor limitation, present results with a note
        caution    — moderate issue, hedge interpretation strongly
        unreliable — results should not be treated as trustworthy
    message  : human-readable explanation with specific numbers
    """
    code: str
    severity: str       # "caveat" | "caution" | "unreliable"
    message: str

    def to_dict(self) -> dict:
        return {"code": self.code, "severity": self.severity, "message": self.message}


def _warn(code: str, severity: str, message: str) -> AnalysisWarning:
    """Shorthand constructor for AnalysisWarning."""
    return AnalysisWarning(code=code, severity=severity, message=message)


def _safe_exp(value: float) -> float:
    """Exponentiate a log-scale coefficient without emitting overflow warnings."""
    clipped = float(np.clip(value, -700, 700))
    return float(np.exp(clipped))


def _round_or_default(value: float, digits: int, default: float = 0.0) -> float:
    """Round finite numeric values, otherwise return a safe default."""
    return round(float(value), digits) if np.isfinite(value) else default


def _filter_predictors(
    df: pd.DataFrame,
    predictor_names: list[str],
    sparse_threshold: float = 0.8,
) -> tuple[list[str], list[AnalysisWarning]]:
    """Filter predictors by coverage and variance. Shared by logit/OLS/survival.

    Steps:
    1. Drop predictors where > sparse_threshold of values are NaN
    2. Drop predictors with zero variance (only one unique value after dropna)

    Returns (available_predictors, warnings).
    """
    available = []
    warn_list: list[AnalysisWarning] = []

    for pred in predictor_names:
        if pred not in df.columns:
            continue
        nan_rate = df[pred].isna().mean()
        if nan_rate > sparse_threshold:
            warn_list.append(_warn("sparse_predictor", "caveat",
                f"Predictor '{pred}' is missing for > {int(sparse_threshold * 100)}% of users — dropped."
            ))
            continue
        available.append(pred)

    return available, warn_list


def _drop_zero_variance(
    X: pd.DataFrame,
    predictor_names: list[str],
    warn_list: list[AnalysisWarning],
) -> tuple[pd.DataFrame, list[str]]:
    """Drop predictors with no variance from feature matrix X.

    Modifies warn_list in place. Returns (X, remaining_predictors).
    """
    remaining = []
    for pred in predictor_names:
        if X[pred].nunique() < 2:
            warn_list.append(_warn("zero_variance_predictor", "caveat",
                f"Predictor '{pred}' has no variance — dropped."
            ))
            X = X.drop(columns=[pred])
        else:
            remaining.append(pred)
    return X, remaining


def _check_vif(
    X: pd.DataFrame,
    predictor_names: list[str],
    warn_list: list[AnalysisWarning],
    threshold: float = 5.0,
) -> None:
    """Check VIF multicollinearity and append warnings. Best-effort."""
    if len(predictor_names) < 2:
        return
    try:
        from statsmodels.stats.outliers_influence import variance_inflation_factor
        pred_matrix = X[predictor_names].astype(float)
        for j, pred in enumerate(predictor_names):
            vif = variance_inflation_factor(pred_matrix.values, j)
            if np.isfinite(vif) and vif > threshold:
                warn_list.append(_warn("high_vif", "caution",
                    f"High multicollinearity on '{pred}' (VIF={vif:.1f}) — "
                    "coefficient may be unstable."
                ))
    except Exception:
        pass


def _dedupe_warnings(warnings_list: list[AnalysisWarning]) -> list[AnalysisWarning]:
    """Preserve order while removing duplicate warnings (by code)."""
    seen: set[str] = set()
    result = []
    for w in warnings_list:
        if w.code not in seen:
            seen.add(w.code)
            result.append(w)
    return result


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
    condition_clause = ""
    sex_clause = ""
    age_clause = ""

    if condition:
        condition_clause = """
            AND EXISTS (
                SELECT 1 FROM conditions c
                WHERE c.user_id = tr.user_id
                AND LOWER(c.condition_name) LIKE LOWER(?)
            )
        """

    if sex:
        sex_clause = """
            AND EXISTS (
                SELECT 1 FROM user_profiles up
                WHERE up.user_id = tr.user_id
                AND LOWER(up.sex) = LOWER(?)
            )
        """

    if age_bucket:
        age_clause = """
            AND EXISTS (
                SELECT 1 FROM user_profiles up
                WHERE up.user_id = tr.user_id
                AND up.age_bucket = ?
            )
        """

    sql = f"""
        SELECT
            tr.user_id,
            AVG(tr.sentiment)   AS avg_sentiment,
            COUNT(*)            AS n_posts
        FROM treatment_reports tr
        JOIN treatment t ON t.id = tr.drug_id
        WHERE t.canonical_name = ? COLLATE NOCASE
        {condition_clause}
        {sex_clause}
        {age_clause}
        GROUP BY tr.user_id
    """
    ordered_params: list = []
    ordered_params.append(drug)
    if condition:
        ordered_params.append(f"%{condition}%")
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
    warnings: list[AnalysisWarning] = field(default_factory=list)


def check_sample_sizes(group_a: pd.Series, group_b: pd.Series) -> SampleSizeCheck:
    """Check whether sample sizes are adequate for the planned tests.

    Flags:
    - Either group has n < 5 (too small for any meaningful test)
    - Either group has n < 20 (results should be interpreted cautiously)
    - Any expected cell count < 5 in the chi-square contingency table
      (triggers fallback to Fisher's exact test)
    """
    warn_list: list[AnalysisWarning] = []
    na, nb = len(group_a), len(group_b)

    if na < 5 or nb < 5:
        return SampleSizeCheck(
            ok=False,
            warnings=[_warn("sample_too_small", "unreliable",
                f"Sample sizes are too small to run a meaningful test "
                f"(Group A: {na} users, Group B: {nb} users). "
                f"At least 5 users per group are needed."
            )],
        )

    if na < 20:
        warn_list.append(_warn("small_sample", "caveat",
            f"Group A has only {na} users — interpret results cautiously."
        ))
    if nb < 20:
        warn_list.append(_warn("small_sample", "caveat",
            f"Group B has only {nb} users — interpret results cautiously."
        ))
    ratio = max(na, nb) / min(na, nb)
    if ratio >= 3:
        warn_list.append(_warn("imbalanced_samples", "caveat",
            f"Sample sizes are imbalanced ({na} vs {nb} users), which can distort effect estimates."
        ))

    return SampleSizeCheck(ok=True, warnings=warn_list)


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
    warnings: list[AnalysisWarning]


def _count_categories(series: pd.Series) -> dict[str, int]:
    """Count each sentiment category, ensuring all 4 are present."""
    counts = series.value_counts().to_dict()
    return {cat: counts.get(cat, 0) for cat in SENTIMENT_CATEGORIES}


def _mann_whitney_effect_size(scores_a: pd.Series, scores_b: pd.Series, p_value: float) -> float:
    """Return signed Mann-Whitney r using the larger-median group for direction."""
    total_n = len(scores_a) + len(scores_b)
    if total_n == 0 or p_value >= 1.0:
        return 0.0

    z = sp_stats.norm.ppf(1 - p_value / 2)
    if not np.isfinite(z):
        return 0.0

    median_a = float(scores_a.median())
    median_b = float(scores_b.median())
    direction = 0.0
    if median_a > median_b:
        direction = 1.0
    elif median_a < median_b:
        direction = -1.0

    return direction * (abs(float(z)) / math.sqrt(total_n))


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
    if scores_a.nunique() == 1 and scores_b.nunique() == 1:
        comparison_warnings = list(size_check.warnings)
        comparison_warnings.append(_warn("no_within_variation", "caution",
            "Both groups have zero within-group sentiment variation."
        ))
    else:
        comparison_warnings = list(size_check.warnings)

    # ── Check for identical distributions ─────────────────────────────────────
    if scores_a.nunique() == 1 and scores_b.nunique() == 1 and float(scores_a.iloc[0]) == float(scores_b.iloc[0]):
        comparison_warnings.append(_warn("identical_distributions", "unreliable",
            "Both groups have identical sentiment distributions — no comparison possible."
        ))

    # ── Mann-Whitney U ────────────────────────────────────────────────────────
    mw_stat, mw_p = sp_stats.mannwhitneyu(scores_a, scores_b, alternative="two-sided")
    mw_r = _mann_whitney_effect_size(scores_a, scores_b, float(mw_p))

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
    if len(active_cats) < 2:
        comparison_warnings.append(_warn("single_category", "unreliable",
            "Only one sentiment category is present across both groups; the categorical comparison is not informative."
        ))

    if len(active_cats) >= 2:
        chi2_stat, chi2_p, _, expected = sp_stats.chi2_contingency(observed)
        use_fisher = len(active_cats) == 2 and (
            has_zero_observed or any(cell < 5 for row in expected for cell in row)
        )
        if len(active_cats) > 2 and any(cell < 5 for row in expected for cell in row):
            comparison_warnings.append(_warn("sparse_cells", "caveat",
                "Categorical comparison uses chi-square with sparse cells; interpret cautiously."
            ))
    else:
        chi2_stat, chi2_p, expected = None, None, None
        use_fisher = True

    if use_fisher:
        fisher_table = observed if len(active_cats) == 2 else [
            [counts_a["positive"], n_a - counts_a["positive"]],
            [counts_b["positive"], n_b - counts_b["positive"]],
        ]
        odds_ratio_raw, fisher_p = sp_stats.fisher_exact(fisher_table)
        if len(active_cats) == 2:
            a00, a01 = fisher_table[0]
            b00, b01 = fisher_table[1]
            odds_ratio = ((a00 + 0.5) * (b01 + 0.5)) / ((a01 + 0.5) * (b00 + 0.5))
        else:
            pos_a = counts_a["positive"]
            pos_b = counts_b["positive"]
            not_pos_a = n_a - pos_a
            not_pos_b = n_b - pos_b
            odds_ratio = ((pos_a + 0.5) * (not_pos_b + 0.5)) / ((not_pos_a + 0.5) * (pos_b + 0.5))
        cat_name = "Fisher's exact"
        cat_stat = None
        cat_p = fisher_p
        cat_effect = round(float(odds_ratio if np.isfinite(odds_ratio_raw) else odds_ratio), 3)
    else:
        # Cramér's V as effect size
        n_total = n_a + n_b
        k = len(active_cats) - 1  # (cols - 1) for 2-row table
        cramers_v = math.sqrt(chi2_stat / (n_total * k)) if n_total > 0 and k > 0 else 0.0
        cat_name = "chi-square"
        cat_stat = round(chi2_stat, 3)
        cat_p = chi2_p
        cat_effect = round(cramers_v, 3)

    if abs(mw_r) > 0.8 and max(n_a, n_b) < 20:
        comparison_warnings.append(_warn("large_effect_small_n", "caution",
            "A very large Mann-Whitney effect was estimated from a small sample."
        ))

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
        warnings=_dedupe_warnings(comparison_warnings),
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
    warnings: list[AnalysisWarning] = field(default_factory=list)


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
    if not 0 <= baseline <= 1:
        raise ValueError("baseline must be between 0 and 1 inclusive")

    n = len(df)
    n_pos = int((df["category"] == "positive").sum())
    result = sp_stats.binomtest(n_pos, n, p=baseline, alternative="two-sided")
    ci_lower, ci_upper = wilson_ci(n_pos, n)
    result_warnings: list[AnalysisWarning] = []
    if n < 10:
        result_warnings.append(_warn("small_sample", "caveat", f"Only {n} users available for the binomial test."))
    if n_pos == 0 or n_pos == n:
        result_warnings.append(_warn("no_variation", "caution", "Observed outcomes have no variation; the rate estimate is extreme."))
    if baseline in (0.0, 1.0):
        result_warnings.append(_warn("extreme_baseline", "caution", "Baseline is at an extreme boundary (0 or 1); interpret cautiously."))

    return BinomialResult(
        n_users=n,
        n_positive=n_pos,
        observed_rate=round(n_pos / n, 3),
        baseline=baseline,
        p_value=round(result.pvalue, 4),
        significant=result.pvalue < 0.05,
        ci_lower=round(ci_lower, 3),
        ci_upper=round(ci_upper, 3),
        warnings=_dedupe_warnings(result_warnings),
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
    warnings: list[AnalysisWarning] = field(default_factory=list)


def _load_latest_profiles(conn: sqlite3.Connection) -> pd.DataFrame:
    """Return one profile row per user using the latest available extraction run."""
    rows = conn.execute(
        """
        SELECT up.user_id, up.sex, up.age_bucket
        FROM user_profiles up
        JOIN (
            SELECT user_id, MAX(run_id) AS run_id
            FROM user_profiles
            GROUP BY user_id
        ) latest
            ON latest.user_id = up.user_id
           AND latest.run_id = up.run_id
        """
    ).fetchall()
    return pd.DataFrame(rows, columns=["user_id", "sex", "age_bucket"])


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
        profiles = _load_latest_profiles(conn)
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

    # Filter predictors by coverage and variance
    available_predictors, result_warnings = _filter_predictors(df, predictor_names)
    if not available_predictors:
        return LogitResult(
            predictors=[], pseudo_r2=0.0, aic=0.0,
            n_obs=len(df), n_events=int(df["positive"].sum()),
            converged=False,
            warnings=result_warnings + [_warn("no_predictors", "unreliable", "No predictors with sufficient coverage.")],
        )

    cols = ["positive"] + available_predictors
    model_df = df[cols].dropna()
    dropped_rows = len(df) - len(model_df)
    if dropped_rows > 0:
        result_warnings.append(_warn("rows_dropped", "caveat",
            f"Dropped {dropped_rows} users with missing predictor values before fitting."
        ))
    if len(model_df) < 10:
        return None

    y = model_df["positive"]
    if y.nunique() < 2:
        return LogitResult(
            predictors=[], pseudo_r2=0.0, aic=0.0,
            n_obs=len(model_df), n_events=int(y.sum()),
            converged=False,
            warnings=_dedupe_warnings(
                result_warnings + [_warn("no_variation", "unreliable", "Outcome has no variation after filtering; logistic regression is unusable.")]
            ),
        )
    X = sm.add_constant(model_df[available_predictors].astype(float))

    # Check events-per-predictor rule (≥ 10 events per predictor)
    n_events = int(y.sum())
    if n_events < 10 * len(available_predictors):
        result_warnings.append(_warn("low_epp", "caution",
            f"Low events-per-predictor ratio ({n_events} events / "
            f"{len(available_predictors)} predictors). Results may be unreliable."
        ))

    X, available_predictors = _drop_zero_variance(X, available_predictors, result_warnings)
    if not available_predictors:
        return LogitResult(
            predictors=[], pseudo_r2=0.0, aic=0.0,
            n_obs=len(model_df), n_events=n_events,
            converged=False,
            warnings=result_warnings + [_warn("no_predictors", "unreliable", "All predictors had zero variance after filtering.")],
        )

    _check_vif(X, available_predictors, result_warnings)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            logit_model = sm.Logit(y, X)
            fit = logit_model.fit(disp=0, maxiter=100)
            converged = bool(
                fit.mle_retvals.get("converged", False) if hasattr(fit, "mle_retvals") else True
            )
            llf = float(fit.llf)
            llnull = float(fit.llnull)
            aic = float(fit.aic)
            conf = fit.conf_int()

            pred_results = []
            for pred in available_predictors:
                if pred not in fit.params.index:
                    continue
                coef = fit.params[pred]
                ci_lo, ci_hi = conf.loc[pred]
                p_value = float(fit.pvalues[pred])
                pred_results.append(LogitPredictor(
                    name=pred,
                    coefficient=round(float(coef), 3),
                    odds_ratio=round(_safe_exp(float(coef)), 3),
                    ci_lower=round(_safe_exp(float(ci_lo)), 3),
                    ci_upper=round(_safe_exp(float(ci_hi)), 3),
                    p_value=round(p_value, 4),
                    significant=p_value < 0.05,
                ))
    except Exception as e:
        return LogitResult(
            predictors=[], pseudo_r2=0.0, aic=0.0,
            n_obs=len(model_df), n_events=n_events,
            converged=False,
            warnings=[f"Model failed to fit: {e}"],
        )
    if not converged:
        result_warnings.append(_warn("non_convergence", "unreliable", "Logistic regression did not fully converge."))
    if not np.isfinite(llnull):
        result_warnings.append(_warn("unstable_ll", "unreliable", "Baseline log-likelihood is non-finite; model fit is unstable."))
        pseudo_r2 = 0.0
    elif llnull == 0:
        result_warnings.append(_warn("unstable_ll", "unreliable", "Baseline log-likelihood is zero; pseudo R² is undefined."))
        pseudo_r2 = 0.0
    else:
        pseudo_r2 = 1 - (llf / llnull)
        if not np.isfinite(pseudo_r2):
            result_warnings.append(_warn("unstable_r2", "unreliable", "Pseudo R² is non-finite; model fit is unstable."))
            pseudo_r2 = 0.0
    if pred_results and all(not pred.significant for pred in pred_results) and n_events < 20:
        result_warnings.append(_warn("no_sig_small_n", "caution",
            "No predictors were significant and the event count is small."
        ))

    return LogitResult(
        predictors=pred_results,
        pseudo_r2=_round_or_default(pseudo_r2, 3),
        aic=_round_or_default(aic, 1),
        n_obs=int(fit.nobs),
        n_events=n_events,
        converged=converged,
        warnings=_dedupe_warnings(result_warnings),
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
    warnings: list[AnalysisWarning] = field(default_factory=list)


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

    available_predictors, result_warnings = _filter_predictors(df, predictor_names)
    if not available_predictors:
        return OLSResult(
            predictors=[], r_squared=0.0, adj_r_squared=0.0,
            f_statistic=0.0, f_p_value=1.0, n_obs=len(df),
            warnings=result_warnings + [_warn("no_predictors", "unreliable", "No predictors with sufficient coverage.")],
        )

    model_cols = ["avg_sentiment"] + available_predictors
    model_df = df[model_cols].dropna()
    dropped_rows = len(df) - len(model_df)
    if dropped_rows > 0:
        result_warnings.append(_warn("rows_dropped", "caveat",
            f"Dropped {dropped_rows} users with missing predictor values before fitting."
        ))
    if len(model_df) < 10:
        return None

    # Use shared helpers for zero-variance and VIF checks
    y = model_df["avg_sentiment"]
    if y.nunique() < 2:
        return OLSResult(
            predictors=[], r_squared=0.0, adj_r_squared=0.0,
            f_statistic=0.0, f_p_value=1.0, n_obs=len(model_df),
            warnings=_dedupe_warnings(
                result_warnings + [_warn("no_variation", "unreliable", "Outcome has no variation after filtering; OLS is not informative.")]
            ),
        )
    X = sm.add_constant(model_df[available_predictors].astype(float))
    X, available_predictors = _drop_zero_variance(X, available_predictors, result_warnings)
    if not available_predictors:
        return OLSResult(
            predictors=[], r_squared=0.0, adj_r_squared=0.0,
            f_statistic=0.0, f_p_value=1.0, n_obs=len(model_df),
            warnings=result_warnings + [_warn("no_predictors", "unreliable", "All predictors had zero variance.")],
        )
    _check_vif(X, available_predictors, result_warnings)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            fit = sm.OLS(y, X).fit()
    except Exception as e:
        return OLSResult(
            predictors=[], r_squared=0.0, adj_r_squared=0.0,
            f_statistic=0.0, f_p_value=1.0, n_obs=len(model_df),
            warnings=[f"OLS failed to fit: {e}"],
        )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        fvalue = float(fit.fvalue)
        f_pvalue = float(fit.f_pvalue)
        rsquared = float(fit.rsquared)
        adj_r_squared = float(fit.rsquared_adj)
    if not np.isfinite(fvalue):
        result_warnings.append(_warn("unstable_fit", "unreliable", "OLS F-statistic is non-finite; model fit is unstable."))
        fvalue = 0.0
        f_pvalue = 1.0

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
        r_squared=_round_or_default(rsquared, 3),
        adj_r_squared=_round_or_default(adj_r_squared, 3),
        f_statistic=_round_or_default(fvalue, 3),
        f_p_value=_round_or_default(f_pvalue, 4, default=1.0),
        n_obs=int(fit.nobs),
        warnings=_dedupe_warnings(result_warnings),
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
    warnings: list[AnalysisWarning] = field(default_factory=list)


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

    result_warnings: list[AnalysisWarning] = []
    for name, n in group_sizes.items():
        if n < 20:
            result_warnings.append(_warn("small_group", "caveat", f"Group '{name}' has only {n} users."))
        if valid[name]["avg_sentiment"].nunique() == 1:
            result_warnings.append(_warn("no_within_variation", "caution", f"Group '{name}' has zero within-group sentiment variation."))

    # Kruskal-Wallis H test
    h_stat, kw_p = sp_stats.kruskal(*arrays)
    eta_sq = float(h_stat) / (N - 1) if N > 1 else 0.0

    # Post-hoc pairwise Mann-Whitney with Bonferroni correction
    n_comparisons = len(group_names) * (len(group_names) - 1) // 2
    if n_comparisons >= 10:
        result_warnings.append(_warn("multiple_comparisons", "caveat",
            f"{n_comparisons} pairwise comparisons — Bonferroni correction applied, "
            "individual effects may be masked."
        ))
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
        warnings=_dedupe_warnings(result_warnings),
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
    warnings: list[AnalysisWarning] = field(default_factory=list)


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
    df["post_date"] = _parse_mixed_datetimes(df["post_date"])
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
    result_warnings: list[AnalysisWarning] = []

    if len(monthly) < 3:
        return TimeTrendResult(
            tau=0.0, p_value=1.0, significant=False, slope=0.0,
            direction="stable", n_months=len(monthly),
            monthly_data=[],
            warnings=[_warn("misc", "caveat", "Fewer than 3 months of data — trend analysis not meaningful.")],
        )
    if len(monthly) < 6:
        result_warnings.append(_warn("short_series", "caution", "Fewer than 6 months of data are available for trend estimation."))
    month_index = pd.period_range(monthly["month"].min(), monthly["month"].max(), freq="M")
    if len(month_index) != len(monthly):
        result_warnings.append(_warn("gappy_series", "caution", "Monthly data contain gaps; trend estimates may be distorted."))
    if monthly["avg_sentiment"].nunique() == 1:
        result_warnings.append(_warn("no_variation", "caution", "Monthly sentiment has no variation; trend testing is not informative."))

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
        warnings=_dedupe_warnings(result_warnings),
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
    warnings: list[AnalysisWarning] = field(default_factory=list)


def _parse_mixed_datetimes(values: pd.Series) -> pd.Series:
    """Parse epoch-second or ISO-style datetimes into naive timestamps."""
    numeric_dates = pd.to_numeric(values, errors="coerce")
    parsed_numeric = pd.to_datetime(numeric_dates, unit="s", errors="coerce", utc=True)
    parsed_generic = pd.to_datetime(values, errors="coerce", utc=True)
    return parsed_numeric.fillna(parsed_generic).dt.tz_localize(None)


def _load_parsed_posts(conn: sqlite3.Connection) -> pd.DataFrame:
    """Load posts with normalized datetimes for downstream temporal analyses."""
    posts = pd.DataFrame(
        conn.execute(
            "SELECT post_id, user_id, post_date FROM posts WHERE post_date IS NOT NULL"
        ).fetchall(),
        columns=["post_id", "user_id", "post_date"],
    )
    if posts.empty:
        return posts
    posts["post_date"] = _parse_mixed_datetimes(posts["post_date"])
    posts = posts.dropna(subset=["post_date"])
    return posts


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
    posts = _load_parsed_posts(conn)
    if posts.empty:
        return None
    entries = posts.groupby("user_id", as_index=False)["post_date"].min()
    entries.columns = ["user_id", "entry_date"]

    # Get treatment reports with dates for this drug
    report_sql = """
        SELECT tr.user_id, tr.post_id, tr.sentiment
        FROM treatment_reports tr
        JOIN treatment t ON t.id = tr.drug_id
        WHERE t.canonical_name = ? COLLATE NOCASE
    """
    reports = pd.DataFrame(
        conn.execute(report_sql, [drug]).fetchall(),
        columns=["user_id", "post_id", "sentiment"],
    )
    if reports.empty:
        return None
    reports = reports.merge(posts[["post_id", "post_date"]], on="post_id", how="inner")
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
    df["duration_days"] = (df["end_date"] - df["entry_date"]).dt.total_seconds() / 86400
    df["duration_days"] = df["duration_days"].clip(lower=1)  # minimum 1 day

    # Join predictors
    if "sex" in predictor_names or "age_bucket" in predictor_names:
        profiles = _load_latest_profiles(conn)
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
    result_warnings: list[AnalysisWarning] = []

    if n_events < 10:
        early_warnings: list[AnalysisWarning] = [
            _warn("too_few_events", "unreliable",
                f"Only {n_events} events observed (need ≥ 10 for Cox PH). "
                "Cannot run survival analysis reliably.")
        ]
        if n_users > 0 and (n_users - n_events) > n_users / 2:
            early_warnings.append(_warn("heavy_censoring", "caution",
                "More than half of observations are censored."))
        if n_users > 0 and (n_events / n_users) < 0.2:
            early_warnings.append(_warn("low_event_rate", "caution",
                "Event rate is below 20%; hazard estimates may be unstable."))
        return SurvivalResult(
            predictors=[], concordance=0.0,
            n_users=n_users, n_events=n_events,
            n_censored=n_users - n_events,
            median_time_days=None,
            warnings=_dedupe_warnings(early_warnings),
        )

    # Prepare model DataFrame
    available_preds = [p for p in predictor_names if p in df.columns]
    model_cols = ["duration_days", "event"] + available_preds
    model_df = df[model_cols].dropna()
    dropped_rows = len(df) - len(model_df)
    if dropped_rows > 0:
        result_warnings.append(_warn("rows_dropped", "caveat",
            f"Dropped {dropped_rows} users with missing predictor values before fitting."
        ))

    if len(model_df) < 10:
        return None

    model_df, available_preds = _drop_zero_variance(model_df, available_preds, result_warnings)

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
    if int((model_df["event"] == 0).sum()) <= len(model_df) / 2:
        event_durations = model_df.loc[model_df["event"] == 1, "duration_days"]
    else:
        event_durations = pd.Series(dtype=float)
        result_warnings.append(_warn("heavy_censoring", "caution", "More than half of observations are censored."))
    if len(event_durations) > 0:
        median_time = round(float(event_durations.median()), 1)
    event_rate = float(model_df["event"].mean())
    if event_rate < 0.2:
        result_warnings.append(_warn("low_event_rate", "caution", "Event rate is below 20%; hazard estimates may be unstable."))
    if (model_df["duration_days"] <= 1).mean() > 0.25:
        result_warnings.append(_warn("clipped_durations", "caution", "Many durations were clipped to the 1-day minimum."))

    return SurvivalResult(
        predictors=pred_results,
        concordance=round(float(cph.concordance_index_), 3),
        n_users=len(model_df),
        n_events=int(model_df["event"].sum()),
        n_censored=int((model_df["event"] == 0).sum()),
        median_time_days=median_time,
        warnings=_dedupe_warnings(result_warnings),
    )


# ── Test 9: Wilcoxon signed-rank (paired within-subject) ─────────────────────

@dataclass
class WilcoxonResult:
    """Result of a paired within-subject comparison (Wilcoxon signed-rank)."""
    statistic: float
    p_value: float
    significant: bool
    effect_size_r: float        # r = Z / sqrt(N)
    direction: str              # "drug_a_better" / "drug_b_better" / "no_difference"
    drug_a: str
    drug_b: str
    n_paired: int               # users who tried both
    mean_diff: float            # mean(sentiment_a - sentiment_b)
    median_diff: float
    warnings: list[AnalysisWarning] = field(default_factory=list)


def get_paired_sentiment(
    conn: sqlite3.Connection,
    drug_a: str,
    drug_b: str,
) -> pd.DataFrame | None:
    """Return one row per user who tried BOTH drugs.

    Columns: user_id, sentiment_a, sentiment_b, diff
    """
    sql = """
        SELECT
            a.user_id,
            a.avg_a,
            b.avg_b
        FROM (
            SELECT tr.user_id, AVG(tr.sentiment) AS avg_a
            FROM treatment_reports tr
            JOIN treatment t ON t.id = tr.drug_id
            WHERE t.canonical_name = ? COLLATE NOCASE
            GROUP BY tr.user_id
        ) a
        JOIN (
            SELECT tr.user_id, AVG(tr.sentiment) AS avg_b
            FROM treatment_reports tr
            JOIN treatment t ON t.id = tr.drug_id
            WHERE t.canonical_name = ? COLLATE NOCASE
            GROUP BY tr.user_id
        ) b ON a.user_id = b.user_id
    """
    rows = conn.execute(sql, [drug_a, drug_b]).fetchall()
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["user_id", "sentiment_a", "sentiment_b"])
    df["diff"] = df["sentiment_a"] - df["sentiment_b"]
    return df


def run_wilcoxon(
    conn: sqlite3.Connection,
    drug_a: str,
    drug_b: str,
) -> WilcoxonResult | None:
    """Paired within-subject comparison of two drugs using Wilcoxon signed-rank.

    Only includes users who tried BOTH drugs — all between-subject confounders
    (severity, demographics, illness duration) cancel out.

    Returns None if fewer than 5 paired users.
    """
    df = get_paired_sentiment(conn, drug_a, drug_b)
    if df is None or len(df) < 5:
        return None

    n = len(df)
    result_warnings: list[AnalysisWarning] = []

    if n < 20:
        result_warnings.append(_warn("small_paired_n", "caveat",
            f"Only {n} users tried both drugs — interpret cautiously."
        ))

    diffs = df["diff"].values

    # Check for zero differences (ties) — Wilcoxon drops them
    non_zero = diffs[diffs != 0]
    if len(non_zero) == 0:
        return WilcoxonResult(
            statistic=0.0, p_value=1.0, significant=False,
            effect_size_r=0.0, direction="no_difference",
            drug_a=drug_a, drug_b=drug_b, n_paired=n,
            mean_diff=0.0, median_diff=0.0,
            warnings=result_warnings + [_warn("zero_differences", "unreliable", "All paired differences are zero — no comparison possible.")],
        )

    stat, p = sp_stats.wilcoxon(diffs, alternative="two-sided")

    # Effect size r = Z / sqrt(N)
    z = sp_stats.norm.ppf(1 - p / 2) if p < 1.0 else 0.0
    r = z / math.sqrt(n) if n > 0 and np.isfinite(z) else 0.0

    mean_diff = float(np.mean(diffs))
    if mean_diff > 0:
        direction = "drug_a_better"
    elif mean_diff < 0:
        direction = "drug_b_better"
    else:
        direction = "no_difference"

    return WilcoxonResult(
        statistic=round(float(stat), 3),
        p_value=round(float(p), 4),
        significant=float(p) < 0.05,
        effect_size_r=round(r, 3),
        direction=direction,
        drug_a=drug_a,
        drug_b=drug_b,
        n_paired=n,
        mean_diff=round(mean_diff, 3),
        median_diff=round(float(np.median(diffs)), 3),
        warnings=_dedupe_warnings(result_warnings),
    )


# ── Test 10: Spearman correlation ─────────────────────────────────────────────

@dataclass
class SpearmanResult:
    """Result of a Spearman rank correlation."""
    rho: float                  # -1 to 1
    p_value: float
    significant: bool
    n: int
    variable_a: str
    variable_b: str
    warnings: list[AnalysisWarning] = field(default_factory=list)


def run_spearman(
    values_a: pd.Series,
    values_b: pd.Series,
    label_a: str = "variable_a",
    label_b: str = "variable_b",
) -> SpearmanResult | None:
    """Spearman rank correlation between two numeric series.

    Useful for: sentiment vs signal strength, number of posts vs outcome,
    time since first post vs sentiment, etc.

    Returns None if fewer than 5 paired observations.
    """
    # Align and drop NaN
    combined = pd.DataFrame({"a": values_a, "b": values_b}).dropna()
    if len(combined) < 5:
        return None

    n = len(combined)
    result_warnings: list[AnalysisWarning] = []

    if n < 20:
        result_warnings.append(_warn("small_sample", "caveat", f"Only {n} observations — interpret cautiously."))

    if combined["a"].nunique() < 3 or combined["b"].nunique() < 3:
        result_warnings.append(_warn("low_variability", "caution", "One or both variables have very low variability."))

    rho, p = sp_stats.spearmanr(combined["a"], combined["b"])

    return SpearmanResult(
        rho=round(float(rho), 3),
        p_value=round(float(p), 4),
        significant=float(p) < 0.05,
        n=n,
        variable_a=label_a,
        variable_b=label_b,
        warnings=_dedupe_warnings(result_warnings),
    )


# ── Test 11: Propensity score matching ────────────────────────────────────────

@dataclass
class PropensityResult:
    """Result of propensity-score-matched comparison."""
    n_matched: int              # pairs after matching
    n_unmatched_treated: int    # treated users that couldn't be matched
    ate: float                  # average treatment effect (mean diff in matched pairs)
    ate_ci_lower: float
    ate_ci_upper: float
    p_value: float
    significant: bool
    balance_table: list[dict]   # [{predictor, smd_before, smd_after}]
    warnings: list[AnalysisWarning] = field(default_factory=list)


def run_propensity_match(
    conn: sqlite3.Connection,
    drug: str,
    predictor_names: list[str],
    caliper: float = 0.2,
) -> PropensityResult | None:
    """Propensity score matching: compare users who tried a drug vs those who didn't.

    1. Build a feature matrix of all users with treatment reports
    2. Fit logistic regression predicting treatment (tried drug vs not)
    3. Match treated to untreated on propensity score within caliper
    4. Compare sentiment in matched pairs

    Returns None if insufficient data or predictors.
    """
    import statsmodels.api as sm

    # Get all users with any treatment report
    all_users_sql = """
        SELECT DISTINCT tr.user_id
        FROM treatment_reports tr
    """
    all_user_ids = {r[0] for r in conn.execute(all_users_sql).fetchall()}

    # Get users who tried THIS drug
    drug_users_sql = """
        SELECT DISTINCT tr.user_id, AVG(tr.sentiment) AS avg_sentiment
        FROM treatment_reports tr
        JOIN treatment t ON t.id = tr.drug_id
        WHERE t.canonical_name = ? COLLATE NOCASE
        GROUP BY tr.user_id
    """
    drug_df = pd.DataFrame(
        conn.execute(drug_users_sql, [drug]).fetchall(),
        columns=["user_id", "sentiment"],
    )
    if drug_df.empty or len(drug_df) < 10:
        return None

    treated_ids = set(drug_df["user_id"])
    control_ids = all_user_ids - treated_ids

    if len(control_ids) < 10:
        return None

    # Get average sentiment for control users (across all their drugs)
    control_sql = """
        SELECT tr.user_id, AVG(tr.sentiment) AS avg_sentiment
        FROM treatment_reports tr
        WHERE tr.user_id IN ({})
        GROUP BY tr.user_id
    """.format(",".join("?" for _ in control_ids))
    control_df = pd.DataFrame(
        conn.execute(control_sql, list(control_ids)).fetchall(),
        columns=["user_id", "sentiment"],
    )

    # Build combined DataFrame
    drug_df["treated"] = 1
    control_df["treated"] = 0
    df = pd.concat([drug_df, control_df], ignore_index=True)

    # Join predictors
    result_warnings: list[AnalysisWarning] = []
    available_predictors = []

    if any(p in ("sex", "age_bucket") for p in predictor_names):
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

    # Drop sparse predictors
    for pred in predictor_names:
        if pred in df.columns and df[pred].isna().mean() <= 0.8 and df[pred].nunique() >= 2:
            available_predictors.append(pred)
        elif pred in df.columns:
            result_warnings.append(_warn("sparse_predictor", "caveat", f"Predictor '{pred}' dropped (sparse or no variance)."))

    if not available_predictors:
        return PropensityResult(
            n_matched=0, n_unmatched_treated=len(treated_ids), ate=0.0,
            ate_ci_lower=0.0, ate_ci_upper=0.0, p_value=1.0, significant=False,
            balance_table=[],
            warnings=result_warnings + [_warn("no_predictors", "unreliable", "No valid predictors for propensity model.")],
        )

    model_df = df[["user_id", "treated", "sentiment"] + available_predictors].dropna()
    if len(model_df) < 20:
        return None

    # Fit propensity score model
    y = model_df["treated"]
    X = sm.add_constant(model_df[available_predictors].astype(float))

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ps_model = sm.Logit(y, X).fit(disp=0)
        model_df["propensity"] = ps_model.predict(X)
    except Exception as e:
        return PropensityResult(
            n_matched=0, n_unmatched_treated=len(treated_ids), ate=0.0,
            ate_ci_lower=0.0, ate_ci_upper=0.0, p_value=1.0, significant=False,
            balance_table=[],
            warnings=[f"Propensity model failed: {e}"],
        )

    # Nearest-neighbor matching within caliper
    treated = model_df[model_df["treated"] == 1].copy()
    control = model_df[model_df["treated"] == 0].copy()

    matched_pairs: list[tuple[float, float]] = []  # (sentiment_treated, sentiment_control)
    matched_treated_idx = set()
    matched_control_idx = set()

    for idx, row in treated.iterrows():
        ps = row["propensity"]
        distances = (control["propensity"] - ps).abs()
        # Exclude already-matched controls
        distances = distances[~distances.index.isin(matched_control_idx)]
        if distances.empty:
            continue
        nearest_idx = distances.idxmin()
        if distances[nearest_idx] <= caliper * model_df["propensity"].std():
            matched_pairs.append((row["sentiment"], control.loc[nearest_idx, "sentiment"]))
            matched_treated_idx.add(idx)
            matched_control_idx.add(nearest_idx)

    n_matched = len(matched_pairs)
    if n_matched < 5:
        return PropensityResult(
            n_matched=n_matched,
            n_unmatched_treated=len(treated) - n_matched,
            ate=0.0, ate_ci_lower=0.0, ate_ci_upper=0.0,
            p_value=1.0, significant=False, balance_table=[],
            warnings=result_warnings + [_warn("few_matches", "unreliable", f"Only {n_matched} matches found (need ≥ 5).")],
        )

    # ATE = mean difference in matched pairs
    diffs = [t - c for t, c in matched_pairs]
    ate = float(np.mean(diffs))
    se = float(np.std(diffs, ddof=1)) / math.sqrt(n_matched)
    ci_lower = ate - 1.96 * se
    ci_upper = ate + 1.96 * se

    # Paired t-test on matched differences
    _, p = sp_stats.ttest_rel(
        [t for t, c in matched_pairs],
        [c for t, c in matched_pairs],
    )

    # Balance table: standardized mean difference before/after matching
    balance_table = []
    for pred in available_predictors:
        t_before = model_df.loc[model_df["treated"] == 1, pred].mean()
        c_before = model_df.loc[model_df["treated"] == 0, pred].mean()
        pooled_std = model_df[pred].std()
        smd_before = (t_before - c_before) / pooled_std if pooled_std > 0 else 0.0

        t_after = model_df.loc[list(matched_treated_idx), pred].mean()
        c_after = model_df.loc[list(matched_control_idx), pred].mean()
        smd_after = (t_after - c_after) / pooled_std if pooled_std > 0 else 0.0

        balance_table.append({
            "predictor": pred,
            "smd_before": round(smd_before, 3),
            "smd_after": round(smd_after, 3),
        })
        if abs(smd_after) > 0.1:
            result_warnings.append(_warn("residual_imbalance", "caution",
                f"Residual imbalance on '{pred}' after matching (SMD={smd_after:.2f})."
            ))

    return PropensityResult(
        n_matched=n_matched,
        n_unmatched_treated=len(treated) - n_matched,
        ate=round(ate, 3),
        ate_ci_lower=round(ci_lower, 3),
        ate_ci_upper=round(ci_upper, 3),
        p_value=round(float(p), 4),
        significant=float(p) < 0.05,
        balance_table=balance_table,
        warnings=_dedupe_warnings(result_warnings),
    )


# ── Survivorship / reporting bias disclaimer ──────────────────────────────────

REPORTING_BIAS_DISCLAIMER = (
    "Based on self-selected Reddit posts. Users who never posted about a "
    "treatment are not represented. Results reflect reporting patterns, not "
    "population-level treatment effects."
)
