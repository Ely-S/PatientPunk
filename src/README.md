# PatientPunk — Drug Mention Pipeline (`src/`)

General-purpose pipeline for building a sentiment database across all drugs and interventions mentioned in a Reddit corpus. Automatically discovers every drug mentioned, normalizes synonyms, and classifies how each author feels about each drug — without any hardcoded drug list.

For rigorous, prompt-tuned analysis of a specific intervention, see `detailed_analysis/`.

---

## Overview

The pipeline takes a Reddit posts file and produces a sentiment database: for each post/comment × drug pair, did this author have a positive, negative, or mixed experience?

A key design principle: **reply chain context is preserved**. A short reply like "same, it really helped me" is correctly attributed to the drug being discussed in the parent post. Each entry carries both `drugs_direct` (mentioned in that post/comment) and `drugs_context` (inherited from ancestors).

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

**Run specific steps only:**
```bash
python src/run_pipeline.py \
  --posts-file data/subreddit_posts.json \
  --output-dir data/outputs \
  extract canonicalize
```

**Ignore existing caches and reprocess everything:**
```bash
python src/run_pipeline.py ... --regenerate-cache
```

Each step can also be run standalone — see the `Usage:` docstring at the top of each script.

---

## Pipeline steps

### Step 1 — `extract_mentions.py`

Scans every post and comment, asks Haiku to identify all drugs/supplements/interventions mentioned. Uses batching (20 texts per call) and saves incrementally.

**Output:** `tagged_mentions.json`

```json
{
  "id": "t1_abc123",
  "author": "<hashed>",
  "text": "I've been taking LDN for 3 months...",
  "post_title": "My LDN experience",
  "parent_id": "t3_xyz",
  "created_utc": "2026-01-01T00:00:00+00:00",
  "drugs_direct": ["ldn"],
  "drugs_context": ["mestinon"]
}
```

- `drugs_direct` — drugs mentioned in this post/comment's own text
- `drugs_context` — drugs from the ancestor chain (parent, grandparent, etc.)

### Step 2 — `canonicalize.py`

Collects all unique drug names from `tagged_mentions.json`, sends them to Haiku in batches of 50, and merges true synonyms (e.g. `"low dose naltrexone"` → `"ldn"`, `"pepcid"` → `"famotidine"`). Rewrites `tagged_mentions.json` in place with canonical names.

**Rule:** only collapses true synonyms — does NOT merge a specific drug into a broader category (e.g. `famotidine` and `antihistamines` stay separate).

**Output:** `canonical_map.json` — maps every raw name to its canonical form

### Step 3 — `classify_sentiment.py`

For each entry × drug pair, classifies the author's sentiment toward that drug. Two-stage process to minimize cost:

1. **Haiku prefilter** — asks "does this author express personal experience with this drug?" Batches 10 items per call. Filtered entries are stored in `filtered_cache.json` and skipped in future runs.
2. **Sonnet classifier** — for entries that pass, classifies sentiment and signal strength. Batches 5 items per drug (shared system prompt). Results saved to `sentiment_cache.json`.

**Output:** `sentiment_cache.json`

```json
{
  "t1_abc123:ldn": {
    "sentiment": "positive",
    "signal": "strong",
    "author": "<hashed>",
    "text": "LDN changed my life — I went from bedbound to walking...",
    "created_utc": "2026-01-01T00:00:00+00:00"
  }
}
```

Cache key format: `entry_id:drug_name`

Sentiment values: `positive`, `negative`, `mixed`, `neutral`
Signal values: `strong`, `moderate`, `weak`, `n/a`

---

## Output files

| File | Description |
|------|-------------|
| `tagged_mentions.json` | Every post/comment with drug mentions, including ancestor context |
| `canonical_map.json` | Raw drug name → canonical name mapping |
| `sentiment_cache.json` | Classified entry × drug pairs (real results only) |
| `filtered_cache.json` | Entry × drug pairs that didn't pass the prefilter (no personal experience) |

---

## File structure

```
src/
  run_pipeline.py          # Orchestrates all three steps
  requirements.txt
  scripts/
    extract_mentions.py    # Step 1: tag drugs in each post/comment
    canonicalize.py        # Step 2: normalize synonyms
    classify_sentiment.py  # Step 3: classify sentiment per entry×drug
  prompts/
    intervention_config.py # All LLM prompts (extract, canonicalize, prefilter, classify)
  utilities/
    __init__.py            # Shared: client, models, cache helpers, JSON parsing
```

---

## Querying the output

`sentiment_cache.json` is the main output. To get all entries for a specific drug:

```python
import json

cache = json.loads(open("data/outputs/sentiment_cache.json").read())
ldn = {k: v for k, v in cache.items() if k.endswith(":ldn")}
```

To get a breakdown by sentiment:
```python
from collections import Counter
Counter(v["sentiment"] for v in ldn.values())
# Counter({'positive': 42, 'neutral': 8, 'negative': 3, 'mixed': 2})
```
