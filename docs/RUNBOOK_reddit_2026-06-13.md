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

> **The database holds raw Reddit usernames** — `posts.author` and `comments.author`
> are plain handles, 133,675 distinct ones, attached to posts about people's medical
> conditions. Everywhere else in this project a patient is a SHA-256 `author_hash`.
>
> **The pipeline path is safe.** `db_to_corpus.py` hashes every author on the way out
> and has no flag to disable it, so nothing downstream of step 2 ever sees a handle.
>
> **Analysis that reads the database directly is not.** A notebook, an ad-hoc query, a
> join for a sanity check — any of those can put real usernames into a chart, a CSV, or
> a figure that gets shared. Hash on the way in, the same way the converter does:
> `hashlib.sha256(name.encode()).hexdigest()`.

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

## Steps 1–5 · Setup to run

Copy the whole block. Everything except the final command is safe to paste and run
as-is; the real run is left commented out so it does not start before you have
looked at the ten-record test.

```bash
# ---------------------------------------------------------------- 1 · setup
uv sync                                              # from the repo root
cp .env.example .env                                 # then edit: add ANTHROPIC_API_KEY
                                                     # (or OPENROUTER_API_KEY)
aws s3 cp s3://patientpunk/raw_data/pushshift/reddit_2026-06-13.db .

# ------------------------------------------------------------- 2 · convert
# See what is in the database before converting any of it.
python Scrapers/db_to_corpus.py --db reddit_2026-06-13.db --list

# Every subreddit, hashing usernames on the way -- raw handles are in the
# database and must not reach records.csv. Writes output/subreddit_posts.json.
#   --subreddit NAME [NAME ...]   restrict to some, for a single-community run
#   --since / --until YYYY-MM-DD  filter posts AND comments by their own
#                                 timestamp, so a narrow window leaves comments
#                                 whose parent post falls outside it; those are
#                                 reported as orphans and still become patients
python Scrapers/db_to_corpus.py --db reddit_2026-06-13.db --out-dir output

# Confirm no raw handles got through -- every author_hash should be 64 hex
# characters, and this should print 0.
python -c "import json;d=json.load(open('output/subreddit_posts.json'));print(sum(1 for p in d if p['author_hash'] and len(p['author_hash'])!=64))"

# ----------------------------------------------------------- 3 · aggregate
# One record per patient rather than per post. This is what turns 4,996 posts
# and 65,046 comments into 4,209 patients, and it is the only way a
# comment-only patient is captured at all -- extraction reads title+body.
cd variable_extraction
python main.py aggregate --input-dir ../output --out-dir ../output_perpatient --min-items 3

# ---------------------------------------------------------------- 4 · test
# Ten records first. Responses are cached under cache/ at the repo root (on by
# default), so these ten are not billed again in the real run.
python main.py run --schema schemas/covidlonghaulers_schema.json --input-dir ../output_perpatient --limit 10

# Now open ../output_perpatient/records.csv and check it looks sane.

# ------------------------------------------------------------ 5 · real run
# BATCH_SIZE = 1, so this is one LLM call per patient -- roughly 144,000 for
# the full corpus at --min-items 3. The README's "~$0.10-0.50" is for a
# 220-post corpus and does not transfer. Multiply what the ten cost.
#
# Uncomment when the test above looks right:
#
# python main.py run --schema schemas/covidlonghaulers_schema.json --input-dir ../output_perpatient --workers 10
```

Interrupted runs resume with `--resume`. The cache means re-running over
already-seen records costs nothing.

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
