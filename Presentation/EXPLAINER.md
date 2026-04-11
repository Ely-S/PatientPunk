# PatientPunk

**Turning patient Reddit posts into queryable biomedical evidence.**

---

## The Problem

Patients with chronic and poorly-understood conditions — Long COVID, ME/CFS, POTS, EDS, PSSD — often discover treatments through peer communities years before clinical trials catch up. This knowledge is real, it is detailed, and it is completely unstructured.

Millions of posts on Reddit contain first-person treatment reports: what people tried, whether it helped, how they felt, what conditions they have. No tool currently extracts this at scale into something a researcher can query.

---

## What PatientPunk Does

PatientPunk is an end-to-end pipeline that:

1. **Scrapes** patient communities from Reddit (via Arctic Shift historical data + live scraping)
2. **Extracts** structured variables from free text using LLMs — drug mentions, sentiment, demographics, conditions
3. **Stores** everything in a unified SQLite database with privacy-preserving hashed user IDs
4. **Runs statistics** using a validated engine covering 11 test types (binomial, Mann-Whitney, logistic regression, Cox survival, propensity matching, and more)
5. **Generates** research notebooks automatically — a Claude skill turns natural-language questions into executable Jupyter notebooks backed by real patient data

---

## The Data

| Subreddit | Posts collected |
|---|---|
| r/covidlonghaulers | 37,000+ posts · 650k comments (2 years) |
| r/ehlersdanlos | 270 posts |
| r/PSSD | 332 posts |
| r/microdosing | 164 posts |
| r/abortion | 385 posts |

Current extraction covers ~1,100 posts from r/covidlonghaulers with **526 treatment sentiment reports** across **177 canonicalized drugs**.

---

## Example Findings (1-month r/covidlonghaulers snapshot)

- **KPV** (a tetrapeptide): 86% positive outcomes, n=7
- **Low Dose Naltrexone**: 60% positive, n=15 — no significant POTS vs. non-POTS difference
- **Tirzepatide**: 38% positive, n=8 — notably mixed/negative signal
- **BPC-157**: 17% positive, n=6 — predominantly negative reports

*All results carry structured caveats about sample size and self-selection bias.*

---

## Why It's Rigorous

- **User-level aggregation** — one data point per user per drug, satisfying statistical independence
- **Structured warnings** — every result flags `small_sample`, `low_epp`, `sparse_cells`, etc. with severity levels (`caveat`, `caution`, `unreliable`)
- **Validated packages** — scipy, statsmodels, pingouin, lifelines, causalinference. No hand-rolled formulas.
- **Reporting bias disclaimer** — appended to every notebook summary automatically

---

## The Stack

| Layer | Technology |
|---|---|
| Scraping | Python · Arctic Shift API |
| Extraction | Anthropic Claude (via OpenRouter) |
| Storage | SQLite |
| Statistics | scipy · statsmodels · pingouin · lifelines · causalinference |
| Notebooks | Jupyter · nbconvert |
| LLM orchestration | Claude Code · Anthropic Agent SDK |

---

## Team

| Person | Role |
|---|---|
| **Eli** | Project lead · research-assistant skill · OpenRouter config |
| **Polina** | Drug sentiment pipeline (extract → canonicalize → classify) |
| **Shaun** | Variable extraction · stats engine · data scraping · ETL |

---

*Built at a biotech hackathon in San Francisco, April 2026.*
