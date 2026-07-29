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
See "The fixture-text defect" below. Compare all future runs to `baseline-50`.

| Date | Label | Model | Prompt/config change | macro_f1 | macro_agreement | MISS / DIFF / EXTRA | Results file |
|------|-------|-------|----------------------|----------|------------------|----------------------|--------------|
| 2026-07-27 | baseline-v2 | deepseek/deepseek-v4-flash | **Fixture v2**: `texts` rebuilt to the production title+body segments; eval now defaults to the fixture's own schema (21 fields scored, was 15). No prompt change. | 0.878 | 0.809 | 2 / 8 / 12 | `results/20260728T034411Z__baseline-v2.json` |
| 2026-07-27 | baseline-50 | deepseek/deepseek-v4-flash | **Fixture: all 50 records**, 146 adjudicated cells folded in. No prompt change. | 0.739 | 0.620 | 37 / 50 / 46 | `results/20260728T040932Z__baseline-50.json` |
| 2026-07-27 | noise-a-50 | deepseek/deepseek-v4-flash | No prompt change; uncached, 50 concurrent workers. One JSON parse failure (`t3_ter21n`). | 0.682 | 0.534 | 54 / 65 / 31 | `results/20260728T052645Z__noise-a-50.json` |
| 2026-07-27 | noise-b-50 | deepseek/deepseek-v4-flash | No prompt change; uncached, 50 concurrent workers. | 0.662 | 0.501 | 53 / 66 / 47 | `results/20260728T052935Z__noise-b-50.json` |
| 2026-07-28 | no-unstated-defaults | deepseek/deepseek-v4-flash | **Rejected (replicated):** prompt overlay requiring an explicit functional tier or infection count. It suppressed too many supported `1` counts/tier values. | 0.655 | 0.502 | 63 / 60 / 23 | `results/20260728T055213Z__no-unstated-defaults.json` |
| 2026-07-28 | no-unstated-defaults-replicate | deepseek/deepseek-v4-flash | Same rejected overlay, independent uncached replicate. | 0.640 | 0.509 | 61 / 62 / 24 | `results/20260728T072857Z__no-unstated-defaults-replicate.json` |
| 2026-07-28 | baseline-covid-canon | deepseek/deepseek-v4-flash | `prior_infections` now canonicalizes `covid-19` to `covid`; uncached. Global comparison is within noise, but the deterministic alias fix is covered by test. | 0.651 | 0.502 | 50 / 64 / 49 | `results/20260728T094423Z__baseline-covid-canon.json` |
| 2026-07-28 | prior-infections-a | deepseek/deepseek-v4-flash | **Accepted (replicated):** `prior_infections` rule -- the onset infection still belongs in the field. Uncached. One JSON parse failure (`t3_kmnxog`). | 0.636 | 0.495 | 49 / 66 / 41 | `results/20260728T224320Z__prior-infections-a.json` |
| 2026-07-28 | prior-infections-b | deepseek/deepseek-v4-flash | Same rule, independent uncached replicate. Now folded into `build_system_prompt`; the overlay file is deleted. | 0.680 | 0.520 | 51 / 64 / 42 | `results/20260728T224455Z__prior-infections-b.json` |

`baseline-50` is **not** a regression from `baseline-v2`: it is a different, harder
fixture (50 records vs 20, with gold now present on cells the 20-record set left
blank -- an unlabeled cell scores as a free pass). The two rows are not
comparable in either direction. `baseline-50` is the reference row from here on;
`baseline-v2` stays only as the 20-record history.

## Noise floor (measured 2026-07-27)

Two uncached, otherwise identical 50-worker runs produced macro-f1 **0.682** and
**0.662** (spread **0.020**), and macro-agreement **0.534** and **0.501** (spread
**0.033**). The named-cell comparison is not small: 29 cells fixed, 45 newly
broken, and 38 still wrong differently. This model is not deterministic at this
configuration, so treat a one-run improvement smaller than those macro spreads as
noise until replicated.

`noise-a-50` includes one JSON parse failure and must not be treated as the better
or worse run; it is part of the operational noise the harness needs to expose.
Also, cached `baseline-50` scored 0.739 / 0.620, outside this two-run range.
That means the two-run spread is a lower bound on uncertainty when comparing a
fresh prompt variant to the cached reference, not a confidence interval.

## Prompt experiment: no unstated defaults (rejected 2026-07-28)

`no-unstated-defaults` targeted the most concentrated triage finding: 9
`functional_status_tier` inferences and 5 `infection_count` inferences. Two
uncached runs scored 0.655 and 0.640 macro-f1. That is below both fresh baseline
runs (0.682 / 0.662); the first is within the observed spread and the replicate
is not. More importantly, both runs over-suppressed the target fields:
`infection_count` precision rose to 1.000 but recall fell to 0.200 / 0.100.
The rule did remove the known invented `1`s, but it also caused the model to
drop counts stated in the text. Keep the overlay as a reproducible rejected
experiment; do not fold it into the production prompt.

## Prompt experiment: prior_infections onset rule (accepted 2026-07-28)

The baseline-50 triage matrix's largest actionable cell was
`prior_infections` / `omission` (10 of the run's 51 omissions). Reading them,
8 were the same failure with one shape: the author states the infection that
started the illness ("I got hit with covid", "five months since covid") and the
model files it as `onset_trigger` only, leaving `prior_infections` empty -- as
though a fact used by one field were spent. The rule says the opposite
explicitly, keeps the "someone else's infection" exclusion so a recall push
doesn't buy back over-attribution, and names the surface form (`covid`, not
`long covid` and not a date).

Two uncached runs, against the two uncached baselines:

| | baselines (noise-a / noise-b) | variant (a / b) |
|---|---|---|
| `prior_infections` f1 | 0.629 / 0.414 | **0.714 / 0.694** |
| `prior_infections` recall | 0.550 / 0.300 | **0.750 / 0.850** |
| `onset_trigger` f1 | 0.696 / 0.640 | **0.818 / 0.708** |
| macro_f1 | 0.682 / 0.662 | 0.636 / 0.680 |

The targeted effect is several times the field's own run-to-run spread and
replicates; macro is a wash, which is what a one-field fix in 21 fields should
look like. Precision did not collapse (0.682 / 0.586 vs 0.733 / 0.667), so this
is not the model spraying `covid` everywhere. `onset_trigger` improving too fits
the mechanism: the rule tells the model the two fields are not in competition.

Folded into `build_system_prompt` in `../patientpunk/llm_extract.py`; the
overlay is deleted. The folded prompt hashes to `0ecec202aaae`, byte-identical
to what both variant runs recorded, so no confirmation run was needed.

**Open, not explained:** `treatment_outcome` f1 was 0.343 / 0.417 in the two
variant runs against 0.452-0.505 across the four baseline runs -- below all of
them, in both replicates. No mechanism connects a `prior_infections` rule to it,
and the field's cells are long multi-value triples whose per-entry matching
swings hard (its candidate entry counts, 42 and 36, are inside the baseline
range 32-38, so the model is not producing less). Treat it as a flagged
observation, not a cost of this rule, and check it against the next baseline.

## Normalization: `prior_infections` COVID alias (2026-07-28)

`normalize_records` now maps `prior_infections: covid-19` to `covid`, matching
the adjudication policy and ensuring candidate and gold values share the same
controlled vocabulary. The accompanying uncached run scored 0.651 / 0.502,
versus 0.662 / 0.501 for one uncached pre-change run; that macro difference is
inside the measured noise floor and cannot establish a model-quality change.
The alias itself is deterministic and has regression coverage, so it remains
independently of the noisy run-level statistic.

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

## Adjudication of the 146 disagreements (done 2026-07-27)

All 146 cells in `review/review_20260728T035253Z.json` are resolved and applied.
`fixtures/eval_50.json` now carries **340 gold cells**: 92 `spotcheck`, 102
`agreed`, 146 `adjudicated`. 50 of the adjudicated cells resolved to *empty* --
that is a label too, and it is what makes the false-positive fields measurable.

The rules used are written down in **`review/ADJUDICATION_POLICY.md`**, including
the two decisions this file said to settle first:

- **`dosage` = bare dose** (`2-4 mg`, not `2-4 mg nicotine gum`). The field
  description says "retain the number and unit"; `medications` holds the drug.
  Dietary quantities (`3 L water`) are not doses.
- **`functional_status_tier` requires a stated function level** -- the tier word
  itself, or an unambiguous global capacity statement ("can't leave the house",
  "max 3,000 steps"). Not derivable from symptom severity, distress, an episodic
  crash, or work status. Strict, and it matches what the two labelers already
  agreed on: 7 of the 8 tier disagreements were production inferring a tier from
  a symptom list where the labeler declined; the eighth had them inferring
  *different* tiers from the same text.

Six other cross-cutting rules were forced by the cells and are in that file --
acute COVID is not a `condition`; `prior_infections` vocabulary is bare `covid`;
no arithmetic for `age_at_onset` / duration fields; `infection_count` needs a
stated count (all 6 production `1`s -> empty); work/school ability is
`work_disability_status`, never `social_impact`; third-party posts extract
nothing clinical.

Every resolved value was checked to be a fixed point of `normalize_records`, so
gold and candidate are compared in the same surface form.

Where a rule makes gold narrower than a defensible extraction, it costs a false
EXTRA. That is deliberate: an EXTRA is visible in triage and can be re-argued,
while a permissive gold silently rewards the inference the prompt forbids.

## Reading baseline-50

133 mismatches over 21 fields. The weakest fields by f1:

| field | f1 | precision | recall | shape |
|---|---|---|---|---|
| `prior_infections` | 0.452 | 0.636 | 0.350 | 9 MISS -- the model does not record the infection the post is *about* |
| `social_impact` | 0.500 | 0.429 | 0.600 | 5 DIFF / 5 EXTRA -- wording, and bleed from work/school |
| `treatment_outcome` | 0.500 | 0.510 | 0.490 | 7 DIFF -- outcome label and symptom granularity |
| `biomarker_results` | 0.552 | 0.727 | 0.444 | misses stated normal results |
| `work_disability_status` | 0.606 | 0.667 | 0.556 | |
| `dosage` | 0.609 | 0.583 | 0.636 | |
| `functional_status_tier` | 0.645 | 0.500 | 0.909 | 9 EXTRA -- inferred tiers, exactly what the policy above declines |

`infection_count` is precision 0.562 / recall 0.900 for the same reason: 7 EXTRA,
all of them `1` inferred from a single mentioned infection.

Do not read `prior_infections` recall as purely a prompt problem before triage:
part of the gap is `covid` vs `covid-19`, which is a `_CANONICAL_MAPS` entry, not
a prompt rule. That distinction is the whole point of stage 2.

## Where this is at (updated 2026-07-28)

The harness and the loop around it are built, and the loop has now run twice
end to end: `no-unstated-defaults` (rejected on replication) and the
`prior_infections` onset rule (accepted on replication, folded into
`build_system_prompt`). Both were chosen from the triage matrix rather than from
reading mismatches, and both were replicated before the verdict -- the two
habits this file exists to enforce.

The section below is the 2026-07-27 build-out record.

Done:

- **Fixture text fixed** and pinned by `tests/test_extraction_quality_fixture.py`.
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
- **`eval_50.json` is fully labeled and scored.** The `claude-opus-5` /
  `deepseek-v4-flash` labeling pass agreed on 102 cells; the 146 disagreements
  were adjudicated against the post text under `review/ADJUDICATION_POLICY.md`
  and applied. `baseline-50` above is the reference row.

The pre-adjudication disagreement split, kept because it says where the two
models differ in kind:

| shape | n | what it usually is |
|---|---|---|
| both models produced values, different | 62 | granularity and format (`covid` vs `covid-19`, `blood test` vs `blood tests`, `2-4 mg` vs `2-4 mg nicotine gum`) |
| opus only | 50 | production model under-extracting -- recall gap |
| production only | 34 | opus declining to infer where production inferred (`functional_status_tier`, `infection_count: 1` from a single mentioned infection) |

Top disagreement fields: `prior_infections` (14), `symptom_duration` (12),
`conditions` / `treatment_outcome` / `social_impact` / `mental_health` (11 each).
`prior_infections` topping the list is mostly `covid` vs `covid-19` vs empty --
a normalization question, not a prompt one.

**Caveat on the adjudicated cells:** they were resolved from the post text by a
model (this one), not by a human. That is weaker than the README's `adjudicated`
row implies -- it is a *third* opinion applied under written rules, not an
independent human answer key. The rules are the durable part; disagree with a
cell and re-resolve it, but re-resolve it by changing
`review/ADJUDICATION_POLICY.md` and re-running the affected cells, not one at a
time. The 50 empty resolutions are the ones most worth a human spot-check, since
they are what makes `infection_count` and `functional_status_tier` look bad.

## Next up

The production prompt has changed (`0ecec202aaae`), so the `baseline-50` triage
matrix is now one prompt behind. Re-establish before picking the next variant:

1. **New reference row.** `prior-infections-b` is the closest thing to it, but
   the honest move is a fresh uncached pair on the folded prompt and a new
   `triage.py` matrix from it. The old matrix's `prior_infections` / `omission`
   cell is spent; the next-largest cells were `inference` (29, already tried and
   rejected) and the remaining `omission` spread across
   `symptom_duration` (6), `mental_health` (6), `treatment_outcome` (5),
   `alternative_treatments` (5) -- no single dominant target, so the next variant
   needs the fresh counts rather than these.
2. Check `treatment_outcome` on that new baseline against the flagged drop
   above. If it stays at ~0.35-0.42 with no variant applied, the drop was noise
   in a high-variance field; if it recovers to ~0.50, the folded rule is
   implicated after all and the rule needs re-testing in isolation.
3. Write the top-count variant into `prompts/`, run, `compare.py` against the
   baseline, add a row here. Repeat until the top code stops moving.
4. Only once the prompt is stable: compare cheaper/faster models at fixed prompt.

Still open on the normalization side: singular/plural test names (`blood test` /
`blood tests`, `urine test`). The `covid-19` -> `covid` alias is done. The rest
of the `vocab_variant` / `granularity` counts read as free paraphrase
(`left college` / `dropped out of college`, `fear` / `scared`) -- not a
vocabulary map, and worth deciding whether the scorer should tolerate them
before more of them get filed as model failures.

Prompt candidates carried forward, now with `baseline-50` counts behind them, to
be confirmed or dropped by the triage matrix rather than assumed:

- `infection_count` and `functional_status_tier`: don't fill a plausible default
  where the text is silent -- 16 EXTRA between them. Attempted as
  `no-unstated-defaults` and rejected: the rule as written also suppressed stated
  counts. If retried, it needs to be narrower than "require an explicit count".
- `treatment_outcome`: don't infer "helped" when the author still reports the
  symptom (`t3_vkkcui`).
- `conditions`/`mental_health`: "the author is discussing X" vs "has X"
  (`t3_lmu7ty`, `t3_sa85zi` -- candidate adds depression/anxiety to conditions).
- `functional_status_tier`/`social_impact`: require near-verbatim support
  (`t3_156wgqv`, `t3_6ygbyh`).
