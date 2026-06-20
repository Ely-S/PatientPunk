# The Cleanup Sequence — Verbatim, Analyzed, + PatientPunk Hazard Map

Source: `C:\Users\leech\Downloads\claude code cleanup prompts.pdf` ("Claude Code: Codebase Cleanup
Prompt Sequence"). Run each prompt in order, one at a time, after the previous finishes.

## A. The 14 steps (verbatim)

1. Do a deep dive into the codebase and delete all dead code, deprecated code, and thin shims.
2. Identify all the magic strings and numbers, and put them as global variables or data
   structures/enums in an appropriate location.
3. As an expert clean and DRY software engineer, identify all the similar logic and DRY it up.
4. Do another deep dive into the codebase and delete all dead code, deprecated code, and thin shims.
5. Identify all the inner/private variables and see what uses them and why.
6. As an English language expert, of all the variables you've identified, determine the best and
   clearest names for each. **Do not change them yet** — just list them out along with the best names.
7. Rename all these variables. **Do not leave any mis-directions** (no references or comments
   pointing to the old names).
8. Identify all the functions and parameters, and see what uses them and why.
9. As an English language expert, of all the functions/parameters you've identified, determine the
   best and clearest names for each. **Do not change them yet** — just list them out.
10. Rename them. **Do not leave any mis-directions.**
11. Identify all the unclear classes and file names, and rename and reorganize them so it's easy for
    you (Claude Code) to understand them.
12. Clean up all the comments and docstrings that are no longer useful.
13. Deep-research online for the latest techniques for Claude Code to understand a codebase easily.
14. Make the codebase easy to understand for yourself. Clean up the CLAUDE.md files, and iterate
    until you're able to understand the codebase easily. Use sub-agents with fresh context to
    evaluate and test.

(PDF note: Step 2 "magic strings/numbers" was placed right after the first dead-code pass per an
"after number 2" correction in the original author's notes. Ordering is adjustable.)

## B. The logic of the sequence (why this order)

Six phases. The ordering is not arbitrary — each transform sets up the next:

- **Subtract first, and repeat (1, 4).** Never invest effort renaming/DRYing/documenting code you'll
  delete. Removing dead code shrinks the surface for everything downstream. It's repeated because
  steps 2–3 *create new* dead code (DRYing orphans the originals; centralizing constants orphans
  helpers).
- **Centralize constants (2).** Low-risk, local. Also *surfaces duplication* — the same literal in 5
  places becomes one constant referenced 5×, which feeds the DRY pass and makes later renames trivial.
- **DRY (3).** Structural dedup, after constants make near-duplicate blocks identical. Followed by the
  second delete pass (4) to remove what DRYing orphaned.
- **Rename, narrow→wide, in a strict 3-beat cadence (5–11):**
  - **Identify + understand** what uses it and why (5, 8; 11 folds identify+act).
  - **Propose names without changing** — "as an English language expert," list current→proposed (6, 9).
  - **Apply atomically, no misdirection** — every reference/comment/string/doc moves with the symbol (7, 10).
  - Scope order = **variables → functions/params → classes/files**, i.e. increasing blast radius. Each
    rename's reach is contained; you don't re-touch the same lines repeatedly.
  - The **propose→apply split is a deliberate human review gate**: it separates the *judgment* task
    ("clearest name?") from the *mechanical* task ("rename everywhere, leave nothing dangling"), and
    lets a human veto bad names before they're applied corpus-wide.
- **Document last (12).** Comments describing still-churning code are wasted/wrong; many comments only
  existed to compensate for bad names now fixed.
- **Meta / self-onboarding (13, 14).** Research current best practices, then make the repo legible to
  the agent itself — clean CLAUDE.md, iterate, and **validate with fresh-context sub-agents**. The
  acceptance test for "is this understandable?" is: *can an agent with no prior context navigate it?*

**The through-line:** the goal function of the whole sequence is **maximize legibility for an AI agent
(and humans) while preserving behavior.** Every step is subtraction or clarification; none should
change what the code *does*.

## C. Invariants we will enforce (these make the sequence safe & generalizable)

1. **Behavior preservation.** Every mutating step ends with the static-gate ladder green
   (format → lint → typecheck → build → test). No step ships on red.
2. **Interface-boundary protection.** Internal names are free to rename/delete; *boundary* names are
   frozen unless explicitly intended (see hazard map §D).
3. **Dead ≠ unreferenced-in-repo.** Account for dynamic dispatch, registries, entry points, public
   API of installable packages, test-only code, cross-repo consumers. Quarantine before delete; verify.
4. **Propose → approve → apply for renames** (the human gate; matches "one prompt at a time").
5. **Atomic, reviewable commit per step** so any step is independently reviewable/revertible.
6. **Externalized, resumable state** — progress lives in `notes/`, not in context (multi-session work).
7. **Fresh-context validation** — sub-agents with no priming both *find* (dead code, dup, bad names)
   and *evaluate* (final comprehension).
8. **Don't fix behavior bugs mid-refactor.** Log discovered bugs; fix them in a separate, intentional
   pass. Fixing behavior during a "no-behavior-change" cleanup muddies review and breaks invariant #1.

## D. PatientPunk hazard map (repo-specific — READ BEFORE EXECUTING ANY STEP)

### D1. Gate commands for THIS repo
- Install/sync: `uv sync` (CI uses `uv sync --locked`, uv 0.8.11, Python 3.13).
- Tests: `uv run pytest -v`. **But** `pyproject` `testpaths=["variable_extraction/tests"]` means the
  default run **excludes** `tests/populate_db_test.py`. To actually cover `src/`, run
  `uv run pytest tests/ variable_extraction/tests/ -v` explicitly. Fixing this collection gap is
  itself a legitimate cleanup item.
- Lint: `ruff` (config at `variable_extraction/ruff.toml`; no root ruff config — check before assuming).
- No type-checker configured (no mypy/pyright config found) — don't assume one.

### D2. Boundary names — DO NOT rename/delete without explicit intent (Steps 1,4,7,10,11)
- **DB schema** (`schema.sql`) table & column names. A frozen ~314 MB DB and the RCT repro gate
  (`verify.py`, `dump_per_drug_csvs.py`) query by these names. Renaming = breaking on-disk data + repro.
- **JSON artifact filenames & field keys:** `tagged_mentions.json`, `canonicalized_mentions.json`,
  `prefilter_results.json`, `aliases_<target>.json`, and keys `drugs_direct`/`drugs_context`. These are
  resume caches — renaming orphans existing caches.
- **Corpus contract:** `output/subreddit_posts.json` shape (Scrapers ↔ both downstream systems).
- **CLI flags** across all entry points (`--db`, `--output-dir`, `--drug`, `--reclassify`,
  `--skip-*`, `--reddit-posts`, `--output-db`, etc.) — documented in README, used by humans.
- **Env vars:** `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `LLM_PROVIDER`, `LLM_API_KEY`,
  `MODEL_FAST`, `MODEL_STRONG` (mirrored in `.env.example`).
- **`patientpunk` public API** — it is the *only installable package*; `__init__.py` exports are
  public surface, not "internal."
- **`main.py` subcommand names:** run, demographics, inspect, corpus, export, promote, consolidate,
  validate, cluster-prep, aggregate, normalize.
- **Data values (not identifiers):** sentiment `positive/negative/mixed/neutral`, signal
  `strong/moderate/weak/n/a` (note: `n/a` with a slash — `n-a` does not appear in code). Stored in DB
  and asserted in tests/validation.
- **Provenance contract:** `extraction_runs.config` JSON shape; `extraction_type` discriminator values.

### D3. Intentional duplication — DO NOT blindly "DRY up" (Step 3)
- The two `PipelineConfig` classes (`src/utilities` `@dataclass` vs `patientpunk/pipeline.py` pydantic):
  **different things, same name.** Do not merge. (Resolving the *name* collision is possible but touches
  the installable package's surface — treat as a boundary rename, ask first.)
- **LLM provider abstraction** duplicated in `src/utilities/__init__.py` vs `patientpunk/_utils.py`:
  merging couples two *intentionally decoupled* systems, and they already **differ** (e.g. placeholder-key
  handling: `sk-ant-your-*`/`your_*` prefix logic exists ONLY in `_utils.py`; `src/` uses exact-match
  set). Flag, don't auto-merge — this is a human judgment call.
- **RCT self-containment duplication:** the dedup rule / `SIG_RANK` / `DRUG_CUTOFFS` / `EXPECTED_OUTPUTS`
  reimplemented across `_build_paper_figures.py`, `verify.py`, `dump_per_drug_csvs.py` (comments say
  "must stay in sync"), and `find_parent_cycles` inlined in `verify.py`. The RCT package *deliberately*
  self-contains for reproducibility/portability. DRY here could break that design goal — ask first.

→ Rule: when duplication straddles the `src/` ↔ `variable_extraction/` ↔ `docs/RCT...` boundary, it is
presumptively intentional. Surface it; let the human decide. Within a single subsystem, DRY freely.

**Intentional-duplication registry (confirmed in Step 3 — 36 surfaced clusters; do NOT merge):**
- **LLM-provider abstraction** — `src/utilities/__init__.py` vs `patientpunk/_utils.py`. Subtly
  DIVERGENT (placeholder-key handling, default openai base URL openrouter-vs-localhost, adapter surface
  `.stream()+.create()` vs `.create()` only, empty-choices handling, client kwargs, unsupported-provider
  `sys.exit` vs fallthrough). Merging changes behavior for ≥1 caller AND breaks package-independence.
- **Demographics extraction** in both systems — incompatible output schemas (bucketed→SQLite vs
  raw-int+country/state→CSV), prompts, and LLM machinery. No shared impl preserves both.
- **Two `PipelineConfig` classes** (src `@dataclass` vs patientpunk pydantic) — unrelated, same name.
- **RCT sync-group** — `SIG_RANK` / `DRUG_CUTOFFS` / `EXPECTED_OUTPUTS` / dedup rule / `find_parent_cycles`
  across `docs/RCT_historical_validation/{verify,_build_paper_figures}.py` + `scripts/dump_per_drug_csvs.py`.
  Deliberate self-containment for reproducibility; "must stay in sync" comments are intentional.
- **Scrapers** `scrape_corpus.py` ↔ `transform_arctic_shift.py` standalone helpers (don't import each other).
- **Cross-script helpers in `scripts/`** (fence-stripping, retry, `collect_texts_*`) — the scripts are
  deliberately subprocess-independent; `extract_biomedical.py` is intentionally stdlib-only. Leave.

**Applied in Step 3 (within-system, byte-identical, behavior-preserving):** `_build_tagged` (extract.py),
`create_extraction_run` (db.py), `_parse_json` (utilities), `META_SKIP_COLUMNS` (consolidated
cluster_prep.DEFAULT_META + evaluate._META; named to avoid the `records_to_csv.META_COLUMNS` collision).

### D4. Genuine dead-code candidates (Steps 1/4 — still verify each isn't dynamically/publicly used)
- `app/__init__.py` (0 bytes; no web app despite the name).
- stray 2-byte `test` file at repo root.
- `canonicalize.main()` / `classify.main()` standalone entry points that can't persist
  (`db_path='.'`, `writer=None`) — decide delete vs fix.
- `make_codebook.py` module-level `META_COLUMNS` (unused).
- `code_demographics_llm.call_haiku()` (unused).
- `run_schema_health_update` skipped in `discover_fields.main()`.

### D5. Stale-doc targets (Step 12 + doc hygiene)
- `Scrapers/{README,SCRAPER_HELP,CONTRIBUTING}.md` reference nonexistent
  `Scrapers/demographic_extraction/`, `requirements.txt`, `.env.example`.
- `docs/MVP_PLAN.md` (self-flagged 90% generated) references nonexistent modules / old author split.
- `docs/ldn_notes.md` references missing `scripts/classify_ldn.py` + hardcoded `/Users/pbinder/…`;
  also introduces a `confounded` signal label not in the canonical set.
- `src/extract_demographics_conditions.py` *docstring* (not `--help`) references a nonexistent
  `run_demographics.py` (the function `run_demographics` exists; no standalone file).
- **(found Step 11) Consolidated stale-filename worklist** for Step 12 — docstrings naming old files
  (`extract_mentions.py` / `classify_sentiment.py` / `run_demographics.py`, the gone `database_creation/` +
  `Scrapers/demographic_extraction/` dirs) — is enumerated precisely in `notes/step11-class-file-plan.md` §4.
- **(found Step 4)** `variable_extraction/main.py` + `patientpunk/pipeline.py` reference an `apps/discover.py`
  Marimo picker that does not exist on disk (no `apps/` dir anywhere) — a broken/aspirational feature
  reference. Distinct from the now-deleted `app/` package. Investigate in Step 12 (delete the dead path
  or build the picker).
- **(found Step 10)** Docstring/comment PROSE saying "Call Haiku" / "Claude Haiku" / "Haiku reads the text" in
  `scripts/{llm_extract,code_demographics_llm,extract_demographics_llm}.py` is now provider-inaccurate after the
  `call_haiku`→`call_model` rename (the model is the provider-agnostic `MODEL_FAST`). Make the prose
  provider-agnostic in Step 12 (comment/docstring cleanup) — it's prose, not a symbol, so Step 10 left it.

### D6. Behavior bugs found — LOG, do not fix during cleanup (invariant #8)
- **Windows encoding (found Step 1):** `tests/populate_db_test.py` does `SCHEMA.read_text()` with no
  `encoding=`, so it dies (`UnicodeDecodeError`) on `schema.sql`'s UTF-8 box-drawing chars under cp1252.
  Invisible in CI (testpaths excludes it). Fix = `encoding="utf-8"`. Gate currently uses `PYTHONUTF8=1`.
- **F841 dropped-value bugs (found Step 1; dead assignments REMOVED in Step 4 per user decision — the
  latent-bug record now lives ONLY here, no longer flagged in code):** each computed a value whose
  intended print/use was dropped:
  - `extract.py` save-throttle: the removed `batches_since_save`/`SAVE_EVERY=50` flagged that the
    checkpoint actually fires every `BATCH_SIZE*100` = **1000 records**, NOT "every 50 batches" as the
    old comment claimed (comment corrected in Step 4; the *throttle value* itself was NOT changed).
  - `pipeline.py:ext_result` — the extractor's richer structured return was discarded; stats are
    re-read from temp JSON via `_collect_stats` instead.
  - `discover_fields.py:regex_fields` — the regex-extractable field-count summary was never printed
    (only the sibling `llm_only_fields` summary is).
  - `extract_biomedical.py:ext_count` — total extension-field count dropped from the `Done!` summary.
  - `llm_extract.py:reason` — producers tag skips with `no_text`/`regex_covered` but the per-reason
    breakdown was never tallied (only an aggregate `{skipped} skipped`).
  Fix in a separate behavioral pass (wire the dropped diagnostic, or accept the simplification).
- `scrape_corpus.fetch_reddit_profile` reads `data['output']` but reddit `about.json` → `{kind,data}`.
- `transform_arctic_shift._sort_key` sorts stringified int timestamps (not numeric).
- `paginate_all` documented "before bound" never implemented.
- `split_retry_batch` (`patientpunk/_utils.py`) substitutes `None` for items failing per-item (silent loss).
- The RCT `DRUG_ALIASES.md` contains un-adjudicated LLM alias errors used as-is (e.g. `loratab`/Lortab
  under loratadine; `prednisolone` under prednisone; standalone `ritonavir` under paxlovid).
