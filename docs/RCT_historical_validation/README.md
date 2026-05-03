# RCT Historical Validation — Reproducibility Package

Reproduces **Figure 1**, **Table 2**, and **Table 3** from:

> *A Methodology for Gathering Real-World Evidence at Scale: Using NLP-Extracted Community Treatment Reports to Predict Clinical Trial Outcomes*

These figures compare what people on r/covidlonghaulers said about 6 Long COVID treatments — collected *before* the relevant clinical trial published — against the actual trial outcomes.

---

## Viewing the Results

Pre-built outputs are included in `output/` — no setup required:
- **`paper_figures.html`** — open in any browser to see all figures and tables
- **`figure1.png`** — Figure 1 as a standalone image
- `paper_figures_executed.ipynb` — executed notebook (open in Jupyter to explore)

## Re-running the Analysis

To regenerate the figures and tables, you only need **one database** (314 MB). Place it in a `data/` subfolder under this directory.

### Required database

| File | Size | Download |
|------|------|----------|
| `historical_validation_2020-07_to_2022-12.db` | 314 MB | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/historical_validation_2020-07_to_2022-12.db) |

This single database contains every classified treatment report needed to reproduce the paper's figures and tables. See [Provenance of the analysis database](#provenance-of-the-analysis-database) below for how it was built.

### Optional databases (for transparency, not required for reproduction)

These are the source databases from the original per-drug pipeline runs. Their classifications are already merged into `historical_validation_2020-07_to_2022-12.db`. They are published here so reviewers can verify that no rows were lost or altered during merging.

| File | Size | Download |
|------|------|----------|
| `famotidine_loratadine_prednisone_may_sept_2021.db` | 51 MB | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/famotidine_loratadine_prednisone_may_sept_2021.db) |
| `paxlovid_pre_stop_pasc_4mo.db` | 59 MB | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/paxlovid_pre_stop_pasc_4mo.db) |
| `colchicine_naltrexone_year_2021.db` | 123 MB | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/colchicine_naltrexone_year_2021.db) |
| `naltrexone_jan_2022.db` | 15 MB | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/naltrexone_jan_2022.db) |
| `corpus_baseline_onemonth.db` | 12 MB | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/corpus_baseline_onemonth.db) |

### Raw Reddit JSON (input to the SQLite DBs)

Pre-classification Reddit data — every post and every comment in the scrape windows with no filtering. Reviewers who want to verify that the SQLite DBs are faithful representations of the underlying scrape can rebuild the DBs from these JSON files using `src/import_posts.py`.

| File | Size | Download |
|------|------|----------|
| `historical_validation_2020-07_to_2022-12.json` | 361 MB | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/raw/historical_validation_2020-07_to_2022-12.json) |
| `famotidine_loratadine_prednisone_may_sept_2021.json` | 45 MB | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/raw/famotidine_loratadine_prednisone_may_sept_2021.json) |
| `paxlovid_pre_stop_pasc_4mo.json` | 50 MB | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/raw/paxlovid_pre_stop_pasc_4mo.json) |
| `colchicine_naltrexone_year_2021.json` | 107 MB | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/raw/colchicine_naltrexone_year_2021.json) |
| `naltrexone_jan_2022.json` | 12 MB | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/raw/naltrexone_jan_2022.json) |

### Per-drug merged + deduped CSVs (intermediate analysis outputs)

These are the row-level data underlying Figure 1 and Table 3, exported as CSV for transparency. They are derivable directly from the combined database, but are also published as static files so reviewers can spot-check headline numbers without running any code.

For each of the six target drugs, two CSVs:
- `{drug}_reports_merged.csv` — all classified reports for the drug pulled from the combined database, filtered to within the pre-publication window. One row per post.
- `{drug}_reports_dedup.csv` — the same data after applying the per-(user, drug) "most recent + signal-strength tiebreaker" rule. One row per (user, drug); these are the rows directly counted into the % responders in Figure 1.

Plus a one-row-per-drug summary:
- `summary.csv` — the headline numbers (n, % responders, Wilson 95% CI, p-value vs 50%) for each drug.

| File | Download |
|------|----------|
| `summary.csv` | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/merged/summary.csv) |
| `famotidine_reports_merged.csv` / `_dedup.csv` | [merged](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/merged/famotidine_reports_merged.csv) / [dedup](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/merged/famotidine_reports_dedup.csv) |
| `loratadine_reports_merged.csv` / `_dedup.csv` | [merged](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/merged/loratadine_reports_merged.csv) / [dedup](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/merged/loratadine_reports_dedup.csv) |
| `prednisone_reports_merged.csv` / `_dedup.csv` | [merged](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/merged/prednisone_reports_merged.csv) / [dedup](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/merged/prednisone_reports_dedup.csv) |
| `naltrexone_reports_merged.csv` / `_dedup.csv` | [merged](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/merged/naltrexone_reports_merged.csv) / [dedup](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/merged/naltrexone_reports_dedup.csv) |
| `paxlovid_reports_merged.csv` / `_dedup.csv` | [merged](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/merged/paxlovid_reports_merged.csv) / [dedup](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/merged/paxlovid_reports_dedup.csv) |
| `colchicine_reports_merged.csv` / `_dedup.csv` | [merged](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/merged/colchicine_reports_merged.csv) / [dedup](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/merged/colchicine_reports_dedup.csv) |

### Reproduce

```bash
# Prerequisites: Python 3.10+
pip install -r requirements.txt

# Download the single required database (~314 MB)
mkdir -p data
curl -L -o data/historical_validation_2020-07_to_2022-12.db \
    https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/historical_validation_2020-07_to_2022-12.db

# Reproduce all figures
python _build_paper_figures.py
```

The build writes `output/paper_figures.html`, `output/figure1.png`, and the executed notebook. Open `output/paper_figures.html` in any browser.

---

## What This Reproduces

| Output | What it shows |
|--------|---------------|
| **Figure 1** | A horizontal bar chart showing, for each drug, what percentage of users reported a positive experience (green) vs. everything else (red). Error bars show the range of plausible values. The right margin labels each drug with whether the clinical trial found it effective ("trial: positive") or not ("trial: null"). |
| **Table 2** | Where the data came from: the date range, how many users and reports per drug, and which clinical trial each drug is being compared against. |
| **Table 3** | The numbers behind Figure 1 in table form: for each drug, the sample size, the percentage who responded positively, the confidence interval around that percentage, and a p-value testing whether it's meaningfully different from a coin flip (50/50). |

---

## Files

### Scripts

| File | What it does |
|------|--------------|
| `_build_paper_figures.py` | The main script. Reads the combined database, runs the analysis, and produces a Jupyter notebook with Figure 1, Table 2, and Table 3. Run this to reproduce everything. |
| `build_notebook.py` | A helper that `_build_paper_figures.py` uses to create and execute Jupyter notebooks. You don't need to touch this. |
| `requirements.txt` | Python packages needed. Install with `pip install -r requirements.txt`. |

### Databases

| File | Size | Drugs covered | Date Range | Role in this analysis |
|------|------|---------------|------------|-----------------------|
| `historical_validation_2020-07_to_2022-12.db` | 314 MB | all 6 drugs | Jul 2020 – Dec 2022 | **Required.** The single self-sufficient analysis database. All figures and tables in this paper are produced from this one DB. |
| `famotidine_loratadine_prednisone_may_sept_2021.db` | 51 MB | famotidine, loratadine, prednisone | May – Dec 2021 | *Optional, transparency only.* Original focused pipeline run for the Glynne and Utrero-Rico comparators. All its in-window classifications are already present in the combined DB. |
| `paxlovid_pre_stop_pasc_4mo.db` | 59 MB | paxlovid | Mar – Jun 2024 | *Optional, transparency only.* 4 months of discussion ending at the STOP-PASC publication. Outside the end-2022 analysis cap, so not used for the paper's primary numbers; published for transparency. |
| `colchicine_naltrexone_year_2021.db` | 123 MB | colchicine, naltrexone (partial) | Jan – Dec 2021 | *Optional, transparency only.* All its in-window classifications are already present in the combined DB. |
| `naltrexone_jan_2022.db` | 15 MB | naltrexone (partial) | Jan 2022 | *Optional, transparency only.* All its in-window classifications are already present in the combined DB. |
| `corpus_baseline_onemonth.db` | 12 MB | all drugs | One-month sample | *Optional, context only.* A broad sample used to characterize the overall positive-sentiment rate across all drugs on the subreddit. Not directly required for Figure 1 / Table 3. |

**What's in each database:** Every database has the same schema — `users`, `posts` (the Reddit posts), `treatment` (drug names and their known aliases/brand names), and `treatment_reports` (the extracted sentiment: did this user say positive, negative, neutral, or mixed things about this drug?). The analysis joins these tables together.

**Why one combined DB plus the originals:** The combined database was constructed for this paper by merging classifications from a master pipeline run (covering 2020-07-24 → 2022-12-31, all six drugs) with a small number of additional classifications from the earlier per-drug pipeline runs that the master run's substring filter missed (~3% of total). The original per-drug DBs are preserved on S3 unchanged so reviewers can independently verify the merge. See *Provenance of the analysis database* below for the full construction.

---

## Pre-publication cutoffs

For each drug, "pre-publication" is defined as the day before the comparator paper was first publicly released. Where a medRxiv preprint preceded the journal publication, the preprint date is the binding cutoff. Cutoffs:

| Drug | Cutoff | Source |
|------|--------|--------|
| famotidine, loratadine | 2021-06-06 | Glynne et al., medRxiv preprint 2021-06-07 |
| prednisone | 2021-10-25 | Utrero-Rico et al., *Biomedicines* online 2021-10-26 |
| naltrexone | 2022-07-02 | O'Kelly et al., *BBI Health* online 2022-07-03 |
| paxlovid | 2024-06-06 | STOP-PASC / Geng et al., *JAMA Intern Med* 2024-06-07 |
| colchicine | 2025-11-30 | Bassi et al., *JAMA Intern Med* 2025-12-01 |

**End-of-2022 cap.** This analysis additionally restricts all per-drug data to posts dated on or before 2022-12-31. For famotidine, loratadine, prednisone, and naltrexone the comparator publication is the binding cutoff and the cap has no effect. For paxlovid and colchicine the cap is binding — their primary numbers reflect approximately 1.5 to 2.5 years of data ending in late 2022.

---

## How the Analysis Works

### Step 1: Pull all reports per drug

For each target drug, we pull every classified `treatment_report` row from the combined SQLite database. No cross-DB merging is required at analysis time — the single database is self-sufficient (see *Provenance of the analysis database* above).

### Step 2: Filter to the pre-publication window

Posts dated after the drug's pre-publication cutoff (or after end of 2022, whichever is earlier) are dropped.

### Step 3: One vote per user per drug — "most recent + signal-strength tiebreaker" dedup

Many users mention the same drug multiple times across different posts. To avoid counting one person's opinion multiple times, each user contributes exactly **one data point per drug**. The rule:

1. **Most recent post wins** (post_date descending). The patient's settled view at their latest post is the canonical answer.
2. **For posts on the same date, the strongest signal wins** (strong > moderate > weak > n/a). Ties on date are broken by which report was more confident.

This rule is symmetric on sentiment direction — a single positive report cannot override later non-positive reports the way an older "best-report" rule would.

### Step 4: Classify as responder or non-responder

- **Responder**: the user's selected report has `positive` sentiment.
- **Non-responder**: the selected report is `negative`, `neutral`, or `mixed`.

We group these because the question is simply: did the drug clearly help, or not?

### Step 5: Confidence intervals (the error bars on Figure 1)

We report **Wilson score 95% confidence intervals** for each proportion. Wilson intervals work well at the boundaries (close to 0% or 100%) and with small samples, where the simpler "Wald" interval can produce nonsensical values.

### Step 6: Is it different from a coin flip?

For each drug, we run a **two-sided binomial test** against a 50% null. The p-value is the probability of observing a result at least this far from 50/50 if positive and non-positive reports were equally likely.

- A small p-value (e.g., < 0.05) means the community signal is unlikely to be random.
- A large p-value (e.g., > 0.5) means we can't reject the null — the community was roughly split.

### Step 7: Only data from before the trial published

This is the key constraint. For each drug, we only count posts from **before** the relevant clinical trial was first publicly available. This ensures the community signal couldn't have been influenced by trial results — it's genuinely predictive, not reactive.

---

## Expected Output (for spot-checking)

If everything ran correctly, Table 3 should show these values:

| Drug | n (users) | % Responders | 95% CI | p-value | Trial Result |
|------|-----------|--------------|--------|---------|--------------|
| loratadine | 97 | 80.4% | [71.4, 87.1] | < 0.0001 | positive |
| famotidine | 248 | 76.6% | [71.0, 81.5] | < 0.0001 | positive |
| naltrexone | 199 | 64.8% | [58.0, 71.1] | < 0.0001 | positive |
| colchicine | 114 | 57.0% | [47.8, 65.7] | 0.16 | null |
| paxlovid | 196 | 54.1% | [47.1, 60.9] | 0.28 | null |
| prednisone | 418 | 49.3% | [44.5, 54.1] | 0.81 | null |

The pattern: every drug where the community clearly leaned positive (loratadine, famotidine, naltrexone) corresponds to a trial that found a positive result — and every comparison reaches p < 0.0001. Every drug where the community was roughly split (colchicine, paxlovid, prednisone) corresponds to a trial that found no significant effect — none reach significance against the 50% null. All 6 directional comparisons match the eventual trial outcome.

---

## Provenance of the analysis database

The single database `historical_validation_2020-07_to_2022-12.db` was constructed for this analysis in two stages:

1. **Master pipeline run.** We scraped r/covidlonghaulers from corpus inception (2020-07-24) through end of 2022 using the Arctic Shift archive, and ran the classification pipeline once per target drug using the `--drug` flag. The `--drug` flag substring-filters posts against the drug's known aliases before LLM extraction, which kept the API cost tractable (~$15 total across the six runs) and the wall time short (~2 hours). This step produced classifications for the bulk of relevant posts.

2. **Backfill from earlier per-drug runs.** A small number of posts (~260 across the six drugs, roughly 3% of total) had been classified in earlier focused per-drug pipeline runs (`famotidine_loratadine_prednisone_may_sept_2021.db`, etc.) but were not picked up by the master pipeline's substring filter. To make this database self-sufficient, we copied those classifications into the combined database, leaving the original DBs unchanged. The merge is implemented in `scripts/build_combined_db.py`; rows from earlier runs are tagged with a synthetic `extraction_runs` row so the provenance is recoverable from the database itself.

After this construction, the entire historical validation analysis can be reproduced from a single database — no merging across DBs at analysis time. We verified that running the analysis directly on the combined DB produces identical numbers to the merge-across-DBs approach used during methodological development.

Both the combined database and the original per-drug DBs are uploaded to S3 — see the Download section above. Only the combined database is required to reproduce the figures and tables.

---

## Original Database Names

For reference, the databases were renamed from the original pipeline for clarity:

| Original | Renamed To |
|----------|------------|
| `may_sept_2021.db` | `famotidine_loratadine_prednisone_may_sept_2021.db` |
| `4mo_pre_stop_pasc.db` | `paxlovid_pre_stop_pasc_4mo.db` |
| `year_2021.db` | `colchicine_naltrexone_year_2021.db` |
| `jan_2022.db` | `naltrexone_jan_2022.db` |
| `polina_onemonth.db` | `corpus_baseline_onemonth.db` |
| (new, combined for this paper) | `historical_validation_2020-07_to_2022-12.db` |
