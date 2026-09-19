# Runbook — garlic beliefs and use probe

**Audience:** an agent executing this end to end. **Design:** [`studies/garlic/DESIGN.md`](../studies/garlic/DESIGN.md).

This pipeline extracts garlic *beliefs* (food lists, mechanism talk, warnings) and, separately, self-reported intervention *use* (preparation, dose, effects, adverse events) from the long-COVID / ME-CFS Reddit corpus. It is not a psychedelic-schema clone: `included` is analysis membership and gates nothing; `use_payload_allowed` is the only gate on doses / effects / adverse events.

Read [`studies/psychedelics/_handoff.txt`](../studies/psychedelics/_handoff.txt) §2 and DESIGN.md §2 before interpreting any output. Additional garlic rules: do not treat garlic bread as use; a high-histamine food list is not personal avoidance and not a negative efficacy outcome; “I avoid garlic” is not “garlic worsened my long COVID.”

## Ground rules

1. **Two commands spend money: `probes run` and nothing else.** `plan` never constructs an LLM client. If you are unsure whether a step is paid, it is not, unless it contains `--confirm-paid-run`.
2. **Stop at every GATE.** Gates exist because the cost checkpoint is the user's decision, not yours. Do not proceed past one on your own judgment. Approval for the pilot is not approval for the full run.
3. **Never commit anything under `data/`.** The probe database holds raw source text, verbatim quotes, and hashed author IDs. `data/probes/`, `*.db`, `*.db-wal`, and `*.db-shm` are gitignored; do not defeat that with `git add -f`.
4. **Never paste source text, quotes, or author hashes into a report, commit message, or PR comment.** Aggregate counts only.
5. If a command fails, stop and report the error verbatim. Do not retry with different flags to make it pass.
6. Do not read `patientpunk.db` / `treatment_reports` for this cohort. That path plans a successful empty run.

---

## Stage 0 — Preconditions

```bash
cd /Users/eli/Desktop/PatientPunk
uv run python -m compileall -q probes && uv run pytest tests/test_garlic_pharmacology.py tests/test_probes_workers.py -q
```

Expect the tests to pass. Then confirm the source corpus exists and has FTS:

```bash
ls -la reddit_2026-06-13.db
ls -la data/full_corpus_2026-07-31/records_covidlonghaulers_v2.json
uv run python -c "
import sqlite3
c = sqlite3.connect('file:reddit_2026-06-13.db?mode=ro', uri=True)
print(sorted(r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")))
"
```

`reddit_2026-06-13.db` must contain `comments`, `posts`, `comments_fts`, `posts_fts`. It is opened read-only and is never written.

---

## Stage 1 — Build the cohort database

```bash
uv run python scripts/build_garlic_cohort_db.py \
  --source-db reddit_2026-06-13.db \
  --records-json data/full_corpus_2026-07-31/records_covidlonghaulers_v2.json \
  --out garlic_cohort.db
```

The builder imports `TARGETS` / `matching_author_hashes` / `author_hash` from `probes/garlic_pharmacology/evidence.py`. It does not read `patientpunk.db`.

### GATE 1 — independent of FTS-versus-SQL agreement

The script prints aggregates only (no hashes, no source text). Expected, from DESIGN.md §4.1:

| | count |
|---|---|
| FTS non-bot authors | **1,928** |
| JSON garlic any-field | **502** |
| JSON ∩ FTS | **500 / 502** |
| FTS authors in the 69k JSON | **1,815** |
| FTS authors with no JSON record | **113** (keep them) |
| JSON-only rows | **2**, with **zero** garlic-family tokens in source |

**STOP if** the FTS cohort is empty, JSON ∩ FTS is 0 (hasher bug), a JSON-only row has garlic-family tokens in source (join miss, not a hallucination), or the FTS author count is far from 1,928.

**Do not chase the two JSON-only rows into the cohort.** Report them as extractor hallucinations.

A small discrepancy on the JSON overlap is a finding to report, not an error to fix by widening the FTS query.

---

## Stage 2 — Plan (free)

GATE 2 is settled by the design. Do not improvise a different model or effort: both are in `RunConfig` and change `run_id`.

- Model: `deepseek/deepseek-v4-flash`
- Reasoning effort: `medium`
- Provider: `--provider openai --base-url https://openrouter.ai/api` (the engine refuses `--reasoning-effort` on `--provider openrouter`)
- Temperature: 0
- `--max-tokens`: 32768

```bash
uv run python -m probes plan garlic_pharmacology \
  --cohort-db garlic_cohort.db \
  --source-db reddit_2026-06-13.db \
  --provider openai --base-url https://openrouter.ai/api \
  --model deepseek/deepseek-v4-flash \
  --temperature 0 \
  --max-tokens 32768 \
  --reasoning-effort medium
```

Output: `planned run=<run_id> members=<n> units=<n> reused=False`

Written to `data/probes/garlic_pharmacology.db` (repo-root anchored, gitignored). Override with `--output-db`.

Re-running `plan` with identical inputs is safe and idempotent — it prints `reused=True` and the same `run_id`.

**If you need a different model or effort, stop and ask.** Changing either means replanning.

---

## Stage 3 — Inspect the plan before paying

```bash
uv run python -c "
import sqlite3
c = sqlite3.connect('file:data/probes/garlic_pharmacology.db?mode=ro', uri=True)
q = lambda s: c.execute(s).fetchone()[0]
print('members      ', q('SELECT COUNT(*) FROM cohort_member'))
print('units        ', q('SELECT COUNT(*) FROM unit'))
print('windows      ', q('SELECT COUNT(*) FROM source_window'))
print('total chars  ', q('SELECT SUM(character_count) FROM unit'))
print('largest unit ', q('SELECT MAX(character_count) FROM unit'))
print('by status    ', dict(c.execute('SELECT status, COUNT(*) FROM unit GROUP BY 1')))
"
```

Design reference: ~1,928 members, ~4,022 windows, ~2,015 units at 6,000-char packing, ~2.19M window chars. A large share of units will be food-list or culinary classification. That is the belief study, not waste.

Confirm the HTTP read timeout is still 90s (not a run flag; not in `run_id`):

```bash
uv run python -c "
from patientpunk._utils import TIMEOUT
print(TIMEOUT)
"
```

Expect `connect=10, read=90, write=90, pool=60`. Record the value for the Stage 6 report.

### GATE 3 — paid work requires explicit approval

Report **volume** (members, units, windows, characters) and the timeout constant, then **stop**. Do not quote a live price; GATE 3 is not a cost gate. Do not run Stage 4 until the user approves. Approval for the pilot is not approval for the full run.

---

## Stage 4 — Pilot

```bash
uv run python -m probes run garlic_pharmacology \
  --cohort-db garlic_cohort.db \
  --source-db reddit_2026-06-13.db \
  --provider openai --base-url https://openrouter.ai/api \
  --model deepseek/deepseek-v4-flash \
  --temperature 0 \
  --max-tokens 32768 \
  --reasoning-effort medium \
  --limit 25 \
  --confirm-paid-run
```

Output: `run=<run_id> attempted=<n> completed=<n> failed=<n> cache_hits=<n>`

Exit code is 1 if any unit failed. Without `--confirm-paid-run` the command raises `PermissionError` before building a client.

```bash
uv run python -c "
import sqlite3
c = sqlite3.connect('file:data/probes/garlic_pharmacology.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
print('unit status  ', dict(c.execute('SELECT status, COUNT(*) FROM unit GROUP BY 1')))
print('attempts     ', dict(c.execute('SELECT status, COUNT(*) FROM attempt GROUP BY 1')))
print('claims       ', c.execute('SELECT COUNT(*) FROM claim').fetchone()[0])
print('included     ', dict(c.execute('SELECT included, COUNT(*) FROM claim GROUP BY 1')))
print('billing unsure', c.execute('SELECT COUNT(*) FROM attempt WHERE billing_uncertain').fetchone()[0])
for r in c.execute('SELECT unit_key, attempt_no, error FROM attempt WHERE status=\"validation_failed\" LIMIT 5'):
    print('  fail:', r['unit_key'][:12], r['attempt_no'], (r['error'] or '')[:120])
"
```

Also check speech-act mix on the pilot (aggregates from `values_json`, still no quotes):

```bash
uv run python -c "
import json, sqlite3
from collections import Counter
c = sqlite3.connect('file:data/probes/garlic_pharmacology.db?mode=ro', uri=True)
acts = Counter()
for (raw,) in c.execute('SELECT values_json FROM claim'):
    acts[json.loads(raw).get('speech_act', '?')] += 1
print(dict(acts))
"
```

Things that matter here:

- **`validation_failed` attempts carrying `not grounded in the cited source window`.** A handful is healthy. A large share means the prompt and the guard disagree — report it; do not lower the 0.5 floor. Quotes are short paraphrases; do not add a verbatim/contiguous companion.
- **Duplicate-event rejections.** Two distinct food-list mentions in one unit can serialize identically and reject the unit. If this shows up in the pilot, stop and report before Stage 5.
- **Units `complete` with zero claims** are legitimate when a window only names garlic in passing. A run that is mostly empty is suspicious.
- **`billing_uncertain` attempts** may still have been billed.

### GATE 4 — two checks on the same private scratch sample

Do this in a local, uncommitted scratch file. Never write quote-bearing worksheets to the repo, a PR, or a report. Report sample size, pass rate, and the confusion matrix only.

Use the **same sample of claim/window ids**, two views:

- **Grounding sheet** may include model fields, quotes, and windows.
- **Blind sheet** is window text only — no `speech_act`, no `values`, no model output. Join after labeling.

**(a) Human paraphrase grounding.** A human reads the grounding sheet and confirms each short paraphrase faithfully supports its field given the window. Verbatim copying is not required and is not the pass criterion. The psychedelic run bypassed this; do not bypass it here.

**(b) Blind speech-act agreement** on `food_list` / `avoidance` / `culinary`. A human labels the blind sheet **without seeing model output**. Then join and report the confusion matrix on those three values. A prior pass overcounted avoidance 302 against a true 10–37; grounding alone does not cover this study's load-bearing distinction. Material confusion is a prompt fix before Stage 5, not a §8 caveat.

Stop and wait for the user's approval of the full run. Approval of the full run is not approval of Stage 5b.

---

## Stage 5 — Full run

Same command with `--limit` removed. Units already `complete` are skipped, so this resumes rather than repeating the pilot. `--workers` is not in `RunConfig` and must not move `run_id`.

**Unless GATE 4 forced a prompt or validator fix.** `spec_hash` hashes `claim.py`, `evidence.py`, and `cohort.sql` ([`probes/engine.py:77`](../probes/engine.py)), so editing the prompt changes `run_id`. The pilot's 25 units then belong to the previous run and are neither skipped nor reusable: re-plan, re-pilot at `--limit 25`, and re-check GATE 4 against the new prompt before paying for the full run. Do not merge claims across the two `run_id`s.

```bash
uv run python -m probes run garlic_pharmacology \
  --cohort-db garlic_cohort.db \
  --source-db reddit_2026-06-13.db \
  --provider openai --base-url https://openrouter.ai/api \
  --model deepseek/deepseek-v4-flash \
  --temperature 0 \
  --max-tokens 32768 \
  --reasoning-effort medium \
  --workers 10 \
  --progress \
  --confirm-paid-run
```

`--progress` draws a unit counter on stderr (`[####......] 42/300 (14%) failed=1
38/min elapsed 1:07 eta 6:48`), redrawn in place on a terminal and printed one
line per unit when stderr is redirected to a log. It leaves the stdout summary
line alone, so `... --progress > run.log` still captures only the result.

To resume after an interruption without re-resolving the cohort:

```bash
uv run python -m probes run garlic_pharmacology \
  --run-id <run_id> --confirm-paid-run --workers 10 --progress
```

---

## Stage 5b — Repeat pass

Stage 5b is additional paid work (~2.5% of the full run): a cold-cache re-run of ~50 units into a separate database. GATE 4 approval of the full run does **not** cover 5b. **Stop and wait** until the user confirms.

Re-run ~50 units against a **separate `--output-db`**. Identical inputs give the same `run_id`; a fresh database yields a cold cache and new provider calls. Compare field sets and values against the full run. Report agreement in Stage 6.

At temperature 0 this measures residual provider nondeterminism, a floor on instability rather than a full re-elicitation. Say so when reporting it.

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
  --confirm-paid-run
```

---

## Stage 6 — Report

Produce, from the probe database only, a quote-free report in `docs/` or `studies/garlic/`:

- cohort members resolved, units planned, units complete / failed;
- claims total, included vs excluded (`included=0` is the inspectable denominator — culinary, gossip, planned);
- speech-act mix (claim-level counts, plus a note that headline analysis is reporter-level);
- attempts by status, cache hits, tokens, and **realized** cost from `usage_json.provider_cost`, with `billing_uncertain` named as uncertain;
- HTTP timeout constant recorded at GATE 3;
- Stage 5b field-set and value agreement;
- GATE 4 sample size, quote-grounding pass rate, and the `food_list` / `avoidance` / `culinary` confusion matrix.

Every number is an aggregate. No quotes, no source text, no author hashes.

Do not analyse dose-response. Collapse preparation bins with reporter n < 30. If personal-avoidance n < 30, one sentence, no contrast tests. State the denominator on every figure.

---

## Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| `no such table: garlic_cohort` | `--cohort-db` pointed at `patientpunk.db` | Stop. Use `garlic_cohort.db` from Stage 1. |
| `cohort pairs: 0` / empty FTS | Wrong source DB, or hasher/query drift | Stop. Confirm `TARGETS` and `author_hash` in `evidence.py`. |
| GATE 1 JSON ∩ FTS is 0 | Hasher does not match the JSON `author_hash` | Stop. Do not proceed. |
| `provider 'openrouter' cannot send ['reasoning_effort']` | Engine refuses settings a provider would drop | Use `--provider openai --base-url https://openrouter.ai/api`. |
| `PermissionError: run requires --confirm-paid-run` | Working as designed | Only add the flag once the user has approved. |
| `plan` prints `reused=True` | Identical run identity already planned | Not an error. |
| `run_id` changed unexpectedly | A config, cohort, or source-corpus change | Diff your flags against the prior invocation. |
| Many `not grounded` failures | Prompt and grounding guard disagree | Report as a finding. Do not lower the threshold. |
| Many `duplicate event` failures | Identical food-list serializations in one unit | Report before Stage 5. Do not weaken the fingerprint. |

## What this pipeline does not do

There is no `finalize` command. Stage 6 is manual SQL. Analysis notebooks are out of scope until a validated run exists. Do not write quote-bearing review worksheets into git.
