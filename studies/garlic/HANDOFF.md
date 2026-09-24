# Handoff — garlic beliefs and use probe

Paste this into a fresh session in `/Users/eli/Desktop/PatientPunk`, branch `ps-study`.

**Date left off:** 2026-08-13. **Nothing is committed.** Quote contract is short paraphrases (`PROMPT_VERSION` `2026-08-12-v3`). **Stage 5, 5b, and 6 are done** on live `run_id` `c05891b6…`. Stage 5: 1,990 complete / 6 failed. Stage 5b: 38 complete / 11 failed / 1 left `running` (user directed stop; do not resume). Stage 6: [`docs/garlic_probe_run_report.md`](../../docs/garlic_probe_run_report.md). **DESIGN §8 (loader + analysis notebook) is also done** 2026-08-13 — [`garlic.py`](garlic.py) + [`garlic_analysis.ipynb`](garlic_analysis.ipynb), user-requested, quote constraint relaxed to paraphrases. **Read "Analysis phase" below before committing the notebook: its §8 excerpts are frequently verbatim source text.** Do not resume `0ec115ec…`, `7c68eba2…`, or `3a368b7d…`. Do not mix a new `spec_hash` into this run. Same-flags retry of failed units is additional paid work — ask first.

You are continuing [`DESIGN.md`](DESIGN.md) on the generic second-pass engine (`probes/engine.py`). The governing runbook is [`docs/garlic_probe_runbook.md`](../../docs/garlic_probe_runbook.md). Read that and DESIGN.md §2 (plus [`studies/psychedelics/_handoff.txt`](../psychedelics/_handoff.txt) §2) before interpreting any output or spending money.

---

## Where to stop

| Stage | Status |
|---|---|
| 0 Preconditions | **Done.** HTTP timeout is `connect=10, read=90, write=90, pool=60`. Record that for Stage 6. |
| 1 Build cohort + GATE 1 | **Passed**, exact design table. `garlic_cohort.db` exists (gitignored, 1,928 rows, target `garlic`). Cohort is unchanged by the spec edit. |
| 2 Plan (free) | **Done.** `run_id` `c05891b6ecad47900230eb606afbb230a9867fc9f41d1d2b88ec0292a05b03df` (`reused=False`). Volume matches `0ec115ec…` (dedup unchanged). Do not resume stale ids. |
| 3 Inspect volume + GATE 3 | **Passed.** Volume matches design. Prior paid approval was for `0ec115ec…` (verbatim-span spec). |
| 4 Pilot `--limit 25 --workers 10` | Not started on `c05891b6…`. User skipped the paraphrase-spec re-pilot and approved Stage 5. |
| GATE 4 human checks | **Marked complete by user 2026-08-12.** Opus 5 pre-screen stands as documented; human adjudication deferred. Check (a) is whether the paraphrase supports the field, not whether it is verbatim. |
| 5 Full run | **Done 2026-08-13.** 1,990 complete / 6 failed / 1,996 planned. Final resume of the 6 leftover `running` units: `attempted=6 completed=0 failed=6`, exit 1. |
| 5b Repeat ~50 units, separate `--output-db` | **Done 2026-08-13 (stopped short).** 38 complete / 11 failed / 1 `running`. User directed not to finish the last unit. Same `run_id` in `data/probes/garlic_pharmacology_repeat.db`. See **Stage 5b** below. |
| 6 Quote-free report | **Done 2026-08-13.** [`docs/garlic_probe_run_report.md`](../../docs/garlic_probe_run_report.md). |
| Analysis notebooks / loader | **The stop.** Out of scope until asked (DESIGN §8 / §11). |

---

## Spec changes (uncommitted, move `run_id`)

### Dedup key — `evidence.py` (stands)

Per author+target, **`text_sha256` of the window body**. Representative is earliest `created_utc`, then `(source_type, source_id)`. Cross-author copies stay. Do not put `source_id` back in the key. This is why `0ec115ec…` had 3,873 windows rather than 4,027.

### Quotes are short paraphrases — `claim.py` (user 2026-08-12)

The contiguous-span companion was the wrong contract. The 3 `validation_failed` contiguous retries on `0ec115ec…` were the model compressing real source words — which is the desired quote, not a defect. User: paraphrased quotes are superior to direct quotes.

Live contract (`PROMPT_VERSION` `2026-08-12-v3`):

- Prompt **requires** a short paraphrase, not a verbatim excerpt. Rewording is expected. Keep distinctive source terms so the 0.5 floor still locates the passage.
- Validator is the **0.5 bag-of-words floor only**. Do not lower it. Do not reintroduce a contiguous/verbatim companion.
- GATE 4 (a) judges whether the paraphrase supports the field given the window, not whether it is a copy.

Do not resume `0ec115ec…`. Its claims were elicited under the verbatim-span prompt.

---

## Ground rules (do not weaken)

1. **`probes run` is the only paid command.** `plan` never builds a client. No `--confirm-paid-run` until the user has approved that specific stage.
2. **Stop at every GATE.** Pilot approval is not full-run approval. Full-run approval is not Stage 5b approval.
3. **Never commit `data/`, `*.db`, or quote-bearing scratch.** No `git add -f`. GATE 4 sheets live under gitignored `data/probes/garlic_gate4/`.
4. **Never paste source text, quotes, or author hashes** into this folder, a PR, a commit, or a report. Aggregates only.
5. If a command fails, report the error verbatim. Do not retry with different flags to make it pass.
6. **Do not read `patientpunk.db` / `treatment_reports`.** Zero garlic rows; that path plans a successful empty run. Same trap as PR 133.
7. Do not treat garlic bread as use; a food list is not personal avoidance and not a negative efficacy outcome; “I avoid garlic” is not “garlic worsened my long COVID.”
8. Do not reintroduce identity regex gates. FTS/regex is retrieval only.
9. **Do not mix `run_id`s.** Stale: `3a368b7d…`, `7c68eba2…`, `0ec115ec…`. **Live:** `c05891b6ecad47900230eb606afbb230a9867fc9f41d1d2b88ec0292a05b03df` (paraphrase spec, 1,996 planned, 1,990 complete, 6 failed). Do not merge claims across `run_id`s. Do not edit `claim.py` and then resume this run.

---

## GATE 4 — marked complete by user 2026-08-12

User directed this session to mark GATE 4 complete and start Stage 5 (`--workers 20`) on `c05891b6…`. The Opus 5 pre-screen below is the documented review; human adjudication remains deferred. Stage 5b later ran and was stopped short; see that section.

### Opus 5 pre-screen (not a human pass)

Sheets: `data/probes/garlic_gate4/` (gitignored). 80 claims = 80 windows, 280 quotes, join key `sample_id` (`G4-001`…`G4-080`).

**2026-08-12: labeled by Opus 5, not by a human, at the user's explicit direction** (the standing "do not bypass unless the user says to" was invoked). The user's stated plan is human adjudication later. Treat every number here as a **pre-screen**: an AI labeler shares failure modes with the extraction model, so *agreement* is weak evidence and *disagreement* is the informative signal. Do not cite these as GATE 4 pass criteria. The user later marked GATE 4 complete and authorized Stage 5 anyway.

Blindness was preserved across the two passes: two agents with disjoint file access, because `grounding.csv` carries `model_speech_act` and one agent doing both sheets would have un-blinded check (b) on itself. Neither agent could reach `key.csv` or `index.csv`.

Originals are backed up at `blind.csv.orig` / `grounding.csv.orig` (label columns blank) so a clean human pass is still possible.

### (a) Quote grounding — 257/280 = 91.8%

93.6% (147/157) after collapsing to distinct window+field+quote.

| field_path | as sampled | deduped |
|---|---|---|
| speech_act | 79/80 = 98.8% | 45/46 = 97.8% |
| subject | 63/80 = 78.8% | 42/46 = 91.3% |
| exposure_status | 75/80 = 93.8% | 41/46 = 89.1% |
| doses[0] | 27/27 = 100% | 6/6 = 100% |
| 8 other paths (13 rows) | 100% | 100% |

The 23 failures sit in **8 distinct window texts**; one text contributes 14. `subject`'s 78.8% is largely that one duplicated post.

**Validator note, superseded:** 8 of those `n` labels were non-contiguous spans that still cleared 0.5 overlap. A contiguous companion was added, then **removed** — the user ruled paraphrases superior to verbatim spans. Do not put the companion back.

### (b) Blind speech-act — 5/12 on the three values

Overall agreement 71/80 = 88.8% is an artifact: **66 of the 71 are the `other`/`other` cell**. Report the three-way block, not the headline.

| model ↓ / labeler → | food_list | avoidance | culinary | other |
|---|---|---|---|---|
| **food_list** | 1 | 2 | 1 | 0 |
| **avoidance** | 1 | 2 | 0 | 1 |
| **culinary** | 0 | 1 | 2 | 1 |
| **other** | 1 | 0 | 1 | 66 |

Model assigned one of the three 12 times; labeler 12 times; they agree on 5. Note the direction: 2 rows are model `food_list` → labeler `avoidance`, the **opposite** of the §4.4 302-vs-10–37 overcount. n=12 is too thin to declare material confusion or to clear it.

**`_review_queue.csv`** holds the 9 disagreements with a blank `human_verdict` column — the entire adjudication surface for check (b), 9 windows rather than 80.

### Two defects found during the review — now fixed in code

See **Spec changes** above. Dedup stands; the contiguous companion does not. The sample-composition finding (80 rows → 46 distinct texts) remains a reason the old GATE 4 numbers are a pre-screen, not a pass.

Good signal from that sample: across all 36 identical-text rows the model returned identical `speech_act` every time. Zero divergence at temperature 0.

### Next work

1. Stage 5, 5b, and 6 are done. Do not merge a new spec into `c05891b6…`. Do not resume the leftover 5b `running` unit or the 6 Stage 5 failures unless asked.
2. **DESIGN §8** (quote-free loader / notebooks) is the stop. Out of scope until asked.

| File | Role | State |
|---|---|---|
| `INSTRUCTIONS.txt` | Label rules | — |
| `blind.csv` | Check **(b)**. Shuffled. Window text only. | 80/80 `human_speech_act` filled by Opus 5 |
| `grounding.csv` | Check **(a)**. Model fields + quote + window. | 280/280 `grounded` filled by Opus 5 |
| `_ai_blind_labels.csv` / `_ai_grounding_labels.csv` | Raw Opus 5 output, kept as provenance | — |
| `_review_queue.csv` | **The human's actual task on the old sample.** 9 disagreements, blank `human_verdict` | awaiting human |
| `*.orig` | Pre-label backups, label columns blank | for a clean human re-pass |
| `key.csv` / `index.csv` | Analyst join only; `key.csv` un-blinds (b) | — |

**Order was load-bearing and was honored:** the blind pass never saw `grounding.csv`, `key.csv`, or `index.csv`. If a human re-labels from `.orig`, keep that order.

`human_speech_act` ∈ `food_list` · `avoidance` · `culinary` · `none_of_these` · `mixed`.

After labeling, join on `sample_id` and report **only** sample size, grounding pass rate, and the three-way `food_list` / `avoidance` / `culinary` confusion matrix. Material confusion is a prompt fix before Stage 5, not a §8 caveat. A prompt/validator edit changes `spec_hash` → new `run_id` → re-plan, re-pilot `--limit 25`, re-do GATE 4. Do not merge claims across `run_id`s.

The psychedelic run bypassed GATE 4. **Here the user explicitly directed an AI labeling pass on 2026-08-12** (Opus 5), with human adjudication deferred, and on the same date marked GATE 4 complete and authorized Stage 5. That is a documented, deliberate deviation — not a silent bypass like the psychedelic run.

`apply_and_report.py` in that folder merges the label files and prints the matrix; its header and output both state the gate is **not** satisfied until a human error-checks the labels. Re-running it is idempotent and will not overwrite the `.orig` backups. The user overrode that stop on 2026-08-12.

User approved Stage 5 on 2026-08-12 after marking GATE 4 complete. Stage 5 finished 2026-08-13. Stage 5b ran 2026-08-13 and was stopped short by the user. Stage 6 report written 2026-08-13.

---

## GATE 1 (passed, exact)

| | count |
|---|---|
| FTS non-bot authors | **1,928** |
| JSON garlic any-field | **502** |
| JSON ∩ FTS | **500 / 502** |
| FTS authors in the 69k JSON | **1,815** |
| FTS authors with no JSON record | **113** (kept) |
| JSON-only rows | **2**, 21 source items, **zero** garlic-family tokens |

Do not chase the two JSON-only rows. Extractor hallucinations (`raw garlic: helped: constipation` and `garlic: helped: bladder problems` in JSON; no garlic/allicin/kyolic/clove/allium in source).

---

## GATE 2 / 3 identity

Config (do not change; it is in `run_id`):

- `--provider openai --base-url https://openrouter.ai/api`
- `--model deepseek/deepseek-v4-flash`
- `--reasoning-effort medium --temperature 0 --max-tokens 32768`

`--provider openrouter` will refuse `--reasoning-effort`. That is deliberate.

**Live `run_id`:** `c05891b6ecad47900230eb606afbb230a9867fc9f41d1d2b88ec0292a05b03df`

Do not resume `0ec115ec…`, `7c68eba2…`, or `3a368b7d…`.

GATE 3 volume (paraphrase spec; windows unchanged from `0ec115ec…`):

| | Design reference | Verbatim-span spec (`0ec115ec…`) | **Paraphrase spec (`c05891b6…`)** |
|---|---|---|---|
| members | ~1,928 | 1,928 | **1,928** |
| units | ~2,015 | 1,996 | **1,996** |
| windows | ~4,022 | 3,873 | **3,873** |
| total chars | ~2.19M | 2,058,992 | **2,058,992** |
| largest unit | 6,000-char packing | 6,000 | **6,000** |
| HTTP timeout | record for Stage 6 | — | **connect=10, read=90, write=90, pool=60** |

Food-list/culinary units are the belief study, not waste. GATE 3 is volume, not price. Do not quote a live price.

---

## Stage 4 re-pilot (stale `run_id` `0ec115ec…`, verbatim-span spec)

User-approved:

```bash
uv run python -m probes run garlic_pharmacology \
  --run-id 0ec115ecb11eb3bcfbb679efc98be39e8310b8f34f9e6651a6e5b16e94dcba9c \
  --limit 25 \
  --workers 10 \
  --confirm-paid-run
```

Result: `attempted=25 completed=24 failed=1 cache_hits=0` (~2.1 min). Exit code 1.

| | |
|---|---|
| units complete / failed / still planned | **24** / **1** / 1,971 |
| claims | **33** (26 included, 7 excluded) |
| `validation_failed` then retry | **5** (all recovered on attempt 2) |
| of those, contiguous-span | **3** (companion check is live; do not drop it) |
| of those, source ID/type mismatch | **1** |
| of those, `source_type` not post/comment | **1** |
| not-grounded (0.5 floor) | **0** (do not lower the floor) |
| duplicate-event rejections | **0** (do not weaken the fingerprint) |
| complete units with zero claims | **0 / 24** |
| use payload on food_list / avoidance / culinary | **0** stored claims |
| `billing_uncertain` | **0** |

Terminal failure (1 unit, attempt 1 only):

```
LLMResponseError: deepseek/deepseek-v4-flash: provider returned null content
```

Same-flags resume would retry that unit. Not done. Do not change flags to make it pass.

Claim-level `actual_use` is 9/33 — **wrong denominator.** Reporter-level (24 complete units):

| Speech act present | Re-pilot authors | Old-spec pilot | Corpus prior (DESIGN §4) |
|---|---|---|---|
| `actual_use` | **5 / 24 (21%)** | 11 / 25 (44%) | first-person regex floor **~8%** |
| `food_list` | **8 / 24 (33%)** | 3 / 25 (12%) | **~28%** |
| `avoidance` | **1 / 24 (4%)** | 3 / 25 (12%) | **~0.5–2%** (10–37) |
| `culinary` | **1 / 24 (4%)** | 4 / 25 (16%) | **~10%** |

Max claims in one unit: **6** (old spec max 22, inflated by duplicate windows). No unit has ≥10 events. n=24 is still a pilot.

---

## Stage 4 pilot (old `run_id` `7c68eba2…`, historical)

Historical. Do not treat these 25 units as complete for the new spec.

First paid invocation failed in ~7s, all 25 `transport_failed`:

```
TypeError: Messages.create() got an unexpected keyword argument 'reasoning_effort'
```

Cause: `RunConfig.provider=openai` puts `reasoning_effort` on the request, but `get_llm_client()` followed env `LLM_PROVIDER=openrouter` (repo-root `.env`) and built the Anthropic SDK. Client-side; 25 `billing_uncertain` on those rows; accepted attempts later are certain.

Fix (uncommitted, **not** in `spec_hash`, does not move `run_id`): `run_probe` passes `config.provider` / `config.base_url` into `get_llm_client`. OpenRouter’s Anthropic-shaped root `https://openrouter.ai/api` is rewritten to `/api/v1` for the OpenAI SDK only. Regression test in `variable_extraction/tests/test_llm_response_validation.py`.

Resume (user-approved):

```bash
uv run python -m probes run garlic_pharmacology \
  --run-id 7c68eba20a9765585804a9fb13016b92e7693f3442a5a89c02b50ba7bcc1caa5 \
  --limit 25 \
  --workers 10 \
  --confirm-paid-run
```

`--workers` is not in `RunConfig` and did not move `run_id`. Source `.env` for `OPENROUTER_API_KEY`; the engine now ignores env `LLM_PROVIDER` for this client.

Result: `attempted=25 completed=25 failed=0 cache_hits=0` (~6.9 min).

| | |
|---|---|
| units complete / still planned | **25** / 1,979 |
| claims | **80** (71 included, 9 excluded) |
| `validation_failed` then retry | 8 (recovered) |
| not-grounded | **1** (do not lower the 0.5 floor) |
| duplicate-event rejections | **0** (do not weaken the fingerprint) |
| complete units with zero claims | **1 / 25** (passing mention) |
| use payload on food_list / avoidance / culinary | **0** stored claims |

Claim-level `actual_use` is 54/80 — **wrong denominator.** Reporter-level (25 authors = 25 units):

| Speech act present | Pilot authors | Corpus prior (DESIGN §4) |
|---|---|---|
| `actual_use` | **11 / 25 (44%)** | first-person regex floor **~8%** |
| `food_list` | 3 / 25 (12%) | **~28%** |
| `avoidance` | 3 / 25 (12%) | **~0.5–2%** (10–37) |
| `culinary` | 4 / 25 (16%) | **~10%** |

Direction matches the known failure mode (avoidance over-call 302 vs 10–37). That is why GATE 4 (b) exists. Two units have ≥10 events (max 22); do not headline claim counts.

---

## Stage 5 — full run (approved 2026-08-12, finished 2026-08-13)

Resume the **post-paraphrase** `run_id` from `probes plan`, not `0ec115ec…`. Complete units on that run are skipped. User directed `--workers 20` (not in `RunConfig`; does not move `run_id`):

```bash
uv run python -m probes run garlic_pharmacology \
  --run-id c05891b6ecad47900230eb606afbb230a9867fc9f41d1d2b88ec0292a05b03df \
  --workers 20 \
  --confirm-paid-run
```

`--progress` was added later the same day (not in `RunConfig`). The first invocation was interrupted with units still `running`. A 2026-08-13 resume of the leftover 6 used the same flags plus `--progress`.

### Mid-run spec drift (restored before the final 6-unit resume)

During Stage 5, `claim.py` on disk drifted off stored `spec_hash` `4dea2fd1049d033c…`:

- `QUOTE_GROUNDING_MIN_OVERLAP` commented out / set to `0.1`, and the 0.5 check disabled. **Forbidden.** Restored to `0.5` with the check live.
- `magnitude_basis` removed and `PROMPT_VERSION` bumped to `2026-08-13-v1` (user request, 2026-08-13). That **moves `run_id`**. Reverted so the leftover units were validated under the same spec as the 1,990 already complete.
- `source_type` allow-list widened to `reddit_comment` / `reddit_post`. Reverted to `{post, comment}`.

`claim.py` on disk now matches the stored spec (`PROMPT_VERSION` `2026-08-12-v3`, floor 0.5, `magnitude_basis` present). Re-applying the magnitude_basis removal requires a new plan, new `run_id`, re-pilot, and GATE 4. Do not mix it into `c05891b6…`.

### Stage 5 results (`c05891b6…` only)

Final resume of the 6 leftover units (all were ~5.7–5.9k-char packed units):

```
run=c05891b6… attempted=6 completed=0 failed=6 cache_hits=0
```

Exit code 1. Last errors (verbatim heads): 3× `LLMResponseError: deepseek/deepseek-v4-flash: provider returned null content`; 1× `source_type must be post or comment`; 1× `events[N].duration: Extra inputs are not permitted`; 1× `speech_act_quote: quote is not grounded…`. Same-flags retry of those 6 is additional paid work — do not start it unless asked.

| | |
|---|---|
| members | **1,928** (1 author has no complete unit) |
| units complete / failed / planned | **1,990** / **6** / 0 |
| windows / total chars | **3,873** / **2,058,992** |
| claims | **3,723** (2,911 included, 812 excluded) |
| complete units with zero claims | **24 / 1,990** |
| use payload on food_list / avoidance / culinary | **0** stored claims |
| duplicate-event rejections | **0** |
| cache hits | **0** |
| HTTP timeout | connect=10, read=90, write=90, pool=60 |

Attempts: **1,990** accepted, **3,994** `validation_failed`, **103** `transport_failed`. `billing_uncertain` **72** on this run (no usage). The 25 TypeError `billing_uncertain` rows live on stale `7c68eba2…`, not here.

`validation_failed` heads (a row can match more than one): not-grounded **3,330**; `source_type` **270**; use-payload **112**; source ID/type mismatch **107**; source not in unit **89**; extra inputs **25**; truncated `max_tokens` **20**; bad JSON **3**; placeholder **1**. Not-grounded fields: `subject` 1,573, `exposure_status` 938, `speech_act` 804; dose/effect/AE quotes are rare. Transport: timeout 41, null content 31, connection 28.

**534 / 1,990** complete units passed on attempt 1 with zero validation failures. **1,456** needed at least one validation retry. Do not lower the 0.5 floor. This is the prompt-vs-guard mismatch documented during the run: the model writes taxonomy glosses (`author`, `personal`, `listed`…) for the three required quotes; retries eventually copy source tokens (accepted quotes are mostly overlap 1.0). Validation retries are **65% of realized spend**.

Realized cost from `usage_json.provider_cost` over **6,015** attempts that carry usage: **$6.9939**

| status | n with cost | cost |
|---|---|---|
| accepted | 1,990 | $2.1803 |
| validation_failed | 3,994 | $4.5551 |
| transport_failed | 31 | $0.2586 |

Tokens 23.49M in / 20.92M out; reasoning **17.82M** (85% of output). The 72 `billing_uncertain` attempts are **not** in $6.99.

Claim-level `actual_use` is 1,412 / 3,723 — **wrong denominator.** Reporter-level (1,927 authors with a complete unit):

| Speech act present | Stage 5 authors | Re-pilot (n=24) | Corpus prior (DESIGN §4) |
|---|---|---|---|
| `actual_use` | **650 / 1,927 (33.7%)** | 5 / 24 (21%) | first-person regex floor **~8%** |
| `actual_use` + `self` | **640 / 1,927 (33.2%)** | — | — |
| `food_list` | **355 / 1,927 (18.4%)** | 8 / 24 (33%) | **~28%** |
| `avoidance` | **109 / 1,927 (5.7%)** | 1 / 24 (4%) | **~0.5–2%** (10–37) |
| `culinary` | **408 / 1,927 (21.2%)** | 1 / 24 (4%) | **~10%** |

Avoidance 109 is above the 10–37 regex band and below the old 302 overcount. Food-list is under the 536-author regex prior; culinary is over. 33 units have ≥10 claims (max 32). Do not headline claim counts.

---

## Stage 5b — repeat pass (approved and run 2026-08-13; stopped short)

Stability check: ~50 units into `data/probes/garlic_pharmacology_repeat.db` (gitignored). Same `run_id` `c05891b6…` (`reused=True` as expected). Cold cache, new provider calls. Temperature 0, so this is residual provider nondeterminism, not a full re-elicitation.

Command actually used (`--workers 20 --progress` not in `RunConfig`):

```bash
uv run python -m probes run garlic_pharmacology \
  --cohort-db garlic_cohort.db \
  --source-db reddit_2026-06-13.db \
  --output-db data/probes/garlic_pharmacology_repeat.db \
  --provider openai --base-url https://openrouter.ai/api \
  --model deepseek/deepseek-v4-flash \
  --temperature 0 \
  --max-tokens 32768 \
  --reasoning-effort medium \
  --limit 50 \
  --workers 20 \
  --progress \
  --confirm-paid-run
```

Did **not** pass `--run-id` (that would have resumed the Stage 5 store). User directed **stop without finishing** the last unit. Do not resume the leftover `running` row unless asked.

### Result

| | |
|---|---|
| attempted | **50** (all 50 were `complete` on Stage 5) |
| complete / failed / left running | **38** / **11** / **1** |
| claims | **69** (57 included, 12 excluded) |
| complete units with zero claims | **1 / 38** |
| cache hits | **0** |
| `billing_uncertain` | **0** |

Attempts: 38 accepted, 75 `validation_failed`, 0 `transport_failed`. Validation heads: not-grounded 63, `source_type` 7, use-payload 2, source not in unit 2, ID/type 1. Same paraphrase/floor fight as Stage 5.

The leftover `running` unit has two `validation_failed` attempts (use-payload, then not-grounded) and was on attempt 3/3 when stopped.

Realized cost from `usage_json.provider_cost` over 113 attempts: **$0.1080** (accepted $0.0414, validation_failed $0.0667). Tokens 0.44M in / 0.30M out; reasoning 0.26M.

### Agreement vs Stage 5 (38 units complete in both)

Join claims greedily on `source_window_id` + `speech_act`, then same window. **68** pairs; 0 Stage 5 claims unmatched; 1 extra 5b claim. 37/38 units have the same claim count. 26/38 units have the same set of speech acts.

| metric | n | vs first-pass JSON prior |
|---|---|---|
| top-level field-set identical | **52 / 68 = 76.5%** | 36.5% |
| shared top-level values equal | **541 / 609 = 88.8%** | 58.8% |
| pair: every shared key equal | 21 / 68 = 30.9% | — |
| flattened field-set identical | 33 / 68 = 48.5% | — |
| flattened values equal | 563 / 607 = 92.8% | — |
| `speech_act` | 54 / 68 = 79.4% | — |
| `subject` / `exposure_status` | 61 / 68 each | — |
| `included` | 63 / 68 | — |

Say in Stage 6: temperature-0 residual nondeterminism; 12/50 units did not complete on the repeat (11 exhausted retries + 1 stopped). Completers look more stable than the first-pass JSON on field-set and shared values. `speech_act` still moves on 14/68 paired claims. The three-way `food_list` / `avoidance` / `culinary` block on this sample is too small to headline (a few swaps, including one `food_list`↔`avoidance` each way).

---

## Stage 6 — quote-free report (done 2026-08-13)

Written to [`docs/garlic_probe_run_report.md`](../../docs/garlic_probe_run_report.md). Ops/methods only (volume, claims, reporter-level speech-act mix, cost, GATE 4 pre-screen, 5b agreement). DESIGN §8 cuts (preparation, polarity, mechanisms, AE shares, loader, notebooks) were left out. Live DB numbers matched the aggregates already in this file; extra_inputs overlapping head is 25; flattened/top-level 5b agreement reproduced. HTTP timeout `connect=10, read=90, write=90, pool=60`. Realized Stage 5 cost **$6.9939** over 6,015 attempts with usage; 72 `billing_uncertain` not in that total; 25 TypeError uncertain rows are on stale `7c68eba2…`. Headline units are **reporter-level**. Avoidance n = 109 is provisional (GATE 4 (b) 5/12). No dose-response.

---

## Analysis phase — DESIGN §8 (done 2026-08-13, user-requested)

| Path | Role | Git |
|---|---|---|
| `studies/garlic/garlic.py` | Read-only loader + aggregation helpers | untracked |
| `studies/garlic/garlic_analysis.ipynb` | Executed high-level analysis, 49 cells / 9 figures | untracked — **see privacy note** |

Run pinned by full `run_id` in `garlic.RUN_ID`; the DB holds four runs and the loader raises rather than guessing. `author_hash` → dense `reporter` id at load; `source_window.text` never enters a frame. Every count in the ops report reproduces from the notebook.

**Denominators (fixed by schema, stated on every cut):** speech acts 1,927 accounts with a complete unit · belief payload 950 · use payload 640 · effect records 301. Bins below reporter n = 30 are collapsed, not plotted.

**Findings not already in the ops report:**

1. **Mechanism sorts almost cleanly by polarity.** Pro-use: `antimicrobial` 195/214 accounts, `immune` 77/87, `gut_or_biofilm` 73/88, `cardiovascular_or_bleeding` 126/149. Anti-use: `allium_intolerance` 67/72, `histamine_or_mcas_trigger` 31/38. The two camps assert different mechanisms rather than arguing over one.
2. **Cardiovascular talk is bigger than the prior and runs the wrong way.** DESIGN §4.5 expected ~70 accounts of anticoagulant *caution*; the extraction finds 149 accounts, 126 of them pro-use (blood pressure, circulation, microclots). Never checked by hand — top validation target after the food_list/avoidance boundary.
3. **The histamine/MCAS anti-use engine is much smaller than the 198-account co-mention prior** — 38 accounts assert it as a mechanism. Same co-mention-vs-assertion error that produced the discredited 302 avoidance figure.
4. **`unspecified_form` is 330/640 (52%) of use reporters.** Over half say they take garlic without saying in what form. Caps the preparation cut.
5. **Belief is overwhelmingly uncited** — 156/950 (16.4%) cite any garlic-specific authority; `named_protocol` is 7 accounts.
6. **Mechanism talk ≫ experience.** 149 accounts discuss blood-thinning; 3 report a bleeding adverse event.
7. **Adverse events:** 106/640 (16.6%) report ≥1, 18 (2.8%) explicitly deny, ~81% silent. Not a side-effect rate.

**Verbatimness (new measurements, `garlic.quote_character()` and `garlic.freetext_character()`):** DESIGN §7.5 assumed short paraphrases.

- **Evidence anchors** (0.5 floor applies): 12,691 strings, **41.9% exact contiguous spans**, 62% full bag-of-words overlap. Grounding quotes 34–40%; payload quotes `duration` 85%, `doses` 82%, `adverse_events` 81%, `effects` 71%.
- **Free-text payload fields** (**no floor at all**): 835 strings, **74.7% contiguous**. `duration.raw_text` 95%, **`doses.raw_text` 91%** — the most literal field in the whole extraction — `adverse_events.raw_event` 65%, `effects.target` 55%.

**A "model-written summary field" is not the safe alternative to a quote; it is the less governed one.** DESIGN §7.3 asks `Dose.raw_text` to preserve the author's amount string, and nothing constrains `raw_event` or `target`. An earlier draft of the notebook printed these under "model-written summary fields (not quotes)" as if safer — corrected. The 0.5 floor is a fabrication guard covering evidence anchors only, and GATE 4 (a)'s 91.8% was never evidence of paraphrasing.

**Privacy — decide before committing the notebook.** Its §8 prints ~32 short unlinked excerpts, frequently verbatim Reddit text. That does not satisfy DESIGN §10 ("tracked if it contains no private fields") as written. Options: strip §8 outputs before committing · keep the executed copy gitignored and commit a cleared one · amend DESIGN §2 to permit short unlinked excerpts. **Not decided.** Nothing else in the notebook carries source text, hashes, or window text; `effects.target` is used in §5.3 only through closed symptom classes.

---

## What was implemented (uncommitted)

| Path | Role |
|---|---|
| `probes/garlic_pharmacology/` | Probe package (`evidence.py`, `claim.py`, `cohort.sql`) |
| `scripts/build_garlic_cohort_db.py` | FTS cohort + GATE 1 |
| `tests/test_garlic_pharmacology.py` | Garlic tests (dedup + paraphrase-quote cases) |
| `docs/garlic_probe_runbook.md` | Stages 0–6 |
| `docs/garlic_probe_run_report.md` | Stage 6 quote-free ops/methods report |
| `studies/garlic/DESIGN.md` | Spec; status line: Stage 6 done, report at `docs/garlic_probe_run_report.md` |
| `studies/garlic/garlic.py` | §8 read-only loader + aggregation helpers |
| `studies/garlic/garlic_analysis.ipynb` | §8 executed analysis notebook (privacy note above) |
| `studies/README.md` | Index row **implemented** |
| `probes/engine.py` | `run_probe` builds the client from `RunConfig`, not env `LLM_PROVIDER` |
| `variable_extraction/patientpunk/_utils.py` | `get_llm_client(provider=, base_url=)`; OpenRouter `/api` → `/api/v1` for OpenAI SDK |
| `tests/test_probes_workers.py` | Asserts client kwargs match `RunConfig` |
| `variable_extraction/tests/test_llm_response_validation.py` | reasoning_effort regression |

Git: branch `ps-study`. Probe package, builder, garlic tests, runbook, and `studies/garlic/` are untracked. Tracked edits: `probes/engine.py`, `variable_extraction/patientpunk/_utils.py`, worker + LLM-response tests, `studies/README.md`. Do not commit unless asked. Do not commit `garlic_cohort.db`, `data/probes/`, or GATE 4 sheets.

---

## Load-bearing decisions (do not “simplify”)

**Cohort is FTS, not first-pass JSON.** `TARGETS` lives in `evidence.py`; the builder imports `matching_author_hashes` / `TARGETS` / `author_hash`. Single target `garlic`. Allicin and Kyolic are preparations, not extra cohort targets. Include the 113 authors absent from the 69k JSON.

**Hasher** is `hashlib.sha256(username.encode()).hexdigest()` — no case fold, no salt — matching `scripts/db_to_corpus.py`. Changing it empties the run or makes GATE 1 a lie.

**FTS query** is `garlic OR allicin OR kyolic`. Term regex also catches `allium sativum`. Do **not** add bare `allium` or the garlic emoji.

**GATE 1 JSON matcher** must stay word-bounded:

```python
JSON_GARLIC_RE = re.compile(
    r"\bgarlic\b|\ballicin\b|\bkyolic\b|\ballium sativum\b",
    re.IGNORECASE,
)
```

An unanchored `garlic` counted **503** JSON rows (one letter-embedded substring). The design table is **502 / 500**. Do not reuse the evidence term regex for this check.

**`included` and `use_payload_allowed` are separate.** Reusing `included` as the payload gate lets a `food_list` event carry an adverse-event status.

| Property | Rule | Job |
|---|---|---|
| `use_payload_allowed` | `speech_act == actual_use and subject == self` | Gates doses, effects, AE lists, `adverse_event_status`, `preparation` |
| `included` | actual_use+self, avoidance, food_list, recommendation, warning, mechanism_belief, question | Analysis membership only. Gates nothing. |

Culinary, `planned_or_considered`, `other`, and actual_use about someone else are `included=false` (inspectable denominator). Belief payload (polarity / mechanism / cited_authority) is **never** gated on speech act. One passage that is both use and mechanism is **one event**, not two.

**Engine placeholder ban** full-matches the string `unspecified`. Closed-vocab remainders are `unspecified_form` and `unspecified_authority`, not `unspecified`. Prompt and schema use those tokens. Do not rename them back.

**Quote-grounding floor is 0.5.** Do not lower it. Quotes are short paraphrases; there is **no** contiguous/verbatim companion. Do not add one back. Duplicate-event fingerprint is the whole event JSON with `exclude_none=True`; two distinct food-list mentions in one unit can serialize identically and reject the unit. Do not weaken the fingerprint.

**Window dedup is per-author `text_sha256`.** Do not put `source_id` back in the key. Keep the earliest `created_utc` as the representative.

**`cited_authority`** requires a quote, and the citation must be about garlic. A nearby “my doctor” is not `clinician`.

**GATE 4 is two views of the same sample**, not one worksheet: grounding sheet may include model fields; blind sheet is window text only (no `speech_act`). Join after labeling for the `food_list` / `avoidance` / `culinary` confusion matrix. A prior pass overcounted avoidance 302 vs a true 10–37.

**`--workers` is not in `RunConfig`.** It must not move `run_id`. Pilot used `--workers 10`.

**Client follows `RunConfig`, not `.env`.** `get_llm_client()` must be called with `provider=` / `base_url=` from the stored config. Env `LLM_PROVIDER=openrouter` plus `--provider openai` is how Stage 4 first died.

---

## Reviews already done

A code-reviewer subagent reviewed each implementation step. Findings already applied:

1. Probe package: no critical/important issues.
2. Cohort builder: JSON regex was unanchored (`503` vs `502`); fixed to word boundaries.
3. Tests: grounding floor was not actually pinned at 0.5; food_list dose rejection was vacuous; AE inverse (`non-reported` + list) untested. All three fixed; 25 garlic tests still pass.
4. Runbook: Stage 5b had no spend stop; GATE 4 one-sheet would un-blind check (b). Both fixed in the runbook.
5. Stage 0–3 execution: complete. GATE 1 re-run after the `sys.path` fix matched the design table exactly.
6. Stage 4 first execution: Anthropic SDK vs `reasoning_effort`. Client routing fixed; resume completed 25/25.
7. GATE 4 pre-screen: per-author `text_sha256` dedup (stands) + contiguous-span quote check (**reversed** — user required short paraphrases; companion removed).

---

## Traps

| Symptom | Cause | Action |
|---|---|---|
| `no such table: garlic_cohort` | `--cohort-db patientpunk.db` | Use `garlic_cohort.db` from Stage 1. |
| GATE 1 JSON ∩ FTS is 0 | Hasher drift | Stop. Do not proceed. |
| `provider 'openrouter' cannot send ['reasoning_effort']` | Wrong **flag** | `--provider openai --base-url https://openrouter.ai/api` |
| `TypeError: … unexpected keyword argument 'reasoning_effort'` | Wrong **client** (env `LLM_PROVIDER=openrouter`) | Client must come from `RunConfig`; do not “fix” by dropping effort |
| `run_id` `3a368b7d…` or `7c68eba2…` | Stale spec | Resume only the `run_id` from the post-spec `probes plan` |
| `run_id` changed on a new plan | `claim.py` / evidence / cohort / config | Diff `spec_hash`; do not mix runs |
| Widening FTS to emoji / `allium` | “Recall gap” in §4.6 | Documented limitation. Do not widen. |
| Opening `key.csv` before `blind.csv` is done | Un-blinds GATE 4 (b) | Blind first, then grounding |
| `claim.py` on disk does not hash to stored `spec_hash` | Mid-run prompt/validator edit | Restore the matching spec before any resume. A new spec needs a new `run_id`. |

---

## What this study is not asking

Efficacy, causal effect, incidence, dose-response, or “garlic works for long COVID.” Every figure is a share of extractable reports. Silence is not absence. The word “reporter” means a Reddit account.
