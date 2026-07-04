# A3 Result Analysis

This folder is the downstream analysis layer for A2 comment-coding batch outputs.
It validates an A2 export, creates analysis-ready tables, prepares review and
reporting artifacts, and can run a small OpenRouter end-to-end eval.

A3 is meant to answer:

- how do we audit and score A2 outputs after a run?
- how do we export comment-level and claim-level tables for analysis?
- how do we compare cheap-model outputs against gold or strong-model references?
- how do we normalize high-cardinality claim labels without losing provenance?
- how do we aggregate comment-level claims into post, thread, author, or time
  summaries?
- what result shapes does A2 need to store so later analysis is not blocked?

A3 is downstream of A2. If A3 needs an identifier, metadata field, export, or
audit record that A2 does not store, that requirement should be pushed back into
`a2_batch_extraction/` before A2 runs at scale.

## Main Commands

Validate an A2 run export:

```powershell
python dev/analysis/a3_result_analysis/scripts/validate_a2_run.py --run dataset/covidlonghaulers_comments/derived/a2_batch_extraction/runs/comment_coding/<run_id>
```

Build the full A3 analysis package for an A2 run:

```powershell
python dev/analysis/a3_result_analysis/scripts/run_analysis.py --run dataset/covidlonghaulers_comments/derived/a2_batch_extraction/runs/comment_coding/<run_id>
```

Write only summaries:

```powershell
python dev/analysis/a3_result_analysis/scripts/summarize_run.py --run dataset/covidlonghaulers_comments/derived/a2_batch_extraction/runs/comment_coding/<run_id>
```

Write only label-normalization draft outputs:

```powershell
python dev/analysis/a3_result_analysis/scripts/normalize_claim_labels.py --run dataset/covidlonghaulers_comments/derived/a2_batch_extraction/runs/comment_coding/<run_id>
```

Write only codebook outputs:

```powershell
python dev/analysis/a3_result_analysis/scripts/make_codebook.py --run dataset/covidlonghaulers_comments/derived/a2_batch_extraction/runs/comment_coding/<run_id>
```

Write reportability summaries:

```powershell
python dev/analysis/a3_result_analysis/scripts/build_reportability.py --run dataset/covidlonghaulers_comments/derived/a2_batch_extraction/runs/comment_coding/<run_id>
```

Score manually reviewed audit CSVs:

```powershell
python dev/analysis/a3_result_analysis/scripts/score_audit.py --audit-comments <audit_comments.csv> --audit-claims <audit_claims.csv> --output-dir <score_output_dir>
```

Run a tiny OpenRouter connectivity check:

```powershell
python dev/analysis/a3_result_analysis/scripts/eval_openrouter.py --model openai/gpt-4o-mini --connectivity
```

Run A1 -> A2 -> A3 on three prompt-development comments:

```powershell
python dev/analysis/a3_result_analysis/scripts/eval_openrouter.py --model openai/gpt-4o-mini --sample prompt_dev --limit 3 --max-attempts 2
```

## Output Layout

The default full-analysis output path is:

```text
dataset/covidlonghaulers_comments/derived/a3_result_analysis/runs/<a2_run_id>/
```

The full package currently writes:

```text
a2_validation_report.json
analysis_manifest.json
run_quality_report.json
run_quality_report.md
comment_distribution.csv
claim_distribution.csv
claim_label_frequency.csv
context_quality_summary.csv
attempt_quality_summary.csv
denominator_summary.csv
claim_rows_normalized.csv
normalization_map.csv
normalization_manifest.json
quote_candidates.csv
codebook.csv
codebook.md
reportability_summary.csv
```

OpenRouter eval outputs go under:

```text
dataset/covidlonghaulers_comments/derived/a3_result_analysis/openrouter_evals/<eval_id>/
```

Each structured eval also creates an A2 run under A2's run root and a normal A3
analysis package under A3's run root.

## Model Notes

The current Rumi structured-output path depends on provider support for the
Pydantic JSON schema emitted by A1. In smoke testing:

- `openai/gpt-4o-mini` completed the three-comment A1 -> A2 -> A3 eval.
- `anthropic/claude-haiku-4.5` reached OpenRouter, but failed structured output
  because the provider rejected the schema's integer `minimum` keyword.
- `openai/gpt-oss-120b` reached OpenRouter, but the structured eval was too slow
  or hung on the first live item during this run.

Current research notes:

```text
notes/downstream_requirements_for_a2.md
notes/analysis_export_research.md
notes/audit_scoring_plan.md
notes/a3_implementation_research.md
notes/a2_smoke_output_review.md
notes/normalization_and_codebook_strategy.md
notes/audit_scoring_implementation_research.md
notes/a4_requirements_for_a3.md
```

Generated analysis outputs should stay under ignored dataset-derived paths, not
inside `dev/analysis/`.
