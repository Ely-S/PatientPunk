# Audit And Scoring Plan

Date: 2026-07-04

This note defines how A3 should evaluate A2 outputs. It is grounded in the
existing `patientpunk.evaluate` and `dev/eval` patterns, but adapted to
comment-level and claim-level coding.

## Scoring Units

A3 needs two scoring units:

- comment-level decisions
- claim-level extractions

Comment-level questions:

- should this target comment be codeable?
- was the skip reason correct?
- did the model miss any target-author claim?
- did it extract any claim from context rather than the target?
- did it need context and use it correctly?

Claim-level questions:

- is this claim supported by the target comment?
- is the evidence quote sufficient?
- is the claim type correct?
- is the normalized label correct enough for analysis?
- is the experiencer correct?
- is the assertion correct?
- is confidence calibrated?

## Gold, Silver, And Audit Labels

A3 should distinguish:

```text
gold: human-reviewed labels
silver: strong-model reference or adjudication aid
candidate: cheap-model A2 output
```

A strong model can help triage disagreements, but it should not silently become
ground truth. The final A2 scale gate should be based on human-reviewed or
explicitly adjudicated rows.

## Core Metrics

### Structured Validity

Measured by A2:

```text
structured_success_rate = successful validated rows / attempted rows
final_failure_rate = final failed work items / attempted rows
retry_rate = rows needing >1 attempt / attempted rows
```

### Comment-Level Metrics

Against gold/audit labels:

```text
codeable_accuracy
skip_accuracy
wrong_skip_rate
missed_claim_rate
over_extracted_claim_rate
parent_context_leakage_rate
unsupported_evidence_comment_rate
context_use_accuracy
```

### Claim-Level Metrics

Against audited claim rows:

```text
claim_precision
claim_type_accuracy
normalized_label_accuracy
experiencer_accuracy
assertion_accuracy
evidence_support_rate
duplicate_claim_rate
```

Recall is harder at claim level because it requires gold claims that may not
align one-to-one with model claims. Start with manually labeled missed-claim
flags at comment level, then add gold claim rows when the codebook stabilizes.

## Wilson Intervals

A3 should report rates with Wilson confidence intervals, following
`dev/eval/wilson.py`.

For every rate:

```text
k successes
n audited opportunities
p_hat
95% Wilson lower
95% Wilson upper
```

If zero failures are observed, A3 should report the rule-of-three upper bound on
the failure rate. Example:

```text
0 failures in n=50 does not mean 0% true failure rate.
Rule-of-three upper bound is about 3/50 = 6%.
```

This is important before A2 scales from 200 audited rows to hundreds of
thousands of comments.

## Disagreement Analysis

A3 should compare candidate vs reference at the row level before summarizing.

Useful disagreement views:

- cheap model codeable but reference skip
- cheap model skip but reference codeable
- cheap model uses context but reference says not needed
- cheap model extracted claims when target only asked a question
- cheap model assigns `self` when target discusses another person
- cheap model marks context as unused for "same here" cases
- unsupported evidence quotes
- high-confidence wrong claims

Every prompt revision in A1 should tie back to a concrete disagreement cluster.

## Audit Sample Design

Audit samples should be stratified, not only random.

Mandatory strata:

- removed/deleted
- short comments
- long comments
- replies with available parent
- replies with missing parent
- top-level comments with missing root post
- context-reference rows
- other-person rows
- question-only rows
- low attribution confidence rows
- context-used rows
- retry-success rows
- failed rows
- high claim count rows

For each live A2 gate, A3 should produce:

```text
audit_sample_ids.jsonl
audit_comment_template.csv
audit_claim_template.csv
```

## Thresholds For A2 Gates

Initial suggested thresholds:

```text
structured_success_rate >= 0.99
final_failure_rate <= 0.01
parent_context_leakage_rate <= 0.02
unsupported_evidence_rate <= 0.02
wrong_experiencer_rate <= 0.03
wrong_assertion_rate <= 0.05
deleted_removed_skip_accuracy >= 0.99
high_confidence_error_rate <= 0.02
```

These are starting thresholds. A1 should revise them after actual review. A3's
job is to compute them consistently.

## Model Comparison

For cheap vs strong model comparisons:

- use the same source lines
- use the same prompt and context renderer when possible
- store both run IDs
- compare at comment and claim levels
- flag disagreements for audit

Do not compare two models on different samples and call it a bakeoff.

## A3 Score Outputs

Recommended files:

```text
scores/
  comment_scorecard.csv
  claim_scorecard.csv
  disagreement_rows.csv
  metric_summary.json
  metric_summary.md
```

`metric_summary.json` should be machine-readable. `metric_summary.md` should be
human-readable and used in run-review notes.

## Scoring Implementation Notes

The existing `patientpunk.evaluate` assumes wide CSV rows and multi-value
cells. A3's claim extraction is nested, so it needs custom scoring:

- comment-level scoring can use `source_line` as the join key
- claim-level scoring should use `claim_id` when auditing model claims
- gold-claim recall needs separate human gold claim rows, not just model-claim
  audit rows
- evidence support is a binary claim-level label
- parent-context leakage is both a claim-level error and a comment-level row
  failure

Start with audit scoring over model claims. Add full gold-claim recall after
the codebook stabilizes.

## Stop/Proceed Decision

Every A2 gate should end with one of:

```text
proceed
rerun_same_instrument
revise_a1_prompt
revise_a1_schema
revise_a2_runner
revise_a3_audit
stop
```

This decision belongs in the A3 score report and should be referenced by A2
before launching the next gate.

