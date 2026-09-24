# Stage 6 report — garlic beliefs and use probe

**Run ID:** `c05891b6ecad47900230eb606afbb230a9867fc9f41d1d2b88ec0292a05b03df`
**Date:** 2026-08-13 · **Branch:** `ps-study`
**Model:** `deepseek/deepseek-v4-flash` via OpenRouter (OpenAI-compatible surface)
**Config:** `--provider openai --base-url https://openrouter.ai/api`, reasoning effort `medium`, temperature 0, max_tokens 32768
**Quote contract:** short paraphrases (`PROMPT_VERSION` `2026-08-12-v3`). Grounding floor 0.5. No contiguous/verbatim companion.

All figures below are aggregates drawn from the probe database only, filtered to this `run_id`. No quotes, source text, or author hashes appear here or were used to produce it. Headline units are **reporter-level** (a Reddit account), not claim-level.

The default store also holds three stale runs (`3a368b7d…`, `7c68eba2…`, `0ec115ec…`). They are not mixed into any table here.

---

## 1. Read these limitations before using any number

**This is a self-selected Reddit reporting cohort, not a clinical cohort.** Every figure is a share of extractable reports. Silence is not absence. Do not read these numbers as efficacy, causal effect, incidence, or dose-response. Do not infer chronology from timestamps.

**GATE 4 was an Opus 5 pre-screen, then marked complete by the user on 2026-08-12.** A human has not error-checked the labels. Agreement between an AI labeler and the extraction model is weak evidence; disagreement is the informative signal. Human adjudication remains deferred (`_review_queue.csv` still has a blank `human_verdict` column). Check (a) asks whether a short paraphrase supports the field given the window, not whether it is a verbatim span.

**The three-way `food_list` / `avoidance` / `culinary` block was 5/12.** Overall 71/80 agreement is an artifact of the `other`/`other` cell (66 of 71). Personal-avoidance reporter n = 109 is above the n < 30 rule, but those figures are **provisional** because of that block. A prior regex pass overcounted avoidance 302 against a true 10–37.

**Six of 1,996 units failed** after exhausting retries. Same-flags retry is additional paid work and was not done. One cohort member produced no unit.

**Stage 5b was stopped short by the user:** 38 complete / 11 failed / 1 left `running`. Temperature 0, so the repeat measures residual provider nondeterminism, not a full re-elicitation. 12/50 units did not complete.

**Mid-run spec drift was restored before the final six-unit resume.** This report is the paraphrase spec only (`spec_hash` `4dea2fd1049d033c…`). Do not merge claims from `0ec115ec…` (verbatim-span prompt) or earlier ids.

Additional garlic rules: do not treat garlic bread as use; a high-histamine food list is not personal avoidance and not a negative efficacy outcome; “I avoid garlic” is not “garlic worsened my long COVID.”

---

## 2. Cohort and units

HTTP timeout recorded at GATE 3 and still in code: `connect=10, read=90, write=90, pool=60`.

| | |
|---|---|
| cohort members | 1,928 |
| authors with ≥1 complete unit | 1,927 |
| members with no unit | 1 |
| source windows | 3,873 |
| total characters | 2,058,992 |
| largest unit | 6,000 |
| units planned | 1,996 |
| units complete | **1,990 (99.7%)** |
| units failed (exhausted attempts) | **6 (0.3%)** |

Volume matches GATE 3 / the paraphrase-spec plan. Food-list and culinary units are the belief study, not waste.

---

## 3. Claims

| | |
|---|---|
| claims total | 3,723 |
| included (`included=1`) | 2,911 (78.2%) |
| excluded (`included=0`) | 812 (21.8%) |
| complete units with zero claims | 24 / 1,990 |
| use payload on `food_list` / `avoidance` / `culinary` | **0** stored claims |
| duplicate-event rejections | **0** |

`included=0` rows are retained as the inspectable denominator — culinary, planned-only, residual `other`, and actual-use about someone else. They are not errors. `included` is analysis membership only and gates nothing; `use_payload_allowed` (`speech_act=actual_use` and `subject=self`) is the only gate on doses / effects / adverse events.

Included by speech act (claim-level, not a headline): `actual_use` 1,401 (all `subject=self`); `food_list` 491; `recommendation` 455; `mechanism_belief` 217; `question` 188; `avoidance` 138; `warning` 21. Excluded: `culinary` 494; `other` 191; `planned_or_considered` 116; `actual_use` about someone else 11.

33 units have ≥10 claims (max 32). Do not headline claim counts.

---

## 4. Speech-act mix

**Claim-level `actual_use` is 1,412 / 3,723 — the wrong denominator.** One account is not an independent observation, and mixed-act reporters are expected. Reporter-level presence among the 1,927 authors with a complete unit:

| Speech act present | Stage 5 authors | Share | Corpus prior (DESIGN §4) |
|---|---|---|---|
| `actual_use` | **650 / 1,927** | 33.7% | first-person regex floor ~8% |
| `actual_use` + `self` | **640 / 1,927** | 33.2% | — |
| `food_list` | **355 / 1,927** | 18.4% | ~28% (536 authors) |
| `avoidance` | **109 / 1,927** | 5.7% | ~0.5–2% (10–37) |
| `culinary` | **408 / 1,927** | 21.2% | ~10% |
| `recommendation` | 297 / 1,927 | 15.4% | — |
| `mechanism_belief` | 179 / 1,927 | 9.3% | — |
| `question` | 164 / 1,927 | 8.5% | — |
| `other` | 166 / 1,927 | 8.6% | — |
| `planned_or_considered` | 96 / 1,927 | 5.0% | — |
| `warning` | 15 / 1,927 | 0.8% | — |

A reporter may appear in more than one row. Avoidance 109 is above the 10–37 regex band and below the old 302 overcount; treat it as provisional (GATE 4 (b) 5/12). Food-list is under the 536-author regex prior; culinary is over. Preparation mix, polarity, mechanisms, and adverse-event shares are DESIGN §8 and are not in this report.

Claim-level speech-act counts (wrong denominator; listed only as a methods check): `actual_use` 1,412; `culinary` 494; `food_list` 491; `recommendation` 455; `mechanism_belief` 217; `other` 191; `question` 188; `avoidance` 138; `planned_or_considered` 116; `warning` 21.

---

## 5. Attempts, cache, and cost

| status | count |
|---|---|
| accepted | 1,990 |
| validation_failed | 3,994 |
| transport_failed | 103 |
| cache hits | 0 |
| **billing_uncertain** | **72** (all `transport_failed`; no usage) |

Attempts per unit (complete + failed) go above three because resumes accumulate attempts; the per-invocation ladder remains 3. 531 units had one attempt; the tail reaches 23 on one unit.

**534 / 1,990** complete units passed on attempt 1 with zero validation failures. **1,456** needed at least one validation retry.

Validation-failed heads (a row can match more than one of 3,994):

| category | n |
|---|---|
| not grounded in the cited source window | 3,330 |
| `source_type` must be post or comment | 270 |
| use-payload (doses / effects / AE / preparation without `use_payload_allowed`) | 112 |
| source ID/type mismatch | 107 |
| source does not belong to unit | 89 |
| extra inputs | 25 |
| truncated `max_tokens` | 20 |
| bad JSON | 3 |
| placeholder | 1 |

Not-grounded fields: `subject` 1,573; `exposure_status` 938; `speech_act` 804; dose / effect / AE / authority quotes are rare. Transport: timeout 41; null content 31; connection 28; malformed provider JSON 3.

**Realized cost** from `usage_json.provider_cost` over **6,015** attempts that carry usage: **$6.9939**. Do not recompute from list price. Failed attempts were billed too.

| status | n with cost | cost |
|---|---|---|
| accepted | 1,990 | $2.1803 |
| validation_failed | 3,994 | $4.5551 |
| transport_failed | 31 | $0.2586 |

Validation retries are **65% of realized spend** ($4.5551 / $6.9939). Tokens 23.49M in / 20.92M out; reasoning **17.82M** (85% of output).

**The 72 `billing_uncertain` attempts are not in $6.99** and may also have been billed. A separate **25** `billing_uncertain` TypeError rows live on stale `7c68eba2…` in the same file (Anthropic SDK vs `reasoning_effort` on the old-spec pilot). They are not this run.

---

## 6. GATE 4 (Opus 5 pre-screen)

Sheets live under gitignored `data/probes/garlic_gate4/`. 80 claims = 80 windows, 280 quotes. Labeled by Opus 5 at the user's direction on 2026-08-12; the user marked the gate complete the same day and authorized Stage 5. This is a documented deviation, not a silent bypass. Numbers below are copied from that pre-screen; the quote-bearing sheets were not re-opened for this report.

**(a) Quote grounding — 257/280 = 91.8%** (147/157 = 93.6% after collapsing to distinct window+field+quote).

| field_path | as sampled | deduped |
|---|---|---|
| speech_act | 79/80 = 98.8% | 45/46 = 97.8% |
| subject | 63/80 = 78.8% | 42/46 = 91.3% |
| exposure_status | 75/80 = 93.8% | 41/46 = 89.1% |
| doses[0] | 27/27 = 100% | 6/6 = 100% |
| 8 other paths (13 rows) | 100% | 100% |

The 23 failures sit in 8 distinct window texts; one text contributes 14. `subject`'s 78.8% is largely that one duplicated post. Pass criterion is whether the paraphrase supports the field, not whether it is a copy.

**(b) Blind speech-act — 5/12 on the three values**

Overall 71/80 = 88.8% is an artifact: **66 of the 71 are the `other`/`other` cell.** Report the three-way block, not the headline.

| model ↓ / labeler → | food_list | avoidance | culinary | other |
|---|---|---|---|---|
| **food_list** | 1 | 2 | 1 | 0 |
| **avoidance** | 1 | 2 | 0 | 1 |
| **culinary** | 0 | 1 | 2 | 1 |
| **other** | 1 | 0 | 1 | 66 |

Model assigned one of the three 12 times; labeler 12 times; they agree on 5. n=12 is too thin to declare material confusion or to clear it. Direction note: 2 rows are model `food_list` → labeler `avoidance`, the opposite of the §4.4 302-vs-10–37 overcount.

---

## 7. Stage 5b — repeat pass

Same `run_id`, separate `--output-db` `data/probes/garlic_pharmacology_repeat.db`, cold cache, temperature 0. `--limit 50`. User directed stop without finishing the last unit. Do not resume the leftover `running` row unless asked.

| | |
|---|---|
| attempted | 50 (all 50 were `complete` on Stage 5) |
| complete / failed / left running | **38 / 11 / 1** |
| claims | 69 (57 included, 12 excluded) |
| complete units with zero claims | 1 / 38 |
| cache hits | 0 |
| `billing_uncertain` | 0 |
| attempts | 38 accepted, 75 `validation_failed`, 0 `transport_failed` |
| realized cost (113 attempts with usage) | **$0.1080** (accepted $0.0414, validation_failed $0.0667) |
| tokens | 0.44M in / 0.30M out; reasoning 0.26M |

The leftover `running` unit has two `validation_failed` attempts and was on attempt 3/3 when stopped. Validation heads: not-grounded 63, `source_type` 7, use-payload 2, source not in unit 2, ID/type 1.

**Agreement vs Stage 5 (38 units complete in both).** Join claims greedily on `source_window_id` + `speech_act`, then same window. **68** pairs; 0 Stage 5 claims unmatched; 1 extra 5b claim. 37/38 units have the same claim count. 26/38 units have the same set of speech acts.

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

Temperature-0 residual nondeterminism. Completers look more stable than the first-pass JSON on field-set and shared values. `speech_act` still moves on 14/68 paired claims. The three-way `food_list` / `avoidance` / `culinary` block on this sample is too small to headline (a few swaps, including one `food_list`↔`avoidance` each way).

---

## 8. Units that exhausted all attempts (6)

Last-attempt error categories:

| count | category |
|---|---|
| 3 | provider returned null content |
| 1 | `source_type` must be post or comment |
| 1 | extra inputs not permitted (nested `duration`) |
| 1 | quote not grounded in the cited source window |

These six were packed ~5.7–5.9k-character units. A resume with `--run-id` would re-dispatch them without re-billing the 1,990 accepted responses. That is additional paid work and is **not** part of this stage.

---

## 9. Findings

**a. The prompt and the 0.5 grounding floor disagree about what a short paraphrase looks like.** Not-grounded is 3,330 of 3,994 validation failures. The model writes taxonomy glosses (`author`, `personal`, `listed`, …) for the three required quotes; retries eventually copy source tokens. Do not lower the floor. Do not add a contiguous/verbatim companion. Validation retries are 65% of realized spend.

**b. GATE 4 (b) does not clear the load-bearing `food_list` / `avoidance` / `culinary` distinction.** 5/12 on the three-way block. Avoidance 109 / 1,927 (5.7%) is usable as a count and provisional as a contrast. Food-list and culinary classification *is* the belief study.

**c. Stage 5b is a floor on instability, not a re-elicitation.** Temperature 0; 12/50 units did not complete. On completers, field-set and shared-value agreement beat the first-pass JSON prior. `speech_act` still moves on 14/68 pairs.

**d. Use-payload leakage onto food-list / avoidance / culinary is zero** in stored claims. The validator held. Duplicate-event rejections are zero.

**e. This run is not asking whether garlic works.** Share of extractable reports only. DESIGN §8 (quote-free loader, notebooks, preparation mix, polarity, mechanisms, adverse-event shares, JSON-vs-probe) remains out of scope until someone takes that phase.
