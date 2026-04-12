# PatientPunk

## The Problem

Reddit, patient forums, and social media are overflowing with firsthand patient reports: symptoms, treatments tried, outcomes, comorbidities, demographics. This data is qualitative, unstructured, and largely invisible to researchers. Patients who have tried dozens of treatments and documented their journeys in detail have no way to contribute that knowledge to science at scale.

Traditional clinical research has a structural blind spot: it relies on data it chooses to collect, from populations it chooses to study, on timelines measured in years and decades. Meanwhile, millions of patients are running informal experiments every day — trying treatments, tracking responses, reporting outcomes in plain language — and that signal disappears into forum threads.

## Patient Reports Are Data

Patient reports are the only source of ground truth for the lived experience of disease. No biomarker tells you whether someone can get out of bed. No lab value captures treatment-induced cognitive impairment. No clinical trial follows patients long enough to capture the years-long arc of a complex chronic illness. For conditions like ME/CFS, long COVID, POTS, and other poorly understood diseases, patient testimony is not a weak signal — it is often the *only* signal.

The problem is not the quality of patient data. The problem is that we have never had the infrastructure to aggregate it, normalize it, and make it queryable at scale. PatientPunk is that infrastructure.

## What PatientPunk Does

PatientPunk ingests patient-generated content from social media, normalizes it into structured records, and exposes it as queryable datasets for researchers and patient-driven scientists.

A patient or researcher can ask:

> *"Do other patients with ME/CFS, severe neuroinflammation, and brain fog report positive outcomes with LDN treatment?"*

And get back:

> **64% positive outcome · 20% negative outcome · 16% no effect**
> *(based on 312 patient reports)*

---

## Installation

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13+.

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install dependencies
git clone https://github.com/Ely-S/PatientPunk.git
cd PatientPunk
uv sync

# Set up your LLM API key
cp .env.example .env
# Edit .env — set one of:
#   OPENROUTER_API_KEY=your_key    (recommended — supports any model)
#   ANTHROPIC_API_KEY=your_key     (direct Anthropic access)
# The pipeline auto-detects which key is set.
```

### Running tests

```bash
uv run pytest -v
```

---

## Running the Pipeline

### Step 1 — Get Reddit data

Two options:

**Option A — Arctic Shift API** (live scraping, no Reddit API key needed):

```bash
uv run python Scrapers/scrape_corpus.py --months 6 --comments
# Outputs: data/subreddit_posts.json + data/users/*.json
```

Currently hardcoded to r/covidlonghaulers. See [Scrapers/README.md](Scrapers/README.md) for all flags, time estimates, and user history options.

| Flag | Description |
|------|-------------|
| `--months N` | How many months back to scrape (default: 2) |
| `--weeks N` | Alternative: weeks instead of months |
| `--comments` | Fetch full comment trees (recommended) |
| `--user-histories` | Scrape each author's full Reddit history (adds 2-4 hours) |
| `--limit-posts N` | Stop after N posts (for testing) |

**Option B — Arctic Shift bulk download** (faster for large datasets):

Download NDJSON files from [Arctic Shift](https://arctic-shift.photon-reddit.com/), then transform:

```bash
uv run python Scrapers/transform_arctic_shift.py \
    --posts r_covidlonghaulers_posts_6_months.jsonl \
    --comments r_covidlonghaulers_comments_6_months.jsonl \
    --output data/subreddit_posts.json
```

Supports `.zst` compressed files. Works with any subreddit — not hardcoded.

### Step 2 — Import into SQLite

```bash
sqlite3 data/posts.db < schema.sql
uv run python src/import_posts.py \
    --reddit-posts data/subreddit_posts.json \
    --output-db data/posts.db
```

### Step 3 — Run the drug sentiment pipeline

```bash
uv run python src/run_pipeline.py \
    --db data/posts.db \
    --output-dir data/drug_pipeline
```

This runs three stages automatically:
1. **Extract** — LLM identifies all drugs/supplements/interventions mentioned in each post
2. **Canonicalize** — LLM merges synonyms (e.g., "low dose naltrexone" + "ldn" + "naltrexone")
3. **Classify** — LLM classifies each user's sentiment toward each drug (positive/negative/mixed/neutral)

Results are written to the `treatment_reports` table in the SQLite database.

| Flag | Description |
|------|-------------|
| `--db` | Path to SQLite database with posts imported (required) |
| `--output-dir` | Directory for intermediate files (required) |
| `--limit N` | Process only the first N posts (default: all) |
| `--reclassify` | Re-run classification for all pairs, even those already in the DB |
| `--skip-canonicalize` | Skip synonym normalization |

### Step 4 (optional) — Demographic extraction

Extracts age, sex, location, conditions (POTS, MCAS, ME/CFS, etc.) from user post histories using regex + LLM.

```bash
uv run python Scrapers/demographic_extraction/run_pipeline.py \
    --schema Scrapers/demographic_extraction/schemas/covidlonghaulers_schema.json
```

See [Scrapers/README.md](Scrapers/README.md) for full documentation, flags, and cost estimates.

---

## LLM Provider

The pipeline supports **Anthropic** (direct) and **OpenRouter** (any model). The provider is auto-detected from which API key is set in `.env`.

### Using non-Anthropic models (Qwen, Llama, Gemini, etc.)

Any model on [OpenRouter](https://openrouter.ai/models) works. Set `MODEL_FAST` and `MODEL_STRONG` in your `.env`:

```bash
OPENROUTER_API_KEY=your_key
MODEL_FAST=qwen/qwen-2.5-7b-instruct
MODEL_STRONG=qwen/qwen-2.5-7b-instruct
```

`MODEL_FAST` is used for extraction and prefiltering (high volume, cheap). `MODEL_STRONG` is used for sentiment classification (lower volume, needs accuracy).

| Model | Cost | Notes |
|-------|------|-------|
| `anthropic/claude-haiku-4.5` | $0.80/1M | Default fast model. Best JSON reliability. |
| `anthropic/claude-sonnet-4.6` | $3.00/1M | Default strong model. Best classification quality. |
| `qwen/qwen-2.5-7b-instruct` | $0.04/1M | 20x cheaper. Works end-to-end but more batch retries. |
| `qwen/qwen-2.5-72b-instruct` | $0.12/1M | Good balance of cost and quality. |

Start with `--limit 50` to test a new model cheaply before running on the full dataset.

---

## Pipeline Architecture

The drug sentiment pipeline reads posts from SQLite and produces a sentiment database: for each post/comment x drug pair, did this author have a positive, negative, or mixed experience?

**Reply chain context is preserved.** A short reply like "same, it really helped me" is correctly attributed to the drug being discussed in the parent post. Each entry carries both `drugs_direct` (mentioned in that post/comment) and `drugs_context` (inherited from upstream comments via the parent chain).

### Step-by-step

**Extract** (`src/pipeline/extract.py`) — Asks a fast model to identify all drugs/supplements/interventions in each post. Batches 20 texts per call with automatic retry on mismatch. Saves incrementally every 5 batches. Output: `tagged_mentions.json`.

**Canonicalize** (`src/pipeline/canonicalize.py`) — Sends all unique drug names to a fast model in batches and merges true synonyms (e.g., "pepcid" -> "famotidine"). Only collapses true synonyms — does NOT merge a specific drug into a broader category. Populates the `treatment` table. Output: updated `tagged_mentions.json` + `canonical_map.json`.

**Classify** (`src/pipeline/classify.py`) — Two-stage process:
1. Fast model prefilter: "does this author express personal experience with this drug?" Rejects questions and research discussions.
2. Strong model classifier: classifies sentiment and signal strength. The system prompt includes synonym info so the model knows "naltrexone" = "ldn".

| Column | Values |
|--------|--------|
| `sentiment` | `positive`, `negative`, `mixed`, `neutral` |
| `signal_strength` | `strong`, `moderate`, `weak`, `n/a` |

### Crash recovery

- **Extract:** cached in `tagged_mentions.json`, skipped on re-run
- **Canonicalize:** re-runs fully (cheap). Treatment table uses `INSERT OR IGNORE`
- **Classify:** loads existing `(post_id, drug_id)` pairs at startup and skips them. Commits every 5 writes.

---

## Data Model

Three layers:

- **Layer 1 — Raw:** `users`, `posts` — scraped social media content
- **Layer 2 — Configuration:** `treatment`, `extraction_runs` — lookup tables and run metadata
- **Layer 3 — Extracted:** `user_profiles`, `conditions`, `treatment_reports` — LLM-extracted structured data

All tables join on `user_id` (SHA-256 hash of Reddit username).

**[View interactive schema diagram](schema_diagram_v5.html)** | **[schema.sql](schema.sql)**

### Example query

```sql
SELECT
  t.canonical_name                                   AS treatment,
  COUNT(DISTINCT tr.user_id)                         AS users,
  ROUND(AVG(CASE tr.sentiment
    WHEN 'positive' THEN 1.0 WHEN 'mixed' THEN 0.5
    WHEN 'neutral' THEN 0.0 WHEN 'negative' THEN -1.0
    ELSE 0.0 END), 2)                                AS avg_sentiment,
  SUM(CASE WHEN tr.sentiment = 'positive' THEN 1 ELSE 0 END)
    * 100.0 / COUNT(*)                               AS pct_positive
FROM treatment_reports tr
JOIN treatment t ON t.id = tr.drug_id
GROUP BY t.canonical_name
HAVING users >= 10
ORDER BY pct_positive DESC;
```

Note: sentiment is stored as TEXT strings in SQLite. Use the CASE expression above to convert to numeric for aggregation — `AVG(tr.sentiment)` on strings silently returns 0.

---

## Key Features

- **Modular ingestion** — swap in new data sources (Reddit, forums, health apps) without changing downstream logic
- **Any LLM provider** — works with Anthropic, OpenRouter (Qwen, Llama, Gemini), or any OpenAI-compatible API
- **Treatment outcome tracking** — classifies reported outcomes as positive, negative, neutral, or mixed
- **Cohort queries** — filter by condition profile, demographics, comorbidities, and treatment history
- **Reply chain context** — correctly attributes sentiment in comment threads to the drug being discussed
- **Crash recovery** — all pipeline steps resume cleanly after interruption
- **Privacy-first** — no PII stored; usernames SHA-256 hashed; posts anonymized before storage

---

## Ethical Commitments

- Data is used strictly for scientific and patient-benefit purposes
- No re-identification of individuals
- Opt-out mechanisms respected (deleted posts are purged)
- Transparent about data provenance in all exports

---

## Built at

Biotech Hackathon · San Francisco · April 4, 2026 · Frontier Tower
