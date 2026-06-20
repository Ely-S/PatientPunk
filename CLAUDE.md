# CLAUDE.md — PatientPunk

PatientPunk mines firsthand patient reports from Reddit (r/covidlonghaulers) into queryable structured
data — drug **sentiment** and patient **demographics/conditions** — to gather real-world evidence at
scale. Product overview + full run instructions: @README.md

## Architecture — TWO decoupled systems (IMPORTANT)
This repo holds **two parallel, fully decoupled systems** that share no database and no code:
1. **`src/`** — the drug-**sentiment** pipeline (extract → canonicalize → classify). Writes a **SQLite**
   DB (`schema.sql`, 7 tables). NOT an installable package (it sits on the pytest `pythonpath`).
   Orchestrator: `src/run_sentiment_pipeline.py`.
2. **`variable_extraction/patientpunk/`** — wide clinical-**variable** extraction (5 phases). Writes
   **files only** (JSON temp → `records.csv` + a codebook). The **only installable package** — its
   `__init__.py` exports are **public API**. Orchestrator: `variable_extraction/main.py`.

**IMPORTANT — never couple them.** They duplicate the LLM-provider abstraction
(`src/utilities/__init__.py` vs `patientpunk/_utils.py`) and both define an *unrelated* class named
`PipelineConfig` (src = `@dataclass`, patientpunk = pydantic) **on purpose**. Do NOT "DRY" these together;
do NOT import `patientpunk` inside `src/`, nor `sqlite3`/`treatment_reports` inside `variable_extraction/`.
A third area, `docs/RCT_historical_validation/`, is a deliberately **self-contained** reproducibility
package that *inlines* copies (`find_parent_cycles`, `SIG_RANK`/`DRUG_CUTOFFS`/`EXPECTED_OUTPUTS`) — do
not unify those either. Full architecture map: `notes/codebase-understanding.md`; the frozen-boundary +
"do not merge / must stay in sync" registry: `notes/cleanup-sequence-and-hazards.md`.

## Commands
- Setup: `uv sync` (this repo uses **`uv`** + Python 3.13 — never bare `python`/`pip`). LLM key: `cp .env.example .env`.
- DB bootstrap (src/ pipeline): `mkdir -p data && sqlite3 data/posts.db < schema.sql`.
- Running the scraper / sentiment pipeline / variable extraction: see @README.md for the exact commands + flags.

## Gate — run before claiming a change is done
- **Tests (the gate):** `uv run pytest tests/ variable_extraction/tests/ -v` — target **63 passed**.
  - Pass the paths **explicitly**. CI runs bare `uv run pytest -v`, and `pyproject` `testpaths=["variable_extraction/tests"]`
    means the root `tests/` **end-to-end SQLite test (`tests/populate_db_test.py`) is NOT collected by default** — CI's bare run
    covers only the `variable_extraction/` subset (fewer than 63), so a green CI does *not* exercise the `src/` pipeline.
  - **On Windows, prefix `PYTHONUTF8=1`** (e.g. `PYTHONUTF8=1 uv run pytest …`). The e2e test reads `schema.sql`'s
    UTF-8 box-drawing chars and dies under cp1252 otherwise.
- **Lint:** `ruff check .` / `ruff format .`. The repo is NOT ruff-clean (~154 known findings) — don't try to zero it; just keep the count from rising.
- **Paper reproducibility:** `uv run python docs/RCT_historical_validation/verify.py`.

## Where to look
- A drug-sentiment row → `src/run_sentiment_pipeline.py` → `src/pipeline/{extract,canonicalize,classify}.py`; the DB writer is `ReportWriter` in `src/utilities/db.py`.
- Wide-variable extraction → `variable_extraction/main.py` → `patientpunk/pipeline.py`; the real logic is the subprocess scripts in `patientpunk/scripts/*.py`.
- DB shape / run traceability → `schema.sql` (7 tables; `extraction_runs` + `run_id` is the provenance spine).
- LLM provider/models → `src/utilities/__init__.py` AND `patientpunk/_utils.py` (duplicated, one per system).
- Prompts → `src/prompts/`. Reproduce the paper → `docs/RCT_historical_validation/verify.py`.
- Deep architecture + an exhaustive "where do I look for X" index → `notes/codebase-understanding.md`.

## Conventions
- `uv` for everything (`uv run …`); Python 3.13; `ruff` for format/lint; `gh` for GitHub/PRs.
- Behavior-preserving by default: keep the gate at 63 green, and do NOT rename frozen boundaries — DB
  column/table names, JSON cache keys (`drugs_direct`/`drugs_context`/`tagged_mentions.json`/…), CLI flags,
  env vars, the `patientpunk` public API, or the 7 subprocess `_SCRIPT` filenames.

## Gotchas — do NOT "fix" these (they are intentional or out of scope)
- **Silent drops:** `treatment_reports` rows are written only when `signal != 'n/a'` — absence of a row ≠ "never classified".
- **Load-bearing ordering:** `import_posts.strip_reddit_prefix()` must run BEFORE the SQL `UPDATE` that nulls dangling `parent_id`s.
- **LLM config is resolved once at IMPORT time** (auto-detect: `OPENROUTER_API_KEY`→openrouter else `ANTHROPIC_API_KEY`→anthropic;
  `LLM_PROVIDER` overrides; `LLM_PROVIDER=openai` requires explicit `MODEL_FAST`/`MODEL_STRONG` or `src/` `sys.exit()`s at import). Changing env after import has no effect.
- **Known real bugs are LOGGED, not fixed** here — see `notes/cleanup-sequence-and-hazards.md` §D6 (e.g. `scrape_corpus.fetch_reddit_profile` reads the wrong JSON shape; a half-wired save-throttle). Surface bugs; don't silently change behavior.

<!-- Maintainer note: CLAUDE.md is force-added past .gitignore (it ignores CLAUDE.md/AGENTS.md). Keep this under ~120 lines; push depth into notes/. Written in cleanup Step 14 from notes/codebase-understanding.md + the hazard map + README. -->
