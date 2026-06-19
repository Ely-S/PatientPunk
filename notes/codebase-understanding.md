# PatientPunk — Verified Architecture Reference

> Distilled from a 13-agent deep-read workflow (11 parallel readers → synthesis → adversarial
> verification against real files) run 2026-06-19. Treat this as the canonical map so we never
> have to re-run that workflow. Every load-bearing claim below was file-grounded by the verifier.

## 1. What it is

A research toolkit that mines patient self-reports on Reddit (primarily r/covidlonghaulers) into
queryable structured data, to gather **real-world evidence at scale**. Two research questions, two
systems (see §2). Flagship result: pre-publication community sentiment about 6 Long COVID treatments
correctly predicted the *direction* of every subsequent clinical-trial outcome (the RCT
historical-validation study). Built at the Biotech Hackathon SF, April 4 2026 (`README.md:324`).

## 2. THE critical fact — two parallel, fully decoupled extraction systems

Neither supersedes the other. Verified: **zero** `sqlite3`/`treatment_reports`/`schema.sql`
references inside `variable_extraction/`, and **zero** `patientpunk` imports inside `src/`.

| | `src/` — sentiment pipeline | `variable_extraction/patientpunk` — variable extraction |
|---|---|---|
| Question | *Which drugs help?* (per (post,drug) sentiment) | *Who are the patients?* (37+ clinical/demographic vars) |
| Storage | **SQLite** (`schema.sql`, 7 tables) | **Files only** (JSON temp → `records.csv` + `codebook`) |
| Orchestrator | `src/run_sentiment_pipeline.py` (extract→canonicalize→classify) | `variable_extraction/main.py run` → `patientpunk/pipeline.py` (5 phases) |
| LLM config | `src/utilities/__init__.py` | `patientpunk/_utils.py` (**duplicated, near-verbatim, but subtly divergent**) |
| Installable? | No (just on pytest `pythonpath=["src"]`) | **Yes** — `patientpunk*` is the *only* installable package |

They share only: the upstream corpus, the `author_hash` (SHA-256) join key, the domain, the name,
the env-var/model conventions, and a **duplicated LLM-provider abstraction**. Two unrelated classes
both named `PipelineConfig` (`src/utilities` `@dataclass` vs `patientpunk/pipeline.py` pydantic).

## 3. End-to-end data flow

**Stage 0 — Scrape (`Scrapers/`).** `scrape_corpus.py` (live Arctic Shift API, no Reddit key) or
`transform_arctic_shift.py` (offline NDJSON bulk-dump converter — the path used for the research
corpus). Both emit byte-compatible `output/subreddit_posts.json` (+ `users/{hash}.json`,
`corpus_metadata.json`). Usernames SHA-256-hashed in memory before touching disk. `t3_`/`t1_`
kind prefixes preserved on write.

**Track A — `src/` → SQLite.**
1. `sqlite3 data/posts.db < schema.sql` creates the empty DB. (`mkdir -p data` first; gitignored.)
2. `src/import_posts.py` (`import_reddit_posts`, flags `--reddit-posts --output-db --subreddit`)
   flattens into `users` + `posts`. `strip_reddit_prefix()` strips `t1_`/`t3_` **before** a single
   SQL `UPDATE` nulls dangling `parent_id`s — ordering is load-bearing for thread reconstruction.
3. `src/run_sentiment_pipeline.py`:
   - **extract** (`pipeline/extract.py`) → fast-LLM drug mentions + parent-inherited context →
     `outputs/tagged_mentions.json` (atomic `.tmp`+replace; doubles as resume cache).
   - **canonicalize** (`pipeline/canonicalize.py`) → strong-LLM synonym merge →
     `outputs/canonicalized_mentions.json` + upserts `treatment` table.
   - **classify** (`pipeline/classify.py`) → (entry×drug) queue skipping pairs already in
     `treatment_reports`; fast-LLM prefilter (cached `outputs/prefilter_results.json`) → strong-LLM
     classify → `ReportWriter.write_one` inserts `treatment_reports` **only when `signal != 'n/a'`**.
4. `src/extract_demographics_conditions.py` (`run_demographics`) reads `posts` by user →
   `user_profiles` + `conditions`.
5. Every run inserts one `extraction_runs` row (git commit + config JSON, `extraction_type`
   discriminator: `treatment_sentiment` vs demographics); every Layer-3 row carries its `run_id`.

**Track B — `variable_extraction` → CSV.** optional `aggregate.py` (one synthetic post/author) →
Phase1 regex `extract_biomedical.py` → `temp/patientpunk_records_*.json` → Phase2 Haiku gap-fill
`llm_extract.py` → `temp/merged_records_*.json` → Phase3 discovery `discover_fields.py` (Haiku+Sonnet)
→ `temp/discovered_records_*.json` → Phase4 `records_to_csv.py` → `output/records.csv` → Phase5
`make_codebook.py` → `codebook`. Post-hoc: `normalize.py` → `cluster_prep.py` → `evaluate.py`.

**Track C — RCT validation (`docs/RCT_historical_validation/`).** Read-only over a *frozen* ~314 MB
SQLite DB, **no LLM**, regenerates paper Fig 1/2 + Tables. `verify.py` = one-command repro gate.

## 4. Schema (`schema.sql`, repo root, owned/written exclusively by `src/`)

7 tables, `WAL` + `foreign_keys=ON` (per-connection pragma, re-issued in app code). Column order
matters when diffing — actual `treatment` order is `id, canonical_name, treatment_class, aliases, notes`.

- **Layer 1 (raw):** `users(user_id PK=author_hash, source_subreddit, scraped_at)`;
  `posts(post_id PK, title, parent_id→posts self-ref, user_id, body_text, flair, post_date, scraped_at NOT NULL, metadata JSON)`.
- **Layer 2 (config):** `treatment(id PK, canonical_name COLLATE NOCASE UNIQUE, treatment_class, aliases JSON, notes)`;
  `extraction_runs(run_id PK, run_at, commit_hash, extraction_type, config JSON)` — the traceability spine.
- **Layer 3 (run-stamped):** `user_profiles(user_id+run_id composite PK, age_bucket, sex, location)`;
  `conditions(condition_id PK, run_id, user_id, post_id?, condition_type CHECK IN ('illness','symptom'), condition_name, diagnosed_at, resolved_at, severity)`;
  `treatment_reports(report_id PK, run_id, post_id, user_id?, drug_id, sentiment, signal_strength, side_effects JSON)`.

Runs **append** (re-runs don't overwrite); `ReportWriter` skips already-present `(post_id, drug_id)`
unless `--reclassify`. In the validated DB, `conditions`/`user_profiles` are empty (reserved).

## 5. LLM provider abstraction (duplicated in both systems)

- **Auto-detect provider** from which key is set: `OPENROUTER_API_KEY`→openrouter, else
  `ANTHROPIC_API_KEY`→anthropic; override via `LLM_PROVIDER`; `LLM_API_KEY` wins when set.
- **Fast vs strong:** `MODEL_FAST` (Haiku) for extraction/gap-fill/prefilter; `MODEL_STRONG`
  (Sonnet) for canonicalization/classification/discovery. Defaults: `claude-haiku-4-5-20251001` /
  `claude-sonnet-4-6` (anthropic) or `anthropic/claude-haiku-4.5` / `anthropic/claude-sonnet-4.6` (openrouter).
- **`_OpenAIAdapter`** fakes the Anthropic surface so vLLM/Ollama/OpenRouter-v1 work; `openai`
  provider requires explicit `MODEL_FAST`/`MODEL_STRONG` (no defaults; `src/` `sys.exit()`s at import otherwise).
- Config resolved **once at import time** — changing env after import has no effect.
- Cost tricks: ephemeral prompt caching, bounded parallelism, `--drug` alias-cache bypass, temp 0.0,
  tolerant JSON parsing, batch-split-retry on count mismatch.

## 6. Genuinely clever parts

- **Reply-chain context propagation** — `drugs_context` inherited from ancestor comments via
  `lru_cache`-memoized recursion over `parent_id`; cycle guard (`find_parent_cycles`) runs *first*.
- **Targeted `--drug` mode** — regex extract + alias→target map, zero extract/canonicalize tokens on iteration.
- **Question-only filter + personal-experience prefilter** gate out non-self-reports before expensive classify.
- **Crash recovery everywhere** — JSON resume caches, DB-pair skipping, atomic writes, incremental scraper files.
- **Provenance baked in** — git commit + config JSON per run; RCT `provenance.json` self-checks.

## 7. Known gotchas / rough edges (verified)

- **CI likely doesn't run the e2e DB test.** `pyproject` `testpaths=["variable_extraction/tests"]`;
  CI runs `uv run pytest -v` (no path) → only `variable_extraction/tests/` collected. Root
  `tests/populate_db_test.py` (the schema→import→sentiment+demographics e2e test, with `FakeAnthropic`)
  is importable but **not default-collected**.
- **Silent DB drops.** Rows written only when `signal != 'n/a'`; `write_one` returns `False`
  (skip) if drug not in `treatment`; `--skip-canonicalize` may classify against a stale
  `canonicalized_mentions.json`.
- **Massive intentional duplication** (see hazard map): LLM config; demographics extraction; the
  dedup rule / `SIG_RANK` / `DRUG_CUTOFFS` / `EXPECTED_OUTPUTS` across `_build_paper_figures.py` +
  `verify.py` + `dump_per_drug_csvs.py` ("must stay in sync"); `find_parent_cycles` inlined in `verify.py`.
- **Dead/vestigial:** `app/__init__.py` (0 bytes), stray 2-byte root `test` file,
  `canonicalize.main()`/`classify.main()` (can't persist), `make_codebook.META_COLUMNS`,
  `code_demographics_llm.call_haiku()`, skipped `run_schema_health_update`.
- **Stale docs:** `Scrapers/*.md` (nonexistent `demographic_extraction/`, `requirements.txt`),
  `docs/MVP_PLAN.md` (self-flagged 90% generated, nonexistent modules), `docs/ldn_notes.md`
  (missing `scripts/classify_ldn.py`, hardcoded `/Users/pbinder/…`).
- **Likely real bugs (behavior, NOT cleanup scope):** `scrape_corpus.fetch_reddit_profile` reads
  `data['output']` but reddit `about.json` returns `{kind,data}`; `transform_arctic_shift._sort_key`
  sorts stringified ints; `paginate_all` before-bound unimplemented; `split_retry_batch` silently
  substitutes `None` for items that fail even per-item.

## 8. "Where do I look for X"

- Drug-sentiment row → `src/run_sentiment_pipeline.py` → `src/pipeline/{extract,canonicalize,classify}.py`; writer `src/utilities/db.py`.
- DB shape / traceability → `schema.sql`; `extraction_runs` + `run_id`.
- Prompts/rubrics → `src/prompts/intervention_config.py`, `src/prompts/demographic_prompt.py`; `docs/ldn_notes.md`; `patientpunk/qualitative_standards.py`.
- Wide-variable extraction → `variable_extraction/main.py` → `patientpunk/pipeline.py`; logic in `patientpunk/scripts/*.py`.
- Scrape / corpus contract → `Scrapers/{scrape_corpus,transform_arctic_shift}.py`; contract = `output/subreddit_posts.json`.
- Reproduce paper → `docs/RCT_historical_validation/verify.py`, `_build_paper_figures.py`.
- LLM/model/provider → `src/utilities/__init__.py` + `patientpunk/_utils.py` (duplicated); `.env.example`.
- CI / tests → `.github/workflows/ci.yml`, `pyproject.toml [tool.pytest.ini_options]`, `tests/populate_db_test.py`.
