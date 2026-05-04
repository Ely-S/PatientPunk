# IRR Pilot 500 — Sampling Methodology

This document describes how the 500-unit inter-coder reliability (IRR) sample
in this directory was drawn. It applies to the tracked artifacts in this
folder:

- [`coding_input.csv`](./coding_input.csv) — the 500 sampled units,
  distributed to coders (one row per sample, columns: sample_id, subreddit,
  post_date, unit_type, title, parent_context, post_text)
- [`ai_labels.csv`](./ai_labels.csv) — analyst-only file with stratum labels
  and AI-pipeline output for each sample (columns: sample_id, source_post_id,
  stratum, ai_drug_count, ai_drugs, ai_sentiments, ai_signal_strengths,
  keyword_match)
- [`coder_output_template.csv`](./coder_output_template.csv) — empty form for
  coders to fill in (one row per sample_id, blank fields)

The codebook used by this pilot is the same as the one used for the original
300-sample pilot: see [`../irr_pilot/CODING_INSTRUCTIONS.md`](../irr_pilot/CODING_INSTRUCTIONS.md)
(or the PDF version). It is **not** duplicated in this folder.

The underlying source data (filtered JSON, SQLite DB, AI pipeline outputs)
from which this sample was drawn lives outside git in
`data/irr_pilot_500/source/` (large; not redistributed). The reproducibility
section at the bottom shows how to regenerate it.

Reproducibility scripts: `scripts/convert_jsonl_to_source.py` and
`scripts/sample_for_coding.py` (in the project repository).

## Source corpus

We scraped the entire posting history of r/covidlonghaulers using the Arctic
Shift archive, producing two files:

- `r_covidlonghaulers_posts_all.jsonl` — 117,260 posts
- `r_covidlonghaulers_comments_all.jsonl` — 1,925,353 comments

The full corpus spans 2020-07-24 to 2026-04-28. For this IRR pilot we restricted
the corpus to posts and comments with timestamps in the window
**2021-11-01 00:00 UTC through 2021-12-31 23:59 UTC**, yielding 2,739 posts and
39,559 comments. Comments whose parent post fell outside the window were
excluded so that no orphaned reply lacks its conversational context.

## Codable pool

Posts and comments were classified as "codable" if their body text was between
100 and 800 characters. The lower bound excludes one-line comments that lack
sufficient context for coding; the upper bound caps the cognitive load on human
coders. For comments, the parent context (up to 2 hops upstream) was retained
alongside the comment body — matching the AI pipeline's `max_upstream_depth=2`
setting, so coders see exactly the same upstream context the AI saw.

After this filter, the codable pool contained 22,915 units, broken down as:

- 2,730 units where the AI pipeline already extracted at least one drug mention
- 3,600 units where the AI found nothing but a regex of common medication terms
  matched the body text
- 16,585 units where neither the AI nor the regex matched

## Stratification with enrichment

A simple random sample of patient narratives is dominated by posts that mention
no drugs at all. Such posts produce trivial perfect agreement among coders
("no drug here") and provide little signal about pipeline reliability on the
analyses that matter. To stress-test the pipeline more efficiently, we drew a
stratified random sample with three strata, weighted to oversample the
analysis-relevant cases:

| Stratum | Definition | Share | Target n | Achieved n |
|---|---|---|---|---|
| `ai_found_drug` | AI pipeline extracted at least one drug mention from the unit | 50% | 250 | 250 |
| `no_ai_drug_keyword_match` | AI found no drug, but a regex of common medication terms matched | 30% | 150 | 150 |
| `no_ai_drug_random` | Neither the AI pipeline nor the regex matched | 20% | 100 | 100 |

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
`random.sample()` with `seed=43`. The seed is fixed for reproducibility and was
chosen to differ from the original 300-sample IRR pilot's seed (`seed=42`),
ensuring no sampling overlap when both pilots draw from the same source. The
three strata were concatenated and shuffled together before assignment of
sample IDs, so coders cannot infer a unit's stratum from its position in the
coding sheet.

## Stratum proportions are deliberately non-representative

The 50/30/20 weighting is chosen for analytical efficiency, not for
representativeness of the underlying corpus. In the actual codable pool, the
AI-found-drug stratum is roughly 12% of units (2,730 of 22,915); we upweighted
it to 50% so that per-drug agreement statistics have meaningful sample size.

Inter-coder reliability statistics from this pilot should therefore be
interpreted as **conditional on stratum membership**:

- The α for the AI-found-drug stratum (n = 250) estimates pipeline reliability
  on the units that contribute to per-drug aggregations in downstream analyses.
- The α for the keyword-match stratum (n = 150) is diagnostic for pipeline
  recall.
- The α for the random stratum (n = 100) is diagnostic for pipeline
  specificity, and is dominated by trivially-agreed-on negatives ("no drug
  here").

When citing IRR for the per-drug aggregation results in the historical
validation paper, the most relevant subsample is the `ai_found_drug` stratum,
not the unweighted full sample.

## Sample identifiers and coder blinding

Each sampled unit was assigned a sequential identifier of the form
`irr-pilot-NNN` (zero-padded to three digits). Stratum membership is recorded
in `ai_labels.csv`, which is **analyst-only** and not distributed to coders.

The materials distributed to coders (`coding_input.csv` plus the codebook in
`data/irr_pilot/CODING_INSTRUCTIONS.md`) contain only:

- The unit's body text
- The parent context (for comments — up to 2 hops upstream)
- The post date
- A blank coding template

Coders see no AI labels, no stratum labels, and no other metadata that would
permit them to anticipate the AI's output for a given unit.

## Date range of the sample

| Property | Value |
|---|---|
| Earliest post | 2021-11-01 |
| Latest post | 2021-12-31 |
| Distinct dates | 61 |
| Total samples | 500 |

## Pipeline outputs underlying stratum membership

The `source/pipeline_output/` directory contains the AI pipeline outputs used
for stratification:

- `tagged_mentions.json` — per-entry list of drug names extracted from each
  post or comment
- `canonicalized_mentions.json` — same, after canonicalization to standard
  drug names
- `prefilter_results.json` — fast-model prefilter decisions (whether each
  (entry, drug) pair expresses a personal-use experience)

The pipeline that produced these outputs is the same pipeline whose
classifications appear in `data/historical_validation/master_gap/posts.db` and
the per-drug downstream analyses; the LLM models used were
`anthropic/claude-haiku-4.5` (fast model, used for prefiltering and routine
extraction) and `anthropic/claude-sonnet-4.6` (strong model, used for
classification of (entry, drug) pairs that pass the prefilter).

## Reproducibility

Re-running

```
python scripts/convert_jsonl_to_source.py \
    --posts    PatientPunk_data/r_covidlonghaulers_posts_all.jsonl \
    --comments PatientPunk_data/r_covidlonghaulers_comments_all.jsonl \
    --start    2021-11-01 \
    --end      2022-01-01 \
    --output   data/irr_pilot_500/source/covidlonghaulers_nov_dec_2021.json

python src/import_posts.py \
    --reddit-posts data/irr_pilot_500/source/covidlonghaulers_nov_dec_2021.json \
    --output-db    data/irr_pilot_500/source/posts.db \
    --subreddit    covidlonghaulers

python src/run_sentiment_pipeline.py \
    --db          data/irr_pilot_500/source/posts.db \
    --output-dir  data/irr_pilot_500/source/pipeline_output \
    --workers     3

python scripts/sample_for_coding.py \
    --n               500 \
    --seed            43 \
    --out-dir         data/irr_pilot_500/ \
    --source-json     data/irr_pilot_500/source/covidlonghaulers_nov_dec_2021.json \
    --db-path         data/irr_pilot_500/source/posts.db \
    --tagged-mentions data/irr_pilot_500/source/pipeline_output/tagged_mentions.json \
    --canonical-map   data/irr_pilot_500/source/pipeline_output/canonical_map.json
```

against the same input JSONL files produces an identical sample.

---

## Sampling Methodology — IRR Pilot 500 (Nov–Dec 2021)

### Source corpus

We scraped the entire posting history of r/covidlonghaulers using the Arctic Shift archive, producing two files: `r_covidlonghaulers_posts_all.jsonl` (117,260 posts) and `r_covidlonghaulers_comments_all.jsonl` (1,925,353 comments), spanning 2020-07-24 to 2026-04-28. We restricted this corpus to posts and comments with timestamps in the window 2021-11-01 00:00 UTC through 2021-12-31 23:59 UTC, yielding 2,739 posts and 39,559 comments. Comments whose parent post fell outside the window were excluded.

### Codable pool

Posts and comments were classified as "codable" if their body text was between 100 and 800 characters. The lower bound excludes one-line comments that lack sufficient context for coding; the upper bound caps the cognitive load on human coders. For comments, the parent context (up to 2 hops upstream) was retained alongside the comment body — matching the AI pipeline's `max_upstream_depth=2` setting, so coders see the same upstream context the AI saw.

### Stratification with enrichment

A simple random sample of patient narratives is dominated by posts that mention no drugs at all. Such posts produce trivial perfect agreement among coders ("no drug here") and provide little signal about pipeline reliability on the analyses that matter. To stress-test the pipeline more efficiently, we drew a stratified random sample with three strata, weighted to oversample the analysis-relevant cases:

| Stratum | Definition | Share | Target n |
|---|---|---|---|
| `ai_found_drug` | The AI pipeline extracted at least one drug mention from the unit | 50% | 250 |
| `no_ai_drug_keyword_match` | The AI pipeline found no drug, but a regex of common medication terms matched | 30% | 150 |
| `no_ai_drug_random` | Neither the AI pipeline nor the regex matched | 20% | 100 |

The `ai_found_drug` stratum tests precision and sentiment agreement: when the AI flags a drug, do humans agree it's a drug, and do they agree on its sentiment? The `keyword_match` stratum tests recall: of posts that look pharmacologically relevant on a coarse heuristic, how many drugs is the AI missing? The `random` stratum tests specificity: when the AI flags nothing and there are no obvious keywords, do humans confirm "no drug here"?

Within each stratum, units were drawn uniformly at random using `random.sample()` with `seed=43`. The seed is fixed for reproducibility and was chosen to differ from the original 300-sample pilot's seed (42). The three strata were concatenated and shuffled together before assignment of sample IDs, so coders cannot infer a unit's stratum from its position in the coding sheet.

### Stratum proportions are deliberately non-representative

The 50/30/20 weighting is chosen for analytical efficiency, not representativeness. In the actual codable pool, the AI-found-drug stratum is roughly 12% of units (2,730 of 22,915); we upweighted it to 50% so per-drug agreement statistics have meaningful sample size. Inter-coder reliability statistics from this pilot should therefore be interpreted as conditional on stratum membership: the alpha for the AI-found-drug stratum estimates pipeline reliability on the units that contribute to per-drug aggregations in downstream analyses, while the keyword and random strata contribute mainly diagnostic information about pipeline recall and specificity.

### Sample identifiers and coder blinding

Each sampled unit was assigned a sequential identifier of the form `irr-pilot-NNN` (zero-padded to three digits). Stratum membership is recorded in an analyst-only file (`ai_labels.csv`) and is not visible to coders. The materials distributed to coders consist of the unit's body text, its parent context (for comments), the post date, and a blank coding template — no AI labels, no stratum labels, no other metadata that would permit a coder to anticipate the AI's output.

### Reproducibility

The exact corpus filtering, stratification, and sampling steps are implemented in `scripts/convert_jsonl_to_source.py` and `scripts/sample_for_coding.py`. Re-running with the same input files, date range, seed, and target sample size produces an identical sample.
