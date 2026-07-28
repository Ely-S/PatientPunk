# extraction_quality

Sub-project for tuning the LLM extraction step (`patientpunk.llm_extract`): prompt
wording, model choice, and model config (temperature, service tier, etc.). It exists
because "the aggregate stats look fine" and "the extraction is actually correct" are
different claims -- see the spot-check in PR #92, which found real per-field failure
modes (misattributed claims, inferred severity/diagnosis language) that the run-level
stats didn't surface.

## What's here

- `fixtures/spotcheck_20.json` -- a fixed set of 20 real Reddit posts with a `gold`
  label per field, used as a regression/comparison set across prompt and model
  changes.
- `eval_prompt_fixtures.py` -- runs the *live* extraction prompt/model against the
  fixture set and scores the result against `gold`.
- `results/` -- one JSON file per run (`<timestamp>__<label>.json`): per-field
  precision/recall/f1 plus every mismatch, so a `TRACKER.md` row can point back to
  exact evidence instead of a remembered number.
- `TRACKER.md` -- the experiment log: what changed, what score it got, what to try
  next.

## The gold labels are not full gold labels -- read this before trusting a score

`gold` in the fixture started as the *baseline* extraction (deepseek-v4-flash, 10k-post
run) and was corrected only where a Haiku-subagent spot-check flagged a specific field
as wrong against the source text (7 of 20 records touched -- see each record's
`baseline_extracted` vs `gold` and the generation notes in git history for the
per-record reasoning). It was never audited field-by-field for *omissions*.

Practically: when a run reports a mismatch, the harness labels it one of:

- **MISS** -- gold has a value the candidate didn't produce. Likely a real
  regression.
- **DIFF** -- both sides have a value and disagree. Read the source text; either
  side could be right.
- **EXTRA** -- gold is empty but the candidate found something. This is *not*
  necessarily wrong -- the baseline run under-extracted plenty of fields that are
  genuinely present in the text (see `t3_nma566`'s medications/dosage in an early
  harness run, which the baseline simply never extracted). Verify against the post
  text before writing it off as a hallucination.

Trend the **macro scores across runs** (is precision/recall moving the right
direction as you change the prompt) more than any single run's absolute numbers --
the fixture wasn't built with the labor budget for a from-scratch human gold set.
If a particular field matters enough to justify one, promote it: hand-label that
field across all 20 records from the source text and note the change in
`TRACKER.md`.

## Running an eval

```bash
cd variable_extraction
uv run python extraction_quality/eval_prompt_fixtures.py --label baseline
```

Useful variations:

```bash
# Test an extension schema
uv run python extraction_quality/eval_prompt_fixtures.py --schema schemas/covidlonghaulers_schema.json --label covidlonghaulers

# Test the opt-in group-attribution guard
uv run python extraction_quality/eval_prompt_fixtures.py --group-guard --label group-guard-on

# Test a different model/provider (same env vars as a real run -- see patientpunk/_utils.py)
MODEL_FAST=deepseek/deepseek-v3.2 uv run python extraction_quality/eval_prompt_fixtures.py --label deepseek-v3.2

# Quick single-record smoke test while iterating
uv run python extraction_quality/eval_prompt_fixtures.py --limit 1 --verbose --label smoke
```

To test a **prompt** change: edit `build_system_prompt` (or the field description
dicts) in `../patientpunk/llm_extract.py` directly, then rerun. There's one live
prompt, not forked copies of it per experiment -- `--label` plus the saved JSON is
what distinguishes runs, not a duplicated prompt file.

After a run, add a row to `TRACKER.md` with the label, what changed, the macro
scores, and a link to the saved `results/*.json`.

## Extending the fixture set

`fixtures/spotcheck_20.json` records: `post_id`, `text` (raw source text, as fed to
the model), `baseline_extracted` (what the original run produced), `gold` (corrected
truth per the caveats above). Add records the same shape if you find a new tricky
case worth locking in as a regression test -- especially anything from the failure
modes PR #92 identified: attributing a claim the poster is *discussing* (a theory,
someone else's experience) to the poster themselves, or inferring outcome/severity
language beyond what's stated.
