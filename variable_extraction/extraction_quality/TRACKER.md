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

## Next up

- Grow the fixture to 50 records (`build_fixture.py` + `label_fixture.py`).
- Run `triage.py` on `baseline-v2` and let the field x code matrix pick the first
  prompt variant, rather than guessing from anecdotes.
- Measure the noise floor: two `--no-cache` baseline-v2 runs. Deltas below that
  spread are not results.
- Candidates carried forward, to be confirmed or dropped by the triage matrix:
  - `treatment_outcome`: don't infer "helped" when the author still reports the
    symptom (`t3_vkkcui`).
  - `conditions`/`mental_health`: "the author is discussing X" vs "has X"
    (`t3_lmu7ty`, `t3_sa85zi` -- candidate adds depression/anxiety to conditions).
  - `functional_status_tier`/`social_impact`: require near-verbatim support
    (`t3_156wgqv`, `t3_6ygbyh`).
- Once the prompt is stable, compare cheaper/faster models at fixed prompt.
