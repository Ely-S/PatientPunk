# Analysis Engine Plan

## What this is

A pure-Python statistical analysis engine for querying the PatientPunk database. No UI, no LLM calls — just functions that take a SQLite connection and return structured results with warnings.

This engine will be consumed by a Haiku-powered interface (built separately) where Haiku acts as a statistician: it selects the appropriate test based on the user's question, runs it through this engine, and explains the results in plain language. The structured warning system ensures Haiku knows when to hedge, caveat, or refuse to present results.

## Architecture

```
User question (natural language)
        |
        v
  Haiku wizard (selects test, checks sample sizes)
        |
        v
  Payload builder (normalizes results, computes max_severity)
        |
        v
  Stats engine  <-- THIS PR
  (app/analysis/stats.py)
        |
        v
  Structured result + warnings
        |
        v
  Haiku explainer (interprets results at appropriate confidence level)
        |
        v
  Streamlit UI (graphs + text)
```

The stats engine sits at the bottom of this stack. It knows nothing about Haiku, Streamlit, or natural language. It takes parameters, runs math, and returns dataclasses.

## Key design decisions

### User-level aggregation

All statistics aggregate to **one data point per user per drug**. If a user posted 10 times about LDN, they contribute one average sentiment score, not 10. This achieves independence — a requirement for every test in the suite.

### Warning-oriented, not exception-oriented

Most problematic-but-usable situations do not raise exceptions. Instead, they attach an `AnalysisWarning(code, severity, message)` to the result. The downstream layer (Haiku) uses the severity to decide how confidently to present findings.

### Benjamini-Hochberg FDR

Post-hoc pairwise comparisons report both Bonferroni (conservative) and BH FDR (exploratory-friendly) adjusted p-values. Significance is based on FDR by default — appropriate for exploratory patient data where finding real signals matters more than eliminating every possible false positive.

## Build order for the UI (not in this PR)

1. Payload builder — hard boundary between stats engine and LLM
2. Wizard — Haiku guides the user to a research question
3. Results — Haiku explains output with appropriate confidence
4. Charts — descriptive (bar charts, histograms) + inferential (forest plots, KM curves)
5. Streamlit app — ties it together

## What Haiku will do with this engine

Haiku receives a normalized JSON payload containing:
- The statistical result (p-values, effect sizes, counts)
- Structured warnings with severity tiers
- A `max_severity` field computed deterministically from the warnings

Haiku's system prompt will instruct it to:
- Name the test and explain what it does in one sentence
- Present the result with appropriate confidence based on `max_severity`
- Never hide warnings — every warning appears in the explanation
- Use specific numbers from warnings ("only 8 users" not "few users")
- If `max_severity` is "unreliable", explicitly disclaim the result
- Always end with the reporting bias disclaimer
