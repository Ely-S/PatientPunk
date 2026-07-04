# Reporting Guardrails

Date: 2026-07-04

This note defines language, evidence, and privacy guardrails for A4 reports.

## Core Rule

A4 reports describe self-reported patterns in a Reddit community. They do not
establish diagnosis, prevalence, causality, efficacy, safety, or medical advice.

Every public-facing report should include language equivalent to:

```text
These are self-reported Reddit comments from one community. They are useful for
hypothesis generation and lived-experience mapping, not for estimating clinical
prevalence or making treatment decisions.
```

## Allowed Claim Language

Prefer:

```text
reported
described
mentioned
self-reported
in this extracted sample
among comments that passed the current audit gate
suggestive pattern
```

Avoid:

```text
proves
causes
effective
safe
prevalence
risk reduction
patients improved because of
doctor should prescribe
```

## Confidence Language

A4 should separate:

- model extraction confidence
- audit confidence
- evidence/report confidence

Do not turn model `confidence=high` into report confidence. A high-confidence
wrong extraction is still wrong.

Report confidence should depend on A3 scoring, audit coverage, normalization
review, and sample size.

## Denominator Language

Every percentage should state its denominator:

Good:

```text
42 of 180 extracted symptom claims in this run were canonicalized as fatigue.
```

Bad:

```text
23% of patients had fatigue.
```

The current comments dataset cannot support patient-level denominators unless
author deduplication is deliberately added and validated.

## Quote Guardrails

Quotes should:

- come from `evidence_quote` or reviewed quote candidates
- be short
- be representative
- be linked to claim IDs internally
- have redaction status recorded
- avoid unnecessary rare details that increase re-identification risk

Quotes should not:

- include usernames
- include direct Reddit permalinks in public summaries by default
- combine text from multiple authors into one quote
- be used to imply causality beyond what the author stated
- be selected only for emotional force

## Bias And Limitation Checklist

Every A4 report should mention:

- single-community source
- platform and posting-selection bias
- comment-only limitation if root submissions are unavailable
- missing silent outcomes from people who did not post follow-up
- model extraction error risk
- audit sample size
- normalization/version limitations
- no clinical verification
- no adverse-event denominator

## Quality Gates For Reportability

A4 should mark a finding `not_reportable` if:

- A3 validation failed.
- evidence-source violations exist for the relevant row set.
- normalized labels are unreviewed and high-impact.
- audit disagreement rows show unresolved context leakage.
- denominators are unclear.
- source run gate decision is `stop`, `revise_a1_prompt`, `revise_a1_schema`,
  `revise_a2_runner`, or `revise_a3_audit`.

A4 can mark a finding `exploratory` if:

- A3 validation passed.
- normalization exists.
- audit is missing or too small.
- the finding is used only internally for prioritizing review.

A4 can mark a finding `suggestive_signal` or higher only when:

- A3 audit scorecards exist.
- relevant error rates pass configured thresholds.
- Wilson intervals are acceptable for the intended use.
- representative quotes have been reviewed.

## Methods Transparency

A4 methods should include enough detail that another analyst can reproduce the
finding:

```text
source A2 run IDs
A1 prompt/schema versions
A2 model and instrument hashes
A3 analysis and normalization versions
row counts
file hashes
audit sample sizes
thresholds used
known warnings
```

This follows the spirit of qualitative reporting guidelines such as COREQ and
evidence-map/scoping-review transparency practices such as PRISMA-ScR, adapted
to this pipeline.

## Research Takeaway

A4 should be opinionated about caution. The product is not only a report; it is
a report with enough provenance, denominator discipline, and caveat structure
that downstream readers cannot easily mistake community self-reports for
clinical evidence.

