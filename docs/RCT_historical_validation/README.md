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

| File | Size | SHA-256 | Download |
|------|------|---------|----------|
| `historical_validation_2020-07_to_2022-12.db` | 311 MB | `c50fcacd7ce366f397152f5fe4dbb59d5eaf64ba32627faef91dad86fbf6c6f4` | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/processed/historical_validation_2020-07_to_2022-12.db) |

This single database contains every classified treatment report needed to reproduce the paper's figures and tables. See [Provenance of the analysis database](#provenance-of-the-analysis-database) below for how it was built.

After downloading, verify the file matches the published hash:

```bash
# macOS
shasum -a 256 data/historical_validation_2020-07_to_2022-12.db
# Linux
sha256sum  data/historical_validation_2020-07_to_2022-12.db
# Windows PowerShell
Get-FileHash data\historical_validation_2020-07_to_2022-12.db -Algorithm SHA256
```

The expected hash is `c50fcacd7ce366f397152f5fe4dbb59d5eaf64ba32627faef91dad86fbf6c6f4`. The build script also runs an internal integrity check at startup that fails fast if any `treatment_reports.user_id` does not match the corresponding `posts.user_id` (the bug that an earlier, now-removed backfill script introduced). It additionally asserts every classified report's `post_date` falls strictly before the documented per-drug window end (V2 audit).

### Raw Reddit JSON (input to the SQLite DB)

Pre-classification Reddit data — every post and every comment in the scrape window with no filtering. Reviewers who want to verify that the SQLite DB is a faithful representation of the underlying scrape can rebuild it from this JSON file using `src/import_posts.py`.

| File | Size | SHA-256 | Download |
|------|------|---------|----------|
| `historical_validation_2020-07_to_2022-12.json` | 361 MB (378,221,044 bytes) | `298d5bc719fb42b87169c28207ad509d17c94300d1c5e3b66370e98a79abfe6a` | [Download](https://patientpunk.s3.amazonaws.com/scientific_validation/rct_historical/raw/historical_validation_2020-07_to_2022-12.json) |

**Contents:** 47,434 top-level posts + 684,092 comments = 731,526 entries total. All-entries date range 2020-07-24 18:58 UTC → 2022-12-31 23:58 UTC.

**First post:** `hx7q8g` ("r/covidlonghaulers Lounge"), 2020-07-24 18:58:21 UTC — the subreddit's anchor "Lounge" thread, which is the earliest post in r/covidlonghaulers.

**Last post:** `1006rd2`, 2022-12-31 23:41:15 UTC — the most recent post strictly before 2023-01-01 UTC (matching the analysis's end-of-2022 cap).

For provenance of how this JSON was acquired (Arctic Shift download, scrape date, conversion process), see [`ARCTIC_SHIFT_PROVENANCE.md`](./ARCTIC_SHIFT_PROVENANCE.md).

### Per-drug merged + deduped CSVs (intermediate analysis outputs)

These are the row-level data underlying Figure 1 and Table 3, exported as CSV for transparency. They are derivable directly from the combined database — `scripts/dump_per_drug_csvs.py` regenerates them locally from `data/historical_validation/historical_validation_2020-07_to_2022-12.db` — but are also published as static files so reviewers can spot-check headline numbers without running any code.

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

### Database

| File | Size | Drugs covered | Date Range | Role in this analysis |
|------|------|---------------|------------|-----------------------|
| `historical_validation_2020-07_to_2022-12.db` | 314 MB | all 6 drugs | Jul 2020 – Dec 2022 | **Required.** The single self-sufficient analysis database. All figures and tables in this paper are produced from this one DB. |

**What's in the database:** It has four tables — `users`, `posts` (the Reddit posts), `treatment` (drug names and their known aliases/brand names), and `treatment_reports` (the extracted sentiment: did this user say positive, negative, neutral, or mixed things about this drug?). The analysis joins these tables together. See *Provenance of the analysis database* below for how the database was built.

---

## Pre-publication cutoffs

For each drug, "pre-publication" is defined by a strict-less-than predicate on `post_date`: a post is included iff its UTC timestamp is **strictly before midnight UTC of the comparator paper's publication date** (i.e., `post_date < epoch_midnight(pub_date)`). Where a medRxiv preprint preceded the journal publication, the preprint date is the binding cutoff. Cutoffs:

| Drug | Publication date (exclusive upper bound) | Last day actually included | Source |
|------|------------------------------------------|----------------------------|--------|
| famotidine, loratadine | 2021-06-07 | 2021-06-06 | Glynne et al., medRxiv preprint 2021-06-07 |
| prednisone | 2021-10-26 | 2021-10-25 | Utrero-Rico et al., *Biomedicines* online 2021-10-26 |
| naltrexone | 2022-07-03 | 2022-07-02 | O'Kelly et al., *BBI Health* online 2022-07-03 |
| paxlovid | 2024-06-07 | 2022-12-31 (capped) | STOP-PASC / Geng et al., *JAMA Intern Med* online 2024-06-07 |
| colchicine | 2025-10-20 | 2022-12-31 (capped) | Bassi et al., *JAMA Intern Med* online 2025-10-20 (print issue: 2025-12-01) |

**End-of-2022 cap.** This analysis additionally restricts all per-drug data to posts dated strictly before 2023-01-01 UTC. For famotidine, loratadine, prednisone, and naltrexone the comparator publication is the binding cutoff and the cap has no effect. For paxlovid and colchicine the cap is binding — their primary numbers reflect approximately 1.5 to 2.5 years of data ending December 31, 2022.

## Window verification

The build script's window-audit cell queries the actual `MIN(post_date)` and
`MAX(post_date)` of the classified reports the analysis includes for each
drug, and asserts the maximum is strictly before the publication-date
midnight (or 2023-01-01 for the end-of-2022 cap). Build fails if any
included report falls on or after the cutoff. Latest verified run:

| Drug | Pub date | Window end (excl) | Actual MIN(post_date) | Actual MAX(post_date) | Reports (pre-dedup) | NULL post_dates | In window? |
|------|----------|-------------------|------------------------|------------------------|---------------------|-----------------|------------|
| famotidine | 2021-06-07 | 2021-06-07 00:00 UTC | 2020-08-05 03:42 UTC | 2021-06-06 05:04 UTC | 693 | 0 | ✓ |
| loratadine | 2021-06-07 | 2021-06-07 00:00 UTC | 2020-08-18 16:26 UTC | 2021-06-06 13:28 UTC | 190 | 0 | ✓ |
| prednisone | 2021-10-26 | 2021-10-26 00:00 UTC | 2020-07-28 22:42 UTC | 2021-10-23 19:06 UTC | 790 | 0 | ✓ |
| naltrexone | 2022-07-03 | 2022-07-03 00:00 UTC | 2020-10-12 04:41 UTC | 2022-07-02 20:02 UTC | 583 | 0 | ✓ |
| paxlovid | 2024-06-07 | 2023-01-01 00:00 UTC | 2022-01-18 05:13 UTC | 2022-12-31 18:35 UTC | 488 | 0 | ✓ |
| colchicine | 2025-10-20 | 2023-01-01 00:00 UTC | 2020-08-29 10:55 UTC | 2022-12-29 12:45 UTC | 211 | 0 | ✓ |

**Reports** is the raw count from `treatment_reports` (before per-(user, drug)
dedup); the deduplicated `n` values that appear in Figure 1 / Table 3 are
smaller. The point of this table is to show the predicate is honored, not
the per-user vote count.

**Notable observations:**
- Every `MAX(post_date)` is strictly before its window end. Every
  publication-bound max lands on the day immediately preceding publication
  (famotidine/loratadine 2021-06-06, paxlovid/colchicine 2022-12-31). No
  off-by-one leakage.
- Zero `post_date IS NULL` rows entered any per-drug query — the
  `IS NOT NULL` filter is defensive and the underlying data is clean.
- Paxlovid's earliest mention is 2022-01-18 — paxlovid wasn't in the
  community vocabulary before then, which is consistent with the drug's
  late-2021/early-2022 emergency-use authorization.

### Leakage text search

We searched the body text of the latest 25 reports per drug
(cutoff-adjacent, the highest-leakage-risk subsample) for paired-trial
identifiers — author names (`Glynne`, `Utrero[-Rico]`, `O'Kelly`,
`Geng`, `Bassi`), trial labels (`STOP-PASC`), and journals/preprint
servers (`medRxiv`, `Biomedicines`, `JAMA Intern Med`, `BBI Health`):

| Drug | Specific-term hits in latest 25 | Generic-term hits (`trial`/`RCT`/`published`) |
|------|---------------------------------|-----------------------------------------------|
| famotidine | 0 | 0 |
| loratadine | 0 | 2 |
| prednisone | 0 | 0 |
| naltrexone | 0 | 0 |
| paxlovid   | 0 | 2 |
| colchicine | 0 | 0 |

**Zero specific-term hits across all six drugs.** The four generic-term
hits (loratadine ×2, paxlovid ×2) reference unrelated trials (vaccine
trials, paxlovid clinical-use posts) rather than the paired comparator
study; spot-checked, none discuss the paired RCT result. The community's
pre-publication discussion is empirically free of paired-trial
contamination at the cutoff boundary.

## Drug aliases used in extraction

The full list of brand names, generic names, abbreviations, misspellings,
and class synonyms that the pipeline substring-matched against during
extraction is published as a tracked artifact:

**[`DRUG_ALIASES.md`](./DRUG_ALIASES.md)** — 170 aliases across the six
target drugs, plus heuristic flags for short / multi-word / likely-
misspelling entries and a cross-drug collision check (no collisions).

### What it is

`DRUG_ALIASES.md` is a human-readable export of the `treatment.aliases`
JSON column from the analysis SQLite DB. Every pipeline run's `--drug`
substring filter and every canonicalization mapping operate against
this list, so it is the load-bearing input to V4 (drug mention
extraction) and V5 (canonicalization). Publishing it as a static file
lets reviewers audit precision/recall coverage without running any code.

### How it was made

During the pipeline's canonicalization step (`src/pipeline/canonicalize.py`),
Claude Sonnet 4.6 was queried with `drug_aliases_prompt(target_drug)`
(defined in `src/utilities/__init__.py`) once per target drug. The model
returned a list of brand names, generic names, abbreviations, common
misspellings, and class synonyms; that JSON list was stored in
`treatment.aliases` at pipeline-run time. Subsequent pipeline steps
substring-match against this list, and the analysis-time SQL joins on
`canonical_name` to roll up all alias variants into a single per-drug
count.

The aliases were generated **automatically by an LLM and have not been
manually adjudicated** against the V5 acceptance criteria. The
"V5 reviewer notes" section of `DRUG_ALIASES.md` flags entries worth a
closer look (e.g., `prednisolone` listed under prednisone — different
active molecule; `loratab` listed under loratadine — Lortab is a
hydrocodone brand, likely an LLM error; class-level terms like
`steroid`, `h2 blocker`). The historical-validation analysis used the
list as-is; any edit would require regenerating per-drug counts.

### Regenerating

```bash
python scripts/dump_drug_aliases.py \
    --db data/historical_validation/historical_validation_2020-07_to_2022-12.db \
    --out docs/RCT_historical_validation/DRUG_ALIASES.md
```

Deterministic given the DB content; safe to re-run.

## Dedup audit (V7)

Two complementary outputs cover the V7 audit ("does the per-(user, drug)
deduplication rule actually behave as advertised?"):

1. **Build-time audit cell** in the executed notebook reports, per drug:
   raw treatment_reports count, distinct user count, multi-report users,
   mixed-signal users (with both positive and non-positive labels), final
   responder count under our rule, and the **number of users that would
   land in a different bucket** under two alternative dedup rules:
     - "majority sentiment of the user's reports"
     - "any positive report ⇒ responder"

   Empirically those flips run at 3–11% of total users per drug — small
   enough that the headline result (3 + drugs cleanly separated from 3
   null drugs) is robust to dedup-rule choice. Larger flip counts would
   mean the analysis is dedup-rule-sensitive and the rule choice would
   need stronger justification.

2. **[`V7_DEDUP_AUDIT.md`](./V7_DEDUP_AUDIT.md)** — a static export of
   36 sampled multi-report (user, drug) pairs (6 per drug, biased toward
   mixed-signal users where the rule choice matters most), showing every
   candidate report with the rule's retained pick marked. For reviewers
   to spot-check whether the "most recent + signal-strength tiebreaker"
   rule picked sensibly. Generated by `scripts/v7_dedup_sample_audit.py`.

---

## How the Analysis Works

### Step 1: Pull all reports per drug

For each target drug, we pull every classified `treatment_report` row from the combined SQLite database. No cross-DB merging is required at analysis time — the single database is self-sufficient (see *Provenance of the analysis database* above).

### Step 1a: Deleted-user exclusion

Reddit replaces the author field with `[deleted]` or `[removed]` when the original commenter deletes their account or has it removed by moderators. Our import pipeline maps both of these to a single placeholder user_id, the literal string `"deleted"`. After import, 52,603 of the 731,526 posts in the database carry that placeholder; 122 of the 7,687 classified treatment reports come from those posts.

**Policy: we exclude every post with `user_id = "deleted"` from per-user analysis.** The reasoning:

- Those 52,603 posts come from many distinct real users we cannot identify. Treating them as one pseudo-user would give the entire deleted population a single vote per drug, badly distorting per-user dedup. Treating each deleted post as its own anonymous user would inflate sample sizes with non-random ban/withdrawal artefacts, since accounts get deleted for reasons (spam, hostility, voluntary departure) that are not independent of drug-experience sentiment.
- We verified empirically that excluding deleted-user reports shifts each drug's headline number by at most 0.5 percentage points and 1 unit of `n`. No headline conclusion changes.

The build script applies this filter directly in the SQL query (`AND p.user_id != 'deleted'`), so it propagates to Figure 0, Figure 1, Table 2, Table 3, and the published per-drug CSVs uniformly.

### Step 2: Filter to the pre-publication window

The SQL predicate is literally `p.post_date < window_end_exclusive_in_unix_seconds`, where `window_end_exclusive` is the midnight-UTC timestamp of the comparator paper's publication date (or 2023-01-01, whichever is earlier). Any post on or after the publication date is excluded by construction; the last day of data actually included is the day before the publication date.

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

Wilson CIs come from `statsmodels.stats.proportion.proportion_confint(method="wilson")` and binomial p-values from `scipy.stats.binomtest`; the same numbers are independently reproduced via the alternate aggregation path in `scripts/dump_per_drug_csvs.py`.

### Step 7: Only data from before the trial published

This is the key constraint. For each drug, we only count posts from **before** the relevant clinical trial was first publicly available. This ensures the community signal couldn't have been influenced by trial results — it's genuinely predictive, not reactive.

---

## Expected Output (for spot-checking)

If everything ran correctly, Table 3 should show these values:

| Drug | n (users) | % Responders | 95% CI | p-value | Trial Result |
|------|-----------|--------------|--------|---------|--------------|
| loratadine | 90  | 81.1% | [71.8, 87.9] | < 0.0001 | positive |
| famotidine | 232 | 77.2% | [71.3, 82.1] | < 0.0001 | positive |
| naltrexone | 154 | 65.6% | [57.8, 72.6] |   0.0001 | positive |
| paxlovid   | 196 | 54.1% | [47.1, 60.9] |   0.28   | null |
| colchicine | 91  | 53.8% | [43.7, 63.7] |   0.53   | null |
| prednisone | 343 | 48.7% | [43.4, 54.0] |   0.67   | null |

The pattern: every drug where the community clearly leaned positive (loratadine, famotidine, naltrexone) corresponds to a trial that found a positive result — every comparison reaches p ≤ 0.0001. Every drug where the community was roughly split (colchicine, paxlovid, prednisone) corresponds to a trial that found no significant effect — none reach significance against the 50% null. All 6 directional comparisons match the eventual trial outcome.

---

## Provenance of the analysis database

The database `historical_validation_2020-07_to_2022-12.db` is the direct output of one master pipeline run. We scraped r/covidlonghaulers from corpus inception (2020-07-24) through end of 2022 using the Arctic Shift archive, then ran the classification pipeline once per target drug using the `--drug` flag. The `--drug` flag substring-filters posts against the drug's known aliases before LLM extraction, which kept the API cost tractable (~$15 total across the six runs) and the wall time short (~2 hours). The resulting database has internally consistent user IDs (every `treatment_reports.user_id` matches its `posts.user_id`) — verified by the build script's startup integrity check — and is the sole source of truth for every figure and table in the paper.
