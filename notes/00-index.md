# notes/ — index

A 14-step "Claude Code Codebase Cleanup" (a behavior-preserving legibility pass) was **completed on 2026-06-19**;
63 tests stayed green throughout. The reusable machinery from it became a personal skill (`legibility-pass`).

## Onboarding to the code? Read these (and nothing else here):
1. **`/CLAUDE.md`** (repo root) — start here: the two-system architecture, commands, the gate, gotchas.
2. **`codebase-understanding.md`** — the verified architecture reference + the §8 "where do I look for X" index.
3. **`cleanup-sequence-and-hazards.md`** — the **hazard map**: frozen boundaries (§D2), intentional duplication that
   must NOT be merged (§D3), and real bugs that are *logged, not fixed* (§D6). Read before changing anything risky.

That's it for understanding the codebase. The two files above + CLAUDE.md are the evergreen reference.

## `archive/` — completed-cleanup process artifacts (NOT needed for onboarding)
Per-step inventories/proposals + the skill design, kept only for provenance of how the cleanup was done:
`step5/6` (variable rename cadence), `step8/9` (function rename cadence), `step11` (class/file plan — empty surface),
`step13` (AI-legibility research), and `skill-design-and-progress.md` (the per-step learnings + tracker that became
the `~/.claude/skills/legibility-pass/` skill). Safe to ignore unless you're studying the cleanup itself.
