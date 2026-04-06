# Contributing to PatientPunk

PatientPunk treats Reddit patient self-reports as first-class scientific evidence — aggregating and normalising them into structured, queryable datasets for medical researchers. This document covers the project architecture, data model, and how to extend the system.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Repository Structure](#repository-structure)
3. [Architecture](#architecture)
4. [Data Model — PatientPunk v2.0 Record](#data-model--patientpunk-v20-record)
5. [The Two-Layer Schema System](#the-two-layer-schema-system)
6. [Writing an Extension Schema](#writing-an-extension-schema)
7. [Adding or Modifying Regex Patterns](#adding-or-modifying-regex-patterns)
8. [Scraper Internals](#scraper-internals)
9. [Privacy Model](#privacy-model)
10. [Development Setup](#development-setup)
11. [Testing Your Changes](#testing-your-changes)

---

## Project Overview

The pipeline has four stages:

```
Stage 1: scrape_corpus.py
  Reddit (via Arctic Shift API)  →  raw JSON corpus  (output/)

Stage 2: extract_biomedical.py
  raw JSON corpus                →  structured PatientPunk records  (regex, fast, free)

Stage 3: llm_extract.py
  raw JSON corpus + schema       →  LLM-enhanced records  (Haiku, fills regex gaps)

Stage 4: discover_fields.py
  raw JSON corpus                →  new fields + regex + extraction  (Haiku + Sonnet)
```

Stages 1-2 have no API dependencies. Stages 3-4 require an Anthropic API key.
Each stage can be run independently. The scraper has no knowledge of the extractor's schema.

---

## Repository Structure

```
Scrapers/
├── scrape_corpus.py                    # Stage 1: corpus scraper
├── requirements.txt                    # pip dependencies (requests only)
├── .env.example                        # Reddit credentials template (not used by default)
├── .gitignore
├── README.md                           # User-facing quick-start
├── SCRAPER_HELP.md                     # Full flag reference for scrape_corpus.py
├── CONTRIBUTING.md                     # This file
│
└── demographic_extraction/
    ├── extract_biomedical.py           # Stage 2: regex extractor + schema engine
    ├── llm_extract.py                  # Stage 3: LLM gap-filler (Haiku)
    ├── discover_fields.py              # Stage 4: multi-model field discovery pipeline
    ├── .env.example                    # Anthropic API key template
    └── schemas/
        ├── base_schema.json            # Documentation manifest (not loaded at runtime)
        ├── covidlonghaulers_schema.json  # Hand-crafted extension schema
        └── discovered_*.json           # Auto-generated schemas from discover_fields.py
```

**output/** (gitignored) is created at runtime by `scrape_corpus.py` and read by `extract_biomedical.py`.

---

## Architecture

### Stage 1 — Scraper (`scrape_corpus.py`)

Uses the [Arctic Shift](https://arctic-shift.photon-reddit.com) public Reddit archive API — no API key required. Fetches:
- Posts within a configurable time window (`--months` / `--weeks`)
- Full comment trees per post (`--comments`)
- Full author post/comment histories across all subreddits (`--user-histories`)
- Reddit profile metadata: karma, bio, account age, avatar (`--enrich-profiles`)

All usernames are **SHA-256 hashed** before writing to disk. Raw usernames never touch the filesystem.

Writes are **incremental** — each user file is flushed to disk as soon as it is complete. A crash mid-run preserves all already-scraped data.

### Stage 2 — Extractor (`extract_biomedical.py`)

Reads the corpus and runs regex pattern matching across all text fields. Key design decisions:

- **Two-layer schema**: a fixed universal *base* (23 fields always extracted) plus optional researcher-defined *extension* fields loaded from a JSON schema file (`--schema`).
- **No model inference required** — pure Python regex, runs anywhere.
- **Structured output** — every record is a fully-normalised v2.0 PatientPunk record; missing fields are `null`, not absent.
- **ICD-10 mapping** — condition values in the `conditions` field are automatically mapped to ICD-10 codes where known.
- **Provenance tracking** — every field carries `"self_reported"` (user history) or `"mentioned_by_other"` (subreddit post) provenance.

---

## Data Model — PatientPunk v2.0 Record

Every record written to `patientpunk_records_*.json` has this structure:

```json
{
  "_patientpunk_version": "2.0",
  "_schema_id": "covidlonghaulers_v1",
  "_extracted_at": "2026-04-05T12:00:00+00:00",

  "record_meta": {
    "author_hash": "a3f8c2...",
    "source": "user_history",
    "text_count": 412,
    "post_id": null
  },

  "base": {
    "conditions": {
      "values": ["long covid", "pots"],
      "icd10_candidates": {"long covid": "U09.9", "pots": "G90.3"},
      "provenance": "self_reported",
      "confidence": "high"
    },
    "age": {
      "values": ["34"],
      "provenance": "self_reported",
      "confidence": "medium"
    },
    "time_to_diagnosis": {
      "values": null,
      "provenance": null,
      "confidence": null
    }
    ...
  },

  "extension": {
    "vaccination_status": {
      "values": ["fully vaccinated"],
      "provenance": "self_reported",
      "confidence": "medium"
    }
    ...
  }
}
```

### Field object schema

Every extracted field (in both `base` and `extension`) is an object with four keys:

| Key | Type | Notes |
|---|---|---|
| `values` | `list[str]` or `null` | Deduplicated match list; `null` if nothing found |
| `icd10_candidates` | `dict` or `null` | `{value: code}` map; only present on `conditions` |
| `provenance` | `"self_reported"` \| `"mentioned_by_other"` \| `null` | `null` when `values` is `null` |
| `confidence` | `"high"` \| `"medium"` \| `"low"` \| `null` | From `BASE_FIELD_CONFIDENCE` or schema; `null` when `values` is `null` |

### `source` values

| Value | Meaning |
|---|---|
| `user_history` | Text from a user's full cross-subreddit history (scraped with `--user-histories`) |
| `subreddit_post` | Text from a post + its comments in the target subreddit |

### `_schema_id`

`"base"` for a base-only run. The schema's `schema_id` string for an extension run. Used to namespace output files: `patientpunk_records_{schema_id}.json`.

---

## The Two-Layer Schema System

### Layer 1 — Base fields (always extracted)

23 fields defined in `BASE_FIELDS` (a `frozenset` in `extract_biomedical.py`). These are extracted on every run regardless of whether a `--schema` is passed. They cover the core signals useful to any disease researcher:

| Category | Fields |
|---|---|
| Demographics | `age`, `sex_gender`, `location_country` |
| Healthcare access | `healthcare_system`, `diagnosis_source`, `time_to_diagnosis`, `misdiagnosis` |
| Conditions | `conditions`, `onset_trigger` |
| Symptoms | `symptom_duration`, `symptom_trajectory`, `age_at_onset` |
| Treatments | `medications`, `treatment_outcome`, `procedures` |
| Functional status | `activity_level`, `work_disability_status`, `mental_health` |
| Experience | `doctor_dismissal`, `diagnostic_odyssey` |
| History | `prior_infections`, `hormonal_events`, `family_history` |

### Layer 2 — Base-optional fields

12 additional fields exist in `PATTERNS` but are **not extracted by default**. They are available for extension schemas to activate via `include_base_fields`. These tend to be noisier or more study-specific:

`location_us_state`, `ethnicity`, `occupation`, `bmi_weight`, `dosage`, `dietary_interventions`, `alternative_treatments`, `genetic_testing`, `social_impact`, `trauma_history`, `toxic_exposures`, `healthcare_costs`

### Extension fields

Entirely new fields defined in the schema's `extension_fields` block with their own regex patterns. These only appear in the record's `extension` namespace.

---

## Writing an Extension Schema

Create a `.json` file in `demographic_extraction/schemas/`. It will be validated at startup before any extraction runs — bad patterns or missing keys produce a clear error and early exit.

### Minimal schema

```json
{
  "schema_id": "my_study_v1",
  "extension_fields": {
    "my_new_field": {
      "description": "What this field captures",
      "confidence": "medium",
      "patterns": [
        "\\b(pattern one|pattern two)\\b",
        "another pattern \\d+"
      ]
    }
  }
}
```

### Full schema reference

```json
{
  "schema_id": "string — used in output filenames and record metadata",
  "_description": "optional — human-readable description, ignored at runtime",

  "include_base_fields": [
    "dosage",
    "location_us_state",
    "healthcare_costs"
  ],

  "override_base_patterns": {
    "conditions": {
      "mode": "append",
      "patterns": ["\\b(my disease|variant name)\\b"]
    },
    "medications": {
      "mode": "replace",
      "patterns": ["\\b(drug a|drug b|drug c)\\b"]
    }
  },

  "extension_fields": {
    "my_field": {
      "description": "Human-readable description (not used at runtime)",
      "confidence": "high",
      "patterns": [
        "\\b(value one|value two)\\b"
      ]
    }
  }
}
```

### Schema keys

| Key | Required | Description |
|---|---|---|
| `schema_id` | **Yes** | Short identifier string. Used in output filenames. |
| `include_base_fields` | No | List of base-optional field names to activate |
| `override_base_patterns` | No | Modify patterns on existing base fields (append or replace) |
| `extension_fields` | No | New fields not in the base at all |

### `override_base_patterns`

Each entry needs:
- `"mode"`: `"append"` (add your patterns alongside existing ones) or `"replace"` (use only your patterns)
- `"patterns"`: list of regex strings

### `extension_fields`

Each entry needs:
- `"patterns"`: list of regex strings (required)
- `"confidence"`: `"high"`, `"medium"`, or `"low"` (optional, defaults to `"medium"`)
- `"description"`: free text, ignored at runtime (optional)

### Regex tips

- All patterns are compiled with `re.IGNORECASE`
- Use `\\b` for word boundaries (double-escape in JSON)
- Prefer captured groups `(like this)` — the extractor uses `m.group(1)` when a group is present, falling back to the full match
- Test your patterns with `--text` before running the full corpus:

```bash
python extract_biomedical.py --text "your test sentence" --schema schemas/my_schema.json
```

---

## Adding or Modifying Regex Patterns

All base patterns live in the `PATTERNS` dict in `extract_biomedical.py`. Each key maps to a list of compiled `re.Pattern` objects.

### To add a pattern to an existing base field

Find the field's entry in `PATTERNS` and append a `re.compile(...)` to its list:

```python
"medications": [
    re.compile(r"\b(existing|patterns|here)\b", re.I),
    re.compile(r"\b(your new drug|brand name)\b", re.I),  # add here
],
```

### To add a new base-optional field

1. Add it to `PATTERNS` with its pattern list
2. It will automatically be available for extension schemas via `include_base_fields`
3. If it should be extracted by default, add its name to `BASE_FIELDS` and add a confidence tier to `BASE_FIELD_CONFIDENCE`

### Confidence tiers

`BASE_FIELD_CONFIDENCE` (in `extract_biomedical.py`) stores the confidence tier for each base field:

| Tier | Meaning |
|---|---|
| `"high"` | Patterns are precise; low false-positive rate |
| `"medium"` | Patterns are reasonable but context-dependent |
| `"low"` | Patterns are broad; results need downstream validation |

### ICD-10 mapping

`CONDITION_ICD10_MAP` (in `extract_biomedical.py`) maps lowercased condition strings to ICD-10 codes. To add a mapping, add an entry:

```python
"my condition": "X00.0",
```

The key must match exactly what the regex extracts (lowercased). The mapping is applied during `build_record` to the `conditions` field only.

---

## Scraper Internals

Key functions in `scrape_corpus.py`:

| Function | Purpose |
|---|---|
| `window_start_iso(months, weeks)` | Returns `(iso_timestamp, label)` for the time window. Uses `strftime("%Y-%m-%dT%H:%M:%SZ")` — Arctic Shift requires `Z` suffix, no microseconds |
| `count_posts_in_window(subreddit, after)` | Phase 0 lightweight post count before full scrape |
| `fetch_full_post(post_id)` | Fetches a single post via `/api/posts/ids` |
| `fetch_comments_for_post(post_id)` | Paginated comment fetch via `/api/comments/search` |
| `scrape_user_history(username, enrich)` | Full cross-subreddit history for one author |
| `fetch_reddit_profile(username)` | Unauthenticated Reddit `about.json` call for profile metadata |

**Deduplication**: posts are deduplicated within a run using a `seen_post_keys` set of `(author.lower(), title.strip().lower())` tuples.

**Retry logic**: all API calls use exponential backoff on 5xx responses and rate-limit headers.

**Arctic Shift quirks**:
- Timestamp format must be `YYYY-MM-DDTHH:MM:SSZ` — `+00:00` suffix causes 400 errors
- The `fields` parameter is not supported — request full objects
- No authentication needed; no per-user rate limits documented

---

## Privacy Model

- Usernames are SHA-256 hashed with `hashlib.sha256(username.encode()).hexdigest()` immediately on receipt
- Raw usernames exist **only in memory** during a scrape and are never written to any file
- The `output/` directory is gitignored — never commit scraped data
- `.env` (if used) is gitignored

Do not add any feature that writes a raw username, email, or other PII to disk.

---

## Development Setup

```bash
# Clone and install
pip install -r requirements.txt        # just 'requests'

# Run the scraper (small test window)
python scrape_corpus.py --weeks 1 --comments

# Run the extractor
python demographic_extraction/extract_biomedical.py

# Test a single string (base only)
python demographic_extraction/extract_biomedical.py \
    --text "I'm a 34F with long COVID, housebound, on LDN 4.5mg"

# Test with an extension schema
python demographic_extraction/extract_biomedical.py \
    --text "omicron, fully vaccinated, 18 months of long covid" \
    --schema demographic_extraction/schemas/covidlonghaulers_schema.json

# Test schema validation error handling
python demographic_extraction/extract_biomedical.py --schema nonexistent.json
```

Python 3.12+ recommended. The extractor uses `dict | None` union syntax (Python 3.10+) and `list[str]` generics (Python 3.9+).

---

## Testing Your Changes

There is no automated test suite yet. Validate changes manually:

### 1. Spot-check extraction on known strings

```bash
python demographic_extraction/extract_biomedical.py --text "YOUR TEST STRING"
```

Confirm expected fields appear and no obvious false positives are present.

### 2. Schema round-trip

```bash
python demographic_extraction/extract_biomedical.py \
    --schema demographic_extraction/schemas/covidlonghaulers_schema.json \
    --text "I got omicron in 2022, fully vaccinated, 18 months of long covid, bedbound"
```

Expected extension output should include `covid_wave`, `vaccination_status`, `functional_status_tier`.

### 3. Full corpus run

After scraping with `scrape_corpus.py`, run the extractor on the real corpus and check:
- `patientpunk_records_base.json` — every record has all 23 base fields (null where not found)
- `extraction_metadata_base.json` — `field_hit_counts` shows reasonable hit rates
- No Python exceptions

### 4. Schema validation errors

```bash
# Missing schema file
python demographic_extraction/extract_biomedical.py --schema missing.json
# → "Schema file not found: missing.json"

# Missing schema_id
echo '{"extension_fields": {}}' > /tmp/bad.json
python demographic_extraction/extract_biomedical.py --schema /tmp/bad.json
# → "Schema missing required string field 'schema_id'"
```

### 5. Privacy check

```bash
grep -r "u/" output/ 2>/dev/null | head
grep -r "reddit.com/user" output/ 2>/dev/null | head
```

Both should return nothing. All usernames in output files should be 64-character hex strings.
