# trial_superset

Builds the **training-trial set** for Nikita's NATURAL-v2 model — as large and clean as we
can make it — in her exact format. We **depend on `naturalv2` (pinned), we don't reproduce or
edit it**: her `check_trial` / `Experiment` / `Study` are called unchanged; only the data we
feed them is ours.

## What this is for

NATURAL-v2 predicts a clinical trial's **outcome** from **pre-publication patient-community
signal** (what Reddit patients said about a drug *before* the trial read out). To train and
validate that, you need many **completed trials whose real per-arm outcome is known** — the
ground truth. This package produces that labeled trial set. Her pipeline separately attaches
the Reddit/PubMed evidence and learns to predict; we feed the trial side.

## The pipeline

```
ClinicalTrials.gov ─▶ filter by design + condition ─▶ trials WITH results ─┐
                                                                            ├▶ her Study ─▶ training set
   completed trials WITHOUT results ─▶ find paper ─▶ LLM-extract outcome ──┘   (per condition, study YAML)
```

1. **Frame (CT.gov).** Download completed interventional trials for the 5 cluster conditions
   (long COVID, ME/CFS, fibromyalgia, dysautonomia, chronic Lyme). Apply her design filters
   (`check_trial`: randomized, parallel-relaxed, etc.) and assign each to a condition. We
   replaced her substring condition-matcher with a clean keyword classifier — see
   [docs/condition_filter_audit.md](docs/condition_filter_audit.md). → **157 train+val trials.**
2. **Label = real per-arm outcome.** For a trial that posted structured results, her
   `Experiment` reads the per-arm primary-endpoint value (e.g. 45% drug vs 30% placebo) — the
   number NATURAL learns to predict.
3. **Papers-as-labels (the key gain).** Many completed trials **never post structured results**
   to CT.gov, so her pipeline silently drops them. We rescue them: find each trial's results
   paper (Europe PMC), pull the open-access full text, and use an LLM (Claude Sonnet via
   OpenRouter/Anthropic) to extract the **primary endpoint per arm**, then synthesize that into
   the CT.gov-results shape her `Experiment` expects and inject it as a new labeled trial.

## Two modes (both call her code unchanged)

| Mode | What | Output | Faithful to her shared study? |
|---|---|---|---|
| **Faithful** | her filters exactly | `data/m2_outputs/` | yes (reproduces her long-COVID retro 21/21) |
| **Improved** (canonical) | clean keyword classifier | `data/improved_outputs/` | deliberately deviates — see audit doc |

We keep both so we can hand Nikita the exact delta.

## Scripts

| Script | Does |
|---|---|
| `run_study.py` | M1 — drive her `create_study` with a condition-scoped CT.gov download; reproduce her study |
| `verify_m1.py` | M1 regression check (format loads in her `Study`; retro reproduced; test gap explained) |
| `relaxed_test_universe.py` | the recruiting-inclusive test universe (her `status:act` excludes recruiting trials incl. LIFT) |
| `seed_terms.py` | the 5 conditions (filter + download scope), the clean classifier `CLASSIFY`, candidate drugs (incl. IVIG) |
| `broaden.py` | M2 — run faithful mode across all 5 conditions |
| `audit_conditions.py` | audit each condition's filter for under/over-matching |
| `build_improved.py` | build the clean/canonical per-condition studies |
| `consolidate.py` | flatten the canonical studies → `data/training_set_manifest.csv` |
| `litlabels/extract_labels.py` | M3 — link paper → fetch full text → LLM-extract per-arm primary outcome (`--all` for the full run) |
| `build_augmented.py` | M3c — inject extracted labels and build the augmented training set |
| `litlabels/europe_pmc.py`, `cache.py` | vendored EPMC client + cache (provenance headers) |
| `m3_pool.py` | M3 gate — quantify the papers-as-labels addressable pool |

## Running

```bash
PY=trial_superset/.venv/Scripts/python.exe
PYTHONPATH=trial_superset            # for the litlabels package + top-level modules

# faithful + improved training sets
$PY trial_superset/broaden.py
$PY trial_superset/build_improved.py
$PY trial_superset/consolidate.py

# papers-as-labels
$PY -m litlabels.extract_labels --n 15      # validation gate (cwd = repo root, PYTHONPATH set)
$PY -m litlabels.extract_labels --all       # full extraction (resumable, cached)
$PY trial_superset/build_augmented.py       # inject + build augmented set
```

LLM extraction needs `ANTHROPIC_API_KEY` (or `OPENROUTER_API_KEY`) in the repo `.env`;
model via `M3_MODEL` (default `claude-sonnet-4-6`).

## Data

**All data lives in S3, not git.** `data/` is gitignored; mirror to
`s3://patientpunk/trial_superset/` with `aws s3 sync trial_superset/data s3://patientpunk/trial_superset/`.
Canonical artifact: `training_set_manifest.csv` (and `..._augmented.csv` after M3c).

## Status

- **M0–M2 done & committed** (`shaun/trial-superset`): 157 train+val (clean), 5 per-condition studies.
- **M3 in progress**: pool gate cleared (209 OA-fulltext candidates); extractor validated (gate
  8/14, values verified non-hallucinated); full run + injection pending.

## For Nikita (differences worth discussing)

- [docs/condition_filter_audit.md](docs/condition_filter_audit.md) — her substring condition-matcher
  mis-classifies (long-COVID admits acute / drops post-COVID; dysautonomia under-matches). We
  adopted a clean classifier; the long-COVID one is effectively a bug in her own pipeline.
- [docs/test_universe_status.md](docs/test_universe_status.md) — `status:act` excludes still-recruiting
  trials (so LIFT can't be a test trial); her shared study is effectively recruiting-inclusive.
- Continuous-mean labels inherit her notbinary pipeline's `value/denom` normalization (carried
  faithfully; flag for review).
