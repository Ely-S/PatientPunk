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
4. **`step5-variable-inventory.md`** — the inner/private-variable catalog (rename candidates + frozen
   boundary keys) produced by Step 5; the actionable input for Steps 6 (propose names) & 7 (apply).
5. **`step6-rename-proposal.md`** — the `current → proposed` name map (critic-approved); the exact
   instructions for Step 7 to apply. Includes cross-module/mirror sites and §6 flagged choices.
6. **`step8-function-param-inventory.md`** — the function/parameter rename candidates + the frozen
   public-API/CLI/subprocess/serialized boundary; the input for Steps 9 (names) & 10 (apply).

## Current status (2026-06-19)
- Step 0 (recon/setup) **done** (`6cc6820`): PDF read, repo deep-read, hazard map built, notes scaffolded.
- Step 1 (dead code, pass 1) **done** (`63c93d8`): 3 dead internal symbols + 10 unused imports + stray
  `test` file removed; 63 tests green, ruff 171→161. See tracker for deferred judgment-call items.
- Step 2 (magic literals → constants) **done** (`0066153`): ~12 constants across all 3 systems
  (4 src/, 2 Scrapers, 6 variable_extraction); 4 candidates deliberately left inline. 63 green, ruff 161→159.
- Step 3 (DRY) **done** (`618be3a`): 4 within-system consolidations applied; 36 cross-boundary clusters
  surfaced as intentional duplication (registry in hazards §D3). 63 green, ruff 159.
- Step 4 (dead code, pass 2) **done** (`e96a6cb`): fresh sweep found 0 new dead code; resolved the deferred
  judgment calls per user — deleted app/+ui group, the broken canonicalize/classify `main()`s, and the 5
  F841 locals + SAVE_EVERY. 63 green, ruff 159→154, F841 0.
- Step 5 (identify private/inner variables) **done** (notes only, no code change): inventory in
  `step5-variable-inventory.md` — ~3 cryptic attrs + ~27 candidate locals out of ~700 (codebase is well-named).
- Step 6 (propose names) **done** (notes only, no code change): `step6-rename-proposal.md` — 30 critic-approved
  renames; `td` deferred to Step 8; `D`/`Xa`/`sims` left. The review gate.
- Step 7 (apply variable renames) **done** (`d10d3a8`): 30 renames across 16 files (+149/−149, pure). 63 green,
  ruff 154, 0 misdirection, 0 over-reach. **Variable rename cadence (5→6→7) COMPLETE.**
- Step 8 (identify functions/params) **done** (notes only, no code change): `step8-function-param-inventory.md` —
  ~13 fn + ~3 param candidates of ~284 (all private internals); frozen boundary mapped.
- Steps 9–14 **pending**. Branch: `cleanup/legibility-pass`. Next: **Step 9** — propose the clearest names for the
  Step-8 candidates (review gate, no code change), then **Step 10** applies (function blast radius: call sites,
  the `patientpunk` public API frozen, same-name copies kept distinct not merged).

## Operating protocol
ONE step per go-ahead → run gates (`uv run pytest tests/ variable_extraction/tests/ -v`, `ruff`) →
commit → update the tracker → stop and report. Never chain steps without the user's signal.
Behavior-preserving only: log behavior bugs, don't fix them mid-cleanup. Notes are currently
uncommitted (no commits made without the user asking).
