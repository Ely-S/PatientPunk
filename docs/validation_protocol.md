# Validation protocol — psychedelic pharmacology extraction (GATE 4)

This is the item-level human review that the v2 run skipped (`docs/psychedelic_probe_run_report.md` §1).
A person reads each sampled record against its source window and scores whether the
extraction is right. **No LLM fills in a verdict.**

## The sheet

```bash
uv run python scripts/build_validation_sample.py      # writes data/validation/psychedelics_v2_sample.csv
uv run python scripts/score_validation.py data/validation/psychedelics_v2_sample.csv
```

The sheet is quote-bearing and lives under `data/` (gitignored). Never commit it, and never
paste a row, quote or source excerpt into a report, commit, PR or chat. Only the scorer's
aggregate output leaves `data/`.

It reads the pinned v2 run (`710567555e…`, database SHA-256 `2edbe613…`) read-only and
samples records with a fixed seed (recorded in the `seed` column and in
`psychedelics_v2_sample.manifest.json`):

| stratum | n | records | why |
|---|---|---|---|
| `fatigue_ketamine` | 40 | ketamine effects whose target matches `fatigue_general` or `low_energy` | the headline finding |
| `fatigue_psilocybin_lsd` | 20 | the same, psilocybin and LSD | the comparison arm of the headline |
| `pem_explicit` | all, after the cap | effects whose target matches `pem_explicit` | is PEM undercounted or mislabelled? |
| `severe_adverse_event` | 40 | adverse events graded `severe` | the highest-stakes field |
| `random_helped` | 30 | random `helped` effects | base rate of label error |
| `random_excluded` | 30 | random excluded claims | does the inclusion rule work? |

Symptom strata use the same multilabel patterns as the notebooks (`psychedelics_v2.symptom_labels`).
Each stratum takes **at most 2 rows per reporter account**, so a few prolific posters
cannot dominate it, and a record sampled into one stratum is not offered again in a later
one. The v2 sheet has 184 rows; `pem_explicit` yields 24, because its 38 remaining
records are concentrated in a few accounts.

Each row is one record: an effect, an adverse event, or (for `random_excluded`) a whole
claim. It shows the extracted fields, the quote cited for that record (`field_quote`), the
claim's subject / exposure / dose / duration quotes, and the full `source_window_text`.
Three extracted fields share a name with their scoring column, so they appear as
`extracted_direction`, `extracted_ae_category` and `extracted_ae_severity`. The plain
`direction`, `ae_category` and `ae_severity` columns are the verdicts.

## How to score

Fill each scoring column with `correct`, `incorrect` or `unclear`. Cells prefilled `n/a`
do not apply to that row; leave them. A blank cell means "not yet scored", and the scorer
reports it. Use `unclear` only when the source genuinely does not let you decide, not when
the extraction is merely imprecise; say why in `notes`.

Judge against the **source window**, not the quote alone. The quote may lightly paraphrase;
what matters is whether the source says what the field claims.

### `quote_supports_field`

Does `field_quote` appear in substance in the source window, **and** does it support this
record's field?

- *Correct:* the effect is `helped` / target "brain fog", and the quote is the author saying
  their thinking cleared up for weeks after a session.
- *Incorrect:* the quote is real but is about a different symptom from the one in the
  target, or comes from a sentence about another drug.

### `drug_attribution`

Is the record about **this row's `drug`**, as opposed to another substance in the same
passage or a combined stack?

- *Correct:* the author lists three supplements and then says that ketamine in particular
  lifted their mood.
- *Incorrect:* the author says that a combination of LDN and microdosing helped, and the
  record credits psilocybin alone. The prompt says a stack outcome must be withheld unless
  the text isolates the target.

### `self_actual_use`

Did **the author** actually take the drug? For `random_excluded` rows, score whether the
**exclusion** was right: `correct` means the passage really is about someone else's use, a
plan, a refusal, or is indeterminate.

- *Correct (included row):* the author describes their own infusion series.
- *Incorrect (included row):* the author is summarising a friend's experience, or says they
  are thinking about trying it.
- *Incorrect (excluded row):* the model marked the passage `unclear`, but the author plainly
  describes their own past use a sentence earlier.

### `direction`

Effect rows only. Is `helped` / `no_effect` / `worsened` / `mixed` right for the target?

- *Correct:* `worsened` for a passage where the author's fatigue got worse for days after a dose.
- *Incorrect:* `helped` where the author says that it helped other people but did nothing for them.

### `symptom_class_matches_meaning`

Effect rows with a stated target. Does `symptom_class` (and, if more than one,
`symptom_labels`) describe what the author meant, not just the words that matched?

- *Correct:* `fatigue_general` for a target about constant daytime exhaustion.
- *Incorrect:* `low_energy` for a target where "energy" means the atmosphere of a trip, or
  `fatigue_general` for a target that actually describes a crash after exertion (that is
  PEM; also mark `describes_pem` = yes).

### `describes_pem`

Effect rows only. `yes` / `no` / `unclear`: does the target, read with its source, describe
**post-exertional malaise**, meaning a delayed worsening triggered by physical or mental
exertion? This is not a correctness verdict. It measures whether the `pem_explicit` class
is precise and whether PEM hides in the fatigue classes.

- *Yes:* the author says that walking further than usual left them bedbound two days later.
- *No:* the author says they are tired all the time, with no link to exertion.

### `ae_category`

Adverse-event rows. Is the closed category right? `other` is correct only when no listed
category fits.

- *Correct:* `anxiety_panic` for a racing heart and fear during a session that the author
  describes as a panic attack.
- *Incorrect:* `cardiac` for the same passage, when the author attributes the racing heart to panic.

### `ae_severity`

Adverse-event rows with a severity. Use the prompt's definitions: *mild* = brief or tolerable;
*moderate* = meaningfully disruptive or caused a dose change; *severe* = **medical care,
danger, major persistent impairment, or stopping treatment**. Strong language alone is not
severity.

- *Correct (`severe`):* the author went to an emergency department, or stopped the treatment
  because of the event.
- *Incorrect (`severe`):* the author calls a session "awful" and "the worst night", but it
  resolved by morning and they continued treatment. That is mild or moderate.

### `dose`

Rows whose claim carries a dose. Do the amount, unit, route and intent in `doses` match the
source, with nothing invented or converted?

- *Correct:* "two grams of dried mushrooms" becomes amount 2, unit g.
- *Incorrect:* the unit is filled in as mg where the author gave none, or a range is
  collapsed to one end.

### `duration`

Rows with a duration. Is the bin right, and was the duration **stated** rather than inferred?

- *Correct:* `one_to_four_weeks` for "the lift lasted about three weeks".
- *Incorrect:* `ongoing_at_report` where the author never says whether the effect continues.

## Targets

Precision = correct / (correct + incorrect), with a Wilson 95% interval; `unclear` is
counted and reported but kept out of the denominator.

| field | target |
|---|---|
| `quote_supports_field` (quote/source integrity) | 100% |
| `drug_attribution` | ≥95% |
| `self_actual_use` | ≥95% |
| `dose` | ≥90% |
| `duration` | ≥90% |
| `ae_category`, `ae_severity` | ≥90% |

`direction`, `symptom_class_matches_meaning` and `describes_pem` have no pass mark. They are
reported because the findings depend on them. The scorer prints PASS/FAIL on the point
estimate and says whether the interval's lower bound clears the target. At this sample size
a 100% target allows zero errors.

## What the report must answer

The results go into `docs/psychedelics_v2_validation_report.md`, and it must answer:

1. Do the fatigue-class targets mean general fatigue, or is the class diluted PEM?
   (`symptom_class_matches_meaning` and `describes_pem` in the two fatigue strata.)
2. Is `pem_explicit` undercounted? (`describes_pem` = yes outside the `pem_explicit` stratum.)
3. How often is a `severe` adverse event really severe by the prompt's definition?
   (`ae_severity` in `severe_adverse_event`.)
