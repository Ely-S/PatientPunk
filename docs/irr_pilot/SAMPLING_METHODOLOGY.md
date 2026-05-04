# IRR Pilot 300 — Sampling Methodology

This document describes how the original 300-unit inter-coder reliability (IRR)
sample in this directory was drawn. It applies to the tracked artifacts in
this folder:

- [`coding_input.csv`](./coding_input.csv) — the 300 sampled units,
  distributed to coders (one row per sample, columns: sample_id, subreddit,
  post_date, unit_type, title, parent_context, post_text)
- [`ai_labels.csv`](./ai_labels.csv) — analyst-only file with stratum labels
  and AI-pipeline output for each sample (columns: sample_id, source_post_id,
  stratum, ai_drug_count, ai_drugs, ai_sentiments, ai_signal_strengths,
  keyword_match)
- [`coder_output_template.csv`](./coder_output_template.csv) — empty form
  for coders to fill in (one row per sample_id, blank fields)
- [`CODING_INSTRUCTIONS.md`](./CODING_INSTRUCTIONS.md) /
  [`CODING_INSTRUCTIONS.pdf`](./CODING_INSTRUCTIONS.pdf) — codebook
  distributed alongside the coding sheet

This is the *original* IRR pilot. A larger 500-unit pilot was drawn later
under the same procedure with `seed=43`; see
[`docs/irr_pilot_500/SAMPLING_METHODOLOGY.md`](../irr_pilot_500/SAMPLING_METHODOLOGY.md).
The two pilots cover non-overlapping windows of r/covidlonghaulers and use
different seeds, so no codable unit can appear in both.

Reproducibility script: `scripts/sample_for_coding.py` (in the project
repository).

## Source corpus

We scraped one month of r/covidlonghaulers posting history into a single JSON
file:

- `~/OneDrive/Documents/Projects/PatientPunk_data/subreddit_posts_month_1081posts.json`
  — 1,081 top-level posts and 16,342 comments

The window covered is **2026-03-11 20:02 UTC through 2026-04-10 21:06 UTC**
(30 days). Comments are nested inside their parent post in the JSON;
comments whose parent post fell outside the scrape window were never pulled
in the first place, so no orphaned reply lacks its conversational context.

## Codable pool

Posts and comments were classified as "codable" if their body text was between
100 and 800 characters. The lower bound excludes one-line comments that lack
sufficient context for coding; the upper bound caps the cognitive load on human
coders. For comments, the parent context (up to 2 hops upstream) was retained
alongside the comment body — matching the AI pipeline's `max_upstream_depth=2`
setting, so coders see exactly the same upstream context the AI saw.

After this filter, the codable pool contained 9,930 units (474 top-level posts
+ 9,456 comments), broken down as:

- 183 units where the AI pipeline already extracted at least one drug mention
- 2,327 units where the AI found nothing but a regex of common medication terms
  matched the body text
- 7,420 units where neither the AI nor the regex matched

## Stratification with enrichment

A simple random sample of patient narratives is dominated by posts that mention
no drugs at all. Such posts produce trivial perfect agreement among coders
("no drug here") and provide little signal about pipeline reliability on the
analyses that matter. To stress-test the pipeline more efficiently, we drew a
stratified random sample with three strata, weighted to oversample the
analysis-relevant cases:

| Stratum | Definition | Share | Target n | Achieved n |
|---|---|---|---|---|
| `ai_found_drug` | AI pipeline extracted at least one drug mention from the unit | 50% | 150 | 150 |
| `no_ai_drug_keyword_match` | AI found no drug, but a regex of common medication terms matched | 30% | 90 | 90 |
| `no_ai_drug_random` | Neither the AI pipeline nor the regex matched | 20% | 60 | 60 |

Each stratum tests a different aspect of pipeline behavior:

- The `ai_found_drug` stratum tests **precision** and sentiment agreement: when
  the AI flags a drug mention, do humans agree it is a drug, and do they agree
  on the personal-use, sentiment, and signal-strength labels?
- The `no_ai_drug_keyword_match` stratum tests **recall**: of posts that look
  pharmacologically relevant on a coarse heuristic, how many drug mentions is
  the AI missing?
- The `no_ai_drug_random` stratum tests **specificity**: when the AI flags
  nothing and there are no obvious medication keywords, do humans confirm "no
  drug here"?

Within each stratum, units were drawn uniformly at random using
`random.sample()` with `seed=42`. The seed is fixed for reproducibility; the
later 500-sample pilot used `seed=43` so the two samples could share a source
corpus without overlapping. The three strata were concatenated and shuffled
together before assignment of sample IDs, so coders cannot infer a unit's
stratum from its position in the coding sheet.

## Stratum proportions are deliberately non-representative

The 50/30/20 weighting is chosen for analytical efficiency, not for
representativeness of the underlying corpus. In the actual codable pool, the
AI-found-drug stratum is **roughly 1.8% of units (183 of 9,930)**; we
upweighted it to 50% so that per-drug agreement statistics have meaningful
sample size.

Inter-coder reliability statistics from this pilot should therefore be
interpreted as **conditional on stratum membership**:

- The α for the AI-found-drug stratum (n = 150) estimates pipeline reliability
  on the units that contribute to per-drug aggregations in downstream analyses.
- The α for the keyword-match stratum (n = 90) is diagnostic for pipeline
  recall.
- The α for the random stratum (n = 60) is diagnostic for pipeline
  specificity, and is dominated by trivially-agreed-on negatives ("no drug
  here").

When citing IRR for per-drug aggregation results in downstream analyses, the
most relevant subsample is the `ai_found_drug` stratum, not the unweighted
full sample.

## Sample identifiers and coder blinding

Each sampled unit was assigned a sequential identifier of the form
`irr-pilot-NNN` (zero-padded to three digits). Stratum membership is recorded
in `ai_labels.csv`, which is **analyst-only** and not distributed to coders.

The materials distributed to coders (`coding_input.csv` plus the codebook in
`CODING_INSTRUCTIONS.md` / `.pdf`, optionally bundled as
`irr_pilot_for_coders.zip`) contain only:

- The unit's body text
- The parent context (for comments — up to 2 hops upstream)
- The post date
- A blank coding template

Coders see no AI labels, no stratum labels, and no other metadata that would
permit them to anticipate the AI's output for a given unit.

## Date range of the sample

| Property | Value |
|---|---|
| Earliest unit | 2026-03-11 |
| Latest unit | 2026-04-10 |
| Span | 30 days |
| Total samples | 300 |

## Pipeline outputs underlying stratum membership

The pipeline outputs used for stratification live in the project's standard
locations rather than a per-pilot `source/` subdirectory:

- `data/patientpunk.db` — SQLite database with the pipeline's
  `treatment_reports` table for this 1-month corpus
- `data/drug_pipeline/tagged_mentions.json` — per-entry list of drug names
  extracted from each post or comment
- `data/drug_pipeline/canonical_map.json` — raw-name → canonical-name mapping
  used to canonicalize the extracted mentions

The pipeline that produced these outputs is the same pipeline whose
classifications appear in the historical-validation analyses; the LLM models
used were `anthropic/claude-haiku-4.5` (fast model, used for prefiltering and
routine extraction) and `anthropic/claude-sonnet-4.6` (strong model, used for
classification of (entry, drug) pairs that pass the prefilter).

For consistency with the AI pipeline's `max_upstream_depth=2`, AI labels in
`ai_labels.csv` are filtered to only those (post, drug) pairs that a
depth-capped pipeline run would produce — drugs inherited from ancestors more
than 2 hops upstream are excluded so the human↔AI comparison stays apples-to-
apples.

## Reproducibility

Re-running

```
python scripts/sample_for_coding.py \
    --n               300 \
    --seed            42 \
    --out-dir         data/irr_pilot/ \
    --source-json     ~/OneDrive/Documents/Projects/PatientPunk_data/subreddit_posts_month_1081posts.json \
    --db-path         data/patientpunk.db \
    --tagged-mentions data/drug_pipeline/tagged_mentions.json \
    --canonical-map   data/drug_pipeline/canonical_map.json
```

against the same input JSON and pipeline outputs produces an identical sample.
