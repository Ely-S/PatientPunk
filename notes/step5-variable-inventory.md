# Step 5 — Inventory of Inner/Private Variables

> Read-only identification pass (no code changes). This is the catalog that feeds **Step 6** (propose the
> clearest names — review gate) and **Step 7** (apply renames, no misdirection). Produced by a 7-agent
> workflow (`wf_9a72256e-bca`): parallel readers → synthesis → boundary-accuracy critic. The critic's two
> corrections + one omission are folded in (see ⚑ marks). No replacement names are proposed here — that's Step 6.

## 1. Summary

**The codebase is well-named.** Across all systems the overwhelming majority of locals (~700+), and
essentially all underscore-private module-data and private instance attributes, are clear. The actionable
rename surface is **small and bounded**:

| Scope | Count | Notes |
|---|---|---|
| Cryptic private attributes | **3** | all in one OpenAI-compat shim (`src/utilities/__init__.py`) |
| Unclear private module-data | **0** | every underscore-private datum is clearly named (data smells are *collisions/dups*, not names) |
| Rename-candidate locals | **~27** | two patterns: over-abbreviation, or generic names hiding the value's shape |

Two recurring drivers: **(a) over-aggressive abbreviation** (`prov`, `disc`, `lut`, `lbl`, `av`, `av_map`,
`ne_items`, `mn`/`mx`, `rel`, `bits`, `cats`, `td`, `syns`, `cached_pf`) and **(b) generic/jargon names that
hide the value's shape** (`to_do`, `tagged`, `flat`, `stub`, `raw`, `data`, `sub`). The cross-cutting theme
is **inconsistency** — the same concept spelled out in one place, contracted in another in the same file/system.

Systems (renames must stay within one): **A** `src/` · **B** `Scrapers/` · **C** `variable_extraction/patientpunk` core ·
**D** `variable_extraction` scripts + `main.py` · **E** RCT (`docs/RCT_historical_validation/` + `scripts/` + `analysis_scripts/`, self-contained).

## 2. Rename candidates — the actionable list for Step 6

Each: current name · location · scope · what uses it / why it exists · why the name is unclear.

### A — `src/`
**`src/utilities/__init__.py` — OpenAI-compat shim private attrs (tight scope, small blast radius):**
- **`_t`** · `_Stream` (165 set, 168 read) · the precomputed response text returned (wrapped in `_Msg`) by `get_final_message()` · single-letter; says nothing about being the final message text.
- **`_c`** · `_OpenAIMessages` (171 set, 179 `self._c.chat.completions.create`) · the wrapped OpenAI client · single-letter; collides visually with `_Block`/`_Msg` scaffolding. ⚑ (the well-named list earlier mislabeled this as `_client` — it's `_c`, a rename candidate.)
- **`_temp`** · `_OpenAIMessages` (172 set, 180 `temperature=self._temp`) · sampling temperature (default 0.0) · reads as "temporary," conflating two meanings.

**`src/pipeline/extract.py` (`run_extraction`):**
- **`to_do`** · 206-208, 221 · list of `(item_id, text)` pairs still needing extraction; batched for the pool · generic; the *same* name in `classify.py` holds a different element shape.
- **`flat`** · 239-240 · flattened/lowercased per-item drug list → `id_to_drugs[item_id]` · names the transform, not the contents (a per-item drug list).

**`src/pipeline/classify.py` (`run_classification`):**
- **`to_do`** · 189,205,221,237,273 · `(entry, drug)` pairs needing classification · same generic name as the differently-shaped `extract.py:to_do`.
- **`tagged`** · 146+ (also `run_sentiment_pipeline.py:run_pipeline:50`) · entry dicts from `canonicalized_mentions.json` (or `tagged_mentions.json` fallback) · named after a stage; the canonicalized branch loads *post-tagging* data, so the name lags the state. (Cross-file in one system — §3.)
- **`syns`** · 216-219 · synonym list passed to `system_prompt(...)` · terse; sits next to the fuller `synonyms_for` — inconsistent.
- **`cached_pf`** · 229-270 · dict prefilter-key → bool, from/to `prefilter_results.json` · `pf` opaque; inconsistent with `prefilter_path`/`prefilter_batches`.

### B — `Scrapers/`
- **`stub`/`post_stubs`/`stubs`** · `scrape_corpus.py` (`count_posts_in_window` returns; main loop iterates) · minimal post record (`id`+`created_utc`) reused to avoid a 2nd fetch · "stub" is undefined jargon; 3 spellings for one concept.
- **`raw`** · `scrape_corpus.py:173` (`fetch_comments_for_post`) · list of un-transformed Arctic Shift comment dicts before `build_comment` · generic; inconsistent with sibling `*_raw` names.
- **`data`** · `scrape_corpus.py` (`arctic_get`/`fetch_full_post`/`fetch_reddit_profile`/`paginate_all`) · decoded JSON envelope; callers read `data['output']` · maximally generic, reused for several response shapes.
- **`sub`** · `transform_arctic_shift.py:134` (`main`) · lowercased subreddit name, filtered against `args.subreddit.lower()` · ambiguous (subreddit/submission/substitution); hides that it's normalized.

### C — `variable_extraction/patientpunk` core (locals)
- **`prov`** · `pipeline.py:234` (`Pipeline.run`) · provenance dict → `llm_provenance.json` · truncated; context spells out "provenance."
- **`disc`** · `pipeline.py:468` (`_run_phase_4`) · discovered-records `Path` · over-abbreviated; the parallel `disc_schema` in phase 5 is clearer.
- **`lut`** · `normalize.py:145,153` (`normalize_value`) · per-field inverted lookup (`_LOOKUP.get(field)`) surface→canonical · cryptic; inconsistent with the `_LOOKUP` it's drawn from.
- **`lbl`** · `normalize.py:223` (`decompose_treatment_outcome`) · normalized outcome label, deduped into `labels` · vowel-dropped; the list it feeds is the fully-spelled `labels`.
- **`pa`/`ca`/`cb`** · `aggregate.py:57,65,66` · post-author / comment-author / comment-body · two-letter initialisms encode 2 dimensions at once where attribution correctness is load-bearing.
- **`rs`/`cs`** · `evaluate.py:75` (`score_field`) · reference-value set / candidate-value set · `r`/`c` is a convention but trailing `s` opaque; ref-vs-cand is load-bearing and the names don't signal "set."
- **`av`** · `consolidate.py:142` (`_merge_group`) · a member's `allowed_values`, unioned into `allowed` · 2-letter contraction; the accumulator is the clearer `allowed`. (Same smell in System D — treat the `allowed_values` family holistically.)
- **`D`/`Xa`/`sims`** · `cluster_prep.py:162-167` (`readiness_report`) · numpy matrix / Jaccard distance / similarities · *(borderline)* conventional ML notation; flagged only because `D` is reassigned (raw→NaN-cleaned) so it no longer signals its state.

### D — `variable_extraction` scripts + `main.py` (locals)
- **`av`** · `discover_fields.py` (577-579, 1093-1097, 1276-1278) · a field's `allowed_values` · cryptic, reused under one opaque name in 3 functions; inconsistent with `av_map`/`field_allowed_values`.
- **`av_map`** · `discover_fields.py:1145,1336` · per-field lowercase→canonical dict · inherits the cryptic `av` prefix.
- **`ne_items`** · `code_demographics_llm.py:285` (`process_batch`) · non-empty subset of batch items → `split_retry_batch` · `ne_` cryptic; sibling `extract_demographics_llm.py` spells it `non_empty_items`/`non_empty_indices` — one idea, two names (§3).
- **`high_bleed`** · `discover_fields.py:310-315` · list of `(field, bleed_rate)` ≥0.10 for the prompt · *(borderline)* reads as a boolean flag, not a collection.

### E — RCT validation (locals; renames must mirror across the self-contained copies — §3)
- **`mn`/`mx`** · `verify.py:207` (`check_window_per_drug`) · MIN/MAX post_date; **`mn` is a dead binding** (never read) · heavily contracted, read as typos; parallel build-cell uses clearer `_mn`/`_mx`.
- **`rel`** · `verify.py:356` (`check_expected_outputs`) · relative p-value drift gating the `1e-3` check · bare; meaning depends entirely on adjacent lines.
- **`bits`** · `verify.py:271` (`check_dedup_audit`) · accumulator of per-drug summary strings → `CheckResult.details` · vague; reads as "binary bits."
- **`cats` (sense 1)** · `scripts/dump_drug_aliases.py:116` · dict of alias review-flag categories · ambiguous; collides with sense 2.
- **`cats` (sense 2)** · `_build_paper_figures.py:543` · ordered sentiment class list `['positive','mixed','neutral','negative']` · one token, two meanings within the slice.
- **`td`** · `_build_paper_figures.py:656` (`_trial_tag`) · trial-direction code → human label · *(borderline)* opaque; surrounding code spells out `trial_dir`.

⚑ **`records_to_csv.py` (reviewed — critic correction):** the file **exists** (256 lines; wrapped by `exporters/csv_exporter.py` `_SCRIPT`). Its locals are well-named (`meta`, `values`, `all_fields`, `field_names`, `all_columns`, `total_rows`) → **0 rename candidates**. Its `_fields_merged` is an in-memory record key → §4 (boundary), not a variable.

## 3. Cross-module / shared-local names (one system; Step 7 renames all usages)
- **A:** `tagged` is a local in two files (`classify.py`, `run_sentiment_pipeline.py`) — rename both. `to_do` is an independent local in `extract.py` + `classify.py` with *different* shapes — Step 6 decides keep-parallel vs distinguish.
- **B:** the `(author,title)` dedup locals (`seen_post_keys`/`dedup_key` vs `seen_keys`/`dedup_key`) mirror across the two scrapers — keep consistent.
- **C/D:** the `av`/`av_map`/`field_allowed_values` abbreviation family spans `consolidate.py` + `discover_fields.py` — treat holistically. `ne_items` vs `non_empty_items` spans two sibling scripts — reconcile both.
- **E:** `mn`/`mx`/`rel`/`bits`/`n_null` in `verify.py` vs `_mn`/`_mx`/`_rel`/`_n_null` in `_build_paper_figures.py` cells compute the same values in two styles; `SIG_RANK`/`DRUG_CUTOFFS`/`EXPECTED_OUTPUTS`/`END_2022_EXCLUSIVE`/dedup logic are copied verbatim across `verify.py`, `_build_paper_figures.py`, `dedup_sample_audit.py`, `dump_per_drug_csvs.py` — a rename in one must mirror in all four (intentional self-contained copies, §D3). The `_detect_cycles` mirror of `src/utilities/graph.find_parent_cycles` is a deliberate **cross-system** copy — do NOT couple.

## 4. Boundary keys — NOT variables, do NOT rename (frozen contracts)
Underscore-prefixed (and plain) serialized JSON/CSV keys, SQL identifiers, sentinel strings, and external API
field names that *look* like private vars but are frozen. The critic confirmed **none of the §2 candidates is
a boundary name**. Highlights of what's frozen:
- **JSON record/field keys:** `drugs_direct`, `drugs_context`, `age_bucket`, `sex`, `location`, `conditions`, `condition_name`, `condition_type`; the prefilter cache key `"<entry_id>:<drug>"`.
- **Underscore serialized/schema-metadata keys:** `_patientpunk_version`, `_promoted_at`/`_promoted_from`, `_n_runs_seen`, `_consolidated_from`, `_base_schema`, `_description`, `_target_subreddit`, `_discovered_at`, `_schema_id`, `_extraction_method`, `_model`, `_extracted_at`, `_generated_at`, `_version`, `_bleed_rate_last_run`; in-memory control keys `_skipped`/`_ready`/`_failed`/`_from_record`; ⚑ `_fields_merged` (`records_to_csv.py:107,141`, in-memory record key). CSV column **suffixes** `__provenance`/`__confidence`.
- **Corpus output dict keys** (Scrapers → consumed by `import_posts`/`corpus`/tests): `post_id`, `title`, `body`, `author_hash`, `created_utc`, `score`, `comment_id`, `parent_id`, `subreddit`, etc.; files `subreddit_posts.json`/`corpus_metadata.json`.
- **External API fields** (Arctic Shift/Reddit): `output`, `selftext`, `permalink`, `link_id`, `link_flair_text`, `num_comments`, about.json `link_karma`/`snoovatar_img`/`public_description`.
- **SQL identifiers/tables** (RCT): `post_date`, `parent_id`, `user_id`, `drug_id`, `signal_strength`, `sentiment`, `run_id`, …; tables `treatment_reports`/`treatment`/`posts`/`extraction_runs`/`users`; sentinel value `'deleted'`; `provenance.json` keys.
- **String-template pseudo-globals (NOT source globals):** in `_build_paper_figures.py` r-strings, names like `_DB_FILENAME`/`_violations`/`_audit_rows` exist only inside the generated notebook namespace (underscore = deliberate to avoid clobbering notebook user vars). Do NOT rename.
- **Public UPPER_CASE constants** (Step 2's domain, frozen): `MODEL_FAST`/`MODEL_STRONG`, `PAGE_SIZE`, `DELETED_AUTHOR`, `REDDIT_REMOVED`, `OUTCOME_LABELS`, `FIELD_VOCAB`, `SIG_RANK`, `DRUG_CUTOFFS`, etc.

## 5. Clearly-named (no action) + structural smells (NOT renames — for owners)
**~700+ locals**, all underscore-private module-data (`_PLACEHOLDER_KEYS`, `_TRAILING_COMMA`, `_TEMP_PATTERNS`,
`_LOOKUP`, `_PUNCT`, `_ANALYSIS_CARRY`, `_CONDITION_CANONICAL`, `_OUTCOME_SYNONYMS`, …), and the well-named
private attrs (`ReportWriter._conn`/`_pending`/`_drug_ids`/`_existing`; `Pipeline._schema_id`/`_temp_dir`;
`BaseExtractor._script_path`) are clear — no rename. ⚑ (`_OpenAIMessages._client` was a phantom in the draft; the real attr `_c` is a §2 candidate.)

**Structural smells (duplication/collision/orphan — flag for owners, NOT Step 6/7 variable renames):**
1. **`BATCH_SIZE` ×3** (A): `extract.py`=10, `canonicalize.py`=3500, `classify.py`=5 — same name, 3 values (file-local, no break).
2. **`COMMIT_EVERY` ×2** (A): `db.py`=50 vs `extract_demographics_conditions.py:88`=20.
3. **`_REDDIT_REMOVED` ×3 forms** (C/D): frozenset / inline `('[removed]','[deleted]','')` tuples / imported `REDDIT_REMOVED`.
4. **`_DEFAULT_BASE` / `_DEFAULT_BASE_SCHEMA` dup** (C): same base-schema path defined twice.
5. **`FUNCTIONAL_RANK` orphan** (C, `normalize.py`): no reader; values can't form a strict order (`housebound`=`severe_unspecified`=3). Likely dead/aspirational public data.
6. **`_base_field_names` triplicated** (D, `discover_fields.py:1598`) vs `BASE_FIELDS` in two other scripts.
7. **Out-of-scope underscore *functions*** (Step 8, not now): `transform_arctic_shift._sort_key` (latent sort bug, §D6), `paths._is_package_root`/`_walk_up`, `verify._fetch_drug_reports`/`_detect_cycles`, etc.

---
**Hand-off to Step 6:** propose the clearest name for each §2 entry (and decide the cross-module reconciliations in §3),
respecting the §4 frozen boundaries and the §3 self-contained-copy mirrors. Do not touch the §5 structural smells as part of the rename pass.
