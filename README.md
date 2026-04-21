# PatientPunk

Reddit, patient forums, and social media overflow with firsthand patient reports: symptoms, treatments tried, outcomes, comorbidities, demographics. This signal disappears into forum threads. PatientPunk is the infrastructure to aggregate it, normalize it, and make it queryable at scale.

Patient self-reports aren't soft evidence — they're the only source of ground truth for the lived experience of disease. No biomarker tells you whether someone can get out of bed. No clinical trial follows patients long enough to capture the years-long arc of ME/CFS or long COVID. Self-reported qualitative markers ("I crash after any exertion," "went from bedbound to functional on this protocol") are treated here as first-class fields — dimensions to slice and filter on, not noise to discard.

A researcher can ask:

> *"Do patients with ME/CFS, neuroinflammation, and brain fog report positive outcomes with LDN?"*

And get back:

> **64% positive · 20% negative · 16% no effect** *(312 reports)*

---

## Architecture Overview

**[View pipeline diagram](docs/pipeline_diagram.pdf)**

The pipeline reads posts from a SQLite database and produces a sentiment database: for each post/comment × drug pair, did this author have a positive, negative, or mixed experience?

A key design principle: reply chain context is preserved. A short reply like "same, it really helped me" is correctly attributed to the drug being discussed in the parent post. Each entry carries both drugs_direct (mentioned in that post/comment) and drugs_context (inherited from upstream comments via the parent chain).

The pipeline also extracts demographic data for each user, including age bucket, sex, and location (in progress). For each user, when available, it extracts their conditions, onset and recovery time, and severity.

---

## Installation

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13.

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install dependencies
git clone https://github.com/Ely-S/PatientPunk.git
cd PatientPunk
uv sync

# Set up your LLM API key
cp .env.example .env
```

All pipeline commands are prefixed with `uv run`. Run tests with `uv run pytest -v`.

### LLM Provider

The pipeline supports two providers: **Anthropic** (direct) and **OpenRouter** (any model).

**Option A — Anthropic (default):**
```bash
export ANTHROPIC_API_KEY=your_key_here
```

**Option B — OpenRouter:**
```bash
export OPENROUTER_API_KEY=your_key_here
```

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


You can also put these in a `.env` file in the project root — the pipeline loads it automatically.

The provider is auto-detected from whichever key is set. To force a specific provider:
```bash
export LLM_PROVIDER=openrouter   # or "anthropic"
```

### Using non-Anthropic models (Qwen, Llama, Gemini, etc.)

Any model available on [OpenRouter](https://openrouter.ai/models) can be used. Set the `MODEL_FAST` and `MODEL_STRONG` environment variables to the OpenRouter model ID:

```bash
# Step 1: Set your OpenRouter key
export OPENROUTER_API_KEY=your_key_here

# Step 2: Pick a model from https://openrouter.ai/models
#         Use the model ID exactly as shown on OpenRouter.
export MODEL_FAST="qwen/qwen-2.5-7b-instruct"
export MODEL_STRONG="qwen/qwen-2.5-7b-instruct"
```

---

## Running the Pipeline

### Step 1 — Get the Reddit Data

**Option A — Arctic Shift API**:

Pulls posts from r/covidlonghaulers via the [Arctic Shift](https://github.com/ArthurHeitmann/arctic_shift) API — no Reddit API key required. Usernames are SHA-256 hashed before touching disk.

```bash
uv run python Scrapers/scrape_corpus.py --months 6 --comments --user-histories
# Outputs:
#   output/subreddit_posts.json     posts (+ comments if --comments)
#   output/users/{hash}.json        per-author history (only with --user-histories)
#   output/corpus_metadata.json     run summary
```

Currently hardcoded to r/covidlonghaulers. See [Scrapers/README.md](Scrapers/README.md) for all flags, time estimates, and user history options. Note: the scraper writes to `output/`, not `data/`.

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
    --output output/subreddit_posts.json
```

Supports `.zst` compressed files. Works with any subreddit — not hardcoded.


### Step 2 — Import into SQLite database

```bash
mkdir -p data
sqlite3 data/posts.db < schema.sql
uv run python src/import_posts.py \
    --reddit-posts output/subreddit_posts.json \
    --output-db data/posts.db
```

### Step 3a — Demographic extraction *(who are the patients?)*

Groups posts by user, sends them to a fast model, and extracts demographics and conditions.

In `user_profiles`, we store demographic data that is inferred from the user's posts: age bucket, sex, and location. In the `conditions` table, we store the conditions that are inferred from the user's posts, along with the type of condition (illness or symptom), the severity of the condition, and the date of diagnosis and resolution. Both of these may have empty values if the model fails to extract any information.

```bash
uv run python src/extract_demographics_conditions.py --db data/posts.db
```

| Flag | Description |
|------|-------------|
| `--db` | Path to SQLite database (required) |
| `--limit N` | Limit to N users (default: all) |
| `--max-posts N` | Max posts per user sent to LLM (default: 10) |
| `--max-chars N` | Max characters per post (default: 500) |


### Step 3b — Drug sentiment *(what do they say about treatments?)*

A general-purpose pipeline for building a sentiment database across all drugs and interventions mentioned in the corpus. It automatically discovers every drug/supplement/intervention mentioned — including categories like "antihistamines", enzymes like "DAO", and generic references like "an oral antibiotic" — normalizes synonyms, and classifies how each author feels about each treatment, without any hardcoded drug list.

A key design principle: **reply chain context is preserved**. Each entry carries both `drugs_direct` (mentioned in that post/comment) and `drugs_context` (inherited from upstream comments). A short reply like "same, it really helped me" is correctly attributed to the drug being discussed in the parent post.

```bash
uv run python src/run_sentiment_pipeline.py \
    --db data/posts.db \
    --output-dir outputs
```

Add `--limit 50` for a quick demo run.

| Flag | Description |
|------|-------------|
| `--db` | Path to SQLite database (required) |
| `--output-dir` | Directory for intermediate files (required) |
| `--limit N` | Process only the first N posts/comments (default: all) |
| `--skip-canonicalize` | Skip synonym normalization |
| `--reclassify` | Re-classify all pairs, even those already in the database |
| `--max-upstream-chars N` | Truncate upstream comment text to N chars (default: unlimited) |
| `--max-upstream-depth N` | Max upstream hops for drug context (default: unlimited) |

Steps 3a and 3b are independent — run in either order. Both are keyed on `author_hash` (SHA-256 of username).

---

## Drug Sentiment Pipeline — Internals

### Step 1 — Extract (`pipeline/extract.py`)

Reads posts/comments from the `posts` table in SQLite. Asks a fast model (e.g. Haiku) to identify all drugs/supplements/interventions mentioned. Extracts specific drugs, brand names, abbreviations, drug categories ("antihistamines", "beta blocker"), enzymes/supplements ("DAO", "probiotics"), and generic references ("an oral antibiotic"). Uses batching (20 texts per call) with automatic retry on mismatch (splits into smaller batches, up to 2 levels of recursion). Saves incrementally every 5 batches.

**Upstream context:** For each comment, `drugs_context` is computed by walking up the parent chain (up to the maximum number of steps specified) and collecting all `drugs_direct` from upstream comments. This ensures a reply to an LDN thread carries LDN in its context even if it doesn't mention LDN by name. 

**Output:** `tagged_mentions.json` — intermediate file with drug mentions per entry.

### Step 2 — Canonicalize (`pipeline/canonicalize.py`)

Collects all unique drug names from `tagged_mentions.json`, sends them to a fast model in batches, and merges true synonyms (e.g. `"low dose naltrexone"` → `"ldn"`, `"pepcid"` → `"famotidine"`). Rewrites `tagged_mentions.json` in place with canonical names.

**Rule:** only collapses true synonyms — does NOT merge a specific drug into a broader category (e.g. `famotidine` and `antihistamines` stay separate).

Also populates the `treatment` table from the drug names and canonical map. Each unique drug name becomes a row; aliases are stored as a JSON array. Uses `INSERT OR IGNORE` so re-runs are safe.

Can be skipped with `--skip-canonicalize` (raw drug names inserted into the treatment table with no aliases).

### Step 3 — Classify (`pipeline/classify.py`)

For each entry × drug pair, classifies the author's sentiment. Two-stage process to minimize API cost:

1. **Fast Model prefilter** (cheap) — asks "does this author express personal experience with this drug?" Batches 20 items per call. Explicitly rejects questions ("Have you tried X?") and research discussions. Filtered entries are not persisted.

2. **Strong Model classifier** (accurate) — for entries that pass, classifies sentiment and signal strength. Batches 5 items per drug (shared system prompt). The system prompt includes synonym info from the `treatment` table so the model knows "naltrexone" in upstream comment text = "ldn". The subreddit name is read from the database and injected into the prompt.

**Reply chain handling:** Upstream comment text is included in both the prefilter and classifier so the model can resolve pronouns ("I love it too" → positive, where "it" = the drug in the parent post).

**Output:** Rows in `treatment_reports` table, written incrementally via `ReportWriter`. Each row links a `post_id` to a `drug_id` with sentiment and signal strength. Progress is preserved across crashes — on re-run, pairs already in the table are skipped.

| Column | Values |
|--------|--------|
| `sentiment` | `positive`, `negative`, `mixed`, `neutral` |
| `signal_strength` | `strong`, `moderate`, `weak`, `n/a` |

---

## Run traceability

Each pipeline run creates a new row in `extraction_runs` with a unique `run_id`, along with the timestamp, git commit hash, extraction type, and config used. Every row written to `treatment_reports`, `user_profiles`, and `conditions` is tagged with this `run_id`, so results are always traceable to the exact run that produced them.

Re-running the pipeline does not delete old data. The classify step skips `(post_id, drug_id)` pairs that already exist in `treatment_reports`, so only new pairs are processed. Use `--reclassify` to force re-classification of all pairs — old results are preserved with their original `run_id` alongside the new ones.

---

## Crash recovery

The pipeline is designed to resume after interruptions:

- **Extract:** Already-extracted entries are cached in `tagged_mentions.json` and skipped on re-run. Saves every 5 batches.
- **Canonicalize:** Re-runs fully (cheap fast model calls on drug names only). Treatment table uses `INSERT OR IGNORE`.
- **Classify:** `ReportWriter` loads all existing `(post_id, drug_id)` pairs at startup and skips them. Commits to SQLite every 5 writes, so at most 5 results are lost on crash.

---

## Output

Results live in the `treatment_reports` table:

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

-- Top drugs by report count
SELECT t.canonical_name, COUNT(*) as n
FROM treatment_reports tr
JOIN treatment t ON tr.drug_id = t.id
GROUP BY t.canonical_name
ORDER BY n DESC
LIMIT 20;
```

---

## Built at

Biotech Hackathon · San Francisco · April 4, 2026 · Frontier Tower
