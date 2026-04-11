# PatientPunk — Drug Mention Pipeline (`src/`)

General-purpose pipeline for building a sentiment database across all drugs and interventions mentioned in a Reddit corpus. Automatically discovers every drug/supplement/intervention mentioned (including categories like "antihistamines", enzymes like "DAO", and generic references like "an oral antibiotic"), normalizes synonyms, and classifies how each author feels about each drug — without any hardcoded drug list.

For rigorous, prompt-tuned analysis of a specific intervention, see `detailed_analysis/`.

---

## Overview

The pipeline reads posts from a SQLite database and produces a sentiment database: for each post/comment × drug pair, did this author have a positive, negative, or mixed experience?

A key design principle: **reply chain context is preserved**. A short reply like "same, it really helped me" is correctly attributed to the drug being discussed in the parent post. Each entry carries both `drugs_direct` (mentioned in that post/comment) and `drugs_context` (inherited from ancestors via the parent chain).

---

## Setup

```bash
pip install -r src/requirements.txt
export ANTHROPIC_API_KEY=your_key_here
```

---

## Running the pipeline

**Step 0 — Import posts into SQLite:**
```bash
sqlite3 data/posts.db < schema.sql
python src/import_posts.py \
  --reddit-posts data/subreddit_posts.json \
  --output-db data/posts.db
```

**Run the pipeline:**
```bash
python src/run_pipeline.py \
  --db data/posts.db \
  --output-dir outputs
```

| Flag | Description |
|------|-------------|
| `--db` | Path to SQLite database with posts already imported (required) |
| `--output-dir` | Directory for intermediate files (required) |
| `--limit N` | Process only the first N posts/comments (default: all) |
| `--skip-canonicalize` | Skip synonym normalization, classify using raw drug names |
| `--reclassify` | Re-classify all pairs, even those already in the database |

---

## Architecture

All pipeline steps accept a shared `PipelineConfig` dataclass (defined in `utilities/`), which holds the Anthropic client, output directory, database path, limit, and reclassify flag.

All LLM prompts live in `prompts/intervention_config.py` — one file for the extract prompt, canonicalization prompt, prefilter prompt, and the Sonnet classification system prompt.

Shared helpers (`llm_call`, `parse_json_array`, `parse_json_object`) and `LLMParseError` live in `utilities/__init__.py`, along with model constants (`MODEL_FAST = claude-haiku-4-5`, `MODEL_STRONG = claude-sonnet-4-6`).

Database helpers live in `utilities/db.py`: `open_db()` for connection setup, `upsert_treatments()` and `load_synonyms()` for the treatment table, and `ReportWriter` for incremental classification writes.

LLM classification responses are validated with a Pydantic model (`ClassificationResult` in `models.py`), enforcing `Literal` types for sentiment and signal values.

---

## Pipeline steps

### Step 1 — Extract (`pipeline/extract.py`)

Reads posts/comments from the `posts` table in SQLite. Asks Haiku to identify all drugs/supplements/interventions mentioned. Extracts specific drugs, brand names, abbreviations, drug categories ("antihistamines", "beta blocker"), enzymes/supplements ("DAO", "probiotics"), and generic references ("an oral antibiotic"). Uses batching (20 texts per call) with automatic retry on mismatch (splits into smaller batches, up to 2 levels of recursion). Saves incrementally every 5 batches.

**Ancestor context:** For each comment, `drugs_context` is computed by walking up the parent chain and collecting all `drugs_direct` from ancestors. This ensures a reply to an LDN thread carries LDN in its context even if it doesn't mention LDN by name.

**Output:** `tagged_mentions.json` — intermediate file with drug mentions per entry.

### Step 2 — Canonicalize (`pipeline/canonicalize.py`)

Collects all unique drug names from `tagged_mentions.json`, sends them to Haiku in batches of 50, and merges true synonyms (e.g. `"low dose naltrexone"` → `"ldn"`, `"pepcid"` → `"famotidine"`). Rewrites `tagged_mentions.json` in place with canonical names.

**Rule:** only collapses true synonyms — does NOT merge a specific drug into a broader category (e.g. `famotidine` and `antihistamines` stay separate).

Also populates the `treatment` table from the drug names and canonical map. Each unique drug name becomes a row; aliases are stored as a JSON array. Uses `INSERT OR IGNORE` so re-runs are safe.

Can be skipped with `--skip-canonicalize` (raw drug names inserted into the treatment table with no aliases).

### Step 3 — Classify (`pipeline/classify.py`)

For each entry × drug pair, classifies the author's sentiment. Two-stage process to minimize API cost:

1. **Haiku prefilter** (cheap) — asks "does this author express personal experience with this drug?" Batches 20 items per call. Explicitly rejects questions ("Have you tried X?") and research discussions. Filtered entries are not persisted.

2. **Sonnet classifier** (accurate) — for entries that pass, classifies sentiment and signal strength. Batches 5 items per drug (shared system prompt). The system prompt includes synonym info from the `treatment` table so the model knows "naltrexone" in ancestor text = "ldn". The subreddit name is read from the database and injected into the prompt.

**Reply chain handling:** Ancestor text is included in both the prefilter and classifier so the model can resolve pronouns ("I love it too" → positive, where "it" = the drug in the parent post).

**Pure-question filter:** Before any LLM calls, entries where every sentence ends with `?` are filtered out.

**Validation:** Each LLM classification response is validated through the `ClassificationResult` Pydantic model. Invalid sentiment or signal values raise `ValidationError` instead of silently writing bad data to the database.

**Output:** Rows in `treatment_reports` table, written incrementally via `ReportWriter`. Each row links a `post_id` to a `drug_id` with sentiment and signal strength. Progress is preserved across crashes — on re-run, pairs already in the table are skipped.

| Column | Values |
|--------|--------|
| `sentiment` | `positive`, `negative`, `mixed`, `neutral` |
| `signal_strength` | `strong`, `moderate`, `weak`, `n/a` |

---

## Error handling

LLM responses that can't be parsed as JSON raise `LLMParseError(ValueError)` instead of silently returning empty results. Callers catch this to trigger retry logic (e.g. splitting a failed batch into smaller pieces).

---

## Crash recovery

The pipeline is designed to resume after interruptions:

- **Extract:** Already-extracted entries are cached in `tagged_mentions.json` and skipped on re-run. Saves every 5 batches.
- **Canonicalize:** Re-runs fully (cheap Haiku calls on drug names only). Treatment table uses `INSERT OR IGNORE`.
- **Classify:** `ReportWriter` loads all existing `(post_id, drug_id)` pairs at startup and skips them. Commits to SQLite every 5 writes, so at most 5 results are lost on crash.

Use `--reclassify` to force re-classification of all pairs. Old results are preserved with their original `run_id` — nothing is deleted.

---

## Output

Results live in the `treatment_reports` table in the SQLite database:

```sql
-- All reports for a specific drug
SELECT tr.*, t.canonical_name
FROM treatment_reports tr
JOIN treatment t ON tr.drug_id = t.id
WHERE t.canonical_name = 'ldn';

-- Sentiment breakdown per drug
SELECT t.canonical_name, tr.sentiment, COUNT(*) as n
FROM treatment_reports tr
JOIN treatment t ON tr.drug_id = t.id
GROUP BY t.canonical_name, tr.sentiment
ORDER BY t.canonical_name, n DESC;

-- Top drugs by number of reports
SELECT t.canonical_name, COUNT(*) as n
FROM treatment_reports tr
JOIN treatment t ON tr.drug_id = t.id
GROUP BY t.canonical_name
ORDER BY n DESC
LIMIT 20;
```

---

## File structure

```
src/
  run_pipeline.py              # Orchestrates all steps
  import_posts.py              # Step 0: import Reddit JSON into SQLite
  models.py                    # ClassificationResult (Pydantic validation)
  requirements.txt
  pipeline/
    extract.py                 # Step 1: extract drug mentions from posts
    canonicalize.py            # Step 2: normalize synonyms + populate treatment table
    classify.py                # Step 3: two-stage sentiment classification
  utilities/
    __init__.py                # PipelineConfig, llm_call, LLMParseError, JSON parsing
    db.py                      # open_db, upsert_treatments, load_synonyms, ReportWriter
  prompts/
    intervention_config.py     # All LLM prompts in one place
```
