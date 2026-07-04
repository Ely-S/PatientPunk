# A2 Runner And Storage Design

Date: 2026-07-04

This note designs the first A2 batch runner around the actual A1 interfaces.
It is a design note, not an implementation.

## Design Goal

A2 should make a coding run:

- resumable
- auditable
- reproducible
- cost-measured
- failure-aware
- safe to scale in gates

The A1 JSONL runner is useful as a smoke-test harness, but A2 should use a
SQLite run ledger. JSONL files are fine as exports, not as the primary state
store.

A3 downstream-analysis research adds one non-negotiable requirement: A2 must
store claim-level rows as first-class data. The nested `result_json` remains
the source of truth, but A3 needs a queryable `claim_rows` table and matching
exports for audit, scoring, normalization, and time-series analysis.

## Recommended Folder Shape

```text
dev/analysis/a2_batch_extraction/
  README.md
  notes/
  scripts/
    README.md
    create_run.py
    run_batch.py
    inspect_run.py
    summarize_run.py
    export_run.py
    select_audit_sample.py
  tests/
    test_run_db.py
    test_resume.py
    test_hashes.py
```

Generated outputs should stay under the ignored dataset-derived path:

```text
dataset/covidlonghaulers_comments/derived/a2_batch_extraction/runs/
  comment_coding/
    <run_id>/
      run.sqlite
      manifest.json
      exports/
      audit/
```

The run database should be the source of truth. `manifest.json` is a readable
sidecar.

## Run ID

Use a timestamped, human-readable run id:

```text
20260704T120000Z_comment_coding_prompt-dev_tiny
```

For code, do not parse meaning back out of the run id. Store all run semantics
in `run_manifest`.

## SQLite Tables

### run_manifest

One row per run, stored as key/value or a single JSON blob.

Minimum fields:

```text
run_id
created_at_utc
updated_at_utc
finished_at_utc
status
mode                    # dry_render | live | audit | export
dataset_root
context_db
dataset_manifest_sha256
source_export_sha256
task_name
schema_name
schema_version
schema_hash
prompt_name
prompt_version
prompt_hash
context_renderer_version
context_config_json
instrument_hash
agent_name
agent_version
model
model_config_json
max_attempts
workers
where_sql
where_params_json
order_sql
limit
git_commit
git_dirty
python_version
rumi_import_path
openrouter_base_url
```

Do not store API keys or secrets.

### work_items

One row per target comment in the run.

```text
source_line INTEGER PRIMARY KEY
comment_id TEXT NOT NULL
date_utc TEXT
created_utc INTEGER
year_month TEXT
post_id TEXT
link_id TEXT
parent_kind TEXT
parent_comment_id TEXT
body_length INTEGER
is_removed_or_deleted INTEGER
selection_bucket TEXT
status TEXT NOT NULL
attempt_count INTEGER NOT NULL DEFAULT 0
claimed_by TEXT
claimed_at_utc TEXT
last_attempt_at_utc TEXT
finished_at_utc TEXT
last_error_type TEXT
last_error TEXT
deterministic_skip_reason TEXT
input_hash TEXT
context_hash TEXT
prompt_message_hash TEXT
rendered_context_chars INTEGER
prompt_message_chars INTEGER
context_available_count INTEGER
missing_context_json TEXT
result_hash TEXT
result_id INTEGER
```

Statuses:

```text
pending
running
succeeded
deterministic_skipped
failed
abandoned
```

`deterministic_skipped` should only be used for local rules A1 has approved,
such as exact `[removed]` or `[deleted]`.

### attempts

One row per model attempt or deterministic attempt.

```text
attempt_id INTEGER PRIMARY KEY AUTOINCREMENT
run_id TEXT
source_line INTEGER
comment_id TEXT
attempt_number INTEGER
started_at_utc TEXT
finished_at_utc TEXT
status TEXT
model TEXT
agent_id TEXT
latency_ms INTEGER
error_type TEXT
error TEXT
traceback_summary TEXT
raw_metadata_json TEXT
prompt_tokens INTEGER
completion_tokens INTEGER
total_tokens INTEGER
cost_usd REAL
resolved_upstream TEXT
input_hash TEXT
context_hash TEXT
prompt_message_hash TEXT
result_hash TEXT
```

Failed attempts are important. They show model brittleness, prompt-size
problems, and provider instability.

### results

One row per final successful or deterministic result.

```text
result_id INTEGER PRIMARY KEY AUTOINCREMENT
run_id TEXT
source_line INTEGER UNIQUE
comment_id TEXT UNIQUE
schema_version TEXT
prompt_version TEXT
model TEXT
resolved_upstream TEXT
result_json TEXT NOT NULL
result_hash TEXT NOT NULL
is_codeable INTEGER
skip_reason TEXT
claim_count INTEGER
used_context INTEGER
context_comment_ids_used_json TEXT
attribution_confidence TEXT
ambiguity_notes TEXT
attempt_count INTEGER
prompt_tokens INTEGER
completion_tokens INTEGER
total_tokens INTEGER
cost_usd REAL
latency_ms INTEGER
created_at_utc TEXT
attempt_id INTEGER
```

Store full `result_json` even if claim rows are also normalized.

### claim_rows

Mandatory. A3's analysis, audit, normalization, and export workflows operate at
claim level. This table is derived from `results.result_json`, but A2 should
write it during the run and provide a rebuild command.

```text
claim_id INTEGER PRIMARY KEY AUTOINCREMENT
result_id INTEGER
run_id TEXT
source_line INTEGER
comment_id TEXT
claim_stable_id TEXT
claim_hash TEXT
claim_index INTEGER
claim_type TEXT
raw_text TEXT
normalized_label TEXT
normalized_label_canonical TEXT
normalization_version TEXT
experiencer TEXT
assertion TEXT
confidence TEXT
evidence_quote TEXT
evidence_source TEXT
evidence_json TEXT
used_context INTEGER
context_comment_ids_used_json TEXT
attribution_confidence TEXT
date_utc TEXT
year_month TEXT
parent_kind TEXT
body_length INTEGER
model TEXT
schema_version TEXT
prompt_version TEXT
```

`normalized_label_canonical` and `normalization_version` are A3-derived columns.
They should be nullable in A2 and filled later. A2 must not overwrite the raw
model `normalized_label`.

`claim_stable_id` should be deterministic:

```text
<run_id>:<source_line>:<claim_index>
```

### rendered_inputs

Optional. Rendered inputs contain raw Reddit text, so they should be treated as
data, not code.

Recommended fields:

```text
source_line INTEGER PRIMARY KEY
comment_id TEXT
context_hash TEXT
prompt_message_hash TEXT
render_config_json TEXT
context_comment_ids_available_json TEXT
rendered_context TEXT
prompt_message TEXT
created_at_utc TEXT
```

Default policy:

- store hashes always
- store raw rendered text for dry runs, tiny pilots, and audit rows
- allow `--store-rendered all` only under ignored dataset paths
- never store rendered text in tracked `dev/analysis`

### audit_comment_labels

One row per comment-level audit item.

```text
audit_id INTEGER PRIMARY KEY AUTOINCREMENT
run_id TEXT
source_line INTEGER
comment_id TEXT
reason TEXT
selected_at_utc TEXT
review_status TEXT
reviewer TEXT
correct INTEGER
wrong_skip INTEGER
missed_claim INTEGER
over_extracted_claim INTEGER
parent_context_leakage INTEGER
wrong_experiencer INTEGER
wrong_negation INTEGER
unsupported_evidence INTEGER
context_needed_but_not_used INTEGER
context_used_but_not_needed INTEGER
confidence_too_high INTEGER
ambiguous_not_marked INTEGER
notes TEXT
```

### audit_claim_labels

One row per claim-level audit item.

```text
audit_claim_id INTEGER PRIMARY KEY AUTOINCREMENT
run_id TEXT
claim_stable_id TEXT
source_line INTEGER
comment_id TEXT
claim_index INTEGER
reason TEXT
selected_at_utc TEXT
review_status TEXT
reviewer TEXT
claim_correct INTEGER
unsupported_evidence INTEGER
wrong_claim_type INTEGER
wrong_normalized_label INTEGER
wrong_experiencer INTEGER
wrong_assertion INTEGER
parent_context_leakage INTEGER
duplicate_claim INTEGER
too_broad INTEGER
too_narrow INTEGER
notes TEXT
```

Structured audit columns are deliberate. A3 can still store extra JSON later,
but boolean columns make gate metrics straightforward.

## Runner Flow

### Create Run

`create_run.py` should:

1. Load A1 manifest.
2. Compute schema, prompt, context, model, and instrument hashes.
3. Resolve the source comment set from `comments.sqlite`.
4. Write `manifest.json`.
5. Create `run.sqlite`.
6. Insert `work_items`.

The create step should not call the model.

### Dry Render

`run_batch.py --dry-render` should:

1. Claim pending rows.
2. Fetch context with `CommentStore`.
3. Render context with `render_context_for_prompt`.
4. Build final message with `build_message`.
5. Compute hashes.
6. Store hashes and optionally raw rendered text.
7. Mark item succeeded for dry-render mode, or leave live mode pending.

Dry render should be the first gate for every non-trivial run.

### Live Run

For each work item:

1. Transactionally claim one pending or stale-running item.
2. Fetch comment/context.
3. Render prompt and compute hashes.
4. If deterministic skip applies, write a schema-valid local result and mark
   `deterministic_skipped`.
5. Otherwise call `code_comment_with_metadata`.
6. Validate returned `comment_id`, `source_line`, `schema_version`, and
   `prompt_version`.
7. Write an `attempts` row.
8. Write `results` and mandatory `claim_rows` if successful.
9. Mark `work_items.status`.

Use one Rumi world per run process and one fresh agent id per attempt:

```text
<run_id>-<source_line>-a<attempt_number>
```

## Resume Semantics

A2 should support `--resume` by default.

Resume should:

- not re-run succeeded rows
- not re-run deterministic skips unless explicitly requested
- reclaim `running` rows older than a stale timeout
- continue failed rows only if `attempt_count < max_attempts`
- refuse to resume when `instrument_hash` differs unless `--new-run` or
  `--force-hash-mismatch` is used

If prompt, schema, model config, context config, or source dataset changes, the
honest default is a new run.

## Hashes

Minimum hash functions:

```text
schema_hash = sha256(CommentCodingResult.model_json_schema JSON)
prompt_hash = sha256(prompt file + build_message template marker + schema_hash)
context_hash = sha256(rendered_context)
prompt_message_hash = sha256(final user message)
instrument_hash = sha256(manifest subset that defines semantics)
result_hash = sha256(result.model_dump_json sorted/canonical)
```

The A1 runner already computes rendered context and prompt message hashes. A2
should make those mandatory.

## Concurrency

Start simple:

```text
workers=1 for tiny runs
workers=2-4 for pilot
workers=8 only after rate-limit and retry behavior is known
```

SQLite can support this if:

- WAL mode is enabled
- each worker uses its own SQLite connection
- claims are done in short transactions
- model calls happen outside write transactions

Do not share a single SQLite connection across threads.

## Rate Limits And Backoff

The old extraction code used shared retry delays:

```text
2s, 5s, 15s, 30s
```

A2 should implement provider-transient retries separately from structured-output
retries:

- provider 429, 5xx, connection error, timeout: backoff and retry
- empty structured body: retry fresh agent id
- validation error: retry once fresh agent id, then fail
- length finish: fail or rerun with smaller context/max chars if A1 permits it

A2 should record the class of retry in `attempts.error_type`.

## Query And Export

Primary development queries should read from SQLite.

Exports should be derived:

```text
exports/run_manifest.json
exports/run_report.json
exports/comment_rows.csv
exports/claim_rows.csv
exports/claim_rows_normalized.csv
exports/failed_items.csv
exports/attempts.csv
exports/results.jsonl
exports/audit_sample_ids.jsonl
exports/audit_comment_template.csv
exports/audit_claim_template.csv
exports/codebook.md
exports/export_manifest.json
```

`results.jsonl` should contain one row per successful target comment with the
full structured result.

`comment_rows.csv` and `claim_rows.csv` are the main A3 analysis tables.
`results.result_json` remains the source of truth for exact model output.

`export_manifest.json` should include run id, instrument hash, export time,
normalization version, row counts, and file hashes. A3 notebooks should be able
to tell when an export changed.

## A3 Compatibility Checks

Before A2 marks a run ready for downstream analysis, it should verify:

- every successful codeable result has matching `claim_rows`
- every `claim_rows.claim_stable_id` is unique
- every evidence source is `target_comment`
- comment and claim exports can be generated without reparsing raw Rumi history
- audit templates can be generated from the run DB
- run, comment, claim, attempt, and export row counts reconcile
- prompt/context/result hashes are present

A2 scale gates should fail if these checks fail. A run that cannot be audited or
exported is not complete for A3.

## Why Not Multi-Comment Batches Yet

The older extraction scripts had to add split-retry because multi-item LLM
calls produced malformed JSON or the wrong number of outputs. Comment-level
attribution is even more sensitive because claims from one target could bleed
into another.

A2 v0 should run one target comment per model call. Micro-batches are a later
optimization only after:

- exact output count validation exists
- exact source ID validation exists
- split-retry exists
- attribution leakage is measured against single-call mode

## First Implementation Slice

Recommended first A2 implementation:

1. `create_run.py` creates a SQLite run DB from a sample file or SQL filter.
2. `run_batch.py --dry-render --limit 10` renders and hashes inputs.
3. `inspect_run.py` prints pending/succeeded/failed counts.
4. `run_batch.py --live --limit 5 --workers 1` runs a tiny live batch.
5. `summarize_run.py` writes `run_report.json`.
6. `export_run.py` writes comment-level and claim-level CSV/JSONL exports.
7. `select_audit_sample.py` writes comment and claim audit templates.

Do not implement full-corpus scheduling first. The ledger and resume semantics
are the hard part that make scaling safe.
