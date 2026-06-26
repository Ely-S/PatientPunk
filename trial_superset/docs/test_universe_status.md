# Test-universe status filter: `status:act` vs recruiting-inclusive

**Date:** 2026-06-25 · **Context:** M1 reproduction of Nikita's NATURAL-v2 study
(`long_covid_noparallel_notbinary_apo`), naturalv2 @ pinned `16ca178`.

## TL;DR
NATURAL-v2's test universe is `aggFilters=studyType:int,results:without,status:act`,
where **`status:act` = "Active, not recruiting" only** — it excludes every
still-**recruiting** trial, including **LIFT (NCT06366724)**, our top pick.

- Recruiting trials can **never** be in the **training** set (no posted results ⇒ no
  labels). This only ever affects the **test / prediction** set.
- Her *shared* study's test set is effectively **recruiting-inclusive**: it matches the
  relaxed universe **48/51**, but strict `status:act` only **13/51**. So the pinned
  repo's `status:act` does **not** reproduce her shared test set; the relaxed status does.
- We therefore use a **relaxed test universe** (status ∈ {ACTIVE_NOT_RECRUITING,
  RECRUITING, ENROLLING_BY_INVITATION}) as the selectable base. It is both more faithful
  to her shared study and includes LIFT.

## How we found it
LIFT was absent from our strict test pull. Peeling the filters (pinned to LIFT):

| filter | LIFT |
|---|---|
| `results:without` | PRESENT |
| `studyType:int` | PRESENT |
| `status:act` | **DROPPED** ← sole cause |
| `query.cond=COVID` | would include (tagged Long COVID / PASC) |

LIFT's live `overallStatus = RECRUITING`. Our entire strict test download was
**74/74 ACTIVE_NOT_RECRUITING**, confirming `status:act` excludes recruiting.

## Quantification (Long COVID, `noparallel_notbinary_apo`)
CT.gov, scope `query.cond=COVID`, `studyType:int,results:without`, today:

| universe | status set | test trials |
|---|---|---|
| **strict** (her repo `status:act`) | ACTIVE_NOT_RECRUITING | **13** |
| **relaxed** | + RECRUITING + ENROLLING_BY_INVITATION | **50** (**+37**) |

- **LIFT (NCT06366724) ∈ relaxed.**
- Her shared `test_trials` (51): **48** ∈ relaxed, **13** ∈ strict, **3** true drift
  (`NCT06928480, NCT06960928, NCT07559994`).
- The 37 additions are overwhelmingly genuine Long COVID trials (e.g. baricitinib
  `NCT06631287`, anakinra `NCT05926505`, taurine `NCT06721949`, immunoadsorption
  `NCT07316127`, plitidepsin `NCT06766825`, antiviral `NCT06511063`) — closely mirroring
  the team's `candidates_final_cut`. Two are acute-COVID substring-quirk catches
  (`NCT04351347` ivermectin, `NCT04382846`).

## Why her pipeline chose `status:act` (the tradeoff)
"Active, not recruiting" = **recruitment complete** ⇒ arms/enrollment locked, nearer and
more certain readout = a cleaner prediction target. Still-recruiting trials can change
(arms, enrollment, termination) and read out later. Relaxing trades target stability for
the ability to predict trials *now* (incl. LIFT) — earlier-stage, design could still shift.
**Training is identical either way**; this only changes which prospective trials are eligible.

## Open question for Nikita
The repo's pinned code uses `status:act`, but her **shared** study's test set is
recruiting-inclusive (48/51). So her shared output was produced by a **different status
selection** than the current pinned code implies (older/edited config, or manual
curation). Worth confirming which she intends as canonical before we lock the test
universe — we can match either.

## Artifacts
- **Relaxed universe (select off this):** [`data/relaxed_test_universe.csv`](../data/relaxed_test_universe.csv)
  — columns: `nct, overall_status, phase, primary_completion, title, conditions, interventions`.
- Generator: [`relaxed_test_universe.py`](../relaxed_test_universe.py) (calls her
  `find_valid_ncts` / `find_condition_ncts` / `check_trial` unchanged; only the download
  status filter is relaxed).
