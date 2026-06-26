# Condition-filter audit — classification wins, noise, and differences for Nikita

**Date:** 2026-06-25 · **Context:** M2 broadening of the training universe across the
5 cluster conditions · naturalv2 @ pinned `16ca178` · filters = `noparallel_notbinary_apo`
(`randomized=True, parallel=False, num_noncontrol=1, nonhealthy=True, binary_endpoint=False`).

This documents how her **condition-matching step** (`find_condition_ncts`) performs per
condition, the wins from widening it, the noise it admits, and which changes deviate from
her shared output. Goal: the cleanest training set we can build, with every deviation
labeled for discussion with Nikita.

**Provenance** (see README): the matcher `find_condition_ncts` and the `"Long Covid"` string are
**Nikita's [N]**; the four other condition strings (POTS / Myalgic Encephalomyelitis / Fibromyalgia
/ Post-Treatment Lyme) are **TrialScout's [TS]** (`build_candidates.py`); the clean keyword
classifier that replaces the matcher is **ours [NEW]**. So the mis-classification below is a
property of *her* matcher + the condition strings, run faithfully — we measured it; we didn't cause it.

> **DECISION (2026-06-25): improved/clean classification adopted as the canonical training
> set — including the long-COVID change.** We deliberately deviate from her shared study
> (we no longer reproduce her 21/21 long-COVID retro, because we drop her acute-COVID
> trials and add the post-COVID ones she missed). Faithful mode is retained ONLY as the
> reference for the delta we'll walk Nikita through. Canonical artifact:
> `data/training_set_manifest.csv` (213 trials: 157 train+val, 56 test).

## How her condition match works (and why it misclassifies)
`find_condition_ncts` keeps a trial if **any** of its mesh + conditions terms `tc` and any
configured condition string `c` satisfy `c in tc` **or** `tc in c` (plain substring, both
directions, lowercased). Two failure modes follow directly:
- **Over-match:** a short trial term that is a substring of the condition string matches
  everything containing it. e.g. `"covid"` ⊂ `"long covid"` → every bare-`covid` (acute)
  trial matches the Long-COVID filter; `"fatigue"` ⊂ `"chronic fatigue syndrome"` → cancer/
  renal "fatigue" trials match ME/CFS.
- **Under-match:** a genuine trial whose tags don't share a substring with the condition
  string is dropped. e.g. `"post-acute covid-19 syndrome"` does not substring-match
  `"long covid"`; `"orthostatic hypotension"` does not substring-match
  `"postural orthostatic tachycardia syndrome"`.

## Audit method
`trial_superset/audit_conditions.py` — over every scope-downloaded trial that passes her
`check_trial`, compare HER condition match against a condition-specific keyword test:
- **UNDER** = looks like the condition (keyword) but her filter dropped it → widen filter.
- **OVER** = her filter kept it but it doesn't look like the condition → substring noise.

## Results (valid = passed check_trial)

| condition | valid | matched | genuine | **missed (UNDER)** | **noise (OVER)** | verdict |
|---|---|---|---|---|---|---|
| **dysautonomia** | 66 | 7 | 7 | **30** | 0 | filter far too narrow — biggest win |
| **long_covid** | 205 | 22 | 10 | **7** | **12** | both: admits acute-COVID, drops post-COVID |
| me_cfs | 15 | 14 | 9 | 0 | 5 | broadening (this audit) added 5 generic-fatigue |
| chronic_lyme | 4 | 3 | 3 | 1 | 0 | marginal (1 neuroborreliosis) |
| fibromyalgia | 95 | 91 | 91 | 0 | 0 | clean — leave as is |

(me_cfs is shown **after** the M2 fix that added `"Chronic Fatigue Syndrome"` to its filter,
taking it 1 → 14 matched.)

## Per-condition findings

### dysautonomia — pure win (no faithfulness tension)
Filter `["Postural Orthostatic Tachycardia Syndrome"]` matches only 7 of 66 valid trials.
**30 genuine autonomic trials are dropped**, e.g.:
- `NCT00555880`, `NCT01030874` — orthostatic hypotension
- `NCT00738062` — neurogenic orthostatic hypotension
- `NCT01044693`, `NCT00633880` — multiple system atrophy / pure autonomic failure
**Fix:** widen filter to `+ ["Orthostatic Hypotension", "Orthostatic Intolerance",
"Dysautonomia", "Autonomic Failure", "Autonomic Dysfunction"]` → ~7 → ~30+.
**Judgment call:** `multiple system atrophy` / `pure autonomic failure` are autonomic but
distinct neurodegenerative diseases — include in a POTS-centric cluster or not? Clean win
without them is ~15–20.

### long_covid — the important one; it's *her* definition, affects her shared study
Filter `["Long Covid"]` matched 22, but only **10 are genuine** long-COVID:
- **OVER (12 acute-COVID admitted):** `NCT04359901`, `NCT04382924`, `NCT04385199`,
  `NCT04391179`, `NCT04401293`, `NCT04402060`… tagged bare `covid` / `coronavirus` /
  `ARDS` — 2020 acute hospitalization trials, matched only because `"covid"` ⊂ `"long covid"`.
- **UNDER (7 genuine post-COVID dropped):** `NCT05104749`, `NCT05633407` (post-acute
  covid-19 syndrome), `NCT05445427` (post covid syndrome), `NCT05047952` (post-COVID
  cognitive)… tagged `"post-acute covid-19 syndrome"` / `"post covid syndrome"`, which
  don't substring-match `"long covid"`.

So her Long-COVID training set is **~half acute-COVID contamination while missing real
post-COVID trials**. This is in her *shared* study too (those acute trials are why M1
reproduced her retro 21/21). **Effectively a bug in her condition definition — discuss
with Nikita.**

**Faithfulness tension:** a clean filter (require a post-COVID-specific token: `pasc`,
`post-acute`, `post-covid`, `long covid`) would *add the 7 and drop the 12* — but then we
**no longer reproduce her 21/21**. So long_covid is the one condition where "better" and
"faithful to her output" diverge.

### me_cfs — broadening helped but admits generic fatigue
After adding `"Chronic Fatigue Syndrome"` (1 → 14 matched, ~9 genuine), **5 OVER**:
`NCT00506454` (ESRD fatigue), `NCT00719563` (cancer fatigue), `NCT01700725` (Gulf War),
`NCT03891667` (post-Lyme), `NCT05047952` (post-COVID). Cause: `"fatigue"` ⊂ `"chronic
fatigue syndrome"`. **Fix:** specificity gate requiring an ME/CFS-specific token
(`myalgic`, `chronic fatigue`, `me/cfs`, `post-viral`, `post-exertional`) drops the 5,
keeps the 9.

### chronic_lyme — marginal
3 matched, 1 missed (`NCT02553473` lyme neuroborreliosis). Tiny population (PTLDS is rare);
broadening to `+ ["Lyme", "Neuroborreliosis"]` recovers ~1. Low priority.

### fibromyalgia — clean
95 valid, 91 matched, 91 genuine, 0 noise, 0 missed. Leave unchanged.

## Proposed "best training set" config (deviates from her — all labeled)
| condition | change vs her | net effect | faithful to her output? |
|---|---|---|---|
| dysautonomia | widen filter (+orthostatic/autonomic) | ~7 → ~30 | additive only ✓ |
| me_cfs | widen filter (done) + specificity gate | 1 → ~9 clean | deviates (drops 5 noise) |
| long_covid | require post-COVID token | 22 → ~17 clean | **deviates** (−12 acute, +7 post) |
| chronic_lyme | minor widen (optional) | 3 → ~4 | additive only ✓ |
| fibromyalgia | none | — | ✓ |

Two ways to ship, to keep faithfulness recoverable:
1. **Faithful mode** = her filters exactly (reproduces her shared study; documented warts) —
   `run_study.py` / `broaden.py`, output `data/m2_outputs/`.
2. **Improved mode** = clean keyword classifier (`seed_terms.CLASSIFY`) — `build_improved.py`,
   output `data/improved_outputs/`.
Both call her `check_trial` + `Study` unchanged; only trial→condition assignment differs.

## Improved-mode results (built)

Training set (train+val) **136 → 157 (+21)** and cleaner. All 5 improved studies reload in
her `Study` class.

| condition | faithful retro | improved retro | Δ | note |
|---|---|---|---|---|
| dysautonomia | 7 | **37** | **+30** | the big win; 6/47 are MSA/PAF (judgment call) |
| chronic_lyme | 3 | 4 | +1 | +neuroborreliosis |
| fibromyalgia | 90 | 90 | 0 | already clean |
| me_cfs | 14 | 9 | −5 | dropped 5 generic-fatigue (cleaner, not smaller-worse) |
| long_covid | 22 | 17 | −5 | dropped ~12 acute-COVID, added genuine post-COVID |
| **TOTAL** | **136** | **157** | **+21** | larger *and* cleaner |

The −5s on long_covid/me_cfs are **quality gains** (noise removed), not losses; dysautonomia's
+30 is the headline. long_covid test also grew 13 → 24 (post-COVID trials the substring filter
had dropped). MSA/pure-autonomic-failure inclusion in dysautonomia is the one open judgment call
(excluding them: still ~+24).

## Discussion points for Nikita (decisions we made, with the delta to show her)
1. **Long-COVID definition — likely a bug in her pipeline.** Her substring filter admits
   acute-COVID and drops post-COVID-syndrome trials, in her *own* shared study too. We
   adopted the clean classifier (drop acute, add post-COVID). Recommend she tighten the
   matcher; this changes her results, not just ours.
2. **Dysautonomia scope — we widened to orthostatic/autonomic** (7 → 37). MSA / pure
   autonomic failure are included (6 of 47); trivially excluded if she wants POTS-only
   (still ~+24).
3. **Condition matching generally — we replaced the substring-both-directions matcher with a
   per-condition keyword classifier** (`seed_terms.CLASSIFY`). Recommend the same change in
   her pipeline; the substring approach is the shared root cause across conditions.

## Artifacts
- Audit: [`audit_conditions.py`](../audit_conditions.py)
- M2 per-condition studies: `data/m2_outputs/<condition>/studies/`
- Related: [`test_universe_status.md`](test_universe_status.md) (the `status:act` test-universe finding)
