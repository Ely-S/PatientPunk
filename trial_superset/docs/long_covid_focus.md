# Long-COVID focus: the three targets, the benchmark, and the factorial-arm bug

> **Framing note (read [method_and_scope.md](method_and_scope.md) first):** NATURAL estimates each trial
> *independently* from its own community text — it does **not** train a pooled model on the trials. So
> this set is a **benchmark + target list**, not "training data," and "lever / training" language below
> should be read as *growing the benchmark pool*. The primary set is **Long COVID** (`master_pulled_data.csv`);
> the non-LC cluster conditions were **split into a separate `cluster_benchmark.csv`** (kept, not deleted —
> they add nothing to LC under per-trial estimation, so they're their own benchmark).

**Date:** 2026-06-25 · scope decision: keep the prediction universe at **Long COVID** (that's where
the candidate targets *and* the Reddit corpus signal are; the other cluster conditions are mostly
off-premise or population-mismatched — see master CSV flags).

## The three trials we're predicting

These are the prospective targets. In the data they are flagged **`is_prediction_target=True`** in
`master_pulled_data.csv`. Note `master`'s test rows are **trial/outcome-level** (one per registered
primary outcome), so the **arm-level** targets — e.g. LIFT's LDN-alone vs pyridostigmine-alone arms,
with the factorial relabel — live in **`data/long_covid_eval_set.csv`**, which is the canonical
**arm-level prediction-target artifact** (annotated with per-arm corpus signal).

| trial | NCT | drug(s) | corpus signal (LC) | fits NATURAL's premise? |
|---|---|---|---|---|
| **Tirzepatide** | NCT07128082 | tirzepatide | 446 | ✅ **yes** — single-agent, blinded, fatigue PRO |
| **LIFT** | NCT06366724 | LDN + pyridostigmine (2×2 factorial) | LDN 5183, pyrido 683 | ⚠️ **partial** — richest signal, but factorial; only its **LDN-alone arm** is learnable (after the relabel below) + it's recruiting |
| **IVIG** | NCT06305793 | IVIG | 0 | ❌ **no** — clinic-administered, no corpus signal, combination |

**Bottom line: of the 3, only Tirzepatide cleanly fits** (see [method_and_scope.md](method_and_scope.md)) —
the honest framing for the report is "1 clean + 1 partial (LIFT, via its LDN arm) + 1 off-premise (IVIG)."

## Growing the Long-COVID *training* set — what works (corrected 2026-06-27)

Two string layers; only one was the lever, and it wasn't the one assumed first.

- **The CLASSIFIER is not the lever.** Of the valid COVID structured-results trials, the ~188 the
  classifier excludes are genuine *acute* COVID (pneumonia/ARDS/coagulopathy). Loosening the post-COVID
  keyword tokens just re-admits acute contamination.
- **The DOWNLOAD SCOPE query *was* the lever.** `query.cond="COVID"` does **not** match a trial tagged
  `"Post-Acute Sequelae of SARS-CoV-2"` / `"PASC"` / `"Post-COVID-19 Condition"` — no "COVID" substring,
  and CT.gov does **not** auto-expand. Broadening the scope to the synonym set
  (`COVID OR SARS-CoV-2 OR PASC OR Post-Acute Sequelae of SARS-CoV-2 OR Post-COVID-19 Condition OR
  Chronic COVID OR Long-haul COVID`) recovers genuine Long-COVID trials the bare scope missed:
  **structured training 17 → 21 (+4); paper-rescue pool 85 → 118 (+33).** Wired into `seed_terms.py`.
- **Paper repositories (Europe PMC) confirm the ceiling is structural.** ~4,800 Long-COVID RCT papers
  exist; harvesting NCTs from them yields **371 distinct trials**, but after requiring *genuine
  Long-COVID* + *her RCT criteria*, only ~7 are new and usable and **0 have structured results**. Most
  Long-COVID literature is reviews/observational/non-RCT, and the trials are dominated by
  behavioral/device/rehab interventions.
- **Caveat on what the +4/+33 actually are:** mostly behavioral/device (tDCS, cognitive rehab, exercise,
  inspiratory-muscle training, yoga). A *few* accessible drugs appear (Montelukast, Vitamin D/K2,
  Sulodexide) that are corpus-relevant. So the scope fix grows the **raw** count meaningfully but the
  **corpus-learnable** subset only slightly — the structural scarcity of self-experimentable-drug
  Long-COVID RCTs stands.
- **No-results extraction lever:** `relink_long_covid.py` retries each candidate across **multiple**
  candidate papers (`extract_best`) to recover wrong-paper declines (review/protocol/secondary).

## Current net outcome (2026-06-28)
**Long-COVID train+val: 31 -> 50** (21 CT.gov-structured + 23 paper-rescued +
6 registry-adapted); whole-superset augmented **236 -> 255**. Corpus-learnable Long-COVID
benchmark trials: **9** overall (**8** CT.gov-structured + **1** paper-rescued, `NCT04795557`).
The new trials skew behavioral/device, with only a handful of accessible drugs. Eval set:
**88 trials / 153 prediction-target arms** (LIFT included).

## Recruiting-inclusive test universe (so LIFT is predictable)
Her `status:act` excludes recruiting trials, so LIFT (RECRUITING) was absent from the test set.
Switching to recruiting-inclusive (ACTIVE_NOT_RECRUITING + RECRUITING + ENROLLING_BY_INVITATION) +
the broadened scope grows the Long-COVID test set to **88 trials** and **includes LIFT**. Eval set
persisted to `data/long_covid_eval_set.csv` (one row per prediction-target arm, annotated with corpus signal).

## The factorial-arm bug (a real bug in her pipeline — flag to Nikita)
*(Registry entry: [bugs.md](bugs.md) A3.)*
LIFT is a 2×2 factorial. Her `check_nonplacebo` filters arms by **title**, so factorial arms named
`"X/Placebo"` are silently treated as placebo and **dropped**:

| LIFT arm | what it is | her pipeline keeps it? |
|---|---|---|
| Pyridostigmine/LDN | the stack | ✅ |
| Pyridostigmine/Placebo | **pyridostigmine main effect** | ❌ dropped (label has "Placebo") |
| Placebo/LDN | **LDN main effect** | ❌ dropped (label has "Placebo") |
| Placebo/Placebo | control | ✅ dropped (correct) |

Run naively, LIFT keeps **only the stack** — and the **LDN-alone arm (the 5183-signal target) is lost.**
This affects **any** 2×2 factorial in her pipeline, not just LIFT.

**Fix:** relabel factorial arms to their non-placebo component before her filter —
`"Placebo/LDN" → "Low-Dose Naltrexone"`, `"Pyridostigmine/Placebo" → "Pyridostigmine"`,
`"Pyridostigmine/LDN" -> "Pyridostigmine + Low-Dose Naltrexone"`. Then NATURAL can target all
three main-effect / interaction arms. Implemented in `long_covid_eval.py::relabel` for the
arm-level eval CSV; a relabeled JSON/Experiment is still needed if pinned `naturalv2` will run
directly on the LIFT main-effect arms.

This operationalizes the candidates-CSV guidance ("predict the **main effects**, the community can't
isolate the stack"): the *trial* isolates them via the factorial; her *arm filter* was discarding them;
and the *corpus* signal is for the stack — so LDN-alone is the hard, high-value prediction.

## Artifacts
- `data/long_covid_eval_set.csv` - 88 trials / 153 prediction-target arms (LIFT relabeled).
- `relink_long_covid.py` + `litlabels/extract_labels.py::candidate_papers/extract_best` — the multi-paper push.
- `long_covid_eval.py` — the eval-set generator (+ the factorial relabel).
