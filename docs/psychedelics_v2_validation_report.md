# Validation report — v2 psychedelic pharmacology extraction

Pinned run: `710567555e22b68c025d8ceb1c3373564d7f9b01dcc5fe94b02b7c3209ecbc05`
(`data/probes/psychedelic_pharmacology.db`, SHA-256 `2edbe613…f96cc`).
Aggregates only. No quote, source text, author hash or Reddit ID appears here.

Two questions, answered separately:

1. **Precision**: is each extracted field right? This needs a human to read records
   against their source (§1, pending).
2. **Stability**: does the extraction come out the same when it is re-run? This needs
   repeat passes (§2, done).

---

## 1. Item-level precision (human review) — PENDING

Protocol: `docs/validation_protocol.md`. Sheet: `data/validation/psychedelics_v2_sample.csv`
(184 records, seed 20261002, at most 2 per account per stratum). Scoring is in progress.
This section will hold the output of
`uv run python scripts/score_validation.py data/validation/psychedelics_v2_sample.csv`
and the answers to:

- Do the fatigue-class targets mean general fatigue, or are they diluted PEM?
- Is `pem_explicit` undercounted?
- How often is a `severe` adverse event really severe by the prompt's definition?

Until then, every v2 number remains **unvalidated at the item level**.

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
