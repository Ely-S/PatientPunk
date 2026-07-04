# A3 To A4 Contract

Date: 2026-07-04

This note defines what A4 needs from A3 before A4 can create evidence marts or
human-facing reports.

## Required A3 Artifacts

A4 should require these A3 outputs:

```text
analysis_manifest.json
run_quality_report.json
run_quality_report.md
comment_distribution.csv
claim_distribution.csv
claim_label_frequency.csv
claim_rows_normalized.csv
normalization_map.csv
normalization_manifest.json
codebook.md
codebook.csv
```

When audit has happened:

```text
scores/comment_scorecard.csv
scores/claim_scorecard.csv
scores/metric_summary.json
scores/metric_summary.md
scores/disagreement_rows.csv
scores/gate_decision.json
```

A4 can generate internal exploratory reports without audit scorecards, but the
report must mark findings as `not_reportable` or `exploratory`.

## Required A3 Manifest Fields

`analysis_manifest.json` should include:

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

A4 should refuse to build a report package if source hashes are missing.

## Required Quality Fields

A4 needs a compact quality state for every source run:

```text
run_id
structured_success_rate
final_failure_rate
retry_rate
evidence_source_violation_count
comment_rows_count
claim_rows_count
audit_status
gate_decision
known_blockers_json
```

A4 also needs enough audit scoring detail to decide whether a finding can be
reported:

```text
metric
level
k
n
rate
wilson_low
wilson_high
rule_of_three_upper_if_zero_failures
threshold
pass_fail
```

## Required Normalized Claim Columns

A4's evidence marts should be built from `claim_rows_normalized.csv`, not raw
`claim_rows.csv`.

Required columns:

```text
run_id
source_line
comment_id
claim_id
claim_hash
claim_type
raw_text
normalized_label
normalized_label_clean
normalized_label_canonical
analysis_bucket
normalization_version
normalization_rule
normalization_review_status
experiencer
assertion
confidence
evidence_quote
evidence_source
used_context
attribution_confidence
date_utc
year_month
parent_kind
body_length
model
schema_version
prompt_version
```

If `normalized_label_canonical` is empty, A4 may still include the row in raw
frequency tables but should not use it in stable evidence cards.

## Required Denominators

A4 needs A3 to expose denominators explicitly:

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

Every A4 percentage should say which denominator it uses.

## Required Quote Inputs

A4 should not sample quotes directly from raw model output without A3 filters.

A3 should provide a quote candidate table:

```text
quote_id
run_id
claim_id
source_line
comment_id
evidence_quote
claim_type
canonical_label
analysis_bucket
assertion
experiencer
confidence
audit_status
contains_sensitive_terms
redaction_status
selection_reason
```

The first A3 version can mark `redaction_status=not_reviewed`. A4 should then
keep such quotes out of public-facing reports.

## Required Drilldown Keys

A4 reports must support drilldown from aggregate finding to source rows:

```text
finding_id -> claim_ids -> comment_ids/source_lines -> A2 result hashes
```

A3 should preserve:

- `claim_id`
- `claim_hash`
- `result_hash`
- `prompt_message_hash`
- `context_hash`
- source A2 run directory or manifest path

## Gate Contract

A4 should treat A3 gate decisions as report constraints:

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

Only `proceed` should allow a report to use confident language such as
`stable_descriptive_pattern`. `proceed_to_more_audit` should cap findings at
`exploratory` or `suggestive_signal`.

## Pushbacks To A3

A3 notes should be refined to require:

- `analysis_manifest.json` as a first-class output
- explicit denominator tables
- `quote_candidates.csv`
- `normalization_manifest.json`
- `gate_decision.json`
- row-level drilldown keys in every aggregate
- reportability labels separate from extraction confidence
- public/private output modes for quote-bearing artifacts

## Research Takeaway

A3 is not done when it writes distributions. A3 is done when A4 can build a
traceable report package without reinterpreting raw outputs, guessing
denominators, or reverse-engineering quality status.

