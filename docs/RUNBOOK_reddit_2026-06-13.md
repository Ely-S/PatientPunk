# Running the pipeline on `reddit_2026-06-13.db`

> **Needs branch `feat/db-corpus`** ([#110](https://github.com/Ely-S/PatientPunk/pull/110),
> stacked on [#109](https://github.com/Ely-S/PatientPunk/pull/109)). Neither has merged,
> so `main` has neither the converter nor the `subreddits` column. Step 1 checks it out.

A step-by-step for this specific dataset. For the commands in general see
[`variable_extraction/README.md`](../variable_extraction/README.md); for what the
output means and what to distrust, [`METHODS.md`](../variable_extraction/METHODS.md).

## What the dataset is

```
s3://patientpunk/raw_data/pushshift/reddit_2026-06-13.db      2.45 GB
```

SQLite, two flat tables (`posts`, `comments`) joined on `comments.link_id`.
Fifteen subreddits, 243,289 posts and 3,602,691 comments in total. r/covidlonghaulers
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
| longcovid_research | 71 | 275 |
| MECFS | 28 | 29 |
| me_cfs | 20 | 5 |
| cfs_DE | 5 | 7 |

`mecfs` and `MECFS` are separate rows because the names differ only in case. They
are the same community; anything grouping by subreddit will treat them as two
unless it lowercases first.

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

**Name every run.** Each run gets its own output directory, and the notes for it
live inside that directory. Never write into `output/` — it is a shared name, it
may already hold another run's `records.csv`, and on at least one machine
`output/subreddit_posts.json` was a **symlink to another corpus**, so writing
there would have destroyed it. `db_to_corpus.py` now refuses to overwrite an
existing corpus for that reason; pass `--force` only when you mean it.

Copy the whole block. Everything except the final command is safe to paste and
run as-is; the real run is left commented out so it does not start before you
have looked at the ten-record test.

```bash
# ---------------------------------------------------------------- 1 · setup
# db_to_corpus.py and the subreddits column are not on main yet -- they are
# PRs #110 and #109. Until those merge, work from this branch.
git fetch origin && git checkout feat/db-corpus

uv sync                                              # from the repo root

# Name this run. Everything below writes under it, so runs never collide.
RUN=output_reddit2026
REPO=$(pwd)

# Which model will actually answer? Two .env files are read and
# variable_extraction/.env is merged SECOND, so it overrides the repo root --
# and it is gitignored, so it will not show up in git status. Check both before
# you spend anything; the run banner and llm_provenance.json also print it.
cp .env.example .env       # template carries OPENROUTER_API_KEY
grep -sE '^(LLM_PROVIDER|LLM_BASE_URL|MODEL_FAST|MODEL_STRONG)=' \
     .env variable_extraction/.env

aws s3 cp s3://patientpunk/raw_data/pushshift/reddit_2026-06-13.db .

# Start the run log now. Append to it at every step -- see the RUN_NOTES.md
# section below for what belongs in each heading.
mkdir -p "$RUN"
cat >> "$RUN/RUN_NOTES.md" <<NOTES
# Run notes — $RUN

- Operator:
- Started: $(date -u +%Y-%m-%dT%H:%MZ)
- Commit: $(git rev-parse --short HEAD) on $(git rev-parse --abbrev-ref HEAD)
- Database: reddit_2026-06-13.db
- Window:
- Model that actually answered:

## Commands, in order

## Results per step

## Deviations from the runbook, and why

## Errors and warnings

## Data quality

## Conclusion — learnings, insights, takeaways
NOTES

# ------------------------------------------------------------- 2 · convert
# See what is in the database before converting any of it.
python Scrapers/db_to_corpus.py --db reddit_2026-06-13.db --list

# Every subreddit, hashing usernames on the way -- raw handles are in the
# database and must not reach records.csv.
#   --subreddit NAME [NAME ...]   restrict to some, for a single-community run
#   --since / --until YYYY-MM-DD  filter posts AND comments by their own
#                                 timestamp. A comment whose parent post falls
#                                 outside the window is DROPPED -- there is
#                                 nothing to nest it under. The tool reports how
#                                 many; widen the window to keep them.
# Start with a window. The whole database is 243,289 posts and 3.6M comments,
# which converts to a 2 GB JSON -- and aggregate (next step) reads the corpus
# whole into memory, so the full pull needs a machine sized for it. A month is
# ~24 MB and runs in seconds; scale up once the shape looks right.
python Scrapers/db_to_corpus.py --db reddit_2026-06-13.db \
    --since 2026-05-01 --out-dir "$RUN"

# Confirm no raw handle got through, in posts AND in comments. Both print 0.
python - "$RUN/subreddit_posts.json" <<'EOF'
import json, re, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
bad = lambda h: h is not None and not re.fullmatch(r"[0-9a-f]{64}", h)
print("unhashed post authors   ", sum(bad(p["author_hash"]) for p in d))
print("unhashed comment authors", sum(bad(c["author_hash"]) for p in d for c in p["comments"]))
EOF

# ----------------------------------------------------------- 3 · aggregate
# One record per patient rather than per post -- the only way a comment-only
# patient is captured at all, since extraction reads title+body.
# main.py resolves a relative --input-dir differently depending on the
# subcommand, so pass absolute paths and the question does not arise.
cd variable_extraction
python main.py aggregate --input-dir "$REPO/$RUN" \
    --out-dir "$REPO/${RUN}_perpatient" --min-items 3

# ---------------------------------------------------------------- 4 · test
# Ten records first. Responses are cached under cache/ at the repo root (on by
# default), so these ten are not billed again in the real run.
python main.py run --schema schemas/covidlonghaulers_schema.json \
    --input-dir "$REPO/${RUN}_perpatient" --limit 10

# Now open $REPO/${RUN}_perpatient/records.csv and check it looks sane.

# ------------------------------------------------------------ 5 · real run
# BATCH_SIZE = 1, so this is one LLM call per patient. Multiply what the ten
# cost. --workers well above 10 is fine and cuts wall time substantially.
#
# Uncomment when the test above looks right:
#
# python main.py run --schema schemas/covidlonghaulers_schema.json \
#     --input-dir "$REPO/${RUN}_perpatient" --workers 250
```

Interrupted runs resume with `--resume`, which also leaves `temp/` alone.
Already-extracted records come from the cache and cost nothing.

## `$RUN/RUN_NOTES.md`

Every run keeps its own log, inside its own output directory, written **as you go**
rather than reconstructed afterwards. The test is whether someone who was not
there could reproduce the run from the file alone.
[Issue #112](https://github.com/Ely-S/PatientPunk/issues/112) is the worked example.

**Append-only.** Do not tidy it up or rewrite earlier entries. A command that
failed and what you did next is the most useful thing in the file — it is the part
the next person would otherwise repeat. Coming back to a run on another day and
re-running step 1 appends a second header, with its own timestamp and commit;
that is the intent, not a duplicate.

Step 1 seeds it with the headings below. Fill each as you reach it:

| Section | What goes in it |
|---|---|
| **Header** | Operator, date, branch and commit, database, window, and the model **that actually answered** — read it off the run banner or `llm_provenance.json`, not from what you intended. See the `.env` note in step 1. |
| **Commands, in order** | Every command verbatim, including the failures. Paste them; do not retype. |
| **Results per step** | The numbers each step printed — post and comment counts, orphans dropped, patients out, records extracted, wall time. These are what a re-run gets checked against. |
| **Deviations** | Anything you did differently from this runbook, and why. Output directory, worker count, an added flag, a step skipped. |
| **Errors and warnings** | Every one, with its count and kind. Failures that were retried, failures that stayed failed, anything printed that you did not expect. |
| **Data quality** | Fill rates, empty-field rates, anything that looked off. Plus the two checks below. |
| **Conclusion** | Learnings, insights, takeaways. What surprised you, what you would do differently, what the next person should know before starting. |

Two checks to run and record every time:

- **Privacy.** The check in step 2 printed 0 for posts **and** comments. If either
  is non-zero, stop — a raw handle is in the corpus.
- **`text_count` is not a volume measure.** It reads `1` for every aggregated
  patient, because it counts input documents and aggregation makes one document
  per patient. The real figure is `n_items` in the per-patient corpus, and it is
  **not** carried into `records.csv`.

### Going wider than a month

Drop `--since` to take everything. Two things scale badly and are worth knowing
before you do:

| Window | Posts | Corpus JSON |
|---|---:|---:|
| 10 days | 1,271 | 9 MB |
| 1 month | 4,996 | 24 MB |
| Full, 2020-07 → 2026-06 | 243,289 | **2,006 MB** |

`db_to_corpus.py` handles the full database fine — it streams from SQLite and the
conversion takes a couple of minutes. **`aggregate` is the constraint:** it reads the
corpus with a single `json.loads` over the whole file, so a 2 GB corpus becomes many
gigabytes of Python objects. On a laptop that thrashes rather than finishes.

Until that is fixed, go wide by converting in windows — a year at a time, say — and
running each separately, or run it somewhere with the memory to hold the whole
corpus at once.

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
