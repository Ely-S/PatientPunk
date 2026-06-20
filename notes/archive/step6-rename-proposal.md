# Step 6 — Variable Rename Proposal (current → proposed)

> **PROPOSAL ONLY — the review gate before Step 7. No code changed.** Produced by workflow
> `wf_dc08ce88-bcd` (per-group namers → reconcile → boundary/collision/param-scope critic). Critic verdict:
> **APPROVE — 0 collisions, 0 boundary violations, 0 misfiled params, 0 missed mirror sites, 0 weaker names.**
> Main-agent review: concur. Step 7 applies these (with the §6 recommended options) unless the user edits them.

## 1. Summary
- **30 identifiers** proposed for rename, across 10 files.
- **Cross-module / mirror** (must change in >1 file together): 4 concepts — `tagged`, `ne_items`↔`non_empty_items`, and the `mn`/`mx`/`rel` verify↔notebook mirrors.
- **Left as-is** (conventional/borderline): `D`, `Xa`, `sims`.
- **Deferred to Step 8** (it's a parameter, not a variable): `td`.
- **Flagged for your decision** (sensible defaults; see §6): the two `to_do` distinction, the `pairs_to_classify` near-rhyme, the `summary_bits` sibling-name reuse.

## 2. Proposed renames, by system → file

### A — `src/`
**`src/utilities/__init__.py`** (OpenAI-compat shim private attrs)
| current | → proposed | sites | why |
|---|---|---|---|
| `_t` | `_text` | 165,168 | final response text; mirrors ctor param `text` |
| `_c` | `_client` | 171,179 | wrapped OpenAI client; matches `ReportWriter._conn` style |
| `_temp` | `_temperature` | 172,180 | reads as "temporary"; conflicts conceptually with `_temp_dir` |

**`src/pipeline/extract.py`**
| current | → proposed | sites | why |
|---|---|---|---|
| `to_do` | `pending_extractions` | 206,208,221 | `(item_id, text)` pairs to extract; distinguished from classify's (§6a) |
| `flat` | `drug_names` | 239,240 | per-item drug-name list → `id_to_drugs`; names contents not the transform |

**`src/pipeline/classify.py`**
| current | → proposed | sites | why |
|---|---|---|---|
| `to_do` | `pairs_to_classify` | 189,205,221,237,273 | `(entry, drug)` pairs; distinguished from extract's (§6a/§6b) |
| `syns` | `synonyms` | 216,218,219 | consistent with neighbour `synonyms_for` |
| `cached_pf` | `cached_prefilter_results` | 229,232,233,239,263,268,270 | dict from/to `prefilter_results.json`; matches `prefilter_*` family |

### B — `Scrapers/`
| file | current | → proposed | sites | why |
|---|---|---|---|---|
| `scrape_corpus.py` | `stub`/`post_stubs`/`stubs` | `partial_post`/`partial_posts` | 149,157,453,456,457,474,487,488 | minimal id+created_utc record; one concept, 3 spellings → element/list |
| `scrape_corpus.py` | `raw` | `raw_comments` | 173,177 | un-transformed comment dicts; matches `*_raw` convention |
| `scrape_corpus.py` | `data` | `response` | 116,117,166,167,302,307 | decoded JSON envelope (unwrapped via `["output"]`); `"output"` key stays frozen |
| `transform_arctic_shift.py` | `sub` | `subreddit` | 134,135 | lowercased subreddit name; `sub` ambiguous |

### C — `variable_extraction/patientpunk` core
| file | current | → proposed | sites | why |
|---|---|---|---|---|
| `pipeline.py` | `prov` | `provenance` | 234,237-243 | provenance dict → `llm_provenance.json` |
| `pipeline.py` | `disc` | `discovered_records` | 468-471 | discovered-records path; sibling spells `discovered` |
| `normalize.py` | `lut` | `lookup` | 145-147,152,153 | per-field surface→canonical map from `_LOOKUP` |
| `normalize.py` | `lbl` | `label` | 223-228 | one outcome label; feeds spelled-out `labels` |
| `aggregate.py` | `pa` | `post_author` | 57,61,62 | post author_hash (attribution is load-bearing) |
| `aggregate.py` | `ca` | `comment_author` | 65,67,68 | comment author_hash; mirror of `post_author` |
| `aggregate.py` | `cb` | `comment_body` | 66,67,68 | comment body; pairs with `comment_author` |
| `evaluate.py` | `rs` | `ref_set` | 75,76,80,83,84,86 | reference value SET; keeps `ref_`/`cand_` convention |
| `evaluate.py` | `cs` | `cand_set` | 75,78,80,83,85,86 | candidate value SET; mirror of `ref_set` |
| `consolidate.py` | `av` | `allowed_values` | 142,143,144 | reads the literal `'allowed_values'` key; distinct from `allowed` accumulator |

### D — `variable_extraction/.../scripts/`
**`discover_fields.py`**
| current | → proposed | sites | why |
|---|---|---|---|
| `av` (site 1, Phase-1 merge) | `member_allowed_values` | 577,578,579 | **collision-forced** — bare `allowed_values` already bound at 591 |
| `av` (site 2, Phase 3) | `allowed_values` | 1093,1094,1095 | free; spelled-out clearest |
| `av` (site 3, Phase 4) | `allowed_values` | 1277 | free |
| `av_map` (Phase 3 + Phase 4) | `canonical_by_lower` | 1145,1149,1150 / 1336-1340 | lowercase→canonical dict; same name both phases |
| `high_bleed` | `high_bleed_fields` | 310,316,319 | list of `(field,rate)` tuples; bare adjective read as a flag |

### E — RCT validation
| file | current | → proposed | sites | why |
|---|---|---|---|---|
| `verify.py` | `bits` | `summary_bits` | 271,300,308 | per-drug summary strings; matches sibling `check_window_per_drug` (§6c) |
| `scripts/dump_drug_aliases.py` | `cats` (sense 1) | `alias_categories` | 116,126,128,130,135,137 | dict of alias review-flag lists (§6d) |
| `_build_paper_figures.py` | `cats` (sense 2) + loop `cat` | `sentiment_classes` + `sentiment_class` | 543,565,567,574,576 | ordered list of 4 sentiment classes (§6d) |

## 3. Cross-module / mirror renames (change in >1 file together)
- **`tagged` → `mention_entries`** (System A): the per-entry dicts carrying `drugs_direct`/`drugs_context`; source may be `canonicalized_mentions.json`, so `tagged` lags state.
  - `src/pipeline/classify.py`: 146,147,166,171,172,174,192 · `src/run_sentiment_pipeline.py`: 50,51
  - *Frozen, NOT renamed:* `tagged_path`, the const `TAGGED_MENTIONS`, the filename, and JSON keys.
- **`ne_items` → `non_empty_items`** (System D): adopt the sibling's existing name.
  - `code_demographics_llm.py`: 285,291 (change) · `extract_demographics_llm.py`:299 (already correct — no change).
  - Advisory (not proposed): `code_demographics_llm.py:271`'s `non_empty` index list could align to `non_empty_indices` for full parity.
- **`mn`/`mx`/`rel` mirrors** (System E — verify.py ↔ `_build_paper_figures.py` cells; move in lockstep):
  | concept | verify.py | notebook mirror | sites |
  |---|---|---|---|
  | MIN(post_date) | `mn`→`min_post_date` | `_mn`→`_min_post_date` | verify:207 · figures:1015,1043 |
  | MAX(post_date) | `mx`→`max_post_date` (+`mx_iso`→`max_post_date_iso`) | `_mx`→`_max_post_date` | verify:207,224,225 · figures:1015,1028,1030,1044,1047 |
  | rel p-drift | `rel`→`rel_drift` (+ f-string label `'rel'`→`'rel drift'` :359) | `_rel`→`_rel_drift` | verify:356,357,359 · figures:501,502,505 |
- **`av`/`av_map` family** (consistency, §2): reconciled to `allowed_values` (where free) / `member_allowed_values` (collision) / `canonical_by_lower`. Advisory: `field_av_maps` (discover_fields:1275) could align to `field_canonical_maps`.

## 4. Deferred to Step 8 (parameters, not variables)
- **`td`** — formal param of `_trial_tag(td)` in `_build_paper_figures.py:656`. Parameters are Steps 8–9. Step-8 target (for the record): `trial_dir` (matches the dict key/`resp_df['trial_dir']`). No other candidate was actually a parameter (`rs`/`cs` confirmed locals).

## 5. Left as-is (conventional / borderline)
- **`D`** (`cluster_prep.py`) — capital `D` = distance matrix (SciPy/ML convention), paired with `Xa`; the `nan_to_num` reassignment is the same matrix cleaned in place.
- **`Xa`** — numpy feature matrix (capital-X convention); `a` disambiguates from the list-of-lists param `X`.
- **`sims`** — conventional contraction of "similarities", tied to `similarity_*` output keys.

## 6. Flagged for your decision (recommended option first)
- **6a — distinguish the two `to_do` (RECOMMENDED) vs keep parallel.** They hold *different shapes* (`(item_id,text)` vs `(entry,drug)`), so a shared name would falsely imply a shared shape. → `pending_extractions` / `pairs_to_classify`.
- **6b — `pairs_to_classify` near-rhymes with the sibling local `to_classify`** (classify.py:273). Distinct identifier, no collision; recommend keeping it. **Fallback:** `entry_drug_pairs` (names the shape directly).
- **6c — `bits`→`summary_bits` reuses a sibling function's name** (`check_window_per_drug` already uses `summary_bits` for the same role; different function scopes → no collision). Recommend `summary_bits` (consistency). **Fallback:** `summary_lines`.
- **6d — the two `cats` senses get different names** (required): `alias_categories` (dict of flag-lists) vs `sentiment_classes` (ordered label list). Confirmed different shapes. For sign-off, not contentious.

---
**Hand-off to Step 7:** apply §2–§3 (with §6 recommended options) as one behavior-preserving rename pass; grep for the old names afterward to confirm **no misdirection** (no stale references/comments). Do NOT touch §4 (`td` — Step 8), §5 (leave), or any frozen boundary name. Gate: `PYTHONUTF8=1 uv run pytest tests/ variable_extraction/tests/ -q` must hold at 63.
