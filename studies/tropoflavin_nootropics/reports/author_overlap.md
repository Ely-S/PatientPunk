# Cross-subreddit author overlap

This is a diagnostic for possible double counting. The cohorts remain separate and no denominators are pooled. Deleted or unidentifiable authors are excluded. An overlap count means the same deterministic author hash had at least one retained comparator report in both subreddits. Multiple accounts owned by one person cannot be detected, so measured overlap is a lower bound on possible double counting.

Hash algorithm verified across cohorts: `sha256-128-raw-reddit-username-v1`.

## Overlap counts

| Subreddit | Nootropics | Supplements | Peptides | NootropicsDepot | NooTopics | depressionregimens | StackAdvice | Longevity | Psilocybin |
|---|---|---|---|---|---|---|---|---|---|
| Nootropics | 8669 | 411 | 545 | 341 | 393 | 106 | 788 | 2 | 5 |
| Supplements | 411 | 2527 | 73 | 98 | 69 | 12 | 137 | 0 | 2 |
| Peptides | 545 | 73 | 7369 | 71 | 170 | 16 | 144 | 1 | 0 |
| NootropicsDepot | 341 | 98 | 71 | 1046 | 83 | 11 | 127 | 0 | 0 |
| NooTopics | 393 | 69 | 170 | 83 | 1648 | 23 | 71 | 0 | 0 |
| depressionregimens | 106 | 12 | 16 | 11 | 23 | 223 | 45 | 0 | 0 |
| StackAdvice | 788 | 137 | 144 | 127 | 71 | 45 | 1925 | 0 | 1 |
| Longevity | 2 | 0 | 1 | 0 | 0 | 0 | 0 | 5 | 0 |
| Psilocybin | 5 | 2 | 0 | 0 | 0 | 0 | 1 | 0 | 63 |

## Source verification

| Subreddit | Authors | Database | SHA-256 |
|---|---|---|---|
| Nootropics | 8669 | comparators.db | ac321297811718cf1be0e0393d91e5b3a49f9bdbe92217115fb31dee927b595a |
| Supplements | 2527 | sentiment.db | b2d6ca3e8b14444918798c2ce2769b5627689ebcbe73fefeb3b87c9add8558b3 |
| Peptides | 7369 | sentiment.db | 4e239ef5971c8f08389bd30ec26321ac118443406a01e3c3933b16564a2e180b |
| NootropicsDepot | 1046 | sentiment.db | ad41435c6415187f15ff703b3534aa93aa70f21cbca5abd5a623ce07ae6ec476 |
| NooTopics | 1648 | sentiment.db | bfd47703240b1bf3afa2e3fe32e01a03ed03a73be041e91d51676ebb4dbf6406 |
| depressionregimens | 223 | sentiment.db | 0e9e3563ca9dcacb835ec22202b15c30e696340ff49dc65cc4c18c04eaa9670c |
| StackAdvice | 1925 | sentiment.db | 5c0bf29b8515012b1cc96c6d545b2c31d26b5fae01f13e9706e522d112bda8a2 |
| Longevity | 5 | sentiment.db | 94b8b2eaa92de97e1e462371caeaefffbb1395d0f57e4717492177b5f328234c |
| Psilocybin | 63 | sentiment.db | b558b4474607bcad390584c8613d55184f6a88af6b2ed0e8639475f835abcb29 |
