# PatientPunk

## The Problem

Reddit, patient forums, and social media are overflowing with firsthand patient reports: symptoms, treatments tried, outcomes, comorbidities, demographics. This data is qualitative, unstructured, and largely invisible to researchers. Patients who have tried dozens of treatments and documented their journeys in detail have no way to contribute that knowledge to science at scale.

Traditional clinical research has a structural blind spot: it relies on data it chooses to collect, from populations it chooses to study, on timelines measured in years and decades. Meanwhile, millions of patients are running informal experiments every day — trying treatments, tracking responses, reporting outcomes in plain language — and that signal disappears into forum threads.

## Patient Reports Are Data

The medical establishment has long treated patient self-reports as soft evidence — anecdote, noise, the kind of thing that gets filtered out before analysis begins. This is a mistake.

Patient reports are the only source of ground truth for the lived experience of disease. No biomarker tells you whether someone can get out of bed. No lab value captures treatment-induced cognitive impairment. No clinical trial follows patients long enough to capture the years-long arc of a complex chronic illness. For conditions like ME/CFS, long COVID, POTS, and other poorly understood diseases, patient testimony is not a weak signal — it is often the *only* signal.

The problem is not the quality of patient data. The problem is that we have never had the infrastructure to aggregate it, normalize it, and make it queryable at scale. PatientPunk is that infrastructure.

## Why Qualitative Markers Matter

Clinical research segments patients by diagnosis codes and lab values. But patients know things about themselves that never make it into their charts: how their symptoms cluster, how severity fluctuates, which comorbidities they believe are connected, what functional limitations look like day-to-day. These self-reported qualitative markers — "I crash after any exertion," "my symptoms are worse in the morning," "I went from bedbound to functional on this protocol" — contain signal that structured clinical data cannot capture.

Segmenting by these markers is not a compromise. It is a research strategy.

A patient who reports post-exertional malaise alongside brain fog and fatigue is a different cohort than one who reports the same diagnosis without PEM. A patient who self-identifies as a "slow responder" to LDN may have biology distinct from someone who saw results in the first week. These distinctions are invisible to standard ICD-10-based analysis. They are only visible if you take patient language seriously and build systems that can query it.

PatientPunk treats self-reported qualitative markers as first-class fields — not as noise to be discarded, but as dimensions to slice and filter on. This is what makes patient-driven science possible.

## What PatientPunk Does

PatientPunk ingests patient-generated content from social media, normalizes it into structured records, and exposes it as queryable datasets for researchers and patient-driven scientists.

A patient or researcher can ask:

> *"Do other patients with ME/CFS, severe neuroinflammation, and brain fog report positive outcomes with LDN treatment?"*

And get back:

> **64% positive outcome · 20% negative outcome · 16% no effect**
> *(based on 312 patient reports)*

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

- **Modular ingestion** — swap in new data sources (Reddit, forums, health apps) without changing downstream logic
- **Symptom normalization** — maps patient language ("brain fog", "crushing fatigue") to standard medical ontologies
- **Treatment outcome tracking** — classifies reported outcomes as positive, negative, neutral, or mixed
- **Analysis engine with sanity checks** — statistical routines surface small-sample, sparse-table, censoring, convergence, and missing-data issues as structured warnings for downstream interpretation
- **Cohort queries** — filter by condition profile, demographics, comorbidities, and treatment history
- **Privacy-first** — no PII stored; usernames hashed; posts anonymized before storage
- **Researcher-ready exports** — CSV, SQL dumps, and structured JSON for direct analysis

---

## Analysis Layer

The query-side analysis code lives in `app/analysis/stats.py`. It works on user-level aggregates and currently supports:

- two-group comparisons
- one-sample binomial checks
- logistic and OLS regression
- Kruskal-Wallis multi-group comparisons
- monthly trend analysis
- Cox proportional hazards survival analysis

The analysis layer is intentionally warning-oriented. Most suspicious-but-usable situations do not raise exceptions. Instead they are attached to the returned result as `warnings` so the UI or downstream LLM can interpret them in context.

Examples of situations that now emit warnings:

- small or highly imbalanced sample sizes
- sparse categorical tables
- dropped rows from missing predictors
- unstable or non-converged regression fits
- flat outcomes with no variation
- short or gappy trend series
- heavy censoring or low event rates in survival analysis

Hard failures are reserved for invalid inputs or genuinely unusable outputs, such as impossible parameter values.

### Analysis test suite

The focused regression and stress-test suite for the analysis engine is:

```bash
pytest tests/test_stats.py -q
```

This suite intentionally covers mixed timestamp storage, repeated profile runs, sparse regressions, heavy censoring, and warning propagation behavior.

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

The schema is organized into three layers:

- **Layer 1 — Raw:** `users`, `posts` — scraped social media content
- **Layer 2 — Configuration:** `treatment`, `extraction_runs` — lookup tables and run metadata
- **Layer 3 — Extracted:** `user_profiles`, `conditions`, `treatment_reports` — LLM-extracted structured data

**[View interactive schema diagram](schema_diagram_v5.html)** · **[schema.sql](schema.sql)**

---

## Ethical Commitments

- Data is used strictly for scientific and patient-benefit purposes
- No re-identification of individuals
- Opt-out mechanisms respected (deleted posts are purged)
- Transparent about data provenance in all exports

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

# Copy env template and add your API key
cp Scrapers/demographic_extraction/.env.example .env
# Edit .env and set ANTHROPIC_API_KEY=<your key>
```

To run any pipeline command, prefix it with `uv run`:

```bash
uv run python Scrapers/scrape_corpus.py --help
```

### Running tests

```bash
uv run pytest -v
```

---

## Running the Pipeline

### Step 1 -- Scrape

```bash
# Quick test (80 posts, no comments or user histories)
python Scrapers/scrape_corpus.py --weeks 2 --limit-posts 80

# Full scrape (2 months of posts + comments + user histories)
python Scrapers/scrape_corpus.py --months 2 --comments --user-histories
# Outputs: data/subreddit_posts.json  +  data/users/*.json
```

### Step 2a -- Variable extraction *(who are the patients?)*

Extracts 36+ demographic and clinical fields per record using regex + LLM backfill.

```bash
# Default: regex extraction + LLM gap-fill (Phases 1-2-4-5)
python variable_extraction/main.py run \
    --schema variable_extraction/schemas/covidlonghaulers_schema.json

# With field discovery (finds new variables in the data)
python variable_extraction/main.py run \
    --schema variable_extraction/schemas/covidlonghaulers_schema.json \
    --discover auto

# Regex only (no API key needed)
python variable_extraction/main.py run \
    --schema variable_extraction/schemas/covidlonghaulers_schema.json \
    --no-llm
# Outputs: data/records.csv  +  data/codebook.csv
```

### Step 2b -- Demographics *(age, sex, location)*

Dedicated LLM pass for demographic fields (deductive + inductive coding).

```bash
python variable_extraction/main.py demographics --input-dir data --mode both
# Outputs: data/demographics_deductive.csv  +  data/demographics_inductive.json
```

### Step 2c -- Drug sentiment *(what do they say about treatments?)*

```bash
cd database_creation
python extract_mentions.py --output-dir ../data/drug_pipeline
python canonicalize.py --output-dir ../data/drug_pipeline
python classify_sentiment.py --output-dir ../data/drug_pipeline
# Output: data/drug_pipeline/sentiment_cache.json
```

Steps 2a-2c are independent -- run them in any order. All tag records with
`author_hash` (SHA-256 of username) as the join key.

See [`variable_extraction/README.md`](variable_extraction/README.md) for full
CLI reference and library API.

### Step 3 -- Combine into unified database

```bash
python load_db.py
# Joins both pipelines into patientpunk.db via author_hash
# Outputs: patientpunk.db + data/combined_treatment_outcomes.csv
```

### Latest run (316 records: 220 posts + 96 user histories)

| Metric | Value |
|---|---|
| Treatment reports | 1,316 |
| Unique drugs | 430 |
| Sentiment | 70% positive, 21% negative, 9% mixed |
| Demographics | age 30%, sex 46%, location 57% |
| Conditions | 88 unique, 78% coverage |
| Overall field fill rate | 47.2% |

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
