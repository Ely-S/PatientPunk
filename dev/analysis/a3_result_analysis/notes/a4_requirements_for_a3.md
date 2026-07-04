# A4 Requirements For A3

Date: 2026-07-04

This note records what A4 evidence reporting needs from A3. It refines the A3
research notes after looking one layer downstream.

## A4's Dependency On A3

A4 should not build reportable findings from raw A2 outputs. A4 needs A3 to
validate, normalize, score, and package analysis artifacts first.

Therefore A3 must produce:

```text
analysis_manifest.json
run_quality_report.json
comment_distribution.csv
claim_distribution.csv
claim_label_frequency.csv
claim_rows_normalized.csv
normalization_manifest.json
codebook.md
codebook.csv
denominator_summary.csv
quote_candidates.csv
reportability_summary.csv
```

When audit labels exist, A3 must also produce:

```text
scores/comment_scorecard.csv
scores/claim_scorecard.csv
scores/metric_summary.json
scores/metric_summary.md
scores/disagreement_rows.csv
scores/gate_decision.json
```

## Analysis Manifest

A3 should treat `analysis_manifest.json` as a required output, not an
implementation detail.

Required fields:

```text
analysis_id
analysis_version
generated_at_utc
source_a2_run_ids
source_a2_export_manifests
source_a2_instrument_hashes
source_file_hashes
analysis_file_hashes
normalization_version
normalization_map_sha256
audit_score_version
codebook_sha256
row_counts
warnings
errors
```

A4 should be able to verify that every file used in a report came from a known
A2/A3 artifact.

## Denominator Summary

A3 should write `denominator_summary.csv` with one row per relevant denominator.

Suggested columns:

```text
name
value
source_table
source_filter
description
```

Required denominator names:

```text
n_work_items_selected
n_comments_attempted
n_comments_succeeded
n_comments_codeable
n_comments_skipped
n_comments_failed
n_claims_extracted
n_claims_after_normalization
n_comments_audited
n_claims_audited
```

A4 should never have to guess whether a percentage is over comments, claims,
audited comments, or audited claims.

## Quote Candidates

A3 should generate `quote_candidates.csv` for A4, even before public reporting
exists.

Suggested columns:

```text
quote_id
run_id
claim_id
source_line
comment_id
evidence_quote
claim_type
normalized_label_canonical
analysis_bucket
assertion
experiencer
confidence
attribution_confidence
audit_status
contains_sensitive_terms
redaction_status
selection_reason
```

The first implementation can use:

```text
redaction_status = not_reviewed
contains_sensitive_terms = unknown
```

A4 should keep those quotes out of public-facing reports until quote review is
implemented.

## Reportability Summary

A3 should create `reportability_summary.csv` so A4 can tell which outputs are
ready for which use.

Suggested columns:

```text
unit
key
reportability_label
reason
source_metric
source_metric_rate
source_metric_wilson_high
normalization_review_status
audit_status
gate_decision
```

Allowed reportability labels:

```text
not_reportable
exploratory
weak_signal
suggestive_signal
stable_descriptive_pattern
```

A3 should assign conservative defaults:

- no audit labels: `exploratory` at most
- failed validation: `not_reportable`
- unreviewed normalization for high-frequency labels: `exploratory` at most
- gate decision other than `proceed`: cap at `exploratory` or `weak_signal`

## Normalized Claims For A4

A3's `claim_rows_normalized.csv` should include raw and derived values side by
side:

```text
normalized_label
normalized_label_clean
normalized_label_canonical
analysis_bucket
normalization_version
normalization_rule
normalization_review_status
```

If canonical labels are missing, A4 can still show raw exploratory frequency
tables, but it should not create stable finding cards from those rows.

## Gate Decision

A3's gate decision must be machine-readable.

Allowed values:

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

A4 should use this as a hard reportability constraint.

## A3 First Slice Refinement

The A3 first implementation should now be:

1. validate A2 run and file hashes
2. write `analysis_manifest.json`
3. write run/comment/claim summaries
4. write `denominator_summary.csv`
5. normalize claim labels and write `normalization_manifest.json`
6. write `quote_candidates.csv`
7. write codebook
8. score audit labels when present
9. write `gate_decision.json`
10. write `reportability_summary.csv`

## Research Takeaway

A3 must package analysis for A4, not only for local inspection. The difference
is explicit denominators, quote candidates, reportability labels, and
machine-readable gate decisions.

