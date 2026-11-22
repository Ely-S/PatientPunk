# Track D results (corpus: reddit_2026-06-13.db)

## Item 2: crash delay (delay.py)
The scan found 6,125 texts (posts and comments) matching a crash/PEM/flare word near delay wording.
| delay bin | texts |
|---|---|
| next day / day after / following day / tomorrow | 3,500 |
| a range (24-72 h, 1-3 days ...) | 855 |
| 2 days / 48 hours | 691 |
| a few hours/days | 364 |
| 1 day / 24 hours | 254 |
| same day (<24 h) | 251 |
| 3 days / 72 hours | 191 |
| 4+ days | 156 |
Of 52 contexts drawn from the first 400 retained matches in each bin, 40 described a trigger-to-crash delay.
In the next-day bin it was 23/28, and in the two-day bin 2/6. Numeric matches sometimes referred to the
duration of worsening. See the [next-version diary comparison](../../next_version/README.md#handling-the-delay-after-activity)
for how to test the observation window.

## Item 3: instrument names (FTS, posts + comments)
FUNCAP 364 · Bell scale 273 · Chalder 197 · SF-36 89 · DePaul 79 · PROMIS 27

## Item 6: repeat % self-ratings (longit.py, strict pattern, 5,919 ratings / 3,099 authors)
For the 764 same-author pairs 0.5–14 days apart, r=0.63 and 51% were identical. Median absolute change was 0
(10 among non-identical pairs), the 90th percentile was 20, and the SD of signed change was 15.5 points.
For the 860 pairs 90 or more days apart, r=0.43.
55% of all ratings are ≥90.

The archived script's 30-point detectable-change estimate is withdrawn. It applies a measurement-error formula
to informal ratings without evidence that patients were stable. See the
[author-weighted summary](../../next_version/README.md#what-the-existing-data-can-tell-us).

## Item 5: coder agreement
Sonnet vs DeepSeek, 68 posts: kappa 0.61-0.84 (as on page).
Sonnet vs Sonnet, 40 posts of chunk 0: kappa 0.54-0.87; current_severity 0.54 (82% raw).
Chunk-2 recode, 20 posts: current_severity 0.57.
