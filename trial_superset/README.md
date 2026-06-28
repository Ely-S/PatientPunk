# trial_superset

Builds the **Long-COVID benchmark + target set** for Nikita's NATURAL-v2 model, in her exact format.
We **depend on `naturalv2` (pinned); we do not reproduce or edit it**: her `check_trial` /
`Experiment` / `Study` are called unchanged. Only the data we feed them, and a few additive layers, are ours.

> **Read [docs/method_and_scope.md](docs/method_and_scope.md) first.** NATURAL estimates each trial
> *independently* from its own patient-community text — it does **not** train a pooled model on the
> trials. So this is a **benchmark + target list, not training data**, and the **canonical set is now
> Long COVID only** (the non-LC cluster conditions add nothing under per-trial estimation and were
> removed; they remain recoverable). Headline: **50 LC trials with ground truth, of which 9 fit
> NATURAL's premise** (the real benchmark; ~2× NATURAL v1's ~4-per-condition).

## What this is for

NATURAL-v2 estimates a clinical trial's **outcome** from **pre-publication patient-community signal**
(what Reddit patients said about a drug *before* the trial read out), **per trial, zero-shot** — no
cross-trial training. Validating that needs **completed trials whose real per-arm outcome is known** —
ground truth to benchmark the estimates against. This package produces that **Long-COVID benchmark**
plus the **prospective targets** we want to predict. Her pipeline attaches the Reddit/PubMed evidence
and runs the estimator per trial; we provide the trial side.

## Provenance & attribution (read this first)

Everything here is one of three sources. Be precise about which:

- **[N]** — Nikita / [`naturalv2`](https://github.com/nikitadhawan/naturalv2): her code and design (pinned `16ca178`).
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
| `mine_registries.py` | **additional-source explorer #1** — mine ISRCTN/EudraCT (non-CT.gov) LC RCTs → `data/mined_registries.csv` |
| `mine_reviews.py` | **additional-source explorer #2** — mine LC systematic-review evidence tables → `data/mined_reviews.csv` |
| `adapt_registries.py` | adapt ISRCTN LC RCTs → CT.gov-shaped JSON (template-clone + paper outcome); 6 ingested into long_covid |
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
- `training_set_manifest_augmented.csv` — 50 LC train+val + test, `label_source` tagged (LC-only canonical)
- `labels_sidecar.csv` — per (trial, outcome, arm) model-ready labels
- `endpoint_classification.csv` — endpoint domain/modality/self_reportable/instrument
- `master_pulled_data.csv` — everything joined (also gitignored; generator `build_master_csv.py` gitignored too).
  Provenance columns: **`data_source`** = `trial_listing` (CT.gov results) / `paper` (extracted from
  publication) / `registry_adapted` (non-CT.gov ISRCTN); **`is_prediction_target`** = the 3 trials we
  predict (LIFT, Tirzepatide, IVIG — LIFT is recruiting so pulled from the relaxed test universe);
  **`in_nikita_seed`** = trial was in Nikita's original shared study (her M1-reproduced pull).
- `long_covid_eval_set.csv` — the recruiting-inclusive Long-COVID prediction targets (incl. LIFT's factorial arms + corpus signal)

## Status

- **M0–M3 + validation + endpoint-match done & committed** (`shaun/trial-superset`, unpushed, no PR).
- **Canonical set (Long COVID only):** 50 train+val benchmark trials = 21 CT.gov + 23 paper-rescued +
  6 non-CT.gov ISRCTN (adapted). **Of these, 9 fit NATURAL's premise** (the real benchmark). 3 prospective
  targets (LIFT, Tirzepatide, IVIG); only Tirzepatide cleanly fits. See docs/method_and_scope.md,
  docs/long_covid_focus.md, docs/additional_sources.md. (Non-LC cluster removed but recoverable — set
  `CANONICAL_CONDITIONS = list(CLUSTER)` in `build_augmented.py`.)
- **Validated:** loads/runs in her `Study`; extraction ~75–88% accurate vs CT.gov ground truth (conservative,
  no fabrication); structured baseline (157) preserved; disjointness checks pass.
- **Not done:** full Step-3 estimator run (needs GPU/vLLM + the Reddit/PubMed corpus) — ingestion validated, not end-to-end training.

## For Nikita (differences & decisions)

> **⚠️ [docs/bugs.md](docs/bugs.md) — start here.** A single registry of every bug found. Four are in
> `naturalv2` itself and change *your own* published study (condition matcher, `value/N` continuous
> labels, factorial-arm dropping, `status:act` vs your shared test set). The per-topic docs below have
> the full detail for each.

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
- [docs/additional_sources.md](docs/additional_sources.md) — exploring growth beyond CT.gov: non-CT.gov
  registries (ISRCTN/EudraCT, `mine_registries.py`) and systematic-review evidence tables
  (`mine_reviews.py`). Both are candidate-CSV explorers, kept separate; injection would cross the
  CT.gov-only boundary, so it's flagged not done.
- Open decisions that are hers: which conditions belong in the cluster; the long-COVID/POTS definitions;
  the canonical target for continuous endpoints (absolute vs change); recruiting-inclusive test universe;
  whether to ingest non-CT.gov registries (needs a schema adapter).

## References & external resources

**Core dependency**
- [`naturalv2`](https://github.com/nikitadhawan/naturalv2) — Nikita Dhawan's NATURAL-v2 pipeline, the
  consumer of this trial set. Installed from `requirements.txt`, pinned at commit
  [`16ca178`](https://github.com/nikitadhawan/naturalv2/commit/16ca17819e7b6310f9d9799238f4ff8b11b4c6f5)
  — **do not bump without re-validating** (her schema/criteria can change).
- Her seed study (the format we match, Long COVID only): `long_covid_noparallel_notbinary_apo_study.yaml`.

**Data sources**
- [ClinicalTrials.gov API v2](https://clinicaltrials.gov/data-api/api) — trial protocols + structured results (the frame).
- [Europe PMC REST API](https://europepmc.org/RestfulWebService) — paper linking + OA full text (papers-as-labels, both miners).
- [ISRCTN registry API](https://www.isrctn.com/page/api) — non-CT.gov (UK) trial records (`mine_registries.py`, `adapt_registries.py`).
- Reddit patient-community corpus + precomputed signal — sibling project `../TrialScout/` (`signal_distinct.json`, `count_distinct_authors.py`).

**Data storage**
- All `data/` is gitignored and mirrored to **`s3://patientpunk/trial_superset/`**
  (`aws s3 sync trial_superset/data s3://patientpunk/trial_superset/ --exclude ".cache/*" --exclude "*.log"`).
- Master export: `data/master_pulled_data.csv` (also gitignored; generator `build_master_csv.py` gitignored too).

**Documentation index (`docs/`)**
- [method_and_scope.md](docs/method_and_scope.md) — **READ FIRST: how NATURAL actually works (per-trial, zero-shot), why this is a benchmark not training data, why Long-COVID-only.**
- [bugs.md](docs/bugs.md) — **consolidated bug registry (start here for Nikita).**
- [condition_filter_audit.md](docs/condition_filter_audit.md) — her condition matcher's over/under-matching.
- [test_universe_status.md](docs/test_universe_status.md) — `status:act` vs recruiting-inclusive test set.
- [label_normalization.md](docs/label_normalization.md) — the `value/N` continuous-label problem + sidecar fix.
- [validation.md](docs/validation.md) — extraction accuracy + downstream compatibility + limits.
- [long_covid_focus.md](docs/long_covid_focus.md) — Long-COVID targets, scope fix, factorial-arm bug.
- [additional_sources.md](docs/additional_sources.md) — ISRCTN/EudraCT + systematic-review mining + the adapter.
