# A2 Smoke Output Review For A3

Date: 2026-07-04

This note reviews the implemented A2 tiny live run from an A3 perspective.

## Run Reviewed

```text
dataset/covidlonghaulers_comments/derived/a2_batch_extraction/runs/comment_coding/20260704T055236Z_prompt_dev_3
```

Run report:

```text
attempt_count: 3
result_count: 3
claim_count: 20
structured_success_rate: 1.0
failed_attempt_count: 0
evidence_source_violations: 0
total_tokens: 10138
cost_usd: 0.000963862
median_latency_seconds: 24.894211200000427
```

Export manifest row counts:

```text
comment_rows.csv: 3
claim_rows.csv: 20
attempts.csv: 3
failed_items.csv: 0
results.jsonl: 3
audit_comment_template.csv: 3
audit_claim_template.csv: 20
```

## What A2 Already Provides Well

A2 now provides the pieces A3 needed most:

- a SQLite run ledger as source of truth
- `work_items`, `attempts`, `results`, and `claim_rows`
- deterministic `claim_id` and `claim_hash`
- exported comment-level and claim-level CSVs
- exported results JSONL
- audit templates
- export manifest with file hashes and row counts
- prompt/context/result hashes
- token, cost, and latency metadata

This is enough for A3 to start deterministic validation and summaries.

## Export Shape Observed

`comment_rows.csv` columns:

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

`claim_rows.csv` columns include:

```text
claim_id
claim_stable_id
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
evidence_json
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

`attempts.csv` columns include:

```text
work_item_id
attempt_number
model
agent_id
started_at_utc
finished_at_utc
latency_seconds
status
error_type
error_message
context_hash
prompt_message_hash
prompt_tokens
completion_tokens
total_tokens
cost_usd
metadata_json
```

## A3 Pushbacks For A2

These are not blockers for A3 first-slice work, but they should be pushed back
before larger A2 runs.

1. `attempts.csv` should flatten join keys.

   A3 can join attempts to work items through `work_item_id`, but an exported
   CSV should include `run_id`, `source_line`, and `comment_id` directly. This
   makes provider/retry analysis easier outside SQLite.

2. `attempts.csv` should flatten provider metadata.

   `resolved_upstream` is currently inside `metadata_json`. A3 can parse it,
   but A2 should export it as a first-class column because upstream-specific
   failures and latency are core scale-up questions.

3. `comment_rows.csv` should include more direct operational fields.

   Useful additions:

   ```text
   prompt_tokens
   completion_tokens
   latency_seconds
   prompt_message_chars
   deterministic
   sample
   selection_bucket
   context_comment_ids_available_json
   ```

4. Audit templates need audit ergonomics.

   The current templates are structurally useful, but manual reviewers will
   need either excerpts or a parallel review sheet that includes:

   ```text
   audit_reason
   target_excerpt
   rendered_context_excerpt
   model_used_context
   model_ambiguity_notes
   ```

   These can live only under ignored derived paths because they contain Reddit
   text.

5. A2 should generate `codebook.md`.

   A3 can do this, but A2 exports would be easier to hand to reviewers if every
   run had a small codebook explaining column meanings and label semantics.

## Quality Findings From The Tiny Run

The tiny eval is too small for quality claims, but it already shows what A3
needs to measure.

### Source Line 82: Context Adoption Risk

The target comment is short and context-dependent:

```text
I will give both a try!
```

In the A2 live run, the model extracted three `timeline_or_course` claims for
trying magnesium threonate, CoQ10, and omega oil, with `used_context=true`.

This is exactly the boundary A3 must audit:

- Did the target author explicitly adopt the parent comment's suggestions?
- Is "will give both a try" enough evidence for a treatment/timeline claim?
- Why did "both" become three items?
- Should this be `unclear_or_insufficient` instead?

This row should be a mandatory audit seed for context leakage, over-extraction,
and wrong count/split decisions.

### Source Line 18276: High Claim Count Risk

One long top-level comment produced 15 claims.

A3 should inspect high-claim rows for:

- over-splitting
- duplicate claims
- overly broad evidence quotes
- missed negation or uncertainty
- label fragmentation

High claim count should be an audit stratum.

### Source Line 33285: Trigger/Exacerbating Factor Shape

The model extracted two tachycardia-trigger claims:

```text
tachycardia triggered by bending over
tachycardia triggered by prolonged standing
```

This looks plausibly useful, but A3 should decide whether trigger labels should
stay as free-text labels or be normalized into:

```text
symptom: tachycardia
trigger: bending_over
trigger: prolonged_standing
```

This is a normalization and schema question for later, not an A2 infrastructure
issue.

## A3 Validation Queries

The first A3 validator should check:

```sql
SELECT COUNT(*) FROM work_items;
SELECT COUNT(*) FROM results;
SELECT COUNT(*) FROM claim_rows;
SELECT COUNT(*) FROM claim_rows WHERE evidence_source != 'target_comment';
SELECT claim_id, COUNT(*) FROM claim_rows GROUP BY claim_id HAVING COUNT(*) > 1;
SELECT source_line FROM results WHERE is_codeable = 1 AND claim_count = 0;
```

For exported CSVs, A3 should compare those counts to `export_manifest.json`.

## Research Takeaway

A2 infrastructure is now good enough for A3 implementation research. The first
A3 code should focus on validation, summaries, audit seeding, and disagreement
review. Quality should not be inferred from the 3-row success rate; the most
important finding is that the first tiny run already contains an attribution and
context-adoption edge case.

