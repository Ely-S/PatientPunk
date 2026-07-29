# Adjudication policy

The rules used to resolve `review_20260728T035253Z.json` (146 cells). They exist
because inconsistency across 146 cells is worse than either choice on any one of
them. Anything gold-labeled `adjudicated` after 2026-07-27 follows these; change
them only by re-adjudicating the affected cells, not silently on the next pass.

Where a rule makes gold *narrower* than a defensible extraction, the cost is a
false EXTRA against the model. That is the cheaper error here: an EXTRA is
visible in triage and can be re-litigated, while a permissive gold quietly
rewards inference the production prompt explicitly forbids ("Only extract
information that is EXPLICITLY stated. Never infer or guess").

## The two decisions TRACKER.md flagged

**1. `dosage` holds the bare dose, not dose+drug.** `2-4 mg`, not `2-4 mg
nicotine gum`. The field description says "retain the number and unit";
`medications` already carries the drug name, and the 1-5-word format rule breaks
on dose+drug for anything with a multi-word name. Dietary quantities (`3 L
water`, `650 g raw veg`) are not doses -- the field is medication/supplement
dosages.

**2. `functional_status_tier` requires a stated function level.** Extract it only
when the author states their own functional level, either as the tier word
itself ("I'm bordering on severe", "housebound", "bedbound since 13") or as an
unambiguous *global* capacity statement ("I can't leave the house", "my absolute
maximum is 3,000 steps"). Do **not** derive a tier from symptom severity, from
distress, from a single episodic crash ("I was bedbound for 3 days after a
walk"), or from work/school status alone.

This is the stricter of the two readings, and it is what the two labelers
already agree on in practice: every fixture record where a tier word or a global
capacity statement appears was an `agreed` cell, and 7 of the 8 disagreements
are production inferring a tier where the labeler left the field empty (the
eighth, `t3_mqlzc2`, is the two models inferring *different* tiers from the same
symptom description). Production's inferences also disagree
with each other in kind -- `mild` for someone on medical leave, `severe` for
someone working full-time -- which is what an inferred tier looks like when the
text does not carry one.

## The other rules the 146 cells forced

Each of these came up in more than one cell; they are recorded so the next
adjudication pass does not re-decide them differently.

- **Acute COVID is not a `condition`.** An infection goes to `prior_infections`
  (and `onset_trigger` if the author ties onset to it). `conditions` takes named
  diagnoses the author has: long covid, POTS, GERD, fibromyalgia, IBS, anxiety.
  "Long covid" only when the author claims it, not because the subreddit implies
  it.
- **`prior_infections` vocabulary is `covid`** -- bare, no `covid-19`, no date
  qualifier (`covid june 2022` -> `covid`). This is the single largest
  disagreement field (14 cells) and it is a vocabulary question, not a prompt
  one: `covid-19` -> `covid` belongs in `normalize.py` `_CANONICAL_MAPS`.
- **No arithmetic for `age_at_onset` or duration fields.** Extract only what the
  text states. "23 y/o, got covid in January" does not yield `age_at_onset: 22`;
  "I developed ME/CFS when I was 12" does. Same for
  `long_covid_duration_months`: "5 months later" -> `5`; inferring 6 from a
  January infection and a 30-day recovery -> nothing.
- **`infection_count` needs a count.** One mentioned infection is not a stated
  count of infections. All 6 production `1`s resolved to empty. (Same failure
  shape as the tier: a plausible default filled in where the text is silent.)
- **Work and school ability go to `work_disability_status`, never
  `social_impact`.** `social_impact` is relationships, isolation, support,
  stigma, and financial hardship. This split was the cause of several
  double-counted cells on both sides.
- **Third-party posts extract nothing clinical.** In `t3_124jme1` the illness is
  the author's mother's: every clinical field is empty, and only the author's own
  stated experience (`mental_health: stress`) survives.
- **Symptoms are not conditions**, per the prompt's own list -- `migraines`,
  `chronic cough`, `brain fog` stay out of `conditions` even when both models
  put them there.
- **Normal test results are `biomarker_results`** when the text states them
  ("all of these results came back fine" -> `normal mri | normal eeg | ...`).
  BMI is not a lab value and this schema has no `bmi_weight` field, so it is
  dropped rather than filed under biomarkers.
- **Vaccines are not `medications`.**
- **`treatment_outcome` keeps one treatment per value.** `nicotine patch +
  butyrate: helped: migraine` is not a legal value; it becomes the single-drug
  claim the text supports. Treatment names match the spelling used in
  `medications` / `alternative_treatments` for the same record.
- **`symptom_trajectory`** prefers the description's vocabulary
  (improving/worsening/stable/relapsing) where the text fits it, and the
  author's own state where it does not (`full remission`, `not improving`).
  Unlike `functional_status_tier`, this field's description does not say "use
  ONLY", so it is not treated as a closed enum.
