---
paths:
  - "variable_extraction/**"
---
# Track B — `variable_extraction/patientpunk` (file-only, installable)

You're editing the `patientpunk` package: wide clinical-**variable** extraction that writes FILES only
(`records.csv` + a codebook). It is the **only installable package** — `__init__.py` exports are public API.

- **Decoupled from `src/`** — do NOT `import sqlite3`, reference `treatment_reports`, or import from `src/`.
  The duplicated LLM shim (`patientpunk/_utils.py`) and the pydantic `PipelineConfig` are intentionally
  separate from the src versions; never "DRY"-merge them.
- The 7 subprocess scripts under `patientpunk/scripts/` are referenced by `_SCRIPT` filenames — those
  filenames are frozen. `scripts/extract_biomedical.py` is deliberately stdlib-only.
- Note: there are two unrelated classes named `PipelineConfig` (this one is pydantic; src's is a dataclass).
- Gate: `PYTHONUTF8=1 uv run pytest tests/ variable_extraction/tests/ -v` (target 63 passed).

Full context: `/CLAUDE.md` + `notes/codebase-understanding.md`.
