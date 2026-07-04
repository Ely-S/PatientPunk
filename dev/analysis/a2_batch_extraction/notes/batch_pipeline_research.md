# A2 Batch Pipeline Research

Date: 2026-07-03

This note grounds the future `a2_batch_extraction/` stage in the code that
already exists locally and pushes concrete requirements back into A1. A2 is the
stage that eventually runs a chosen coding/extraction task over many comments.

No batch runner is implemented here yet.

Follow-up notes after the initial A1 implementation:

```text
a1_to_a2_contract.md
runner_storage_design.md
scaleup_eval_plan.md
```

Follow-up grounding from A3 result-analysis research:

```text
dev/analysis/a3_result_analysis/notes/downstream_requirements_for_a2.md
dev/analysis/a3_result_analysis/notes/analysis_export_research.md
dev/analysis/a3_result_analysis/notes/audit_scoring_plan.md
```

## Local Sources Read

- `dev/analysis/helpers.py`
- `dev/analysis/a0_extraction/comment_context.py`
- `dev/analysis/a1_coding_research/notes/agent_folder_research.md`
- `variable_extraction/patientpunk/_utils.py`
- `variable_extraction/patientpunk/scripts/llm_extract.py`
- `variable_extraction/patientpunk/scripts/discover_fields.py`
- `variable_extraction/patientpunk/scripts/code_demographics_llm.py`
- `variable_extraction/patientpunk/qualitative_standards.py`
- `C:\Users\leech\Rumi\src\rumi\agent\agent.py`
- `C:\Users\leech\Rumi\src\rumi\heart\openrouter.py`
- `C:\Users\leech\Rumi\src\rumi\ideas\types.py`

## A2's Role

A2 is not where we invent the coding schema. A2 is where we operationalize a
schema that A1 has already tested.

The clean separation is:

- A0: build and verify the comment corpus and context database.
- A1: design, test, and evaluate the coding instrument.
- A2: run the selected coding instrument at increasing scale with resume,
  provenance, cost tracking, and quality checks.

A2 should reject under-specified A1 work. A large run should not start just
because code can iterate over comments.

## Existing Local Lessons

The older extraction code contains useful operational patterns.

`patientpunk._utils`:

- Centralizes model/provider configuration.
- Records model config without secrets through `llm_config()`.
- Uses shared transient retry delays.
- Provides `split_retry_batch()` for multi-item calls that fail JSON parsing or
  return the wrong number of outputs.

`llm_extract.py`:

- Learned that large inputs can truncate JSON outputs.
- Uses `MAX_TEXT_CHARS` to reserve output room.
- Defaults to one record per call after multi-record batching produced count
  ambiguity.
- Re-asks malformed single-record responses at higher temperature because a
  deterministic malformed reply can repeat at temperature 0.
- Saves incrementally every small number of completed records.
- Implements `--resume` using stable record keys.
- Merges regex and LLM results with provenance and confidence fields.
- Performs post-merge normalization and deduplication.

`discover_fields.py`:

- Separates discovery, regex validation, extraction, gap filling, and reporting.
- Saves intermediate phase outputs so a failed later phase does not force a full
  restart.
- Uses random sampling as a cost-control and representativeness tool.
- Writes a report with run metadata, coverage, hit rates, and rejected counts.
- Explicitly guards against cross-post/comment bleed by processing segments
  individually or telling the model not to span boundaries.
- Keeps discovered schemas separate from curated schemas until reviewed.

`code_demographics_llm.py`:

- Separates deductive coding from inductive discovery.
- Aggregates inductive categories into a codebook with examples.
- Reports coverage by source type.
- Maps parse failures to explicit error rows instead of silently dropping work.

These are worth carrying forward, but A2 should improve on them with typed
Pydantic outputs and a database-backed run ledger.

## Rumi Constraint For A2

Rumi supports:

```python
idea = agent.whirl(message, response_model=SomePydanticModel)
result = idea.content
```

For A2, the extraction agent should have no Rumi tools, because the local Rumi
heart raises when `response_model` and tools are used together in one `whirl()`.

Therefore:

1. A2 fetches comment/context deterministically from SQLite.
2. A2 renders the prompt deterministically.
3. A2 calls a no-tool Rumi Dervish with a Pydantic response model.
4. A2 writes the validated result, usage metadata, and errors to our own
   durable output store.

Rumi tablet history is not the A2 output store.

## Recommended A2 Folder Shape

Future structure:

```text
dev/analysis/a2_batch_extraction/
  README.md
  notes/
    batch_pipeline_research.md
    a1_to_a2_contract.md
    runner_storage_design.md
    scaleup_eval_plan.md
  scripts/
    README.md
    create_run.py
    run_batch.py
    verify_run.py
    export_results.py
  tests/
    test_run_ledger.py
    test_resume.py
    test_prompt_hash.py
```

Reusable agent code should stay in:

```text
dev/analysis/agents/
```

A2 scripts should import agents and helpers. A2 should not define long-lived
agent packages inside the stage folder.

## A2 Run Storage Contract

A2 needs an explicit run ledger. SQLite is the most pragmatic first target
because the corpus context database is already SQLite, runs need resumability,
and the output is structured but still evolving.

Proposed output location:

```text
dataset/covidlonghaulers_comments/derived/runs/
  comment_coding/
    run_YYYYMMDD_HHMMSS_<slug>.sqlite
    run_YYYYMMDD_HHMMSS_<slug>.json
```

The `.json` sidecar is a human-readable manifest. The `.sqlite` file is the
resumable ledger and result store.

Minimum `run_manifest` fields:

```text
run_id
created_at
finished_at
status
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
agent_name
agent_version
model_provider
model_name
model_config
rumi_version_or_path
python_version
git_commit
git_dirty
where_sql
order
limit
ancestor_depth
previous_sibling_limit
previous_thread_limit
```

Minimum `work_items` fields:

```text
source_line
comment_id
created_utc
date_utc
status                 # pending | running | succeeded | failed | skipped
attempt_count
last_attempt_at
last_error_type
last_error
input_hash
prompt_hash
context_hash
result_hash
skip_reason
```

Minimum `results` fields:

```text
source_line
comment_id
schema_version
prompt_version
model_name
result_json
result_hash
is_codeable
claim_count
used_context
context_comment_ids_used_json
attribution_confidence
raw_response_kind
prompt_tokens
completion_tokens
total_tokens
cost_usd
latency_ms
created_at
```

Minimum `attempts` fields:

```text
attempt_id
source_line
comment_id
started_at
finished_at
status
model_name
prompt_hash
input_hash
error_type
error
raw_metadata_json
```

Do not only write final successful rows. Failed attempts are data for prompt and
operational improvement.

## Work Item Identity

Use `source_line` and `comment_id` together.

- `source_line` is stable within this source JSONL export and makes debugging
  easy.
- `comment_id` is the Reddit-level identifier and should survive a rebuild if
  the input ordering ever changes.
- Store `source_export_sha256` and dataset manifest information so a run cannot
  be mistaken for a different source snapshot.

The natural primary key for a run is probably `source_line`, with a unique index
on `comment_id` for lookup.

## Prompt And Context Hashes

A2 needs hashes so resume is honest.

`input_hash` should include:

- target comment fields used by the prompt
- rendered ancestors/siblings/thread context
- missing-context flags
- context limits

`prompt_hash` should include:

- system instructions
- user-message template
- schema JSON
- any qualitative standards text injected into the prompt
- context renderer version

If `prompt_hash` or `input_hash` changes, A2 should not silently treat old
results as valid for the new run. Either create a new run or explicitly mark
the previous rows as from another prompt/input version.

## Batching Strategy

Start with one comment per LLM call.

The older scripts tried multi-item calls and had to add split-retry because LLMs
can return the wrong number of results or blur boundaries. For comment-level
attribution, that risk is worse: a model could blend claims across target
comments.

A2 can later experiment with micro-batches only if:

- the response model includes one result per `source_line`
- the parser validates exact count and exact source IDs
- failed batches split recursively
- eval shows no attribution degradation

Default A2 should prioritize correctness and resumability over throughput.

## Scaling Plan

A2 should scale in gates:

1. `dry_render`: render prompts for selected comments, no LLM calls.
2. `tiny`: 25-50 comments, one worker.
3. `pilot`: 300-1,000 comments, low concurrency.
4. `distribution`: 5,000-10,000 comments, compare output distributions to A1.
5. `large`: 25,000-100,000 comments, with audit sampling.
6. `full`: all eligible comments only after cost, quality, and failure rates are
   acceptable.

Each gate should produce a short run report before the next gate.

## Quality Gates

A2 should refuse or warn before scaling if:

- structured-output validation failure rate is above the A1 threshold
- attribution leakage rate is above threshold on audit samples
- skipped/deleted/removed handling differs from A1 rules
- output distribution shifts sharply from the A1 pilot
- too many rows use `attribution_confidence=low`
- the model frequently uses context but does not identify which context comment
  disambiguated the target
- retry rate or rate-limit failures are high enough to distort throughput/cost
- prompt/model/schema hashes are missing

Example run-level metrics:

```text
total_items
succeeded
failed
skipped
validation_error_rate
transient_error_rate
mean_latency_ms
p50_latency_ms
p95_latency_ms
total_prompt_tokens
total_completion_tokens
total_cost_usd
mean_claims_per_codeable_comment
is_codeable_rate
used_context_rate
low_attribution_confidence_rate
removed_or_deleted_skip_rate
```

## Retry And Failure Policy

Suggested failure classes:

- `transient_provider_error`: retry with backoff.
- `rate_limited`: retry with backoff and maybe lower concurrency.
- `structured_validation_error`: retry once, then fail for review.
- `empty_response`: retry.
- `context_missing`: not an error if expected; encode in result/missing flags.
- `deleted_or_removed`: skip according to A1 policy.
- `prompt_too_large`: fail loudly and feed back into A1 context limits.
- `unexpected_exception`: fail and keep traceback summary.

Do not hide malformed outputs. With Pydantic response models, malformed outputs
should become explicit failed attempts and review artifacts.

## Concurrency

Start with conservative worker counts.

Large concurrency can make failures harder to debug and can trigger provider
rate limits. A2 should support:

- `--workers`
- `--limit`
- `--where-sql`
- `--resume`
- `--max-attempts`
- `--stop-after-failures`
- `--dry-render`

The runner should update status transactionally:

1. claim pending item as running
2. render prompt and compute hashes
3. call model
4. validate result
5. write attempt and result
6. mark item succeeded/skipped/failed

If the process crashes after a row is marked running, resume should be able to
reclaim stale running items older than a timeout.

## Output Format

SQLite should be the primary run store during development. JSONL exports can be
generated from SQLite for downstream analysis.

Recommended exports:

```text
results.jsonl              # one validated result per successful comment
failures.jsonl             # failed work items with error summaries
audit_sample_ids.jsonl     # source lines selected for manual review
run_report.json            # metrics and provenance
```

JSONL rows should include both metadata and structured output:

```json
{
  "run_id": "...",
  "source_line": 11,
  "comment_id": "fz5axid",
  "schema_version": "comment_coding_v0.1",
  "prompt_version": "comment_coder_v0.1",
  "result": {}
}
```

## Sampling And Audit In A2

A2 should automatically select audit samples from each meaningful run:

- random successful rows
- all failed rows up to a cap
- high-claim-count rows
- low-confidence rows
- rows where context was used
- deep replies
- very short target comments
- long target comments
- top-level comments with missing root post
- comments with deleted/removed ancestors

This pushes back into A1: A1 must define the audit rubric, the attribution
failure taxonomy, and the metrics that determine whether a larger A2 run is
allowed.

## Relationship To Field Discovery

A2 should not mix field discovery and production extraction in the same run.

There are two separate A2-style runners:

- coding/extraction runner: applies a fixed A1 schema to comments.
- discovery runner: samples comments and proposes fields/codebook changes.

Discovery outputs should return to A1 for review and schema revision. They
should not mutate the production extraction schema automatically.

The older `discover_fields.py` eventually moved toward keeping discovered
schemas in temp output instead of writing directly back into curated schema.
That is the right instinct for A2 as well.

## What A1 Must Hand To A2

A1 must produce these before A2 can run beyond tiny/pilot scale:

- task name and scope
- Pydantic response model
- schema version
- prompt version
- context renderer and default context limits
- skip rules
- attribution rules
- evaluation set IDs
- validation metrics from prompt-development runs
- acceptable failure thresholds
- model choice and fallback model
- expected output distribution from pilot samples
- audit rubric
- storage field requirements
- normalization rules for controlled values

If any item is missing, A2 can still do dry renders or tiny experiments, but it
should not run a large batch.

## Open Decisions

- Whether A2 runner should live entirely in SQLite or use SQLite plus JSONL from
  the start.
- Whether each schema/prompt pair gets its own run database or multiple runs
  share one database.
- Whether A2 should join directly against `comments.sqlite` or access comments
  only through `CommentStore`.
- How to record raw rendered prompts without duplicating too much Reddit text.
- Whether prompt texts should be stored in the run DB, hashed only, or both.
- Whether to use Rumi for all model calls or call OpenRouter/OpenAI directly for
  easier usage/cost metadata.
- How strict the first large-run gates should be.
