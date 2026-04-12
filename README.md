# PatientPunk

Reddit, patient forums, and social media overflow with firsthand patient reports: symptoms, treatments tried, outcomes, comorbidities, demographics. This signal disappears into forum threads. PatientPunk is the infrastructure to aggregate it, normalize it, and make it queryable at scale.

Patient self-reports aren't soft evidence — they're the only source of ground truth for the lived experience of disease. No biomarker tells you whether someone can get out of bed. No clinical trial follows patients long enough to capture the years-long arc of ME/CFS or long COVID. Self-reported qualitative markers ("I crash after any exertion," "went from bedbound to functional on this protocol") are treated here as first-class fields — dimensions to slice and filter on, not noise to discard.

A researcher can ask:

> *"Do patients with ME/CFS, neuroinflammation, and brain fog report positive outcomes with LDN?"*

And get back:

> **64% positive · 20% negative · 16% no effect** *(312 reports)*

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                       INGESTION                         │
│  (modular — Reddit, Twitter/X, patient forums, etc.)    │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                    NORMALIZATION                         │
│  Posts stored in a normalized schema:                   │
│  User entity · Post entity · source metadata            │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                 AI TRANSFORMATION                        │
│  LLM-powered entity extraction · Symptom ontology       │
│  mapping (MeSH / SNOMED) · Outcome scoring              │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                     DATABASE                            │
│  User records · Post records ·                          │
│  LLM outputs stored as structured JSON                  │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                      OUTPUTS                            │
│  CSV exports · SQL queries · REST API · Research kits   │
└─────────────────────────────────────────────────────────┘
```

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

Builds a treatment outcome database in three stages:

1. **Extract** — Haiku identifies all drugs, supplements, and interventions per post. Drug mentions propagate to replies via the parent chain.
2. **Canonicalize** — Collapses synonyms ("low dose naltrexone", "LDN" → one entry). Populates the `treatment` table.
3. **Classify** — Haiku prefilters for personal experience; Sonnet classifies sentiment (`positive` / `negative` / `mixed` / `neutral`) and signal strength. Writes incrementally — safe to interrupt and resume.

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
