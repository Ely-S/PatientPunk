# A1 Prompt Engineering Plan

Date: 2026-07-03

This note translates the local Claude prompt-engineering skill and the
`dr-hiro` prompt-engineering guides into a plan for A1 comment-coding prompt
engineering.

This is still research/design. No prompt runner or LLM call is implemented here.

## Local Sources Read

Claude skill:

- `C:\Users\leech\dr\dr-hiro\.claude\skills\prompt-engineering\SKILL.md`
- `C:\Users\leech\dr\dr-hiro\.claude\skills\prompt-engineering\reference\eval-recipe.md`
- `C:\Users\leech\dr\dr-hiro\.claude\skills\prompt-engineering\reference\constraints-checklist.md`
- `C:\Users\leech\dr\dr-hiro\.claude\skills\prompt-engineering\reference\gpt-oss-cheatsheet.md`
- `C:\Users\leech\dr\dr-hiro\.claude\skills\prompt-engineering\reference\output-overlays.md`

Guide corpus:

- `C:\Users\leech\dr\dr-hiro\docs\guides\prompt-engineering\00-INDEX.md`
- `C:\Users\leech\dr\dr-hiro\docs\guides\prompt-engineering\guide\00-spine.md`
- `C:\Users\leech\dr\dr-hiro\docs\guides\prompt-engineering\guide\guide-2-eval-model-prompt.md`
- `C:\Users\leech\dr\dr-hiro\docs\guides\prompt-engineering\guide\guide-3-prompt-build.md`
- `C:\Users\leech\dr\dr-hiro\docs\guides\prompt-engineering\guide\guide-4-model-migration.md`

Nearby A1/A2 notes:

- `dev/analysis/a1_coding_research/notes/agent_folder_research.md`
- `dev/analysis/a1_coding_research/notes/a2_requirements_for_a1.md`
- `dev/analysis/a2_batch_extraction/notes/batch_pipeline_research.md`

## Main Translation To PatientPunk

The `dr-hiro` prompt-engineering doctrine is not "write a better prompt."

It is:

```text
baseline -> inspect actual failures -> make a targeted positive-cue edit ->
measure on the same frozen cases -> de-bloat only redundancy -> gate before scale
```

For PatientPunk A1, the equivalent is:

```text
sample -> manually inspect -> write a baseline schema/prompt -> run on frozen
prompt-dev cases -> inspect row-level failures -> add targeted examples/rules ->
compare on the same cases -> freeze a holdout -> decide whether A2 may pilot
```

The prompt is not done when it sounds rigorous. It is done when it clears the A1
eval gates and produces an A2-ready versioned coding instrument.

## What Carries Over Directly

From the Claude skill and guide corpus:

- **Baseline first.** A scary result from a cheap model means little until a
  stronger comparator or manual baseline is checked on the same cases.
- **Read the failing rows, not just summary metrics.** For A1, the equivalent of
  `results[]` is each comment/context/result triple.
- **Fix the one real failure mode.** Do not add broad rules because they feel
  reasonable. Add the smallest rule/example that closes an observed failure.
- **Use positive directives and routes.** Prefer "extract target-author claims
  only from TARGET_COMMENT; use context only to resolve references" over a long
  stack of "do not extract..." prohibitions.
- **Cue specificity beats abstract rules.** Literal examples for "same here",
  "my friend", quoted text, parent-only symptoms, and deleted parents will do
  more than another paragraph of abstract instruction.
- **Measure prompt changes as arms.** Prompt versions should be compared on the
  same frozen IDs, not judged by vibes.
- **Treat the harness as software.** The eval rubric, sample labels, and metrics
  need adversarial review; many apparent model failures will be label or scorer
  failures.
- **De-bloat after the gate is understood.** Cut redundant prose, not directives,
  examples, attribution scars, or schema definitions.
- **Keep tested-vs-predicted separate.** Literature tips and intuitions are
  hypotheses until our A1 eval proves them on this corpus.

## What Does Not Transfer Directly

The `dr-hiro` skill is mostly about routing/tool selection and `@tool`
docstrings. A1 is different:

- no money tools
- no Rumi tools if using `response_model`
- no routing decision among tool calls
- structured extraction over patient-authored text
- context disambiguation across Reddit reply chains
- qualitative research validity rather than transaction safety

So A1 should borrow the discipline, not the exact gate metrics.

The A1 equivalent of a money-tool leak is **attribution leakage**:

```text
the model extracts a claim from a parent/context comment and attributes it to
the target comment author
```

That should be treated as a zero-tolerance or near-zero-tolerance failure class.

## A1 Prompt Surface Map

A1 prompt engineering has these surfaces:

- Pydantic response model
- system instructions
- user-message/context renderer
- qualitative standards injected into the prompt
- literal examples/few-shot cases, if any
- skip policy
- confidence scale
- evidence contract
- normalization rules
- model config

Every prompt experiment should say which surfaces changed.

Do not silently change schema and prompt at the same time unless the run is
explicitly a bundled arm.

## Prompt Architecture

Recommended structure for `CommentCoderAgent` instructions:

```text
1. Role and task
2. Input section definitions
3. Core attribution rule
4. Context-use policy
5. Skip policy
6. Claim extraction schema semantics
7. Evidence and confidence policy
8. Literal examples of hard cases
9. Output contract
```

The prompt should be boring and contractual. A1 is a measurement instrument, not
a conversational assistant.

## Core Positive Directives

Use positive routing language:

```text
Code only the TARGET_COMMENT author's claims.
Use ANCESTORS only to resolve what the target author is referring to.
Record which context comment IDs were used when context changes interpretation.
Quote evidence from TARGET_COMMENT for extracted target-author claims.
Mark ambiguous when interpretation would require guessing.
Return an explicit skip reason when the target comment is not codeable.
```

Avoid relying on negation alone:

```text
Do not extract claims from context.
Do not hallucinate.
Do not over-infer.
```

Those can still appear as secondary constraints, but the main instruction should
tell the model what to do instead.

## Literal Cues A1 Probably Needs

These should become few-shot or mini-examples after we inspect actual comments.

`same here` / `me too`:

- Parent says "I have crushing fatigue."
- Target says "Same here, since March."
- Allowed: extract fatigue for target, because the target explicitly adopts the
  parent claim.
- Evidence quote remains from target: `"Same here, since March."`
- Context comment ID goes in `context_comment_ids_used`.

Parent-only claim:

- Parent says "LDN helped my brain fog."
- Target says "What dose did you take?"
- Do not extract LDN outcome for target.
- Target is asking about parent experience, not reporting their own.

Other-person claim:

- Target says "My husband has POTS after COVID."
- Extract only if schema has `experiencer=other_person`; otherwise mark
  non-self-report or separate from self-reported claims.

Quoted text:

- Target quotes another user or doctor.
- Extract only what the target endorses or reports as their own experience.
- The quote itself is not automatically the target author's claim.

General advice:

- Target says "People should try electrolytes."
- This is a general recommendation, not necessarily a self-report.

Negation:

- Target says "I do not have POTS, just tachycardia."
- Extract the positive reported condition/symptom if in scope; do not extract
  the negated condition as present.

Unclear reference:

- Parent mentions several symptoms.
- Target says "It got worse."
- If "it" cannot be resolved confidently, mark ambiguous or low confidence.

Deleted/removed:

- Target body is `[deleted]` or `[removed]`.
- Skip with the configured skip reason.
- If parent is deleted but target is meaningful, code the target and record
  missing context.

These examples are not final labels. They are A1 prompt-engineering probes.

## Prompt Arms To Test

A1 should version prompt arms explicitly.

Candidate ladder:

```text
B0  baseline schema + minimal target/context prompt
A1  + explicit TARGET_COMMENT / CONTEXT roles and attribution rule
C1  + context-use examples ("same here", parent-only, unclear reference)
S1  + skip-policy block and deleted/removed handling
E1  + evidence contract and confidence calibration
Q1  + qualitative standards/codebook discipline
R1  compacted version after the best arm is known
```

Each arm should run on the same prompt-dev IDs. Do not compare a prompt run on
one sample to another prompt run on a different sample.

Possible controls:

- **Position control:** move the attribution rule earlier/later to see if the
  model is sensitive to placement.
- **Example ablation:** remove examples while keeping the same schema to measure
  whether hard-case examples actually help.
- **Context ablation:** run target-only vs context-included on the same IDs to
  measure when context improves recall and when it causes leakage.
- **Model comparator:** cheap model vs stronger model on the same prompt and IDs.

The `dr-hiro` lesson is not that every control is mandatory forever. It is that
large claims need controls. If we claim "context helps," we need a context
ablation. If we claim "examples fix attribution," we need an example ablation.

## A1 Failure Taxonomy

A1 prompt failures should be classified row-by-row.

Suggested labels:

- `invalid_structured_output`
- `wrong_skip`
- `missed_self_report`
- `over_extracted_context_claim`
- `parent_context_leakage`
- `wrong_experiencer`
- `wrong_negation`
- `wrong_temporality`
- `wrong_normalization`
- `unsupported_evidence`
- `confidence_too_high`
- `context_needed_but_not_used`
- `context_used_but_not_needed`
- `ambiguous_not_marked`
- `too_much_free_text`
- `schema_mismatch`

The first A1 eval loop should spend more time reading failures than adjusting
the prompt. The prompt edit should be traceable to a dominant failure class.

## Metrics For Prompt Engineering

A1 should track:

```text
structured_output_validity
skip_accuracy
self_report_precision
self_report_recall
parent_context_leakage_rate
wrong_experiencer_rate
unsupported_evidence_rate
ambiguous_case_handling_rate
used_context_rate
context_use_precision
low_confidence_rate
mean_claims_per_codeable_comment
prompt_too_large_rate
```

For early A1, some metrics may be manually scored on a small set. That is fine.
The important part is that every prompt change has a measurable before/after on
the same IDs.

## A1 Eval Sets

Recommended split:

- `seed_review`: 50-100 rows read by humans to understand the data shape.
- `prompt_dev`: 100-300 rows used for prompt/schema iteration.
- `gold_holdout`: 100-300 rows frozen and not used for prompt writing.
- `adversarial_context`: small hand-curated set of hard context cases.

The `adversarial_context` set should include:

- same/me-too replies
- parent-only claims
- replies asking questions
- target discusses another person
- target quotes another user
- target gives general advice
- negated diagnosis/symptom
- multiple possible antecedents
- missing parent
- deleted/removed target
- very short replies
- long multi-claim replies

## De-Bloat Policy

De-bloat only after a candidate prompt clears the main gates.

Safe cuts:

- duplicated wording
- long rationale the model does not need
- repeated schema descriptions already enforced by Pydantic field descriptions
- examples that do not affect eval metrics
- prose that restates a deterministic renderer label

Do not cut:

- attribution rule
- context-use rule
- literal hard-case examples that closed observed failures
- skip rules
- confidence scale
- evidence contract
- qualitative standards that define the measurement construct
- schema field definitions

For A1, token reduction is secondary to measurement validity. A2 can pay for a
longer prompt if it avoids attribution leakage.

## How To Use gpt-oss-120b In A1

The skill's gpt-oss lesson probably transfers:

- It is good at tool/JSON/structured work, but still needs explicit instructions.
- It may default to polite hedging or clarification when an input is ambiguous.
- Literal examples help more than abstract rules.
- The `effort:low` configuration is usually the intended low-latency default.

For our Rumi setup:

- use no-tool Dervishes when calling `whirl(..., response_model=...)`
- keep the prompt's structured-output contract explicit
- do not assume provider-native schema enforcement saves weak prompt wording
- compare against a stronger model on the same cases before trusting it

Potential A1 gpt-oss-specific failure modes:

- returns valid schema but overuses low confidence
- treats context as target evidence
- asks/hedges in fields instead of making the required structured decision
- summarizes narrative instead of coding atomic claims
- follows the most recent context section more than the target section

Those should be measured, not assumed.

## Prompt File Discipline

A1 prompts should live as files or deterministic Python builders, not as
untracked notebook strings.

Suggested future shape:

```text
a1_coding_research/
  prompts/
    README.md
    comment_coder_v0.1.md
    comment_coder_v0.2.md
    changelog.md
```

Each prompt version should record:

- what changed
- why it changed
- which failure class it targeted
- which sample/eval run tested it
- whether it was kept, rejected, or superseded

This mirrors the `dr-hiro` "tested vs predicted" firewall.

## Relationship To A2

A2 should receive only a prompt/schema pair that A1 has versioned and evaluated.

Before A2 pilot:

```text
[ ] prompt version exists as a file or deterministic builder
[ ] response model version exists
[ ] context renderer version exists
[ ] prompt-dev results reviewed row-by-row
[ ] holdout results reviewed
[ ] attribution leakage rate is under threshold
[ ] context ablation has been run or explicitly deferred
[ ] cheap model compared with stronger model
[ ] failure taxonomy updated from observed failures
[ ] prompt changelog written
```

If this checklist is incomplete, A2 can still do dry renders or tiny pilots, but
not large runs.

## Strong Recommendation

For A1, prompt engineering should begin with an **eval notebook/script**, not
with a polished prompt. The prompt should evolve from observed failures.

The first concrete A1 implementation should probably be:

1. select `seed_review`, `prompt_dev`, `gold_holdout`, and
   `adversarial_context` IDs
2. render context windows deterministically
3. draft `CommentCodingResult` Pydantic model
4. draft `comment_coder_v0.1`
5. run 25-50 examples through cheap model and stronger comparator
6. manually inspect failures
7. only then revise the prompt

The `dr-hiro` doctrine applies cleanly here: **the measurement instrument is the
product**.
