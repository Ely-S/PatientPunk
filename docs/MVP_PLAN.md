# PatientPunk MVP Plan
## Static Drug Intervention Database — r/covidlonghaulers
################################################################################ 
##This is 90% Claude generated and I need to think about this a bit more for myself:  please both humans and LLMs, do not take it as gospel -SG
################################################################################ 

---


## Use Cases

A sick patient wants to understand:
1. What proportion of people with their condition report benefit from a given drug
2. The same, filtered by demographic similarity (age, sex, location)
3. *(Expanded)* The same, filtered by symptom history and time

The patient is not making LLM calls. They are querying a static, pre-built database that we maintain and update periodically.

---

## Architecture

```
Reddit corpus
    ↓
scrape_corpus.py
    ↓
subreddit_posts.json + users/*.json
    ↓                              ↓
Polina's pipeline              Shaun's pipeline
(drug sentiment)               (demographics)
    ↓                              ↓
sentiment_cache.json           records.csv
    ↓                              ↓
              ETL loader
                  ↓
            data.db (SQLite)
                  ↓
            query interface
```

The two pipelines run independently on the same corpus and are joined in the database on `author_hash`.

---

## Step 1 — Drug Sentiment Database
**Status: Partially complete — blocked on `scripts/` folder**

### What it produces
One record per `(user, drug)` pair with sentiment and signal strength.

### Pipeline

**1a. Drug mention tagging** — `database_creation/extract_mentions.py`
- Scans every post and comment
- Haiku tags every drug/supplement/intervention mentioned
- Tracks ancestor context for short replies
- Status: ✅ Done

**1b. Canonicalization** — `database_creation/canonicalize.py`
- Collapses synonym drug names to a canonical form
- Current issues: missed cross-batch synonyms, non-drug entities leaking in, category terms mixed with specific drugs
- Needs: rebuild using regex-first approach with expected drug list, Haiku backfill, Sonnet pattern generation for new terms
- Status: ⚠️ Works but needs quality improvements before full run

**1c. Sentiment classification** — `database_creation/classify_sentiment.py`
- Two-stage: Haiku prefilter → Sonnet classification
- Per-drug system prompts for calibrated classification
- Produces: `sentiment` (positive/negative/mixed/neutral) + `signal_strength` (strong/moderate/weak)
- Status: ❌ Blocked — requires `scripts/utilities.py` and `scripts/intervention_config.py` which are missing from repo

**1d. ETL to SQLite** — not yet written
- Load `users` and `posts` from scraped corpus
- Load canonical drug names into `treatment` table with aliases
- Convert sentiment strings to numeric values
- Load `treatment_reports`
- Status: ❌ Not written

### Remaining work
- [ ] Recover or reconstruct `scripts/` folder from Polina
- [ ] Rebuild `canonicalize.py` with regex-first approach
- [ ] Run `classify_sentiment.py` on full corpus
- [ ] Write ETL loader → SQLite
- [ ] Define sentiment → numeric mapping (e.g. positive=1.0, negative=-1.0, mixed=0.0, neutral=null)

---

## Step 2 — User Demographic Database
**Status: Pipeline built, not run on this corpus**

### What it produces
One record per user with age, sex, location — joined to treatment reports by `author_hash`.

### Pipeline

**2a. Variable extraction** — `python variable_extraction/main.py run`
- Full pipeline: regex extraction → Haiku gap-fill → LLM field discovery
- Extracts demographics, conditions, medications, treatment outcomes, and more
- Schema: `variable_extraction/schemas/covidlonghaulers_schema.json`
- Status: ⚠️ Still needs to be debugged a bit.

**2b. ETL to SQLite** — not yet written
- Load `user_profiles` (age_bucket, sex, location) from `records.csv`
- Join to `users` table on `author_hash`
- Status: ❌ Not written

### Remaining work
- [ ] Run demographic pipeline on `reddit_sample_data` corpus
- [ ] Write ETL to load `user_profiles` into SQLite
- [ ] Verify join quality on `author_hash`

---

## Step 3 — Query Interface
**Status: Not started**

A simple interface for a patient to query the database. No LLM calls at query time — pure SQL against the static database.

### Queries to support

**Basic (Step 1):**
```
What % of people report benefit from LDN?
→ positive: 68%, negative: 18%, mixed: 14%  (n=45)
```

**Demographic filter (Step 2):**
```
What % of women aged 30-50 report benefit from LDN?
→ positive: 71%, negative: 15%, mixed: 14%  (n=28)
```

**Multi-drug comparison:**
```
For people with long COVID, rank all drugs by % positive
→ LDN: 68% (n=45), ketotifen: 72% (n=31), ...
```

### Interface options

**Option A — CLI script** (simplest, MVP)
- User runs `python query.py --drug "ldn" --sex female --age 30-50`
- Prints results to terminal
- No dependencies beyond SQLite

**Option B — Simple web UI** (one step up)
- Local Flask/FastAPI app
- Drug name input + optional demographic filters
- Returns formatted results in browser
- Still no LLM calls, pure DB queries

Recommendation: build CLI first, web UI second. Both query the same database — the interface is thin on top of SQL.

### Remaining work
- [ ] Write `query.py` CLI — drug lookup, optional demographic filters, output formatting
- [ ] Define "close enough" for demographic matching (exact match vs. buckets)
- [ ] *(Optional)* Wrap in minimal local/executable UI

---

## Expanded MVP — Symptom and Condition Matching
**Status: Not started — Step 3 of original plan**

Extends the user database to include illness and symptom history with timestamps and severity. Allows a patient to specify their condition profile and get treatment outcomes matched to similar patients.

Requires:
- Conditions/symptoms extracted from full demographic pipeline (already in schema)
- `conditions` table populated in SQLite
- Similarity matching logic (exact condition name match as v1; embedding similarity later)
- Extended query interface

This is explicitly post-MVP. The condition extraction is built into the demographic pipeline — it just needs to be loaded into the database and exposed via the query interface.

---

## Database

SQLite. Schema defined in `schema.sql`. Point at a new database with `--db data.db` for a clean start.

Key tables: `users`, `posts`, `treatment`, `treatment_reports`, `user_profiles`, `conditions`, `extraction_runs`

---

## Critical Path to Step 1 MVP

1. Get `scripts/` folder from Polina → unblocks sentiment classification
2. Fix canonicalization → clean drug names before full classification run
3. Run `classify_sentiment.py` on full corpus
4. Write ETL loader → populate SQLite
5. Write `query.py` CLI

## Critical Path to Step 2 MVP

1. Run demographic pipeline on `reddit_sample_data`
2. Write ETL for `user_profiles`
3. Extend `query.py` with demographic filters

Steps 1 and 2 can run in parallel once the `scripts/` folder is recovered.

---

## Open Questions

- **Canonicalization standard**: should canonical drug names map to RxNorm CUIs for the drugs that have them? Supplements and off-label treatments would stay as strings. Improves long-term interoperability.
- **Sentiment numeric mapping**: what float values for positive/negative/mixed? Or keep as categorical and convert at query time?
- **Demographic matching**: exact match on sex + age bucket, or allow partial matches with a count caveat?
- **Update cadence**: how often do we re-run the full pipeline on a fresh scrape?
