# Downstream Requirements For A2

Date: 2026-07-04

This note defines what A3 needs from A2 so batch extraction outputs can be
audited, scored, normalized, exported, and analyzed without re-running models.

## Local Sources Read

- `dev/analysis/a2_batch_extraction/notes/a1_to_a2_contract.md`
- `dev/analysis/a2_batch_extraction/notes/runner_storage_design.md`
- `dev/analysis/a2_batch_extraction/notes/scaleup_eval_plan.md`
- `dev/analysis/agents/CommentCoderAgent/schemas.py`
- `dev/analysis/a1_coding_research/scripts/summarize_eval.py`
- `variable_extraction/patientpunk/evaluate.py`
- `variable_extraction/patientpunk/scripts/records_to_csv.py`
- `variable_extraction/patientpunk/normalize.py`
- `variable_extraction/patientpunk/cluster_prep.py`
- `variable_extraction/main.py` validate/export/cluster-prep commands
- `dev/eval/run_eval.py`
- `dev/eval/wilson.py`

## A3's Role

A3 is not another model-calling stage. It is the consumer of A2 run outputs.

The clean separation is:

- A1: define and evaluate the coding instrument.
- A2: run the instrument safely over comments.
- A3: audit, score, export, normalize, aggregate, and analyze the results.

A3's main finding for A2: **claim-level rows must be first-class outputs, not
optional convenience views.**

The A1 schema returns a list of `target_author_claims`. Almost every useful
analysis asks about claims, not just comments:

- how many symptom claims were extracted?
- which claim types dominate by year?
- how often are claims negated vs present?
- which normalized labels are common?
- which claims relied on context?
- which claims were low confidence?
- which evidence quotes support a label?

If A2 only stores `result_json`, every A3 query must repeatedly parse nested
JSON. That is workable for a tiny run but wrong for large analysis.

## Required A2 Outputs

A3 needs four canonical output levels.

### Run Level

One row per A2 run:

```text
run_id
instrument_hash
schema_version
prompt_version
context_renderer_version
model
dataset snapshot
selection definition
status counts
token/cost/latency summaries
audit status
export paths
```

### Comment Level

One row per target comment:

```text
run_id
source_line
comment_id
post_id
link_id
date_utc
year_month
parent_kind
parent_comment_id
body_length
is_removed_or_deleted
status
is_codeable
skip_reason
claim_count
used_context
context_available_count
context_comment_ids_used_json
missing_context_json
attribution_confidence
ambiguity_notes
result_hash
prompt_message_hash
context_hash
model
attempt_count
total_tokens
cost_usd
```

### Claim Level

One row per extracted claim:

```text
run_id
source_line
comment_id
claim_index
claim_id
claim_hash
claim_type
raw_text
normalized_label
normalized_label_canonical
experiencer
assertion
confidence
evidence_quote
evidence_source
used_context
context_comment_ids_used_json
attribution_confidence
date_utc
year_month
parent_kind
body_length
model
schema_version
prompt_version
```

`claim_id` can be deterministic:

```text
<run_id>:<source_line>:<claim_index>
```

`claim_hash` should be stable across exports:

```text
sha256(source_line + claim_type + raw_text + normalized_label + assertion + evidence_quote)
```

### Audit Level

One row per audited comment and one row per audited claim.

Comment audit labels:

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
```

Claim audit labels:

```text
claim_correct
unsupported_evidence
wrong_claim_type
wrong_normalized_label
wrong_experiencer
wrong_assertion
parent_context_leakage
duplicate_claim
too_broad
too_narrow
```

If A2 has only a single `audit_items` table with free-form JSON labels, A3 can
work, but it will be harder to compute metrics. A2 should support structured
comment-level and claim-level audit tables.

## Required A2 Metadata For Analysis

A3 needs these fields preserved before model text is discarded:

- `created_utc`, `date_utc`, and `year_month`
- `post_id` and `link_id`
- `parent_kind` and `parent_comment_id`
- target `body_length`
- `is_removed_or_deleted`
- context counts and missing-context flags
- prompt/context hashes
- model/upstream metadata
- retry count
- token and cost metadata
- whether the row was model-coded or deterministically skipped

Without these, A3 cannot stratify quality or output distributions by time,
context availability, prompt size, model behavior, or comment shape.

## Normalization Requirements

The existing `normalize.py` and `cluster_prep.py` show why normalization cannot
be an afterthought. Free-text values fragment quickly.

For A2 comment coding, model `normalized_label` is useful but not enough. A3
needs a post-hoc normalization layer:

```text
raw normalized_label -> canonical label -> optional ontology/codebook category
```

A2 should not overwrite the model's `normalized_label`. It should store it as
emitted. A3 can add derived columns:

```text
normalized_label_canonical
normalization_version
normalization_rule
```

This allows later normalization revisions without corrupting the original model
output.

## Aggregation Requirements

A3 will probably need these aggregations:

- comment-level summaries
- claim-level summaries
- post/thread-level summaries by `link_id`
- monthly summaries by `year_month`
- parent-kind summaries
- body-length decile summaries
- context-used vs context-not-used summaries
- model/upstream summaries

The current comments dataset does not include root submissions, so top-level
comments have missing root-post context. A3 can still analyze top-level comments
if A2 stores `parent_kind`, `post_id`, and missing-context flags.

## Evaluation Requirements

Existing evaluation code uses field-level precision/recall/F1 and agreement
against a reference CSV. A3 should adapt the same principle to comment coding:

- comment skip accuracy
- claim detection precision/recall
- claim type accuracy
- normalized-label agreement
- assertion accuracy
- experiencer accuracy
- evidence support accuracy
- context leakage rate

Rates should be reported with Wilson intervals, following `dev/eval/wilson.py`.
A3 should avoid "0 failures means safe" language on small samples; use the
rule-of-three upper bound.

## A2 Changes Pushed Back By A3

A2 notes should be refined to require:

- `claim_rows` as mandatory
- `audit_comment_labels` and `audit_claim_labels` tables
- `comment_exports.csv` and `claim_exports.csv`
- `year_month`, `post_id`, prompt char counts, and context metadata on work
  items/results
- deterministic claim IDs and claim hashes
- run-level export manifest
- codebook/data-dictionary export for columns
- normalization columns as derived A3 outputs, never overwriting raw model rows

## A3 Rule Of Thumb

If a field is needed to stratify quality, reproduce a row, compare models, or
join a claim back to its source comment, A2 should store it before the model run
is considered complete.

