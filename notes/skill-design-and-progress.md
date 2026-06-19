# Repo-Agnostic Cleanup Skill — Design + Progress Tracker

We are executing the 14-step cleanup sequence (see `cleanup-sequence-and-hazards.md`) on PatientPunk
**one step at a time, human-paced**, and *incrementally distilling* the reusable machinery into a
repo-agnostic Claude Code skill. PatientPunk is the proving ground; the skill must then work on:

- `C:\Users\leech\dr\plans\nodeai-rebuild-design\crates` (Rust / cargo)
- `C:\Users\leech\dr\dr-hiro` (server — likely TS/JS)
- `C:\Users\leech\dr\dr-hiro-client` (client — likely TS/JS; **cross-repo contract with dr-hiro**)
- `C:\Users\leech\minecraft-mcp` (likely TS/Node)

## 1. Skill identity

- **Working name:** `legibility-pass` (a.k.a. "codebase cleanup / AI-legibility pass").
- **Goal function:** transform a repo to be maximally legible to an AI agent (and humans) **without
  changing behavior or breaking interfaces.** Subtraction + clarification only.
- **Shape:** a multi-phase, verify-after-each-step, human-gated protocol that is *resumable across
  sessions*. NOT a single autonomous blast — it mirrors the "paste one prompt, review, continue" cadence.

## 2. Invariants (carried from the sequence analysis; these are the skill's backbone)

1. Behavior preservation — static-gate ladder green after every mutating step.
2. Interface-boundary protection — internal vs boundary names; boundaries frozen unless intended.
3. Dead ≠ unreferenced-in-repo — reachability oracle; quarantine before delete.
4. Propose → approve → apply for renames (human gate).
5. Atomic, reviewable commit per step.
6. Externalized, resumable state.
7. Fresh-context sub-agents both *find* and *evaluate*.
8. Don't fix behavior bugs mid-refactor — log them.

## 3. Phase structure (generalized from the 14 steps)

- **Phase 0 — Recon & Setup (skill adds this; required for repo-agnosticism).**
  - Detect stack + gate commands (build/test/lint/format/typecheck) by probing config & CI files.
  - Establish a **green baseline** *before* touching anything (else breakage isn't attributable).
  - Build the **boundary registry** (public API, CLI, env, schema, serialized formats, cross-repo consumers).
  - Branch + snapshot; create the progress tracker.
  - Deep-read the repo (a fan-out workflow like the one used here) → an architecture reference.
- **Phase 1 — Subtract** (PDF 1): delete dead/deprecated/thin-shim code, guarded by oracle + registry.
- **Phase 2 — Constants** (PDF 2): magic strings/numbers → named constants/enums in the right place.
- **Phase 3 — DRY** (PDF 3): consolidate similar logic; **respect boundaries** (never merge across
  intentionally-decoupled systems — flag cross-boundary duplication, ask).
- **Phase 4 — Subtract again** (PDF 4): clean up what 2–3 orphaned.
- **Phase 5 — Rename variables** (PDF 5–7): identify+understand → propose (no change) → apply (grep-verified no misdirection).
- **Phase 6 — Rename functions/params** (PDF 8–10): same 3-beat cadence.
- **Phase 7 — Rename classes/files + reorganize** (PDF 11): widest blast radius; fix imports/paths.
- **Phase 8 — Comment/docstring hygiene** (PDF 12).
- **Phase 9 — Research current best practices** (PDF 13): → `deep-research` skill.
- **Phase 10 — Self-onboarding + validate** (PDF 14): clean CLAUDE.md/AGENTS.md; fresh-context
  sub-agents evaluate comprehension; iterate. → `init` (CLAUDE.md) + `deep-guide` + Explore agents.

## 4. Repo-agnostic mechanics

- **Stack detection table** (probe these, learn the *actual* commands from config/CI, don't hardcode):
  | Marker | Stack | test / lint / format / typecheck |
  |---|---|---|
  | `pyproject.toml`/`uv.lock` | Python (uv) | `uv run pytest` / `ruff check` / `ruff format` / (mypy/pyright if configured) |
  | `Cargo.toml` | Rust | `cargo test` / `cargo clippy` / `cargo fmt` / `cargo check` |
  | `package.json` | TS/JS | `npm/pnpm/bun test` / `eslint` / `prettier` / `tsc --noEmit` |
  | `go.mod` | Go | `go test ./...` / `go vet` / `gofmt` / `go build` |
  Always read the repo's CI workflow to confirm the canonical gate commands.
- **Boundary detection** = the hard generalization. Sources: installable-package manifests (what's
  exported), CLI arg parsers, env-var reads, schema/migration files, serialization (JSON keys, CSV
  headers, protobuf/openapi), and **cross-repo** consumers (e.g. dr-hiro ↔ dr-hiro-client: a rename in
  the server API breaks the client). At minimum: enumerate exported symbols + ask before renaming them.
- **Resumability:** the progress tracker (§6) + the per-repo architecture reference are the externalized
  state. A fresh session reads them and continues at the first non-`done` step.
- **Composition with existing skills:** Phase 0 deep-read ≈ a Workflow fan-out; Phase 9 ≈ `deep-research`;
  Phase 10 ≈ `init` + `deep-guide` + Explore. The skill orchestrates rather than reinvents.

## 5. How the skill is built (incremental extraction)

Each step we run on PatientPunk, we ask: *what part of that was repo-specific vs reusable?* The
reusable part (the prompt template, the gate-runner, the boundary check, the grep-for-misdirection
verifier, the fresh-agent evaluator) gets distilled toward `SKILL.md` + supporting scripts. By the time
we finish PatientPunk, the skill should be runnable against the other four repos with only Phase-0
re-detection.

## 6. Progress tracker (the resumable state — UPDATE AFTER EVERY STEP)

Status legend: `pending` · `in-progress` · `done` · `skipped` · `blocked`.
Working branch: `cleanup/legibility-pass` (off `repo-meta-and-docs-cj`). Commit per step.
Gate: `PYTHONUTF8=1 uv run pytest tests/ variable_extraction/tests/ -q` → must hold at **63 passed**.
Lint watch: `uv run ruff check .` total must not rise (baseline 171 → now 161).

| Step | Description | Status | Commit | Notes |
|---|---|---|---|---|
| 0 | Recon: read PDF, deep-read repo, build hazard map, scaffold notes | done | `6cc6820` | Workflow `wf_0f707536-71a`. |
| 1 | Delete dead/deprecated/thin shims (pass 1) | done | `63c93d8` | Workflow `wf_92192192-1a5`. Deleted 3 dead internal symbols + 10 unused imports + stray `test` file. 171→161 ruff, 63 tests green. Deferred items below. |
| 2 | Magic strings/numbers → constants/enums | pending | — | Watch boundary *values* (§D2) — don't "constant-ize" a frozen string into a renamed symbol carelessly. |
| 3 | DRY similar logic | pending | — | **Do NOT merge cross-boundary dup (§D3).** |
| 4 | Delete dead code (pass 2) | pending | — | Re-scan after 2–3. |
| 5 | Identify private/inner variables + usage | pending | — | |
| 6 | Propose best variable names (no change) | pending | — | Human review gate. |
| 7 | Apply variable renames (no misdirection) | pending | — | grep old names after. |
| 8 | Identify functions/params + usage | pending | — | |
| 9 | Propose best function/param names (no change) | pending | — | Human review gate. |
| 10 | Apply function/param renames | pending | — | grep old names; watch CLI flag boundary. |
| 11 | Rename/reorganize unclear classes & files | pending | — | Widest blast radius; `patientpunk` public API is a boundary. |
| 12 | Clean up comments/docstrings | pending | — | Stale-doc targets in §D5. |
| 13 | Deep-research latest CC-comprehension techniques | pending | — | Use `deep-research`. |
| 14 | Make repo self-legible; clean CLAUDE.md; fresh-agent eval | pending | — | Use `init` + `deep-guide` + Explore. |

**Operating protocol:** do ONE step per go-ahead, run gates, commit, update this table, then stop and
report. Do not chain steps without the user's signal (mirrors the "one prompt at a time" design).

### Deferred dead-code items (revisit at Step 4, the second dead-code pass)
The Step-1 adversarial gate deliberately kept these; they're judgment calls, not mechanical dead code:
- **`app/__init__.py` (0 bytes) + `[dependency-groups] ui` (streamlit/plotly) in pyproject** — roadmap
  scaffolding for the unbuilt web UI documented in `docs/MVP_PLAN.md`. Deleting is a *product* decision.
  → ask the user.
- **`src/pipeline/canonicalize.py:main()` and `classify.py:main()`** — real but vestigial `__main__` CLI
  entry points that can't actually persist (`db_path='.'`, `writer=None`). Delete-vs-fix decision.
- **F841 unused locals** (`extract.py:batches_since_save`, `pipeline.py:ext_result`,
  `discover_fields.py:regex_fields`, `extract_biomedical.py:ext_count`, `llm_extract.py:reason`) —
  likely **bug symptoms** (computed-but-dropped values). Removing them would mask the bug → handle in a
  separate behavioral pass, not here.

### Skill learnings harvested this step (toward the repo-agnostic skill)
- **Green-baseline gotcha:** on Windows, `tests/populate_db_test.py` dies reading `schema.sql` (UTF-8
  box-drawing) under cp1252. Neutralized with `PYTHONUTF8=1` (no code change). The skill's Phase-0 must
  detect encoding/locale gate failures and pin an env that yields a *truly* green baseline before edits.
- **Cross-reference the linter with the agent hunt:** ruff's `F401/F811/F841` are deterministic dead-code
  oracles that catch things the LLM finders/verifiers miss (e.g. an unused import the verifier kept by
  conflating "used in another module"). Run the linter's dead-code rules as a second, authoritative finder.
- **"Verify live twins survive":** when deleting a symbol that has same-named copies elsewhere
  (`call_haiku`, `META_COLUMNS`), assert post-deletion that the dead one is gone AND the live ones remain.
- **Prefer the linter's safe autofix** (`ruff --select F401 --fix`) for mechanical removals over hand-edits;
  it also cleans imports newly orphaned by function deletions (cascade).
