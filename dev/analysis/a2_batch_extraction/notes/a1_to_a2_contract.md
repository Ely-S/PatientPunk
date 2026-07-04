# A1 To A2 Contract

Date: 2026-07-04

This note records what A2 can rely on after the initial A1 implementation, and
what A2 must still push back to A1 before any large run.

## Local Sources Read

- `dev/analysis/a1_coding_research/README.md`
- `dev/analysis/a1_coding_research/scripts/select_samples.py`
- `dev/analysis/a1_coding_research/scripts/render_sample_contexts.py`
- `dev/analysis/a1_coding_research/scripts/run_prompt_dev.py`
- `dev/analysis/a1_coding_research/scripts/summarize_eval.py`
- `dev/analysis/agents/CommentCoderAgent/api.py`
- `dev/analysis/agents/CommentCoderAgent/brain/brain.json`
- `dev/analysis/agents/CommentCoderAgent/brain/prompts.py`
- `dev/analysis/agents/CommentCoderAgent/manifest.py`
- `dev/analysis/agents/CommentCoderAgent/schemas.py`
- `dev/analysis/agents/_common/render_context.py`
- `dev/analysis/agents/_common/runtime.py`
- `dataset/covidlonghaulers_comments/derived/a1_coding_research/runs/20260704T051455Z_prompt_dev_live_3/metrics.json`
- `variable_extraction/patientpunk/_utils.py`
- `variable_extraction/patientpunk/scripts/llm_extract.py`
- `variable_extraction/patientpunk/scripts/discover_fields.py`

## Current A1 Instrument

A1 now exposes a usable but early coding instrument:

```text
task_name: comment_coding
schema_name: comment_coding
schema_version: comment_coding_v0.1
prompt_name: comment_coder
prompt_version: comment_coder_v0.1
context_renderer_version: comment_context_prompt_v0.1
default_model: openai/gpt-oss-120b
strong_comparator_model: anthropic/claude-sonnet-4
```

Default context limits:

```text
ancestor_depth: 2
previous_sibling_limit: 2
previous_thread_limit: 3
max_body_chars: 1200
max_total_chars: 16000
```

Default model config:

```text
model: openai/gpt-oss-120b
temperature: 0
max_tokens: 4096
context_window: 0
```

`context_window=0` matters. A2 should keep each model call independent and use
a fresh agent id per attempt. The model should not see previous comments through
Rumi history.

## A2 Should Import These Interfaces

A2 should use the A1 public interfaces instead of duplicating prompt or schema
logic:

```python
from dev.analysis.a0_extraction.comment_context import CommentStore
from dev.analysis.agents._common.render_context import (
    ContextRenderConfig,
    context_comment_ids,
    render_context_for_prompt,
    stable_text_hash,
)
from dev.analysis.agents.CommentCoderAgent.brain.prompts import build_message
from dev.analysis.agents.CommentCoderAgent.api import code_comment_with_metadata
from dev.analysis.agents.CommentCoderAgent.manifest import manifest
```

Recommended call path:

```text
comments.sqlite -> CommentStore.get_context()
-> render_context_for_prompt()
-> build_message()
-> code_comment_with_metadata()
-> write validated result to A2 run store
```

Do not make A2 assemble prompt strings independently. If A2 changes the prompt,
context renderer, or schema, that is an A1 change and should be versioned there.

## A1 Result Shape

A2 receives a `CodingResponse`:

```text
result: CommentCodingResult
metadata: OpenRouter/Rumi usage metadata
latency_seconds
model
agent_id
```

`CommentCodingResult` validates:

- exact schema version
- exact prompt version
- target `comment_id`
- target `source_line`
- skipped rows have `skip_reason` and no claims
- codeable rows have at least one claim
- `used_context` implies non-empty `context_comment_ids_used`
- context evidence is disallowed by schema; evidence source must be
  `target_comment`

A2 should still enforce these fields at the storage boundary. Do not trust a
row simply because the model API returned a response.

## Lessons From The A1 Live Smoke Test

The successful smoke test:

```text
run: 20260704T051455Z_prompt_dev_live_3
attempted: 3
successes: 3
failures: 0
structured_success_rate: 1.0
claim_count: 21
used_context: 0
total_tokens: 10602
total_cost_usd: 0.00169469
```

The earlier live attempts exposed two operational failures that A2 must handle:

1. Long comments can hit completion limits. The A1 `max_tokens` cap had to move
   from 1800 to 4096.
2. `openai/gpt-oss-120b` can occasionally return an empty body or non-structured
   result through OpenRouter. A1 now retries with a fresh agent id.

This means A2 must treat retries as normal run data, not as an exceptional
debug-only path.

Rough smoke-test cost:

```text
tokens/comment: about 3534
cost/comment: about $0.000565
```

This is not a full-corpus estimate. The sample included one long, multi-claim
comment, so the average is likely skewed. If that number held across all
1,950,192 comments, the cheap-model full run would be about $1,100. A2 should
measure cost again on larger, representative pilots before budgeting.

## What A2 Can Do Now

A2 can safely implement:

- dry-render runs over any selected comment set
- run manifests
- prompt/input hashing
- SQLite ledger schema
- local deterministic work-item selection
- tiny live runs with strict `--limit`
- resume and retry mechanics
- run summarization
- audit-sample selection
- comment-level and claim-level analysis exports

A2 should not yet run:

- full corpus extraction
- high-concurrency model calls
- production exports
- schema-changing discovery
- automatic promotion from A1 samples to full scale

## A1 Gaps Blocking A2 Scale

A1 still needs these before A2 can go beyond tiny or pilot runs:

- manual review of `seed_review`
- prompt-dev run on enough frozen IDs to see real failure modes
- strong-model comparator on the same IDs
- holdout run on `gold_holdout`
- attribution leakage audit labels
- unsupported-evidence audit labels
- context-use correctness audit labels
- skip-rule audit labels
- acceptable thresholds for structured failures, retry rates, and leakage
- expected distributions for codeable rate, claim count, used-context rate, and
  low-confidence rate

A2 should encode these as run gates. If the gates are missing, A2 can continue
doing dry renders and tiny smoke tests, but it should warn before larger runs.

## A3 Downstream Requirements

A3 research adds downstream requirements that A2 should treat as part of the run
contract, not as optional exports:

- mandatory `claim_rows` derived from each successful `result_json`
- deterministic claim IDs and claim hashes
- comment-level rows with time, parent/context, cost, retry, and hash metadata
- claim-level rows with evidence quote/source, assertion, experiencer, and
  context-use metadata
- separate comment-level and claim-level audit templates
- export manifests with file hashes and row counts
- normalization columns added later by A3 without overwriting raw model labels

If A2 cannot produce these tables from a run, the run is not ready for downstream
analysis even if every model call succeeded.

## Deterministic Skips

A2 can save cost by deterministically skipping exact `[removed]` and
`[deleted]` target comments. There are two acceptable approaches:

1. Still call the model and let the schema record `removed_deleted`.
2. Locally create a schema-valid `CommentCodingResult` with
   `is_codeable=false` and `skip_reason=removed_deleted`, then mark the work
   item as `deterministic_skipped`.

The second approach is cheaper and more reproducible, but A1 should explicitly
approve it because it bypasses the model. For early pilots, include a small set
of removed/deleted rows through the model to confirm the prompt remains aligned.

## Hash Inputs A2 Must Own

A1 currently records rendered context and prompt message hashes in dry/live run
JSONL. A2 needs stronger run-level hashes:

```text
schema_hash:
  CommentCodingResult JSON schema

prompt_hash:
  comment_coder_v0.1.md
  build_message() template/version
  schema_hash
  context_renderer_version

context_hash:
  rendered_context_for_prompt output
  ContextRenderConfig values

prompt_message_hash:
  final user message sent to Rumi

instrument_hash:
  task manifest
  schema_hash
  prompt_hash
  model config
  context config
```

Resume must compare hashes. If the hash changes, A2 should start a new run or
mark old rows as belonging to a different instrument.

## A2 Rule Of Thumb

A1 defines the measurement instrument. A2 operates it.

If A2 needs to change what a field means, how evidence works, how context is
used, or what model output is valid, that is an A1 change first.
