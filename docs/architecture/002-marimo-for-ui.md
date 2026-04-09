# ADR-002: Marimo for interactive UI over Streamlit/Gradio

**Status:** Accepted
**Date:** 2026-04-07
**Deciders:** Shaun

## Context

The project needs an interactive interface for three tasks:

1. Querying treatment outcomes (drug/condition/demographics filters)
2. Exploring pipeline CSV outputs (filterable table viewer)
3. Selecting inductively-discovered variables (checkbox picker + merge)

Options considered: Streamlit, Gradio, Jupyter + ipywidgets, Marimo.

## Decision

Use Marimo for all three apps.

Key factors:

- **Git-friendly:** Marimo apps are plain .py files with no JSON cell metadata.
  They diff cleanly and review like normal code.
- **Reactive:** Cell dependencies are tracked automatically. Changing a
  dropdown re-runs only downstream cells.
- **Dual mode:** `marimo edit` for development (notebook UI), `marimo run`
  for end-user mode (no code visible).
- **No server state:** Each browser tab is an independent session. No shared
  server state to manage.

## Consequences

- `marimo>=0.9` becomes a project dependency.
- Apps live in `apps/` as standalone .py files.
- Apps use `sys.path.insert` to reach `src/patientpunk` during development;
  this goes away once the package is pip-installed.
