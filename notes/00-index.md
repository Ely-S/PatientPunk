# notes/ — Codebase Cleanup Effort (index)

We are running the 14-step "Claude Code Codebase Cleanup" sequence on PatientPunk **one step at a
time, human-paced**, and incrementally building a **repo-agnostic cleanup skill** from it.

Read these in order:

1. **`codebase-understanding.md`** — verified architecture reference (from a 13-agent deep-read).
   Read this so we never re-run that workflow. The §2 "two decoupled systems" fact is load-bearing.
2. **`cleanup-sequence-and-hazards.md`** — the 14 steps verbatim, the logic of their ordering, the
   safety invariants, and the **PatientPunk-specific hazard map** (boundaries that must NOT be
   renamed/deleted, duplication that must NOT be DRYed, real dead code, stale docs, behavior bugs to
   log-not-fix, and this repo's gate commands). **Read before executing any step.**
3. **`skill-design-and-progress.md`** — the repo-agnostic skill design + the **progress tracker**
   (the resumable state — update after every step). Other target repos listed there.

## Current status (2026-06-19)
- Step 0 (recon/setup) **done**: PDF read, repo deep-read, hazard map built, notes scaffolded.
- Steps 1–14 **pending**. Awaiting the user's go-ahead to begin Step 1.

## Operating protocol
ONE step per go-ahead → run gates (`uv run pytest tests/ variable_extraction/tests/ -v`, `ruff`) →
commit → update the tracker → stop and report. Never chain steps without the user's signal.
Behavior-preserving only: log behavior bugs, don't fix them mid-cleanup. Notes are currently
uncommitted (no commits made without the user asking).
