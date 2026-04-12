"""
app/analysis/models.py
~~~~~~~~~~~~~~~~~~~~~~
Pydantic v2 models for the analysis engine's result types.

These models mirror the dataclasses in stats.py and provide:
- Explicit validation (bounded fields, enum severities)
- Safe JSON serialization with .model_dump_json()
- Schema generation for documentation / OpenAPI
- Type-safe LLM handoff contract

Usage:
    from app.analysis.models import AnalysisResultModel
    from dataclasses import asdict
    result = run_comparison(df_a, df_b)
    model = ComparisonResultModel.model_validate(asdict(result))
    json_for_llm = model.model_dump_json()
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ── Warning severity enum ────────────────────────────────────────────────────

class WarningSeverity(str, Enum):
    caveat = "caveat"
    caution = "caution"
    unreliable = "unreliable"


class WarningModel(BaseModel):
    """Structured warning with machine-readable code and severity tier."""
    code: str = Field(description="Machine-readable identifier (e.g., 'low_epp', 'sparse_cells')")
    severity: WarningSeverity = Field(description="caveat (minor), caution (moderate), unreliable (do not trust)")
    message: str = Field(description="Human-readable explanation with specific numbers")


# ── Single drug summary ──────────────────────────────────────────────────────

class SingleDrugSummaryModel(BaseModel):
    drug: str
    n_users: int = Field(ge=0)
    n_posts: int = Field(ge=0)
    pct_positive: float = Field(ge=0, le=100)
    pct_positive_ci: tuple[float, float]
    pct_mixed: float = Field(ge=0, le=100)
    pct_neutral: float = Field(ge=0, le=100)
    pct_negative: float = Field(ge=0, le=100)
    mean_sentiment: float = Field(ge=-1, le=1)
    median_sentiment: float = Field(ge=-1, le=1)
    std_sentiment: float = Field(ge=0)


# ── Binomial test ────────────────────────────────────────────────────────────

class BinomialResultModel(BaseModel):
    n_users: int = Field(ge=0)
    n_positive: int = Field(ge=0)
    observed_rate: float = Field(ge=0, le=1)
    baseline: float = Field(ge=0, le=1)
    p_value: float = Field(ge=0, le=1)
    significant: bool
    ci_lower: float = Field(ge=0, le=1)
    ci_upper: float = Field(ge=0, le=1)
    warnings: list[WarningModel] = Field(default_factory=list)


# ── Comparison (Mann-Whitney + Chi-square/Fisher's) ──────────────────────────

class ComparisonResultModel(BaseModel):
    mw_statistic: float
    mw_p_value: float = Field(ge=0, le=1)
    mw_effect_size_r: float = Field(ge=-1, le=1)
    mw_significant: bool
    cat_test_name: str
    cat_statistic: float | None = None
    cat_p_value: float = Field(ge=0, le=1)
    cat_effect_size: float
    cat_significant: bool
    counts_a: dict[str, int]
    counts_b: dict[str, int]
    n_a: int = Field(ge=0)
    n_b: int = Field(ge=0)
    warnings: list[WarningModel] = Field(default_factory=list)


# ── Logistic regression ──────────────────────────────────────────────────────

class LogitPredictorModel(BaseModel):
    name: str
    coefficient: float
    odds_ratio: float = Field(ge=0)
    ci_lower: float = Field(ge=0)
    ci_upper: float = Field(ge=0)
    p_value: float = Field(ge=0, le=1)
    significant: bool


class LogitResultModel(BaseModel):
    predictors: list[LogitPredictorModel]
    pseudo_r2: float
    aic: float
    n_obs: int = Field(ge=0)
    n_events: int = Field(ge=0)
    converged: bool
    warnings: list[WarningModel] = Field(default_factory=list)


# ── OLS regression ───────────────────────────────────────────────────────────

class OLSPredictorModel(BaseModel):
    name: str
    coefficient: float
    ci_lower: float
    ci_upper: float
    p_value: float = Field(ge=0, le=1)
    significant: bool


class OLSResultModel(BaseModel):
    predictors: list[OLSPredictorModel]
    r_squared: float = Field(ge=0, le=1)
    adj_r_squared: float
    f_statistic: float
    f_p_value: float = Field(ge=0, le=1)
    n_obs: int = Field(ge=0)
    warnings: list[WarningModel] = Field(default_factory=list)


# ── Kruskal-Wallis ───────────────────────────────────────────────────────────

class PairwiseResultModel(BaseModel):
    group_a: str
    group_b: str
    p_value: float = Field(ge=0, le=1, description="Raw uncorrected p-value")
    p_bonferroni: float = Field(ge=0, le=1, description="Bonferroni-corrected p-value")
    p_fdr: float = Field(ge=0, le=1, description="Benjamini-Hochberg FDR-corrected p-value")
    significant: bool = Field(description="True if p_fdr < 0.05")
    effect_size_r: float


class KruskalResultModel(BaseModel):
    h_statistic: float
    p_value: float = Field(ge=0, le=1)
    significant: bool
    eta_squared: float
    group_sizes: dict[str, int]
    pairwise: list[PairwiseResultModel]
    warnings: list[WarningModel] = Field(default_factory=list)


# ── Time trend ───────────────────────────────────────────────────────────────

class MonthlyDataPoint(BaseModel):
    month: str
    avg_sentiment: float
    n_reports: int = Field(ge=0)


class TimeTrendResultModel(BaseModel):
    tau: float = Field(ge=-1, le=1)
    p_value: float = Field(ge=0, le=1)
    significant: bool
    slope: float
    direction: Literal["improving", "declining", "stable"]
    n_months: int = Field(ge=0)
    monthly_data: list[MonthlyDataPoint]
    warnings: list[WarningModel] = Field(default_factory=list)


# ── Survival (Cox PH) ───────────────────────────────────────────────────────

class SurvivalPredictorModel(BaseModel):
    name: str
    hazard_ratio: float = Field(ge=0)
    ci_lower: float = Field(ge=0)
    ci_upper: float = Field(ge=0)
    p_value: float = Field(ge=0, le=1)
    significant: bool


class SurvivalResultModel(BaseModel):
    predictors: list[SurvivalPredictorModel]
    concordance: float = Field(ge=0, le=1)
    n_users: int = Field(ge=0)
    n_events: int = Field(ge=0)
    n_censored: int = Field(ge=0)
    median_time_days: float | None = None
    warnings: list[WarningModel] = Field(default_factory=list)


# ── Wilcoxon signed-rank ─────────────────────────────────────────────────────

class WilcoxonResultModel(BaseModel):
    statistic: float
    p_value: float = Field(ge=0, le=1)
    significant: bool
    effect_size_r: float
    direction: Literal["drug_a_better", "drug_b_better", "no_difference"]
    drug_a: str
    drug_b: str
    n_paired: int = Field(ge=0)
    mean_diff: float
    median_diff: float
    warnings: list[WarningModel] = Field(default_factory=list)


# ── Spearman correlation ─────────────────────────────────────────────────────

class SpearmanResultModel(BaseModel):
    rho: float = Field(ge=-1, le=1)
    p_value: float = Field(ge=0, le=1)
    significant: bool
    n: int = Field(ge=0)
    variable_a: str
    variable_b: str
    warnings: list[WarningModel] = Field(default_factory=list)


# ── Propensity score matching ────────────────────────────────────────────────

class BalanceRow(BaseModel):
    predictor: str
    smd_before: float
    smd_after: float


class PropensityResultModel(BaseModel):
    n_matched: int = Field(ge=0)
    n_unmatched_treated: int = Field(ge=0)
    ate: float
    ate_ci_lower: float
    ate_ci_upper: float
    p_value: float = Field(ge=0, le=1)
    significant: bool
    balance_table: list[BalanceRow]
    warnings: list[WarningModel] = Field(default_factory=list)


# ── Conversion helper ────────────────────────────────────────────────────────

def to_model(result) -> BaseModel:
    """Convert a dataclass result to its Pydantic model equivalent.

    Uses the dataclass type name to find the matching Pydantic model.
    """
    from dataclasses import asdict

    type_map = {
        "SingleDrugSummary": SingleDrugSummaryModel,
        "BinomialResult": BinomialResultModel,
        "ComparisonResult": ComparisonResultModel,
        "LogitResult": LogitResultModel,
        "OLSResult": OLSResultModel,
        "KruskalResult": KruskalResultModel,
        "TimeTrendResult": TimeTrendResultModel,
        "SurvivalResult": SurvivalResultModel,
        "WilcoxonResult": WilcoxonResultModel,
        "SpearmanResult": SpearmanResultModel,
        "PropensityResult": PropensityResultModel,
    }

    cls_name = type(result).__name__
    model_cls = type_map.get(cls_name)
    if model_cls is None:
        raise ValueError(f"No Pydantic model for {cls_name}")

    return model_cls.model_validate(asdict(result))
