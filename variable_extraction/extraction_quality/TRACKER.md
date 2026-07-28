# Extraction quality tracker

Log of prompt/model/config experiments run against the fixture set via
`eval_prompt_fixtures.py`. One row per run. Read `README.md`'s gold-label
caveats before reading scores as absolute rather than relative.

`macro_f1` / `macro_agreement` are the mean of `f1` / `agreement_present` across
all fields with any gold or candidate data in that run -- a quick single number
per run, not a substitute for reading the mismatches in the linked results file.

| Date | Label | Model | Prompt/config change | macro_f1 | macro_agreement | MISS / DIFF / EXTRA | Results file |
|------|-------|-------|----------------------|----------|------------------|----------------------|--------------|
| 2026-07-27 | baseline | deepseek/deepseek-v4-flash | Prompt as of project creation -- first tracked run | 0.540 | 0.423 | 5 / 26 / 40 | `results/20260728T032402Z__baseline.json` |
| 2026-07-27 | baseline-normalized | deepseek/deepseek-v4-flash | No prompt change -- scored candidate output through `normalize_records` | 0.556 | 0.440 | 5 / 20 / 42 | `results/20260728T032729Z__baseline-normalized.json` |

### ⚠️ Fixture v2 divider -- the two rows above are void

Both rows above were measured against **input the gold labels were never derived
from**, so their numbers mean nothing and no conclusion drawn from them survives.
See "The fixture-text defect" below. Compare all future runs to `baseline-v2`.

| Date | Label | Model | Prompt/config change | macro_f1 | macro_agreement | MISS / DIFF / EXTRA | Results file |
|------|-------|-------|----------------------|----------|------------------|----------------------|--------------|
| 2026-07-27 | baseline-v2 | deepseek/deepseek-v4-flash | **Fixture v2**: `texts` rebuilt to the production title+body segments; eval now defaults to the fixture's own schema (21 fields scored, was 15). No prompt change. | 0.878 | 0.809 | 2 / 8 / 12 | `results/20260728T034411Z__baseline-v2.json` |

## The fixture-text defect (fixed 2026-07-27)

The fixture's `text` held **title + body + every comment**, but the production
pipeline extracts from title+body only (`patientpunk/corpus.py` `_texts_from_post`,
`include_comments=False` -- comments are other users' words and must not be
attributed to the post author). `baseline_extracted` and `gold` came from a real
title+body-only run, so the harness was scoring the model on text three to eight
times longer than the text the labels describe:

| post | old fixture `text` | production title+body |
|---|---|---|
| `t3_nma566` | 2829 chars | 479 |
| `t3_tc5p1a` | 4000 (truncated) | 649 |
| `t3_d0jyeu` | 2572 | 162 |

Fixing it moved macro_f1 0.556 -> 0.878 and mismatches 67 -> 22, with EXTRA
falling 42 -> 12 -- the candidate had been extracting other commenters' drugs
and outcomes that gold could not contain because the labeling run never saw them.

**What this retracts:** the previous "Next up" item calling for a
multi-speaker/thread attribution rule, and the `t3_tc5p1a` over-attribution
finding it rested on. That was an artifact of fixture construction. Production
never feeds the model a multi-commenter thread, so a prompt rule for it would
have been tuning against a problem that does not exist. (Genuine multi-speaker
text can still appear *inside* a single post body, e.g. a pasted conversation --
but that is rare and was not what the finding measured.)

Records now carry `texts` (the segment list) rather than a pre-joined `text`,
because production calls `build_user_message([title, body])`, which joins with
`\n\n---\n\n`. A `tests/` assertion pins this so the drift cannot return.

## Reading baseline-v2

22 mismatches over 21 fields. The weakest fields are `prior_infections`
(f1 0.400), `functional_status_tier` (0.727), `social_impact` (0.769) and
`conditions` (0.800). Several mismatches are visibly *not* prompt problems --
`covid` vs `covid-19` and `postcovid` vs `long covid` are vocabulary variants for
`normalize.py`, not the model. Stage 2 (`triage.py`) exists to split those out by
count before any prompt is edited.

## Where this is at (2026-07-27)

The harness and the loop around it are built; **no prompt change has been
evaluated yet**, deliberately -- the pre-existing scores were measured against
the wrong input, and editing the prompt before fixing that would have been tuning
on noise.

Done:

- **Fixture text fixed** and pinned by `tests/test_extraction_quality_fixture.py`.
  `baseline-v2` above is the number to beat.
- **`build_fixture.py`** -- deterministic (`--seed 42`) stratified sampler.
  `fixtures/eval_50.json` exists: the 20 original records plus 30 new, stratified
  by extraction density (12 high / 10 medium / 5 low / 3 empty, where "empty"
  means the production run extracted nothing -- the only way to measure false
  positives on posts with nothing to find). Subreddit share is capped at 50% per
  stratum, giving 22 covidlonghaulers / 19 cfs / 8 LongCovid / 1
  LongHaulersRecovery instead of the corpus's 55% covidlonghaulers.
- **`label_fixture.py`** -- two-model adjudication. Labels each new record with
  `anthropic/claude-opus-5`, compares against the production deepseek run's
  labels for the same post, and promotes only the cells where both models agree
  (after `normalize_records`) to gold, tagged `gold_source: "agreed"`.
  Disagreements go to a `fixtures/review_*.json` file for a human pass and come
  back via `--apply` as `gold_source: "adjudicated"`.
- **`triage.py`** -- classifies every mismatch into the failure taxonomy (see
  README) and prints a field x code matrix, so the next prompt edit is chosen by
  count rather than by anecdote. `--propose-gold-fixes` emits gold corrections as
  a review file rather than applying them, because a model that can silently
  rewrite its own answer key is not being measured.
- **`compare.py`** -- run-vs-run per-field deltas plus the named cells fixed and
  newly broken. A macro-f1 gain that breaks a field is a regression, and the
  macro number alone hides it.
- **`--prompt-variant`** -- `build_system_prompt(..., extra_rules=...)` plus
  `prompts/<name>.md` overlays, generalizing the mechanism `group_guard` already
  used. An experiment is now a file and a flag, not an edit to the working tree;
  runs record `prompt_sha` and the variant names.

In flight -- **`eval_50.json` is not ready to score against yet**:

The labeling pass over the 30 new records is done. `claude-opus-5` and the
production `deepseek-v4-flash` run agreed on **102 cells** (now gold,
`gold_source: "agreed"`) and disagreed on **146**, written to
`fixtures/review_20260728T035253Z.json` awaiting adjudication. Those 146 fields
currently have no gold, so scoring the 50-record set now would read them as MISS
and manufacture a fake regression. Use `baseline-v2` on the 20-record set until
the review is applied.

The disagreement split says something useful on its own, before any of it is
resolved:

| shape | n | what it usually is |
|---|---|---|
| both models produced values, different | 62 | granularity and format (`covid` vs `covid-19`, `blood test` vs `blood tests`, `2-4 mg` vs `2-4 mg nicotine gum`) |
| opus only | 50 | production model under-extracting -- recall gap |
| production only | 34 | opus declining to infer where production inferred (`functional_status_tier`, `infection_count: 1` from a single mentioned infection) |

Top disagreement fields: `prior_infections` (14), `symptom_duration` (12),
`conditions` / `treatment_outcome` / `social_impact` / `mental_health` (11 each).
`prior_infections` topping the list is mostly `covid` vs `covid-19` vs empty --
a normalization question, not a prompt one.

Adjudication needs the full post text per cell and real judgment; it is the one
step in this pipeline that cannot be automated without letting a model grade its
own work. Budget it as its own pass.

## Next up

1. **Adjudicate the 146 disagreements** in `fixtures/review_20260728T035253Z.json`
   (fill `resolved`), then `label_fixture.py --apply`. Two decisions to settle
   *before* starting, and to write down here, because inconsistency across 146
   cells is worse than either choice:
   - `dosage`: bare dose (`2-4 mg`) or dose+drug (`2-4 mg nicotine gum`)? The
     field description says "retain the number and unit"; `medications` already
     holds the drug name.
   - `functional_status_tier`: does it require the author to state their function
     level, or may it be read off described capacity? Production infers it freely
     (that is most of the 34 production-only cells); opus almost never does.
2. Re-run the baseline on the full 50 (`--label baseline-50`) and treat that as
   the new reference row. `baseline-v2` stays as the 20-record reference.
3. Measure the noise floor: two `--no-cache` runs of the same config. Record the
   macro-f1 spread here. **Deltas below it are not results** -- without this
   number every subsequent row is unfalsifiable.
4. `triage.py` on the 50-record baseline; let the field x code matrix pick the
   first variant. Route `vocab_variant` / `granularity` counts to
   `patientpunk/normalize.py` and `gold_wrong` back into the fixture -- neither is
   a prompt problem, and spending a prompt round on them is exactly the mistake
   the `me/cfs` DIFFs already cost once.
5. Write the top-count variant into `prompts/`, run, `compare.py` against the
   baseline, add a row here. Repeat until the top code stops moving.
6. Only once the prompt is stable: compare cheaper/faster models at fixed prompt.

Prompt candidates carried forward from the baseline-v2 mismatches, to be
confirmed or dropped by the triage matrix rather than assumed:

- `treatment_outcome`: don't infer "helped" when the author still reports the
  symptom (`t3_vkkcui`).
- `conditions`/`mental_health`: "the author is discussing X" vs "has X"
  (`t3_lmu7ty`, `t3_sa85zi` -- candidate adds depression/anxiety to conditions).
- `functional_status_tier`/`social_impact`: require near-verbatim support
  (`t3_156wgqv`, `t3_6ygbyh`).
