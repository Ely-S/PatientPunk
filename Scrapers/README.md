# PatientPunk Scrapers

Reddit corpus scraper for the PatientPunk project. Fetches posts, comment
trees, and author histories from r/covidlonghaulers using the
[Arctic Shift](https://arctic-shift.photon-reddit.com) public API — **no
Reddit API key required**.

---

## Quick Start

```bash
pip install -r requirements.txt
python scrape_corpus.py --weeks 2 --comments
```

Output goes to `output/` at the project root. Then run the extraction pipeline:

```bash
cd ..
python Scrapers/demographic_extraction/run_pipeline.py \
    --schema Scrapers/demographic_extraction/schemas/covidlonghaulers_schema.json
```

---

## scrape_corpus.py

Fetches posts, comment trees, and author histories from r/covidlonghaulers
within a configurable time window.

### Usage

```bash
python scrape_corpus.py                                   # posts only, last 2 months (default)
python scrape_corpus.py --weeks 1 --comments              # 1-week sample with comments
python scrape_corpus.py --months 3 --comments             # 3 months of posts + comments
python scrape_corpus.py --months 3 --comments \
    --user-histories                                      # + author histories (~4-6 hrs)
python scrape_corpus.py --months 3 --comments \
    --user-histories --enrich-profiles                    # everything (run overnight)

python scrape_corpus.py --help                            # full inline help
```

### Flags

| Flag | Description |
|---|---|
| `--months N` | Scrape posts from the last N months (default: 2) |
| `--weeks N` | Scrape posts from the last N weeks (mutually exclusive with `--months`) |
| `--comments` | Fetch full comment trees for every post |
| `--user-histories` | Scrape each post author's full Reddit history across all subreddits |
| `--enrich-profiles` | Fetch Reddit profile data per author: avatar, bio, karma, account age. Requires `--user-histories` |

See `SCRAPER_HELP.md` for time estimates and full documentation.

### Output

```
output/          # project root
  subreddit_posts.json      # All posts in window (+ comments if --comments)
  users/
    {sha256_hash}.json      # One file per unique post author (--user-histories only)
  corpus_metadata.json      # Run summary and stats
```

User files are written **incrementally** — if the script crashes mid-run, completed user files are preserved.

---

## Data Source

All scripts use [Arctic Shift](https://arctic-shift.photon-reddit.com), a free public archive of Reddit data.

- No API key or developer registration needed
- No 1,000-item cap per user (unlike Reddit's official API)
- Profile metadata (avatar, bio, karma) requires a separate Reddit call via `--enrich-profiles`
- Data freshness: typically hours to days behind live Reddit

## Privacy

All usernames are SHA-256 hashed before being written to any output file. Raw usernames exist only in memory during the scrape.

The `output/` directory and `.env` are gitignored by default.
