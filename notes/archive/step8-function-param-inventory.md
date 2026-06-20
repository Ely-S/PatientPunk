# Step 8 — Inventory of Function & Parameter Rename Candidates

> Read-only identification (no code changes). Feeds **Step 9** (propose names) and **Step 10** (apply).
> Workflow `wf_c4c4418e-4ce`: parallel readers → synthesis → boundary-accuracy critic. Critic verdict:
> **accurate on every boundary judgment — 0 mislabeled-frozen, 0 missed call sites, 0 out-of-scope.**
> Minor critic corrections folded in (⚑). No replacement names here — that's Step 9.

## 1. Summary
**Function & parameter naming is good.** Of ~**284** well-named functions/params, only **~13 functions**
(9 "core" + the haiku/collision group) and **3 real + 2 borderline params** are candidates (<5%), and
**every candidate is a private, single-system internal helper** — no public API / CLI / test / serialized
boundary (critic verified via recursive grep: zero cross-module callers for any candidate).

Three weakness patterns (not scattered cruft):
1. **Predicate-shaped names that don't return predicates** — `_hit` (returns a float rate), `_keep`
   (returns a cleaned string), and the `_eq`/`_other`/`_presence` trio (two are closure *factories*, one a bare predicate).
2. **Over-generic one-word verbs** — `_clean`, `_invert`, `_walk` (no object/return signal).
3. **Misleading provider-specific labels** — `call_haiku` / `_call_haiku_batch_raw` hardcode "haiku" while
   the model is the provider-agnostic `_utils.MODEL_FAST`; they diverge from the sibling `call_model`.

Secondary: **same-name/different-body collisions** in `scripts/` (`merge_records`, `_call_haiku_batch_raw`,
`parse_json_response`, `collect_texts_from_*`, `build_text`) — these are *parallel-but-divergent* copies;
Step 10 must NOT treat them as one symbol (most are frozen/test-imported anyway — §4/§5).

## 2. Function rename candidates (no replacement names — Step 9's job)

| Function | Location | Kind | Called by / why | Why unclear |
|---|---|---|---|---|
| `_pf_key` | `src/pipeline/classify.py:41` | private-helper | builds the `'{entry_id}:{drug}'` prefilter-cache key; callers `classify.py:238,262,273` | `pf` opaque; module spells out `prefilter_*` elsewhere |
| `_hit` | `consolidate.py:109` | private-helper | reads `hit_rate_at_discovery`→float; callers `_merge_group` `:128,146` | reads as a bool/noun; actually returns a **rate float** |
| `_keep` | `aggregate.py:32` | private-helper | normalizes text→stripped string, `''` for removed/deleted; callers `:58,59,66` ⚑ | reads as bool "keep?" but returns a **cleaned string** |
| `_eq` | `cluster_prep.py:85` | private-helper (closure **factory**) | returns a per-value membership predicate; called `_eq(v)` `:118,122` | cryptic; reads like equality, not a column-builder factory |
| `_other` | `cluster_prep.py:89` | private-helper (closure **factory**) | predicate for the long-tail "other" bucket; called `_other(set(top))` `:123` | bare adjective; no factory/predicate signal |
| `_presence` | `cluster_prep.py:93` | private-helper (bare predicate) | 1 if value-set non-empty; used directly `:113` ⚑ | **inconsistent with the trio**: `_eq`/`_other` are factories, this is a bare predicate |
| `_invert` | `normalize.py:128` | private-helper | inverts `{canonical:[syns]}`→`{cleaned_surface:canonical}`; caller `_LOOKUP` `:137` | generic; doesn't convey it inverts AND cleans keys |
| `_clean` | `normalize.py:35` | private-helper | lowercase/dequote/strip/collapse a raw string pre-match; callers `normalize_value`, `_invert` | very generic; collides conceptually with `normalize_value`/`normalize_cell` |
| `call_haiku` | `scripts/llm_extract.py:164` | module-function | one LLM call (retry/cache); callers `_call_batch_raw`, `main` | hardcodes "haiku" but model = `MODEL_FAST` (provider-agnostic); sibling uses `call_model` |
| `_call_haiku_batch_raw` | `scripts/code_demographics_llm.py:230` | private-helper | one demographic-coding batch call; caller `process_batch` | same "haiku" misnomer; **identical name** to the next, different body |
| `_call_haiku_batch_raw` | `scripts/extract_demographics_llm.py:210` | private-helper | one batch w/ escalating-temp retry; caller `process_batch` | same misnomer; identical name to the above, different signature |
| `merge_records` | `scripts/records_to_csv.py` | module-function | fills empty CSV-row cells from a same-key record | **same name** as `llm_extract.py:851`'s (provenance reconciliation) — different op |
| `_walk` | `variable_extraction/main.py` (closure in `_cmd_validate`) | private-helper (nested) | recursively collects `post_id→text` for `--export-template`; self-recursive `:755`, driven `:758` | generic verb, no object — what does it build? |
| `nnt`, `_trial_tag` | `build_notebook.py` / `_build_paper_figures.py:656` | string-literal helpers ⚑ | inside r-string notebook cells (NOT importable). `nnt`=number-needed-to-treat (no live caller); `_trial_tag`=trial-dir→label, caller same cell | `nnt` bare acronym; `_trial_tag` flagged only for its `td` param (§3). Cosmetic-within-a-string. |

## 3. Parameter rename candidates
| Param | Function · file | Role | Why unclear |
|---|---|---|---|
| **`td`** (real; deferred from Step 7) | `_trial_tag` · `_build_paper_figures.py:656` (string-literal) | trial-direction code from `r['trial_dir']`; `'+'`/`'0'`/passthrough → display label | cryptic; reads as "to-do"/date; contracts `trial_dir` (used everywhere else) |
| `eid` (borderline) | inner closure `upstream(eid, remaining)` ⚑ inside `compute_upstream_mentioned_drugs` · `src/pipeline/extract.py:95` | the entry/post id being resolved in the recursion | abbreviates "entry-id"; module spells `post_id`/`item_id`. ⚑ It's the *closure* param, not the public fn's — freely renameable |
| `k` (borderline) | `wilson_ci` · `build_notebook.py` (string-literal) | successes count → statsmodels `proportion_confint` | single letter; mirrors textbook `(k of n)` but elsewhere named `pos`. Cosmetic |
| `fdata` (borderline) | `_ext_row(fname, fdata)` · `scripts/make_codebook.py:59` ⚑ | one field-definition dict | terse "field data"; ⚑ it's a real param ONLY of `_ext_row` (in the test-imported `build_field_registry` it's a loop var, not a kwarg) → freely renameable |

> **`fmt` → reclassified FROZEN** (was a candidate): param of `CodebookGenerator.__init__` (a **public exporter class**), passed by keyword at `pipeline.py:535`, mirrors the `--format` CLI flag. Keyword + CLI contract — see §4.

## 4. Frozen contracts — the Step-10 do-NOT-touch list
Public-API exports, public methods of exported classes, CLI flags/subcommands, subprocess script filenames,
serialized fields, and keyword-arg contracts. (Renaming any of these breaks an external/serialized/CLI contract.)

**`src/`:** the orchestrator↔stage functions `run_pipeline` / `run_extraction` / `run_canonicalization` /
`run_classification` / `run_demographics` / `import_reddit_posts` (multi-caller incl. tests; keyword params
`skip_*`/`writer=`/`subreddit=`/`limit`/`max_posts`/`max_chars` mirror CLI flags); `open_db`,
`ReportWriter.write_one` (all-keyword call), `find_parent_cycles`; `ClassificationResult` fields
`sentiment`/`signal`/`side_effects` (serialized + DB column); the `*_PROMPT` constants;
`system_prompt`/`drug_aliases_prompt` params (cross-module).

**Scrapers:** both `main` CLIs + all argparse flags (`--months`/`--comments`/…, `--posts`/`--output`/…);
`build_post`/`build_comment` **return-dict keys** = the `subreddit_posts.json` serialized schema (consumed by `src/` + patientpunk).

**`variable_extraction/patientpunk` (public API via `__init__.py` + `extractors/`/`exporters/` `__all__`):**
`Pipeline`/`.run`/`.__init__(config)`, `PipelineConfig`/`PipelineResult`/`PhaseResult` (+ fields/`.ok`/`.summary()`);
`CorpusLoader`/`CorpusRecord` (+ `iter_records`/`load_all`/`full_text`/…); `Schema`/`FieldDefinition` (+ `from_file`/`field_names`/`to_dict`);
`BaseExtractor.run`/`BaseExporter.run`/`_build_args`/`_SCRIPT` (subprocess filenames); the extractor/exporter classes
`BiomedicalExtractor`/`LLMExtractor`/`FieldDiscoveryExtractor`/`DemographicCoder`/`DemographicsExtractor`/`CSVExporter`/`CodebookGenerator`
and their `__init__` keyword params (incl. **`fmt`**) — doubly frozen (public kwarg **and** mirror CLI flags);
`Extractor/Exporter Error/Result` (+ fields); the 4 `*_STANDARDS` constants; all `_build_args` CLI flag strings;
`Consolidate/Promote/Eval Result` serialized fields; synthetic-record dict keys (`author_hash`/`post_id`/`body`/`comments`/…).

**`variable_extraction` scripts + `main.py`:** every script `main` + argparse flags (the wrapper classes invoke
`python <script>.py …`); **test-imported functions** (renameable only with the test updated together):
`compile_extension_patterns`, `build_field_registry`, and from `discover_fields.py` `collect_texts_from_post`/
`collect_texts_from_user`/`merge_into_schema`/`parse_json_response`/`evaluate_patterns`; serialized JSON/LLM-schema
keys (`field_name`/`value`/`evidence`/`confidence`/`age`/`sex_gender`/…); `main.py` subcommand strings
(`run`/`demographics`/`export`/…); the 7 `_SCRIPT` filenames.

**RCT + `scripts/`:** `build_notebook`/`execute_and_export` (documented import API + params); `paths.py`
`find_package_root`/`db_path`/`data_dir`/`output_dir` (+ `start=` kwarg) — public API imported by verify/figures/scripts;
`write_provenance_manifest(package_root=)`; `PathResolutionError`; every script `main` + argparse flags.

## 5. Cross-module call map (Step 10 must rename every site together)
- **`src/` orchestrator↔stages** (all already clearly named — frozen above): `run_pipeline`/`run_extraction`/
  `run_canonicalization`/`run_classification`/`run_demographics`/`import_reddit_posts`/`open_db`/`system_prompt`/
  `drug_aliases_prompt`/`find_parent_cycles` — call sites enumerated in §4.
- **`variable_extraction` core helpers** called by `main.py` (clearly named, multi-site if ever touched):
  `consolidate_schemas`, `promote_discovered_fields`, `aggregate_corpus_by_author`, `aggregate_patients`,
  `build_matrix`, `select_fields`, `readiness_report`, `score_extraction`, `normalize_records`, etc.
  **`_utils.py` shared helpers** (package + scripts): `split_retry_batch`, `get_llm_client`, `load_json`,
  `clean_temp_dir`, `csv_fill_rate`, … — all clearly named, not candidates.
- **Same-name/different-body collisions — do NOT merge by renaming** (parallel-but-divergent copies; the test
  pins which is which): `collect_texts_from_*`/`parse_json_response` (×3 scripts; test imports the
  `discover_fields` ones = frozen), `merge_records` (llm_extract vs records_to_csv — different ops),
  `_call_haiku_batch_raw` (×2 demographics scripts — both §2 candidates), `build_text` (×2), and
  `call_haiku` vs `call_model` (cross-script inconsistency for the same role — Step 9 may align the names; both script-internal).
- **Self-contained RCT mirrors — do NOT unify with `src/`** (intentional decoupling, §D3): `_detect_cycles` ≠
  `src/.../graph.find_parent_cycles`; `DRUG_CUTOFFS`/`SIG_RANK`/`EXPECTED_OUTPUTS` duplicated in verify.py +
  _build_paper_figures.py; most RCT "functions" live inside r-string notebook cells (cosmetic-within-a-string,
  no importable call site). Scrapers are standalone (no symbol imports — only the `subreddit_posts.json` shape couples them).

## 6. Clearly-named (no action) — ~284
Representative well-named, skipped: `src/` `extract_batch`/`prefilter_batch`/`classify_batch`/`format_entry`/
`compute_upstream_mentioned_drugs`/`strip_reddit_prefix`/`already_classified`; Scrapers `hash_username`/`paginate_all`/
`fetch_full_post`/`utc_iso` (and `_sort_key` — clear name; its **body** has a latent stringified-int sort bug, a
*behavior* issue out of naming scope, §D6); core `aggregate_corpus_by_author`/`readiness_report`/`decompose_treatment_outcome`
(and `_OpenAIMessages.create` deliberately mirrors the Anthropic SDK shape); scripts `run_phase1_discovery`…`run_phase4_fill_gaps`/
`build_record`/`build_csv_row` and the `_cmd_*`/`_add_*_parser` dispatchers (only `_walk` flagged); RCT `epoch_midnight`/
`categorize_aliases`/`_compute_db_sha256`/`_git_metadata`/`_is_package_root`/`_walk_up`.

---
**Hand-off to Step 9:** propose the clearest name for each §2/§3 candidate (consider aligning `call_haiku`↔`call_model`
and giving the two `_call_haiku_batch_raw` copies *distinct* names, since they're different functions). Decide the
borderline params (`eid`/`k`/`fdata`) — recommend or leave. Do NOT touch §4 (frozen) or the §5 collisions/mirrors as merges.
