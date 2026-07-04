# A1 Agent Folder Research

Date: 2026-07-03

This note captures the current research direction for putting Rumi-run analysis
agents under `dev/analysis/` while keeping numbered analysis stages such as
`a0_extraction/`, `a1_coding_research/`, and later `a2_...` folders clean.

No pipeline code is implemented here yet. This is a design note for A1.

## Local Sources Read

- `C:\Users\leech\dr\dr-hiro\src\agents\`
- `C:\Users\leech\dr\dr-hiro\src\agents\README.md`
- `C:\Users\leech\dr\dr-hiro\src\agents\AnalystAgent\`
- `C:\Users\leech\dr\dr-hiro\src\agents\PortfolioManagerAgent\`
- `C:\Users\leech\PatientPunk\src\agents\`
- `C:\Users\leech\PatientPunk\src\agents\_common\brain.py`
- `C:\Users\leech\PatientPunk\src\agents\_common\runtime.py`
- `C:\Users\leech\Rumi\src\rumi\agent\agent.py`
- `C:\Users\leech\Rumi\src\rumi\heart\openrouter.py`
- `C:\Users\leech\Rumi\src\rumi\ideas\types.py`

## What Dr Hiro Does Well

The `dr-hiro` agent tree has a useful package contract:

```text
src/agents/
  README.md
  __init__.py
  _common/
    services/
    storage/
    tools/
    ui/
    ...
  SomeAgent/
    __init__.py
    manifest.py
    main.py
    api.py
    brain/
      prompts.py
      model_configs.json
    tools/
      deps.py
      tool_*.py
      shared/
    storage/
    tests/
```

Important conventions worth borrowing:

- One folder per agent.
- `_common/` is for deterministic shared code, not agent-specific behavior.
- `manifest.py` is plain metadata: name, version, description, dependencies.
- `main.py` is the contract surface that wires the agent brain and public tools.
- `api.py` is the public import surface; other code should not import directly
  from `tools/`, `storage/`, or implementation internals.
- `brain/` separates prompt text from model config.
- `tools/deps.py` lazily creates external clients/services. No heavy clients at
  module import time.
- `tools/tool_*.py` files hold implementation. In `dr-hiro`, the decorated tool
  wrapper often lives in `main.py`, while the real implementation lives in a
  tool module.
- `storage/` holds stable structured models and durable state shapes.
- `tests/` are colocated with the agent or shared module they protect.

This structure is heavier than we need for early analysis, but the boundary
ideas are good: manifest, brain, API, implementation, tests, and shared code
should not be mixed together.

## What PatientPunk Already Does

PatientPunk already has Rumi-style one-shot agents under `src/agents/`:

```text
src/agents/
  ResolverAgent/
    manifest.py
    main.py
    brain/
      brain.json
      prompts.py
  JudgeAgent/
  HooperAgent/
  DrVexAgent/
  SynthesizerAgent/
  TheTrialAgent/
  _common/
    brain.py
    runtime.py
```

Those agents use this pattern:

- Subclass `rumi.Dervish`.
- Set a class-level `heart_config = HeartConfig(voices=[...])`.
- Load model settings from `brain/brain.json`.
- Put system instructions in `brain/prompts.py`.
- Use an ephemeral `World()` for one-shot calls so history does not bleed
  between runs.
- Keep public functions such as `resolve_query()` or `grade()` as thin wrappers
  around `agent.whirl(...)`.

This is a better runtime fit for the analysis pipeline than the `dr-hiro`
NodeAI decorators, because our A1/A2 work is mostly one-shot classification and
structured extraction over database rows.

## Rumi Structured Output Constraints

The local Rumi checkout supports typed structured output:

```python
idea = agent.whirl(message, response_model=SomePydanticModel)
result = idea.content
```

Observed constraints from the local Rumi code:

- `response_model` routes through the OpenAI SDK parse path.
- The returned idea is a `BaseModelIdea` whose immediate `content` is a
  validated Pydantic instance.
- `response_model` cannot currently be combined with Rumi tools in the same
  `whirl()` call. Rumi raises before sending the request because strict tool
  schemas are not generated.
- Persisted/replayed Rumi history should not be treated as the canonical
  analysis output. Store extraction results explicitly in our own derived files
  or database tables.
- Batch extraction should use fresh agent identities or ephemeral worlds to
  avoid previous comments contaminating later comments.

For our comment coding pipeline, this means the likely design is:

1. Deterministic Python fetches the target comment and context from
   `comments.sqlite`.
2. Python renders a single prompt message.
3. A no-tool Rumi Dervish calls `whirl(..., response_model=...)`.
4. Python validates, records metadata, and writes explicit output rows.

Do not make the coding agent fetch comments with Rumi tools if we want strict
Pydantic structured output.

## Recommended Analysis Layout

The user suggestion is sound: keep reusable agents in an `agents/` folder and
keep numbered `a1_...`, `a2_...` folders for pipeline stages.

Recommended shape:

```text
dev/analysis/
  README.md
  helpers.py
  a0_extraction/
    ...

  agents/
    __init__.py
    README.md
    _common/
      __init__.py
      brain.py              # analysis-local Rumi voice loading
      runtime.py            # ephemeral World / env handling
      render_context.py     # prompt rendering helpers
      schemas.py            # shared structured-output primitives
    CommentCoderAgent/
      __init__.py
      manifest.py
      main.py               # Dervish + public `code_comment(...)`
      api.py                # stable import surface
      brain/
        brain.json
        prompts.py
      schemas.py            # Pydantic output model for comment coding
      tests/
    FieldDiscoveryAgent/
      __init__.py
      manifest.py
      main.py
      api.py
      brain/
        brain.json
        prompts.py
      schemas.py
      tests/
    AuditAgent/
      ...

  a1_coding_research/
    README.md
    notes/
      agent_folder_research.md
      codebook_design.md
      sampling_plan.md
      prompt_eval_plan.md
    samples/
      README.md
    evals/
      README.md
    scripts/
      README.md

  a2_batch_extraction/
    README.md
    ...
```

The split matters:

- `dev/analysis/agents/` should contain reusable Rumi agent definitions.
- `a1_coding_research/` should contain research notes, sample selection code,
  prompt experiments, eval harnesses, and small reviewed artifacts.
- `a2_batch_extraction/` should later contain resumable batch runners, output
  writers, retry logic, cost tracking, and large-run operational code.

A1 should not become the permanent home for agents. A1 should use agents.

## What A1 Should Actually Produce

A1 is the measurement-design stage, not the full extraction stage.

Expected A1 outputs:

- A stable context rendering format.
- A sample strategy for small, representative comment sets.
- One or more reviewed sample JSONL files containing comment IDs/source lines,
  not copied raw corpus blobs.
- A first-pass codebook or schema.
- Pydantic structured-output models.
- Prompt versions with changelog notes.
- A model comparison report.
- A small gold or review set that is not used for prompt tuning.
- Error taxonomy: attribution errors, malformed output, over-extraction,
  missing uncertainty, parent-comment leakage, deleted-comment handling.
- A2 readiness checklist: schema version, prompt version, context renderer
  version, skip rules, attribution rules, audit rubric, eval metrics, and
  scaleup thresholds.

Expected A1 non-goals:

- No full-dataset LLM run.
- No assumption that the first schema is final.
- No direct reliance on physical year/month JSONL file order.
- No storing final results only inside Rumi history.
- No production batch runner; that belongs in `a2_batch_extraction/`.

## A2 Backpressure On A1

After researching the future A2 batch stage, A1 should be treated as the place
where we create a versioned coding instrument for A2.

A2 will need:

- `task_name`
- `schema_name`
- `schema_version`
- Pydantic `response_model`
- `prompt_name`
- `prompt_version`
- prompt hash inputs
- context renderer version
- default context limits
- skip rules
- attribution rules
- normalization rules
- review set IDs
- eval metrics
- acceptance thresholds
- audit rubric
- model plan
- expected output distribution from pilot samples

If A1 does not produce these, A2 can still do dry renders or tiny experiments,
but it should not run a large batch.

Practical consequence: A1 notes should not stop at "this prompt looks good."
They should record what changed, how it was evaluated, what it failed on, and
which exact schema/prompt/context versions A2 is allowed to run.

## Suggested A1 Subfolders

```text
a1_coding_research/
  README.md
  notes/
    agent_folder_research.md
    a2_requirements_for_a1.md
    sampling_plan.md
    codebook_design.md
    attribution_rules.md
    model_bakeoff.md
  samples/
    sample_manifest.json
    seed_review_ids.jsonl
    prompt_dev_ids.jsonl
    gold_holdout_ids.jsonl
  evals/
    README.md
    metrics_definition.md
    run_manifest_template.json
    runs/
  prompts/
    README.md
    comment_coder_v0.1.md
    changelog.md
  scripts/
    select_samples.py
    render_sample_contexts.py
    run_prompt_dev.py
```

The sample files should mostly store identifiers and metadata:

```json
{"source_line": 11, "comment_id": "fz5axid", "sample": "seed_review", "reason": "reply_with_parent_context"}
```

The context and comment bodies can be rendered from the SQLite database when
needed. That avoids duplicating raw Reddit content across git-tracked files.

## Candidate Agent Roles

Start with fewer agents.

`CommentCoderAgent`:

- Codes one target comment at a time.
- Receives target comment plus bounded context.
- Must extract only target-author claims.
- Uses parent/ancestor context only for disambiguation.
- Returns a Pydantic `CommentCodingResult`.

`FieldDiscoveryAgent`:

- Reads batches of sampled target comments.
- Proposes candidate fields/codebook entries.
- Should follow the qualitative standards already present in
  `variable_extraction/patientpunk/qualitative_standards.py`.
- Should output field proposals, not final labels for the corpus.

`AuditAgent`:

- Reviews a completed `CommentCodingResult` against the rendered context.
- Flags attribution leakage, missing evidence, uncertainty problems, and schema
  misuse.
- Useful for model bakeoff and for later quality-control sampling.

Do not add more agents until a single coder and audit loop expose a real need.

## Comment Context Rules For Prompts

Every extraction prompt should make these roles explicit:

- `TARGET_COMMENT`: the only comment being coded.
- `ANCESTORS`: parent chain used for reference resolution.
- `PREVIOUS_SIBLINGS`: earlier replies to the same parent, used cautiously.
- `PREVIOUS_THREAD_COMMENTS`: earlier comments in the same post/thread, broad
  context only.

Core attribution rule:

Only code claims made by the target comment's author in the target comment.
Context can clarify pronouns, omitted objects, and conversational references,
but context claims are not target-author claims.

Useful output flags:

- `used_context`: whether context materially changed interpretation.
- `context_comment_ids_used`: which context comments were actually used.
- `attribution_confidence`: high/medium/low.
- `ambiguous`: true when the target cannot be interpreted without guessing.
- `skip_reason`: deleted, removed, too_short, non_patient, unclear, other.

## Initial Structured Output Sketch

This is not final, but it gives A1 a shape to test:

```python
class EvidenceSpan(BaseModel):
    quote: str
    source: Literal["target_comment"]
    rationale: str


class ExtractedClaim(BaseModel):
    kind: str
    normalized_label: str
    raw_text: str
    experiencer: Literal["self", "other_person", "general", "unclear"]
    temporality: str | None = None
    confidence: Literal["high", "medium", "low"]
    evidence: list[EvidenceSpan]


class CommentCodingResult(BaseModel):
    comment_id: str
    source_line: int
    is_codeable: bool
    skip_reason: str | None = None
    claims: list[ExtractedClaim]
    used_context: bool
    context_comment_ids_used: list[str]
    attribution_confidence: Literal["high", "medium", "low"]
    notes: str | None = None
```

The exact fields should be tuned after a small qualitative read. The important
thing is that evidence points to the target comment only unless we explicitly
create separate fields for context-derived disambiguation.

## Model Strategy For A1

Use cheap models for iteration, but compare them against a stronger model and
manual review before trusting them.

Recommended A1 phases:

1. Human read: 50-100 context windows.
2. Seed schema: write the first Pydantic model and prompt.
3. Prompt dev: 100-300 comments, cheap model.
4. Bakeoff: same sample through cheap and stronger models.
5. Audit: inspect disagreements and attribution failures.
6. Lock an initial schema only after the failure modes are understood.

For Rumi, model config should live per agent in `brain/brain.json`, with a
global `RUMI_MODEL` override kept available for experiments.

## Strong Recommendations

- Yes, create `dev/analysis/agents/`.
- Yes, keep `a1_...`, `a2_...` as stage folders.
- Put Rumi Dervish classes in `agents/`, not inside A1.
- Put A1 prompt/eval/sample research under `a1_coding_research/`.
- Treat A1's main deliverable as a versioned coding instrument, not merely a
  promising prompt.
- Use strict Pydantic `response_model` for coding agents.
- Do not register Rumi tools on coding agents that need `response_model`.
- Fetch comments/context deterministically with Python helpers before the Rumi
  call.
- Use fresh Rumi worlds or agent IDs for each independent coding call.
- Store outputs explicitly in `dataset/covidlonghaulers_comments/derived/` or a
  later ignored run directory, not only in Rumi tablet history.
- Keep generated sample contexts and LLM outputs out of git unless they are
  tiny, reviewed, and intentionally de-identified or ID-only.

## Open Decisions

- Exact A1 folder name: this note uses `a1_coding_research`.
- Whether first coding target is broad relevance triage or specific biomedical
  extraction.
- Whether field discovery should happen before or after a hand-authored starter
  codebook.
- Whether output storage for A1 runs should be SQLite, JSONL, or both.
- How much context to include by default for each coding task.
- How to represent deleted/removed comments in samples and evals.
- Whether to use one all-purpose `CommentCoderAgent` or split into narrower
  agents after the first evaluation round.
- What exact readiness checklist A2 must verify before pilot, distribution, and
  full-corpus runs.
