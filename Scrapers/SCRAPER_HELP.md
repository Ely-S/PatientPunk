# scrape_corpus.py — Help & Reference

Scrapes posts, comments, and author data from r/covidlonghaulers via the
[Arctic Shift](https://arctic-shift.photon-reddit.com) public API.
No Reddit API key or developer registration required.

---

## Quick Start

```bash
pip install requests
python scrape_corpus.py
```

Default run: fetches all posts from the last **2 months**, no comments, no histories.

---

## Flags

### Time window
Exactly one of these may be passed. If neither is passed, defaults to `--months 2`.

| Flag | Description |
|---|---|
| `--months N` | Scrape posts from the last N months |
| `--weeks N` | Scrape posts from the last N weeks |

`--months` and `--weeks` are mutually exclusive — passing both is an error.

---

### What to collect

These flags are independent and can be combined freely.

| Flag | What it adds | Extra time (est.) |
|---|---|---|
| `--comments` | Full comment trees for every post | +15–30 min (3-month window) |
| `--user-histories` | Full post+comment history for each unique post author, across all subreddits | +2–4 hrs |
| `--enrich-profiles` | Reddit profile data per author: avatar, bio, karma, account creation date | +~7s per user (~10 min for 80 users) |

> `--enrich-profiles` requires `--user-histories`. Passing `--enrich-profiles` alone is an error.

---

## Example Commands

```bash
# Posts only, last 2 months (default)
python scrape_corpus.py

# Posts only, last 3 months
python scrape_corpus.py --months 3

# Posts only, last 6 weeks
python scrape_corpus.py --weeks 6

# Posts + comments, last 2 months
python scrape_corpus.py --comments

# Posts + comments, last 1 week (quick sample)
python scrape_corpus.py --weeks 1 --comments

# Full corpus: posts + comments + author histories
python scrape_corpus.py --months 3 --comments --user-histories

# Everything: posts + comments + histories + Reddit profiles (overnight run)
python scrape_corpus.py --months 3 --comments --user-histories --enrich-profiles
```

---

## Run Phases

Every run goes through the same phases — flags control what happens in each.

| Phase | What happens | Always runs? |
|---|---|---|
| **Phase 0** | Counts posts in the time window before downloading | Yes |
| **Phase 1** | Downloads full post metadata. Fetches comment trees if `--comments` | Yes |
| **Phase 2** | Scrapes author histories. Fetches Reddit profiles if `--enrich-profiles` | Only with `--user-histories` |
| **Phase 3** | Writes `corpus_metadata.json` | Yes |

---

## Output Files

All output is written to `data/` at the project root.

```
data/
  subreddit_posts.json      # All posts in the time window (+ comments if --comments)
  users/
    {sha256_hash}.json      # One file per unique post author (only with --user-histories)
  corpus_metadata.json      # Summary stats for the run
```

### subreddit_posts.json
Array of post objects. Each contains: `post_id`, `title`, `body`, `author_hash`,
`created_utc`, `score`, `num_comments`, `url`, `flair`, and `comments` (empty array
unless `--comments` was passed).

### users/{hash}.json
One file per unique post author. Contains:
- `author_hash` — SHA-256 of the username
- `profile` — Reddit profile data (`null` unless `--enrich-profiles` was used)
- `posts` — all posts by this author across all subreddits
- `comments` — all comments by this author across all subreddits
- `scraped_at` — timestamp of when this file was written

User files are written **incrementally** as each author is scraped. If the script
crashes mid-run, all previously written user files are preserved.

### corpus_metadata.json
Run summary including: post count, unique authors, success/failure counts,
all subreddits seen across author histories, start/end timestamps, and which
flags were active.

---

## Privacy

All usernames are **SHA-256 hashed** before being written anywhere. Raw usernames
exist only in memory during the scrape and are never written to disk.

To verify no raw usernames leaked into output:
```bash
# Spot-check a known username
grep -r "actual_username" ../data/   # should return nothing
```

---

## Rate Limits & Timing

| Source | Delay | Enforced by |
|---|---|---|
| Arctic Shift API | 1 second between requests | `polite_sleep()` in script |
| Reddit about.json (profiles) | 7 seconds between requests | `REDDIT_REQUEST_DELAY` constant |

Arctic Shift is a free community resource with no uptime guarantees. If requests
fail, the script retries with exponential backoff (1s, 2s, 4s, 8s, 16s) before
giving up on that item.

### Rough time estimates (3-month window, ~500 posts, ~400 authors)

| Command | Estimated time |
|---|---|
| Posts only | ~30–45 min |
| + `--comments` | ~1–2 hrs |
| + `--user-histories` | +2–4 hrs |
| + `--enrich-profiles` | +~1 hr |
| Full run (everything) | **4–7 hrs** — run overnight |

---

## Extraction Pipeline

After scraping, run the full extraction pipeline with a single command:

```bash
python variable_extraction/main.py run \
    --schema variable_extraction/schemas/covidlonghaulers_schema.json
```

This runs all five phases in sequence:

| Phase | Script | What it does |
|---|---|---|
| 1 | `extract_biomedical.py` | Regex extraction — free, seconds |
| 2 | `llm_extract.py` | LLM gap-filling (Claude Haiku) |
| 3 | `discover_fields.py` | Auto-discovers new fields, builds regex, fills gaps |
| 4 | `records_to_csv.py` | Flattens all records to a flat CSV |
| 5 | `make_codebook.py` | Generates a data dictionary / codebook |

Outputs: `data/records.csv` and `data/codebook.csv`.

```bash
# Free run (regex only, no API key needed):
python variable_extraction/main.py run \
    --schema variable_extraction/schemas/covidlonghaulers_schema.json \
    --no-llm --no-discover

# Resume after a crash at phase 3:
python variable_extraction/main.py run \
    --schema variable_extraction/schemas/covidlonghaulers_schema.json \
    --start-at 3
```

See `README.md` for the full pipeline documentation and all flags.
