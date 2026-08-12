# How NATURAL works, what this set is, and why it's Long-COVID-only

**This is the most important doc to read first — it corrects an earlier framing error.**

## NATURAL does not train a model on trials
We initially treated this as "build a big labeled *training set* so the model learns better, possibly
across adjacent conditions (transfer)." **That is wrong.** Reading the paper
([arXiv:2407.07018](https://arxiv.org/abs/2407.07018), NeurIPS 2024) and the v2 code settles it:

- **NATURAL estimates each trial's effect *independently* from that trial's own patient-community text**
  (its Reddit/PubMed posts), zero-shot. Paper: *"NATURAL does not require any curated task-specific
  training data (it is zero-shot)."*
- **The clinical trials are the *benchmark*, not training data.** Paper: *"we treated the ATE from a
  corresponding real-world completely randomized experiment (CRE) as ground truth."*
- **Estimates are *local*; no cross-disease generalization is claimed.** Paper: *"our framework is only
  capable of estimating local ATEs — external validity is not guaranteed a priori."*
- **v2 confirms it:** `estimate_ate.py` processes **one trial at a time**, loading *that trial's* curated
  text; the estimator's `model.fit()` runs on *that trial's own* extracted (covariate, treatment, outcome)
  rows. There is **no fit-on-train → apply-to-test step.** The train/val/test split is temporal — for
  **leakage control** (use only community text from *before* each trial read out) and honest evaluation,
  not for training a pooled predictor.

## Therefore: this set is a benchmark + a target list
- It is **not** training data for a learned predictor (there is no such predictor).
- It is **(a)** a set of completed trials with known per-arm outcomes — a **benchmark** to measure how
  accurately NATURAL's text-derived estimates match ground truth; and **(b)** the prospective **targets**
  we want to predict.
- What determines whether NATURAL can estimate a given trial is **that trial's own community signal**
  (does the drug have enough Reddit discussion *for this condition*) — exactly what
  `is_corpus_learnable` measures. Set *size* is not the lever; per-trial *signal* is.

## Two separate datasets (Long COVID primary, cluster secondary)
Because there is **no pooled model**, the non-LC trials (ME/CFS, fibromyalgia, dysautonomia, chronic
Lyme) **neither help nor hurt** LC prediction — they are a *different* benchmark, not part of the LC one.
So they are kept but **split into their own dataset**, not mixed into the headline LC set:

- **`master_pulled_data.csv`** — **Long COVID** benchmark (primary): 50 trials, 9 corpus-learnable
  overall. The 21 CT.gov-structured subset contains 8 of those; the ninth is paper-rescued.
- **`cluster_benchmark.csv`** — **adjacent conditions** benchmark (separate): ME/CFS, fibromyalgia,
  dysautonomia, chronic Lyme. Same schema; for anyone who wants to evaluate NATURAL across the
  post-viral/chronic-fatigue cluster rather than LC alone.

(Earlier we worried that fibromyalgia dominating 56% of a *combined* set would *bias* predictions — that
worry was a product of the wrong framing; nothing is trained, so nothing is biased. The fix is simply to
not mix the two benchmarks, which the split achieves.) Both are produced by the same pipeline
(`build_augmented.py` builds all conditions; `build_master_csv.py` writes the two files).

## The honest numbers (Long COVID)
| | count | what it is |
|---|---|---|
| LC train+val trials | **50** | completed LC trials with ground-truth outcomes (the benchmark pool) |
| …of which corpus-learnable | **9** | LC trials whose premise actually holds (single-agent, blinded, accessible drug, self-report signal). This is 8 CT.gov-structured trials plus 1 paper-rescued trial. |
| …off-premise | 41 | behavioral/device/clinic-administered — NATURAL can't estimate these from community text |
| prospective targets | **3** | LIFT, Tirzepatide, IVIG |
| …cleanly fitting the premise | **1** | **Tirzepatide** only. LIFT is a factorial (its LDN-alone arm is learnable after the relabel); IVIG is off-premise (clinic-administered, ~0 signal). |

**9 corpus-learnable LC trials exceeds NATURAL v1's own benchmark (~4 ground-truth RCTs per condition)** —
so Long COVID alone is a sufficient benchmark. The headline is **9**, not 50. If discussing only the
21 CT.gov-structured trials, the corpus-learnable count is **8**.

## What the growth work actually bought (re-stated honestly)
The scope fix, papers-as-labels, and ISRCTN adapter grew the LC **benchmark pool** (more LC trials with
ground truth to evaluate against) and surfaced a few accessible-drug trials — genuine value. They did
**not** "add training data for the model," because the model isn't trained on trials. Frame them as
benchmark breadth, not training volume.
