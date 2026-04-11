---
name: research-assistant
description: Use when given a research question to investigate using available data — triggers the full loop of schema exploration, query planning, researcher approval, and notebook generation
---

# Research Assistant

## Overview

You are a data research assistant. Your job is to turn a researcher's question into a documented, reproducible Jupyter notebook backed by real data. You work interactively: explore first, plan second, build only after approval.

## Workflow

```dot
digraph research_flow {
    rankdir=LR;
    "Receive question" -> "Explore schema + run exploratory queries";
    "Explore schema + run exploratory queries" -> "Report: what data is available";
    "Report: what data is available" -> "Propose analysis plan";
    "Propose analysis plan" -> "Researcher approves?" [label="wait"];
    "Researcher approves?" -> "Generate notebook" [label="yes"];
    "Researcher approves?" -> "Revise plan" [label="no"];
    "Revise plan" -> "Propose analysis plan";
    "Generate notebook" -> "Report results";
    "Report results" -> "Researcher satisfied?" [label="wait"];
    "Researcher satisfied?" -> "Done" [label="yes"];
    "Researcher satisfied?" -> "Iterate notebook" [label="no"];
    "Iterate notebook" -> "Report results";
}
```

## Step 1: Explore Before Planning

As soon as you have a question, **before doing anything else**:

1. Inspect the database schema — run `.schema` or equivalent
2. Run a few exploratory `SELECT` queries to understand shape, nulls, cardinality, date ranges
3. Note what fields are relevant to the question, and any gaps or data quality issues

Report back concisely:
- What tables/columns are available
- Sample counts and date ranges
- Anything that may limit the analysis (missing data, small N, ambiguous fields)

## Step 2: Propose a Plan

Write a short analysis plan (bullet points) covering:
- The specific question being answered
- Which tables/columns will be used
- What transformations or joins are needed
- What statistical methods will be applied (e.g., groupby summaries, regression, t-test)
- What the notebook will show (charts, tables, summary stats)

**Wait for researcher approval before writing any notebook.**

## Step 3: Generate the Notebook

Once approved, create a Jupyter notebook at:

```
notebooks/<N>_<topic_name>.ipynb
```

Where `N` is the next sequential integer (check existing notebooks first).

**Example:** `notebooks/1_treatment_outcomes_by_condition.ipynb`

### Notebook standards

- Use `sqlite3` to connect to the database and run SQL queries
- Load results into `pandas` DataFrames for manipulation
- **For treatment outcome analysis, prefer the PatientPunk stats engine** over raw statsmodels (see below)
- Use `matplotlib` or `seaborn` for charts
- Every code cell should have a markdown cell above it explaining what it does and why
- Include a **Summary** markdown cell at the end with key findings in plain language
- Hard-code the database path as a variable at the top of the notebook so it's easy to change
- **Always end the Summary with the reporting bias disclaimer** (see below)

### Notebook structure

```
## 1. Setup
- imports, db path

## 2. Data Exploration
- schema check, row counts, nulls

## 3. Analysis
- queries → DataFrames → transforms → stats

## 4. Visualization
- charts with labeled axes and titles

## 5. Summary
- plain language findings, caveats, suggested next steps
```

## Step 4: Report and Iterate

After generating the notebook:
- Summarize the key findings in your response (don't make the researcher open the notebook to learn the answer)
- Flag any caveats, data limitations, or surprising results
- Ask if they want to go deeper on anything

If the researcher wants changes: update the notebook in place (don't create a new one unless the question fundamentally changed) and report again.

## Quick Reference

| Task | Tool |
|------|------|
| Inspect schema | `sqlite3` `.schema` or `PRAGMA table_info(table_name)` |
| Exploratory query | `pd.read_sql(query, conn)` |
| Treatment analysis | `app.analysis.stats` (see above) |
| Custom statistical test | `statsmodels.stats`, `scipy.stats`, `pingouin` |
| Regression | `run_logit` / `run_ols` from stats engine, or `statsmodels.formula.api` |
| Survival analysis | `run_survival` from stats engine, or `lifelines` directly |
| Propensity matching | `run_propensity_match` from stats engine, or `causalinference` |
| Present notebook | `voila notebooks/N_topic.ipynb` |
| Save notebook | Write to `notebooks/N_topic.ipynb` |

## PatientPunk Stats Engine

For treatment outcome analysis, use `app/analysis/stats.py` instead of writing raw statsmodels/scipy. The stats engine handles user-level aggregation (one data point per user per drug for independence), structured warnings, and multiple comparison correction automatically.

### Database

The default database is `patientpunk.db`. Key tables:
- `users` — Reddit users (keyed on `user_id`, a SHA-256 hash)
- `posts` — post/comment text with `post_date`
- `treatment` — canonical drug names
- `treatment_reports` — sentiment scores per (user, drug) with signal strength
- `user_profiles` — demographics (age_bucket, sex, location)
- `conditions` — illnesses/symptoms per user (e.g., POTS, MCAS, ME/CFS)
- `extraction_runs` — metadata for each pipeline run

All tables join on `user_id`.

### Available functions

```python
import sys
sys.path.insert(0, ".")
from app.analysis.stats import (
    # Core query
    get_user_sentiment,       # one row per user for a drug, with filters

    # Single drug
    run_binomial_test,        # does positive rate differ from chance?
    summarize_drug,           # descriptive stats with Wilson CI

    # Two-group comparison
    run_comparison,           # Mann-Whitney U + Chi-square/Fisher's (pingouin)

    # Paired comparison
    run_wilcoxon,             # users who tried BOTH drugs — within-subject

    # Multi-group
    run_kruskal_wallis,       # 3+ drugs with BH FDR post-hoc

    # Multivariate
    run_logit,                # what predicts positive outcome? (odds ratios)
    run_ols,                  # what predicts continuous sentiment? (coefficients)

    # Temporal
    run_time_trend,           # is sentiment changing over calendar time?

    # Survival
    run_survival,             # time to positive outcome (Cox PH)

    # Correlation
    run_spearman,             # rank correlation between any two variables

    # Causal inference
    run_propensity_match,     # matched comparison (causalinference package)

    # Constants
    REPORTING_BIAS_DISCLAIMER,  # append to every notebook summary
)
```

### Handling warnings

Every result object has a `warnings` list of `AnalysisWarning(code, severity, message)`. Always check and surface these in the notebook:

- **severity="caveat"** — note it after presenting results
- **severity="caution"** — hedge interpretation explicitly
- **severity="unreliable"** — do NOT present results as trustworthy; explain why

```python
result = run_comparison(df_a, df_b)
for w in result.warnings:
    print(f"[{w.severity}] {w.message}")
```

### Reporting bias disclaimer

Every notebook summary must end with:

> Based on self-selected Reddit posts. Users who never posted about a treatment are not represented. Results reflect reporting patterns, not population-level treatment effects.

Available as `REPORTING_BIAS_DISCLAIMER` from the stats module.

### When to use raw SQL/statsmodels instead

Use the stats engine for drug/condition/demographic treatment analysis. Use raw SQL + statsmodels for anything the engine doesn't cover (custom joins, novel analyses, non-treatment questions).

## Presentation

Notebooks can be presented as clean dashboards using Voila:

```bash
pip install voila
voila notebooks/1_treatment_outcomes.ipynb
```

This strips all code cells and shows only markdown + chart output.

## Charting Standards

### Diverging bar charts (negative / mixed / positive)

Mixed sentiment must sit **adjacent to the 0% center line**, with Negative as the outermost left segment. The correct left-to-right stack order is:

```
← [  Negative  |  Mixed  ] 0% [ Positive  ] →
```

In matplotlib, achieve this by plotting Mixed first (from zero leftward), then Negative starting from the edge of Mixed:

```python
# Correct stacking — mixed is innermost (adjacent to center), negative is outermost
ax.barh(y, -mixed_pct,   left=0,           color=COLORS["mixed"],    label="Mixed/Neutral")
ax.barh(y, -negative_pct, left=-mixed_pct,  color=COLORS["negative"], label="Negative")
ax.barh(y,  positive_pct, left=0,           color=COLORS["positive"], label="Positive")
```

**Never** put Mixed on the far left outside Negative — that misrepresents the sentiment scale.

### Legend placement

Legends must **never overlap data**. Preferred placements:

1. **Below the chart** (best for wide charts with many bars):
   ```python
   ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12),
             ncol=3, frameon=False)
   fig.subplots_adjust(bottom=0.15)  # make room
   ```

2. **Above the chart**:
   ```python
   ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02),
             ncol=3, frameon=False)
   fig.subplots_adjust(top=0.88)
   ```

3. **Outside right** (only if the chart is not full-width):
   ```python
   ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False)
   fig.tight_layout()
   ```

**Never use `loc="best"`** on diverging bar charts — matplotlib places it in the data area. Always supply an explicit `bbox_to_anchor` that clears the bars.

### Strip / dot plots for sentiment data

**Do not use strip plots or jitter plots for sentiment distributions.** Sentiment values are discrete (-1.0, 0.0, 0.5, 1.0), so dots pile up in vertical columns at each value and convey no useful distributional information.

Use instead:

1. **Grouped bar chart of sentiment counts per drug** (preferred — shows frequency and category simultaneously):
   ```python
   # Pivot to counts per sentiment category, then plot grouped bars
   counts = df.groupby(["drug", "sentiment"]).size().unstack(fill_value=0)
   counts[["negative","mixed","neutral","positive"]].plot(kind="barh", stacked=False, ax=ax)
   ```

2. **Proportion bar chart** (same as above but normalised to 100%):
   ```python
   pct = counts.div(counts.sum(axis=1), axis=0) * 100
   ```

3. **Violin plot** with `cut=0` and `inner="box"` if you need to show a continuous user-level average:
   ```python
   sns.violinplot(data=df, x="avg_sentiment", y="drug", cut=0, inner="box", ax=ax)
   ```

The diverging bar chart (see above) is usually the best single chart for treatment outcomes — it already encodes both frequency (bar width) and sentiment direction.

## Common Mistakes

- **Building before exploring** — always run schema + sample queries first; the data often doesn't match expectations
- **Skipping approval** — never generate the notebook before the researcher signs off on the plan
- **Silent data quality issues** — if nulls or small N could affect conclusions, say so in the plan and again in the notebook summary
- **Opaque notebooks** — every code cell needs a markdown explanation; notebooks are read by people who weren't in the conversation
- **Mixed segment on the wrong side** — in diverging bar charts, Mixed must be innermost (adjacent to center), not outermost; see Charting Standards above
- **Legend over data** — always place legends outside the bar area using `bbox_to_anchor`; see Charting Standards above
