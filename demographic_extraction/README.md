# PatientPunk — Demographic Extraction

Structured biomedical data extraction from patient-authored Reddit text.

Reads a corpus produced by `scrape_corpus.py` (subreddit posts + per-user
history files) and extracts demographic and clinical fields (age, sex/gender,
conditions, medications, treatment outcomes, etc.) using a combination of
hand-crafted regex patterns and Claude Haiku/Sonnet LLM calls.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Two Extraction Approaches](#two-extraction-approaches)
3. [Pipeline Phases](#pipeline-phases)
4. [CLI Reference](#cli-reference)
5. [Library Reference](#library-reference)
6. [File Structure](#file-structure)
7. [Schemas](#schemas)
8. [Outputs](#outputs)
9. [Environment Setup](#environment-setup)
10. [Running Tests](#running-tests)
11. [Join Key](#join-key)

---

## Quick Start

```bash
# 1. Install dependencies
pip install anthropic python-dotenv

# 2. Add your Anthropic API key
# Add your Anthropic API key to the project root .env
cp ../.env.example ../.env && echo "ANTHROPIC_API_KEY=sk-ant-..." >> ../.env

# 3. Full pipeline run (regex + LLM gap-fill + CSV + codebook)
python main.py run --schema schemas/covidlonghaulers_schema.json

# 4. LLM-only demographics (age / sex / location only, no regex)
python main.py demographics --input-dir ../reddit_sample_data

# 5. Inspect the schema without running anything
python main.py inspect --schema schemas/covidlonghaulers_schema.json
```

---

## Two Extraction Approaches

This module provides **two distinct pipelines** for extracting demographic data.
They are complementary, not competing.

### Approach A — Full Pipeline (regex → LLM backfill)

Extracts **all 37+ fields** defined in the schema (age, sex/gender, conditions,
medications, procedures, functional status, etc.).

- **Phase 1** — regex patterns match known signals instantly and for free.
- **Phase 2** — Claude Haiku fills fields that regex missed.
- **Phase 3** — (optional) discovers *new* fields not yet in the schema.

Use this when you want the complete structured record for every user.

```bash
python main.py run --schema schemas/covidlonghaulers_schema.json
```

### Approach B — LLM-Only Demographics

Extracts **only age, sex/gender, location_country, location_state** — nothing
else.  No regex.  Haiku is given a strict self-reference constraint: it must
only extract values the author states explicitly about themselves.

Use this when you need clean, high-confidence demographic data and don't need
the full clinical picture.  Works across full user posting histories, which
typically yields 4–5× more coverage than single posts.

```bash
python main.py demographics --input-dir ../reddit_sample_data
```

---

## Pipeline Phases

| Phase | Script (legacy) | Class (library) | Cost | Description |
|-------|----------------|-----------------|------|-------------|
| 1 | `extract_biomedical.py` | `BiomedicalExtractor` | Free | Regex patterns across all schema fields |
| 2 | `llm_extract.py` | `LLMExtractor` | ~$0.05–0.10 | Claude Haiku fills fields regex missed |
| 3 | `discover_fields.py` | `FieldDiscoveryExtractor` | ~$1–3 | Haiku discovers new fields; Sonnet writes regex |
| 4 | `records_to_csv.py` | `CSVExporter` | Free | Flatten JSON records to `records.csv` |
| 5 | `make_codebook.py` | `CodebookGenerator` | Free | Generate `codebook.csv` data dictionary |

### Phase 3 is expensive — use flags to control it

```bash
# Skip discovery entirely (fastest, cheapest)
python main.py run --schema schemas/... --no-discover

# Run discovery but skip the LLM gap-filling stage (Phase 3 Stage 4)
python main.py run --schema schemas/... --no-fill

# Reuse a previously saved candidate scan (skip Phase 3 Stage 1)
python main.py run --schema schemas/... --candidates output/temp/phase1_candidates.json
```

### Intermediate files

All intermediate JSON files are written to `output/temp/` and wiped at the
start of each full run.  Final outputs (`records.csv`, `codebook.csv`) stay
in `output/`.

```
output/
├── records.csv                                  ← final output (one row per user/post)
├── codebook.csv                                 ← field documentation
└── temp/
    ├── patientpunk_records_{schema_id}.json     ← Phase 1 regex results
    ├── extraction_metadata_{schema_id}.json     ← Phase 1 stats
    ├── llm_records_{schema_id}.json             ← Phase 2 LLM results
    ├── llm_field_suggestions_{schema_id}.json   ← Phase 2 new-field suggestions
    ├── merged_records_{schema_id}.json          ← Phase 1 + 2 combined
    ├── phase1_candidates.json                   ← Phase 3 discovery candidates
    ├── discovered_records_{schema_id}.json      ← Phase 3 extraction results
    └── discovered_field_report_{schema_id}.json ← Phase 3 coverage stats
```

---

## CLI Reference

All commands are accessed through `main.py`:

```
python main.py <command> [options]
```

### `run` — full pipeline

```bash
python main.py run --schema schemas/covidlonghaulers_schema.json [options]

  --input-dir PATH      Corpus directory (default: ../output)
  --temp-dir PATH       Intermediate files dir (default: {input-dir}/temp/)
  --start-at N          Resume from phase N (1–5)
  --no-llm              Skip Phase 2 (LLM gap-filling)
  --no-discover         Skip Phase 3 (field discovery)
  --no-clean            Don't wipe temp/ before starting
  --workers N           Concurrent API workers (default: 10)
  --limit N             Process at most N records (cost control)
  --resume              Resume an interrupted LLM/discovery run
  --skip-threshold F    LLM skips records where regex hit ≥ F fields (default: 0.7)
  --no-focus-gaps       Send full prompt to LLM (not just missed fields)
  --candidates PATH     Saved phase1_candidates.json (skips Phase 3 Stage 1)
  --sample N            Random N-item sample for Phase 3 Stage 1
  --no-fill             Skip Phase 3 Stage 4 gap-filling
  --sep STR             Multi-value separator in CSV (default: " | ")
  --provenance          Add {field}__provenance and {field}__confidence columns
  --codebook-format     csv (default) or markdown
  --no-discovered       Exclude llm_discovered fields from codebook
```

### `demographics` — LLM-only age/sex/location

```bash
python main.py demographics --input-dir ../reddit_sample_data [options]

  --input-dir PATH      Corpus directory
  --output PATH         Output CSV (default: {input-dir}/demographics.csv)
  --workers N           Concurrent Haiku workers (default: 10)
  --posts-only          Only process subreddit_posts.json
  --users-only          Only process users/*.json histories
  --max-chars N         Max characters per record sent to LLM (default: 6000)
```

### `inspect` — schema introspection

```bash
python main.py inspect --schema schemas/covidlonghaulers_schema.json [options]

  --source STR          Filter by source: base | base_optional | extension | llm_discovered
  --verbose             Show regex patterns for each field
```

### `corpus` — corpus statistics

```bash
python main.py corpus --input-dir ../reddit_sample_data
# Prints: post count, user history count, total records
```

### `export` — re-run export only (Phases 4 + 5)

```bash
python main.py export --schema schemas/covidlonghaulers_schema.json [options]
# Re-generates records.csv and codebook.csv from existing temp/ files
# without re-running any extraction
```

---

## Library Reference

The `patientpunk` package can be imported directly for use in notebooks or
other scripts.

### Corpus loading

```python
from patientpunk import CorpusLoader, CorpusRecord
from pathlib import Path

loader = CorpusLoader(Path("../reddit_sample_data"))
print(loader.post_count, loader.user_count)   # 100, 87

for record in loader.iter_records(limit=5):
    print(record.source, record.author_hash[:8], record.full_text[:80])
```

### Schema inspection

```python
from patientpunk import Schema

schema = Schema.from_file(Path("schemas/covidlonghaulers_schema.json"))
print(schema.schema_id)                    # covidlonghaulers_v1
print(schema.field_names(source="base"))   # ['age', 'sex_gender', ...]

fd = schema.all_fields["functional_status_tier"]
print(fd.confidence, fd.icd10)             # high   Z73.6
```

### Running an individual extractor

```python
from patientpunk.extractors import BiomedicalExtractor, LLMExtractor
from patientpunk import DemographicsExtractor

# Phase 1 only (regex, free)
result = BiomedicalExtractor(
    input_dir=Path("output"),
    schema_path=Path("schemas/covidlonghaulers_schema.json"),
).run()
print(result.ok, result.elapsed)

# LLM-only demographics
result = DemographicsExtractor(
    input_dir=Path("../reddit_sample_data"),
    output_path=Path("output/demographics.csv"),
    workers=10,
    include_users=True,   # use full posting histories
).run()
```

### Running the full pipeline programmatically

```python
from patientpunk import Pipeline, PipelineConfig

config = PipelineConfig(
    schema_path=Path("schemas/covidlonghaulers_schema.json"),
    input_dir=Path("output"),
    run_llm=True,
    run_discovery=False,   # skip the expensive step
    workers=10,
    limit=50,              # cap at 50 records for a test run
)
result = Pipeline(config).run()
print(result.ok)
print(result.summary())
```

---

## File Structure

```
demographic_extraction/
│
├── main.py                        Entry point — CLI with 5 subcommands
├── conftest.py                    pytest config (tells pytest to skip old/)
├── pytest.ini                     Test runner settings
├── .env                           API keys (not committed — see .env.example)
│
├── schemas/
│   ├── base_schema.json           24 universal biomedical fields (always active)
│   └── covidlonghaulers_schema.json  Disease-specific extension fields
│
├── patientpunk/                   Importable Python library
│   ├── __init__.py                Public API surface
│   ├── py.typed                   PEP 561 marker (enables mypy/pyright)
│   ├── corpus.py                  CorpusLoader + CorpusRecord
│   ├── schema.py                  Schema + FieldDefinition
│   ├── pipeline.py                Pipeline + PipelineConfig orchestrator
│   ├── _utils.py                  Internal shared helpers
│   │
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── base.py                BaseExtractor ABC (subprocess runner)
│   │   ├── biomedical.py          Phase 1 — regex extraction
│   │   ├── llm.py                 Phase 2 — LLM gap-filling
│   │   ├── discovery.py           Phase 3 — field discovery
│   │   └── demographics.py        Standalone: LLM-only age/sex/location
│   │
│   └── exporters/
│       ├── __init__.py
│       ├── base.py                BaseExporter (inherits subprocess runner)
│       ├── csv_exporter.py        Phase 4 — flatten records to CSV
│       └── codebook.py            Phase 5 — data dictionary
│
├── old/                           Legacy flat scripts (archived, still functional)
│   ├── __init__.py                Index of what each script does
│   ├── extract_biomedical.py      Original Phase 1 script
│   ├── llm_extract.py             Original Phase 2 script
│   ├── discover_fields.py         Original Phase 3 script
│   ├── records_to_csv.py          Original Phase 4 script
│   ├── make_codebook.py           Original Phase 5 script
│   ├── run_pipeline.py            Original pipeline orchestrator
│   └── extract_demographics_llm.py  Original LLM-only demographics script
│
└── tests/
    ├── __init__.py
    └── test_pipeline.py           Unit tests (pure functions, no API calls)
```

---

## Schemas

PatientPunk uses a two-layer schema system:

### Base schema (`schemas/base_schema.json`)

24 universal fields that apply to any patient community: `age`, `sex_gender`,
`conditions`, `medications`, `treatment_outcome`, etc.  Always active.

Some fields are marked `base_optional` — they are dormant unless explicitly
activated by an extension schema via `include_base_fields`.

### Extension schema (e.g. `schemas/covidlonghaulers_schema.json`)

Adds community-specific fields on top of the base: `covid_wave`,
`vaccination_status`, `functional_status_tier`, etc.

Can also:
- Activate `base_optional` fields via `"include_base_fields": [...]`
- Override base regex patterns via `"override_base_patterns": {...}`
- Accumulate `llm_discovered` fields from Phase 3 runs

### Adding a new disease community

1. Copy `schemas/covidlonghaulers_schema.json` as a template.
2. Set a new `schema_id` and `_target_subreddit`.
3. Add community-specific fields under `extension_fields`.
4. Run with `--schema schemas/yournew_schema.json`.

---

## Outputs

### `output/records.csv`

One row per user / subreddit post.  Multi-value fields (e.g. `conditions`,
`medications`) are joined with `" | "` by default.

Key columns:
- `author_hash` — SHA-256 of the Reddit username (join key with Polina's pipeline)
- `source_type` — `subreddit_post` or `user_history`
- One column per schema field (e.g. `age`, `sex_gender`, `conditions`, ...)
- With `--provenance`: additional `{field}__confidence` and `{field}__provenance` columns

### `output/codebook.csv`

One row per field.  Columns: field name, source, description, confidence tier,
ICD-10 code, observed coverage %, example values.

### `output/demographics.csv` (LLM-only approach)

Columns: `author_hash`, `source_type`, `age`, `sex_gender`,
`location_country`, `location_state`, `confidence`, `evidence`.

---

## Environment Setup

```bash
# Install dependencies
pip install anthropic python-dotenv

# Create .env at the project root (PatientPunk/.env)
cp ../.env.example ../.env
# Edit ../.env — add your Anthropic API key
```

The `.env` file at the project root is the canonical location for API keys.
It is shared by both Shaun's extraction pipeline and Polina's sentiment
pipeline.  A local `demographic_extraction/.env` is also checked as a
fallback.  Phase 1 (regex) and Phases 4–5 (export) require no API key.

---

## Running Tests

```bash
cd demographic_extraction
python -m pytest tests/ -v
```

39 tests cover pure utility functions (no API calls, no file I/O):
- JSON parsing helpers
- Regex pattern evaluation
- Text collection from posts/users
- Schema merge logic
- Schema pattern compilation + spot-checks against the real schema file

---

## Join Key

The `author_hash` column is a **SHA-256 hash of the Reddit username**.

This is the join key between:
- **Shaun's pipeline** (this module) — demographic and clinical extraction
- **Polina's pipeline** — drug sentiment and NLP analysis

> ⚠️ The legacy `records_to_csv.py` script truncated `author_hash` to 16
> characters for display.  The current library preserves the full 64-character
> hash.  When joining with data produced by the old script, join on `post_id`
> using `subreddit_posts.json` as a bridge.
