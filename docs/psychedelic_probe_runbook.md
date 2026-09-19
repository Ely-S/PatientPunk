# Runbook — psychedelic pharmacology probe (second-pass pipeline)

**Branch:** `pr/3-psychedelic-probe`. **Audience:** an agent executing this end to end.

This pipeline re-extracts drug/dose/effect/adverse-event data from raw Reddit
text for patients already known to report psilocybin, ketamine, or LSD. It
replaces `studies/psychedelics/extract_pharmacology.py`, which stays untouched.

Read `studies/psychedelics/_handoff.txt` §2 before interpreting any output. The
research and privacy constraints there govern this work: no efficacy or
incidence claims, silence is never "no adverse events", and quote-bearing
artifacts never leave the private database.

## Ground rules

1. **Two commands spend money: `probes run` and nothing else.** `plan` never
   constructs an LLM client. If you are unsure whether a step is paid, it is
   not, unless it contains `--confirm-paid-run`.
2. **Stop at every GATE.** Gates exist because the cost checkpoint is the
   user's decision, not yours. Do not proceed past one on your own judgment.
3. **Never commit anything under `data/`.** The probe database holds raw source
   text, verbatim quotes, and hashed author IDs. `data/probes/`, `*.db`,
   `*.db-wal`, and `*.db-shm` are gitignored; do not defeat that with `git add -f`.
4. **Never paste source text, quotes, or author hashes into a report, commit
   message, or PR comment.** Aggregate counts only.
5. If a command fails, stop and report the error verbatim. Do not retry with
   different flags to make it pass.

---

## Stage 0 — Preconditions

```bash
cd /Users/eli/Desktop/PatientPunk
git checkout pr/3-psychedelic-probe
uv run python -m compileall -q probes && uv run pytest tests -q
```

Expect the test suite to pass. Then confirm the two input files exist:

```bash
ls -la reddit_2026-06-13.db          # raw Reddit FTS corpus, read-only
ls -la data/posts.db output/records.csv   # inputs to Stage 1
```

`reddit_2026-06-13.db` must contain `comments`, `posts`, `comments_fts`,
`posts_fts`. It is opened read-only and is never written.

---

## Stage 1 — Build the cohort database

The probe resolves its cohort with `probes/psychedelic_pharmacology/cohort.sql`,
which reads `treatment_reports JOIN treatment`. That lives in `patientpunk.db`,
which is gitignored and **not** in a fresh checkout.

```bash
uv run python load_db.py
```

Defaults: `--posts-db data/posts.db --records output/records.csv --db patientpunk.db`.
`--demographics output/demographics_deductive.csv` is optional and is currently
absent; that is fine.

### GATE 1 — the cohort must be real

This is the step most likely to silently produce a useless run. Verify:

```bash
uv run python -c "
import sqlite3
from collections import Counter
c = sqlite3.connect('file:patientpunk.db?mode=ro', uri=True)
rows = list(c.execute(open('probes/psychedelic_pharmacology/cohort.sql').read()))
print('patient-drug pairs:', len(rows))
print('distinct patients:', len({r[0] for r in rows}))
print(dict(Counter(r[1] for r in rows)))
"
```

**Expected**, from the legacy pipeline's asserted cohort:

| | pairs |
|---|---|
| psilocybin | 538 |
| ketamine | 525 |
| lsd | 94 |
| **total** | **1,157** (1,041 distinct patients) |

**STOP and report if you get 0, or anything far below 1,157.** The repository
ships a 25-row `data/posts.db` sample; building from it yields an empty
cohort. The real corpus lives in `PatientPunk_data/` + S3 — see the note in
`.gitignore`. Do not proceed with a truncated cohort: the run would look
successful and mean nothing.

**Also report, without stopping, if the total is close to but not exactly
1,157.** The legacy pipeline derived its cohort from
`data/full_corpus_2026-07-31/records_covidlonghaulers_v2.json`, while this one
derives it from SQL. These are two derivations of the same corpus and have
never been reconciled. A small discrepancy is a finding the user needs, not an
error to fix on your own.

---

## Stage 2 — Plan (free)

Planning resolves the cohort, retrieves evidence windows from the FTS corpus,
and assembles bounded units. It makes no provider call.

```bash
uv run python -m probes plan psychedelic_pharmacology \
  --cohort-db patientpunk.db \
  --source-db reddit_2026-06-13.db \
  --model deepseek/deepseek-v4-flash \
  --temperature 0 \
  --max-tokens 32768
```

Output: `planned run=<run_id> members=<n> units=<n> reused=False`

Written to `data/probes/psychedelic_pharmacology.db` (repo-root anchored,
gitignored). Override with `--output-db`.

**Every setting in the command is part of the run identity.** Change the model,
temperature, max-tokens, or evidence config and you get a different `run_id`
and a different database state. Re-running `plan` with identical inputs is
safe and idempotent — it prints `reused=True` and the same `run_id`.

### On `--reasoning-effort`

The legacy run was pinned to reasoning effort `max`. **This engine refuses
`--reasoning-effort` on `--provider openrouter` or `anthropic`:**

```
ValueError: provider 'openrouter' cannot send ['reasoning_effort']; these
change the answer and must not be dropped silently
```

That is deliberate — the legacy adapter silently dropped the parameter, buying
a "max effort" run that ran with no reasoning. To send it, use the
OpenAI-compatible surface, which OpenRouter serves:

```bash
  --provider openai --base-url https://openrouter.ai/api --reasoning-effort max
```

**GATE 2 — ask the user which configuration they want** before planning the
real run. Reasoning effort materially changes both answers and cost (legacy
estimate: ~$0.40 without, ~$2.40 with, plausibly $1.18–$11.26). It also changes
`run_id`, so switching later discards planned state.

---

## Stage 3 — Inspect the plan before paying

```bash
uv run python -c "
import sqlite3
c = sqlite3.connect('file:data/probes/psychedelic_pharmacology.db?mode=ro', uri=True)
q = lambda s: c.execute(s).fetchone()[0]
print('members      ', q('SELECT COUNT(*) FROM cohort_member'))
print('units        ', q('SELECT COUNT(*) FROM unit'))
print('windows      ', q('SELECT COUNT(*) FROM source_window'))
print('total chars  ', q('SELECT SUM(character_count) FROM unit'))
print('largest unit ', q('SELECT MAX(character_count) FROM unit'))
print('by status    ', dict(c.execute('SELECT status, COUNT(*) FROM unit GROUP BY 1')))
"
```

Legacy reference for the full cohort: 4,180 source windows, ~1,207 units,
2,182,844 characters, largest unit 5,990 chars. Units are capped by
`--max-chars` (default 6,000); an oversized window is split, never truncated.

**Report these numbers to the user with a cost estimate before Stage 4.**
Estimate from total characters (roughly chars/4 input tokens, plus output),
using the model's current price. Do not guess the price — read it from the
provider.

### GATE 3 — paid work requires explicit approval

Report the counts and estimate, then **stop**. Do not run Stage 4 until the
user approves. Approval for the pilot is not approval for the full run.

---

## Stage 4 — Pilot

Run a small slice first. `--limit` caps units dispatched this invocation.

```bash
uv run python -m probes run psychedelic_pharmacology \
  --cohort-db patientpunk.db \
  --source-db reddit_2026-06-13.db \
  --model deepseek/deepseek-v4-flash \
  --temperature 0 \
  --max-tokens 32768 \
  --limit 25 \
  --confirm-paid-run
```

Output: `run=<run_id> attempted=<n> completed=<n> failed=<n> cache_hits=<n>`

Exit code is 1 if any unit failed. Without `--confirm-paid-run` the command
raises `PermissionError` before building a client.

What happens per unit: the prompt is built, the request cache is checked once,
the response is **persisted before any validation**, then JSON parsing and
claim validation run. A validation failure feeds its error back into the next
attempt as feedback, up to 3 attempts. A unit that exhausts them is marked
`failed`; the run continues.

### Review the pilot

```bash
uv run python -c "
import sqlite3
c = sqlite3.connect('file:data/probes/psychedelic_pharmacology.db?mode=ro', uri=True)
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

Things that matter here:

- **`validation_failed` attempts carrying `not grounded in the cited source
  window`.** This is the quote-grounding floor: a quote must share at least
  half its words with the window it cites. A handful is healthy — it is the
  guard working. A large share means the prompt and the guard disagree, and
  that is a finding to report, not a threshold to lower.
- **`billing_uncertain` attempts** are transport failures where usage could not
  be read. They may still have been billed.
- **Units `complete` with zero claims** are legitimate when a window only
  mentions a drug in passing, but a run that is mostly empty is suspicious.

### GATE 4 — human quote grounding

The grounding floor is a mechanical guard, not the acceptance gate. Before the
full run, a human must read a sample of claims against their source windows and
confirm each quote actually supports its field. **This requires reading private
quote-bearing data. Do that in a local, uncommitted scratch file; never write
it to the repo, a PR, or a report.**

Report the sample size and pass rate as aggregate numbers only. Stop and wait
for the user's approval of the full run.

---

## Stage 5 — Full run

Same command with `--limit` removed. Units already `complete` are skipped, so
this resumes rather than repeating the pilot.

```bash
uv run python -m probes run psychedelic_pharmacology \
  --cohort-db patientpunk.db \
  --source-db reddit_2026-06-13.db \
  --model deepseek/deepseek-v4-flash \
  --temperature 0 \
  --max-tokens 32768 \
  --confirm-paid-run
```

To resume after an interruption without re-resolving the cohort or re-reading
the source corpus:

```bash
uv run python -m probes run psychedelic_pharmacology \
  --run-id <run_id> --confirm-paid-run
```

Resume is a query over unit status. A crash mid-run loses nothing already
persisted: every response is written before validation, and accepted responses
are reused from the attempt ledger rather than re-billed.

---

## Stage 6 — Report

Produce, from the probe database only:

- cohort pairs resolved, units planned, units complete / failed;
- claims total, and the included vs excluded split (`included=0` rows are
  denominator data — reports the model classified as not-self or not-actual-use,
  kept deliberately so the denominator is inspectable);
- attempts by status, cache hits, tokens, and cost, with any
  `billing_uncertain` attempts named as uncertain rather than folded into a
  total;
- units that failed all 3 attempts, with their error text summarized.

Every number is an aggregate. No quotes, no source text, no author hashes.

State the denominator on any adverse-event figure, and use the schema's own
distinction: `reported` / `explicit_none` / `not_stated`. Silence is not
absence.

---

## Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| `cohort pairs: 0` | `patientpunk.db` built from the 25-row sample `data/posts.db` | Stop. Get the real corpus. |
| `provider 'openrouter' cannot send ['reasoning_effort']` | Engine refuses settings a provider would drop | Use `--provider openai --base-url https://openrouter.ai/api`, or drop the flag. |
| `PermissionError: run requires --confirm-paid-run` | Working as designed | Only add the flag once the user has approved. |
| `plan` prints `reused=True` | Identical run identity already planned | Not an error. Nothing was re-done. |
| `run_id` changed unexpectedly | A config, cohort, or source-corpus change | Diff your flags against the prior invocation. Identity covers all of them. |
| `KeyError: no unit ... in run ...` | Status update against an unknown key | Real bug. Stop and report. |
| Many `not grounded` failures | Prompt and grounding guard disagree | Report as a finding. Do not lower the threshold. |

## What this pipeline does not do

There is no `finalize` or reporting command — those exist only in the legacy
extractor. Stage 6 is manual SQL. There is no notebook integration; do not
modify `psychedelics_analysis.ipynb` or `build_nb.py`. Provider calls are
sequential, so a large run takes a while; that is current behavior, not a hang.
