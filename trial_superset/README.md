# trial_superset

Builds the **training-trial set** for Nikita's NATURAL-v2 model — larger and cleaner than her
single Long-COVID study — in her exact format. We **depend on `naturalv2` (pinned); we do not
reproduce or edit it**: her `check_trial` / `Experiment` / `Study` are called unchanged. Only the
data we feed them, and a few additive layers on top, are ours.

## What this is for

NATURAL-v2 predicts a clinical trial's **outcome** from **pre-publication patient-community signal**
(what Reddit patients said about a drug *before* the trial read out). Training/validating that needs
many **completed trials whose real per-arm outcome is known** — the ground truth. This package
produces that labeled trial set. Her pipeline separately attaches the Reddit/PubMed evidence and
learns to predict; we feed the trial side.

## Provenance & attribution (read this first)

Everything here is one of three sources. Be precise about which:

- **[N]** — Nikita / `naturalv2`: her code and design.
- **[TS]** — TrialScout: the team's prior work, *before* this effort (`../TrialScout/`).
- **[NEW]** — built in this effort (`trial_superset/`).

| Layer | Component | Source |
|---|---|---|
| Trial data | ClinicalTrials.gov | — |
| Download | `download_clinical_trials` — pulls the *whole* interventional+results corpus, no condition filter | **[N]** |
| Download (opt) | condition-*scoped* download (`query.cond=…`) — efficiency only; does **not** change which trials get selected | **[NEW]** |
| Criteria | `check_trial` + the preset toggles (randomized / parallel / binary…) | **[N]** |
| Criteria | choosing the `noparallel_notbinary_apo` preset | **[N]** — it's the preset her shared file used |
| Condition match | her substring matcher `find_condition_ncts` (the one that admits acute-COVID, under-matches POTS) | **[N]** |
| Condition string | `"Long Covid"` | **[N]** chose it for her study (TS uses the same string) |
| Condition string | the other four — POTS, Myalgic Encephalomyelitis, Fibromyalgia, Post-Treatment Lyme | **[TS]** (`build_candidates.py` CONDITIONS) |
| Condition match | the **clean keyword classifier** (`seed_terms.CLASSIFY`) replacing her matcher | **[NEW]** (deliberate deviation from [N]) |
| Labels | `Experiment`/`Study`: per-arm APO from structured results, temporal split, study-YAML format | **[N]** |
| Labels | papers-as-labels (rescue no-results trials from publications) | **[NEW]** |
| Labels | label sidecar (endpoint_type, clean_outcome, scale_proportion, is_change_from_baseline) | **[NEW]** |
| Labels | endpoint classification + match-to-test, relaxed test universe | **[NEW]** |

**The 5-condition cluster itself** (which conditions to include) is **[TS]** — from `build_candidates.py`,
not from Nikita. Her shared study is **Long COVID only**.

## The pipeline

```
ClinicalTrials.gov ─▶ check_trial [N] ─▶ condition match ─▶ trials WITH results ─┐
                                          (her matcher [N] OR our classifier [NEW])│─▶ her Study [N] ─▶ training set
   completed trials WITHOUT results ─▶ find paper ─▶ LLM-extract outcome [NEW] ───┘    (per condition, study YAML)
```

1. **Frame [N].** Completed interventional trials, design-filtered by `check_trial`, assigned to one
   of the 5 conditions. Condition assignment runs in two modes (below).
2. **Label [N].** For a trial with posted structured results, her `Experiment` reads the per-arm
   primary-endpoint value — the number NATURAL learns to predict.
3. **Papers-as-labels [NEW].** Many completed trials **never post structured results** to CT.gov, so
   her pipeline drops them. We rescue them: link the results paper (Europe PMC), pull OA full text,
   LLM-extract the per-arm primary outcome, synthesize the CT.gov-results shape her `Experiment`
   expects, and inject it. **+88 trials → 249 train+val** (161 structured + 88 paper-rescued).

## Two modes (both call her code unchanged)

| Mode | Condition match | Output | Reproduces her shared study? |
|---|---|---|---|
| **Faithful** | her substring matcher [N] | `data/m2_outputs/` | yes — long-COVID retro 21/21 |
| **Improved** (canonical) | our keyword classifier [NEW] | `data/improved_outputs/` → augmented in `data/m3_labeled/` | deliberately deviates — see audit doc |

Both are kept so we can hand Nikita the exact delta.

## Scripts ([NEW] unless noted)

| Script | Does |
|---|---|
| `seed_terms.py` | the 5 conditions (filter strings [TS] + scope + classifier [NEW]), candidate drugs (incl. IVIG) |
| `run_study.py` | M1 — drive her `create_study` [N] with a scoped download; reproduce her study |
| `verify_m1.py` | M1 regression check (loads in her `Study`; retro reproduced; test gap explained) |
| `relaxed_test_universe.py` | recruiting-inclusive test universe (her `status:act` excludes recruiting trials, incl. LIFT) |
| `broaden.py` | M2 — faithful mode across all 5 conditions |
| `audit_conditions.py` | audit each condition's matcher for under/over-matching |
| `build_improved.py` | build the clean/canonical per-condition studies |
| `consolidate.py` | flatten canonical studies → `data/training_set_manifest.csv` |
| `m3_pool.py` | M3 gate — quantify the papers-as-labels addressable pool |
| `litlabels/extract_labels.py` | M3 — link paper → full text → LLM-extract per-arm outcome (`--all` for the full run) |
| `build_augmented.py` | inject extracted labels → `data/m3_labeled/`, the augmented set |
| `build_labels_sidecar.py` | model-ready label sidecar (endpoint_type / clean_outcome / scale_proportion / is_change) |
| `endpoint_classify.py` | LLM-classify endpoints → domain / modality / self_reportable / instrument |
| `drug_classify.py` | LLM-classify interventions → drug_class / drug_accessibility (self-experimentable) |
| `relink_long_covid.py` | grow Long-COVID training: multi-paper retry on declined no-results trials |
| `long_covid_eval.py` | persist the recruiting-inclusive Long-COVID eval set (LIFT factorial relabeled) |
| `extract_validate.py` | extraction accuracy vs CT.gov ground truth |
| `binary_compare.py` | binary-vs-notbinary trial-count comparison (justifies notbinary+sidecar) |
| `sanity_check.py` | data QA (disjointness, baseline, label ranges) |
| `litlabels/europe_pmc.py`, `cache.py` | vendored EPMC client + cache (provenance headers, from AI_Scientist_Assistant) |
| `build_master_csv.py` | one master CSV joining everything (**gitignored**, S3 only) |

## Running

```bash
PY=trial_superset/.venv/Scripts/python.exe
# run from the repo root with PYTHONPATH=trial_superset for the litlabels package + top-level modules

# faithful + improved training sets
$PY trial_superset/broaden.py
$PY trial_superset/build_improved.py

# papers-as-labels
PYTHONPATH=trial_superset $PY -m litlabels.extract_labels --all   # full extraction (resumable, cached)
$PY trial_superset/build_augmented.py                             # inject -> augmented set
$PY trial_superset/build_labels_sidecar.py                        # model-ready label sidecar
PYTHONPATH=trial_superset $PY -m endpoint_classify                # endpoint classification
$PY trial_superset/build_master_csv.py                            # master CSV (gitignored)
```

LLM steps use the Anthropic API (OpenAI-compatible endpoint) via `ANTHROPIC_API_KEY` in the repo
`.env`; model via `M3_MODEL` (default `claude-sonnet-4-6`). (OpenRouter is supported but was out of
credits.)

## Data

**All data lives in S3, not git.** `data/` is gitignored; mirror with
`aws s3 sync trial_superset/data s3://patientpunk/trial_superset/ --exclude ".cache/*" --exclude "*.log"`.
Key artifacts in `s3://patientpunk/trial_superset/`:
- `training_set_manifest_augmented.csv` — 249 train+val + test, `label_source` tagged
- `labels_sidecar.csv` — per (trial, outcome, arm) model-ready labels
- `endpoint_classification.csv` — endpoint domain/modality/self_reportable/instrument
- `master_pulled_data.csv` — everything joined (also gitignored; generator `build_master_csv.py` gitignored too)

## Status

- **M0–M3 + validation + endpoint-match done & committed** (`shaun/trial-superset`, unpushed, no PR).
- **Training set:** 249 train+val (161 structured [N] + 88 paper-rescued [NEW]) + test, across 5 conditions.
  Long COVID specifically: 44 train+val (broadened `query.cond` scope catches `SARS-CoV-2`/`PASC`-tagged trials
  that bare `COVID` missed — see docs/long_covid_focus.md).
- **Validated:** loads/runs in her `Study`; extraction ~75–88% accurate vs CT.gov ground truth (conservative,
  no fabrication); structured baseline (157) preserved; disjointness checks pass.
- **Not done:** full Step-3 estimator run (needs GPU/vLLM + the Reddit/PubMed corpus) — ingestion validated, not end-to-end training.

## For Nikita (differences & decisions)

- [docs/condition_filter_audit.md](docs/condition_filter_audit.md) — **her** substring matcher [N] mis-classifies
  (long-COVID admits ~12/22 acute-COVID trials and drops post-COVID; dysautonomia under-matches). Effectively a
  bug in her pipeline that affects her own shared study. We adopted a clean classifier [NEW].
- [docs/test_universe_status.md](docs/test_universe_status.md) — her `status:act` [N] excludes recruiting trials
  (so LIFT can't be a test trial), yet her shared test set is effectively recruiting-inclusive → repo vs output disagree.
- [docs/label_normalization.md](docs/label_normalization.md) — her notbinary `value/N` [N] is a rate for binary
  but `mean/N` (garbage) for continuous (~80% of endpoints). Sidecar fixes it [NEW]; binary preset is non-viable (234→20).
- [docs/validation.md](docs/validation.md) — extraction accuracy + downstream-compatibility + limits
  (covariate sparsity on rescued trials, ~12% extraction error).
- [docs/long_covid_focus.md](docs/long_covid_focus.md) — Long-COVID focus + **a real factorial-arm bug**:
  her `check_nonplacebo` drops factorial arms named `"X/Placebo"` (e.g. LIFT's LDN-alone and
  pyridostigmine-alone main-effect arms), keeping only the stack. Affects any 2×2 factorial. Fix = relabel.
- Open decisions that are hers: which conditions belong in the cluster; the long-COVID/POTS definitions;
  the canonical target for continuous endpoints (absolute vs change); recruiting-inclusive test universe.
