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

To regenerate everything from scratch, you need the underlying SQLite databases (~580 MB total, not included in this repo). Download them from the links below and place them in a `data/` subfolder.

### Download the databases

| File | Size | Download |
|------|------|----------|
| `master_gap_2020-07_to_2022-12.db` | 314 MB | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/master_gap_2020-07_to_2022-12.db) |
| `famotidine_loratadine_prednisone_may_sept_2021.db` | 51 MB | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/famotidine_loratadine_prednisone_may_sept_2021.db) |
| `paxlovid_pre_stop_pasc_4mo.db` | 59 MB | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/paxlovid_pre_stop_pasc_4mo.db) |
| `colchicine_naltrexone_year_2021.db` | 123 MB | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/colchicine_naltrexone_year_2021.db) |
| `naltrexone_jan_2022.db` | 15 MB | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/naltrexone_jan_2022.db) |
| `corpus_baseline_onemonth.db` | 12 MB | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/corpus_baseline_onemonth.db) |

The raw (pre-processed) Reddit JSON data is also available:

| File | Download |
|------|----------|
| `famotidine_loratadine_prednisone_may_sept_2021.json` | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/raw/famotidine_loratadine_prednisone_may_sept_2021.json) |
| `paxlovid_pre_stop_pasc_4mo.json` | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/raw/paxlovid_pre_stop_pasc_4mo.json) |
| `colchicine_naltrexone_year_2021.json` | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/raw/colchicine_naltrexone_year_2021.json) |
| `naltrexone_jan_2022.json` | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/raw/naltrexone_jan_2022.json) |

### Reproduce

```bash
# Prerequisites: Python 3.10+
pip install -r requirements.txt

# Reproduce all figures
python _build_paper_figures.py
```

---

## What This Reproduces

| Output | What it shows |
|--------|---------------|
| **Figure 1** | A horizontal bar chart showing, for each drug, what percentage of users reported a positive experience (green) vs. everything else (red). Error bars show the range of plausible values. The right margin labels each drug with whether the clinical trial found it effective ("trial: positive") or not ("trial: null"). |
| **Table 2** | Where the data came from: which databases, what date range, how many users/reports per drug, and which trial it's being compared to. |
| **Table 3** | The numbers behind Figure 1 in table form: for each drug, the sample size, the percentage who responded positively, the confidence interval around that percentage, and a p-value testing whether it's meaningfully different from a coin flip (50/50). |

---

## Files

### Scripts

| File | What it does |
|------|--------------|
| `_build_paper_figures.py` | The main script. Reads the databases, runs the analysis, and produces a Jupyter notebook with Figure 1, Table 2, and Table 3. Run this to reproduce everything. |
| `build_notebook.py` | A helper that `_build_paper_figures.py` uses to create and execute Jupyter notebooks. You don't need to touch this. |
| `requirements.txt` | Python packages needed. Install with `pip install -r requirements.txt`. |

### Databases

All databases are **full, unmodified copies** of the SQLite databases used in the analysis. They are included in full so you can verify that nothing was excluded or filtered at the database level. All data was scraped from the public subreddit r/covidlonghaulers.

| File | Size | Drugs covered | Date Range | Why this window |
|------|------|---------------|------------|-----------------|
| `master_gap_2020-07_to_2022-12.db` | 314 MB | all 6 drugs | Jul 2020 – Dec 2022 | Built specifically for this analysis: covers the entire pre-publication window for each drug from the corpus inception through end of 2022. The pipeline was run once with `--drug` per target drug, leveraging substring-prefiltering for efficiency. |
| `famotidine_loratadine_prednisone_may_sept_2021.db` | 51 MB | famotidine, loratadine, prednisone | May – Dec 2021 | Original focused window for Glynne (June 2021 preprint) and Utrero-Rico (Oct 2021) comparators. Also contains cetirizine, which is excluded from the analysis because there is no direct comparator trial. |
| `paxlovid_pre_stop_pasc_4mo.db` | 59 MB | paxlovid | Mar – Jun 2024 | 4 months of discussion ending at the STOP-PASC trial publication (Jun 2024). Outside the end-2022 cap used in this analysis, so currently unused for paxlovid's primary numbers. |
| `colchicine_naltrexone_year_2021.db` | 123 MB | colchicine, naltrexone (partial) | Jan – Dec 2021 | Full year 2021. Pre-dates Bassi et al. (Dec 2025) for colchicine and provides the first portion of naltrexone data. |
| `naltrexone_jan_2022.db` | 15 MB | naltrexone (partial) | Jan 2022 | Extends naltrexone coverage through Jan 2022, before O'Kelly et al. (Jul 2022). Combined with the year_2021 database above. |
| `corpus_baseline_onemonth.db` | 12 MB | all drugs | One-month sample | A broad sample used to compute the overall positive rate across all drugs on the subreddit, for context. |

**What's in each database:** Every database has the same structure — `users`, `posts` (the Reddit posts), `treatment` (drug names and their known aliases/brand names), and `treatment_reports` (the extracted sentiment: did this user say positive, negative, neutral, or mixed things about this drug?). The analysis joins these tables together.

**Why multiple databases:** The original pipeline was run multiple times with different time windows and `--drug` filters. To reproduce the paper's figures we merge across all of them, deduping on `post_id` so each post is counted exactly once. When the same post appears in multiple databases, the `master_gap` classification takes priority (most recent pipeline run, consistent prompts).

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

### Step 1: Merge all databases per drug

For each target drug, we pull every classified `treatment_report` row across all databases listed above. When the same post appears in multiple databases, we keep the master_gap version.

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

## Master gap database

The `master_gap_2020-07_to_2022-12.db` database was built specifically for this analysis. The original per-drug pipelines were focused on narrower windows (covering about a year of pre-publication data each), but for the headline comparison we wanted all available pre-publication data for every drug. We re-scraped r/covidlonghaulers from inception (2020-07-24) through end of 2022 and ran the pipeline once per target drug using the `--drug` flag, which substring-filters posts against the drug's known aliases before extraction. This kept the LLM cost tractable (~$15 in OpenRouter API charges) and the wall time short (~2 hours) while producing classifications for all six drugs across the full window.

The master_gap database is uploaded to S3 alongside the other databases — see the Download section above.

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
| (new) | `master_gap_2020-07_to_2022-12.db` |
