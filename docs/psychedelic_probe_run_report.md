# Stage 6 report — psychedelic pharmacology probe

**Run ID:** `710567555e22b68c025d8ceb1c3373564d7f9b01dcc5fe94b02b7c3209ecbc05`
**Date:** 2026-08-09 · **Branch:** `pr/3-psychedelic-probe`
**Model:** `deepseek/deepseek-v4-flash` via OpenRouter (OpenAI-compatible surface)
**Config:** reasoning effort `high`, temperature 0, max_tokens 32768

All figures below are aggregates drawn from the probe database only. No quotes,
source text, or author hashes appear here or were used to produce it.

---

## 1. Read these limitations before using any number

**The cohort was imported, not independently derived.** GATE 1 returns exactly
the runbook's expected table (1,157 pairs / 1,041 patients / psilocybin 538,
ketamine 525, lsd 94). **This agreement is by construction and confirms
nothing.** The drug-sentiment pipeline that `cohort.sql` reads was never run on
the full corpus, so every database on disk yields ~0 psychedelic pairs. The
authoritative cohort existed only as legacy JSON and was copied into
`cohort_legacy.db` by `scripts/build_legacy_cohort_db.py`. The runbook's
"do the two derivations agree" check **remains unanswered.**

**GATE 4 was bypassed, not satisfied.** No human has read any claim against its
source window to confirm the quote actually supports the field. The grounding
floor below is a mechanical guard, not an acceptance gate. These numbers should
not be used for anything until that sample is done.

**Unit count differs from the legacy reference by one:** 1,206 units here vs
~1,207 legacy, and largest unit 5,998 chars vs 5,990. Source windows (4,180) and
total characters (2,182,844) match exactly. The one-unit delta is unexplained.

**Research constraints carried from `_handoff.txt` §2**, which govern any use of
this output: self-selected Reddit reporting cohort, not a clinical cohort; no
efficacy, causal, incidence, or dose-response claims; silence is never
"no adverse events."

---

## 2. Cohort and units

| | |
|---|---|
| cohort pairs resolved | 1,157 |
| source windows | 4,180 |
| units planned | 1,206 |
| units complete | **1,192 (98.8%)** |
| units failed (exhausted attempts) | **14 (1.2%)** |

## 3. Claims

| | |
|---|---|
| claims total | 3,982 |
| included (`included=1`) | 2,921 (73.4%) |
| excluded (`included=0`) | 1,061 (26.6%) |

`included=0` rows are retained deliberately as denominator data — reports the
model classified as not-self or not-actual-use. They are not errors.

All 2,921 included claims carry `subject=self` and `exposure_status=actual_use`
at 100%, which is definitional: those two labels are what qualifies a claim as
included. This is not evidence about the corpus.

## 4. Attempts, cache, and cost

| status | count |
|---|---|
| accepted | 1,192 |
| validation_failed | 179 |
| transport_failed | 68 |
| cache hits | 0 |
| **billing_uncertain** | **65** |

Attempts per unit: 1,048 units on the first attempt, 105 on two, 37 on three,
12 on four, 2 on five, 2 on six. Counts above three reflect attempts accumulated
across separate resumed invocations, not a widened per-invocation ladder (which
remains 3).

**Cost — accepted attempts with readable usage (n=1,192):**

| | |
|---|---|
| input tokens | 3,835,711 |
| output tokens | 5,120,427 |
| input cost | $0.54 |
| output cost | $1.43 |
| **total** | **$1.97** |

Priced at $0.14/M input, $0.28/M output, read live from the OpenRouter API.

**The 65 `billing_uncertain` attempts are excluded from that total and may also
have been billed.** They are transport failures where usage could not be read.
Realized cost also varies because OpenRouter routing was not pinned to a
provider; endpoint prices for this model span roughly a 3x band.

## 5. Adverse events

**Denominator: included claims per drug. These are shares of extractable
reports, never incidence.**

| drug | included claims | not_stated | reported | explicit_none |
|---|---|---|---|---|
| ketamine | 1,588 | 1,388 (87%) | 181 (11%) | 19 (1%) |
| psilocybin | 1,172 | 1,020 (87%) | 127 (11%) | 25 (2%) |
| lsd | 161 | 131 (81%) | 29 (18%) | 1 (1%) |

`not_stated` dominates at ~87%. **This is silence, not absence.** Only
`explicit_none` — 45 claims across all three drugs — records an author actually
stating they had no adverse effects.

Events per claim, among `reported` claims only:

| drug | reported | distribution (events: claims) |
|---|---|---|
| ketamine | 181 | 1:140, 2:26, 3:9, 4:3, 5:1, 6:1, 8:1 |
| psilocybin | 127 | 1:99, 2:13, 3:8, 4:3, 5:2, 7:2 |
| lsd | 29 | 1:21, 2:8 |

## 6. Findings

**a. The prompt and the schema disagree about where pharmacology data may
attach.** The single largest validation-failure category is
`doses/effects/adverse_events require subject=self and exposure_status=actual_use`
— the model attaching dose, effect, or adverse-event data to events it had
itself labelled not-self or not-actual-use. Per the runbook this is reported as
a finding, not resolved by relaxing the constraint.

**b. Quote grounding is healthy.** `not grounded in the cited source window`
accounts for only a small minority of the 179 validation failures. That is the
guard working correctly rather than the prompt and guard disagreeing.

**c. Source-attribution errors are the leading cause of permanent failure.**
`source does not belong to unit` / `source ID/type does not match window`
dominate the 14 exhausted units — the model citing a window outside the unit it
was given.

**d. A 60-second HTTP read timeout was silently discarding the hardest units.**
`_utils.py` set `read=60`, but this configuration averages 3,673 output tokens
per unit at reasoning effort `high`. Long-reasoning requests could not return in
time and were killed client-side. This produced 64 `billing_uncertain` failures
and, more seriously, **a survivorship bias against units the model thought
longest about** — throughput had collapsed to 2.2 units/min with ~5% of units
failing permanently. Raised to 90s and concurrency raised to 30 workers on the
user's instruction; throughput recovered to ~28 units/min and only **4 further
transport failures occurred across the remaining ~935 units**. All 14 units that
had permanently failed under the 60s timeout succeeded on retry, confirming the
timeout as the cause rather than bad data.

Residual risk: at 3,673 average output tokens, 90s still implies sustaining
~41 tok/s, so the extreme tail can still time out. The rate is now rare but not
zero.

## 7. Units that exhausted all attempts (14)

Error categories, counted across all attempts belonging to failed units:

| count | category |
|---|---|
| 8 | `source does not belong to unit` (indices 3, 4, 5, 14) |
| 3 | provider returned null content |
| 2 | quote not grounded in cited source window |
| 2 | provider response did not contain valid JSON |
| 1 | `ExtractionEnvelope` validation error |
| 1 | APIConnectionError |
| 1 | APITimeoutError |

These 14 units are retryable: a resume with `--run-id` would re-dispatch them
without re-billing the 1,192 accepted responses. Estimated marginal cost ~$0.02.

---

## Reproduction

```bash
uv run python -m probes run psychedelic_pharmacology \
  --run-id 710567555e22b68c025d8ceb1c3373564d7f9b01dcc5fe94b02b7c3209ecbc05 \
  --workers 30 --confirm-paid-run
```

`--workers` is deliberately excluded from `RunConfig`: it changes how fast units
are dispatched, never what is sent, so it must not move `run_id`.
