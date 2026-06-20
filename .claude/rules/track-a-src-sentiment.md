---
paths:
  - "src/**"
---
# Track A — `src/` drug-sentiment pipeline (SQLite)

You're editing the `src/` system: the drug-**sentiment** pipeline (extract → canonicalize → classify)
that owns `schema.sql` and the SQLite DB. It is NOT an installable package (it sits on the pytest `pythonpath`).

- **Decoupled from `variable_extraction/`** — do NOT `import patientpunk` here. The duplicated LLM-provider
  shim (`src/utilities/__init__.py`) and the `PipelineConfig` dataclass are intentionally separate from the
  patientpunk versions; never "DRY"-merge them.
- `treatment_reports` rows are written only when `signal != 'n/a'` (the silent drop is intentional).
  `import_posts.strip_reddit_prefix()` must run BEFORE the `parent_id`-nulling `UPDATE`.
- Frozen: DB table/column names, JSON cache keys (`tagged_mentions.json`, `drugs_direct`, …), CLI flags.
- Gate: `PYTHONUTF8=1 uv run pytest tests/ variable_extraction/tests/ -v` (target 63 passed).

Full context: `/CLAUDE.md` + `notes/codebase-understanding.md`.
