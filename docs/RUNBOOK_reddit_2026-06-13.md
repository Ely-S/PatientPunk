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

## Run everything, aggregated

**All subreddits, in one corpus.** The unit is the patient, and a patient who posts
in r/cfs and r/covidlonghaulers is one person. Splitting the corpus by community
would fragment them into partial records. On a single month of this data **31.8% of
patients wrote in more than one community**:

| Communities | Patients |
|---|---:|
| 1 | 2,871 |
| 2 | 1,007 |
| 3 | 244 |
| 4 | 70 |
| 5+ | 17 |

Which communities each patient wrote in is kept on the record as `subreddits`
counts (`cfs:24 covidlonghaulers:11`), so nothing is lost by merging — you can still
select or stratify afterwards.

**Aggregated, not posts-only.** Extraction reads each post's title and body only, so
a patient who only ever commented is invisible without `aggregate`. Comments are
where most of the text is: that same month is 4,996 posts against 65,046 comments.
Aggregating is also cheaper — one LLM call per patient rather than per post — and it
is the unit `cluster-prep` uses anyway.

`--min-items` sets how much text a patient needs to qualify:

| | Patients out |
|---|---:|
| `--min-items 1` | 8,793 |
| `--min-items 3` | 4,209 |
| `--min-items 5` | 2,926 |

3 is a reasonable default: it drops one-line commenters who cannot support a profile
without discarding most of the corpus.

> **The exception.** Aggregation collapses time — a synthetic record has no
> `created_utc`, because it spans many posts. Drift work (how one patient's reports
> move over months) needs a separate posts-only run. That is not this run.

## 1 · Setup

```bash
uv sync                                   # from the repo root
cp .env.example .env                      # then add ANTHROPIC_API_KEY or OPENROUTER_API_KEY
aws s3 cp s3://patientpunk/raw_data/pushshift/reddit_2026-06-13.db .
```

## 2 · Convert to a corpus

```bash
python Scrapers/db_to_corpus.py --db reddit_2026-06-13.db --list   # what is in there

python Scrapers/db_to_corpus.py --db reddit_2026-06-13.db --out-dir output
```

Exports every subreddit by default. Writes `output/subreddit_posts.json`, hashing
every username on the way — raw handles are in the database and must not reach
`records.csv`.

`--subreddit NAME [NAME ...]` narrows it, for a deliberately single-community run.
`--since` / `--until` take `YYYY-MM-DD` and filter posts *and* comments by their own
timestamp, so a narrow window leaves comments whose parent post falls outside it.
Those are reported as orphan comments; they still become patients via `aggregate`.

## 3 · Aggregate

```bash
cd variable_extraction
python main.py aggregate --input-dir ../output --out-dir ../output_perpatient --min-items 3
```

This is the step that turns 4,996 posts and 65,046 comments into 4,209 patients.
Skip it only for the drift case noted above.

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
