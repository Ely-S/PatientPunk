# Clustering study

Do patients cluster by what they report, and does response to a treatment vary
with where a patient sits? The corpus is patient-authored Reddit text across
fifteen long-COVID and ME/CFS communities, extracted one record per patient.

**Status:** corpus and extraction procedure ready; no clustering run yet.

## Documents

| | |
|---|---|
| [`CORPUS_RUNBOOK.md`](./CORPUS_RUNBOOK.md) | How to build the corpus and run extraction on it, end to end, including what to distrust in the output |

## Where the data lives

```
s3://patientpunk/raw_data/pushshift/reddit_2026-06-13.db      2.45 GB
```

SQLite, 243,289 posts and 3,602,691 comments across fifteen subreddits.
r/covidlonghaulers runs 2020-07-24 → 2026-06-11 — the subreddit's first day to
the scrape date, so it is the complete history rather than a window.

Nothing derived from it is kept in git. Each run writes its own output directory
containing the corpus, `records.csv`, and a `RUN_NOTES.md` recording exactly how
that run was produced. See the runbook.

**The database holds raw Reddit usernames.** The pipeline hashes them on the way
in and no handle reaches any artifact, but analysis that queries the database
directly can put real usernames into a chart or CSV. The runbook says how to
avoid that.

## What the extraction can and cannot support

Measured, and worth knowing before designing an analysis on top:

- **Cohorts cannot be separated on `conditions`.** In a long-COVID community
  nobody writes "I have long COVID", so the field is empty for a large share of
  records — 55% on a 300-post sample, 35% on Eli's 4,193-record run. Not
  extraction failure; there is nothing in the text to extract.
- **Symptom-domain placement is only partly deterministic.** A three-rule table
  routes symptoms that are multi-domain by definition, covering 4.7% of mentions;
  the rest is model judgement at unmeasured consistency. `routing_*.json` records
  what the table moved.
- **`infection_count` is wrong on roughly six of nine `1`s** and is a drop
  candidate. Not usable as a reinfection measure.
- **A patient spans communities.** 31.8% of patients in a one-month window wrote
  in more than one; the `subreddits` column counts which. Aggregation merges them
  deliberately — one person is one patient wherever they wrote.

[`METHODS.md`](../../variable_extraction/METHODS.md) carries the rest, including
the group-attribution guard (`PP_GROUP_GUARD=1`, off by default) which is worth
enabling for anything reporting per-drug `helped` rates.
