# Validation report — v2 psychedelic pharmacology extraction

Pinned run: `710567555e22b68c025d8ceb1c3373564d7f9b01dcc5fe94b02b7c3209ecbc05`
(`data/probes/psychedelic_pharmacology.db`, SHA-256 `2edbe613…f96cc`).
Aggregates only. No quote, source text, author hash or Reddit ID appears here.

Two questions, answered separately:

1. **Precision**: is each extracted field right? This needs a human to read records
   against their source (§1; two fields are awaiting a re-check, §1.1).
2. **Stability**: does the extraction come out the same when it is re-run? This needs
   repeat passes (§2, done).

---

## 1. Item-level precision (human review)

Protocol: `docs/validation_protocol.md`. Sheet: `data/validation/psychedelics_v2_sample.csv`
(gitignored), with 184 records, seed 20261002, and at most 2 per account per stratum. All
184 rows were scored by one human reviewer. The figures come from:

```bash
uv run python scripts/score_validation.py data/validation/psychedelics_v2_sample.csv
```

Precision = correct / (correct + incorrect), with a Wilson 95% interval. `unclear` verdicts
are counted but kept out of the denominator.

### 1.1 A defect in the first sheet, and which verdicts it affects

The first version of `build_validation_sample.py` used the same column name for an extracted
field and for its scoring column in three places: `direction`, `ae_category` and
`ae_severity`. The CSV writer kept one column per name, so the empty scoring cell overwrote
the extracted value. **The reviewer never saw the extracted direction, AE category or AE
severity.** Every other extracted field the rubric asks about was visible: quotes, source
window, drug, subject, exposure status, symptom target and class, doses and duration.

The builder now writes those three values as `extracted_direction`,
`extracted_ae_category` and `extracted_ae_severity`, and refuses a sheet with repeated
column names (regression test in `tests/test_validation_tools.py`). The scored sheet was
patched in place: it was regenerated with the same seed, checked to align row for row on
`(row_id, stratum, claim_id, record_type, record_index)`, and given the three columns.
No verdict was changed. The pre-patch file is kept as
`data/validation/psychedelics_v2_sample.scored_backup.csv`.

How each affected verdict stands:

| verdict | rows | status |
|---|---|---|
| `ae_severity`, `severe_adverse_event` stratum | 40 | **valid**: the stratum is defined by `severity = severe` (the patched column confirms all 40) |
| `direction`, `random_helped` stratum | 30 | **valid**: the stratum is defined by `direction = helped` (all 30 confirmed) |
| `direction`, fatigue and PEM strata | 84 | **awaiting re-check**: the reviewer could not see the extracted direction (58 helped, 21 no effect, 4 worsened, 1 mixed) |
| `ae_category`, `severe_adverse_event` stratum | 40 | **awaiting re-check**: the reviewer could not see the extracted category |

Numbers below that rest on the last two rows are marked *pending* and are not used in any
conclusion.

### 1.2 Precision by field

| field | correct | incorrect | unclear | precision | 95% Wilson | target | result |
|---|---|---|---|---|---|---|---|
| `quote_supports_field` | 179 | 5 | 0 | 97.3% | 93.8–98.8% | 100% | **FAIL** |
| `drug_attribution` | 174 | 6 | 4 | 96.7% | 92.9–98.5% | ≥95% | PASS (lower bound does not clear it) |
| `self_actual_use` | 176 | 6 | 2 | 96.7% | 93.0–98.5% | ≥95% | PASS (lower bound does not clear it) |
| `dose` | 72 | 8 | 0 | 90.0% | 81.5–94.8% | ≥90% | PASS, at the line |
| `duration` | 15 | 6 | 0 | 71.4% | 50.0–86.2% | ≥90% | **FAIL** (n=21) |
| `ae_severity` (all `severe`) | 19 | 19 | 2 | 50.0% | 34.8–65.2% | ≥90% | **FAIL** |
| `ae_category` | 39 | 0 | 1 | 100.0% | 91.0–100% | ≥90% | *pending re-check* |
| `symptom_class_matches_meaning` | 100 | 9 | 0 | 91.7% | 85.0–95.6% | none | — |
| `direction`, `random_helped` only | 29 | 0 | 1 | 100.0% | 88.3–100% | none | — |
| `direction`, fatigue and PEM strata | 80 | 3 | 1 | — | — | none | *pending re-check* |

Three of the protocol's targets fail: quote/source integrity, duration and AE severity.
Drug attribution, self-report and dose pass on their point estimates, but 184 records
cannot show that their true rates clear the bar.

### 1.3 By stratum (fields that bear on the findings)

| stratum | field | precision | n |
|---|---|---|---|
| `fatigue_ketamine` | quote / drug / self | 100% / 100% / 100% | 40 / 39 / 40 |
| `fatigue_ketamine` | `symptom_class_matches_meaning` | 87.5% (73.9–94.5%) | 40 |
| `fatigue_psilocybin_lsd` | `symptom_class_matches_meaning` | 100% (83.9–100%) | 20 |
| `pem_explicit` | `symptom_class_matches_meaning` | 100% (86.2–100%) | 24 |
| `pem_explicit` | `drug_attribution` | 87.5% (69.0–95.7%) | 24 |
| `random_helped` | `symptom_class_matches_meaning` | 84.0% (65.3–93.6%) | 25 |
| `random_helped` | `drug_attribution` | 93.3% (78.7–98.2%) | 30 |
| `random_excluded` | `self_actual_use` (exclusion was right) | **80.0%** (62.7–90.5%) | 30 |
| `severe_adverse_event` | `ae_severity` | **50.0%** (34.8–65.2%) | 38 |

### 1.4 The three questions

**Do the fatigue-class targets mean general fatigue, or are they diluted PEM?** Mostly
general fatigue. In ketamine, 6 of 40 sampled fatigue or low-energy effects describe
post-exertional malaise (15%, Wilson 7–29%), and 35 of 40 have a class that matches their
meaning. In psilocybin and LSD, 0 of 19 describe PEM and 20 of 20 classes match. The PEM
leakage is therefore confined to ketamine, the arm carrying the headline. The 6 PEM records
in the ketamine sample were extracted as 3 helped, 1 no effect and 2 worsened. That is 50%
helped, against 62% (21 of 34) for the genuinely general-fatigue records, so removing them
would raise the sampled helped share by about 2 points. A shift that small cannot account
for a 46-pp deficit, so the deficit is not an artefact of PEM reports being counted as
fatigue. Whether the remaining helped and no-effect labels are right waits
on the `direction` re-check (§1.1).

**Is `pem_explicit` undercounted?** Slightly, and only through ketamine's fatigue class.
`pem_explicit` itself is precise: 24 of 24 sampled targets describe PEM (Wilson 86–100%).
Outside it, 0 of 29 random helped effects and 0 of 19 psilocybin/LSD fatigue effects describe
PEM, while 6 of 40 ketamine fatigue effects do. Ketamine has 99 fatigue or low-energy effect
records, so roughly 15 more PEM records may sit there (Wilson range about 7–29). Adding
them would not bring any drug's PEM cell above the evidence gate on its own.

**How often is a `severe` adverse event really severe by the prompt's definition** (medical
care, danger, major persistent impairment, or stopping treatment)? Half the time: 19 of 38
(Wilson 35–65%), with 2 unclear. The headline "98 severe adverse-event records from 49
accounts" is likely overstated by about twofold. It should be read as reports the model
called severe, not as severe events.

### 1.5 Other findings

- **The inclusion rule under-includes.** 6 of 30 sampled excluded claims (20%) actually
  described the author's own use. Excluded claims are 27% of all claims, so some real
  reports are missing from every denominator. Precision on included claims is high (96.7%),
  so the error runs toward excluding real use, not toward including other people's.
- **Stated duration is unreliable.** 15 of 21 duration bins were correct. Together with the
  91% of effects that state no duration, this makes the duration section of notebook 2
  descriptive at best.
- **Quote integrity misses its 100% target.** 5 of 184 cited quotes did not support their
  field, including 2 of 24 in `pem_explicit`. The mechanical grounding floor caught none of
  these, as it is not designed to.

### 1.6 Still to do

1. Re-check `direction` on the 84 fatigue and PEM rows and `ae_category` on the 40 severe-AE
   rows against the new `extracted_*` columns, then re-run the scorer.
2. Replace the *pending* cells above with the re-checked results.
3. Cite this report in notebook 1 §10 and notebook 3 §11, in place of "unvalidated" and the
   v1 instability figures.

---

## 2. Repeat-pass stability

### 2.1 The passes

The v2 spec was run unchanged into two fresh databases, so neither pass had any cache hits.

| pass | database | model | `run_id` | units complete / failed | cost |
|---|---|---|---|---|---|
| v2 (reference) | `psychedelic_pharmacology.db` | `deepseek/deepseek-v4-flash` | `710567555e22…` | 1,192 / 14 | $2.07 |
| same config | `psychedelic_pharmacology_repeat.db` | `deepseek/deepseek-v4-flash` | `710567555e22…` (identical) | 1,187 / 19 | $1.84 |
| different model | `psychedelic_pharmacology_altmodel.db` | `deepseek/deepseek-v4.1-flash` | `c66c169f2c7d…` | 1,204 / 2 | $5.24 + 5 attempts with unknown billing |

All three use temperature 0, `max_tokens` 32768, `reasoning_effort` high, and OpenRouter
with routing left unpinned. The planned `run_id` of the same-config pass equals v2's, which
confirms an identical spec, cohort, unit set and request config.

**Transport differs from v2, and the `run_id` does not record it.** The two new passes ran
with a 300 s client read timeout (v2: 90 s), patched at runtime. The reason is that
`deepseek-v4.1-flash` averaged about 7,800 output tokens per completed unit, and 5 of its 20
pilot units timed out at 90 s. A transport setting is not part of the run identity, so it
does not move `run_id`.

The temperature is 0, but OpenRouter routes each request to one of several endpoints, so
the "same config" pass is not guaranteed to hit the same backend as v2.

Validation-failure profile, same-config pass: 238 validation failures, of which 52 were
`outcomes_on_excluded_event`, 39 `empty_quote`, 27 `wrong_source_reference`, 23
`quote_not_grounded` and 97 other (v2: 179 in total). The different-model pass had 19
validation failures and none of them was `outcomes_on_excluded_event`.

### 2.2 Method

Claims do not align one-to-one across runs, so agreement is measured at the level the
analysis uses: one row per (account, drug) cohort pair. The universe is pairs whose units
all completed in both runs. A pair with no included claim in a run counts as all-negative
and `not_stated` there. For each pair-level field the table reports Cohen's κ and raw
agreement. Pair AE status is the strongest status over the pair's claims (`reported` >
`explicit_none` > `not_stated`). Symptom classes use the notebooks' display class.

```bash
uv run python scripts/compare_probe_runs.py data/probes/psychedelic_pharmacology.db data/probes/psychedelic_pharmacology_repeat.db
uv run python scripts/compare_probe_runs.py data/probes/psychedelic_pharmacology.db data/probes/psychedelic_pharmacology_altmodel.db
```

### 2.3 Agreement

κ / raw agreement. "Positives" are v2 → other pass.

| pair-level field | v2 vs same config (n=1,039) | positives | v2 vs v4.1-flash (n=1,053) | positives |
|---|---|---|---|---|
| any included claim | 0.931 / 0.987 | 934 → 935 | 0.894 / 0.981 | 947 → 949 |
| any helped | 0.885 / 0.945 | 629 → 634 | 0.878 / 0.941 | 640 → 610 |
| any no effect | 0.814 / 0.949 | 171 → 170 | 0.820 / 0.950 | 173 → 182 |
| any worsened | 0.690 / 0.962 | 64 → 74 | 0.576 / 0.954 | 66 → 54 |
| AE status | 0.876 / 0.956 | 210 → 214 | 0.852 / 0.945 | 214 → 238 |
| any severe AE | 0.769 / 0.979 | 50 → 50 | 0.688 / 0.970 | 50 → 58 |
| class: `pem_explicit` | 0.680 / 0.989 | 18 → 17 | 0.660 / 0.987 | 19 → 23 |
| class: `exertion_intolerance` | 0.283 / 0.995 | 4 → 3 | 0.219 / 0.993 | 5 → 4 |
| class: `fatigue_general` | 0.780 / 0.975 | 66 → 60 | 0.734 / 0.967 | 67 → 74 |
| class: `low_energy` | 0.593 / 0.975 | 37 → 29 | 0.619 / 0.972 | 37 → 42 |
| class: `mood_cognitive` | 0.687 / 0.874 | 292 → 289 | 0.696 / 0.870 | 300 → 349 |
| class: `pain` | 0.786 / 0.962 | 106 → 102 | 0.822 / 0.965 | 110 → 123 |
| class: `other` | 0.538 / 0.815 | 291 → 283 | 0.572 / 0.805 | 300 → 415 |
| class: `unspecified` | 0.470 / 0.763 | 336 → 362 | 0.390 / 0.765 | 341 → 182 |
| symptom-class set, exact match¹ | 0.490 | | 0.449 | |
| symptom-class set, mean Jaccard¹ | 0.609 | | 0.579 | |

¹ Over pairs that are effect-bearing in either run (773 and 769 pairs).

### 2.4 Does the headline survive a re-run?

The headline is ketamine general fatigue against ketamine's other symptom classes,
helped-reporting, computed as in notebook 3 §1 (reporter-clustered bootstrap, same seed).

| run | ketamine `fatigue_general` helped | other classes | difference | 95% clustered interval |
|---|---|---|---|---|
| v2 | 37.1% (n=35) | 83.5% | −46.4 pp | −60.4 to −30.1 |
| same config | 37.1% (n=35) | 83.5% | −46.3 pp | −63.2 to −29.2 |
| v4.1-flash | 35.1% (n=37) | 81.9% | −46.8 pp | −62.6 to −30.1 |

Explicit-PEM cells stay below the evidence gate in every run: at most 9, 10 and 12
reporter accounts per drug respectively, against a gate of 20 rows and 10 accounts.

### 2.5 Reading

- **Pair-level outcomes are much more stable than the v1 record-level figures suggested.**
  The notebooks cited v1's 36.5% field-set / 58.8% value agreement between two identical
  passes. That figure was measured on a different pipeline and at the record level. At the
  pair level used by the v2 analysis, a re-run of the same config gives κ 0.81–0.93 for
  inclusion, any helped, any no-effect and AE status.
- **Rare fields are less stable.** Any worsened (κ 0.69), any severe AE (0.77) and the small
  symptom classes (`pem_explicit` 0.68, `low_energy` 0.59, `exertion_intolerance` 0.28) move
  more between passes. Results resting on them deserve wider error than their sampling
  intervals show.
- **The symptom-class set is the least stable output.** Only about half of effect-bearing
  pairs get the same set of classes on a re-run (exact match 0.49, mean Jaccard 0.61), and
  most of the churn is between `unspecified` and `other`, i.e. whether a target is stated at
  all. The different model states targets far more often (`unspecified` 341 → 182 pairs),
  which moves pairs into `other` and the named classes. That is a model difference in what
  gets written into `target`, not noise.
- **The headline finding replicates.** The ketamine general-fatigue deficit comes out at
  −46 to −47 pp in all three passes, with near-identical intervals, including under a
  different model version.
- **This is stability, not correctness.** Two passes can agree and both be wrong. Precision
  is §1's job.

Every interval in notebooks 2 and 3 still covers sampling only. A pair-level field with
κ ≈ 0.8 carries extraction noise on top of that, and so does a class with κ ≈ 0.5–0.7.
