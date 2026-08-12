# NATURAL reddit source adapter — run on our pre-built corpus (no Pushshift)

**Problem this solves:** the reddit `download_and_clean` stage fetches archive dumps from the-eye
(Pushshift mirror), which is **down** — so `RedditDownloadAndClean` can't produce a corpus. This adapter
skips the fetch and points NATURAL's *own* contextualizer at a **pre-built Parquet corpus we already
scraped, cleaned, and partitioned** into the exact layout `contextualize.py` expects.

Everything downstream (`condition_filter`, `curate`, the Experiment estimators) is unchanged — only the
first stage is swapped.

## The corpus

- **Where:** `s3://patientpunk/trial_superset/natural_corpus_parquet/` (~458 MB)
- **What:** r/covidlonghaulers + r/LongCovid + r/LongHaulersRecovery, **full history 2020-07 → 2026-06**
  (~6 years), **posts + comments** (147,333 submissions, 2,304,485 comments; 0% null on the key fields).
- **Layout** (already in NATURAL's contextualize input shape):
  ```
  natural_corpus_parquet/
    content_type=submissions/bucket=covidlonghaulers/part-0.parquet   (id, created_utc, subreddit, title, selftext, author, score)
    content_type=submissions/bucket=LongCovid/…
    content_type=submissions/bucket=LongHaulersRecovery/…
    content_type=comments/bucket=covidlonghaulers/part-0.parquet      (id, link_id, created_utc, subreddit, body, author, score)
    content_type=comments/bucket=LongCovid/…
    content_type=comments/bucket=LongHaulersRecovery/…
  ```

## Run it (3 steps)

**1. Pull the corpus to a local dir** (you have S3 access):
```bash
aws s3 sync s3://patientpunk/trial_superset/natural_corpus_parquet/ ./natural_corpus_parquet
```

**2. Drop `reddit_prebuilt_parquet.py` into your repo** (anywhere importable, e.g.
`naturalv2/sources/reddit/stages/`).

**3. Wire it into a reddit source config in place of the download stage:**
```yaml
sources:
  reddit:
    stages:
      # was: RedditDownloadAndClean  — replace with:
      fetch:
        _target_: naturalv2.sources.reddit.stages.reddit_prebuilt_parquet.RedditPrebuiltParquet
        parquet_dir: /abs/path/to/natural_corpus_parquet   # from step 1
      condition_filter:      # unchanged
        _target_: naturalv2.sources.reddit.stages.condition_filter.RedditConditionFilter
        # …your existing args…
      curate:                # unchanged
        _target_: naturalv2.sources.reddit.stages.curate.RedditCurate
        # …your existing args…
```
Then run the source exactly as before (same `experiment_name`, same `save_dir`). The adapter calls
`build_contextualized_dataset(source_dir=parquet_dir, dest_dir=<save_dir>/reddit/final)` and hands off
`state.payload` / `persist_dataset(...{source}_cleaned)` identically to `RedditDownloadAndClean`, so
`condition_filter` → `curate` → the Experiment `source_paths` all resolve normally.

## Please confirm before trusting a run

Written against `naturalv2` main `7a2e006` (we re-pinned; `sources/core.py` and `contextualize.py` were
unchanged in her 2026-08-09 push, so this adapter's interface still holds). **Could not run end-to-end
here** — polars is blocked by Smart App Control on the dev box, so schema and partition layout are
verified against `contextualize.py` but the live pipeline is not. Three things to check on your side:

1. **`StageState` import path** — ✓ verified against main `7a2e006`: `SourceStage`, `CurationContext`,
   and `StageState` all import cleanly from `naturalv2.sources.core`, no change needed. (We could not
   exercise `build_contextualized_dataset` itself here — its import chain pulls the Unix-only `resource`
   module, so it only runs on Linux/Mac, not this Windows box — but the layout is verified statically.)
2. **condition→subreddit map.** `condition_filter` reads the map from
   `context.study_dataset.sources[source_name]` (defaults to `{}`) and otherwise **discovers subreddits
   via a live Reddit API search** — it does *not* read the `available_subreddits` the adapter sets on
   `state`. To pin it to our three buckets and skip the live discovery call, seed that entry before the
   run, keyed by your long-COVID condition string:
   `study_dataset.sources["reddit"] = {"<condition>": ["covidlonghaulers", "LongCovid", "LongHaulersRecovery"]}`.
3. **Date filtering.** If you set `filter_by_date`, the corpus spans 2020-07 → 2026-06 — make sure your
   per-trial `result_public_date` cutoffs fall inside that window (they do for the core-5).

If anything trips, send me the stack trace — the fix is almost certainly one of those three, not the
contextualize call itself.
