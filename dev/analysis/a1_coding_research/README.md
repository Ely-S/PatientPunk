# A1 Coding Research

This folder is for the research phase before large-scale LLM extraction over
the Reddit comment corpus.

A1 is meant to answer:

- what should we code or extract from each comment?
- how much context should a coding prompt receive?
- how do we prevent parent-comment claims from being attributed to the target
  comment author?
- which Rumi agent structure should we use?
- which models are good enough before we scale?
- what should the first reviewed sample and evaluation loop look like?

This folder contains notes, small ID-only sample manifests, prompt experiments,
and evaluation utilities. It should not contain full-corpus generated outputs or
a production batch runner.

Current research notes:

```text
notes/agent_folder_research.md
notes/a2_requirements_for_a1.md
notes/prompt_engineering_plan.md
```

The likely direction is to keep reusable Rumi agents in:

```text
dev/analysis/agents/
```

and keep numbered folders such as `a1_coding_research/` and
`a2_batch_extraction/` focused on stage-specific scripts, notes, samples, and
run orchestration.

## Implemented A1 Instrument

Reusable agent code now lives in:

```text
dev/analysis/agents/CommentCoderAgent/
dev/analysis/agents/_common/
```

The current A1 coding instrument is:

- schema: `comment_coding_v0.1`
- prompt: `comment_coder_v0.1`
- context renderer: `comment_context_prompt_v0.1`
- default cheap model: `openai/gpt-oss-120b`

The agent is intentionally no-tool because Rumi's structured-output path uses
`response_model`, and Rumi does not combine `response_model` with tools.

## Commands

Generate deterministic ID-only samples:

```powershell
python dev/analysis/a1_coding_research/scripts/select_samples.py --replace
```

Render a few sample contexts without calling a model:

```powershell
python dev/analysis/a1_coding_research/scripts/render_sample_contexts.py --sample prompt_dev --limit 5
```

Create a dry prompt-dev run under the ignored derived dataset folder:

```powershell
python dev/analysis/a1_coding_research/scripts/run_prompt_dev.py --sample prompt_dev --limit 5 --dry-render
```

Check that the OpenRouter key and model are reachable:

```powershell
python dev/analysis/a1_coding_research/scripts/run_prompt_dev.py --check-openrouter --model openai/gpt-oss-120b
```

Run a tiny live smoke test:

```powershell
python dev/analysis/a1_coding_research/scripts/run_prompt_dev.py --sample prompt_dev --limit 3 --live --model openai/gpt-oss-120b
```

Summarize the most recent A1 run:

```powershell
python dev/analysis/a1_coding_research/scripts/summarize_eval.py --latest --write
```

Live runs require `--limit`. Runs over 25 rows require
`--allow-large-live`. This keeps A1 in prompt-engineering mode instead of
accidentally becoming a batch pipeline. Live runs default to
`--max-attempts 2` because cheap OpenRouter models can occasionally return an
empty or truncated structured response.

## Output Locations

Tracked A1 artifacts:

```text
prompts/
samples/
evals/
scripts/
notes/
```

Ignored run outputs:

```text
dataset/covidlonghaulers_comments/derived/a1_coding_research/runs/
```

Sample files in `samples/` are ID-only. Rendered contexts and model outputs can
contain raw comment text, so they are written under `dataset/`, which is ignored
by git.

Before A2 can run beyond tiny pilots, A1 should hand it a versioned coding
instrument:

- a Pydantic response model and schema version
- a prompt version and prompt hash inputs
- a context rendering policy and default context limits
- skip rules for deleted, removed, too-short, unclear, and non-patient comments
- attribution rules and an audit rubric
- reviewed sample IDs and an evaluation baseline
- acceptable failure thresholds for structured validation, attribution leakage,
  low-confidence rows, and retry rates

Prompt engineering notes:

```text
notes/prompt_engineering_plan.md
```

This applies the local Claude `/prompt-engineering` skill and the `dr-hiro`
prompt-engineering guide corpus to A1. The key rule is that prompt changes
should be eval-gated: baseline, inspect row-level failures, add targeted
positive cues and literal examples, measure on the same frozen IDs, and only
then promote a prompt version for A2.
