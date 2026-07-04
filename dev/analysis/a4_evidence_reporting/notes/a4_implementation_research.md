# A4 Implementation Research

Date: 2026-07-04

This note translates the A4 research into a concrete first implementation shape.
A4 should consume A3 analysis packages and produce reproducible evidence marts,
finding cards, and report documents without re-running A1/A2 model calls.

## Sources Read

Local sources:

- `dev/analysis/a4_evidence_reporting/README.md`
- `dev/analysis/a4_evidence_reporting/notes/evidence_reporting_research.md`
- `dev/analysis/a4_evidence_reporting/notes/a3_to_a4_contract.md`
- `dev/analysis/a4_evidence_reporting/notes/query_and_aggregation_design.md`
- `dev/analysis/a4_evidence_reporting/notes/reporting_guardrails.md`
- `dev/analysis/a3_result_analysis/README.md`
- `dev/analysis/a3_result_analysis/analysis.py`
- `dev/analysis/a3_result_analysis/reportability.py`
- `dev/analysis/a3_result_analysis/score.py`
- `dev/analysis/a3_result_analysis/notes/a4_requirements_for_a3.md`
- `dataset/covidlonghaulers_comments/derived/a3_result_analysis/runs/a3_openrouter_eval_20260704T190833Z_prompt_dev_3/analysis_manifest.json`
- `dataset/covidlonghaulers_comments/derived/a3_result_analysis/runs/a3_openrouter_eval_20260704T190833Z_prompt_dev_3/denominator_summary.csv`
- `dataset/covidlonghaulers_comments/derived/a3_result_analysis/runs/a3_openrouter_eval_20260704T190833Z_prompt_dev_3/reportability_summary.csv`
- `dataset/covidlonghaulers_comments/derived/a3_result_analysis/runs/a3_openrouter_eval_20260704T190833Z_prompt_dev_3/quote_candidates.csv`
- `variable_extraction/patientpunk/aggregate.py`
- `variable_extraction/patientpunk/cluster_prep.py`
- `variable_extraction/patientpunk/promote.py`
- `variable_extraction/patientpunk/exporters/codebook.py`
- `README_AGENTS.md`
- `src/agents/_common/packet.py`
- `src/agents/_common/validate.py`
- `src/agents/TheTrialAgent/synthesize.py`
- `eval/trial/rubric.py`

External sources checked:

- COREQ, EQUATOR Network: https://www.equator-network.org/reporting-guidelines/coreq/
- PRISMA-ScR project summary: https://knowledgetranslation.net/project/preferred-reporting-items-for-systematic-reviews-and-meta-analyses-extension-for-scoping-reviews/
- GRADE-CERQual home/guidance: https://www.cerqual.org/
- GRADE-CERQual introduction paper: https://link.springer.com/article/10.1186/s13012-017-0688-3
- AoIR internet research ethics: https://aoir.org/ethics/

## A4 Boundary

A4 should be a report builder, not an extraction layer.

It should:

- load one or more A3 analysis directories
- verify A3 manifests and file hashes
- build a disposable evidence mart
- generate deterministic finding cards
- select private-review quote candidates
- render methods, limitations, provenance, and report Markdown
- validate that every number, quote, and caveat traces to a source artifact

It should not:

- call A1 extraction models
- change A2/A3 source artifacts
- infer missing denominators
- upgrade reportability labels without A3 audit/normalization evidence
- publish raw quotes that have not passed review/redaction

## First Slice

The first A4 implementation should be deliberately narrow:

```text
Input:
  one A3 analysis directory

Output:
  one private_review report package

Report type:
  claim_distribution_brief

Allowed confidence:
  not_reportable or exploratory only, unless reviewed A3 audit/normalization
  artifacts are supplied
```

For the current A3 smoke run:

```text
comment_rows = 3
claim_rows_normalized = 17
quote_candidates = 17
validation_ok = true
n_comments_audited = 0
n_claims_audited = 0
reportability gate = proceed_to_more_audit
normalization_review_status = unreviewed
```

Therefore A4 should produce a private exploratory report, not a public summary
or stable evidence claim.

## Proposed Package Layout

```text
dev/analysis/a4_evidence_reporting/
  __init__.py
  common.py              # paths, JSON/CSV helpers, hashing
  loaders.py             # load and validate A3 analysis directories
  manifest.py            # report manifest creation and source verification
  mart.py                # evidence_mart.sqlite builder
  findings.py            # finding-card construction
  confidence.py          # report confidence/reportability policy
  quotes.py              # quote-bank and review-template generation
  render.py              # deterministic Markdown rendering
  validate.py            # report package validation
  scripts/
    build_report.py
    build_mart.py
    make_finding_cards.py
    validate_report.py
```

Keep these modules boring and deterministic. The older Trial agent proves that
patient-facing language can use LLMs later, but the first A4 implementation
should establish provenance, marts, and deterministic report rendering first.

## Proposed CLI

Build a complete private-review report:

```powershell
python dev/analysis/a4_evidence_reporting/scripts/build_report.py `
  --a3 dataset/covidlonghaulers_comments/derived/a3_result_analysis/runs/<a3_run_id> `
  --report-type claim_distribution_brief `
  --mode private_review
```

Build only the evidence mart:

```powershell
python dev/analysis/a4_evidence_reporting/scripts/build_mart.py `
  --a3 dataset/covidlonghaulers_comments/derived/a3_result_analysis/runs/<a3_run_id>
```

Validate a generated package:

```powershell
python dev/analysis/a4_evidence_reporting/scripts/validate_report.py `
  --report dataset/covidlonghaulers_comments/derived/a4_evidence_reporting/reports/<report_id>
```

## Report Package Layout

```text
dataset/covidlonghaulers_comments/derived/a4_evidence_reporting/reports/<report_id>/
  report_manifest.json
  evidence_mart.sqlite
  finding_cards.jsonl
  finding_cards.csv
  evidence_packet.json
  tables/
    claim_counts_by_label.csv
    claim_counts_by_type.csv
    monthly_claim_counts.csv
    reportability_by_label.csv
    source_denominators.csv
  quotes/
    quote_bank_private.csv
    quote_review_template.csv
  report.md
  methods.md
  limitations.md
  provenance.md
  validation_report.json
```

`evidence_packet.json` should be the frozen source for any narrative rendering.
It should contain finding IDs, denominator IDs, quote IDs, caveat IDs, source
manifest hashes, and reportability constraints. Reports should render from this
packet, not from ad hoc table reads.

## Evidence Mart Tables

Minimum SQLite tables:

```text
report_manifest
source_a3_analyses
source_files
denominators
comments
claims
claim_label_frequency
reportability
quote_bank
finding_cards
caveats
```

Useful later tables:

```text
audit_metrics
audit_disagreements
normalization_rules
monthly_claim_counts
cohort_filters
selected_quotes
```

The mart is derived and disposable. Rebuilding it from A3 artifacts should be
the normal workflow.

## Finding Card Policy

A4 should create one finding card per aggregate row that might appear in a
report. A card is not automatically reportable.

The first finding types:

```text
claim_label_frequency
claim_type_distribution
monthly_claim_trend
context_sensitive_claim_queue
unreviewed_normalization_queue
```

Treatment-effect finding cards should wait. The current A1 schema can identify
medication/treatment claims, but it does not yet model treatment, symptom,
outcome direction, side effect, dose, and timing as a first-class relation.

## Confidence Policy

A4 confidence is not model confidence.

Inputs to report confidence:

- A3 validation status
- source row counts and denominators
- A3 gate decision
- audit coverage and Wilson intervals, when present
- normalization review status
- quote review/redaction status
- evidence-source violations
- coherence across strata or repeated runs
- missing author/patient denominator

Default mapping:

```text
A3 validation failed -> not_reportable
no audit -> exploratory
normalization unreviewed -> exploratory
quote not reviewed -> no public quote
A3 gate proceed_to_more_audit -> exploratory or weak_signal at most
A3 gate proceed + audit passes + accepted normalization -> suggestive_signal possible
stable_descriptive_pattern -> requires repeated evidence, accepted labels, and enough audit coverage
```

## Lessons From Older Code

`cluster_prep.py` is relevant because it separates carry-along analysis fields
from clusterable features and reports readiness metrics before clustering. A4
should apply the same discipline before reporting: derive an evidence mart, then
make readiness/reportability explicit.

`promote.py` is relevant because it requires opt-in promotion of discovered
fields. A4 should mirror that for reportable findings: exploratory aggregates do
not become report findings unless a gate promotes them.

`exporters/codebook.py` is relevant because every output surface needs a
data dictionary. A4 should ship its own codebook for finding cards, report
manifest, quote bank, and mart tables.

`aggregate.py` is relevant but also a warning. It aggregates by author for older
pipeline records. The current A2/A3 comment-coding outputs do not include stable
author hashes, so A4 must not claim patient-level or author-level denominators
until A2 explicitly exports them.

## Acceptance Criteria For First Implementation

The first A4 implementation is acceptable when it can:

- build a report package from one A3 analysis directory
- verify source file hashes against `analysis_manifest.json`
- create `evidence_mart.sqlite`
- create finding cards with stable IDs and source claim IDs
- render `report.md`, `methods.md`, `limitations.md`, and `provenance.md`
- keep all quotes private unless review/redaction allows publication
- validate every rendered number against the evidence packet
- mark the current A3 smoke run as exploratory, not reportable
- pass unit tests on a synthetic A3 package and the real A3 smoke package

## Pushbacks To A3/A2

A4 can start now, but better report packages will require:

- A2/A3 author hash export if any patient-level denominator is desired
- A3 score outputs stored under a predictable `scores/` path
- A3 `gate_decision.json` even when no audit labels exist
- A3 quote review/redaction workflow or a handoff template for A4
- A3 accepted normalization maps for common labels
- A2 root post/submission data if top-level comment interpretation matters

## Research Takeaway

A4 should initially be a deterministic evidence packaging layer. The valuable
first product is not a polished public report; it is a verifiable report package
where every count, denominator, quote candidate, confidence label, and caveat is
traceable to A3 and therefore back to A2/A1.
