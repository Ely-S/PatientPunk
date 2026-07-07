# FDA Letter Analysis — LDN & Mestinon Real-World Evidence

Real-world-evidence (RWE) analysis supporting the PatientPunk FDA comment on **drug
repurposing of low-dose naltrexone (LDN)** for post-infectious / dysautonomic chronic
conditions (FDA Docket No. FDA-2026-N-4492). It mines patient-reported treatment outcomes
from public online communities and quantifies use, dosing, sentiment, and side-effect
profiles for two repurposing candidates:

- **LDN** (naltrexone) — Reddit r/covidlonghaulers + the Phoenix Rising forum
- **Mestinon** (pyridostigmine) — Reddit r/covidlonghaulers + r/dysautonomia

All data derive from **public posts**; usernames are de-identified (SHA-256 hashed) at
ingestion — no direct identifiers are stored.

> ## Reproducibility note — read first
> The source SQLite databases (~10 GB) are **not committed** to the repo. The committed
> deliverable is the **executed analysis** itself: notebooks with their outputs baked in
> (`notebooks/*_executed.ipynb` + rendered `*.html`), the publication figures
> (`figures/`), and a deterministic statistics appendix (`phoenix_rwe_stats_appendix.md`).
> These stand on their own for reading and citation. `MANIFEST.csv` documents the
> underlying data files (sizes, SHA-256, original S3 location). **Full re-execution** of
> the build scripts requires those databases and is not supported from this folder alone.

## Contents

| Path | What it is |
|---|---|
| `notebooks/*_executed.ipynb`, `*.html` | The 7 analysis notebooks, executed (outputs embedded) and rendered to HTML for reading without Jupyter. |
| `figures/` | 20 publication figures (PNG + SVG): LDN dose distributions, side-effect profiles, and the FDA-letter composite figures. |
| `ldn_literature_review.md` | LDN mechanism + clinical-evidence review for post-viral conditions. |
| `phoenix_rwe_stats_appendix.md` | Deterministic recompute of the headline statistics (Wilson CIs, dose, AE profile) with definitions/denominators inline. No LLM calls. |
| `mestinon_negative_reason_fragments.xlsx` | Qualitative coding of why non-positive Mestinon reports are non-positive. |
| `MANIFEST.csv` | Registry of the (uncommitted) source data files: size, SHA-256, row counts. |
| `scripts/` | The 16 figure/notebook **builder** scripts that produced the committed artifacts (see note below). |

### Notebooks
`fda_supporting_evidence` · `ldn_2yr_deepdive` · `ldn_rwe_corroboration` ·
`ldn_two_community_tolerability` (the key dose / side-effect analysis across Reddit +
Phoenix) · `mestinon_pyridostigmine_analysis` · `mestinon_predictors_analysis` ·
`mestinon_what_predicts_response`.

### Scripts
A **minimal** set: only the `build_*` / `export_*` scripts that generate the committed
figures and notebooks. The data-preparation and exploratory layer (corpus ingestion,
`pp_*` helpers, probes) is intentionally omitted. The notebook builders reuse the shared
`build_notebook.py` from the pilot-paper package
([`../RCT_historical_validation/`](../RCT_historical_validation/)); they are included as
documentation of method, not as a turnkey rebuild (the source databases are not committed).

## Headline findings (honest summary)

- **LDN sentiment (Reddit, Oct 2020–Dec 2022 slice):** 68.5% user-level positive
  (n = 321; 95% Wilson CI 63–73%). On the full r/covidlonghaulers corpus the user-level
  estimate is ~55.5% (n = 3,354); the higher ~65–68% figures come from smaller/earlier
  slices and do not replicate at full scale.
- **Phoenix Rising sentiment is NOT directly comparable** to Reddit's (different model,
  prompt, forum culture). The pipeline-independent, comparable axes are **dose** (regex
  over raw text) and **side-effect category rank order**.
- **Dose:** ~95% of dose-stating users used a dose in the LDN range (≤ 4.5 mg), consistent
  across both Reddit and Phoenix — i.e. an off-label, low-dose pattern.
- **Side effects:** absolute AE *rates* are not cross-comparable (Phoenix ~4× higher,
  forum-culture effect), but the **category profile** (sleep disturbance > fatigue > GI >
  headache > light-headedness) is consistent across communities and with the literature.
- **Mestinon:** ~53% user-level positive (n = 429 full corpus), **not statistically
  distinguishable from a 50% coin-flip**; response is essentially unpredictable from text
  (logistic regression pseudo-R² ≈ 0.06–0.09). On matched data LDN (~55%) and Mestinon
  (~53%) look similar; neither is a strong-responder drug.

## Methodology (condensed)

Arctic Shift NDJSON → SQLite (usernames SHA-256-hashed, comments threaded to parents) →
word-boundary regex drug/alias match → fast-model prefilter (Claude Haiku 4.5) → strong-model
sentiment + side-effect classification (Claude Sonnet 4.6) → one-outcome-per-user
aggregation with Wilson score CIs, binomial test vs a 50% null, logistic regression for
prediction, and Mantel–Haenszel pooling across corpora.

## Limitations

Observational social-media data. **Sentiment is not a clinical endpoint; there is no
control/placebo arm.** Posters skew toward severe/dramatic outcomes (selection and
survivorship bias). Symptom and co-medication flags are keyword presence, not validated
phenotypes. Findings reflect reporting patterns in online communities, not population-level
treatment effects. **This is research evidence, not medical advice.**

## Related

- Pilot paper (predictive-validity methodology): [`../RCT_historical_validation/`](../RCT_historical_validation/)
