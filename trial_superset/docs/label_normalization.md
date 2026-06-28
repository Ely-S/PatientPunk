# Label normalization — the notbinary `value/N` problem and the sidecar fix

**Date:** 2026-06-25 · **Context:** sanity-checking the augmented training set.

## The problem
Her pipeline computes the per-arm label `avg_potential_outcome = value / N` for **every**
endpoint (or `value/100` if the unit says percent). That's a sensible **response rate** for a
binary/count endpoint, but **meaningless for a continuous endpoint** — dividing a mean by the
arm's sample size mixes the effect with N:

| trial | endpoint | value (correct) | her label = value/N |
|---|---|---|---|
| NCT02499302 | steps/day | 7217 (n=21) | **343.7** ⚠️ |
| NCT04158427 | VAS fatigue 0–100 | 72.8 (n=5) | **14.6** ⚠️ |
| NCT05559021 | FIQ score | 44.07 (n=8) | **5.5** ⚠️ |

In the current sidecar, **~84% of label rows are continuous endpoints** (the `notbinary` preset
admits them), so most labels were affected — only ~52% landed in [0,1], with extremes to ~387.
The extraction is correct; the **normalization** is the issue, and it's inherent to her
`notbinary` `Experiment` (her own notbinary study has it). We reproduced it faithfully, then
fixed it in a sidecar rather than dropping trials or editing her code.

## The fix — keep every trial, add a model-ready label sidecar
`data/labels_sidecar.csv` (built by `build_labels_sidecar.py`). Her native field is untouched;
the sidecar adds, per (trial, outcome, non-placebo arm):

| field | meaning |
|---|---|
| `endpoint_type` | `binary` \| `percentage` \| `continuous` (from CT.gov `paramType` / our `outcome_kind`) |
| `raw_value`, `n` | the extracted/structured per-arm value and denominator |
| `clean_outcome` | **meaningful** label: rate ∈ [0,1] for binary/percentage; **raw mean** for continuous |
| `scale_proportion` | continuous on a **bounded absolute** instrument → oriented `(mean−min)/(max−min)` ∈ [0,1] (higher = better); else blank |

So binary endpoints stay response rates; continuous endpoints become their real mean (no longer
mean/N); and where the instrument is a bounded absolute score we *also* give an oriented
[0,1] proportion so it shares an axis with the rates. The `endpoint_type` flag travels with every
row so the two scales are never silently mixed.

Important NATURAL context: pinned `naturalv2` does **not** read `labels_sidecar.csv`. Native
`estimate_ate.py` still compares predictions against `Experiment.avg_potential_outcomes`. The
sidecar is the corrected, model-ready export for a downstream consumer or for a patched evaluation
path; it does not change `naturalv2` behavior by itself.

## Coverage / honest limits
- `endpoint_type` distribution (689 rows): **continuous 582, binary 66, percentage 41**.
- `scale_proportion` is populated for only **62 / 582 continuous (11%)**. Most continuous
  endpoints here are **change-from-baseline** or **unbounded** (steps, meters, days, labs) — those
  *cannot* be expressed as a proportion of scale, by definition. The flag + raw mean still cover
  all of them; the proportion is a bonus where it's valid.
- `higher_is_better` (scale orientation) is an LLM judgment from the paper — usually right, but
  spot-check a few (e.g. WHOQOL direction can be ambiguous) if orientation matters downstream.

## For Nikita
The root cause is her `notbinary` `Experiment` normalization (`value/denom` for continuous).
Options: (a) consume our `labels_sidecar.csv` (`endpoint_type` + `clean_outcome` [+ `scale_proportion`])
and model binary/continuous as separate scales/heads; or (b) fix the normalization in her
`Experiment` (use the mean directly / standardize for continuous).

**Why not just use the `binary` preset (clean rates, no sidecar)?** Measured (`binary_compare.py`):
the binary preset drops the training set from **255 -> 21 train+val (-92%)**, and zeroes out ME/CFS
and chronic Lyme entirely — because these symptom conditions are dominated by **continuous** primary
endpoints (FSS, 6MWD, FIQ, VAS), not binary "X% responded" ones. So binary is non-viable here, and
the sidecar (keep notbinary, fix continuous labels) is the right approach, not over-engineering.

## Artifacts
- [`build_labels_sidecar.py`](../build_labels_sidecar.py) · `data/labels_sidecar.csv`
- Augmented set: `data/training_set_manifest_augmented.csv` (255 train+val incl. +88 paper-labeled)
