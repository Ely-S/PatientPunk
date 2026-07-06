# The 19-trial Long-COVID benchmark (coverage-first)

This is the **broader** Long-COVID benchmark, kept deliberately separate from the clean core-5 study
handed to Nikita. The core-5 is shipped in her runnable format
(`data/core5/long_covid_core5_noparallel_notbinary_apo_study.yaml`); this document describes the full
coverage-first set for discussion and optional inclusion.

## The metric
A trial is **usable** if its intervention has **≥ 50 on-target patient-usage reports** in the Long-COVID
Reddit corpus — i.e. distinct authors who describe *personally using that treatment for their long COVID
and reporting an outcome* (`effective_authors` = raw distinct-author mentions × LLM-validated on-target
fraction). This is the only inclusion gate; obtainability/confounding is recorded as an annotation, not
a filter (down-weighting confounded trials would hide exactly the failure mode NATURAL is meant to test).

## How we got here (the correction)
The original gate was `is_corpus_learnable` — it required the drug be **self-obtainable** *and*
single-agent *and* blinded *and* have a self-report endpoint. That gate returned only **5** credible
trials. It was too strict: NATURAL only needs a treatment to be **discussed** by patients who took it,
not self-obtained. Measuring actual on-target report coverage recovered **14 more** → **19 total**.

## The 19 (see `data/benchmark_19.csv`)
| origin | count | what they are |
|---|---|---|
| **original_5** | 5 | passed the old gate — the core-5 study (fluvoxamine, vortioxetine, lithium, cyclobenzaprine, Niagen) |
| **recovered_coverage** | 14 | have real patient-usage reports; old gate had excluded them |

Recovered 14, by why they'd been dropped:
- **Clinic-administered / device** (self-obtainability gate wrongly zeroed them): vagus-nerve stim, HBOT,
  stellate-ganglion block, plasma-exchange/apheresis (×2), TENS, oxaloacetate, mesenchymal stem cells.
- **Self-obtainable / oral-Rx, but dropped on blinding / combination / non-self-report-endpoint grounds:**
  vitamin D, prednisolone, Paxlovid (×3), L-citrulline.

## Reliability annotation (an interpretive covariate, NOT a filter)
| reliability | count | meaning |
|---|---|---|
| `high_clean_self_selection` | 11 | self-obtainable / oral-Rx — patient drives the decision, often states why → cleaner observational structure |
| `caveated_access_confounded` | 8 | clinic-administered / procedure — who receives it is selected by severity, wealth, access → confounding NATURAL can only partly adjust for |

Keep this for **interpreting** results (if NATURAL misses on IVIG/HBOT/stem-cells, these are the access-confounded ones), not for excluding or weighting the benchmark.

## The 3 prospective targets (separate from the 19 completed)
LIFT (LDN 3417 / pyridostigmine 261 on-target reports), IVIG (527), Tirzepatide (225). Arm-level detail
(incl. LIFT's factorial relabel) is in `long_covid_eval_set.csv`.

## Caveats
- **Shared evidence pools:** the 19 completed trials draw on **16 distinct drug signals** — Paxlovid has
  3 trials and apheresis 2, each sharing one Reddit pool (NATURAL gives one estimate per drug, tested
  against multiple RCT outcomes there).
- **Boundary:** some recovered trials are non-CT.gov (ISRCTN-adapted) — they cross the original
  CT.gov-only scope and are flagged `registry_adapted` in `master_pulled_data.csv`.

## Artifacts
- `data/benchmark_19.csv` — the 19, annotated (origin, on-target reports, obtainability, reliability).
- `data/core5/long_covid_core5_noparallel_notbinary_apo_study.yaml` — the clean 5 in NATURAL's format.
- `data/studies_list.csv` — the full ranked list (54 trials, all runnable verdicts).
- `data/drug_coverage.csv`, `data/coverage_validation.csv` — raw + validated coverage, with method audit.
