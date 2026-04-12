# Analysis Engine Plan

## What this is

A pure-Python statistical analysis engine for querying the PatientPunk database. No UI, no LLM calls — just functions that take a SQLite connection and return structured results with warnings.

This engine is consumed by a **Claude Code research-assistant skill** (`SKILL.md`) where Claude acts as a statistician: it explores the database, selects the appropriate test based on the user's question, runs it through this engine, and explains the results in a Jupyter notebook. The structured warning system ensures Claude knows when to hedge, caveat, or refuse to present results.

## Architecture

```
User question (natural language)
        |
        v
  Research-assistant skill (SKILL.md)
  Claude explores database, proposes analysis plan
        |
        v
  User approves plan
        |
        v
  Stats engine  <-- THIS PR
  (app/analysis/stats.py)
        |
        v
  Structured result + warnings
        |
        v
  Claude generates Jupyter notebook
  (charts, tables, plain-language summary, caveats)
        |
        v
  Voila renders notebook as web dashboard for presentation
```

The stats engine sits at the bottom of this stack. It knows nothing about Claude, notebooks, or natural language. It takes parameters, runs math, and returns dataclasses.

## Key design decisions

### User-level aggregation

All statistics aggregate to **one data point per user per drug**. If a user posted 10 times about LDN, they contribute one average sentiment score, not 10. This achieves independence — a requirement for every test in the suite.

### Warning-oriented, not exception-oriented

Most problematic-but-usable situations do not raise exceptions. Instead, they attach an `AnalysisWarning(code, severity, message)` to the result. The downstream layer (Claude / notebook) uses the severity to decide how confidently to present findings:
- **caveat** — present results, then note the limitation
- **caution** — present with explicit hedging
- **unreliable** — do not present as trustworthy; explain why and suggest alternatives

### Benjamini-Hochberg FDR

Post-hoc pairwise comparisons report both Bonferroni (conservative) and BH FDR (exploratory-friendly) adjusted p-values. Significance is based on FDR by default — appropriate for exploratory patient data where finding real signals matters more than eliminating every possible false positive.

### Package-backed statistics

Every statistical computation uses an established package — no hand-rolled formulas:
- `pingouin` — Mann-Whitney U, Wilcoxon, effect sizes
- `statsmodels` — logistic/OLS regression, Wilson CI, BH FDR, odds ratios
- `scipy` — chi-square, Fisher's exact, Cramér's V, Spearman, Kendall, binomial
- `lifelines` — Cox proportional hazards
- `causalinference` — propensity score matching

## Presentation layer (not in this PR)

The research-assistant skill generates Jupyter notebooks as output. For hackathon presentation, **Voila** renders these as clean web dashboards (no code cells visible, just charts and text).

**Future upgrade paths:**
- **Marimo** — reactive notebooks with interactive widgets (dropdowns, sliders). ~2-3 hours to switch. Same analysis code, different notebook format.
- **Streamlit** — full web app with chat interface. More polish, more code. Build if the project continues.

## What Claude will do with this engine

The research-assistant skill instructs Claude to:
1. Explore the database schema and run sample queries
2. Propose an analysis plan and wait for approval
3. Generate a notebook using this stats engine for treatment outcome analysis
4. Surface all warnings in the notebook summary
5. End every notebook with `REPORTING_BIAS_DISCLAIMER`
6. Flag caveats, data limitations, and surprising results
