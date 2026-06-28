# Long-COVID focus: the three targets, the training lever, and the factorial-arm bug

**Date:** 2026-06-25 · scope decision: keep the prediction universe at **Long COVID** (that's where
the candidate targets *and* the Reddit corpus signal are; the other cluster conditions are mostly
off-premise or population-mismatched — see master CSV flags).

## The three trials we're actually predicting (`candidates_final_cut.csv`)
| trial | drug(s) | corpus signal (LC) | verdict |
|---|---|---|---|
| **Tirzepatide** NCT07128082 | tirzepatide | 446 | **cleanly predictable** — single-agent, blinded, fatigue PRO |
| **LIFT** NCT06366724 | LDN + pyridostigmine (2×2 factorial) | **LDN 5183, pyrido 683** | richest signal; needs the arm-relabel below + recruiting-inclusive test |
| **IVIG** NCT06305793 | IVIG | 0 | off-premise — clinic-administered, no corpus signal, combination |

## Growing the Long-COVID *training* set — what works
- **Strings are NOT the lever.** Of 205 valid COVID structured-results trials, 17 are Long COVID;
  the 188 excluded are genuine *acute* COVID (pneumonia/ARDS/coagulopathy). Broadening strings just
  re-admits acute contamination. `query.cond="Long COVID"` = 28 total → ~17 after criteria.
- **Cross-bucket reclaim is ~0 net** — the Long-COVID download already uses `query.cond=COVID`, which
  captures every COVID trial regardless of which other condition bucket it also appears in.
- **The real lever = the no-results pool.** Long COVID is recent, so most completed trials never
  posted CT.gov structured results. ~85 completed-no-results Long-COVID trials exist; 41 link to an OA
  paper, of which the first pass extracted 12 and **declined 29** (mostly the *wrong* paper — review /
  protocol / secondary analysis). `relink_long_covid.py` retries those across **multiple** candidate
  papers (`extract_best`) to recover the wrong-paper declines.

## Recruiting-inclusive test universe (so LIFT is predictable)
Her `status:act` excludes recruiting trials, so LIFT (RECRUITING) was absent from the test set.
Switching to recruiting-inclusive (ACTIVE_NOT_RECRUITING + RECRUITING + ENROLLING_BY_INVITATION)
grows the Long-COVID test set **24 → 75 trials** and **includes LIFT**. Eval set persisted to
`data/long_covid_eval_set.csv` (one row per prediction-target arm, annotated with corpus signal).

## The factorial-arm bug (a real bug in her pipeline — flag to Nikita)
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
`"Pyridostigmine/LDN" → "Pyridostigmine + Low-Dose Naltrexone"`. Then NATURAL predicts all three
main-effect / interaction targets. Implemented in `long_covid_eval.py::relabel`.

This operationalizes the candidates-CSV guidance ("predict the **main effects**, the community can't
isolate the stack"): the *trial* isolates them via the factorial; her *arm filter* was discarding them;
and the *corpus* signal is for the stack — so LDN-alone is the hard, high-value prediction.

## Artifacts
- `data/long_covid_eval_set.csv` — 75 trials / 129 prediction-target arms (LIFT relabeled).
- `relink_long_covid.py` + `litlabels/extract_labels.py::candidate_papers/extract_best` — the multi-paper push.
- `long_covid_eval.py` — the eval-set generator (+ the factorial relabel).
