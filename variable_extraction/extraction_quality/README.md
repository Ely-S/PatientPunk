# extraction_quality

Sub-project for tuning the LLM extraction step (`patientpunk.llm_extract`): prompt
wording, model choice, and model config. It exists because "the aggregate stats look
fine" and "the extraction is actually correct" are different claims -- see the
spot-check in PR #92, which found real per-field failure modes the run-level stats
never surfaced.

It also exists because measuring extraction quality is easy to get subtly wrong. Two
defects found here so far were in the *measurement*, not the model:

- the fixture fed the model title+body+comments while its labels came from a
  title+body-only run (macro_f1 was reading 0.556 when it was actually 0.878);
- the eval scored 15 fields while the labels covered 21.

Both are recorded in `TRACKER.md`. The habits below exist to keep that class of
error from recurring.

## What's here

| file | role |
|---|---|
| `fixtures/eval_50.json` | the evaluation set: 50 real posts, `texts` + `gold` per record |
| `build_fixture.py` | deterministic stratified sampler that builds the fixture (no API calls) |
| `label_fixture.py` | produces `gold` by two-model adjudication; folds reviewed cells back in |
| `eval_prompt_fixtures.py` | runs the live prompt/model against the fixture and scores it |
| `triage.py` | classifies a run's mismatches into a failure taxonomy |
| `compare.py` | diffs two runs: per-field deltas + which cells were fixed/broken |
| `prompts/*.md` | additive rule overlays -- one file per prompt experiment |
| `review/` | labeling worksheets awaiting human adjudication (kept out of `fixtures/`) |
| `results/` | one JSON per run, so a `TRACKER.md` row points to evidence, not a memory |
| `TRACKER.md` | the experiment log: what changed, what it scored, what to try next |

## The one invariant: `texts` is what production sends

Each record stores `texts` -- the post's title/body segments exactly as
`collect_texts_from_post(post, include_comments=False)` returns them. Feed them to
`build_user_message(texts)`. Never pre-join them (production joins with
`\n\n---\n\n`, not `\n\n`), and never include comments: comments are other users'
words, the pipeline excludes them, and the labels were produced without them.

The earlier fixture broke this and made the model look like it was hallucinating
30 values it had simply read out of other people's comments -- which in turn
produced a confident, wrong conclusion that the prompt needed a multi-speaker
attribution rule. `tests/test_extraction_quality_fixture.py` now pins it.

## How `gold` is produced, and what it is not

Hand-labeling 21 fields across 50 records from source text is the gold standard and
was not affordable. `gold` here is a **silver standard** built three ways, recorded
per field in `gold_source`:

| `gold_source` | how that cell was established |
|---|---|
| `spotcheck` | the original 20 records: a production run's output, corrected where a human+Haiku spot-check found it wrong (7 of 20 records touched) |
| `agreed` | `claude-opus-5` and the production `deepseek-v4-flash` independently produced the same value set |
| `adjudicated` | the two disagreed and a human resolved it against the post text |

Two independent models agreeing is weak evidence, but it is *independent* evidence,
and it concentrates human effort on the cells where they differ. What it cannot
catch is **a value both models missed**. So:

> Recall against omissions is the weakest axis of any score computed from this
> fixture. A high recall number here means "few of the values the labels contain
> were dropped", not "few of the values in the text were dropped."

Trend macro scores **across runs** rather than reading any single run's absolute
number. If one field matters enough to justify it, promote it: hand-label that field
across all 50 records from the source text, set its `gold_source` accordingly, and
note it in `TRACKER.md`.

## The loop

### 1. Run

```bash
cd variable_extraction
uv run python extraction_quality/eval_prompt_fixtures.py --label baseline-50
```

Schema comes from the fixture's own metadata, so every field the labels cover gets
scored. Useful variations:

```bash
# a prompt experiment: an overlay file, not an edit to llm_extract.py
uv run python extraction_quality/eval_prompt_fixtures.py --prompt-variant conditions-strict --label conditions-strict

# a different model -- same env vars as a real run (see patientpunk/_utils.py)
MODEL_FAST=deepseek/deepseek-v3.2 uv run python extraction_quality/eval_prompt_fixtures.py --label deepseek-v3.2

# noise floor: same config twice, cache bypassed
uv run python extraction_quality/eval_prompt_fixtures.py --no-cache --label noise-a

# quick smoke while iterating
uv run python extraction_quality/eval_prompt_fixtures.py --limit 2 --verbose --label smoke
```

Each run saves `results/<timestamp>__<label>.json` including the **full system
prompt and its sha** -- a saved run used to be unreproducible because the prompt
lived only in the working tree.

**Establish the noise floor before believing any delta.** Two `--no-cache` runs of
the same config differ by some amount; anything smaller than that is not a result.

### 2. Triage

```bash
uv run python extraction_quality/triage.py results/<run>.json
```

A results file says *that* 22 cells disagreed. It cannot say why. `triage.py` shows
each mismatch to a judge model with the source text and assigns one code:

| code | meaning | fix belongs in |
|---|---|---|
| `omission` | in the text and in gold, candidate missed it | prompt / model |
| `hallucination` | no basis in the text at all | prompt |
| `inference` | reasonable reading, not explicitly stated | prompt |
| `over_attribution` | the text ascribes it to someone else | prompt |
| `field_bleed` | right value, wrong field | prompt |
| `format_violation` | >5 words, bad `drug: outcome: symptom`, non-enum tier | prompt |
| `vocab_variant` | same meaning, different words | `normalize.py` `_CANONICAL_MAPS` |
| `granularity` | same fact, different precision or unit | `normalize.py` / scorer |
| `gold_wrong` | the candidate is right and the label is not | the fixture |
| `unclear` | the text supports neither side | nowhere |

Four of these are deliberately **not prompt problems**. Editing the prompt to chase
a `vocab_variant` count is how a normalization gap gets mistaken for a model
failure -- which already happened once here.

`--propose-gold-fixes` writes `gold_wrong` cells to a review file instead of
applying them. Read them before accepting: a model that can silently rewrite its
own answer key is not being measured.

### 3. Change one thing

Write `prompts/<name>.md` containing the additional rule, in the same voice as the
existing `FIELD-SPECIFIC RULES` block. Headings (`#` lines) are stripped; everything
else is appended to the system prompt. Then run with `--prompt-variant <name>`.

Variants are additive and independently toggleable, so two experiments are two runs
rather than two working trees. When one wins, fold it into `build_system_prompt` in
`../patientpunk/llm_extract.py` and delete the overlay.

### 4. Compare

```bash
uv run python extraction_quality/compare.py results/<baseline>.json results/<candidate>.json
```

Prints per-field precision/recall/f1 deltas and names the cells fixed, newly broken,
and still-wrong-differently. A rule that fixes `conditions` while breaking
`medications` shows up as a small macro gain; this is what catches it.

Then add a row to `TRACKER.md`: label, what changed, macro scores, the top triage
codes, and the results path.

## Extending the fixture

```bash
uv run python extraction_quality/build_fixture.py --seed 42 --n 30 --out fixtures/eval_50.json
uv run python extraction_quality/label_fixture.py --fixture fixtures/eval_50.json
# review review/review_<ts>.json, filling in `resolved`
uv run python extraction_quality/label_fixture.py --fixture fixtures/eval_50.json --apply review/review_<ts>.json
```

Sampling is stratified by extraction density rather than uniform: 41% of the corpus
extracts to a completely empty row, so a uniform sample would spend most of the
labeling budget on records that score trivially and measure nothing. The `empty`
stratum is kept deliberately -- it is the only way to measure false positives on
posts with nothing to find.

Add hand-written records in the same shape if you find a case worth locking in as a
regression test, especially the PR #92 failure modes: attributing a claim the poster
is *discussing* to the poster themselves, or inferring outcome/severity language
beyond what is stated.
