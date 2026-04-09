# Reddit Sample Data -- Notes

Source: Arctic Shift API. Scraped 2026-04-05. Subreddit: `r/covidlonghaulers`.

---

## subreddit_posts.json

100 posts with 1,100 total comments from the subreddit.

### Data quality issues
- `num_comments` is unreliable -- often says 0 when comments actually exist in the array
- `depth` is always 0 -- doesn't reflect actual nesting; trace `parent_id` chains to reconstruct reply threads
- `score` is mostly 1 -- data likely captured very soon after posting
- Duplicate posts exist -- same author posted the same question twice (e.g. `t3_1scp1om` and `t3_1scoxzu`)

### Community patterns
- Authors are anonymized via SHA-256 hash, no usernames stored
- OP participates heavily in comment threads -- identifiable by matching `author_hash` between post and comment
- ~1/3 of posts have no comments; max is 162
- Mean 11 comments/post, median 4 -- long tail distribution

### Flair distribution
| Flair | Count |
|---|---|
| Question | 31 |
| Symptom relief/advice | 25 |
| Symptoms | 16 |
| Article | 7 |
| Personal Story | 6 |
| Vent/Rant | 4 |
| Update | 3 |
| Mental Health/Support | 2 |
| Improvement | 2 |
| TRIGGER WARNING | 1 |
| Advocacy | 1 |
| Research | 1 |
| Recovery/Remission | 1 |

### Flair vs content correlation
Flairs are user-selected and inconsistent. The top 3 (Question, Symptom relief/advice, Symptoms) heavily overlap in content -- most are people describing symptoms and asking for help regardless of flair. Smaller flairs like Article, Vent/Rant, and Recovery are more distinct. If categorizing posts, classify from text content rather than trusting flairs.

---

## corpus_metadata.json

Single metadata object summarizing the scrape. Key stats: 87 unique authors, 10,788 total user posts collected, 70,573 total user comments collected, 3,545 subreddits seen across all user histories. 4 authors were deleted/suspended.

---

## users/ (87 files)

One JSON file per unique author, named by their `author_hash`. Contains their full Reddit history -- not just long COVID activity.

### What's in each file
- `author_hash`, `scraped_at`
- `account_created_utc`, `total_karma` -- both null (not available from Arctic Shift)
- `posts[]` -- every post they've made across all subreddits (`post_id`, `subreddit`, `title`, `body`, `created_utc`, `score`, `num_comments`)
- `comments[]` -- every comment they've made across all subreddits (`comment_id`, `subreddit`, `body`, `created_utc`, `score`, `parent_id`)

### Key takeaways
- Full Reddit history, not just long COVID -- posts and comments across all subreddits they've ever participated in
- Longitudinal -- spans years, so you can see pre-illness life, onset, and progression
- No metadata beyond activity -- account age and karma are null; just posts and comments
- Cross-posting is common -- same content posted to multiple health subs (covidlonghaulers, vaccinelonghauler, LongCovid, POTS, etc.)
- Comments lack thread context -- you get `parent_id` but not the parent's content, so you can't fully reconstruct conversations without joining back to the source
- Volume varies widely per user -- one user had 37 posts and 158 comments; others may have thousands or just a handful

### Total activity per user (posts + comments)

| Bucket | Users |
|---|---|
| 1-10 | 11 |
| 11-50 | 14 |
| 51-100 | 4 |
| 101-500 | 23 |
| 501-1000 | 8 |
| 1000+ | 27 |

Min: 1 | Max: 13,118 | Median: 324 | Mean: 935

### Where users are active (subreddit categories)

| Stat | Value |
|---|---|
| Subreddits per user | min 1, max 333, median 33 |
| COVID/CFS % of activity | median 29%, mean 39% |
| General health % of activity | median 2%, mean 9% |
| Other % of activity | median 60%, mean 52% |

Most users are not single-issue accounts -- the majority of their Reddit activity (median 60%) is outside health subs entirely. Notable neurodivergence overlap in this population (autisticadults, aspergirls, aspergers, autisticwithadhd, schizoid all in the top "other" subs). Category boundaries are fuzzy -- several high-volume "other" subs are arguably health-related (cptsd, tmj, pcos, floxies, longcovidwarriors, etc.).

### History span per user

| Bucket | Users |
|---|---|
| <1 year | 29 |
| 1-3 years | 21 |
| 3-5 years | 16 |
| 5-10 years | 18 |
| 10+ years | 3 |

Min: 0.0y | Max: 12.6y | Median: 2.3y | Mean: 3.2y

Earliest post: 2013-08-14. About a third (29) have <1 year of history -- new accounts or recent lurkers. 21 users have 5+ years, providing rich longitudinal data with pre-illness baselines.

---

---

## Fixes and updates

### `num_comments` -- fixed 2026-04-05

The `num_comments` field from Arctic Shift is unreliable (frequently 0 even when comments exist in the response). `scrape_corpus.py` now writes two separate fields to each post record:

- `num_comments_api` -- the raw value from Arctic Shift, preserved for reference
- `comments_fetched` -- the actual count derived from `len(comments)` after fetching

**Use `comments_fetched` for any analysis involving comment counts.** Ignore `num_comments_api` or treat it as advisory only. Data scraped before this fix (including `reddit_sample_data/subreddit_posts.json`) only has the unreliable field.
