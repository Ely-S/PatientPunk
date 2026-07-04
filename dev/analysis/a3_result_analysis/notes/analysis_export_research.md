# Analysis Export Research

Date: 2026-07-04

This note studies local export and normalization patterns and translates them
into A3 exports for A2 comment-coding outputs.

## Existing Local Lessons

`records_to_csv.py`:

- writes metadata columns first
- flattens multi-value fields for spreadsheet use
- can include provenance and confidence columns
- reports field coverage after export
- merges compatible record files while preserving a single row key

`evaluate.py`:

- scores candidate output against reference rows
- separates metadata columns from data columns
- reports precision, recall, F1, agreement, and fill rates
- can export blank gold-labeling templates

`normalize.py`:

- keeps raw values while adding controlled-vocabulary derivatives
- decomposes structured treatment-outcome triples into analysis-friendly columns
- treats normalization as a versioned post-processing step

`cluster_prep.py`:

- aggregates record rows to patient rows
- drops fields below coverage thresholds
- controls cardinality with top-k and "other" buckets
- reports readiness metrics before clustering

`dev/eval/run_eval.py` and `wilson.py`:

- use a grounded bank of hand-read cases
- pool counts across repetitions instead of averaging rates
- report Wilson confidence intervals
- explicitly tests known failure modes such as over-attribution

## A3 Export Philosophy

A3 exports should be derived from the A2 SQLite run DB. They should not be the
primary store.

A3 should export narrow, analysis-friendly tables rather than one enormous
nested JSON file.

Recommended exported files:

```text
exports/
  run_manifest.json
  run_report.json
  comment_rows.csv
  claim_rows.csv
  claim_rows_normalized.csv
  failed_items.csv
  attempts.csv
  audit_comment_template.csv
  audit_claim_template.csv
  audit_sample_ids.jsonl
  codebook.md
  export_manifest.json
```

## comment_rows.csv

One row per target comment.

Purpose:

- skip/codeable analysis
- output-distribution analysis
- prompt-size and cost analysis
- temporal and context stratification

Columns:

```text
run_id
source_line
comment_id
post_id
link_id
date_utc
year_month
parent_kind
body_length
status
is_codeable
skip_reason
claim_count
used_context
context_available_count
context_comment_ids_used
missing_context_keys
attribution_confidence
attempt_count
prompt_tokens
completion_tokens
total_tokens
cost_usd
latency_ms
model
result_hash
prompt_message_hash
context_hash
```

Do not include the raw target body by default. Add an explicit
`--include-text` export option only for ignored local paths.

## claim_rows.csv

One row per extracted claim.

Purpose:

- claim type distributions
- normalized-label frequency
- evidence audit
- context-leakage review
- time-series analysis

Columns:

```text
run_id
claim_id
claim_hash
source_line
comment_id
claim_index
claim_type
raw_text
normalized_label
experiencer
assertion
confidence
evidence_quote
evidence_source
used_context
context_comment_ids_used
attribution_confidence
date_utc
year_month
parent_kind
body_length
model
schema_version
prompt_version
```

`evidence_quote` is raw Reddit text. This export should live only under ignored
dataset paths.

## claim_rows_normalized.csv

Derived from `claim_rows.csv` by A3 normalization.

Additional columns:

```text
normalized_label_canonical
normalization_version
normalization_rule
analysis_bucket
```

Do not replace `normalized_label`; keep both raw model label and derived
canonical label.

## attempts.csv

One row per attempt.

Purpose:

- provider stability
- retry analysis
- cost analysis
- prompt-size failure analysis

Columns:

```text
run_id
source_line
comment_id
attempt_number
status
model
resolved_upstream
latency_ms
prompt_tokens
completion_tokens
total_tokens
cost_usd
error_type
input_hash
context_hash
prompt_message_hash
result_hash
```

## failed_items.csv

One row per final failed work item.

Purpose:

- inspect unresolved failures
- decide whether failures are prompt, model, provider, data, or code issues

Columns:

```text
run_id
source_line
comment_id
date_utc
parent_kind
body_length
attempt_count
last_error_type
last_error
selection_bucket
prompt_message_hash
context_hash
```

## Audit Templates

A3 needs two labeling templates.

### audit_comment_template.csv

One row per audited comment:

```text
run_id
source_line
comment_id
audit_reason
target_excerpt
rendered_context_excerpt
model_is_codeable
model_skip_reason
model_claim_count
model_used_context
review_correct
review_wrong_skip
review_missed_claim
review_over_extracted_claim
review_parent_context_leakage
review_wrong_experiencer
review_wrong_negation
review_unsupported_evidence
review_context_needed_but_not_used
review_context_used_but_not_needed
review_confidence_too_high
review_notes
```

### audit_claim_template.csv

One row per audited claim:

```text
run_id
claim_id
source_line
comment_id
audit_reason
claim_type
raw_text
normalized_label
experiencer
assertion
confidence
evidence_quote
review_claim_correct
review_unsupported_evidence
review_wrong_claim_type
review_wrong_normalized_label
review_wrong_experiencer
review_wrong_assertion
review_parent_context_leakage
review_duplicate_claim
review_too_broad
review_too_narrow
review_notes
```

These templates intentionally expose raw text snippets. They belong only under
ignored data/output paths.

## Codebook

A3 should generate a lightweight codebook for exported columns:

```text
field name
table
description
type
allowed values
source
nullable
derived/raw
```

This mirrors the existing PatientPunk exporter/codebook habit. It matters
because A3 will produce multiple tables with similar columns, and analysis
notebooks need a stable reference.

## Export Manifest

Every export should write:

```text
export_manifest.json
```

Fields:

```text
run_id
exported_at_utc
source_run_db
instrument_hash
schema_version
prompt_version
normalization_version
include_text
tables
row_counts
file_hashes
```

File hashes let A3 notebooks know whether a CSV changed since a figure was made.

## Notebook And Script Boundary

A3 can have notebooks later, but export generation should be scriptable and
reproducible.

Notebooks should consume exported CSV/JSON or the run DB. They should not be the
only place where claim rows, audit templates, or normalized labels are created.

## A3 First Implementation Slice

After A2 has a run DB, A3 should implement:

1. `export_analysis_tables.py --run <run.sqlite>`
2. `make_audit_templates.py --run <run.sqlite>`
3. `summarize_distributions.py --run <run.sqlite>`
4. `normalize_claim_labels.py --claim-rows claim_rows.csv`
5. `score_audit.py --audit-comments ... --audit-claims ...`

The first slice should work on the A2 tiny run before any large run.

