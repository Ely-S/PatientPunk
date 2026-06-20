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
| 2 | Magic strings/numbers → constants/enums | done | `0066153` | Workflow `wf_ddcd00cd-fa2` (39 candidates → 16 extract). Applied ~12 constants (4 src/, 2 Scrapers, 6 variable_extraction); dropped 4 as over-extraction/enum-modeling. 63 green, ruff 161→159. |
| 3 | DRY similar logic | done | `618be3a` | Workflow `wf_313cd4bc-9a5` (60 clusters → **4 dry, 36 surfaced, 20 leave**). Applied 4 within-system DRYs; surfaced the intentional-duplication registry (§D3). 63 green, ruff 159. |
| 4 | Delete dead code (pass 2) | done | `e96a6cb` | Workflow `wf_defc3f44-e36` (fresh sweep found 0 new dead code — Steps 1-3 were clean). Resolved deferred items per user: deleted app/+ui group (uv.lock regenerated), the broken canonicalize/classify `main()`s, and the 5 F841 dead locals + SAVE_EVERY. 63 green, ruff 159→154, F841 0. |
| 5 | Identify private/inner variables + usage | done | (notes only) | Workflow `wf_9a72256e-bca`. Read-only inventory → `notes/step5-variable-inventory.md`. Codebase is well-named: ~3 cryptic attrs + ~27 candidate locals out of ~700. No code change, no gate. Feeds Step 6. |
| 6 | Propose best variable names (no change) | done | (notes only) | Workflow `wf_dc08ce88-bcd`. Proposal in `notes/step6-rename-proposal.md` — 30 renames, critic-APPROVED (0 collisions/boundary/param/missed-site issues). `td` deferred to Step 8; `D`/`Xa`/`sims` left. No code change. Review gate. |
| 7 | Apply variable renames (no misdirection) | done | `d10d3a8` | Workflow `wf_ae74cb2e-9ac` (1 agent/file). 30 renames across 16 files; +149/-149 (pure). 63 green, ruff 154, 0 misdirection, 0 over-reach. Variable cadence (5→6→7) COMPLETE. |
| 8 | Identify functions/params + usage | done | (notes only) | Workflow `wf_c4c4418e-4ce`. Inventory → `notes/step8-function-param-inventory.md`. Naming is good: ~13 fn + ~3 param candidates of ~284, all private internals. Critic-verified frozen boundary (public API/CLI/subprocess/serialized). No code change. Feeds Step 9. |
| 9 | Propose best function/param names (no change) | done | (notes only) | Workflow `wf_7d5033a1-cdc`. Proposal in `notes/step9-function-rename-proposal.md` — ~15 renames, critic-SAFE (0 collisions/frozen/test/weaker). call_haiku→call_model aligned; same-name copies distinct; nnt/k cosmetic. No code change. Review gate. |
| 10 | Apply function/param renames | pending | — | grep old names; watch CLI flag boundary. |
| 11 | Rename/reorganize unclear classes & files | pending | — | Widest blast radius; `patientpunk` public API is a boundary. |
| 12 | Clean up comments/docstrings | pending | — | Stale-doc targets in §D5. |
| 13 | Deep-research latest CC-comprehension techniques | pending | — | Use `deep-research`. |
| 14 | Make repo self-legible; clean CLAUDE.md; fresh-agent eval | pending | — | Use `init` + `deep-guide` + Explore. |

**Operating protocol:** do ONE step per go-ahead, run gates, commit, update this table, then stop and
report. Do not chain steps without the user's signal (mirrors the "one prompt at a time" design).

### Deferred dead-code items — RESOLVED in Step 4 (`e96a6cb`) per user decisions
- **`app/` + `[dependency-groups] ui`** — DELETED (web UI not being scaffolded). uv.lock regenerated.
- **`canonicalize.main()` / `classify.main()`** — DELETED (one crashed, one discarded output); live
  `run_*` functions kept; orphaned imports + stale docstring cleaned.
- **F841 unused locals** — dead assignments REMOVED (user chose strict removal over leave); the
  underlying dropped-diagnostic bugs are now recorded in hazards §D6 (no longer flagged in code).

### Step 2 deferred / left-inline (judgment calls, with reasons)
- **`source` field enum** (`"llm_discovered"`/`"base"`/`"base_optional"`/`"extension"`, ~13 sites) —
  left inline; this is enum-modeling (and `"base"` is overloaded 3 ways), better as a dedicated typed
  constant group than a single magic-literal extraction. Candidate for a focused follow-up.
- **Function-signature defaults** (`max_chars=500`, `max_posts=10`, `sep=" | "` ×9) — kept inline:
  a parameter default is self-documenting at the signature; relocating forces an import-chase.
- **JSON record keys** (`drugs_direct`/`drugs_context`) — kept inline; the maintainers extracted
  filenames but not keys, and naming them makes the schema-defining dict literals less JSON-shaped.
- **RCT `SIG_RANK`/`DRUG_CUTOFFS`/`END_2022_EXCLUSIVE`** — already constants; cross-`src/`↔`RCT`
  consolidation is forbidden (intentional self-containment). SQL `'deleted'` sentinels stay in-query.

### Step 9 skill learnings (toward the repo-agnostic skill)
- **Make misleading names honest, not just shorter→longer**: a function returning a rate-float (`_hit`) or a
  cleaned-string (`_keep`) must NOT read like an `is_x` predicate. The best function name encodes the RETURN.
- **Name to expose a shape difference, not hide it**: the `_eq`/`_other`/`_presence` trio (2 factories + 1 bare
  predicate) → `_value_match`/`_has_other` (builders) vs `_has_any` (direct test).
- **Cross-module alignment is a naming win**: `call_haiku`→`call_model` matches a sibling that does the same
  role — but alignment is name+role only, NOT a directive to unify signatures or merge the functions.
- **Same-name/different-body copies get DISTINGUISHING names** (`_code_demographics_batch_raw` vs
  `_extract_demographics_batch_raw`; `merge_records`→`fill_empty_fields`), and the canonical/frozen copy is left.
- **A param's call-site cost depends on how it's called**: renaming a param only touches the def + body + any
  KEYWORD call sites — POSITIONAL callers (`_trial_tag(r[...])`) need no edit. And watch r-string/notebook code:
  the test gate doesn't cover string content, so those edits need manual eyeballing.

### Step 8 skill learnings (toward the repo-agnostic skill)
- **Function/param renaming has a WIDER frozen boundary than variables.** The killer surface here is the
  installable package's public API — exported functions/classes AND the **public methods of exported classes**,
  plus keyword-arg names of public/multi-caller functions (a keyword call is a contract), CLI flag/subcommand
  strings, subprocess **script filenames**, serialized pydantic fields, and **test-imported** functions. Read
  `__init__.py` (+ sub-package `__all__`) first; a boundary-accuracy critic must verify nothing frozen slipped in.
- **A param's freedom follows its function's boundary** — `fmt` looked renameable but its function is a public
  exporter class, so it's a frozen keyword+CLI contract. Conversely `eid`/`fdata` are free because they're a
  *closure* param / a private helper's param (not the public function's kwarg) — precision matters.
- **Naming smells cluster into patterns**, not noise: predicate-shaped-non-predicates, generic verbs, and
  misleading provider labels (`call_haiku` for a provider-agnostic `MODEL_FAST` call). Reporting the *patterns* is
  more useful to Step 9 than a flat list.
- **Same-name/different-body functions are an inconsistency to flag, NOT a duplication to merge** — the test
  imports pin which copy is canonical; the others are independent. Distinguish "give them distinct names" from "DRY".

### Step 7 skill learnings (toward the repo-agnostic skill)
- **A safe rename needs a verification TRIFECTA, not one check:** (1) no-misdirection grep — old whole-word
  tokens are GONE; (2) over-reach grep — frozen substrings are still INTACT (grep-for-absence alone misses a
  `data`→`response` that mangled `metadata`); (3) the gate (pytest + ruff-unchanged + py_compile). Renames are
  pure → **ruff total must be UNCHANGED** (154→154) and the diff symmetric (+149/−149); any drift = a mistake.
- **Whole-word + per-scope discipline is everything** for local-variable renames. Short/substring-prone names
  (`data`, `sub`, `av`, `pa`, `prov`, `rel`, `tagged`) demand context-bounded edits, never bare replace_all.
- **One agent per file parallelizes safely** (disjoint files = no conflicts, no worktree needed) — and agents
  enforce the no-misdirection rule better than a static plan (one caught a 4th `to_do` in a log f-string the
  proposal's site list missed, and renamed comment references too).
- **Legit survivors are expected** — distinguish a renamed variable's old token appearing as English prose
  (help text), a *different* out-of-scope variable of the same name, or display-label text, from real misdirection.

### Step 6 skill learnings (toward the repo-agnostic skill)
- **Step 6 (propose names) is ALSO read-only — it's the review gate.** Separating "decide the name" from
  "apply the rename" lets a human (or a critic) veto bad names before they're sprayed across the codebase.
  The deliverable is a `current → proposed` doc, not a diff.
- **A good namer LEAVES well enough alone**: conventional notation (`D`/`Xa`/`sims`), and names that are
  already fine, should be recommended "leave". Over-renaming is the Step-2-style failure mode here too.
- **Collision-check every proposed name against its scope BEFORE proposing** — the namer caught `av`
  colliding with an existing `allowed_values` and proposed `member_allowed_values` instead.
- **Reconcile cross-module/mirror names to ONE choice** and list *all* sites (the `mn`/`mx`/`rel`
  verify↔notebook mirror, `ne_items`↔`non_empty_items`, `tagged` across two files) so Step 7 changes them together.
- **Catch scope leaks**: a function PARAMETER (`td`) is Step-8 work, not a Step-6 variable — defer it.
  And rename the loop var alongside its collection (`cat` with `cats`).

### Step 5 skill learnings (toward the repo-agnostic skill)
- **The rename cadence (5→6→7) separates identify / name / apply — Step 5 is READ-ONLY** (inventory). No
  mutation → no test gate; the deliverable is a committed catalog, not a diff. Keep the beats separate.
- **Inventory the rename CANDIDATES, not every variable.** The value is the bounded unclear-name list; skip
  idiomatic short vars (`i`/`e`/`f`/`c`/`d`) and clearly-named locals (count them, don't list them). A
  well-factored repo has a tiny rename surface (here ~30 of ~700 locals).
- **The killer trap: underscore-prefixed NAMES vs underscore-prefixed serialized KEYS.** `_temp` (a private
  attr, rename-eligible) vs `_patientpunk_version`/`_skipped`/`__provenance` (frozen JSON/CSV keys). Also
  string-template pseudo-globals in generated notebooks (`_DB_FILENAME` inside r-strings) are not source vars.
  Misclassifying a frozen key as a rename target would break a contract in Step 7.
- **Run a boundary-accuracy critic on the inventory itself** — it caught a phantom attribute (`_client` vs
  the real `_c`) and a "file doesn't exist" error before Step 7 could act on bad info.
- Note cross-module/shared-local names and self-contained-copy mirrors so Step 7 renames *all* usages.

### Step 4 skill learnings (toward the repo-agnostic skill)
- **The second dead-code pass is mostly about the judgment calls, not new finds.** If Steps 1-3 cleaned
  orphans inline (re-run the linter's F401/F811 after each), the fresh sweep finds ~nothing (here: 0).
  The value of Step 4 is *resolving* what Step 1 deferred — so carry a deferred-items list forward.
- **Surface roadmap/product decisions to the human** (AskUserQuestion), don't infer them: deleting
  `app/`+the `ui` group is a roadmap statement; the user owned it.
- **"Broken" beats "runnable" for deadness**: a `main()` that *crashes* or *discards all output* is
  deprecated/dead even though Step 1's gate kept it as a "runnable entry point." Verify functional-vs-broken.
- **Removing a bug-flag relocates the bug record** — when you delete a dropped-value local that flagged a
  latent bug, move that knowledge to the notes so it isn't lost (§D6).
- **Editing pyproject deps means regenerating the lockfile** (`uv lock`) or CI's `--locked` install breaks.
  Deleting a function orphans imports → autofix F401 after.

### Step 3 skill learnings (toward the repo-agnostic skill)
- **On an intentional-duplication repo, DRY is mostly inapplicable — and a short apply-list is the
  CORRECT outcome.** Here: 60 clusters → 4 applied, 36 surfaced as do-not-merge. The deliverable is as
  much the *map of intentional duplication* as the consolidations. Don't force DRY to hit a quota.
- **Near-identical ≠ mergeable.** Always diff near-duplicates before merging; subtle divergences (the two
  LLM abstractions differ in ≥5 behaviors) mean a merge would silently change behavior. Only `dry` when
  the consolidation is byte-for-byte preserving for EVERY call site.
- **Respect architectural boundaries over textual similarity**: decoupled systems, self-contained
  reproducibility packages, and subprocess-independent / stdlib-only modules are duplication-by-design.
- **Naming-collision check when consolidating**: don't reuse a name that already means something else in
  the package (`META_COLUMNS` was taken with a different value → used `META_SKIP_COLUMNS`).
- **Extracting a code block can orphan imports** (here `json`/`time`): re-run the linter's unused-import
  pass after each DRY. And remember keyword-only defaults live in `__kwdefaults__`, not `__defaults__`.

### Step 2 skill learnings (toward the repo-agnostic skill)
- **Over-extraction is the #1 failure mode**, not breakage. Bias to LEAVE; extract only on repetition
  (drift risk) OR non-obvious domain meaning. A linter-clean codebase already names most constants, so
  the real surface is small (here: 39 candidates → 16 → ~12 applied). Budget ~15–40, not hundreds.
- **Resolve verdict conflicts with taste**: independent adjudicators disagreed (extract `500` vs leave
  its twin `10`; extract `" | "` vs leave it). The tie-breaker is "is the value self-documenting where
  it sits?" — parameter defaults and SQL-context values usually are.
- **Runtime-import test after cross-module constant moves**: `py_compile` does NOT execute imports, so
  it misses cycles/missing-names introduced by new `from ._utils import X` lines. Add an explicit
  `importlib.import_module` + value-assertion probe (catches what the unit tests don't import).
- **Home shared constants at the import-graph bottom** (`_utils.py` here) to make cross-module sharing
  cycle-proof; use `import X as _X` to consolidate a private-named local without touching its usages.
- **Preserve "stdlib-only by design" modules**: don't add a package import just to share a constant
  (left `extract_biomedical.py`'s `"2.0"` inline rather than wire it to `_utils`).

### Skill learnings harvested in Step 1 (toward the repo-agnostic skill)
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
