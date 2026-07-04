# Evidence Reporting Research

Date: 2026-07-04

This note defines A4: the layer that turns A3-analyzed comment-coding outputs
into queryable evidence and human-facing reports.

## Sources Read

Local sources:

- `README.md`
- `dev/analysis/README.md`
- `dev/analysis/a3_result_analysis/README.md`
- `dev/analysis/a3_result_analysis/notes/a3_implementation_research.md`
- `dev/analysis/a3_result_analysis/notes/a2_smoke_output_review.md`
- `dev/analysis/a3_result_analysis/notes/normalization_and_codebook_strategy.md`
- `dev/analysis/a3_result_analysis/notes/audit_scoring_implementation_research.md`
- `variable_extraction/patientpunk/aggregate.py`
- `variable_extraction/patientpunk/cluster_prep.py`
- `variable_extraction/patientpunk/promote.py`
- `variable_extraction/patientpunk/pipeline.py`
- `variable_extraction/patientpunk/exporters/codebook.py`
- `dev/_trial_claude_check.json`
- `dev/_trial_ldn.json`
- `dev/_trial_ldn_real.json`

External reporting-method sources:

- COREQ, EQUATOR Network: https://www.equator-network.org/reporting-guidelines/coreq/
- PRISMA-ScR, EQUATOR Network: https://www.equator-network.org/reporting-guidelines/prisma-scr/
- GRADE-CERQual: https://www.cerqual.org/
- Wilson interval helper already in repo: `dev/eval/wilson.py`

## A4 Role

A4 is not model extraction and not audit scoring. It is the reporting and
decision-support layer that consumes A3 artifacts.

The clean boundary:

```text
A1: define and prompt-engineer the coding instrument
A2: run the instrument and store results
A3: validate, audit, score, normalize, and summarize results
A4: publish queryable evidence marts and reports with caveats
```

A4 should never make an aggregate claim directly from raw A2 output. It should
require A3's analysis manifest, quality report, normalization manifest, and
score outputs.

## Intended Audience

A4 has three audiences:

1. Internal pipeline reviewers deciding whether A2 can scale.
2. Researchers exploring self-reported long-COVID patterns.
3. Patient-facing or public-facing readers who need careful, non-clinical
   summaries.

The same facts can serve all three, but the language must differ. Internal
reports can expose operational details. Public-facing reports need clear
limitations and no treatment advice.

## A4 Outputs

A4 should produce a report package per A3-analyzed run or run family:

```text
dataset/covidlonghaulers_comments/derived/a4_evidence_reporting/reports/<report_id>/
  report_manifest.json
  evidence_mart.sqlite
  finding_cards.jsonl
  finding_cards.csv
  tables/
    claim_counts_by_label.csv
    symptom_treatment_outcome_counts.csv
    monthly_claim_trends.csv
    context_and_quality_caveats.csv
  quotes/
    quote_bank.csv
    quote_review_template.csv
  report.md
  limitations.md
  methods.md
  provenance.md
```

`evidence_mart.sqlite` should be the query surface for downstream notebooks and
interactive tools. CSV/Markdown files are generated views, not the only source.

## Finding Cards

The core A4 unit should be a "finding card": one aggregate finding with its
denominators, uncertainty, audit status, and linked evidence.

Suggested fields:

```text
finding_id
report_id
finding_type
title
plain_language_summary
claim_type
canonical_label
analysis_bucket
cohort_filter_json
n_claims
n_comments
n_authors_available
n_audited_comments
n_audited_claims
quality_status
confidence_label
wilson_interval_json
rule_of_three_note
representative_quote_ids_json
limitations_json
source_a3_analysis_manifest
source_a2_run_ids_json
created_at_utc
```

A finding card is reportable only if A3 can trace it back to normalized claim
rows, scorecards, and source run manifests.

## Confidence Labels

A4 should not use clinical evidence labels such as "proven" or "effective".

Recommended labels:

```text
not_reportable
exploratory
weak_signal
suggestive_signal
stable_descriptive_pattern
```

These labels combine:

- row count and denominator size
- audit coverage
- audit error rates
- normalized-label review status
- coherence across strata
- risk of context leakage or unsupported evidence
- selection and platform limitations

This is inspired by GRADE-CERQual's emphasis on confidence in qualitative
synthesis findings, but A4 should not claim to implement CERQual formally until
the full qualitative review process exists.

## Methods Reporting

A4 should generate `methods.md` for every report. It should include:

- dataset snapshot
- subreddit/source and date range
- comment-only limitation
- A1 schema and prompt versions
- A2 run IDs and model IDs
- A3 normalization and audit versions
- validation checks passed or failed
- audit sample size and scoring thresholds
- quote selection method
- limitations and non-clinical-use statement

COREQ and PRISMA-ScR are not perfect fits because this pipeline is not an
interview study or a formal scoping review, but they correctly push A4 toward
transparent methods, context, analysis, interpretation, and limitations.

## Report Types

First useful report types:

```text
run_quality_brief
claim_distribution_brief
symptom_pattern_brief
treatment_experience_brief
context_sensitivity_brief
scale_gate_brief
```

Later report types:

```text
cohort_comparison_report
time_trend_report
patient_quote_packet
public_plain_language_summary
interactive_query_export
```

## Research Takeaway

A4 should be conservative by design. It should make it easy to ask useful
questions over A3-normalized outputs, but hard to publish a count, percentage,
or quote without provenance, denominator clarity, audit status, and limitations.

