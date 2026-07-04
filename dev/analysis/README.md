# Analysis Pipeline

`dev/analysis/` is the local development home for the staged
`r/covidlonghaulers` Reddit comment analysis pipeline.

The pipeline is organized as numbered stages:

```text
A0  Extraction and context database
A1  Comment-coding prompt/schema/agent
A2  Batch extraction runner
A3  Result analysis, validation, normalization, audit scoring
A4  Evidence reporting, marts, finding cards, private reports
Cluster  Optional post-A4 exploratory comment clustering
```

Generated data belongs under `dataset/covidlonghaulers_comments/derived/` and
is intentionally ignored by git. Do not commit raw Reddit exports, split JSONL
chunks, SQLite run databases, A2/A3/A4 derived packages, clustering outputs,
rendered model inputs, or live model outputs.

## What The Pipeline Does To The Data

The pipeline keeps the raw Reddit export as the immutable source and builds
regenerable derived layers around it. Each stage narrows, annotates, validates,
or packages the data without overwriting upstream artifacts.

```text
raw Reddit JSONL
  -> A0 split JSONL chunks + browsing indexes + comments.sqlite
  -> A1 rendered target-comment prompts + structured comment-coding schema
  -> A2 resumable run ledger + model attempts + validated structured results
  -> A2 exports: comment rows, claim rows, attempts, audit templates, manifests
  -> A3 validated/normalized analysis tables + denominators + quote candidates
  -> A4 evidence mart + finding cards + frozen evidence packet + private report
  -> optional cluster outputs from the A4 mart + A0 raw comment bodies
```

A0 changes the physical shape of the source data, not its meaning. It streams
the giant JSONL export into smaller full-record JSONL chunks, writes compact CSV
indexes for browsing, and builds `comments.sqlite` so code can look up a target
comment, ancestors, siblings, prior thread comments, and source-line metadata
without repeatedly scanning the full corpus.

A1 turns selected target comments plus controlled context into model-ready
messages. It does not write final labels at scale. Its job is to define the
schema, prompt, context policy, and target-author attribution rule that later
stages must follow.

A2 applies the A1 instrument to selected comments. It records every selected
comment as a work item, every model call as an attempt, every validated
structured response as a result, and every extracted target-author statement as
a claim row. A2 exports these tables with manifests, row counts, and hashes so
downstream stages can detect changed or incomplete runs.

A3 audits the shape and quality of A2 output. It validates hashes and row
counts, reconciles exports against the run database, normalizes high-cardinality
claim labels without deleting raw model labels, computes denominators and
distributions, prepares private quote candidates, creates a codebook, and marks
findings as exploratory or not reportable when audit or normalization evidence
is missing.

A4 packages A3-analyzed data for review. It verifies A3/A2 provenance, builds a
queryable evidence mart, creates finding cards, freezes report facts into
`evidence_packet.json`, and renders deterministic private-review Markdown. A4
does not rerun extraction, does not publish unreviewed quotes, does not infer
patient-level denominators, and does not upgrade A3 reportability labels.

The optional clustering layer reads the A4 evidence mart and joins A0 raw
comment bodies. It creates exploratory comment-level feature vectors and cluster
assignments for theme discovery. It does not change A4 findings, does not
create reportable prevalence estimates, and should be treated as exploratory
until enough comments are clustered and the clusters are manually reviewed.

The key data principle is provenance over mutation: derived files can always be
rebuilt from their upstream inputs, and every reportable count or quote should
trace back to source-line, comment ID, run ID, file hash, and prompt/schema
version.

## End Result

The end result is not one single file. It is a traceable set of structured
evidence artifacts that let a researcher query, audit, summarize, and cautiously
report self-reported health patterns from the Reddit comments.

The practical final product is an A4 private-review report package:

```text
dataset/covidlonghaulers_comments/derived/a4_evidence_reporting/reports/<report_id>/
  report_manifest.json
  evidence_mart.sqlite
  finding_cards.csv
  finding_cards.jsonl
  evidence_packet.json
  report.md
  methods.md
  limitations.md
  provenance.md
  validation_report.json
  tables/
  quotes/
```

Optional exploratory clustering can add a cluster package next to the A4 report:

```text
dataset/covidlonghaulers_comments/derived/a4_evidence_reporting/reports/<report_id>/clusters/
  cluster_manifest.json
  cluster_readiness_report.json
  comment_cluster_assignments.csv
  cluster_summary.csv
  cluster_examples.csv
  cosine_similarity.csv
  top_tfidf_terms.csv
  cluster_terms.csv
```

The important end artifacts are:

```text
evidence_mart.sqlite
  Queryable SQLite database for downstream notebooks, dashboards, and research
  queries.

finding_cards.csv / finding_cards.jsonl
  One row per aggregate finding, with denominator, source claim IDs,
  reportability label, audit status, and limitations.

evidence_packet.json
  Frozen packet of the exact facts the rendered report is allowed to say.
  This keeps counts, caveats, and quote references grounded.

report.md
  Human-readable private-review summary of extracted patterns.

methods.md
  Source data, A1/A2/A3/A4 versions, model IDs, denominator definitions,
  validation checks, and processing details.

limitations.md
  Interpretation boundaries: Reddit self-report data, no clinical
  verification, no patient-level denominator yet, no treatment efficacy/safety
  claims, and quote-review limits.

provenance.md
  A3 analysis IDs, A2 run IDs, source file hashes, analysis hashes, and report
  file hashes.

validation_report.json
  Machine-readable check that the package is internally consistent.

tables/
  CSV views for common analysis questions, such as claim counts by label,
  claim counts by type, monthly claim counts, reportability by label, and
  denominator summaries.

quotes/
  Private quote bank and review template. These are not public quote outputs
  until review/redaction exists.
```

In practical terms, the finished pipeline lets a researcher ask:

- what symptoms or health experiences are commonly self-reported in this sample?
- which normalized labels appear most often?
- how many extracted claims mention labels such as fatigue, shortness of breath,
  chest pain, PEM, or other long-COVID experiences?
- how do claim frequencies vary by month?
- which extracted claims are context-sensitive and need manual review?
- which findings are only exploratory because normalization or audit is missing?
- which evidence quotes might support a finding after redaction review?
- which comments appear thematically similar enough to inspect as candidate
  clusters after A4 extraction?

The current end result is deliberately conservative. It does not produce:

- clinical prevalence estimates
- patient-level rates
- treatment efficacy claims
- treatment safety claims
- public-ready medical advice
- public-ready patient quote reports

The pipeline is best understood as a provenance-preserving evidence preparation
and review system: it turns raw Reddit comments into structured, queryable, and
cautiously reportable self-reported health patterns.

## Quick Start

Verify the local split dataset and context database:

```powershell
python dev/analysis/a0_extraction/build_comment_dataset.py --verify-only
python dev/analysis/a0_extraction/build_comment_context_db.py --verify-only
```

Render a small A1 prompt-development sample without model calls:

```powershell
python dev/analysis/a1_coding_research/scripts/select_samples.py --replace
python dev/analysis/a1_coding_research/scripts/render_sample_contexts.py --sample prompt_dev --limit 5
python dev/analysis/a1_coding_research/scripts/run_prompt_dev.py --sample prompt_dev --limit 5 --dry-render
```

Create, dry-render, run, summarize, and export a tiny A2 batch:

```powershell
python dev/analysis/a2_batch_extraction/scripts/create_run.py --sample prompt_dev --limit 3
python dev/analysis/a2_batch_extraction/scripts/run_batch.py --run <a2_run_dir> --dry-render --limit 3
python dev/analysis/a2_batch_extraction/scripts/run_batch.py --run <a2_run_dir> --live --limit 3 --workers 1 --max-attempts 2
python dev/analysis/a2_batch_extraction/scripts/summarize_run.py --run <a2_run_dir>
python dev/analysis/a2_batch_extraction/scripts/export_run.py --run <a2_run_dir>
```

Analyze that exported A2 run with A3:

```powershell
python dev/analysis/a3_result_analysis/scripts/run_analysis.py --run <a2_run_dir>
```

Build a private-review A4 report package from the A3 output:

```powershell
python dev/analysis/a4_evidence_reporting/scripts/build_report.py --a3 <a3_analysis_dir>
```

Optionally cluster comments from the A4 report:

```powershell
python dev/analysis/cluster/scripts/build_clusters.py --a4-report <a4_report_dir>
```

## Directory Map

```text
dev/analysis/
  README.md
  helpers.py
  build_comment_dataset.py
  build_comment_context_db.py

  a0_extraction/
    comment_dataset.py
    comment_context.py
    build_comment_dataset.py
    build_comment_context_db.py

  agents/
    _common/
    CommentCoderAgent/

  a1_coding_research/
    prompts/
    samples/
    scripts/
    evals/
    notes/

  a2_batch_extraction/
    scripts/
    notes/
    tests/

  a3_result_analysis/
    scripts/
    notes/
    tests/

  a4_evidence_reporting/
    scripts/
    notes/
    tests/

  cluster/
    scripts/
    tests/
```

Compatibility wrappers remain at:

```text
dev/analysis/build_comment_dataset.py
dev/analysis/build_comment_context_db.py
scripts/build_covidlonghaulers_comment_dataset.py
```

New implementation code should live in the stage folders. Most notebooks or
ad-hoc analysis scripts should import the user-facing helper in
`dev.analysis.helpers` for comment access.

## Stage Summary

### A0 Extraction

A0 turns the large raw Reddit JSONL export into a structured local dataset and a
SQLite context database.

Primary code:

```text
dev/analysis/a0_extraction/comment_dataset.py
dev/analysis/a0_extraction/comment_context.py
```

Primary outputs:

```text
dataset/covidlonghaulers_comments/
  comments_jsonl/
  index/
  metadata/
  derived/comments.sqlite
```

What A0 guarantees:

- the source JSONL is split into smaller full-record JSONL chunks
- compact CSV indexes exist for browsing
- metadata manifests, checksums, and row-count summaries exist
- `comments.sqlite` supports parent/ancestor/sibling/thread context lookup
- source-line identity is preserved for downstream traceability

### A1 Coding Research

A1 defines the comment-coding instrument: schema, prompt, context rendering
policy, attribution rules, and a no-tool Rumi agent for one target comment at a
time.

Primary code:

```text
dev/analysis/agents/CommentCoderAgent/
dev/analysis/a1_coding_research/prompts/comment_coder_v0.1.md
dev/analysis/a1_coding_research/scripts/
```

Primary outputs:

```text
dataset/covidlonghaulers_comments/derived/a1_coding_research/
```

What A1 guarantees:

- target-comment-only attribution is explicit
- context is used only to resolve references in the target comment
- structured output conforms to the A1 Pydantic schema
- prompt-development samples and eval summaries are versioned
- small live model checks happen before any batch scaleup

### A2 Batch Extraction

A2 turns A1 into a resumable batch runner. It creates SQLite run ledgers,
renders work items, records attempts, stores structured results, expands claim
rows, and exports A3-ready tables.

Primary code:

```text
dev/analysis/a2_batch_extraction/runner.py
dev/analysis/a2_batch_extraction/storage.py
dev/analysis/a2_batch_extraction/scripts/
```

Primary outputs:

```text
dataset/covidlonghaulers_comments/derived/a2_batch_extraction/runs/comment_coding/<run_id>/
  run.sqlite
  manifest.json
  exports/
```

What A2 guarantees:

- every selected target comment becomes a `work_items` row
- every live model call is represented in `attempts`
- validated structured outputs are stored in `results`
- extracted claims are flattened into `claim_rows`
- exported files include hashes and row counts in `export_manifest.json`
- audit templates are generated for comment-level and claim-level review

### A3 Result Analysis

A3 consumes A2 exports. It validates files and hashes, reconciles run databases
against exports, normalizes labels, summarizes distributions, prepares quote
candidates, generates codebooks, computes reportability labels, and scores
reviewed audit labels when supplied.

Primary code:

```text
dev/analysis/a3_result_analysis/analysis.py
dev/analysis/a3_result_analysis/validate.py
dev/analysis/a3_result_analysis/scripts/
```

Primary outputs:

```text
dataset/covidlonghaulers_comments/derived/a3_result_analysis/runs/<a2_run_id>/
  analysis_manifest.json
  a2_validation_report.json
  claim_rows_normalized.csv
  denominator_summary.csv
  quote_candidates.csv
  reportability_summary.csv
  codebook.csv
  codebook.md
```

What A3 guarantees:

- A2 export hashes and row counts are checked before analysis
- claim rows preserve raw model labels and add deterministic canonical fields
- denominators are explicit, not inferred by A4
- quote candidates are private-review inputs, not public-ready quotes
- reportability is conservative when audit/normalization is missing
- audit scoring uses Wilson intervals and gate decisions

### A4 Evidence Reporting

A4 consumes A3 analysis packages. It builds a private-review evidence mart,
finding cards, a frozen evidence packet, deterministic Markdown reports, quote
review templates, provenance docs, and validation reports.

Primary code:

```text
dev/analysis/a4_evidence_reporting/analysis.py
dev/analysis/a4_evidence_reporting/mart.py
dev/analysis/a4_evidence_reporting/scripts/
```

Primary outputs:

```text
dataset/covidlonghaulers_comments/derived/a4_evidence_reporting/reports/<report_id>/
  report_manifest.json
  evidence_mart.sqlite
  finding_cards.csv
  finding_cards.jsonl
  evidence_packet.json
  report.md
  methods.md
  limitations.md
  provenance.md
  validation_report.json
```

What A4 guarantees:

- every report package verifies A3 analysis and source A2 hashes
- every aggregate finding has a finding card and source claim IDs
- every rendered number is traceable to `evidence_packet.json`
- unreviewed quotes stay private
- A4 does not call an LLM in the first implementation
- A4 does not upgrade A3 reportability labels
- A4 does not claim patient-level prevalence without a validated patient denominator

### Optional Comment Clustering

The clustering layer consumes an A4 report package. It uses the A4
`evidence_mart.sqlite` as the source of extracted claims and joins the A0
`comments.sqlite` body text when possible.

Primary code:

```text
dev/analysis/cluster/analysis.py
dev/analysis/cluster/scripts/build_clusters.py
dev/analysis/cluster/tests/
```

Primary outputs:

```text
dataset/covidlonghaulers_comments/derived/a4_evidence_reporting/reports/<report_id>/clusters/
  cluster_manifest.json
  cluster_readiness_report.json
  comment_cluster_assignments.csv
  cluster_summary.csv
  cluster_examples.csv
  cosine_similarity.csv
  top_tfidf_terms.csv
  cluster_terms.csv
```

What clustering does:

- groups A4 claims to one document per `comment_id`
- optionally includes raw A0 comment body text
- vectorizes claim types, normalized labels, claim text, evidence quotes, and
  comment body with TF-IDF
- clusters comments with sklearn agglomerative clustering
- writes cluster assignments and summaries for downstream inspection
- marks tiny runs as `meaningful_clustering: false`

What clustering does not guarantee:

- it does not create validated qualitative themes by itself
- it does not change A3 normalization or A4 reportability labels
- it does not provide clinical prevalence, patient-level rates, treatment
  efficacy, or treatment safety
- it does not remove the need for human review of cluster names and examples

## Common Workflows

### Rebuild A0 From The Raw Export

Default source:

```text
C:\Users\leech\Downloads\r_covidlonghaulers_comments_all.jsonl
```

Default output:

```text
dataset/covidlonghaulers_comments/
```

Rebuild the split dataset:

```powershell
python dev/analysis/a0_extraction/build_comment_dataset.py --replace
```

Rebuild the context database:

```powershell
python dev/analysis/a0_extraction/build_comment_context_db.py --replace
```

Verify both:

```powershell
python dev/analysis/a0_extraction/build_comment_dataset.py --verify-only
python dev/analysis/a0_extraction/build_comment_context_db.py --verify-only
```

### Inspect A Comment With Context

By source line:

```powershell
python dev/analysis/a0_extraction/build_comment_context_db.py `
  --sample-source-line 11 `
  --ancestor-depth 3 `
  --previous-sibling-limit 2 `
  --previous-thread-limit 3
```

By comment ID:

```powershell
python dev/analysis/a0_extraction/build_comment_context_db.py `
  --sample-id fz5axid `
  --ancestor-depth 3
```

### Run A1 Prompt Development

Select frozen prompt-development samples:

```powershell
python dev/analysis/a1_coding_research/scripts/select_samples.py --replace
```

Render target comments and context windows:

```powershell
python dev/analysis/a1_coding_research/scripts/render_sample_contexts.py --sample prompt_dev --limit 5
```

Dry-render A1 prompt messages without model calls:

```powershell
python dev/analysis/a1_coding_research/scripts/run_prompt_dev.py --sample prompt_dev --limit 5 --dry-render
```

Check OpenRouter connectivity:

```powershell
python dev/analysis/a1_coding_research/scripts/run_prompt_dev.py --check-openrouter --model openai/gpt-4o-mini
```

Run a tiny live A1 eval:

```powershell
python dev/analysis/a1_coding_research/scripts/run_prompt_dev.py --sample prompt_dev --limit 3 --live --model openai/gpt-4o-mini
```

Summarize latest A1 eval:

```powershell
python dev/analysis/a1_coding_research/scripts/summarize_eval.py --latest --write
```

### Run A2 Batch Extraction

Create a run from the A1 prompt-development sample:

```powershell
python dev/analysis/a2_batch_extraction/scripts/create_run.py --sample prompt_dev --limit 25
```

Dry-render the run:

```powershell
python dev/analysis/a2_batch_extraction/scripts/run_batch.py --run <run_dir> --dry-render --limit 25
```

Inspect the ledger:

```powershell
python dev/analysis/a2_batch_extraction/scripts/inspect_run.py --run <run_dir>
```

Run a tiny live batch:

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

Run the tiny A2 OpenRouter eval:

```powershell
python dev/analysis/a2_batch_extraction/scripts/eval_openrouter.py --model openai/gpt-4o-mini --sample prompt_dev --limit 3 --max-attempts 2
```

### Run A3 Result Analysis

Validate an A2 export:

```powershell
python dev/analysis/a3_result_analysis/scripts/validate_a2_run.py --run <a2_run_dir>
```

Build the full A3 package:

```powershell
python dev/analysis/a3_result_analysis/scripts/run_analysis.py --run <a2_run_dir>
```

Run individual A3 steps when debugging:

```powershell
python dev/analysis/a3_result_analysis/scripts/summarize_run.py --run <a2_run_dir>
python dev/analysis/a3_result_analysis/scripts/normalize_claim_labels.py --run <a2_run_dir>
python dev/analysis/a3_result_analysis/scripts/make_codebook.py --run <a2_run_dir>
python dev/analysis/a3_result_analysis/scripts/build_reportability.py --run <a2_run_dir>
```

Score reviewed audit labels:

```powershell
python dev/analysis/a3_result_analysis/scripts/score_audit.py `
  --audit-comments <audit_comments.csv> `
  --audit-claims <audit_claims.csv> `
  --output-dir <score_output_dir>
```

Run the A1 -> A2 -> A3 OpenRouter smoke eval:

```powershell
python dev/analysis/a3_result_analysis/scripts/eval_openrouter.py --model openai/gpt-4o-mini --sample prompt_dev --limit 3 --max-attempts 2
```

### Run A4 Evidence Reporting

Build a private-review A4 report package:

```powershell
python dev/analysis/a4_evidence_reporting/scripts/build_report.py --a3 <a3_analysis_dir>
```

Use an explicit report ID:

```powershell
python dev/analysis/a4_evidence_reporting/scripts/build_report.py `
  --a3 <a3_analysis_dir> `
  --report-id <report_id>
```

Validate a report package:

```powershell
python dev/analysis/a4_evidence_reporting/scripts/validate_report.py --report <a4_report_dir>
```

### Run Comment Clustering

Clustering is an optional post-A4 exploratory step. It does not call an LLM. It
reads the A4 evidence mart, joins A0 raw comment bodies when available, and
writes a cluster package under the A4 report directory by default.

Run from the command line:

```powershell
python dev/analysis/cluster/scripts/build_clusters.py --a4-report <a4_report_dir>
```

Use an explicit output directory:

```powershell
python dev/analysis/cluster/scripts/build_clusters.py `
  --a4-report <a4_report_dir> `
  --output-dir <cluster_output_dir>
```

Force a fixed number of clusters:

```powershell
python dev/analysis/cluster/scripts/build_clusters.py `
  --a4-report <a4_report_dir> `
  --n-clusters 8
```

Use threshold clustering instead of a fixed cluster count:

```powershell
python dev/analysis/cluster/scripts/build_clusters.py `
  --a4-report <a4_report_dir> `
  --distance-threshold 0.65
```

Run from Python:

```python
from dev.analysis.helpers import cluster_comments

result = cluster_comments(
    a4_report="dataset/covidlonghaulers_comments/derived/a4_evidence_reporting/reports/<report_id>",
)

print(result["output_dir"])
print(result["meaningful_clustering"])
```

Read the assignments later:

```python
from dev.analysis.helpers import load_comment_cluster_assignments

rows = load_comment_cluster_assignments(
    "dataset/covidlonghaulers_comments/derived/a4_evidence_reporting/reports/<report_id>/clusters"
)
```

Default output:

```text
<a4_report_dir>/clusters/
  cluster_manifest.json
  cluster_readiness_report.json
  comment_cluster_assignments.csv
  cluster_summary.csv
  cluster_examples.csv
  cosine_similarity.csv
  top_tfidf_terms.csv
  cluster_terms.csv
```

How to read the outputs:

```text
cluster_readiness_report.json
  First file to check. It records input paths, row counts, TF-IDF shape,
  number of clusters, warnings, and `meaningful_clustering`.

comment_cluster_assignments.csv
  One row per clustered comment. Join this back to A0 comments by `comment_id`
  or to A4 claims by `comment_id`.

cluster_summary.csv
  Cluster-level counts: number of comments, total claims, top claim types,
  top normalized labels, and representative comment ID.

cluster_examples.csv
  Example claim and quote rows for quick review. Treat these as private-review
  material, not public quote output.

cosine_similarity.csv
  Pairwise comment similarity. Useful for debugging why comments did or did not
  land near each other.

top_tfidf_terms.csv
  Strongest TF-IDF terms per comment.

cluster_terms.csv
  Strongest TF-IDF terms per cluster. Use this to draft provisional cluster
  names, then verify against examples.
```

Important interpretation rule:

```text
meaningful_clustering = false
```

means the code ran, but the sample is too small to interpret as stable
clusters. This is expected for tiny smoke runs. The current guard defaults to
`min_meaningful_comments=10`, which is only a minimal mechanics threshold. Real
theme discovery should use a much larger A2/A3/A4 run and manual cluster review.

Useful knobs:

- `--n-clusters`: force a fixed number of clusters when you already want a
  specific segmentation.
- `--distance-threshold`: let agglomerative clustering decide the cluster count
  from cosine distance.
- `--no-comment-body`: cluster only from A4 extracted claim fields.
- `--no-claim-text`: remove raw claim text from the cluster document.
- `--no-evidence-quotes`: remove evidence quotes from the cluster document.
- `--max-features`: cap TF-IDF vocabulary size.
- `--min-df`: require terms to appear in at least this many comments.
- `--write-feature-matrix`: write `comment_feature_matrix.csv` for inspection.

Expected smoke behavior on the current small A4 test package:

```text
n_claim_rows = 17
n_comments_with_claims = 2
n_joined_comment_bodies = 2
n_clusters = 2
meaningful_clustering = false
```

## Programmatic Comment Access

Use `dev.analysis.helpers.comments` for normal analysis code. It can return one
comment, one comment with context, or an iterator.

One comment with context by source line:

```python
from dev.analysis.helpers import comments

item = comments(
    source_line=11,
    ancestor_depth=3,
    previous_sibling_limit=2,
    previous_thread_limit=3,
)

print(item.target.body)
print([ancestor.body for ancestor in item.ancestors])
```

One bare comment:

```python
from dev.analysis.helpers import comments

comment = comments(source_line=11, with_context=False)
print(comment.body)
```

Iterate through comments with context:

```python
from dev.analysis.helpers import comments

for item in comments(
    ancestor_depth=2,
    previous_sibling_limit=2,
    previous_thread_limit=0,
    order="created_utc, id",
    limit=100,
):
    target = item.target
    ancestors = item.ancestors
    previous_siblings = item.previous_siblings
    missing = item.missing
```

Iterate through bare comments:

```python
from dev.analysis.helpers import comments

for comment in comments(with_context=False, limit=100):
    print(comment.id, comment.body[:80])
```

Lower-level context access remains available:

```python
from dev.analysis.a0_extraction.comment_context import CommentStore, render_context

with CommentStore() as store:
    context = store.get_context("fz5axid", ancestor_depth=3)
    print(render_context(context))
```

## Context And Attribution Policy

Reddit threads are trees, not flat conversations. The context API keeps these
roles separate:

```text
target
  The one comment being classified or extracted.

ancestors
  Direct parent, grandparent, and higher parent-chain comments.

previous_siblings
  Earlier comments under the same parent ID.

previous_thread_comments
  Earlier comments in the same thread, ordered chronologically.
```

Default extraction context should usually be conservative:

```text
ancestor_depth = 2
previous_sibling_limit = 0 or 2
previous_thread_limit = 0
```

Use context only to resolve target-comment references such as:

```text
same
that
it
this medication
that crash
your symptoms
```

Do not copy claims from a parent, sibling, or earlier thread comment into the
target author's record unless the target comment itself endorses, repeats, or
clearly adopts the claim.

Bad extraction:

```text
Parent: "LDN helped my fatigue."
Target: "How long did it take?"

Wrong label: target author took LDN and improved.
```

Better extraction:

```text
Target is asking about LDN timing.
No target-author treatment claim is present.
```

This distinction is central to keeping downstream biomedical analysis clean.

## Dataset Layout And Snapshot

Default dataset root:

```text
dataset/covidlonghaulers_comments/
```

Expected A0 layout:

```text
dataset/covidlonghaulers_comments/
  README.md
  comments_jsonl/
    year=YYYY/
      month=MM/
        comments_YYYY-MM_part-0001.jsonl
  index/
    comments_index_part-0001.csv
  metadata/
    manifest.json
    chunks.csv
    index_files.csv
    summary_by_month.csv
    field_counts.csv
    malformed_lines.jsonl
  derived/
    comments.sqlite
```

Current verified local dataset facts:

```text
source lines: 1,950,192
valid comments: 1,950,192
blank lines: 0
malformed lines: 0
JSONL chunk files: 231
CSV index files: 40
date span UTC: 2020-07-24T19:58:29+00:00 to 2026-06-09T05:10:23+00:00
source SHA-256: 6511221575c20d5d07eab03a26e2e4af2bbb34543fee2a59ecc260bc2cc88ebe
```

Current verified context database facts:

```text
comments: 1,950,192
comments with body: 1,950,192
distinct source lines: 1,950,192
top-level comments: 766,962
reply comments: 1,183,230
reply comments with available parent: 1,183,155
reply comments with missing parent: 75
removed/deleted comments: 52,710
```

These are local build facts, not hardcoded assumptions. Re-run the verification
commands when correctness matters.

## Generated Outputs

Main derived roots:

```text
dataset/covidlonghaulers_comments/derived/
  comments.sqlite
  a1_coding_research/
  a2_batch_extraction/
  a3_result_analysis/
  a4_evidence_reporting/
```

A2 run output:

```text
dataset/covidlonghaulers_comments/derived/a2_batch_extraction/runs/comment_coding/<run_id>/
  run.sqlite
  manifest.json
  exports/
    run_manifest.json
    run_report.json
    comment_rows.csv
    claim_rows.csv
    failed_items.csv
    attempts.csv
    results.jsonl
    audit_comment_template.csv
    audit_claim_template.csv
    export_manifest.json
```

A3 analysis output:

```text
dataset/covidlonghaulers_comments/derived/a3_result_analysis/runs/<a2_run_id>/
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

A4 report output:

```text
dataset/covidlonghaulers_comments/derived/a4_evidence_reporting/reports/<report_id>/
  report_manifest.json
  evidence_mart.sqlite
  finding_cards.jsonl
  finding_cards.csv
  evidence_packet.json
  tables/
  quotes/
  report.md
  methods.md
  limitations.md
  provenance.md
  validation_report.json
  source_a3_validation_report.json
```

Optional cluster output:

```text
dataset/covidlonghaulers_comments/derived/a4_evidence_reporting/reports/<report_id>/clusters/
  cluster_manifest.json
  cluster_readiness_report.json
  comment_cluster_assignments.csv
  cluster_summary.csv
  cluster_examples.csv
  cosine_similarity.csv
  top_tfidf_terms.csv
  cluster_terms.csv
```

## OpenRouter Notes

Live A1/A2/A3 evals use OpenRouter through the local `.env` loading path in
`dev/analysis/agents/_common/runtime.py`.

Set the key in the project `.env` or process environment:

```text
OPENROUTER_API_KEY=...
```

Observed model behavior in this pipeline:

- `openai/gpt-4o-mini` works end-to-end with the current Rumi structured-output path.
- `anthropic/claude-haiku-4.5` can pass simple connectivity but rejects the current structured-output schema through its provider route.
- `openai/gpt-oss-120b` reached OpenRouter in prior checks but was too slow or hung on the structured A2 smoke path.

For small live smoke tests, prefer:

```text
openai/gpt-4o-mini
```

## Verification

Fast syntax and unit-test checks for the implemented A3/A4/cluster layers:

```powershell
python -m compileall dev/analysis/a3_result_analysis dev/analysis/a4_evidence_reporting dev/analysis/cluster dev/analysis/helpers.py
python -m pytest dev/analysis/a3_result_analysis/tests dev/analysis/a4_evidence_reporting/tests dev/analysis/cluster/tests -q
```

Current expected result after the A4 and cluster implementation:

```text
10 passed
```

Verify A0 data and context:

```powershell
python dev/analysis/a0_extraction/build_comment_dataset.py --verify-only
python dev/analysis/a0_extraction/build_comment_context_db.py --verify-only
```

Validate a generated A4 package:

```powershell
python dev/analysis/a4_evidence_reporting/scripts/validate_report.py --report <a4_report_dir>
```

## Development Conventions

- Keep raw and derived data out of git.
- Prefer streaming reads for large JSONL files.
- Prefer SQLite, DuckDB, Parquet, or explicit CSV exports over repeated full JSONL scans.
- Keep context roles explicit: target, ancestor, sibling, previous-thread.
- Keep target-author attribution separate from context-author claims.
- Preserve source-line, comment ID, run ID, hash, prompt, and context provenance.
- Add deterministic CLI commands for every derived artifact.
- Add verification commands for every generated package.
- Use small prompt-dev and smoke runs before any expensive model run.
- Keep public-facing reporting conservative: no unreviewed quotes, no patient denominator without author deduplication, no clinical claims.
- Avoid hidden notebook-only state for pipeline-critical steps.

## Known Limitations

The current source dataset is comments-only. It does not include submission
titles, submission bodies, flair, post score, or root post author text.

For top-level comments, the context DB knows the comment replied to a post:

```text
parent_id = t3_<post_id>
```

but it cannot provide the post title or body. `CommentContext.missing` marks
this as:

```python
{"root_post": "not_available_in_comments_jsonl"}
```

There are also a small number of reply comments whose parent comments are not
present in the export. These are preserved and reported during verification.

Current A2/A3/A4 outputs do not expose a validated stable author/patient
identifier, so A4 reports comment and claim counts rather than patient-level
prevalence.

The current A1 schema identifies health claims, symptoms, treatment mentions,
assertions, experiencers, and evidence quotes. It does not yet model a full
treatment-outcome relation with treatment entity, outcome direction, target
symptom, side effect, dose, and timeline. Do not report treatment efficacy or
safety percentages from the current A4 claim-distribution report.

## Troubleshooting

If the split dataset is missing:

```powershell
python dev/analysis/a0_extraction/build_comment_dataset.py --replace
```

If `comments.sqlite` is missing:

```powershell
python dev/analysis/a0_extraction/build_comment_context_db.py --replace
```

If A1/A2 live calls fail with a missing key, add `OPENROUTER_API_KEY` to
`.env` or the shell environment.

If an A2 run fails partway through, inspect its run ledger:

```powershell
python dev/analysis/a2_batch_extraction/scripts/inspect_run.py --run <run_dir>
python dev/analysis/a2_batch_extraction/scripts/summarize_run.py --run <run_dir>
```

If A3 rejects an A2 run, read:

```text
<a3_analysis_dir>/a2_validation_report.json
```

or run:

```powershell
python dev/analysis/a3_result_analysis/scripts/validate_a2_run.py --run <a2_run_dir>
```

If A4 rejects an A3 package, read:

```text
<a4_report_dir>/source_a3_validation_report.json
<a4_report_dir>/validation_report.json
```

If clustering fails with a missing sklearn import, install the cluster extra or
the package directly:

```powershell
python -m pip install ".[cluster]"
```

or:

```powershell
python -m pip install scikit-learn
```

If clustering succeeds but says `meaningful_clustering: false`, the usual cause
is a tiny smoke run. Inspect `cluster_readiness_report.json` and run A2/A3/A4 on
more comments before interpreting cluster themes.

If a generated report has no reportable public findings, that is usually the
correct conservative result until audit labels, accepted normalization, and
quote review exist.
