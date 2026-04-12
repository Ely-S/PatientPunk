# PatientPunk

Reddit, patient forums, and social media overflow with firsthand patient reports: symptoms, treatments tried, outcomes, comorbidities, demographics. This signal disappears into forum threads. PatientPunk is the infrastructure to aggregate it, normalize it, and make it queryable at scale.

Patient self-reports aren't soft evidence — they're the only source of ground truth for the lived experience of disease. No biomarker tells you whether someone can get out of bed. No clinical trial follows patients long enough to capture the years-long arc of ME/CFS or long COVID. Self-reported qualitative markers ("I crash after any exertion," "went from bedbound to functional on this protocol") are treated here as first-class fields — dimensions to slice and filter on, not noise to discard.

A researcher can ask:

> *"Do patients with ME/CFS, neuroinflammation, and brain fog report positive outcomes with LDN?"*

And get back:

> **64% positive · 20% negative · 16% no effect** *(312 reports)*

---

## Architecture

**[View pipeline diagram](docs/pipeline_diagram.pdf)**

---

## Key Features

- **Modular ingestion** — swap in new data sources without changing downstream logic
- **Symptom normalization** — maps patient language to standard medical ontologies
- **Treatment outcome tracking** — classifies reported outcomes as positive, negative, neutral, or mixed
- **Cohort queries** — filter by condition profile, demographics, comorbidities, and treatment history
- **Privacy-first** — no PII stored; usernames SHA-256 hashed; posts anonymized before storage
- **Researcher-ready exports** — CSV, SQL dumps, and structured JSON

---

## Example Query

```sql
SELECT
  t.canonical_name                                   AS treatment,
  COUNT(*)                                           AS reports,
  ROUND(AVG(tr.sentiment), 2)                        AS avg_sentiment,
  SUM(CASE WHEN tr.sentiment > 0 THEN 1 ELSE 0 END)
    * 100.0 / COUNT(*)                               AS pct_positive
FROM treatment_reports tr
JOIN treatment t ON t.id = tr.drug_id
WHERE EXISTS (
  SELECT 1 FROM conditions c
  WHERE c.user_id = tr.user_id
    AND c.condition_name = 'ME/CFS' COLLATE NOCASE
)
AND EXISTS (
  SELECT 1 FROM conditions c
  WHERE c.user_id = tr.user_id
    AND c.condition_name = 'brain fog' COLLATE NOCASE
)
GROUP BY t.canonical_name
ORDER BY reports DESC;
```

---

## Data Model

- **Layer 1 — Raw:** `users`, `posts` — scraped social media content
- **Layer 2 — Configuration:** `treatment`, `extraction_runs` — lookup tables and run metadata
- **Layer 3 — Extracted:** `user_profiles`, `conditions`, `treatment_reports` — LLM-extracted structured data

**[View interactive schema diagram](schema_diagram_v5.html)** · **[schema.sql](schema.sql)**

---

## Ethical Commitments

- Data used strictly for scientific and patient-benefit purposes
- No re-identification of individuals
- Opt-out mechanisms respected (deleted posts are purged)
- Data provenance transparent in all exports

---

## Installation

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13.

```bash
git clone https://github.com/Ely-S/PatientPunk.git
cd PatientPunk
uv sync

cp Scrapers/demographic_extraction/.env.example .env
# Edit .env and set ANTHROPIC_API_KEY=<your key>
export ANTHROPIC_API_KEY=<your key>
```

All pipeline commands are prefixed with `uv run`. Run tests with `uv run pytest -v`.

---

## Running the Pipeline

### Step 1 — Scrape

Pulls posts from r/covidlonghaulers via the [Arctic Shift](https://github.com/ArthurHeitmann/arctic_shift) API — no Reddit API key required. Usernames are SHA-256 hashed before touching disk.

```bash
uv run python Scrapers/scrape_corpus.py --months 6 --comments --user-histories
# Outputs:
#   output/subreddit_posts.json     posts (+ comments if --comments)
#   output/users/{hash}.json        per-author history (only with --user-histories)
#   output/corpus_metadata.json     run summary
```

`--comments` fetches full reply trees. `--user-histories` scrapes each author's full Reddit history — useful because patients document their journeys across many communities.

### Step 2 — Import into database

```bash
mkdir -p data
sqlite3 data/posts.db < schema.sql
uv run python src/import_posts.py \
    --reddit-posts output/subreddit_posts.json \
    --output-db data/posts.db
```

Preserves the `parent_id` chain between comments and parents — required for drug context propagation in Step 3b.

### Step 3a — Demographic extraction *(who are the patients?)*

Extracts structured patient attributes (vaccination status, functional tier, infection count, biomarkers, etc.) using regex patterns and Claude Haiku. Outputs a per-user CSV and codebook.

```bash
cd Scrapers/demographic_extraction
uv run python run_pipeline.py \
    --schema schemas/covidlonghaulers_schema.json \
    --input-dir ../../output
# Outputs:
#   Scrapers/output/records.csv
#   Scrapers/output/codebook.csv
```

Add `--limit 20 --no-discover` for a quick demo run (skips the LLM field-discovery phase).

### Step 3b — Drug sentiment *(what do they say about treatments?)*

General-purpose pipeline for building a sentiment database across all drugs and interventions mentioned in the corpus. Automatically discovers every drug/supplement/intervention mentioned — including categories like "antihistamines", enzymes like "DAO", and generic references like "an oral antibiotic" — normalizes synonyms, and classifies how each author feels about each treatment, without any hardcoded drug list.

A key design principle: **reply chain context is preserved**. Each entry carries both `drugs_direct` (mentioned in that post/comment) and `drugs_context` (inherited from upstream comments). A short reply like "same, it really helped me" is correctly attributed to the drug being discussed in the parent post.

```bash
uv run python src/run_pipeline.py \
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

Steps 3a and 3b are independent — run in either order. Both key on `author_hash` (SHA-256 of username).

---

## Drug Sentiment Pipeline — Internals

### Extract (`pipeline/extract.py`)

Reads posts/comments from the `posts` table. Asks Haiku to identify all drugs, supplements, and interventions mentioned — specific drugs, brand names, abbreviations, drug categories ("beta blocker"), enzymes/supplements ("DAO", "probiotics"), and generic references ("an oral antibiotic"). Uses batching (20 texts per call) with automatic retry on mismatch (splits into smaller batches, up to 2 levels of recursion). Saves incrementally every 5 batches.

**Upstream context:** For each comment, `drugs_context` is built by walking up the parent chain (up to `--max-upstream-depth` hops) and collecting all `drugs_direct` from upstream posts. This ensures a reply to an LDN thread carries LDN in context even if it doesn't name it.

**Output:** `tagged_mentions.json`

### Canonicalize (`pipeline/canonicalize.py`)

Collects all unique drug names from `tagged_mentions.json`, sends them to a fast model in batches, and merges true synonyms (`"low dose naltrexone"` → `"ldn"`, `"pepcid"` → `"famotidine"`). Rewrites `tagged_mentions.json` in place with canonical names.

**Rule:** only collapses true synonyms — does NOT merge a specific drug into a broader category (e.g. `famotidine` and `antihistamines` stay separate).

Also populates the `treatment` table. Each unique drug name becomes a row; aliases are stored as a JSON array. Uses `INSERT OR IGNORE` so re-runs are safe. Can be skipped with `--skip-canonicalize` (raw drug names are inserted into the treatment table with no aliases).

### Classify (`pipeline/classify.py`)

Two-stage process to minimize API cost:

1. **Haiku prefilter** — "does this author express personal experience with this drug?" Batches 20 items per call. Rejects questions ("Have you tried X?") and research discussions. Filtered entries are not persisted.
2. **Sonnet classifier** — classifies sentiment and signal strength. Batches 5 items per drug. System prompt includes synonym info from the `treatment` table so the model knows "naltrexone" in upstream text = "ldn". The subreddit name is read from the database and injected into the prompt. Upstream comment text is included so replies like *"I love it too"* resolve correctly.

**Output:** Rows in `treatment_reports`, written incrementally via `ReportWriter`. Each row links a `post_id` to a `drug_id`.

| Column | Values |
|--------|--------|
| `sentiment` | `positive`, `negative`, `mixed`, `neutral` |
| `signal_strength` | `strong`, `moderate`, `weak`, `n/a` |

---

## Data Overwriting

Each pipeline run creates a new row in `extraction_runs` with a unique `run_id`, timestamp, git commit hash, extraction type, and config. Every row written to `treatment_reports`, `user_profiles`, and `conditions` is tagged with this `run_id` so results are traceable to the exact run that produced them.

Re-running does not delete old data. The classify step skips `(post_id, drug_id)` pairs already in `treatment_reports`. Use `--reclassify` to force re-classification — old results are preserved with their original `run_id` alongside the new ones.

Demographics uses `INSERT OR REPLACE` on `user_profiles`, keyed on `(user_id, run_id)`, so re-running with the same run overwrites that run's results while different runs produce separate rows.

---

## Crash Recovery

- **Extract:** Cached in `tagged_mentions.json`; already-extracted entries are skipped on re-run. Saves every 5 batches.
- **Canonicalize:** Re-runs fully (cheap — fast model calls on drug names only). Treatment table uses `INSERT OR IGNORE`.
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

```
██████╗ ██╗ ██████╗     ██████╗ ██╗   ██╗███╗   ██╗██╗  ██╗
██╔══██╗██║██╔═══██╗    ██╔══██╗██║   ██║████╗  ██║██║ ██╔╝
██████╔╝██║██║   ██║    ██████╔╝██║   ██║██╔██╗ ██║█████╔╝
██╔══██╗██║██║   ██║    ██╔═══╝ ██║   ██║██║╚██╗██║██╔═██╗
██████╔╝██║╚██████╔╝    ██║     ╚██████╔╝██║ ╚████║██║  ██╗
╚═════╝ ╚═╝ ╚═════╝     ╚═╝      ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝
```
