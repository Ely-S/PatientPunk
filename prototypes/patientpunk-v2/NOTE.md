# PatientPunk v2 prototype — archived for review

**Status: not integrated, not wired into the build. Preserved here for review only.**

## What this is
An orphaned, **local-only** "clean rewrite" scaffold of PatientPunk that was sitting at
`~/Projects/PatientPunk_v2` (created ~2026-04-07, around the SF hackathon) and had **never
been committed to git** — it existed nowhere but local disk. Salvaged onto this branch so
it's preserved and browsable before it's lost to a disk wipe.

It is **not** a checkout of any branch: none of these files (`src/patientpunk/*`, the Marimo
`apps/*`) appear in any ref of this repo. The only overlap with history was a stale
top-level `database_creation/` folder (Polina's early pipeline), which the main repo later
deleted in favor of `src/` — that stale half is **deliberately excluded here**.

## What's included
- **`src/patientpunk/`** — a properly packaged layout (a real Python package, vs. the main
  repo's flat `src/`): `corpus.py`, `db.py`, `models.py`, `schema.py`,
  `qualitative_standards.py`, `_utils.py`, plus `exporters/` and `extraction/` subpackages.
- **`apps/`** — three **Marimo** apps: `discover.py`, `explore.py`, `query.py` (an app-first
  UI take that the main repo doesn't have).
- **`pyproject.toml`** — for context (strict `mypy`, full `ruff` ruleset, marimo/typer deps).
- **`schema.sql`** + **`schemas/`** — same DB schema as the main repo.

## What's deliberately excluded
- The stale top-level `database_creation/` pipeline (superseded + deleted on `main`).
- A throwaway ~90 KB sample `patientpunk.db`.

## What to decide
The pipeline bits are historical (the main repo's `src/pipeline/` has moved well past this).
The parts with potential **forward value** are:
1. The **Marimo apps** (`apps/*.py`) — a UI/app-first direction not present in the main repo.
2. The **clean `src/patientpunk/` package structure** + strict typing config — if a future
   refactor wants a proper package layout, this is a starting point.

Review these two, decide keep/port/discard, then this branch can be deleted.
