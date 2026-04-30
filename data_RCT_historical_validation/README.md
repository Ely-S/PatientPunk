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

To regenerate everything from scratch, you need the underlying SQLite databases (~260 MB, not included in this repo). Contact the authors to obtain the data files, then place them in `data/`.

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
| **Table 2** | Where the data came from: which database, what date range, how many posts/users/reports per drug, and which trial it's being compared to. |
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

| File | Size | Drugs | Date Range | Why this window |
|------|------|-------|------------|-----------------|
| `famotidine_loratadine_prednisone_may_sept_2021.db` | 51 MB | famotidine, loratadine, prednisone | May – Sep 2021 | Pre-dates Glynne et al. (published Oct 2021). Also contains cetirizine data, which is excluded from the analysis because there is no direct trial to compare it to. |
| `paxlovid_pre_stop_pasc_4mo.db` | 59 MB | paxlovid | Mar – Jun 2024 | 4 months of discussion ending at the STOP-PASC trial publication (Jun 2024). |
| `colchicine_naltrexone_year_2021.db` | 123 MB | colchicine, naltrexone (partial) | Jan – Dec 2021 | Full year 2021. Pre-dates Bassi et al. (2025) for colchicine. Also provides the first portion of naltrexone data. |
| `naltrexone_jan_2022.db` | 15 MB | naltrexone (partial) | Jan 2022 | Extends naltrexone coverage through Jan 2022, before O'Kelly et al. (Jul 2022). Combined with the year_2021 database above. |
| `corpus_baseline_onemonth.db` | 12 MB | all drugs | One-month sample | A broad sample used to compute the overall positive rate across all drugs on the subreddit (~65.8%), for context. |

**What's in each database:** Every database has the same structure — `users`, `posts` (the Reddit posts), `treatment` (drug names and their known aliases/brand names), and `treatment_reports` (the extracted sentiment: did this user say positive, negative, neutral, or mixed things about this drug?). The analysis joins these tables together.

---

## How the Analysis Works

### Step 1: One vote per user per drug

Many users mention the same drug multiple times across different posts. To avoid counting one person's opinion multiple times, each user contributes exactly **one data point per drug** — their "best" report. The ranking: positive > mixed > neutral > negative. If there's a tie (e.g., two positive reports), signal strength breaks it: strong > moderate > weak.

### Step 2: Classify as responder or non-responder

- **Responder**: the user's best report for this drug is `positive` (they said it helped).
- **Non-responder**: anything else — `negative` (it made things worse), `neutral` (no outcome expressed), or `mixed` (some good, some bad). We group these together because the question is simply: did the drug clearly help, or not?

### Step 3: Confidence intervals (the error bars on Figure 1)

A percentage from a small sample isn't exact — if 50 out of 76 users (65.8%) said naltrexone helped, the true proportion could plausibly be anywhere from about 55% to 76%. The error bars show this range.

We use **Wilson score intervals**, which are a way of computing this range that works well even when the sample is small or the percentage is close to 0% or 100%. (The simpler textbook method — called "Wald intervals" — can give nonsensical results like negative percentages in those cases. Wilson intervals don't have that problem.)

### Step 4: Is it different from a coin flip?

For each drug, we run a **binomial test** asking: if responders and non-responders were equally likely (50/50), how surprising would this result be? The **p-value** is the probability of seeing a result this extreme by chance alone.

- A small p-value (e.g., < 0.05) means the split is unlikely to be random — the community genuinely leaned one way.
- A large p-value (e.g., 0.63) means we can't rule out chance — the community was roughly split.

### Step 5: Only data from before the trial published

This is the key constraint. For each drug, we only count posts from **before** the relevant clinical trial was published. This ensures the community signal couldn't have been influenced by the trial results — it's genuinely predictive, not reactive.

---

## Expected Output (for spot-checking)

If everything ran correctly, Table 3 should show these values:

| Drug | n (users) | % Responders | p-value | Trial Result |
|------|-----------|-------------|---------|--------------|
| famotidine | 207 | 78.7% | < 0.001 | positive |
| loratadine | 107 | 68.2% | 0.0011 | positive |
| naltrexone | 76 | 65.8% | 0.0082 | positive |
| colchicine | 40 | 62.5% | 0.1537 | null |
| paxlovid | 153 | 52.3% | 0.6588 | null |
| prednisone | 176 | 52.3% | 0.6264 | null |

The pattern: drugs where the community clearly leaned positive (famotidine, loratadine, naltrexone) correspond to trials that found positive results. Drugs where the community was roughly split (paxlovid, prednisone, colchicine) correspond to trials that found no significant effect. All 6 match.

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
