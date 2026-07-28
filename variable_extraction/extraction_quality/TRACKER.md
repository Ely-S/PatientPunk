# Extraction quality tracker

Log of prompt/model/config experiments run against `fixtures/spotcheck_20.json`
via `eval_prompt_fixtures.py`. One row per run. Read `README.md`'s gold-label
caveats before reading scores as absolute rather than relative.

`macro_f1` / `macro_agreement` below are the mean of `f1` / `agreement_present`
across all fields with any gold or candidate data in that run (matches
`evaluate.score_extraction`'s `overall` block) -- a quick single number per run,
not a substitute for reading the mismatches in the linked results file.

| Date | Label | Model | Prompt/config change | macro_f1 | macro_agreement | MISS / DIFF / EXTRA | Results file |
|------|-------|-------|----------------------|----------|------------------|----------------------|--------------|
| 2026-07-27 | baseline | deepseek/deepseek-v4-flash | Prompt as of commit at project creation -- first tracked run, no change yet | 0.540 | 0.423 | 5 / 26 / 40 | `results/20260728T032402Z__baseline.json` |
| 2026-07-27 | baseline-normalized | deepseek/deepseek-v4-flash | No prompt change -- fixed `eval_prompt_fixtures.py` to run candidate output through `normalize_records` (lowercase/dedupe/`_CANONICAL_MAPS`) before scoring, same as a real run. This is the true baseline; the row above scored raw un-normalized model text. | 0.556 | 0.440 | 5 / 20 / 42 | `results/20260728T032729Z__baseline-normalized.json` |

## Reading the baseline run

40 of 71 mismatches are EXTRA (candidate found a value gold doesn't have) vs. only
5 MISS -- consistent with the README's caveat that `gold` is the *baseline*
extraction, which itself under-extracted plenty of real fields (e.g. `t3_tc5p1a`,
`t3_15e9j7b`, `t3_d0jyeu` all have long medication/treatment_outcome lists the
original run simply didn't produce). Two things worth acting on surfaced in the
DIFF/MISS rows specifically, not just from EXTRA noise:

- **CONFIRMED (read the source text)**: `t3_tc5p1a` is a concatenated multi-commenter
  GI thread -- the original poster only says they take baking soda, milk of magnesia,
  and "just started a probiotic." Every other drug the candidate extracted
  (colestyramine, Colestipol, Welchol, klonopin, PPI, famotidine, Pepcid, digestive
  enzymes, Yakult Probiotics, ...) is a *different commenter* describing their own
  regimen ("What worked for me was...", "try ... colestyramine, Colestipol, or
  Welchol", "Could also try famotidine instead"). Candidate is over-attributing --
  this is the PR #92 author-vs-others failure mode, confirmed in the
  over-attribution direction. Prompt rule 3 ("AUTHOR vs OTHERS") isn't enough when
  the text is a jumble of replies with no author markup; needs a stronger rule
  specific to multi-speaker/thread text (see Next up).
- **`t3_156wgqv` treatment_outcome MISS**: candidate dropped
  "stretching and massage: mixed: numbness" that gold (correctly, per the original
  spot-check) has. Check whether current prompt wording for `treatment_outcome`
  or `alternative_treatments` overlap is causing the model to file it under one
  and not the other, or to drop it entirely.
- **RESOLVED**: the `conditions` DIFF rows (`me/cfs` vs `chronic fatigue syndrome`/`CFS`)
  were a pure scoring artifact, not a normalization-map gap. `eval_prompt_fixtures.py`
  scored raw candidate output and never called `normalize_records`, so none of the
  lowercase/dedupe/`_CANONICAL_MAPS` canonicalization a real run applies was in effect.
  Fixed in `eval_prompt_fixtures.py::run_one` (wraps the parsed extraction in a fake
  record and runs it through `normalize_records` before scoring) -- see the
  `baseline-normalized` row above. This dropped DIFF count 26 -> 20 and is now the
  baseline to compare future prompt changes against, not the original `baseline` row.

## Next up

- Candidates worth testing first (from the PR #92 spot-check failure modes):
  - Tighten `treatment_outcome` guidance so the model doesn't infer "helped" from
    an author still reporting the symptom (`t3_vkkcui` in the fixture set).
  - Add a rule distinguishing "the author is discussing/theorizing about X" from
    "the author has X" for `conditions` / `mental_health` (`t3_lmu7ty`).
  - Tighten `functional_status_tier` / `social_impact` to require the tier or
    impact label be stated close to verbatim, not inferred from adjacent context
    (`t3_156wgqv`, `t3_15kwgjz`).
  - Add a rule for multi-speaker/thread text: when the text contains multiple
    distinct commenters (reply-style turns, "what worked for me", quoting another
    comment), only extract what the ORIGINAL POST author says about themselves;
    do not attribute a different commenter's treatment/outcome to the author
    (`t3_tc5p1a`, confirmed above -- candidate pulled in ~10 other commenters'
    medications).
- Consider a cheaper/faster model pass (e.g. current `MODEL_FAST` vs. a Haiku vs.
  DeepSeek comparison) once the prompt is stable, to see whether quality holds at
  lower cost.
