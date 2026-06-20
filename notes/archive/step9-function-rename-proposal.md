# Step 9 — Function & Parameter Rename Proposal (current → proposed)

> **PROPOSAL ONLY — the review gate before Step 10. No code changed.** Workflow `wf_7d5033a1-cdc`
> (per-group namers → reconcile → boundary/collision critic). Critic verdict: **SAFE to proceed — 0 collisions,
> 0 frozen-API violations, 0 test-import freezes, same-name copies correctly distinct, no weaker names.**
> Critic line-number fixes folded in (⚑). Main-agent review: concur. Step 10 applies these (with §6 defaults) unless edited.

## 1. Summary
- **~15 renames proposed** (functions + params), **~45 call sites** + ~5 comment/docstring mentions to update.
- **Left as-is:** `_trial_tag` (name is fine), `k` (textbook k-of-n). **Cosmetic (string-literal):** `nnt` (rename = polish; "leave" defensible).
- Every candidate is a private/script-internal symbol — **no public-API / CLI / subprocess-filename / serialized / test-imported boundary touched** (critic-verified against `__init__.py` + the test file).

## 2. Function / helper renames
| current → proposed | scope | all sites to change together | why |
|---|---|---|---|
| **`_pf_key` → `_prefilter_key`** | private-helper | `classify.py` :41 def, :238, :262, :273 | only abbreviation of "prefilter" in a module that spells it out (`PREFILTER_PROMPT`, `_prefilter_one`) |
| **`_hit` → `_discovery_hit_rate`** | private-helper | `consolidate.py` :109 def, :128, :146 | returns a **rate float** (from `hit_rate_at_discovery`), not a bool |
| **`_keep` → `_clean_text`** | private-helper | `aggregate.py` :32 def, :58, :59, :66 | returns a **cleaned string** ("" to drop), not a keep? bool; deliberately ≠ the frozen `_keep_text` |
| **`_eq` → `_value_match`** | private-helper (**factory**) | `cluster_prep.py` :85 def, :118, :122 | closure factory → per-value predicate; signals predicate-builder, not equality |
| **`_other` → `_has_other`** | private-helper (**factory**) | `cluster_prep.py` :89 def, :123 | factory for the out-of-top-k "other" bucket; pairs with `_has_any` |
| **`_presence` → `_has_any`** | private-helper (**bare predicate**) | `cluster_prep.py` :93 def, :113 (passed directly) | the one bare predicate of the trio; `_has_any` vs the factories makes the shape difference visible |
| **`_invert` → `_build_surface_lookup`** | private-helper | `normalize.py` :128 def, :137 | builds the cleaned `{surface_form: canonical}` reverse lookup (inverts AND cleans keys) |
| **`_clean` → `_clean_surface`** | private-helper | `normalize.py` :35 def, :131, :133, :142 | over-generic `_clean` reads too close to public `normalize_*`; names the object + the pre-match op |
| **`call_haiku` → `call_model`** | function | `llm_extract.py` :164 def, :565, :588, :1255 (+ docstring mention `extract_demographics_llm.py` :189) | provider misnomer (model = provider-agnostic `MODEL_FAST`); **aligns with the sibling `call_model`** in discover_fields.py. Differing signatures are intentional — NOT a merge. |
| **`_call_haiku_batch_raw` → `_code_demographics_batch_raw`** | private-helper | `code_demographics_llm.py` :230 def, :288 | DISTINCT name for the **coding** copy (has `mode`, array path) |
| **`_call_haiku_batch_raw` → `_extract_demographics_batch_raw`** | private-helper | `extract_demographics_llm.py` :210 def, :302 (+ comment :62) | DISTINCT name for the **extract** copy (escalating-temp single-record retry, no `mode`) |
| **`merge_records` → `fill_empty_fields`** | function | `records_to_csv.py` :105 def, :209 | DISTINCT from `llm_extract.py:851 merge_records` (provenance reconciliation, left untouched). This one only fills empty cells. NOT a merge. |
| **`_walk` → `_collect_post_text`** | private-helper (closure) | ⚑ `variable_extraction/main.py` :750 def, :756 self-recursion, :759 driver | bare `_walk` conveys neither object nor output; names the per-`post_id` text index it builds |

## 3. Parameter renames
| current → proposed | location | sites | why |
|---|---|---|---|
| **`eid` → `post_id`** | closure `upstream(eid, …)` in `compute_upstream_mentioned_drugs`, `extract.py` :95 | :95 def, :98, :105 + ⚑ the `(eid, remaining)` docstring mention near :71 | the dicts it indexes are keyed on `post_id`; module never abbreviates to `eid`. Private closure param → free |
| **`fdata` → `field_def`** | param of private `_ext_row(fname, fdata)`, `make_codebook.py` :59 | :59 def, :61–71 body only (calls at :122/:133 are **positional** → no edit; the `fdata` in `build_field_registry` is a loop var, left) | one field-definition dict; matches house style. Borderline → recommend rename (§6.1) |
| **`td` → `trial_dir`** (deferred from Step 7) | param of `_trial_tag(td)`, `_build_paper_figures.py` :656 | ⚑ :656 def + :657 body ONLY — the caller `:661` is a **positional** `_trial_tag(r['trial_dir'])`, no edit | value is literally `r['trial_dir']`, the spelling used everywhere else. **See §7 (string-literal check).** |

## 4. Consistency notes (Step 10)
- **`call_haiku` → `call_model`**: name+role alignment with discover_fields' `call_model`; signatures stay divergent (intentional). `call_model` does not pre-exist in `llm_extract.py` → no collision.
- **Same-name/different-body copies kept DISTINCT, never merged:** the two `_call_haiku_batch_raw` → `_code_demographics_batch_raw` / `_extract_demographics_batch_raw`; `merge_records` (records_to_csv) → `fill_empty_fields` while `llm_extract.merge_records` is untouched.
- **Predicate trio**: `_value_match`/`_has_other` (factories) vs `_has_any` (bare predicate) — names now expose the factory-vs-bare shapes that uniform `_eq`/`_other`/`_presence` hid.

## 5. Left as-is / cosmetic
- **`_trial_tag`** — accurate name (trial-direction code → display tag); only its `td` param is renamed.
- **`k`** (`wilson_ci`) — textbook "k of n" convention, pairs with `n`; statsmodels call is positional. Leave.
- **`nnt` → `number_needed_to_treat`** — **cosmetic** (inside the `SETUP_CODE` notebook string; no importable caller). Recommend rename (matches spelled-out siblings/docstring); "leave" defensible since NNT is a standard acronym.

## 6. Flagged for your decision (recommended option first)
1. **`fdata` → `field_def`** (borderline param) — *recommend rename* (clarity/house-style; touches no frozen/test boundary, no call-site edits). Choose "leave" only to hold zero param churn in script files.
2. **`nnt` → `number_needed_to_treat`** (cosmetic, in-string) — *recommend rename* (low-risk polish). "Leave" defensible (standard acronym, string-only).
3. **`call_model` divergence** — *recommend proceed*: align name+role only; do NOT unify the two signatures (that'd be a separate Step-10 refactor, out of scope).

## 7. Step-10 watch-item — `_trial_tag` string-literal vs real code
Step 8's critic placed `_trial_tag`/`nnt`/`k` **inside an r-string notebook cell** (`_build_paper_figures.py:617` `cells.append(("code", r"""…`); the Step-9 namer called `_trial_tag` "real code". The edit mechanics are identical either way (replace the token in its scope), but **if it's r-string content the test gate does NOT cover it** — so Step 10 must read that region first and verify the `td`→`trial_dir` (and cosmetic `nnt`) edits by eye, not rely on pytest/ruff.

---
**Hand-off to Step 10:** apply §2–§3 (with §6 defaults: rename `fdata`, rename `nnt`, proceed with `call_model`). For each, update **every** call site listed + any comment/docstring mention (no misdirection). Keep `llm_extract.merge_records` and the §4 distinct copies separate. Do NOT touch the Step-8 §4 frozen list. Gate: `PYTHONUTF8=1 uv run pytest tests/ variable_extraction/tests/ -q` must hold at 63 (note §7: r-string edits need manual eyeballing).
