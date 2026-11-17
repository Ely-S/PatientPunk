# Track D results (corpus: reddit_2026-06-13.db)

## Item 2: crash delay (delay.py)
Texts (posts+comments) with a crash/PEM/flare word and a stated delay in the same sentence: 6,125.
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
Hand check of 52 random matches: 40/52 (77%) are real trigger-to-crash delay statements; next-day bin 23/28 (82%).
Numeric bins pick up durations ("crashed for a couple days after") more often (2-day bin 2/6 in sample).

## Item 3: instrument names (FTS, posts + comments)
FUNCAP 364 · Bell scale 273 · Chalder 197 · SF-36 89 · DePaul 79 · PROMIS 27

## Item 6: repeat % self-ratings (longit.py, strict pattern, 5,919 ratings / 3,099 authors)
Pairs 0.5-14 days apart, same author: n=764, r=0.63, 51% identical, median |change| 0 (10 among non-identical), 90th pct 20,
SD of change 15.5 → smallest detectable change ≈ 30 points. Pairs ≥90 days apart: n=860, r=0.43.
55% of all ratings are ≥90.

## Item 5: coder agreement
Sonnet vs DeepSeek, 68 posts: kappa 0.61-0.84 (as on page).
Sonnet vs Sonnet, 40 posts of chunk 0: kappa 0.54-0.87; current_severity 0.54 (82% raw).
Chunk-2 recode, 20 posts: current_severity 0.57.
