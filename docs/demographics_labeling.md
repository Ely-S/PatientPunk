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

**age.** The author's own current age at the time of writing. Write it as stated: `"26"`,
`"30s"`, `"late 30s"`, `"25-34"`. Empty for: past ages ("when I was 22", "31 when I got sick": both go
in `others`), other people ("my 11yo son", "my wife is 36": `others`), news subjects, weights and
durations ("I'm 25 lb underweight", "15 years in"), and ages implied but not stated (school year,
birth year, "I'm a grandmother"). "I'm 18 (19 on the 19th)" is `"18"`. "57m" or "(31F)" posted as the
author's description of themselves is the age.

**sex.** The author's sex or gender in their own words: `"female"`, `"male"`, `"trans man"`,
`"non-binary"`. Give one word per identity: `|` separates distinct identities the author states
(`"non-binary | female"`), never two words for the same one ("26F single mom" is `"F"`, quoting `26F`).
Write the words as stated (#214 is still open; the evaluation scores both the words and the
normalized value). The `F`/`M` in "31F", "male", "woman", "guy", "mom", "boy" count when they describe
the author. The evaluation scores mom, guy, lady and similar words as the sex they mean, by the
pipeline's own rule (`normalize_sex` in `src/resolve_demographics.py`, the one list of these words).
Empty for pronouns, usernames, writing style, and what others call the author.

**country, state.** Where the author lives, one place each. "45 male here in Tennessee" is state
`"Tennessee"` with country empty: label only what is named, never what it implies. Abbreviations are
fine (`"TX"`, `"UK"`); the evaluation treats them as the full name, as the pipeline stores them
(`canonical_place` in `src/resolve_demographics.py`). Empty for places they visited,
were treated in, or are comparing ("doctors in Germany prescribe..."), and for unnamed places ("a
third world country"). Two places they live between ("I split time between Ohio and Florida") is
empty, as the extractor refuses two places.

**city.** The city or town where the author lives, not one they travelled to or were treated in
("saw a specialist in Boston" is `others`). A region after a comma stays with it (`"Austin, TX"`).

## Hard cases

| Text | Label |
| --- | --- |
| "I'm 41 but feel 90" | age `"41"` |
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

## Expected profiles

For each author in `authors.jsonl`, label each of their `post_ids` as above, then write the profile
the merged resolve rules (`src/resolve_demographics.py`) should produce from those posts alone:

```json
{"age": 37.5, "age_bucket": "30s", "sex": "female", "sex_stated": "female",
 "location": "US / Texas", "city": null}
```

- **age**: the most recent stated age, not advanced to today; a range or decade is its midpoint
  ("late 30s" is 37.5, "30s" is 35). `age_bucket` is its decade (`"30s"`).
- **sex_stated**: the most recent sex claim as written; **sex**: female, male or non-binary from it
  (non-binary wins over a binary value; a trans answer is null; null when no rule applies).
- **location**: `"country / state"`, one spelling per country and US state (`US`, `USA` and `United States` are one country): the latest country, plus the latest state from a post that names
  that country or no country, the latter tied to the nearest country named before it. Either alone
  when only one is known.
- **city**: the latest city, cleared when a later post names a different country or state.

`evaluate` compares these with the profile resolved from the labels (does the code follow the
rules?) and from the model's claims (end to end).

## Content-filter blocks

A post the provider's content filter blocks is recorded with no claims. `evaluate` counts blocks
under `posts.blocked` and scores them as empty, so the loss shows in recall.
