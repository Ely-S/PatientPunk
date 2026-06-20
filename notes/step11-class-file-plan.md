# Step 11 — Class & File Rename / Reorganize Plan

> Identify + propose + (gated) apply for CLASS and FILE/module names — the widest-blast-radius step.
> Workflow `wf_6e314a03-2d7`: parallel readers → synthesis → boundary-accuracy critic. **Critic verdict:
> the rename/reorg surface is GENUINELY EMPTY — 0 mislabeled-frozen classes, 0 mislabeled-frozen files,
> 0 missed reference sites.** Minor prose nits folded in (⚑). **Outcome: NO code changes — leave as-is.**

## 1. Decision
- **Class rename candidates: 0.** **File rename / reorganization candidates: 0.**
- Class/file naming and the directory structure are **sound and intentional**. Every class is either
  public-API (frozen) or a clearly-named internal helper; every `.py` is a documented entry, a frozen
  subprocess-script filename, a package-root marker, or a bare-path import-boundary module. This is the
  expected, valid "small surface → leave it" result for a well-organized repo.
- **55 classes evaluated, all well-named; ~60 frozen items mapped (§3).** Two durable products: the
  frozen map (§3) and the Step-12 doc-rot worklist (§4).

## 2. Internal classes evaluated and KEPT (renameable-by-boundary, but names already accurate)
- `_Block` / `_Msg` / `_Stream` / `_OpenAIMessages` / `_OpenAIAdapter` (`src/utilities/__init__.py` L160–193) —
  terse *on purpose*: they mirror the Anthropic SDK response shape (documented by the L155–159 section comment);
  referenced only within `__init__.py`.
- `_AnthropicShapedResponse` / `_OpenAIMessages` / `_OpenAIAdapter` (`patientpunk/_utils.py` L171/177/201) —
  underscore-private, single-file; accurate. **NOTE:** these are an *independent copy* of the `src/utilities`
  shim — two separate systems, NOT a shared import; a rename in one must never touch the other.
- `ConsolidateResult` / `PromoteResult` / `EvalResult` (`consolidate.py:89` / `promote.py:34` / `evaluate.py:102`) —
  internal (not in any `__all__`), parallel the public `PipelineResult`/`PhaseResult` pattern; clear.
- `_UnionFind` (`consolidate.py:67`) — idiomatic data-structure name. `CheckResult` (`verify.py:83`) — accurate
  (the result of a reproducibility *check*); single-file, not exported.

## 3. Frozen — do NOT rename (the canonical class/file boundary)
**Public-API classes** (exported via `__all__`):
- `patientpunk/__init__.py`: `CorpusLoader`, `CorpusRecord`, `Schema`, `FieldDefinition`, `Pipeline`,
  `PipelineConfig`, `PipelineResult`, `PhaseResult`, `DemographicCoder`, `DemographicsExtractor` (+ the 4 `*_STANDARDS`).
- `extractors/__init__.py`: `BaseExtractor`, `ExtractorError`, `ExtractorResult`, `BiomedicalExtractor`,
  `LLMExtractor`, `FieldDiscoveryExtractor` (`DemographicCoder`/`DemographicsExtractor` also frozen via the top `__all__`).
- `exporters/__init__.py`: `BaseExporter`, `ExporterError`/`ExporterResult` (genuine aliases of the Extractor ones),
  `CSVExporter`, `CodebookGenerator`.
- `src/`: `ClassificationResult` (`models.py`), `ReportWriter` (`db.py`, README-documented), `PipelineConfig`
  (`utilities/__init__.py` — the src dataclass, **distinct** from patientpunk's same-named class), `LLMParseError`,
  `UserRow`/`PostRow` (NamedTuples). RCT: `PathResolutionError` (`paths.py`, README-documented).

**Subprocess-script filenames** ⚑ (referenced by the private `_SCRIPT` attribute, *not* `SCRIPT`):
`llm_extract.py`, `extract_biomedical.py`, `discover_fields.py`, `code_demographics_llm.py`,
`extract_demographics_llm.py`, `records_to_csv.py`, `make_codebook.py`.

**Documented CLI entry files:** `src/run_sentiment_pipeline.py`, `src/import_posts.py`,
`src/extract_demographics_conditions.py`, `Scrapers/{scrape_corpus,transform_arctic_shift}.py`,
⚑ `variable_extraction/main.py` (at the package-dir top, NOT under `patientpunk/`),
`docs/RCT_historical_validation/{_build_paper_figures,verify,build_notebook}.py` (the first two are also
`paths.PACKAGE_MARKERS`), all `scripts/*.py` + `analysis_scripts/expand_reports.py`.

**Import-boundary modules** (bare-path / re-export surface): all `src/` modules (`from models/utilities/pipeline import …`
work via `pythonpath`/`sys.path`), the `patientpunk` core+extractors+exporters modules (incl. `consolidate`/`promote`/
`cluster_prep` whose basenames back documented CLI subcommands), and `docs/RCT_historical_validation/paths.py`
(also a path-resolution anchor). **Test files:** `tests/populate_db_test.py`, `variable_extraction/tests/test_pipeline.py`.

## 4. Doc-rot worklist for STEP 12 (stale filenames in docstrings/comments — NOT rename reference sites)
These name old files that no longer exist; fix the prose in the Step-12 comment/docstring pass:
- `src/pipeline/extract.py` L3 docstring → `extract_mentions.py` (file is `extract.py`).
- `src/pipeline/classify.py` L3 docstring → `classify_sentiment.py` (file is `classify.py`).
- `src/extract_demographics_conditions.py` L3/L14/L15 docstring+usage → `run_demographics.py`.
- `src/prompts/intervention_config.py` L4/L55/L72 → `extract_mentions.py` / `classify_sentiment.py`.
- `src/utilities/db.py` L4 → `classify_sentiment`.
- `docs/MVP_PLAN.md` L54/66/82/188 → `extract_mentions.py`/`classify_sentiment.py` under a nonexistent `database_creation/`.
- `Scrapers/README.md` L21–22/74 → `Scrapers/demographic_extraction/run_pipeline.py` (dir gone).
- (Plus the §D5/§D6 items already logged: the `Call Haiku`/`Claude Haiku` prose after the `call_model` rename;
  the stale `apps/discover.py` reference; the `run_demographics.py`/`scripts.classify_sentiment` mentions.)

## 5. Out of scope (noted, not actioned here)
- **Latent packaging fragility:** `src/`'s top-level importable names (`models`, `utilities`, `prompts`, `pipeline`)
  have no `patientpunk`-style namespace, so they could collide with site-packages. That's a **packaging** decision
  (e.g. a `src/` package), not a Step-11 rename — flag for the maintainers, do not change as cleanup.
- **`_detect_cycles` triplication** (`verify.py` + `thread_audit.py` + the src `find_parent_cycles`) is **deliberate**
  self-containment (§D3) — not a reorg opportunity.

---
**Bottom line:** Step 11 closes with an empty rename/reorg surface — leave class names, file names, and structure
as-is. The only follow-on is the §4 doc-rot worklist, which belongs to **Step 12**.
