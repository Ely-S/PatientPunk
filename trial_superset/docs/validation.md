# Validation — downstream compatibility, extraction accuracy, label flags

**Date:** 2026-06-25 · de-risking the augmented training set before it goes near her model.

## #1 — Downstream compatibility (do paper-rescued trials ingest into her pipeline?)
Her Step-2 (`filter_curate`) loads each trial via `Experiment.from_yaml(get_experiment_filepath(...))`
then runs source curation on it. Test (`Experiment.from_yaml` on the persisted YAMLs we write):

- **Paper-rescued Experiments load 8/8** and carry `treatment_names`, `outcome_names`,
  `apo_outcome_treatment`, `conditions` — the fields the source stages query on. **So they do NOT
  break her pipeline** (the main unverified risk). 7/8 had non-empty treatments (1 edge case).
- **Real gap — covariate sparsity:** paper trials have only `[Country, Duration]` covariates
  (we stub an empty `baselineCharacteristicsModule`), vs **5–20** for structured trials. Papers
  rarely report an extractable Table-1 baseline, so paper trials are **outcome-labeled but
  covariate-sparse** → less adjustment data for her IPW/OI estimators. Inherent, not breakage;
  flag for Nikita. (Extracting baseline tables from papers is possible but a much bigger lift.)
- **Not tested:** a full Step-3 estimator run (needs GPU/vLLM + the Reddit/PubMed corpus) — out of
  scope with the data we have. We validated ingestion + field presence, not end-to-end training.

## #2 — Extraction accuracy vs CT.gov ground truth (`extract_validate.py`)
Method: trials with BOTH structured CT.gov results AND an OA paper. Extract from the **paper**
(blind — `extract()` reads only protocolSection), compare per-arm primary value to the CT.gov result.

- 22 trials: **declined 14** (reviews / protocols / secondary analyses / figure-only — *correct*
  rejections, no fabrication), **committed 8** → **6 MATCH, 1 PARTIAL** (right values, missing 2 of
  4 arms), **1 MISMATCH**.
- **75% full-match, 88% match-or-partial** when it commits. Example: `NCT01518946` extracted 1626.6
  = truth 1626.6 exactly. The one miss (`NCT00633880`: truth 1.3 vs extracted −1.8) is a
  change-vs-absolute / timepoint ambiguity — the #5 issue.
- **Implication:** the extractor is conservative (declines when unsure) and ~75–88% accurate when it
  commits. The 88 paper-extracted train/val trials carry roughly that accuracy + occasional incompleteness - a
  measured error bar, not ground truth. Use the per-label `confidence` field; treat as good-but-noisy.

## #5 — Absolute-vs-change flag (`labels_sidecar.csv`)
Continuous labels mixed absolute scores (FIQ 44) and change-from-baseline (RAND-36 +9) — different
quantities. Sidecar now has **`is_change_from_baseline`** (from the outcome title): of 582 continuous
arms, **227 change-from-baseline, 355 absolute**. Prevents a model from mixing levels and deltas.

## Net
The pipeline and assembly are sound; the paper labels are **ingestible and ~75–88% accurate**, with
two honest limits to hand Nikita: **covariate sparsity** on rescued trials, and the **~12% extraction
error rate**. Both are now measured and documented rather than assumed.
