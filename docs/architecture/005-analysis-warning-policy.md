# ADR-005: Analysis functions return warnings for risky-but-usable statistical output

**Status:** Accepted
**Date:** 2026-04-09
**Deciders:** Shaun, Codex

## Context

PatientPunk's analysis layer is used to summarize messy observational data extracted
from Reddit. The data regularly contains:

- small cohort sizes
- imbalanced comparison groups
- sparse categorical tables
- missing demographic coverage
- mixed timestamp formats
- regression separation and non-convergence
- heavy censoring in survival analysis

These situations are common enough that treating them all as hard failures would
make the analysis layer brittle and difficult to use in the UI.

At the same time, silently returning clean-looking numbers for statistically shaky
results is dangerous because downstream consumers may over-trust them.

## Decision

The analysis layer will prefer **structured warnings over exceptions** for
statistical problems that still produce an interpretable output.

Examples:

- sparse or imbalanced two-group comparisons
- dropped rows from missing predictors
- unstable or non-converged logistic regression
- non-finite fit metrics normalized to safe defaults
- short or gappy trend series
- low event rates or heavy censoring in survival analysis

Hard failures should be reserved for:

- invalid input parameters
- empty datasets where no result is possible
- model states that are effectively unusable after filtering

## Consequences

- UI and LLM consumers must read and render the `warnings` field rather than
  treating it as optional noise.
- Documentation and examples should present warnings as part of the contract.
- Tests should cover both numeric outputs and warning behavior.
- Statistical sanity checks belong close to the analysis code, while final
  interpretation belongs downstream.
