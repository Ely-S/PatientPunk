# Phoenix Rising + Reddit LDN — Real-World Evidence Statistics Appendix

_Generated 2026-06-21 from the committed pipeline outputs in `./notebooks/`. Deterministic recompute of the already-classified runs — no LLM calls, no re-classification._

**Sources:** `ldn_2yr.db` (Reddit r/covidlonghaulers, Oct 2020–Dec 2022), `ldn_phoenix.db` + `phoenix_ldn_src.db` (Phoenix Rising). LDN = naltrexone (`drug_id=1`); Phoenix pyridostigmine excluded. Reddit user-level positive reproduces the letter's 68.5% (CI 63–73%) exactly, confirming method fidelity.

> **Comparability caveat (verbatim concern from `scripts/build_ldn_phoenix_data.py` (data-prep, not committed here)):** Phoenix was classified with a different model/prompt and aggregated differently than Reddit, so **Phoenix sentiment is NOT directly comparable to Reddit's 68.5%.** Directly comparable, pipeline-independent axes = **dose** (regex over raw text) and **side-effect category profile**. AE *rates* are also not cross-comparable (forum-culture effect). Treat cross-cohort sentiment and AE-frequency gaps as method/population artifacts, not drug effects.

## 1. Sentiment

### User-level (one outcome per user; responder = best report is positive)

| Cohort | Users | Responders | Positive | 95% Wilson CI |
|---|---|---|---|---|
| Reddit r/covidlonghaulers (2yr slice) | 321 | 220 | 68.5% | 63–73% |
| Phoenix Rising | 354 | 148 | 41.8% | 37–47% |
| Reddit full corpus (per FDA_letter_data_README; not recomputed here) | 3,354 | — | 55.5% | binomial p=1.8e-10 vs 50% null |

_README also notes: "higher LDN figures (~65%) seen in smaller, different corpora do not replicate at this scale." The 68.5% is the 2-year slice; the full-corpus user-level estimate is ~55%._

### Report-level sentiment distribution

| Cohort | n reports | Positive | Mixed | Neutral | Negative |
|---|---|---|---|---|---|
| Reddit (2yr) | 1316 | 81.7% | 4.9% | 1.6% | 11.9% |
| Phoenix Rising | 1622 | 52.0% | 13.4% | 1.4% | 33.1% |

## 2. Dose — directly comparable (regex over raw text, pipeline-independent)

Two distinct definitions; report whichever matches your claim, but don't conflate them:

**(a) Used a dose in the LDN range — minimum stated dose ≤ 4.5 mg** (the committed `dose_le_4_5` column)

| Cohort | Users stating a dose | ≤ 4.5 mg | 95% CI |
|---|---|---|---|
| Reddit (2yr) | 79 | 96.2% | 89–99% |
| Phoenix Rising | 148 | 94.6% | 90–97% |
| **Combined** | **227** | **95.2%** | **92–97%** |

**(b) Never exceeded the LDN range — maximum stated dose ≤ 4.5 mg** (stricter; excludes anyone who mentions titrating higher)

| Cohort | Users stating a dose | ≤ 4.5 mg | 95% CI |
|---|---|---|---|
| Reddit (2yr) | 79 | 77.2% | 67–85% |
| Phoenix Rising | 148 | 81.8% | 75–87% |
| **Combined** | **227** | **80.2%** | **75–85%** |

**Distribution by each user's highest stated dose:**

| Bucket | Reddit | Phoenix |
|---|---|---|
| ≤1.5 mg | 28 | 43 |
| 1.6–3 mg | 9 | 36 |
| 3.1–4.5 mg | 24 | 42 |
| >4.5 mg | 18 | 27 |

## 3. Side effects

| Metric | Reddit (2yr) | Phoenix Rising |
|---|---|---|
| Total LDN reports | 1316 | 1622 |
| Reports mentioning an AE | 194 (14.7%) | 973 (60.0%) |
| Users reporting any AE | 117/321 (36.4%) | 281/354 (79.4%) |
| Discontinuation reports | 26 (2.0%) | 125 (7.7%) |
| Serious AE reports | 10 | 1 |

> AE *rates* are ~4x higher on Phoenix (a chronic-illness forum where side effects are discussed more) and are not cross-comparable. The comparable, stable signal is the **category rank order** below — consistent across both communities and with Du & Nguyen (2025).

### AE category profile (users reporting each category)

| Category | Reddit (% of 321) | Phoenix (% of 354) |
|---|---|---|
| Sleep disturbance | 27 (8.4%) | 145 (41.0%) |
| Fatigue | 18 (5.6%) | 85 (24.0%) |
| GI disturbance | 15 (4.7%) | 72 (20.3%) |
| Headache | 12 (3.7%) | 48 (13.6%) |
| Light-headedness | 8 (2.5%) | 22 (6.2%) |
| Brain fog | 7 (2.2%) | 24 (6.8%) |

---
_No LLM calls were made; all figures are deterministic recomputes of the committed `treatment_reports`. Definitions, denominators, and Wilson 95% CIs are stated inline so each figure can be dropped into the letter with its exact basis._