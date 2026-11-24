# Labeling the demographics test set (#207)

The set scores the per-post extractor (`src/extract_demographics_conditions.py`, prompt in
`src/prompts/demographic_prompt.py`) one post at a time, as #206 reads them. Labels hold what the
post's **author** states **outright** about **themselves**, in **this post**, as written. The set lives
outside Git (`data/demographics_testset/`, ignored), because it holds patient text.

## Files

| File | One line per | Filled by |
| --- | --- | --- |
| `testset.jsonl` | item: `post_id`, `user_id` (hash), `split`, `strata`, `post_date`, `subreddit`, `text`, `label` | `label` by the labeler |
| `authors.jsonl` | multi-post author: `user_id`, `split`, `post_ids` (oldest first), `expected_profile` | `expected_profile` by the labeler |
| `manifest.json` | the sample: source database, seed, sizes, how each stratum was drawn, counts | `sample` |
| `candidates/<case>.jsonl` | candidate for a curated case: an item plus the regex `match` | `curate` |
| `curation.jsonl` | curated pick: `post_id`, `case`, `rationale`, `picked_by` | the picker |

`text` is exactly what the model reads (title and body joined by a newline; a comment has no title).
Label from `text` alone: no parent post, no username, no other posts by the same author.

## A label

```json
{"age": {"value": "34", "evidence": "I’m 34 yo female"},
 "sex": {"value": "female", "evidence": "I’m 34 yo female"},
 "country": null, "state": null, "city": null,
 "others": {"age": ["31"]},
 "notes": "31 is the age they got sick"}
```

- Each field is `null` or `{"value", "evidence"}`. `evidence` is the shortest exact quote from `text`
  that states it, copied character for character.
- `others` lists, per field, values in the post that are **not** the author's current value: other
  people's ages, past ages, places visited or treated in. A model claim equal to one of these is
  scored as a wrong-person error. Leave it `{}` when there are none.
- `label` stays `null` until the item is labeled; unlabeled items are skipped by `evaluate`. A labeled
  post that states nothing is all nulls, `"others": {}`.
- `labeled_by` beside `label` says who wrote it. A model's draft says so (`"gpt-6.2-sol via codex
  (draft)"`); a person who checks or corrects a label replaces it with their name. `manifest.json`
  records how the labels were made under `labeling`.

## Fields

One principle decides the near misses: **only a direct statement about the author is a claim.** A
value that comes close but isn't one (a bound, a comparison, a place they're from, someone else's
age) goes in `others` for that field, so a model that claims it is scored as a wrong-person error.

**age.** The author's own current age at the time of writing. Write it as stated: `"26"`,
`"30s"`, `"late 30s"`, `"25-34"`. Empty for: past ages ("when I was 22", "31 when I got sick": both go
in `others`), other people ("my 11yo son", "my wife is 36": `others`), news subjects, weights and
durations ("I'm 25 lb underweight", "15 years in"), and ages implied but not stated (school year,
birth year, "I'm a grandmother"). "I'm 18 (19 on the 19th)" is `"18"`. "57m" or "(31F)" posted as the
author's description of themselves is the age. A decade or range is a claim (`"late 30s"`). A bound,
comparison or future age is not: "over 60", "almost 20", "feel 90", "turning 40 next month" have no
age claim and go in `others` as written (`"over 60"`). So does an age at a past event, even a recent
one ("diagnosed this year at 39": `others` `["39"]`).

**sex.** The author's sex or gender in their own words: `"female"`, `"male"`, `"trans man"`,
`"non-binary"`. Give one word per identity: `|` separates distinct identities the author states
(`"non-binary | female"`), never two words for the same one ("26F single mom" is `"F"`, quoting `26F`).
Write the words as stated (#214 is still open; the evaluation scores both the words and the
normalized value). The `F`/`M` in "31F", "male", "woman", "guy", "mom", "boy" count when they describe
the author. The evaluation scores mom, guy, lady and similar words as the sex they mean, by the
pipeline's own rule (`normalize_sex` in `src/resolve_demographics.py`, the one list of these words).
Self-referring role and kinship words count ("as a mom", "I'm a dad", "speaking as a wife").
Empty for pronouns, usernames, writing style, and what others call the author. Words about other
people never count ("my husband", "my daughter"); their sex goes in `others` only when it's written
as a value a model could grab, as in "my daughter (16F)" (`others` sex `["F"]`). The author's own sex at birth or
presentation is part of their sex value, joined with ` | ` in their words: "trans masc person who was
born female" is `"trans masc | born female"`, "nonbinary (afab)" is `"nonbinary | afab"`, "nonbinary
but very female presenting" is `"nonbinary | female presenting"`. It never goes in `others`, which is
for other people and for traps such as what others call the author.

**country, state.** Where the author lives, one place each. "45 male here in Tennessee" is state
`"Tennessee"` with country empty: label only what is named, never what it implies. Living there
must be stated in the present: "here in", "I live in", "we're in", "my GP in X". A demonym or "I'm
from X" alone is not residence: "I'm Canadian" and "I'm from Ohio" go in `others` (country
`["Canada"]`, state `["Ohio"]`), written as the place's name. Abbreviations are
fine (`"TX"`, `"UK"`); the evaluation treats them as the full name, as the pipeline stores them
(`canonical_place` in `src/resolve_demographics.py`). Empty for places they visited,
were treated in, or are comparing ("doctors in Germany prescribe..."), and for unnamed places ("a
third world country"). Two places they live between ("I split time between Ohio and Florida") is
empty, as the extractor refuses two places.

**city.** The city or town where the author lives, not one they travelled to or were treated in
("saw a specialist in Boston" is `others`). A region after a comma stays with it (`"Austin, TX"`).
A metro area counts as its city: "the Boston area" is `"Boston"`, "the Bay Area" or "SF Bay Area" is
`"San Francisco"`; the evaluation matches them the same way.

**conditions.** Labeled only on the `random` stratum and the curated condition cases; elsewhere the
key is absent, and the item isn't scored for conditions. A list, `[]` when the author states none,
of the illnesses and symptoms the author says they have or had, each
`{"name", "type", "severity", "evidence"}`, as the per-post prompt (#229) asks for:
- `name`: the common name ("long covid", "ME/CFS", "POTS", "brain fog"); the evaluation matches it
  through the pipeline's `canonical_condition`, so "long-haul covid" and "long covid" are one.
- `type`: `"illness"` or `"symptom"`.
- `severity`: `"mild"`, `"moderate"` or `"severe"` as the post describes it now; `"resolved"` when the
  author says it is gone or describes it only in the past ("I had shingles in 2019"); `null` when the
  post doesn't say. A phrase naming several levels takes the worst ("moderate to severe" is `"severe"`).
- Not the author's: someone else's condition ("my mom has MS"), one they only ask or wonder about
  ("could this be POTS?"), and a covid infection itself (long covid is a condition).
- Only a named diagnosis or a named symptom is a condition. A vague self-assessment is not: "I feel
  like I have some permanent damage done to my nerves", "something is wrong with my gut", "I cannot
  use my brain as I did before" and "needing more naps" are no condition.
- A mood or state word is a symptom under its everyday name: "i'm also getting depressed" is symptom
  `"depression"`, "I am sensitive to magnesium" is symptom `"magnesium sensitivity"`, as written.
- Spelling is not a disagreement: "PEM" and "post-exertional malaise" are one condition, merged by
  `canonical_condition` when labels are scored or compared.

## Hard cases

| Text | Label |
| --- | --- |
| "I'm 41 but feel 90" | age `"41"`, others age `["90"]` |
| "I'm over 60" / "almost 20" | all null, others age `["over 60"]` / `["almost 20"]` |
| "I'm in my late 30s" | age `"late 30s"` |
| "As a mom of two" | sex `"mom"` |
| "I'm nonbinary (afab)" | sex `"nonbinary | afab"` |
| "my husband is 40" | all null, others age `["40"]` (no sex: it isn't written as a value) |
| "I'm Canadian" / "I'm from Ohio originally" | all null, others country `["Canada"]` / state `["Ohio"]` |
| "I'm British, living in Spain" | country `"Spain"`, others country `["United Kingdom"]` |
| "my GP here in Leeds" | city `"Leeds"` |
| "Boy, 20 years old" (author introducing themselves) | age `"20"`, sex `"boy"` |
| "I'm 34 yo female (31 when I got sick)" | age `"34"`, sex `"female"`, others age `["31"]` |
| "About 25 it was very mild then but now its harder. Im 30 now." | age `"30"`, others age `["25"]` |
| "my daughter (14F) and I both have it" | all null, others age `["14"]`, sex `["F"]` |
| "I live in a developed country (slovenia)" | country `"slovenia"` |
| "the Red Cross here in the US" | country `"US"` |
| "I'm still here in 20 years" | all null |
| A quoted or pasted text written by someone else | label only the author's own words |

When a case isn't covered, decide, write the reason in `notes`, and add the rule to this file so the
next labeler decides the same way.

**Excluded items.** An item too ambiguous for two careful readers to agree on is excluded, not
guessed: `manifest.json`'s `excluded` list holds its `post_id`, the reason and who decided. `load`
drops excluded items everywhere (evaluate, stats, authors' posts) and `stats` counts them. Their
labels stay in `testset.jsonl` untouched.

## Expected profiles

For each author in `authors.jsonl`, label each of their `post_ids` as above, then write the profile
the merged resolve rules (`src/resolve_demographics.py`) should produce from those posts alone:

```json
{"age": 37.5, "age_bucket": "30s", "sex": "female", "sex_stated": "female",
 "location": "United States / Texas", "city": null, "ever_minor": 0}
```

- **age**: the most recent stated age, not advanced to today; a range or decade is its midpoint
  ("late 30s" is 37.5, "30s" is 35), except that a newer range or decade doesn't replace an exact
  age in the same decade ("34", then "30s", stays 34). `age_bucket` is its decade (`"30s"`).
- **ever_minor**: 1 when any age claim is under 18, counting a range or decade by its youngest age
  ("16-20" is 1); 0 when none is; null without an age. Leave it out to skip scoring it.
- **sex_stated**: the most recent sex claim as written; **sex**: female, male or non-binary from it
  (non-binary wins over a binary value; a trans answer is null; null when no rule applies).
- **location**: `"country / state"`, one spelling per country and US state (`US`, `USA` and `United States` are one country): the latest country, plus the latest state from a post that names
  that country or no country, the latter tied to the nearest country named before it. Either alone
  when only one is known.
- **city**: the latest city, cleared when a later post names a different country or state.

`evaluate` compares these with the profile resolved from the labels (does the code follow the
rules?) and from the model's claims (end to end).

The report's top-level `posts`, `fields` and `conditions` pool the sampled items in the split
(random, keyword, other_person, author); curated and synthetic items are left out, so adding hard
cases doesn't move the headline numbers. `by_stratum` repeats them for each stratum alone: read
recall from `random`, which is drawn uniformly, and wrong-person errors from `other_person`.
`by_case` does the same for each curated or synthetic case. An item in two strata or cases counts in
both. `conditions` gives precision and recall over condition names, matched through
`canonical_condition`, and `severity_agreement`, the share of matched names whose severity agrees.

## Curated and synthetic items

The `curated` stratum holds hand-picked real posts for the cases in
`src/demographics_testset_cases.json`: trans and non-binary answers, bounds, past ages, demonyms,
bare states, minors, conditions that resolve or return, and others. Each case has a regex, which
only finds candidates, and a quota, 60% dev and 40% test by `split_of`, so an author never sits in
both splits:

```bash
uv run python src/demographics_testset.py curate --db reddit_2026-06-13.db --testset data/demographics_testset
# pick from data/demographics_testset/candidates/<case>.jsonl into curation.jsonl:
#   {"post_id", "case", "rationale", "picked_by"}, one line per pick
uv run python src/demographics_testset.py add-curated --testset data/demographics_testset
```

`curate` writes, per case and split, three times the quota of matching items not already in the set,
in seeded order; `add-curated` appends the picks unlabeled, with `strata: ["curated"]` and their
cases under `case`, and records the selection in `manifest.json` under `curated`. The rationale stays
in `curation.jsonl`: the labeler sees only the text, so the reason for a pick can't steer its label.
Every curated label is reviewed by a person before it counts.

`tests/fixtures/demographics_synthetic.jsonl` holds the `synthetic` stratum: about 20 short posts
written to the rules above, one per hard case, with no patient text, so it lives in Git. `evaluate`
always includes them, whatever `--split` says: they are rule regressions, not a sample, and they are
left out of the pooled metrics, so including them in both splits leaks nothing into test scores.
The evaluator matches spellings of one identity ("MtF" and "trans woman", "FtM" and "trans masc",
"afab" and "assigned female at birth"); bare "trans" matches only itself. `sex_normalized` uses the
pipeline's `normalize_sex`, which gives no value for a trans answer (#214), so on the gender identity
case read `sex`, not `sex_normalized`.

## Evaluating a candidate prompt

`evaluate --prompt-file candidate.txt` sends the file's text as the prompt, exactly as written, with
the post appended. It must be the rendered prompt, not the template in
`src/prompts/demographic_prompt.py`: that is an f-string, so a copy of its source has doubled braces
(`{{"value": ...}}`) and a literal `{DEMOGRAPHIC_AGE_RULES}`. Start from the rendered text:

```bash
cd src && uv run python -c "from prompts.demographic_prompt import POST_DEMOGRAPHICS_PROMPT as p; print(p, end='')" > ../candidate.txt
```

## Reading a report

- **Which labels.** Labels change with each review, so the plan and report carry `testset_sha256`
  (of `testset.jsonl`, `authors.jsonl` and the synthetic fixture) and `labels_by`, the count of items
  per labeler. Compare two reports only when their `testset_sha256` agree.
- **Uncertainty.** Every precision and recall has its denominator (`precision_n`, `recall_n`) and a
  Wilson 95% interval (`precision_ci`, `recall_ci`). Most cases have 5 to 30 items and state and city
  have few labels, so read the interval before the point value.
- **Positives and near misses.** Each curated case mixes items that state the targeted field
  (`positives`) with near misses that don't. `stats` reports the mix per case and split under
  `case_mix`, and `by_case` reports it under `mix`. Near misses can only add false positives, so a
  case's recall comes from its positives alone.
- **The test split is for final comparisons only.** Tune prompts (#208) on `dev`. Every evaluation
  of `--split test` or `all` (not a dry run) appends its tag, time, prompt hash, model, commit and
  `testset_sha256` to `test_runs.jsonl`, so the number of looks at the test split is on record.

## Label noise

Every label outside the curated stratum is one model's draft (gpt-6.2-sol). Two second labelings by
Claude Opus 5.5 (Claude Code on the subscription), each blind to the first label, measure the noise.
The first covers a seeded, stratified 10% of the random and keyword items, all fields (44: random 13
dev / 7 test, keyword 14 / 10). The second covers conditions on all 225 items labeled for them.
`agree` compares them per field: `agree` (both empty, or the same answer by `key()`; conditions as
sets of `canonical_condition` names) with its Wilson interval, and Cohen's kappa on whether the
field is stated. A field the second labeling didn't cover isn't compared.

```bash
uv run python src/demographics_testset.py agree --testset data/demographics_testset \
  --second data/demographics_testset/labeling/second_conditions/second_labels.jsonl
```

| field | n | agree (95% CI) | kappa, stated |
| --- | --- | --- | --- |
| age | 44 | 1.00 (0.92-1.00) | 1.00 |
| sex | 44 | 1.00 (0.92-1.00) | 1.00 |
| country | 44 | 1.00 (0.92-1.00) | 1.00 |
| state | 44 | 1.00 (0.92-1.00) | 1.00 |
| city | 44 | 0.98 (0.88-1.00) | 1.00 |
| conditions | 225 | 0.83 (0.77-0.87) | 0.96 |

Conditions were compared with #229's `canonical_condition`. The disagreements are in
`review/second_label_disagreements_<folder>.md`.

## Content-filter blocks

A post the provider's content filter blocks is recorded with no claims. `evaluate` counts blocks
under `posts.blocked` and scores them as empty, so the loss shows in recall.

## Known gaps

- **Conditions labels are noisy.** Agreement on the set of condition names is 0.83 (95% CI
  0.77-0.87) over 225 items; whether any condition is stated agrees almost always (kappa 0.96). Of
  the 39 disagreements, about 15 are wordings of one symptom that `canonical_condition` doesn't
  merge ("headache" / "headaches", "crash" / "crashes", "sleep disturbance" / "trouble sleeping",
  "muscle cramps" / "cramping"). The rest are coverage: one labeler lists a symptom the other
  leaves out (difficulty concentrating, suicidal ideation, bedbound, a missed ME/CFS). Both kinds
  depress condition recall and precision measured against these labels; read condition metrics as
  approximate.
- **Location agreement says little.** The 44 doubly labeled items state country, state and city
  once each, so their kappa rests on one positive. Location noise is unmeasured outside the curated
  items, which a person reviews.
- **Sampled labels are single drafts.** Only the curated labels get a person's review; the rest are
  one model's draft, checked by the 10% second label above.
- **`sex_normalized` is blind to trans answers**, by the pipeline's design (#214); read `sex` for
  the gender identity case.
