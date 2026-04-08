# PatientPunk — Drug Mention Pipeline (`src/`)

General-purpose pipeline for building a sentiment database across all drugs and interventions mentioned in a Reddit corpus. Automatically discovers every drug/supplement/intervention mentioned (including categories like "antihistamines", enzymes like "DAO", and generic references like "an oral antibiotic"), normalizes synonyms, and classifies how each author feels about each drug — without any hardcoded drug list.

For rigorous, prompt-tuned analysis of a specific intervention, see `detailed_analysis/`.

---

## Overview

The pipeline takes a Reddit posts file and produces a sentiment database: for each post/comment x drug pair, did this author have a positive, negative, or mixed experience?

A key design principle: **reply chain context is preserved**. A short reply like "same, it really helped me" is correctly attributed to the drug being discussed in the parent post. Each entry carries both `drugs_direct` (mentioned in that post/comment) and `drugs_context` (inherited from ancestors via the parent chain).

---

## Setup

```bash
pip install -r src/requirements.txt
export ANTHROPIC_API_KEY=your_key_here
```

---

## Running the pipeline

**Full pipeline (all 3 steps):**
```bash
python src/run_pipeline.py \
  --posts-file data/subreddit_posts.json \
  --output-dir data/outputs \
  --limit 100
```

**Skip canonicalization:**
```bash
python src/run_pipeline.py \
  --posts-file data/subreddit_posts.json \
  --output-dir data/outputs \
  --skip-canonicalize
```

**Ignore existing caches and reprocess everything:**
```bash
python src/run_pipeline.py \
  --posts-file data/subreddit_posts.json \
  --output-dir data/outputs \
  --regenerate-cache
```

| Flag | Description |
|------|-------------|
| `--posts-file` | Path to the Reddit posts JSON file (required) |
| `--output-dir` | Directory for all output files (required) |
| `--limit N` | Process only the first N posts (default: 100) |
| `--skip-canonicalize` | Skip step 2, classify using raw drug names |
| `--regenerate-cache` | Ignore all existing caches and reprocess from scratch |

---

## Architecture

All pipeline steps accept a shared `PipelineConfig` dataclass (defined in `utilities/`), which holds the Anthropic client, output directory, posts file path, limit, and regenerate flag. This means each step can be run via `run_pipeline.py` or standalone.

All LLM prompts live in `prompts/intervention_config.py` — one file for the extract prompt, canonicalization prompt, prefilter prompt, and the Sonnet classification system prompt.

Shared helpers (`llm_call`, `process_in_batches`, `parse_json_array`, `load_cache`, `save_cache`) live in `utilities/__init__.py`, along with model constants (`MODEL_FAST = claude-haiku-4-5`, `MODEL_STRONG = claude-sonnet-4-6`).

---

## Pipeline steps

### Step 1 — `extract_mentions.py`

Scans every post and comment, asks Haiku to identify all drugs/supplements/interventions mentioned. Extracts specific drugs, brand names, abbreviations, drug categories ("antihistamines", "beta blocker"), enzymes/supplements ("DAO", "probiotics"), and generic references ("an oral antibiotic"). Uses batching (20 texts per call) with automatic retry on mismatch (splits into smaller batches, up to 2 levels of recursion). Saves incrementally every 5 batches.

**Ancestor context:** For each comment, `drugs_context` is computed by walking up the parent chain and collecting all `drugs_direct` from ancestors. This ensures a reply to an LDN thread carries LDN in its context even if it doesn't mention LDN by name.

**Output:** `tagged_mentions.json` — only entries with at least one drug (direct or context) are included.

```json
{
  "id": "t1_abc123",
  "author": "<sha256-hashed>",
  "text": "I've been taking LDN for 3 months...",
  "post_title": "My LDN experience",
  "parent_id": "t3_xyz",
  "created_utc": "2026-01-01T00:00:00+00:00",
  "drugs_direct": ["ldn"],
  "drugs_context": ["mestinon"]
}
```

- `drugs_direct` — drugs mentioned in this post/comment's own text
- `drugs_context` — drugs inherited from the ancestor chain (parent, grandparent, etc.)

### Step 2 — `canonicalize.py`

Collects all unique drug names from `tagged_mentions.json`, sends them to Haiku in batches of 50, and merges true synonyms (e.g. `"low dose naltrexone"` -> `"ldn"`, `"pepcid"` -> `"famotidine"`). Rewrites `tagged_mentions.json` in place with canonical names and deduplicates within each entry's drug lists.

**Rule:** only collapses true synonyms — does NOT merge a specific drug into a broader category (e.g. `famotidine` and `antihistamines` stay separate). This is important because categories and specific drugs carry different information.

Can be skipped with `--skip-canonicalize` if you want to classify using raw extracted names.

**Output:** `canonical_map.json` — maps every raw name to its canonical form.

### Step 3 — `classify_sentiment.py`

For each entry x drug pair, classifies the author's sentiment toward that drug. Two-stage process to minimize API cost:

1. **Haiku prefilter** (cheap) — asks "does this author express personal experience with this drug?" Batches 5 items per call. Explicitly rejects questions about the drug ("Have you tried X?") and research/article discussions. Entries that fail are kept in memory for the run but not persisted — only real results are saved.

2. **Sonnet classifier** (accurate) — for entries that pass, classifies sentiment and signal strength. Batches 5 items per drug (shared system prompt amortizes tokens). The system prompt includes synonym info from `canonical_map.json` so the model knows "naltrexone" in ancestor text = "ldn".

**Reply chain handling:** Ancestor text is included in both the prefilter and classifier so the model can resolve pronouns ("I love it too" -> positive, where "it" = the drug in the parent post). But the classifier only scores signal from the reply itself — ancestor text is context, not evidence.

**Pure-question filter:** Before any LLM calls, entries where every sentence ends with `?` are filtered out.

**Output:** `sentiment_cache.json` — only real classified results, no filtered entries.

```json
{
  "t1_abc123:ldn": {
    "sentiment": "positive",
    "signal": "strong",
    "author": "<sha256-hashed>",
    "text": "LDN changed my life -- I went from bedbound to walking...",
    "created_utc": "2026-01-01T00:00:00+00:00"
  },
  "t1_def456:famotidine": {
    "sentiment": "negative",
    "signal": "moderate",
    "author": "<sha256-hashed>",
    "text": "Famotidine did absolutely nothing for me after 3 months.",
    "created_utc": "2026-02-15T12:30:00+00:00"
  }
}
```

Cache key format: `entry_id:drug_name`

| Field | Values |
|-------|--------|
| `sentiment` | `positive`, `negative`, `mixed`, `neutral` |
| `signal` | `strong`, `moderate`, `weak`, `n/a` |

---

## Output files

| File | Description |
|------|-------------|
| `tagged_mentions.json` | Every post/comment with drug mentions, including ancestor context |
| `canonical_map.json` | Raw drug name -> canonical name mapping |
| `sentiment_cache.json` | Classified entry x drug pairs (real results only, the main output) |

---

## File structure

```
src/
  run_pipeline.py            # Orchestrates all three steps via PipelineConfig
  requirements.txt
  scripts/
    extract_mentions.py      # Step 1: tag drugs in each post/comment
    canonicalize.py          # Step 2: normalize synonyms
    classify_sentiment.py    # Step 3: two-stage sentiment classification
  prompts/
    intervention_config.py   # All LLM prompts in one place
  utilities/
    __init__.py              # PipelineConfig, OutputFiles, llm_call, process_in_batches, etc.
```

---

## Querying the output

`sentiment_cache.json` is the main output. To get all entries for a specific drug:

```python
import json

cache = json.loads(open("data/outputs/sentiment_cache.json").read())
ldn = {k: v for k, v in cache.items() if k.endswith(":ldn")}
```

Breakdown by sentiment:
```python
from collections import Counter
Counter(v["sentiment"] for v in ldn.values())
# Counter({'positive': 42, 'negative': 3, 'mixed': 2})
```

All drugs with counts:
```python
drug_counts = Counter(k.split(":", 1)[1] for k in cache)
drug_counts.most_common(20)
```

All entries for a specific author:
```python
author_entries = {k: v for k, v in cache.items() if v["author"] == "<hash>"}
```
