# Pipeline findings — full-corpus run, 2026-07-31

Everything that broke, nearly broke, or cost more than it should have during the
2-week rehearsal and the 69,172-patient full-corpus run. Every item was verified
against the code or the run output; nothing here is inferred.

Run artifacts: `s3://patientpunk/full_corpus_2026-07-31/`. Method logs:
`output_2wk_deepseek/RUN_NOTES.md` and `output_full_reddit2026/RUN_NOTES.md`.

---

## Fixed during this run

| # | what | where | commit |
|---|---|---|---|
| 1 | Every patient loaded into SQLite was stamped `"covidlonghaulers"` with no override | `patientpunk/db.py:157,275` | `e4699dc` |
| 2 | Classify picked its community with `DISTINCT … LIMIT 1`, no `ORDER BY` — arbitrary on a mixed corpus | `src/pipeline/classify.py:164` | `e4699dc` |
| 3 | Neither Arctic Shift scraper emitted a per-post `subreddit`, so PR #109's provenance column came out empty | `Scrapers/transform_arctic_shift.py`, `scrape_corpus.py` | `e4699dc` |
| 4 | `MAX_TEXT_CHARS` was a module constant; comparing two values meant editing code between runs | `patientpunk/llm_extract.py:99` | `04376b1` |
| 5 | No written rule against reading `.env`; five live keys reached a chat transcript | `AGENTS.md`, `CORPUS_RUNBOOK.md` | `6583583` |

All three of 1–3 are harmless on a single-community run and wrong on a
fifteen-community one, which is why they survived until now.

---

## Confirmed bugs, still open

### A. A blank `.env` value shadows a real one
`patientpunk/_utils.py` `load_env()` — the merge filters `None` but not `""`, so
`OPENROUTER_API_KEY=` in `variable_extraction/.env` overwrote the real key from the
repo root. Detection then saw no key and silently fell through to
`provider="anthropic"`, which does not serve `deepseek/*`; every call 404'd.

Cost $0 but it killed a run, and nothing in the output said a key had been shadowed —
the only clue was `provider=anthropic` in the banner. Fix: skip empty values at merge
time (`if v is not None and v.strip()`), and warn when a later file shadows an
already-merged key. *A background task for this is already in flight.*

### B. A run that dies in Phase 1 cannot be exported
`patientpunk/pipeline.py:414` `_resolve_export_input_files` looks only for
`records_{schema_id}.json`, which Phase 1 writes **on completion**. When the first
full-corpus attempt died at 94.2%, 64,586 extracted records existed solely in the
incremental `llm_records_{schema_id}.json` and `--start-at 3` silently skipped export.

Recovering $114 of completed work took a manual `cp` to the expected filename. Fix:
fall back to `llm_records_*.json` when the final file is absent, or have Phase 1 write
both. One line, and every interrupted run becomes a usable partial dataset.

### C. The incremental save has no retry, and rewrites 148 MB every 10 records
`_write_json_atomic` writes `.tmp` then renames. On the second attempt the rename was
refused:

```
[WinError 5] Access is denied: llm_records_….json.tmp -> llm_records_….json
```

The repo sits under OneDrive and the file is fully rewritten every
`SAVE_EVERY_N = 10` records — precisely the pattern a sync client interferes with. A
transient lock killed the run at **96.7%**.

No data was lost (the `.tmp` held ten *more* records than the last good save), but only
because someone looked. Fix: catch `PermissionError` and retry with backoff; and
consider an append-only JSONL sidecar instead of a full rewrite, which is fragile on any
syncing filesystem and slow regardless.

### D. `records.csv` silently drops confidence
Every one of the **729,209** populated cells carries a confidence rating —
50.9% medium, 43.2% high, 5.8% low — and the CSV has no `__confidence` columns at all.
Anyone analysing from the CSV discards a per-cell quality signal without being told.

Fix: emit `<field>__confidence` columns, or print a one-line warning at export. The S3
README now documents it, but the file itself still gives no hint.

### E. `LLM_MAX_TOKENS=32768` is not enough for large inputs
Confirmed, not theorised: with a 400,000-character cap, records whose text ran to six
figures returned `response truncated at max_tokens`. Truncated records fail loudly
(`check_response` raises) rather than storing half a record, which is the right
failure mode — but they are lost. The comment at `MAX_TEXT_CHARS` already records the
same failure at 30,000 chars against 8,192 tokens; the pairing needs documenting as a
rule, not rediscovering.

### F. `--reclassify` also wipes the extract cache
`src/pipeline/extract.py:191` — `if tagged_path.exists() and not config.reclassify`.
The flag is documented as classification-only, so setting it silently re-sends every
post to the fast model for extraction as well. A cost trap hiding behind a
reasonable-sounding name. Fix: rename, or scope the flag to classification.

### G. `treatment_reports` has no uniqueness constraint
`schema.sql` declares only `report_id INTEGER PRIMARY KEY`. Nothing at the database
level stops the same `(post_id, drug_id)` being inserted twice; the only guard is an
in-memory set in `ReportWriter`. Any path that bypasses the writer double-counts.

### H. `normalize.py` defines `functional_status_tier` twice
Lines 85 and 170. The second silently wins. Harmless today because the contents match,
but anyone editing the first copy will watch their change do nothing.

### I. `load_db.py` cannot run on the `db_to_corpus` route
It requires `data/posts.db`, which that route never produces — it emits corpus JSON.
`CORPUS_RUNBOOK.md` step 6 therefore cannot be followed as written by anyone using the
path the runbook itself recommends. Fix the runbook, or teach `load_db.py` to build
its corpus tables from `subreddit_posts.json`.

---

## Sharp edges that are not bugs

**`max_tokens` is part of the cache key.** Raising `LLM_MAX_TOKENS` on a resume to
rescue truncated records would invalidate every cached response — about **$114** to
recover ~29 records. Correct behaviour, genuinely dangerous, worth a warning in the
resume path.

**`--resume` cannot see a cap change.** Resume matches on `(author_hash, post_id)`, and
an aggregated record's `post_id` is `agg_<hash>` — stable no matter what the cap is. So
resuming after changing `LLM_MAX_TEXT_CHARS` silently produces a mixed-cap dataset.
Consider recording the cap in the temp file and refusing to resume across a change.

**`text_count` reads 1 on every aggregated record.** Correct — it counts prompt texts,
and aggregation already joined the patient's segments into one body — but it reads like
a patient-level count and is not one. The real figure is `n_items` on the synthetic post.

**`--limit` means two different things.** In extract it caps posts loaded from the DB;
in classify it caps entries read from the JSON. (Its interaction with `--resume` was
checked and is deliberate — the comment at `llm_extract.py:746` explains why.)

---

## Data quality in the output

**Bots are patients.** The single largest "patient" in the corpus is AutoModerator at
5.5M characters, followed by a moderator removal template and RemindMeBot. Scope is
small — 2 of the top 40 accounts, ~0.6% of corpus text — and the extractor correctly
returned zero fields for them rather than inventing patient data. But they distort the
text-length distribution that cap decisions are read from. Filter bot and moderator
accounts before `aggregate`; it has to happen upstream of `db_to_corpus.py`, which
hashes authors on the way out.

**8,169 records (11.8%) extracted zero fields.** Investigated and benign: median 720
characters against 3,727 for records that did populate — short patients who cleared
`--min-items 3` on three one-line comments. The denominator is sound, but decide
whether they belong in an analysis.

**18,101 uncanonicalized treatment strings.** `ldn`, `low dose naltrexone`, and
`low-dose naltrexone` are three separate strings. Nothing can be counted reliably until
they are collapsed. Tractable: top 500 strings cover 71.7% of mentions, top 1,000 cover
80.1%, true singletons are 5.3%.

**The 67.1% `helped` rate is the least trustworthy number produced.** The extractor
over-calls positive, and stacked treatments can inherit a collective outcome — and this
cohort stacks hard (median 3 distinct treatments per patient, mean 4.5, 31% naming five
or more). Expect the true rate to be materially lower.

**Individual records are not reproducible.** Two identical passes agreed on the field
set for 36.5% of records; where both filled a field they agreed on the value 58.8% of
the time. Aggregates are stable to 0.8pp. Property of the model and of routing across
backend providers, not of this corpus — so it will hold on any future corpus too.

---

## Process failures worth not repeating

**Cost was estimated wrong three times, and the third was structural.** The final model
(`$0.000809/record + $0.000000029/char`) was fitted to two rehearsal arms and reproduced
both to the cent — then ran 33% under on the real corpus. The two arms differed only in
*input* size, so the fit could not see the output term's slope, and the per-record
"constant" is not constant. **A model fitted where one term cannot vary will hide that
term's slope.** Calibration points must differ in output size, not only input.

**A key was validated against the wrong endpoint.** Pre-flight checked
`/api/v1/credits`, which returned 200 and a healthy balance. The pipeline uses
`/api/v1/chat/completions`, which returned `401 User not found` — the key was a
provisioning key, not an inference key. **Check the thing, not a proxy for it.** A
one-token completion is the only pre-flight that proves a key can do the job.

**A config file was cleared by a check too narrow to clear it.** `variable_extraction/.env`
was grepped for `MODEL_` keys, found to have none, and declared safe. Its *API key* was
the problem (finding A). The same shape of error twice in one run: verifying an adjacent
property and reporting it as the property of interest.

---

## Suggested order of work

1. **C** — the save retry. It is the only item here that destroys a multi-hour run.
2. **B** — export fallback. Turns a dead run into a usable partial dataset.
3. **A** — the `.env` shadow. Already in flight.
4. **D** — confidence in the CSV. Cheap, and it is a correctness issue for every
   downstream analysis.
5. Bot filtering, before any further corpus is built.
6. **F**, **G**, **H**, **I** — real but lower-impact.
