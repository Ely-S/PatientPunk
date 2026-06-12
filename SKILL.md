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
- Use `statsmodels` for statistical tests and models when needed
- Use `matplotlib` or `seaborn` for charts
- Every code cell should have a markdown cell above it explaining what it does and why
- Include a **Summary** markdown cell at the end with key findings in plain language
- Hard-code the database path as a variable at the top of the notebook so it's easy to change

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
| Statistical test | `statsmodels.stats`, `scipy.stats` |
| Regression | `statsmodels.formula.api.ols` |
| Save notebook | Write to `notebooks/N_topic.ipynb` |

## Common Mistakes

- **Building before exploring** — always run schema + sample queries first; the data often doesn't match expectations
- **Skipping approval** — never generate the notebook before the researcher signs off on the plan
- **Silent data quality issues** — if nulls or small N could affect conclusions, say so in the plan and again in the notebook summary
- **Opaque notebooks** — every code cell needs a markdown explanation; notebooks are read by people who weren't in the conversation
