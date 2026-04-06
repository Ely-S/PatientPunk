# database_creation

Pipeline for building a user-drug sentiment database from Reddit posts.

Unlike `classify_intervention.py` (which targets a single intervention at a time), this pipeline scans all posts, automatically extracts every drug/supplement/intervention mentioned, and classifies sentiment for each — building a reusable database that can be queried across any drug.

**Reply chain context is always preserved.** Each entry stores its `parent_id`, and at classification time the parent text is looked up and included so the classifier understands what short replies ("I love it too", "same here") are referring to. `drugs_context` captures drugs mentioned in the parent chain even when the reply itself doesn't name them directly.

---

## Pipeline

Run scripts in order:

### 1. `extract_mentions.py`
Scans every post and comment. For each entry, asks Haiku to list all drugs, supplements, and interventions mentioned. Tags each entry with:
- `drugs_direct` — drugs mentioned in the text itself
- `drugs_context` — drugs mentioned in the parent/ancestor chain

**Outputs:**
- `tagged_mentions.json` — all entries with drug tags
- `mentions_cache.json` — Haiku extraction results (cached by entry ID)

```
python database_creation/extract_mentions.py
python database_creation/extract_mentions.py --limit 100   # test run
```

---

### 2. `canonicalize.py`
Collapses synonym drug names into a single canonical form (e.g. "low dose naltrexone" → "ldn", "pepcid" → "famotidine"). Uses Haiku to identify synonyms.

**Rules:**
- Only merges true synonyms (same drug, different names)
- Does NOT roll specific drugs into categories (e.g. "famotidine" ≠ "antihistamines")

**Outputs:**
- `canonical_map.json` — mapping of every raw name to its canonical form
- Rewrites `tagged_mentions.json` in place with canonical drug names

```
python database_creation/canonicalize.py
```

---

### 3. `classify_sentiment.py`
For every entry × drug pair in `tagged_mentions.json`, classifies the author's sentiment toward that drug using the same prompt as `classify_intervention.py`.

**Two-stage classification:**
1. **Haiku prefilter** — does this entry express personal experience with this drug? (cheap)
2. **Sonnet classifier** — sentiment + signal for entries that pass (only what's needed)

Filters out pure-question entries before classification.

**Outputs:**
- `sentiment_cache.json` — keyed `entry_id:drug`, stores `{sentiment, signal, author, text}`
- `sentiment_prefilter_cache.json` — Haiku yes/no per `entry_id:drug` pair

```
python database_creation/classify_sentiment.py
python database_creation/classify_sentiment.py --limit 100
python database_creation/classify_sentiment.py --debug-ldn   # only process LDN entries
```

---

## Output files

| File | Description |
|------|-------------|
| `tagged_mentions.json` | Every entry with drug tags (drugs_direct + drugs_context) |
| `mentions_cache.json` | Haiku drug extraction cache |
| `canonical_map.json` | Raw drug name → canonical name mapping |
| `sentiment_cache.json` | Sonnet sentiment results per entry×drug |
| `sentiment_prefilter_cache.json` | Haiku prefilter results per entry×drug |

---

## Main output: `sentiment_cache.json`

The primary output of the pipeline. Keyed `entry_id:drug`, each value contains the sentiment classification for that entry toward that drug.

```json
{
  "t1_odx7mni:ldn": {
    "sentiment": "positive",
    "signal": "strong",
    "author": "abc123...",
    "text": "LDN has been a game changer for my fatigue...",
    "created_utc": "2026-03-01T14:32:00+00:00"
  },
  "t1_oe5kcrv:ldn": {
    "sentiment": "negative",
    "signal": "moderate",
    "author": "def456...",
    "text": "Tried LDN for 3 months, no changes unfortunately.",
    "created_utc": "2026-02-15T09:11:00+00:00"
  },
  "t1_odx9bxf:pacing": {
    "sentiment": "positive",
    "signal": "strong",
    "author": "ghi789...",
    "text": "I've got it dialed now at year 3...",
    "created_utc": "2026-01-20T18:45:00+00:00"
  }
}
```

The drug name and entry ID are always recoverable from the key by splitting on `:`.

---

## Sentiment categories

| Sentiment | Meaning |
|-----------|---------|
| `positive` | Author tried it and it helped |
| `negative` | Author tried it and it didn't help or made things worse |
| `mixed` | Conflicting outcomes |
| `neutral` | Author has not personally tried it |
| `implicit_positive` | *(behavioral only)* Author implies it works by expressing NOT doing it made things worse |

## Signal strength

| Signal | Meaning |
|--------|---------|
| `strong` | Quantified results, specific symptoms, emphatic language |
| `moderate` | Simple affirmation without detail |
| `weak` | Mentioned in passing, in a stack without ranking |
