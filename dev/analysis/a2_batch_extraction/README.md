# A2 Batch Extraction

A2 is the batch execution layer for the A1 `CommentCoderAgent`. It turns frozen
sample IDs or small SQL selections into resumable SQLite run ledgers, executes
dry renders or tiny live Rumi/OpenRouter runs, and exports A3-ready comment and
claim tables.

The implementation intentionally starts with a safe first slice. It supports
small dry and live runs, exports, audit templates, retry recording, and
OpenRouter eval. It does not try to be a full-corpus scheduler yet.

## Command Flow

Create a small run from the frozen A1 prompt-development sample:

```powershell
python dev/analysis/a2_batch_extraction/scripts/create_run.py --sample prompt_dev --limit 25
```

The command prints the run directory under:

```text
dataset/covidlonghaulers_comments/derived/a2_batch_extraction/runs/comment_coding/<run_id>/
```

Dry-render the selected rows:

```powershell
python dev/analysis/a2_batch_extraction/scripts/run_batch.py --run <run_dir> --dry-render --limit 25
```

Inspect the ledger:

```powershell
python dev/analysis/a2_batch_extraction/scripts/inspect_run.py --run <run_dir>
```

Run a tiny live structured-output smoke test:

```powershell
python dev/analysis/a2_batch_extraction/scripts/run_batch.py --run <run_dir> --live --limit 5 --workers 1 --max-attempts 2
```

Summarize and export:

```powershell
python dev/analysis/a2_batch_extraction/scripts/summarize_run.py --run <run_dir>
python dev/analysis/a2_batch_extraction/scripts/export_run.py --run <run_dir>
```

Generate audit templates:

```powershell
python dev/analysis/a2_batch_extraction/scripts/select_audit_sample.py --run <run_dir> --limit-comments 25 --limit-claims 50
```

Check OpenRouter connectivity:

```powershell
python dev/analysis/a2_batch_extraction/scripts/eval_openrouter.py --model openai/gpt-oss-120b --connectivity
```

Run the end-to-end tiny OpenRouter structured eval:

```powershell
python dev/analysis/a2_batch_extraction/scripts/eval_openrouter.py --model openai/gpt-oss-120b --sample prompt_dev --limit 3 --max-attempts 2
```

## Run Ledger

Each run stores primary state in:

```text
run.sqlite
```

The core tables are:

```text
run_manifest
work_items
attempts
results
claim_rows
rendered_inputs
audit_comment_labels
audit_claim_labels
```

`results` keeps the validated A1 structured output. `claim_rows` expands those
outputs into one row per extracted target-author claim. JSONL and CSV files are
exports, not the source of truth.

## Exports

`export_run.py` writes:

```text
exports/run_manifest.json
exports/run_report.json
exports/comment_rows.csv
exports/claim_rows.csv
exports/failed_items.csv
exports/attempts.csv
exports/results.jsonl
exports/audit_comment_template.csv
exports/audit_claim_template.csv
exports/export_manifest.json
```

The export manifest records file hashes and row counts so A3 can detect changed
outputs.

## Guardrails

Live runs require `--limit`. Runs over 25 rows require `--allow-large-live`.
The first live runner supports `--workers 1` only. This keeps A2 in controlled
eval mode until A1/A3 quality gates are ready.

A2 deterministically skips exact `[removed]` and `[deleted]` target comments by
writing schema-valid skipped results. Early gate runs should still include a
small removed/deleted sample through the model occasionally to confirm prompt
alignment.

## Notes

Current research and design notes:

```text
notes/batch_pipeline_research.md
notes/a1_to_a2_contract.md
notes/runner_storage_design.md
notes/scaleup_eval_plan.md
```

A2 is downstream of A1. If A2 needs something that A1 has not defined, that
requirement should be pushed back into `a1_coding_research/` before any large
run is attempted.

A2 is upstream of A3 result analysis. If A3 needs comment-level exports,
claim-level rows, audit labels, or provenance fields, A2 should store those in
the run ledger before scaleup.
