# Audit Scoring Implementation Research

Date: 2026-07-04

This note converts the A3 audit/scoring plan into implementation details.

## Scoring Philosophy

A3 should score what was actually reviewed, and it should be explicit about
the denominator for every rate.

Small audits are useful for finding failures, not proving safety. A3 should
report Wilson intervals and rule-of-three bounds for every important rate.

## Audit Inputs

A2 currently emits:

```text
exports/audit_comment_template.csv
exports/audit_claim_template.csv
```

For scoring, reviewers should fill these into reviewed copies, for example:

```text
reviewed/audit_comment_labels.csv
reviewed/audit_claim_labels.csv
```

A3 should keep reviewed labels separate from generated templates so templates
can be regenerated without overwriting human work.

## Comment-Level Audit Columns

Current A2 template columns:

```text
correct
wrong_skip
missed_claim
over_extracted_claim
parent_context_leakage
wrong_experiencer
wrong_negation
unsupported_evidence
context_needed_but_not_used
context_used_but_not_needed
confidence_too_high
ambiguous_not_marked
notes
reviewer
```

A3 should accept blank as unknown/not reviewed, not as false.

Valid binary values:

```text
1
0
true
false
yes
no
y
n
```

Anything else should be a validation warning.

## Claim-Level Audit Columns

Current A2 template columns:

```text
correct
wrong_claim_type
wrong_label
wrong_experiencer
wrong_assertion
unsupported_evidence
duplicate_claim
should_be_split
should_be_merged
confidence_too_high
notes
reviewer
```

Claim-level audit primarily measures precision and attribute accuracy over
model-extracted claims. It does not fully measure recall until A3 also has
human gold claim rows for missed claims.

## Derived Metrics

Comment metrics:

```text
reviewed_comment_count
comment_correct_rate
wrong_skip_rate
missed_claim_rate
over_extracted_claim_rate
context_leakage_rate
unsupported_evidence_comment_rate
context_use_error_rate
high_confidence_error_rate
```

Claim metrics:

```text
reviewed_claim_count
claim_correct_rate
claim_precision_proxy
claim_type_accuracy
label_accuracy
experiencer_accuracy
assertion_accuracy
evidence_support_rate
duplicate_claim_rate
split_merge_issue_rate
```

For error-rate metrics, A3 should report both:

```text
failure_rate = failures / reviewed
success_rate = 1 - failure_rate
```

The success rate is easier for proceed gates; the failure rate is easier for
prompt debugging.

## Wilson Output Shape

Every metric row should include:

```text
metric
level
k
n
rate
wilson_low
wilson_high
rule_of_three_upper_if_zero_failures
denominator_description
```

For example:

```text
metric: unsupported_evidence_rate
level: claim
k: unsupported_evidence_count
n: reviewed_claim_count
```

Use `dev/eval/wilson.py` as the implementation reference.

## Disagreement Rows

A3 should write `scores/disagreement_rows.csv` with one row per failed audit
label.

Suggested columns:

```text
level
run_id
source_line
comment_id
claim_id
error_type
claim_type
raw_text
normalized_label
assertion
experiencer
evidence_quote
reviewer
notes
```

This file is what A1 should use for prompt/schema revision.

## Gate Decision

A3 should produce a machine-readable gate decision:

```text
proceed
proceed_to_more_audit
rerun_same_instrument
revise_a1_prompt
revise_a1_schema
revise_a2_runner
revise_a3_audit
stop
```

The decision should be based on explicit thresholds in a config file, not
hard-coded in notebooks.

Initial default thresholds can follow `audit_scoring_plan.md`, but A3 should
make them configurable:

```text
structured_success_rate >= 0.99
final_failure_rate <= 0.01
parent_context_leakage_rate <= 0.02
unsupported_evidence_rate <= 0.02
wrong_experiencer_rate <= 0.03
wrong_assertion_rate <= 0.05
high_confidence_error_rate <= 0.02
```

For tiny gates, A3 should mark the decision as:

```text
proceed_to_more_audit
```

rather than claiming a production-scale pass.

## Audit Sampling

A3 should not rely on pure random samples.

Required strata:

```text
failed_rows
retry_success_rows
deterministic_skips
removed_deleted
short_comments
long_comments
top_level_missing_root_post
reply_parent_available
reply_parent_missing
context_used
context_reference_bucket
low_attribution_confidence
high_claim_count
question_only
other_person
high_confidence_claims
```

A2 already stores enough metadata for many of these strata. A3 may need
additional derived heuristics for `question_only` and `other_person`.

## Review Workflow

Recommended human workflow:

1. A3 validates A2 run and creates stratified audit templates.
2. Reviewer fills binary labels and notes.
3. A3 validates reviewed templates.
4. A3 scores comment and claim labels.
5. A3 writes disagreement rows.
6. A1 uses disagreement clusters to revise prompt/schema.
7. A2 reruns the same IDs with the revised instrument.

This loop should happen on small samples before any large A2 run.

## Strong-Model Comparison

Strong-model output can be useful as a silver comparator, but A3 should not call
it gold.

Comparison requirements:

- same `source_line` IDs
- same context renderer where possible
- separate A2 run IDs
- no mixing candidate and reference rows in the same export
- disagreement rows sampled for human adjudication

Strong-model agreement should be a triage signal, not the final gate.

## First Implementation Acceptance Criteria

The first A3 scoring implementation is acceptable when it can:

- load reviewed comment and claim CSVs
- validate binary label columns
- compute all metrics with Wilson intervals
- write JSON, Markdown, and CSV score outputs
- write disagreement rows
- produce a gate decision
- produce A4-facing reportability labels or enough metrics for
  `reportability_summary.csv`
- run on the tiny A2 live eval outputs

## Research Takeaway

A3 scoring should be conservative and denominator-explicit. Its purpose is not
to bless a model after a tiny smoke test; it is to make the prompt-engineering
loop measurable and to prevent scale-up before known error modes are reviewed.
