# PatientPunk

**Mining patient communities for real-world treatment signals — before the clinical trials exist.**

---

## The Problem

For conditions like Long COVID, ME/CFS, POTS, and EDS, randomized controlled trials are sparse, slow, and often underpowered. Meanwhile, hundreds of thousands of patients are self-experimenting and reporting outcomes in online communities in real time.

Reddit communities like r/covidlonghaulers (37,000+ posts, 650k comments) contain detailed first-person accounts: what treatments patients tried, what symptoms improved, what made things worse, and what comorbidities they carry. This is observational data with all the limitations that implies — but it is also years ahead of the formal literature.

The problem is that none of it is structured. It lives in free text, unqueried.

---

## What PatientPunk Does

PatientPunk turns unstructured patient posts into a queryable database of treatment outcomes, then runs epidemiological analyses on it.

**Step 1 — Extraction**
A large language model reads each post and extracts: drugs and interventions mentioned, the patient's sentiment toward each (positive / negative / mixed), signal strength, demographics (age, sex, location), and self-reported conditions.

**Step 2 — Normalization**
Extracted drug names are canonicalized — "LDN", "low dose naltrexone", and "naltrexone 4.5mg" all resolve to the same entity. Vague references like "medication" or "supplement" are discarded.

**Step 3 — Analysis**
A statistics engine runs validated epidemiological tests on the structured data: outcome rates with confidence intervals, between-group comparisons, survival analysis, regression with covariate adjustment, and propensity-score matching. Every result carries explicit warnings about sample size, power, and data quality.

**Step 4 — Reporting**
A research assistant (powered by Claude) answers natural-language research questions by querying the database, selecting appropriate tests, and generating a documented, reproducible analysis notebook.

---

## Current Data

| Community | Scale |
|---|---|
| r/covidlonghaulers | 37,000+ posts · 650k comments (2 years) |
| r/ehlersdanlos | 270 posts |
| r/PSSD | 332 posts |
| r/microdosing | 164 posts |
| r/abortion | 385 posts |

The current working database covers a 1-month r/covidlonghaulers snapshot: **526 treatment sentiment reports** across **177 distinct interventions** from **2,826 unique users**.

---

## Example Results

From the 1-month Long COVID cohort:

| Intervention | Positive outcome rate | n (users) |
|---|---|---|
| KPV (tetrapeptide) | 86% | 7 |
| Taurine | 73% | 15 |
| Low Dose Naltrexone | 60% | 15 |
| Antihistamines | 50% | 8 |
| Tirzepatide (GLP-1) | 38% | 8 |
| BPC-157 (peptide) | 17% | 6 |

A Mann-Whitney comparison of LDN outcomes in POTS vs. non-POTS patients found no significant difference (p > 0.05, n=15) — suggesting LDN response may not be mediated through POTS-related mechanisms, though sample size limits interpretation.

*All results include confidence intervals and explicit caveats about self-selection, reporting bias, and statistical power.*

---

## Limitations We Take Seriously

- **Self-selection bias** — patients who post about a treatment are not a random sample. Those with strong outcomes (positive or negative) are overrepresented.
- **Confounding** — patients self-select treatments based on severity, prior treatment history, and comorbidities. Propensity-score matching partially addresses this where sample sizes allow.
- **Small n** — most drugs have fewer than 20 user reports in any single time window. Results are hypothesis-generating, not confirmatory.
- **Canonicalization errors** — the LLM occasionally conflates conditions with treatments (e.g. tagging "depression" as a drug). We track and reduce this error rate explicitly.

Every analysis notebook ends with a boilerplate reminder that these are self-reported Reddit posts, not clinical outcomes.

---

## Why It Matters

The gap between patient knowledge and the clinical literature is measured in years. For conditions with no approved treatments and poor mechanistic understanding, patient communities are often the fastest source of real-world efficacy signals. PatientPunk makes that signal queryable, reproducible, and statistically grounded — without waiting for a trial.

---

*Built at a biotech hackathon in San Francisco, April 2026.*

