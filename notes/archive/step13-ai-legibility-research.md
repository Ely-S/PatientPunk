# Step 13 — Making PatientPunk Legible to Claude Code (research → the Step-14 plan)

> Deep-research artifact (no code change). Workflow `wf_e5e6877a-7c4`: 5 web-research agents
> (`claude-code-guide` for the CC-specific topics) → synthesis → adversarial fact-check.
> **Fact-checker verdict: NO hallucinations / critical errors — all cited URLs are real Anthropic docs;
> all core claims web- or repo-verified.** §6 is the payload Step 14 executes.
> Legend: **[WEB]** cited URL · **[KB]** knowledge/community, not primary-source · **[REPO]** verified against this tree.
> Caveats: auto-memory `v2.1.59+` is version-sensitive; the "auto-gen ~3-4% worse / ~40% time wasted" figures are
> [KB] directional only; re-check the gitignore state + `CLAUDE_CODE_NEW_INIT` against the installed CC version.

## 1. TL;DR — highest-leverage techniques
1. **Write a lean root `CLAUDE.md` (<200 lines, target ~80–120)** — loads into context every session, survives `/compact`; the #1 lever, and PatientPunk has none. **[WEB]**
2. **Lead with exact gate commands** — `uv run pytest tests/ variable_extraction/tests/ -v` + `ruff check .`. **[WEB][REPO]**
3. **Make the "TWO decoupled systems" fact the load-bearing top line** — `src/` SQLite sentiment vs `variable_extraction/patientpunk` file-only; never DRY-merge their duplicated LLM-provider code or the two same-named `PipelineConfig`. **[REPO]**
4. **Include only what Claude can't infer; reference the rest** — `@README.md`; point to `notes/`; exclude standard Python conventions + file-by-file walkthroughs. **[WEB]**
5. **Reuse the existing "Where do I look for X" map** (`notes/codebase-understanding.md` §8) → orient in 1–3 reads, not 15–20 greps. **[WEB][REPO]**
6. **Document verified gotchas as guardrails** — the CI not-collected gotcha, must-stay-in-sync duplication, import-time config, silent row-drop on `signal=='n/a'`. **[WEB][REPO]**
7. **Validate with a fresh-context sub-agent comprehension eval** — the Step-14 acceptance test. **[WEB]**
8. **Hand-craft, don't trust auto-gen** — `/init` for a skeleton, then prune + hand-merge from the verified notes. **[WEB][KB]**

## 2. CLAUDE.md — the single most important artifact
- **What it is:** Markdown read **in full into context at session start** (a user message after the system prompt); re-read from disk after `/compact`. A *behavioral contract* (advisory; use hooks for hard enforcement). Carries facts the agent would otherwise re-derive or get wrong. **[WEB]** (code.claude.com/docs/en/memory, /best-practices)
- **Where:** `./CLAUDE.md` at repo root, **checked into git** (also `./.claude/CLAUDE.md`; `~/.claude/CLAUDE.md` user-global; `CLAUDE.local.md` gitignored personal overrides). **[WEB]**
- ⚑ **[REPO] CRITICAL:** `.gitignore` (lines 48–51, commit `0fbc78e`) ignores `.cursorrules`, `AGENTS.md`, **`CLAUDE.md`**. Step 14 **must `git add -f CLAUDE.md`** (or amend the ignore) or the artifact won't travel with the repo.
- **Recommended sections** (scannable headers + bullets, not prose): Project overview (one line + `@README.md`); **Architecture — two decoupled systems** (`IMPORTANT`, + pointer to `notes/codebase-understanding.md`); How-to-run (`uv run …` only; `uv sync`; `mkdir -p data && sqlite3 data/posts.db < schema.sql`); Gate commands (explicit pytest paths + ruff + the RCT `verify.py` gate); Where-to-look (condensed §8 index); Conventions; **Hard rules / Gotchas** (`YOU MUST`/`IMPORTANT` on the few non-negotiables).
- **Conciseness:** target ~80–120 lines. Anthropic: *"Bloated CLAUDE.md files cause Claude to ignore your actual instructions."* Litmus per line: *"Would removing this cause Claude to make a mistake?"* — if no, cut. `IMPORTANT`/`YOU MUST` sparingly (raises salience). HTML comments `<!-- … -->` are stripped before Claude sees them → maintainer rationale at zero token cost. **[WEB][KB]**
- **`@import`/hierarchy:** `@path` expands + loads **in full at launch** (depth ≤4; paths in code fences skipped) → DRY, but **no context savings vs inlining**. So: `@README.md` (strong, ~existing), but only a **one-line pointer** to `notes/codebase-understanding.md` (~140 lines — don't import in full). Optional per-subdir `CLAUDE.md` (on-demand) + `.claude/rules/*.md` with `paths:` glob frontmatter (load only when matching files touched). **[WEB]**

## 3. Other Claude-Code affordances — verdicts for PatientPunk
| Affordance | Verdict | Why |
|---|---|---|
| `/init` | **Use, then prune** | Structure-grounded skeleton (detects uv/pytest/ruff + the two packages); hand-merge the notes over its guesses; never ship raw auto-gen. **[WEB][KB]** |
| `/memory` | **Use for debugging** | Confirms which instruction files are loaded + order. **[WEB]** |
| Auto `MEMORY.md` | **Leave on (default, v2.1.59+)** | Machine-local; complements (not replaces) the git-tracked CLAUDE.md. **[WEB]** |
| `.claude/rules/` (path-scoped) | **Add — strong fit** | Two rules: `src/**` (SQLite-owned, never import `patientpunk`) and `variable_extraction/**`+`patientpunk/**` (file-only, only installable pkg, never import `sqlite3`). Keeps Track-A/Track-B context separate. **[WEB]** |
| Sub-agents `.claude/agents/` | **Add one** | A read-only `fresh-context-navigator` for the §6 comprehension eval. **[WEB]** |
| Skills `.claude/skills/` | **Add for runbooks** | `run-sentiment-pipeline`, `rct-reproduce` as on-demand procedures; CLAUDE.md names them. Extends the existing root `SKILL.md`. **[WEB][REPO]** |
| Settings / Hooks | **Follow-on, not Step 14** | Deterministic enforcement candidates: a Stop-gate (`ruff && pytest`); a PreToolUse deny on cross-system imports. Out of the legibility scope. **[WEB]** |
| `AGENTS.md` | **Not needed now** | Claude Code reads **`CLAUDE.md`, not `AGENTS.md`**. Single-agent scope → one `CLAUDE.md`. (If ever needed: `@AGENTS.md` import — Windows-safe vs symlinks needing Admin.) **[WEB][REPO]** |
| MCP semantic index | **Skip** | Repo is small + well-mapped. **[KB]** |

## 4. Codebase-level legibility — what PatientPunk already satisfies
The practices all serve the **context budget**: an architecture map + "where to look" index (turns 20–40% context-burning grep hill-climbing into 1–3 jumps), clear entry points/boundaries/naming, docstrings + type hints (the machine-readable interface), tests-as-spec + a runnable gate, no huge files. **[WEB][KB]**

PatientPunk **already satisfies most** [REPO] — Steps 1–12 did the work: near-empty rename surface (well-named); the architecture reference (`notes/codebase-understanding.md` incl. §8 index + the two-systems fact) and hazard map (`notes/cleanup-sequence-and-hazards.md`) already exist as pre-digested CLAUDE.md fuel; clean uv/pytest/ruff toolchain; dead code + stale docstrings pruned. **The one missing piece is the agent-facing entry layer — `CLAUDE.md` + scoped rules + the eval. That is exactly Step 14.**

## 5. Anti-patterns → mapped to PatientPunk
- **Bloated CLAUDE.md** → write it lean; push depth into notes.
- **Stale/contradictory docs** (present: `Scrapers/*.md`, `docs/MVP_PLAN.md`, `docs/ldn_notes.md`) → banner or prune; make CLAUDE.md the single source of truth. (Step 12 fixed the in-code doc-rot; MVP_PLAN/ldn_notes remain historical.)
- **Undocumented gate** → put exact commands in. **CRITICAL gotcha [REPO]:** CI runs bare `uv run pytest -v` + `testpaths=["variable_extraction/tests"]`, so the root e2e `tests/` is **NOT default-collected** — green CI doesn't exercise the SQLite pipeline; pass explicit paths (`pythonpath=["src"]` resolves imports).
- **Name collisions** → the two unrelated `PipelineConfig` classes; document which file owns which.
- **Hidden coupling / intentional duplication** → a "Things that must change together" section (LLM-provider abstraction src vs patientpunk; `SIG_RANK`/`DRUG_CUTOFFS`/`EXPECTED_OUTPUTS`; `find_parent_cycles` inlined in verify.py).
- **Non-obvious behaviors fixed as "bugs"** → document as do-not-change/out-of-scope: silent row drop on `signal!='n/a'`; `strip_reddit_prefix()` must run BEFORE the `parent_id` UPDATE; import-time LLM config (`OPENROUTER_API_KEY → ANTHROPIC_API_KEY`; `LLM_PROVIDER` overrides; `openai` needs explicit models or `src/` exits at import); known real bugs are log-not-fix (§D6).

## 6. THE STEP-14 ACTION PLAN (ordered checklist — the payload)
1. **`/clear` first** — fresh context, clean CLAUDE.md load. **[WEB]**
2. **Run `/init`** for a structure-grounded skeleton (draft only). **[WEB]**
3. **Write the root `CLAUDE.md`** (~80–120 lines, hand-crafted) with the §2 sections, drawn from `notes/codebase-understanding.md` + `README.md` + `cleanup-sequence-and-hazards.md`. Opener = the two-decoupled-systems fact (`IMPORTANT`).
4. **Confirm CLAUDE.md is COMMITTED** — `git add -f` (it's gitignored, commit `0fbc78e`); verify current `.gitignore` state. **[REPO]**
5. **Add two `.claude/rules/` files** with `paths:` frontmatter — `src/**` and `variable_extraction/**`+`patientpunk/**` (the decoupling guardrails).
6. **Add 1–2 Skills** (`.claude/skills/run-sentiment-pipeline`, `rct-reproduce`); CLAUDE.md points to them.
7. **Banner the stale historical docs** (`docs/MVP_PLAN.md`, `docs/ldn_notes.md`) with a top "STALE — see CLAUDE.md/notes" note (don't rewrite).
8. **Sub-dir CLAUDE.md? No** (rules cover it). **AGENTS.md? No** (single-agent).
9. **Fresh-context comprehension eval (acceptance test):** spawn a read-only sub-agent (no prior context); it answers from CLAUDE.md + notes alone:
   - "Explain the two decoupled systems — are they coupled?"
   - "Where does a drug-sentiment row get written, and what makes it silently skip?"
   - "Trace reply-chain context through extract→canonicalize→classify."
   - "What's the crash-recovery / append behavior?"
   - "What's the exact gate command, and what does CI's bare pytest miss?"
   - **Pass:** correct answers from a handful of targeted reads, no full-tree crawl. If it fails twice → CLAUDE.md is too vague/long/conflicting → refine + re-run. **[WEB]**
10. **Audit `/memory`** after the eval; fold durable misses back into CLAUDE.md.
11. **(Follow-on, not Step 14):** deterministic hooks (Stop-gate; cross-system-import deny).

## 7. Sources (web-verified primary — Anthropic)
code.claude.com/docs/en/{best-practices, memory, large-codebases, sub-agents, skills, commands, settings, how-claude-code-works}; claude.com/blog/building-agents-with-the-claude-agent-sdk; agents.md. (Community/secondary corroboration + the [KB]-flagged numeric claims are listed in the workflow output; treat non-primary claims as directional.)
