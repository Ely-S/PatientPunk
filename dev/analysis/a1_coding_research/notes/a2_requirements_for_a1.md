# A2 Requirements For A1

Date: 2026-07-03

This note refines A1 after researching the future A2 batch stage. A2 will be the
large-scale runner, so A1 must produce more than a promising prompt. It must
produce a versioned, evaluated coding instrument that A2 can run and audit.

## Core Refinement

A1 should be judged by whether it gives A2 enough information to run safely.

That means A1's deliverable is not:

```text
a prompt that seems good on a few examples
```

It is:

```text
a versioned schema + prompt + context policy + eval baseline + audit rubric
```

## A1 Outputs Required By A2

A1 should hand A2 these artifacts:

- `task_name`: short stable name, for example `comment_coding`.
- `schema_name`: stable schema family name.
- `schema_version`: explicit version, for example `comment_coding_v0.1`.
- `response_model`: Pydantic model used with Rumi `response_model`.
- `prompt_name`: stable prompt family name.
- `prompt_version`: explicit version.
- `prompt_hash_inputs`: list of files/strings included in the prompt hash.
- `context_renderer_version`: explicit version for how context is rendered.
- `context_limits`: default ancestor, previous sibling, and previous thread
  limits.
- `skip_rules`: deleted, removed, too short, non-patient, unclear, not English,
  moderation/meta, and other.
- `attribution_rules`: target-only extraction rules and context-use limits.
- `normalization_rules`: controlled value canonicalization.
- `review_sets`: IDs for seed review, prompt dev, and gold holdout.
- `eval_metrics`: structured-output validity, attribution accuracy, recall,
  over-extraction, skip correctness, context-use correctness.
- `acceptance_thresholds`: the largest acceptable error rates before A2 scaleup.
- `audit_rubric`: how humans or an audit agent judge A2 outputs.
- `model_plan`: cheap model, stronger comparator, fallback model.
- `expected_distribution`: pilot-rate expectations for codeable rows, skipped
  rows, claim counts, context-use rate, and low-confidence rate.

If these are not available, A2 should only do dry renders or tiny experiments.

## A1 Folder Implications

A1 should grow toward this shape:

```text
a1_coding_research/
  README.md
  notes/
    agent_folder_research.md
    a2_requirements_for_a1.md
    sampling_plan.md
    codebook_design.md
    attribution_rules.md
    prompt_eval_plan.md
    model_bakeoff.md
  samples/
    README.md
    seed_review_ids.jsonl
    prompt_dev_ids.jsonl
    gold_holdout_ids.jsonl
  evals/
    README.md
    run_manifest_template.json
    metrics_definition.md
  prompts/
    README.md
    comment_coder_v0.1.md
    changelog.md
```

The files under `samples/` should usually be ID-only. Rendered text can be
recreated from `comments.sqlite` when needed.

## A1 Decisions That Block A2

A2 cannot run a meaningful batch until A1 decides:

- What is the first coding task?
- What target comments are eligible?
- What counts as a patient-authored self-report?
- How should deleted/removed target comments be handled?
- How should deleted/removed parent context be represented?
- Which context sections can influence extraction?
- What is evidence allowed to quote?
- Is context evidence ever allowed, or only target evidence?
- What controlled vocabularies are required?
- Which fields may be multi-valued?
- Which fields require confidence?
- Which fields require a direct quote?
- What should happen when the target says only "same" or "me too"?
- What should happen when the target discusses another person?
- What output distribution is plausible?

These decisions belong in A1 notes and prompts before A2 runs at scale.

## A1 Evaluation Gates

A1 should create a small eval loop before A2 pilot runs:

1. Render context windows for a seed set.
2. Manually inspect enough rows to understand the data shape.
3. Draft a schema and prompt.
4. Run a cheap model on prompt-dev IDs.
5. Run a stronger model on the same IDs.
6. Compare outputs against manual review or adjudicated examples.
7. Revise schema/prompt.
8. Freeze a gold holdout set.
9. Run the final candidate prompt on the holdout.
10. Write a short metrics report.

Possible A1 thresholds before A2 pilot:

```text
structured_output_validity >= 99%
target_attribution_accuracy >= 95% on reviewed examples
parent_context_leakage <= 2% on reviewed examples
deleted_removed_skip_accuracy >= 99%
unexplained_low_confidence_rate <= 10%
prompt_too_large_rate == 0% on sample
```

The exact thresholds can change after the first review, but A1 should define
them explicitly.

## Prompt Requirements From A2

A2 needs prompts to be stable and hashable.

Avoid ad hoc notebooks with invisible prompt edits. Put prompt text in a file or
a deterministic Python function whose inputs can be hashed.

Every prompt version should specify:

- response model version
- qualitative standards text used
- target/context formatting
- skip policy
- attribution policy
- confidence scale
- examples, if any
- changelog from the previous prompt version

## Context Requirements From A2

A2 needs context rendering to be deterministic.

A1 should define:

- section order
- labels for target, ancestors, previous siblings, and previous thread comments
- max body characters per comment
- max total prompt characters or tokens
- handling for missing root submissions
- handling for missing parent comments
- handling for duplicate comments across context sections
- whether scores/authors/dates are included
- whether permalink/source line/comment ID are included

The context renderer should produce the same string for the same database row,
context settings, and renderer version.

## Audit Requirements From A2

A1 should define an audit rubric before A2 large runs.

Minimum audit labels:

- correct
- wrong_skip
- missed_claim
- over_extracted_claim
- parent_context_leakage
- wrong_experiencer
- wrong_temporality
- wrong_normalization
- unsupported_evidence
- confidence_too_high
- ambiguous_but_not_marked

For A2, audit samples should over-sample risky rows: context-used rows,
low-confidence rows, deep replies, very short replies, high-claim rows, failed
rows, and rows near prompt-size limits.

## Strong Recommendation

A1 should maintain a small "readiness checklist" before A2 scaleup. A2 should
not be allowed to run large batches when the checklist is incomplete.

Suggested checklist:

```text
[ ] schema_version chosen
[ ] prompt_version chosen
[ ] context_renderer_version chosen
[ ] sample IDs selected
[ ] gold holdout frozen
[ ] skip rules written
[ ] attribution rules written
[ ] audit rubric written
[ ] pilot metrics report written
[ ] model comparison completed
[ ] A2 run manifest fields confirmed
```
