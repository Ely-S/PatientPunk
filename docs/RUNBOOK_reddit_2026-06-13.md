# Running the pipeline on `reddit_2026-06-13.db`

A step-by-step for this specific dataset. For the commands in general see
[`variable_extraction/README.md`](../variable_extraction/README.md); for what the
output means and what to distrust, [`METHODS.md`](../variable_extraction/METHODS.md).

## What the dataset is

```
s3://patientpunk/raw_data/pushshift/reddit_2026-06-13.db      2.45 GB
```

SQLite, two flat tables (`posts`, `comments`) joined on `comments.link_id`.
Eleven subreddits, 243,289 posts and 3,602,691 comments in total. r/covidlonghaulers
runs **2020-07-24 → 2026-06-11** — the subreddit's first day to the scrape date, so
it is the complete history rather than a window.

| Subreddit | Posts | Comments |
|---|---:|---:|
| covidlonghaulers | 118,675 | 1,951,500 |
| cfs | 87,220 | 1,211,709 |
| LongCovid | 26,615 | 316,798 |
| mecfs | 2,923 | 25,859 |
| Longcovidgutdysbiosis | 2,431 | 36,826 |
| LongHaulersRecovery | 2,079 | 36,954 |
| cfsme | 1,263 | 5,345 |
| LongCovid_MECFS_DE | 712 | 7,289 |
| cfsrecovery | 669 | 7,652 |
| CFSScience | 488 | 2,197 |
| CovidLongHaulersUK | 90 | 246 |

It is **not** in the format the pipeline reads. That is step 2.

## Two decisions to make before spending anything

**Which subreddits.** `db_to_corpus.py` takes one per run, on purpose. Aggregation
merges patients across whatever is in the corpus file, and after that a patient who
posted in both covidlonghaulers and cfs is one record you cannot split — the
synthetic `agg_<hash>` id has no post to join back to. Converting per subreddit
keeps that choice open. (PR #109 adds a `subreddits` count column so a merged record
at least says how mixed it is.)

**Posts-only or aggregated.** Extraction reads each post's title and body only, so a
patient who only ever commented is invisible without `aggregate`. On a one-month
slice of this data:

| | Patients out |
|---|---|
| posts only | 1,322 records, commenters dropped |
| `aggregate --min-items 1` | 3,398 |
| `aggregate --min-items 3` | 1,605 |
| `aggregate --min-items 5` | 1,069 |

Aggregation is also the cheaper unit — one call per patient instead of one per post —
and it matches what `cluster-prep` does anyway.

## 1 · Setup

```bash
uv sync                                   # from the repo root
cp .env.example .env                      # then add ANTHROPIC_API_KEY or OPENROUTER_API_KEY
aws s3 cp s3://patientpunk/raw_data/pushshift/reddit_2026-06-13.db .
```

## 2 · Convert the slice you want

```bash
python Scrapers/db_to_corpus.py --db reddit_2026-06-13.db --list

python Scrapers/db_to_corpus.py \
  --db reddit_2026-06-13.db \
  --subreddit covidlonghaulers \
  --out-dir output
```

Writes `output/subreddit_posts.json`, hashing every username on the way — raw
handles are in the database and must not reach `records.csv`.

`--since` / `--until` take `YYYY-MM-DD` and filter posts *and* comments by their own
timestamp, so a narrow window leaves comments whose parent post falls outside it.
The script reports them as orphan comments; they only become patients via `aggregate`.

## 3 · Aggregate

```bash
cd variable_extraction
python main.py aggregate --input-dir ../output --out-dir ../output_perpatient --min-items 3
```

Skip this only if you deliberately want post-level records and are willing to lose
every comment-only patient.

## 4 · Test on ten records first

```bash
python main.py run --schema schemas/covidlonghaulers_schema.json \
  --input-dir ../output_perpatient --limit 10
```

Check `../output_perpatient/records.csv` looks sane before the real run. Responses
are cached under `cache/` at the repo root, on by default, so these ten are not
re-billed later.

## 5 · The real run

```bash
python main.py run --schema schemas/covidlonghaulers_schema.json \
  --input-dir ../output_perpatient --workers 10
```

**Scale, so it is not a surprise.** `BATCH_SIZE = 1`, so this is one LLM call per
record. Posts-only on the full covidlonghaulers corpus is 118,675 calls; aggregated
at `--min-items 3` it projects to roughly 144,000 patients from the one-month yield.
The README's "~$0.10–0.50" is for a 220-post corpus and does not apply here — do the
`--limit 10` run first and multiply.

Interrupted runs resume with `--resume`. The cache means a re-run over already-seen
records costs nothing.

## 6 · What you get

Durable, in the output directory:

| File | What |
|---|---|
| `records.csv` | One row per patient, values pipe-joined |
| `codebook.csv` | Field list with source and confidence tier |
| `llm_provenance.json` | Provider, model, temperature, schema_id |
| `subreddit_posts.json` | The corpus itself — keep it |

`output/temp/` holds the raw and normalized JSON records and is **wiped at the start
of the next full run of any schema**. Copy it aside if a run matters.

## Reading the output

Three things that will otherwise mislead you, all measured on 300 posts of this
corpus:

- **55% of records have no condition recorded.** Not extraction failure — in a
  long-COVID subreddit nobody writes "I have long COVID", so there is nothing to
  extract. Of those that do, 116 name long COVID, 8 name ME/CFS, 2 name both. You
  cannot separate cohorts on `conditions`.
- **Symptom-domain placement is only partly deterministic.** A three-rule table
  routes symptoms that are multi-domain by definition, covering 4.7% of mentions;
  the rest is model judgement at unmeasured consistency. `output/routing_*.json`
  records what the table moved.
- **`infection_count` is wrong on roughly six of nine `1`s** and is flagged as a drop
  candidate. Do not use it as a reinfection measure.

`METHODS.md` has the rest, including the group-attribution guard
(`PP_GROUP_GUARD=1`), which is **off by default** and worth enabling for anything
reporting per-drug `helped` rates.
