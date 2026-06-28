# Bugs & gotchas found while building trial_superset

A single registry of every bug we hit. The important group is **Category A: real bugs in
`naturalv2`** — they change Nikita's *own* published study, not just ours, so they are the
priority items for the hand-off conversation. Category B is a CT.gov search gotcha; Category C is
bugs in our own code (already fixed). Each entry: what · where · evidence · impact · fix/status.

Full detail for A1/A4/A2 also lives in the per-topic docs (linked); this file is the index.

## Index

| # | bug | location | affects HER results? | severity | status |
|---|---|---|---|---|---|
| **A1** | condition matcher over/under-matches | `naturalv2` `find_condition_ncts` | **yes** | high | flagged for Nikita; we use a clean classifier |
| **A2** | `notbinary` label = `value/N` for continuous | `naturalv2` `Experiment` | **yes** | **high** | flagged; sidecar workaround shipped |
| **A3** | factorial arms `"X/Placebo"` dropped | `naturalv2` `check_nonplacebo` | **yes** | medium | flagged; relabel workaround shipped |
| **A4** | `status:act` excludes recruiting; pinned ≠ shared | `naturalv2` test aggFilters | **yes** | medium | flagged; relaxed universe shipped |
| **B1** | `query.cond="COVID"` misses SARS-CoV-2/PASC tags | CT.gov search (our scope layer) | indirect | medium | fixed in `seed_terms` scope |
| **C1** | `inject_one` ambiguous `None` return | our `build_augmented.py` | no | medium | **fixed** |
| **C2** | misc implementation slips | our code | no | low | **fixed** |

---

## A. Bugs in `naturalv2` (affect Nikita's own results)

### A1 — Condition matcher over- and under-matches
**Where:** `find_condition_ncts` — keeps a trial if any mesh/conditions term `tc` and the condition
string `c` satisfy `c in tc` **or** `tc in c` (plain substring, both directions, lowercased).
**Evidence (Long COVID, the worst case):** 22 trials matched, only **10 genuine**.
- **Over-match (12 acute-COVID admitted):** `NCT04359901`, `NCT04382924`, `NCT04385199`, … — 2020
  hospitalization/ARDS trials, matched only because `"covid"` ⊂ `"long covid"`.
- **Under-match (7 genuine post-COVID dropped):** `NCT05104749`, `NCT05633407`, `NCT05445427`, … —
  tagged `"post-acute covid-19 syndrome"` / `"post covid syndrome"`, which don't substring-match
  `"long covid"`.

Same mechanism elsewhere: dysautonomia matched **7 of 66** valid trials (30 orthostatic/autonomic
dropped); ME/CFS admits generic cancer/renal "fatigue" via `"fatigue"` ⊂ `"chronic fatigue syndrome"`.
**Impact on her:** her shared Long-COVID study is **~half acute-COVID contamination while missing
real post-COVID trials** — those acute trials are *why* M1 reproduced her retro 21/21. **Root cause
is shared across all conditions** (the substring-both-directions match).
**Fix/status:** we replaced it with a per-condition keyword classifier (`seed_terms.CLASSIFY`);
recommend she do the same. Full detail: [condition_filter_audit.md](condition_filter_audit.md).

### A2 — `notbinary` label is `value / N` for continuous endpoints
**Where:** `Experiment` (notbinary preset) sets `avg_potential_outcome = value / N` for **every**
endpoint (`value/100` if the unit says percent). Correct as a response *rate* for binary/count;
**meaningless for a continuous mean** — it mixes the effect size with the arm's sample size.
**Evidence:**

| trial | endpoint | correct value | her label = value/N |
|---|---|---|---|
| NCT02499302 | steps/day | 7217 (n=21) | **343.7** ⚠️ |
| NCT04158427 | VAS fatigue 0–100 | 72.8 (n=5) | **14.6** ⚠️ |
| NCT05559021 | FIQ score | 44.07 (n=8) | **5.5** ⚠️ |

**Impact on her:** **~84% of current sidecar rows are continuous**, so most evaluation labels in the
notbinary path are affected (only ~52% land in [0,1], extremes to ~387). This is the prediction *target* - arguably
the highest-severity item. Present in her own notbinary study. The `binary` preset is not an escape:
it collapses the set 255 -> 21 train+val (-92%) because these symptom conditions use continuous primaries.
**Fix/status:** we keep every trial and add a model-ready **label sidecar** (`endpoint_type` +
`clean_outcome` [raw mean for continuous] + `scale_proportion`). Pinned `naturalv2` does not read
that sidecar by itself, so she would need to consume it explicitly or fix the normalization
(use the mean / standardize). Full detail: [label_normalization.md](label_normalization.md).

### A3 — Factorial arms named `"X/Placebo"` are silently dropped
**Where:** `check_nonplacebo` decides "is this a real treatment arm?" by the arm **title**. Factorial
arms named `"X/Placebo"` contain the word "Placebo", so they're classified as placebo and dropped.
**Evidence (LIFT, NCT06366724, a 2×2 factorial of LDN × pyridostigmine):**

| LIFT arm | what it is | her pipeline keeps it? |
|---|---|---|
| Pyridostigmine/LDN | the stack (both) | ✅ |
| Pyridostigmine/Placebo | **pyridostigmine main effect** | ❌ dropped |
| Placebo/LDN | **LDN main effect** | ❌ dropped |
| Placebo/Placebo | control | ✅ dropped (correct) |

**Impact on her:** run naively, LIFT keeps **only the stack** — the **LDN-alone arm (the highest
corpus-signal target, 5183 distinct authors) is lost.** Affects **any** 2×2 factorial, silently.
**Fix/status:** relabel factorial arms to their non-placebo component before her filter
(`"Placebo/LDN" → "Low-Dose Naltrexone"`); implemented in `long_covid_eval.py::relabel`. Full detail:
[long_covid_focus.md](long_covid_focus.md).

### A4 — `status:act` excludes recruiting trials, and the pinned code ≠ her shared study
**Where:** test universe `aggFilters=studyType:int,results:without,status:act`, where **`status:act`
= "Active, not recruiting" only** — it drops every still-**recruiting** trial.
**Evidence:** LIFT (`overallStatus = RECRUITING`) is dropped solely by `status:act`. For Long COVID,
strict `status:act` = 13 test trials vs relaxed = 50 (+37). Critically, her *shared* study's 51-trial
test set matches the **relaxed** universe **48/51** but strict only **13/51** — so **the pinned repo's
`status:act` does not reproduce her own shared test set** (older/edited config or manual curation).
**Impact on her:** in-flight trials (incl. LIFT) can't be prediction targets under the pinned code,
and the repo disagrees with her published test set. (Training is unaffected — recruiting trials have
no labels.) **It's a tradeoff, not purely a defect** (recruitment-complete = more stable target), but
the pinned-vs-shared mismatch needs resolving. **Fix/status:** we provide a recruiting-inclusive
relaxed universe; open question for Nikita: which status selection is canonical. Full detail:
[test_universe_status.md](test_universe_status.md).

---

## B. Data-source gotcha (CT.gov search)

### B1 — `query.cond="COVID"` misses `SARS-CoV-2` / `PASC` / `Post-COVID-19 Condition` tags
**Where:** our condition-scoped download layer (`run_study.py`, `m3_pool.py`, `relaxed_test_universe.py`)
passes `query.cond=<scope>`. A trial tagged `"Post-Acute Sequelae of SARS-CoV-2"` has **no "COVID"
substring**, and CT.gov does **not** auto-expand `COVID` to it — so the scope silently misses it.
**Evidence:** broadening the Long-COVID scope to
`COVID OR SARS-CoV-2 OR PASC OR Post-Acute Sequelae of SARS-CoV-2 OR Post-COVID-19 Condition OR
Chronic COVID OR Long-haul COVID` recovered **+4** `results:with` and **+33** `results:without`
genuine Long-COVID trials.
**Applicability to her:** her own `download_clinical_trials` pulls the *whole* corpus with **no**
condition filter, so she doesn't hit B1 in the download — **but** her matcher (A1) drops those same
SARS-CoV-2/PASC-tagged trials anyway, and **anyone scoping a pull by condition string hits B1
directly.** Worth a one-line caution in her docs.
**Fix/status:** broadened scope wired into `seed_terms.py`. Full detail:
[long_covid_focus.md](long_covid_focus.md).

---

## C. Bugs in our own code (fixed)

### C1 — `inject_one` ambiguous `None` return → `Study` reads a missing file
**Where:** `build_augmented.py::inject_one`. It returned `None` for **two** different outcomes:
"no usable numeric arm → nothing written" **and** "written but no result date". The caller then
re-added a never-written trial to the `Study` (because the schema still had arms), and her
`build_exp` crashed trying to read the absent JSON.
**Trigger:** `NCT04574050` — the first paper extraction with arms but no numeric values, surfaced by
the broadened-scope re-run.
**Fix/status:** `inject_one` now returns **`False`** when nothing is written; the caller appends only
when a file was actually written. **Fixed** (commit `d74d713`).

### C2 — Misc implementation slips (all fixed during development)
- **EPMC full-text 404** — URL had a double `/PMC/` segment; corrected to the bare PMCID path
  (`{base}/{pmcid}/fullTextXML`).
- **`enrollmentInfo` missing `type`** — some CT.gov records fail her pydantic model; wrapped
  `ClinicalTrial.from_json_file` in try/except and skip.
- **Synthetic `resultsSection` ValidationError** — her model requires `participantFlowModule` +
  `baselineCharacteristicsModule`; we stub them empty and carry only `outcomeMeasuresModule`.
- **Windows `cp1252` UnicodeEncodeError** — em-dash / non-ASCII in trial titles crash console prints;
  use ASCII-safe output.

---

## Cross-cutting note for the Nikita hand-off
A1, B1 (and to a degree A3) share a root cause: **substring/keyword matching on free-text condition
and arm fields is brittle.** The durable fix in her pipeline is a small controlled vocabulary /
classifier for (a) condition assignment and (b) arm role (treatment vs placebo), instead of
substring tests on titles. A2 is independent and is the highest-severity label-quality issue.
