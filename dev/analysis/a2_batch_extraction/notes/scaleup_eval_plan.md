# A2 Scaleup And Evaluation Plan

Date: 2026-07-04

This note defines how A2 should move from dry runs to larger extraction runs
without confusing "the script ran" with "the measurement is valid."

## Principle

A2 should scale only when the previous gate produced enough evidence that the
instrument is stable, attributable, and affordable.

The key A2 risk is not just provider failure. The key scientific risk is
silently generating a large dataset with systematic attribution errors.

## Gate 0: A1 Readiness

A2 can only run dry renders or tiny smoke tests until A1 has:

- versioned schema
- versioned prompt
- versioned context renderer
- frozen prompt-dev IDs
- frozen holdout IDs
- manual review or audit rubric
- expected output distributions
- thresholds for structured failures and attribution leakage

Current status:

```text
schema: exists
prompt: exists
context renderer: exists
samples: exist
tiny live smoke test: exists
manual audit labels: not yet
holdout metrics: not yet
strong-model comparison: not yet
attribution leakage estimate: not yet
```

Therefore, A2 can research and implement infrastructure, but should not run a
large extraction yet.

A3 downstream-analysis research adds another readiness condition: A2 must be
able to export comment-level and claim-level analysis tables from the run DB
before a live run can be considered complete.

## Gate 1: Dry Render

Purpose:

- verify selection logic
- verify prompt/context hashes
- verify no prompt is too large
- inspect actual rendered text before spending money

Suggested command shape:

```powershell
python dev/analysis/a2_batch_extraction/scripts/create_run.py --sample prompt_dev
python dev/analysis/a2_batch_extraction/scripts/run_batch.py --dry-render --limit 25
```

Pass conditions:

- all selected comments resolve in `comments.sqlite`
- no prompt exceeds context limits
- all rows have `context_hash` and `prompt_message_hash`
- rendered raw text is written only under ignored dataset paths
- root-post missing context is represented, not treated as an error
- dry-run rows can be exported to `comment_rows.csv`

## Gate 2: Tiny Live

Purpose:

- verify OpenRouter/Rumi/schema path
- verify retry behavior
- verify SQLite ledger state transitions
- estimate latency and cost

Size:

```text
25-50 rows
workers=1
max_attempts=2
```

Include rows from risky buckets:

- removed/deleted
- short
- long
- context_reference
- missing_parent
- other_person
- question_only

Pass conditions:

```text
final structured success rate >= 0.95
unresolved failure count <= 2
prompt_too_large count == 0
all result comment_id/source_line match target
all evidence sources are target_comment
run DB resumes cleanly after an intentional stop
comment_rows.csv and claim_rows.csv exports reconcile with DB counts
audit_comment_template.csv and audit_claim_template.csv can be generated
```

The structured success threshold is intentionally loose for the first tiny run.
If the issue is infrastructure, fix A2. If the issue is prompt/schema/model
behavior, send it back to A1.

## Gate 3: Prompt-Dev Live

Purpose:

- run the frozen `prompt_dev` sample at enough size to inspect prompt failures
- compare cheap model against a stronger model on the same IDs
- measure retry rate and output distribution

Size:

```text
prompt_dev: 200 rows
workers=1-2
max_attempts=2
model: openai/gpt-oss-120b
comparator: anthropic/claude-sonnet-4 on a matched subset or all rows
```

Metrics:

```text
structured_success_rate
retry_rate
final_failure_rate
is_codeable_rate
skip_reason_distribution
claim_count_distribution
used_context_rate
context_comment_ids_used_rate
low_attribution_confidence_rate
claim_type_distribution
cost_per_comment
latency_p50
latency_p95
comment_export_row_count
claim_export_row_count
audit_template_row_count
```

Manual audit should label:

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
```

Pass conditions before holdout:

```text
final structured success rate >= 0.99
final failure rate <= 0.01
parent_context_leakage <= 0.02 on audited rows
unsupported_evidence <= 0.02 on audited rows
deleted_removed skip accuracy >= 0.99 on audited/deleted rows
prompt_too_large count == 0
claim_rows coverage == 100% for codeable successful rows
comment and claim audit templates generated
```

These thresholds are starting points. A1 can revise them after reviewing real
failures.

## Gate 4: Gold Holdout

Purpose:

- estimate performance after prompt engineering without tuning on the same rows

Size:

```text
gold_holdout: 150 rows
workers=1-2
same prompt/schema/model chosen after prompt-dev
```

Rules:

- no prompt edits based on holdout until after metrics are recorded
- write a holdout report
- if holdout fails a gate, return to A1 and mark the prompt version as not
  ready for A2 scale

Pass conditions:

Same as Gate 3, but weighted more heavily because it is held out.

The holdout report should include A3-compatible exports and a score-input
manifest so later model comparisons can reuse the same audited rows.

## Gate 5: Pilot

Purpose:

- test operational stability on a more representative slice
- estimate real cost per comment
- test concurrency and resume

Size:

```text
300-1000 rows
workers=2-4
```

Selection:

- stratified by year/month
- stratified by parent kind
- include reply and top-level comments
- include A1 risk buckets
- include random rows not selected by keyword buckets

Pass conditions:

```text
final structured success rate >= 0.99
retry rate <= 0.10
provider/rate-limit failures manageable at chosen workers
cost per comment has stable confidence interval
claim and skip distributions are plausible against prompt-dev
audit leakage remains under threshold
resume/restart tested in the middle of the run
analysis exports generated and row-count reconciled
audit sample generated with comment and claim templates
```

## Gate 6: Distribution Run

Purpose:

- discover distribution shifts before spending on very large runs

Size:

```text
5000-10000 rows
workers=4-8 only if Gate 5 supports it
```

Additional checks:

- output distribution by month/year
- output distribution by parent kind
- output distribution by body length decile
- output distribution by context availability
- failures by model upstream/provider when available
- cost and latency by prompt size
- claim distributions by year/month and parent kind
- low-confidence and context-used rows available in audit exports

Pass conditions:

- no large unreviewed distribution shifts
- no rising failure rate with prompt size
- no evidence of context leakage concentration in deep replies
- audit sample reviewed before further scale
- A3 distribution report generated from exports, not ad hoc DB queries only

## Gate 7: Large Run

Purpose:

- run enough of the corpus to make downstream analysis useful

Size:

```text
25000-100000 rows
```

Rules:

- run report required
- audit sample required
- failed rows exported
- cost report required
- no automatic full-corpus continuation

## Gate 8: Full Corpus

Full corpus should only run after:

- A1 prompt/schema is frozen for this task
- holdout passes
- pilot and distribution runs pass
- cost is approved
- audit workflow is ready
- export format is stable
- A3 scoring/export scripts have been tested on a smaller run
- restart/resume has been tested

With the current comment DB count of 1,950,192 valid comments, even a cheap run
is large enough that a small systematic error becomes a large bad dataset.

## Audit Sampling

Every live A2 run should automatically create an audit sample.

Include:

- random successful rows
- all failed rows up to a cap
- all retry-success rows up to a cap
- deterministic skips
- removed/deleted rows
- low attribution confidence rows
- rows where context was used
- rows where context was available but not used
- high claim count rows
- no-claim skipped rows
- short target comments
- long target comments
- missing parent rows
- other-person rows
- question-only rows

Suggested audit sample for pilot:

```text
50 random successful rows
25 risky successful rows
all failures up to 50
all retry-success rows up to 25
all deterministic skips up to 25
```

A3 requires two templates:

```text
audit_comment_template.csv
audit_claim_template.csv
```

Comment templates test skip/codeable/context decisions. Claim templates test
claim type, normalized label, assertion, experiencer, and evidence support.

## Cost Tracking

The A1 smoke test cost was:

```text
3 rows
10602 total tokens
$0.00169469
```

A2 should track:

```text
prompt_tokens
completion_tokens
total_tokens
cost_usd
resolved_upstream
latency_ms
prompt_message_chars
rendered_context_chars
target_body_chars
claim_count
```

Cost reports should show:

```text
mean cost/comment
p50 cost/comment
p95 cost/comment
cost by body length bucket
cost by claim count bucket
cost by retry count
estimated cost for 10k, 100k, and full corpus
```

Do not extrapolate full-corpus cost from a 3-row smoke test except as a warning.

## Model Strategy

Start with:

```text
cheap model: openai/gpt-oss-120b
strong comparator: anthropic/claude-sonnet-4
```

Recommended pattern:

1. cheap model on all prompt-dev rows
2. strong model on same prompt-dev rows or a high-risk subset
3. compare row-level disagreements
4. use strong model as adjudication aid for audit, not as automatic truth
5. for A2 pilot, use cheap model only if A1 audits support it

Fallback policy options:

- retry same model for transient failures
- rerun final failures with strong model and label them as fallback-model rows
- do not mix fallback-model rows into a primary result set without a model field

## Stop Conditions

A2 should stop a live run early when:

- final failure rate exceeds gate threshold after a minimum number of rows
- retry rate exceeds threshold
- prompt-too-large errors appear
- cost/comment exceeds budget
- OpenRouter starts routing to unstable upstreams with repeated empty responses
- result validation catches repeated ID mismatches
- audit rows show parent-context leakage above threshold

For early runners, `--stop-after-failures N` is more useful than trying to
finish a broken batch.

## What To Report After Each Gate

Each A2 run should produce a short report:

```text
run_id
gate
instrument hash
sample/selection definition
row counts by status
success/failure/retry rates
cost and token summary
latency summary
claim distribution
skip distribution
context-use distribution
audit sample path
analysis export paths
comment/claim row reconciliation
known issues
decision: stop, revise A1, rerun, or proceed to next gate
```

No A2 run should proceed to the next gate without this report.
