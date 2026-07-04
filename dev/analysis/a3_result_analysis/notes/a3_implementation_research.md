# A3 Implementation Research

Date: 2026-07-04

This note turns the existing A3 research into an implementable downstream
analysis stage for A2 comment-coding outputs.

## Local Sources Read

- `dev/analysis/a3_result_analysis/README.md`
- `dev/analysis/a3_result_analysis/notes/downstream_requirements_for_a2.md`
- `dev/analysis/a3_result_analysis/notes/analysis_export_research.md`
- `dev/analysis/a3_result_analysis/notes/audit_scoring_plan.md`
- `dev/analysis/a2_batch_extraction/README.md`
- `dev/analysis/a2_batch_extraction/runner.py`
- `dev/analysis/a2_batch_extraction/storage.py`
- `dataset/covidlonghaulers_comments/derived/a2_batch_extraction/runs/comment_coding/20260704T055236Z_prompt_dev_3/exports/export_manifest.json`
- `variable_extraction/patientpunk/evaluate.py`
- `variable_extraction/patientpunk/normalize.py`
- `variable_extraction/patientpunk/cluster_prep.py`
- `variable_extraction/patientpunk/scripts/records_to_csv.py`
- `variable_extraction/patientpunk/scripts/make_codebook.py`
- `variable_extraction/patientpunk/qualitative_standards.py`
- `dev/eval/wilson.py`

## A3 Role

A3 should answer two questions after each A2 run:

1. Can this run be trusted enough to advance to the next gate?
2. What analysis-ready tables, summaries, and normalized labels can be produced
   without re-running the model?

A3 should not be another extraction agent in the first slice. It should consume
A2 run databases and exports, then produce deterministic analysis artifacts.
If A3 later uses a strong model, that should be a separate silver-reference or
triage path, not the default A3 core.

## Inputs

A3 should support two equivalent inputs:

```text
--run <a2_run_dir>
--exports <a2_run_dir>/exports
```

The preferred source of truth is the A2 SQLite run DB when present. Exports are
the interoperability surface for notebooks, spreadsheets, and external review.

Minimum required input files from A2:

```text
run.sqlite
exports/export_manifest.json
exports/run_manifest.json
exports/run_report.json
exports/comment_rows.csv
exports/claim_rows.csv
exports/attempts.csv
exports/results.jsonl
```

Optional but expected for audit:

```text
exports/audit_comment_template.csv
exports/audit_claim_template.csv
```

## Outputs

A3 generated outputs should stay outside `dev/analysis/`, under ignored derived
data paths:

```text
dataset/covidlonghaulers_comments/derived/a3_result_analysis/runs/<a2_run_id>/
```

Recommended first output set:

```text
analysis_manifest.json
manifest.json
run_quality_report.json
run_quality_report.md
comment_distribution.csv
claim_distribution.csv
claim_label_frequency.csv
context_quality_summary.csv
attempt_quality_summary.csv
claim_rows_normalized.csv
normalization_map.csv
normalization_manifest.json
denominator_summary.csv
quote_candidates.csv
reportability_summary.csv
codebook.md
codebook.csv
```

When audit labels are supplied:

```text
scores/comment_scorecard.csv
scores/claim_scorecard.csv
scores/metric_summary.json
scores/metric_summary.md
scores/disagreement_rows.csv
scores/gate_decision.json
```

## Proposed Code Shape

Use small deterministic modules under `dev/analysis/a3_result_analysis/`:

```text
common.py            # paths, CSV/JSON helpers, manifest/hash helpers
loaders.py           # load A2 run DB and exported CSVs
validate.py          # row-count/hash/schema checks
summaries.py         # distributions and run-quality summaries
normalization.py     # claim-label cleaning and mapping application
  codebook.py          # table/column data dictionary generation
  audit.py             # audit-template loading and label validation
  score.py             # comment/claim metrics with Wilson intervals
  reportability.py     # A4-facing reportability labels and gate constraints
scripts/
  validate_a2_run.py
  summarize_run.py
  normalize_claim_labels.py
  make_codebook.py
  score_audit.py
```

Do not put notebooks in the critical path. Notebooks can consume A3 outputs
later, but A3 should be runnable end to end from scripts.

## First Implementation Slice

The first A3 implementation should work on the A2 tiny live run
`20260704T055236Z_prompt_dev_3`.

Suggested command flow:

```powershell
python dev/analysis/a3_result_analysis/scripts/validate_a2_run.py --run <a2_run_dir>
python dev/analysis/a3_result_analysis/scripts/summarize_run.py --run <a2_run_dir>
python dev/analysis/a3_result_analysis/scripts/normalize_claim_labels.py --run <a2_run_dir>
python dev/analysis/a3_result_analysis/scripts/make_codebook.py --run <a2_run_dir>
python dev/analysis/a3_result_analysis/scripts/build_reportability.py --run <a2_run_dir>
```

When reviewed audit templates exist:

```powershell
python dev/analysis/a3_result_analysis/scripts/score_audit.py `
  --run <a2_run_dir> `
  --audit-comments <reviewed_comment_labels.csv> `
  --audit-claims <reviewed_claim_labels.csv>
```

## Validation Checks

A3 should fail fast if:

- `export_manifest.json` is missing.
- exported file hashes do not match the manifest.
- `comment_rows.csv` row count does not match A2 work items.
- `claim_rows.csv` row count does not match A2 `claim_rows`.
- `results.jsonl` row count does not match A2 successful/deterministic results.
- any claim has `evidence_source != target_comment`.
- any `claim_id` is duplicated.
- a row has `status=succeeded` but no matching result row.
- a codeable result has `claim_count=0`.

A3 should warn, not fail, if:

- a run is dry-only and has no results yet.
- audit templates are missing.
- claim-label cardinality is high.
- a tiny eval has zero observed failures but too few audited rows to conclude
  low failure risk.
- A4-facing quote candidates are generated with `redaction_status=not_reviewed`.

## Summaries

A3 should produce both machine-readable JSON and CSV summary tables.

Run-quality summary:

- structured success rate
- retry rate
- final failure rate
- deterministic skip count
- token/cost totals
- latency distribution
- evidence-source violation count
- claim count distribution

Comment distribution:

- by `year_month`
- by `parent_kind`
- by `selection_bucket`
- by `status`
- by `is_codeable`
- by `skip_reason`
- by `used_context`
- by `attribution_confidence`
- by body-length buckets

Claim distribution:

- by `claim_type`
- by `normalized_label`
- by `experiencer`
- by `assertion`
- by `confidence`
- by `year_month`
- by `parent_kind`
- by `used_context`

Attempt quality:

- attempts per row
- error types
- provider/upstream counts from `metadata_json`
- token and cost summaries
- latency by model/upstream

A4-facing summaries:

- denominator summary with named denominators and source filters
- quote candidate table keyed by claim ID
- reportability summary by claim label and finding unit
- gate decision when audit labels exist

## Relationship To Existing PatientPunk Code

`patientpunk.evaluate` is useful for the general idea of scoring a candidate
against a reference, but A3 needs custom scoring because comment coding has two
units: comments and claims.

`patientpunk.normalize` is the right pattern for A3: keep raw model output and
add versioned canonical columns. Do not overwrite `normalized_label`.

`make_codebook.py` is the right pattern for A3 codebooks: include field
descriptions, source, allowed values, coverage, and example values.

`dev/eval/wilson.py` is the right pattern for metrics: report Wilson intervals
and rule-of-three bounds, especially during small gates.

## Research Takeaway

A3 should be a deterministic analysis and measurement layer. Its first useful
version should validate A2 exports, summarize the tiny live run, normalize
claim labels without losing raw values, generate a codebook, produce explicit
denominators and quote candidates for A4, and score reviewed audit templates
with uncertainty intervals.
