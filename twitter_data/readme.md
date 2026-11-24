Issues with Twitter in General
Harder to identify patients that have the diagnosis. Can aggregate all the user posts and infer, or look at author bios — but bio search isn't available on our API tier, so bios only arrive as a side-effect of pulling someone's posts. It's sparser and less accurate than posting in a specific patient community. On Reddit the subreddit guarantees it.
Small percentage of posts mentioning the drug are personal use reports. LDN: 32.4% personal use and 24.6% carrying an outcome on Twitter, against 66.0% and 56.2% on Reddit. 
Smaller communities, caveat that we could have scraped a bit better. Reddit LDN has 12,040 reports from 2,634 authors. Twitter has 1,088 from 555, and a complete re-pull is estimated at ~5,150 reports from ~1,000 authors (~5,790 if we also chase the authors who never pair the drug with the disease, but those are harder to reach). See below So Twitter is 11x smaller as scraped and still roughly half of Reddit at its realistic ceiling.
Bots and marketing activities occur on Twitter but not on Reddit. So far this is an ivermectin problem: 126 copypasta clusters covering 1,232 tweets (9.9%), 48 accounts repeating the same text 5+ times, and a 47-account vendor network. LDN by contrast is 19 clusters over 99 tweets (2.5%), all research-link shares and a charity's prescriber list — no sales network. Could become an issue with any marketed drug.
Discourse is more moved by the news cycle. LDN had exactly one event in the window, a Reuters feature on 18 Oct 2022: 3x volume on Twitter versus 1.4x on Reddit. It barely moved sentiment (69% positive that month vs 79–95% either side) but it moves volume. This is more pronounced with ivermectin.
Shorter user reports, though long posts exist on Twitter. LDN mean 274 chars vs Reddit's 563 (2.1x), but medians are 265 vs 314 (1.2x) — the typical post is the same length, Reddit just has a tail (p90 1,218 vs 307). 
Fewer personal use posts, caveated by the scrape not being done the best way. Every query was `<drug> + <long covid term>`, so only posts naming both were captured, and it read only the standard 280-character field — never the long-post body, no conversation ids, no parents. Re-pulling by author instead returns 4.8x as many posts, and 79% of them carry no disease term at all.
Twitter requests expensive. $0.005 per post read,  $0.10 per counts request. A full LDN sweep is 130 - 200. Not running it yet before discussing methods. The Reddit dumps we already hold, for free.



Estimates of the True LDN dataset size for patients with Long Covid.
Corpus: 1,853 authors, 3,979 posts naming LDN
Of those posts, 1,088 (27%) became a sentiment report, from 555 authors
Sampled 70 authors: they had 163 posts in the corpus, 781 on X → 4.8x
So total ≈ 4.8 × 3,979 = 19,000 posts, × 27% ≈ 5,150 reports
22 of the 70 authors had a personal-use post inside the corpus, 38 had one across all their X posts. So we can assume about 1.7x more authors with personal use, so roughly 1000 authors. 
(Unverified, do not cite: an earlier draft said about 11% of personal-use reports are not found, giving about 5,790 reports. The labels behind the 11% can't be reproduced; see 7.3. The 4.8x multiplier above also comes from 70 hand-picked authors, so neither figure supports a population-level estimate.)

By comparison, reddit has 12,040 directional reports from 2,634 authors.


How to do a better scrape (for Rohan)
Issues:

Long posts truncated. Only the 280-character preview was stored.
Long posts missed. Keyword matching ran on the preview. All real misses in the test weeks were long posts, about a quarter for ivermectin and an eighth for LDN.
 No author profiles. Bios and account data were not pulled.
 Too few synonyms. Brand names, abbreviations, misspellings, non-English forms.
Include more synonyms for long covid/ chronic fatigue. 
 Author's condition unverified. Every post names long covid and the classifier confirms own use of the drug, but neither shows the author has long covid. Acute "no long covid" stories, vaccine-injury accounts, parents and clinicians all pass.
Fixes: 

Request note_tweet; store its text when present.
Filter on the full body.
Add expansions=author_id with user fields.
Expand alias lists.
Add a condition label: bio regex for long covid, ME/CFS, POTS and similar terms; Later could use a second classifier label for the author's relation to the condition, with four values. This could be further expanded.
See section below for Proper author list.  
 
4. Proper author list instructions (Numbers estimated from LDN and the scrape from Long Covid Labs)
	
Find posts with drug + disease.
Look at those authors, get a list of their posts with that drug. 4-5x as many posts then.
This still misses authors who never mention drug + disease together. This is a more expensive scrape. Could aggregate from all drugs + that disease to get list of authors — most of the missing authors (77%) are already in the corpus (provided by Long Covid Labs) under a different drug, so this is cheap and recovers most of them.
Some bounds: sampled 799 X long covid authors. From them we found that 152 mentioned LDN. Found that 39.5% were not in the corpus that had an overlapping post. These on average had 4.2 posts per person as opposed to 18.2 in the other one. So 60 of the 152 LDN authors (39.5%) had no post in the corpus, and they wrote about 13% of the 152 authors' LDN posts. That is a statement about this sample, not a coverage rate for X. (An earlier draft added "~11% of personal-use posts"; that figure can't be reproduced, see 7.3.)
In the sentiment pipeline, could use demographics step + author bio to find diagnosis and further verify. 
Go over all authors with the OR list of drugs we care about.
People who mention long covid only in their bio, never in a post, are unreachable entirely. 

5. Where the data is

Source corpus (104 keyword files, 88 drugs, 87k tweets):
s3://patientpunk/twitter_analysis/source_corpus/twitter_dataset.zip

Twitter pipeline output — 1,088 LDN reports from 555 authors:
s3://patientpunk/twitter_analysis/databases/tweets.db

Reddit LDN — 12,040 reports from 2,634 authors (r/covidlonghaulers):
s3://patientpunk/twitter_analysis/databases/clh_ldn_twmatch.db

Personal-use / outcome rates (the 32.4% and 24.6% figures, plus Reddit's 66.0% and 56.2%):
s3://patientpunk/twitter_analysis/adhoc_results/ldn_results.json

November 2026 API pulls — the 4.8x multiplier, the reverse-route coverage test, bot and vendor pass, and all scripts:
s3://patientpunk/twitter_analysis/coverage_test_2026-11/
  run_ldn_authorpass_20261118T020357Z/    70 authors, 781 posts, gives the 4.8x
  run_reverse_route_20261118T030628Z/     first 450 patients
  run_reverse_resume_20261118T214743Z/    remaining 349 patients
  tier1/                                  copypasta and vendor-network counts
  reverse_route_combined.json             combined coverage figures
  METHOD_ldn_coverage.md                  the costed method


6. Data documentation

A local copy of everything in section 5 is in this folder, laid out the same way as on S3 (about 1.1 GB). The files hold patient posts, usernames and bios: keep them out of Git and off public storage.

| Local path | Size | Format | What it is |
|---|---|---|---|
| source_corpus/twitter_dataset.zip | 21 MB (113 MB unzipped) | zip of 104 JSON files | Raw keyword scrape, Nov 2025 |
| databases/tweets.db | 73 MB | SQLite | Twitter corpus + LDN and ivermectin sentiment reports |
| databases/clh_ldn_twmatch.db | 1,015 MB | SQLite | r/covidlonghaulers corpus + LDN sentiment reports |
| adhoc_results/ldn_results.json | 219 KB | JSON | Personal-use / sentiment labels for 2,273 LDN tweets |
| adhoc_results/reddit_ldn_results.json | 50 KB | JSON | The same labels for a 500-post Reddit LDN sample |
| coverage_test_2026-11/ | 10 MB, 393 files | JSON, CSV, MD, Python | Nov 2026 X API coverage, author-pass and bot tests |

Timestamps in both databases are Unix seconds (UTC). `user_id` in both databases is a 64-character hex hash, not the platform id, so it does not join to the raw `author_id` in the zip or the coverage files. For Twitter, join on `post_id` (= tweet id) or on `metadata.author_username` instead.

6.1 source_corpus/twitter_dataset.zip — raw scrape

- `treatment_wise_tweets/` holds 104 files named `tweets_<keyword>_<YYYYMMDD_HHMMSS>.json`, covering 89 distinct keyword names (88 drugs, plus `tweets_analysis.json`). Some keywords were scraped twice, e.g. ivermectin and paxlovid. Ignore the `__MACOSX/` entries.
- 131,358 records, which dedupe to 87,982 unique tweets from 32,805 authors, 2020-01-01 to 2025-11-12.
- Largest files: paxlovid (21,719 + 12,607), ivermectin (12,963 + 12,961), tweets_analysis (7,522), antiviral (6,244), vitamin_d (4,042), ldn (3,492), naltrexone (1,553). Smallest: the interferon-lambda variants, with 1–2 tweets each.
- Each file is an object: `total_tweets`, `keywords`, `keyword_frequency`, `total_metrics` (retweet/like/reply sums and averages), `verified_authors`, `verified_percentage` and `tweets[]`. `tweets_analysis.json` also has `treatment_statistics`.
- Fields on each tweet: `tweet_id, text, created_at (ISO), author_id, author_username, author_name, author_verified, keywords_found[], metrics{retweet_count, like_count, reply_count, quote_count}, lang, is_reply, is_treatment_related, score, reasoning, treatment_mentioned`.
- Caveats: `text` is the 280-character preview only (no `note_tweet` body). There are no conversation or parent ids, and `is_reply` is false on every record. `is_treatment_related` is true on 3,248 records; `score`, `reasoning` and `treatment_mentioned` are mostly empty.

6.2 databases/tweets.db — Twitter corpus and sentiment reports

The zip loaded into the PatientPunk schema (deduped to 87,041 posts), plus the treatment-sentiment pipeline output for two drugs.

| Table | Rows | Columns |
|---|---|---|
| posts | 87,041 | post_id, title, parent_id, user_id, body_text, flair, post_date, scraped_at, metadata (JSON) |
| users | 32,515 | user_id, source_subreddit (always `twitter`), scraped_at |
| treatment | 2 | id, canonical_name, treatment_class, aliases (JSON list), notes — 1 = `ldn` (29 aliases and misspellings), 2 = `ivermectin` |
| treatment_reports | 4,353 | report_id, run_id, post_id, user_id, drug_id, sentiment, signal_strength, side_effects (JSON list) |
| extraction_runs | 7 | run_id, run_at, commit_hash, extraction_type, config (JSON: models, drug, limit, reclassify…) |
| user_profiles, conditions, variables | 0 | Schema only, not populated |

posts:
- Date range 2020-01-01 to 2025-11-12. By year: 2020 4,265 · 2021 8,681 · 2022 23,941 · 2023 23,446 · 2024 18,430 · 2025 8,278.
- `title` and `flair` are always empty. `parent_id` is set on only 557 rows. `body_text` has a mean of 225 characters and a max of 987.
- `metadata` keys: `author_username, author_verified, lang, keywords_found, metrics{…}, source_file, backfilled` (445 rows backfilled).
- Languages: en 77,136 · de 4,590 · es 1,540 · nl 864 · ja 555 · other.
- 4,039 posts have an LDN/naltrexone keyword and 11,419 have ivermectin.

treatment_reports: use the right run, because earlier runs overlap.

| Drug | Runs | Use | Reports | Authors |
|---|---|---|---|---|
| LDN | 1–4, Sonnet 4.6 / Haiku 4.5, commit 6655bcf | run 4 only (full reclassify; supersedes run 3, which shares 1,054 posts) | 1,088 | 555 |
| Ivermectin | 5–7, commit 35fcbc2 | runs 6 + 7 together (no overlapping posts) | 2,188 | 1,187 |

- `sentiment` is one of positive / negative / mixed / neutral; `signal_strength` is one of strong / moderate / weak.
- LDN run 4: positive 844 (strong 473), negative 177, mixed 62, neutral 5. Side effects are listed on 130 reports.
- Ivermectin runs 6+7: positive 2,011, negative 148, mixed 23, neutral 6. Side effects are listed on 33 reports.
- LDN reports by year (run 4): 2020 1 · 2021 21 · 2022 229 · 2023 346 · 2024 301 · 2025 190.

6.3 databases/clh_ldn_twmatch.db — Reddit r/covidlonghaulers

The same schema as tweets.db. It holds the full subreddit, not just LDN posts.

| Table | Rows | Notes |
|---|---|---|
| posts | 1,854,693 | 101,529 submissions (`t3_` ids, have title, 97,650 have flair) + 1,753,164 comments (`t1_`, `parent_id` set). 2020-07-24 to 2025-11-12, mean 275 chars. `metadata` is empty. |
| users | 75,371 | source_subreddit = `covidlonghaulers` |
| treatment | 1 | `ldn`, same alias list as Twitter |
| treatment_reports | 12,217 | All from run 2 (commit 35fcbc2, skip_canonicalize); 2,668 authors |
| extraction_runs | 2 | |
| user_profiles, conditions, variables | 0 | Not populated |

- Posts by year: 2020 43,106 · 2021 219,782 · 2022 416,896 · 2023 415,306 · 2024 447,219 · 2025 312,384.
- Sentiment: positive 8,921 (strong 4,463) · negative 2,460 · mixed 659 · neutral 177. Side effects are listed on 2,260 reports.
- The 12,040 reports from 2,634 authors quoted above are the directional subset (neutral excluded).
- Reports by year: 2020 16 · 2021 192 · 2022 1,393 · 2023 2,619 · 2024 4,251 · 2025 3,746.

6.4 adhoc_results/ldn_results.json and reddit_ldn_results.json — personal-use labels

- A dict keyed by tweet id, with 2,273 entries. Each value is `{personal_use, sentiment, treatment}`.
- `personal_use`: none 1,537 · author 680 · secondhand 56.
- `sentiment`: unclear 1,714 · positive 362 · negative 104 · mixed 93.
- `treatment` is the free-text drug named; it is empty when personal_use is none, and 533 say "low dose naltrexone".
- This is the source of the 32.4% personal-use and 24.6% outcome rates in section 1.
- `reddit_ldn_results.json` has the same format: a dict of 500 Reddit post ids. `personal_use`: author 325 · secondhand 5 · none 170. 281 have an outcome. This gives the 66.0% / 56.2% Reddit rates. The other `reddit_*` and `*_sample` files in the S3 folder were not downloaded.

6.5 coverage_test_2026-11/ — Nov 2026 X API pulls

The X API v2 responses are kept raw: posts have `id, text, author_id, conversation_id, created_at, lang, public_metrics`, and some also have `note_tweet`, `in_reply_to_user_id` and `referenced_tweets`. Users have `id, username, name, description (bio), created_at, public_metrics, verified`. Unlike the corpus, these files include conversation ids, long-post bodies and bios.

Top level:
- `METHOD_ldn_coverage.md`: the costed four-step recovery method. Read this first.
- `reverse_route_combined.json`: the final reverse-route totals (799 patients screened, 152 posting about LDN, 60 missing from the corpus, posts missing/captured 255/1,675, own-use missing/captured 47/379).
- `tier2_author_list.json`: the 1,715 report authors (drugs, sentiments, report counts) and 300 non-report controls per drug.
- `ldn_counts_by_month_existing_query.json`: 65 rows of [month, count, count] for the original query, 2020-07 onward (the two counts are not labelled; see `step1_search.py`).
- `set_week_2025-09-01_{ldn,ivermectin}.json`: corpus tweets (20 / 25) for the test week, in the zip's record format.
- Scripts: `step1_search.py, week_test.py, probe.py, classify_personal_use.py, reverse_route_resume.py`.

| Folder | Files | Contents |
|---|---|---|
| run_20261113T220703Z | 5 + 13 count pages | First ivermectin test week: X counts and search results vs corpus, and a lookup of X-only posts (`lookup_xonly_conly.json`) |
| run_ldn_20261113T231941Z | 7 + 72 count files | LDN test week. `manifest.json` has the queries, daily counts, the X-vs-corpus diff (x_only, real misses, long-form) and cost. `counts_full_span/` holds daily counts over the full window. Also includes `users_probe.json` |
| run_ldn_counts_wide_20261117T233925Z | 67 | Daily counts 2020–2025 for a wider LDN query (`counts_wide.json`, 1,964 days) and `compare_by_month.json` (narrow vs wide, 65 months) |
| run_ldn_counts_synonyms_20261118T014148Z | 66 | The same daily counts for an expanded synonym query (`counts_synonyms.json`) |
| run_ldn_authorpass_20261118T020357Z | 19 | Source of the 4.8x multiplier. `authorpass_posts.json`: 781 LDN posts and the profiles of 70 authors. `sample_authors.json`: the 70 authors by stratum (30 positive, 15 negative, 5 mixed/neutral, 20 bio-only controls). `condition_tiers.json`: per-author long covid / ME/CFS evidence from bio and posts. Also includes `per_author.json` and `RESULT.md` |
| run_reverse_route_20261118T030628Z | 56 | Reverse route, first 450 patients. `sample_YYYY_MM.json` ×12 and `sample_posts.json`: 1,116 disease posts from 947 authors. `qualifying_authors.json`: 799 patients (bio, post_self, bio_lc). `ldn_posts.json`: 807 LDN posts. `personal_use_labels.json`: 575 labels. Also includes `RESULT.json`, `reverse_route.py` and the batch pages |
| run_reverse_resume_20261118T214743Z | 35 | The remaining 349 patients: `ldn_posts_resume.json` (1,146 posts, 79 users) and pages |
| run_tier2_ldn_20261117T001229Z | 15 | Profile lookups for 554 LDN report authors + 300 controls. `tier2_ldn_users.csv` (854 rows × 36 columns) holds account status, age, follower/following counts, bio flags and tier2_flags. `tier2_ldn_summary.md` summarises it. Also includes the raw `users_page_*.json`, request log and scripts |
| run_tier2_ivermectin_20261117T002057Z | 21 | The same for ivermectin: `tier2_ivermectin_users.csv` (1,487 rows × 36 columns) |
| tier1/ | 6 | Bot and coordination signals for all report authors + controls. `tier1_authors.csv` (2,313 rows × 41 columns) holds per-author flags such as copypasta, self_repeat, bursts, promotional, identical_longform and tier1_score. `tier1_groups.json` holds 675 copypasta clusters and the vendor-network accounts. `vendor_regex_hits.json` has 382 vendor-campaign hits. Summaries are in `tier1_summary.md` and `vendor_reconciliation.md`, and the code is `tier1_run.py` |


7. Review notes (2026-11-20)

I checked every figure in sections 1–5 against the local data. "Reproduced" means I got the same number from the files in this folder.

7.1 Figures that reproduce
- 32.4% / 24.6% Twitter (736 and 559 of 2,273 in `ldn_results.json`) and 66.0% / 56.2% Reddit (330 and 281 of 500 in `reddit_ldn_results.json`).
- 12,040 Reddit reports from 2,634 authors (directional, i.e. neutral excluded) and 1,088 Twitter reports from 555 authors (LDN run 4).
- Corpus size: a text match for naltrexone/LDN in the zip gives 3,984 posts from 1,856 authors, against the quoted 3,979 / 1,853.
- 1,088 / 3,979 = 27%. The 4.8x multiplier (781 / 163 posts) and the 79% untagged share match `RESULT.md`.
- Reverse route: 152 of 799 patients post about LDN, 60 are missing (39.5%), posts per author are 4.2 vs 18.2, and 255 of 1,930 posts are missing (13.2%).
- Long-post misses for LDN: in the test week, 3 of 23 X-visible posts were missing from the corpus, and all 3 were long posts (13%, "an eighth").
- Reuters spike on Twitter: corpus LDN posts were 248 in Oct 2022 against a Jul–Sep average of 77 (3.2x). 69% of that month's reports are positive.
- The arithmetic in the estimates section: 4.8 × 3,979 × 0.27 ≈ 5,157, and 5,150 / 0.89 ≈ 5,790.

7.2 Figures that differ slightly
- Post length (section 1): for the 1,088 Twitter report posts I get mean 249 / median 270 / p90 307. The readme says 274 / 265 / 307. For Reddit I get mean 564 (title + body; 560 body only) / median 312 / p90 1,209, against 563 / 314 / 1,218. The conclusion still holds: the typical post is about the same length, and Reddit has a long tail.
- Reuters spike on Reddit: by a crude text match, LDN-mentioning posts were 346 in Oct 2022 against a Jul–Sep average of 209 (1.65x), and reports were 182 vs 115 (1.6x). The readme says 1.4x. Its baseline is not stated. The Twitter figure rests on only 36 reports that month. The positive share in neighbouring months is 77–94%, not 79–95%.
- Copypasta (section 1): the figures can't be derived from `tier1/`. Those clusters need ≥2 distinct authors and number 675 across the whole corpus. The readme's numbers are close to this definition: identical normalised text, at least 3 tweets, any authors, drug named in the text. That gives ivermectin 135 clusters / 1,242 tweets / 9.6% of 12,899, and LDN 22 / 104 / 2.6% of 3,984 (readme: 126 / 1,232 / 9.9% and 19 / 99 / 2.5%). The "48 accounts repeating the same text 5+ times" figure did not reproduce; I get 27 on the ivermectin keyword subset. The script behind these numbers should be saved next to them.

7.3 Figures I could not verify, and inconsistencies
- The ~11% personal-use loss (and so the 5,790 estimate) can't be reproduced. It comes from `own_missing` 47 / `own_captured` 379 in `reverse_route_combined.json`. But `personal_use_labels.json` holds only 575 labels for 1,930 posts, and every label is "unknown". The labelling script (`classify_personal_use.py`) calls an LLM (DeepSeek v4.1 Flash via OpenRouter), while `METHOD_ldn_coverage.md` says personal use was a regex. Re-run the labelling, save the labels, and say which method produced the 11%.
- "22 of 70 authors had a personal-use post in the corpus, 38 across X" (the 1.7x and ~1,000 authors) is not in any saved file. `per_author.json` only holds [stratum, username, X posts, corpus posts]. It also looks inconsistent: 50 of the 70 sampled authors are sentiment-report authors, so more than 22 should have a personal-use post in the corpus, unless a stricter definition such as the regex was used.
- The ivermectin long-post miss rate ("about a quarter") has no manifest like the LDN one, so I didn't check it.
- The full LDN sweep is "$130–200" in section 1 but "$120–130" for steps 1–2 in `METHOD_ldn_coverage.md`. Settle on one figure, with what it covers.
- Section 5 said `ldn_results.json` also holds the Reddit 66.0% / 56.2% rates. It holds only tweets; the Reddit rates are in `reddit_ldn_results.json` (see 6.4; section 5 is left unedited).

7.4 Caveats on interpreting the numbers
- Two different classifiers give two "rates". The 32.4% / 24.6% come from an ad-hoc classifier run on a sample, not from the sentiment pipeline: only 528 of the 2,273 labelled tweets are among the 1,088 run-4 reports. The 27% report yield (1,088 / 3,979) comes from the pipeline. The two shouldn't be mixed in one calculation.
- Small and unequal samples: the Reddit rates rest on 500 posts (±~4 points at 95%), and the Twitter rates on 2,273.
- 32.4% and 66.0% include secondhand use. Counting only the author's own use, the rates are 29.9% (Twitter) and 65.0% (Reddit).
- The reports aren't counted the same way: the Twitter 1,088 includes 5 neutral reports, while the Reddit 12,040 is directional only. Like for like, it is 1,083 / 554 vs 12,040 / 2,634, or 1,088 / 555 vs 12,217 / 2,668. Either way the ratio is still about 11x.
- The 4.8x sample isn't random. It is 50 report authors (stratified by sentiment) plus 20 bio-only controls, not a random draw from the 1,853 corpus authors, two thirds of whom have only one post. Applying 4.8x to all 3,979 posts, and the 27% yield to untagged posts, are both assumptions that haven't been tested.
- Two different 5,150s: the estimate of ~5,150 *reports* is a coincidence with METHOD's step 1 figure of 5,150 *posts* (drug + disease on X). They are unrelated.
- Vendor network: per `tier1/vendor_reconciliation.md`, the "47-account vendor network" is 47 accounts matching a vendor regex (382 tweets). Only 10 use the "referred me to …" template. About 22 of them wrote first-person sales testimonials that the classifier counted as 102 positive ivermectin reports. Those should be excluded before quoting ivermectin sentiment, since they are ~5% of its 2,011 positive reports. "Not on Reddit" was not tested; no bot pass was run on the Reddit data.
- Author condition: of the 70 author-pass authors (`condition_tiers.json`), 30 confirmed long covid, 2 probable, 14 bio-only, 8 ME/CFS without long covid, and 16 made no statement. This supports the "author's condition unverified" point.
- Database use: in `tweets.db`, use LDN run 4 only (run 3 is an earlier pass over the same posts) and ivermectin runs 6 + 7 together. `user_id` is hashed, so it doesn't join to the X API `author_id` values in `coverage_test_2026-11/`.
- Reproducibility: the coverage scripts hard-code paths under `~/s3_runs/` and `~/PatientPunk/.env`, so they need path changes before they can be re-run from this folder.
