# Contributing to PatientPunk — Scrapers

This document covers scraper internals and the privacy model.
For the extraction pipeline, schema system, and developer guide see
[`variable_extraction/README.md`](../variable_extraction/README.md).

---

## Scraper Internals (`scrape_corpus.py`)

Key functions:

| Function | Purpose |
|---|---|
| `window_start_iso(months, weeks)` | Returns `(iso_timestamp, label)` for the time window. Uses `strftime("%Y-%m-%dT%H:%M:%SZ")` — Arctic Shift requires `Z` suffix, no microseconds |
| `count_posts_in_window(subreddit, after)` | Lightweight post count before the full scrape |
| `fetch_full_post(post_id)` | Fetches a single post via `/api/posts/ids` |
| `fetch_comments_for_post(post_id)` | Paginated comment fetch via `/api/comments/search` |
| `scrape_user_history(username, enrich)` | Full cross-subreddit history for one author |
| `fetch_reddit_profile(username)` | Unauthenticated Reddit `about.json` call for profile metadata |

**Deduplication:** posts are deduplicated within a run using a `seen_post_keys` set of `(author.lower(), title.strip().lower())` tuples.

**Retry logic:** all API calls use exponential backoff on 5xx responses and rate-limit headers.

**Arctic Shift quirks:**
- Timestamp format must be `YYYY-MM-DDTHH:MM:SSZ` — `+00:00` suffix causes 400 errors
- The `fields` parameter is not supported — always request full objects
- No authentication needed; no per-user rate limits documented

---

## Privacy Model

- Usernames are SHA-256 hashed with `hashlib.sha256(username.encode()).hexdigest()` immediately on receipt
- Raw usernames exist **only in memory** during a scrape and are never written to any file
- The `data/` directory is gitignored — never commit scraped data
- `.env` (if used) is gitignored

Do not add any feature that writes a raw username, email, or other PII to disk.
