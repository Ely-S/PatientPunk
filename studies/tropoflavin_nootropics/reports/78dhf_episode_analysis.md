# Same-post 7,8-DHF episode analysis

This analysis requires dose, route, reason, sentiment, and side-effect reporting to be attributable within the same Reddit post. Each globally unique author-post pair is an episode. Repeated episodes are retained and standard errors are clustered by author. A missing mapped side effect means not reported in that episode, not that no side effect occurred.

## Primary design

The primary exposure is log2 quantitative dose, so its odds ratio is the change associated with a dose doubling. Ordinal sentiment is coded negative < neutral/mixed < positive. The second outcome is any mapped same-report side-effect mention. Both use generalized estimating equations with author-clustered robust covariance and subreddit fixed effects. Subreddits with fewer than 5 dose-complete episodes are pooled as Other. The two primary p-values receive Benjamini-Hochberg correction.

## Coverage

| Cohort | Episodes | Authors | Explicit personal use | Single quantitative dose | Single route | Explicit reason | Mapped side effect reported |
|---|---|---|---|---|---|---|---|
| Nootropics | 632 | 278 | 304/632 (48.1%; 44.2% to 52.0%) | 59/632 (9.3%; 7.3% to 11.9%) | 61/632 (9.7%; 7.6% to 12.2%) | 55/632 (8.7%; 6.7% to 11.2%) | 165/632 (26.1%; 22.8% to 29.7%) |
| Supplements | 42 | 30 | 23/42 (54.8%; 39.9% to 68.8%) | 4/42 (9.5%; 3.8% to 22.1%) | 6/42 (14.3%; 6.7% to 27.8%) | 12/42 (28.6%; 17.2% to 43.6%) | 17/42 (40.5%; 27.0% to 55.5%) |
| Peptides | 5 | 4 | 4/5 (80.0%; 37.6% to 96.4%) | 0/5 (0.0%; 0.0% to 43.4%) | 0/5 (0.0%; 0.0% to 43.4%) | 2/5 (40.0%; 11.8% to 76.9%) | 1/5 (20.0%; 3.6% to 62.4%) |
| NootropicsDepot | 813 | 347 | 339/813 (41.7%; 38.4% to 45.1%) | 42/813 (5.2%; 3.8% to 6.9%) | 71/813 (8.7%; 7.0% to 10.9%) | 74/813 (9.1%; 7.3% to 11.3%) | 200/813 (24.6%; 21.8% to 27.7%) |
| NooTopics | 221 | 105 | 96/221 (43.4%; 37.1% to 50.0%) | 9/221 (4.1%; 2.2% to 7.6%) | 15/221 (6.8%; 4.2% to 10.9%) | 18/221 (8.1%; 5.2% to 12.5%) | 73/221 (33.0%; 27.2% to 39.5%) |
| depressionregimens | 15 | 8 | 11/15 (73.3%; 48.0% to 89.1%) | 0/15 (0.0%; 0.0% to 20.4%) | 2/15 (13.3%; 3.7% to 37.9%) | 0/15 (0.0%; 0.0% to 20.4%) | 1/15 (6.7%; 1.2% to 29.8%) |
| StackAdvice | 100 | 61 | 47/100 (47.0%; 37.5% to 56.7%) | 8/100 (8.0%; 4.1% to 15.0%) | 4/100 (4.0%; 1.6% to 9.8%) | 11/100 (11.0%; 6.3% to 18.6%) | 19/100 (19.0%; 12.5% to 27.8%) |
| Longevity | 0 | 0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| Psilocybin | 0 | 0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| Combined | 1828 | 673 | 824/1828 (45.1%; 42.8% to 47.4%) | 122/1828 (6.7%; 5.6% to 7.9%) | 159/1828 (8.7%; 7.5% to 10.1%) | 172/1828 (9.4%; 8.2% to 10.8%) | 476/1828 (26.0%; 24.1% to 28.1%) |

## Main finding

The primary model used 122 same-post, single-dose episodes from 81 authors; 22 authors contributed more than one dose-complete episode. Outcomes comprised 92 positive, 4 neutral/mixed, and 26 negative episodes; 37 had a mapped side-effect report. Neither primary outcome passed Benjamini-Hochberg correction at q < 0.05.

## Combined primary models

| Outcome | Episodes | Authors | OR per dose doubling | 95% CI | p | BH q | Status |
|---|---|---|---|---|---|---|---|
| ordinal sentiment | 122 | 81 | 0.92 | 0.66 to 1.28 | 0.6161 | 0.8820 | estimated |
| side-effect reporting | 122 | 81 | 1.03 | 0.72 to 1.47 | 0.8820 | 0.8820 | estimated |

## Binary sentiment sensitivity

| Outcome | Episodes | Authors | OR per dose doubling | 95% CI | p | BH q | Status |
|---|---|---|---|---|---|---|---|
| positive sentiment | 122 | 81 | 0.92 | 0.67 to 1.27 | 0.6096 | n/a | estimated |

This prespecified sensitivity collapses sentiment to positive versus negative/neutral/mixed. Its raw p-value is descriptive and is not part of the two-outcome primary correction.

## Combined dose descriptives

| Dose band | Episodes | Authors | Median dose | Positive sentiment | Mapped side effect reported |
|---|---|---|---|---|---|
| <5 mg | 3 | 2 | 2.0 mg | 2/3 (66.7%; 20.8% to 93.9%) | 1/3 (33.3%; 6.1% to 79.2%) |
| 5 to <10 mg | 1 | 1 | 8.0 mg | 1/1 (100.0%; 20.7% to 100.0%) | 1/1 (100.0%; 20.7% to 100.0%) |
| 10 to <25 mg | 28 | 24 | 20.0 mg | 21/28 (75.0%; 56.6% to 87.3%) | 7/28 (25.0%; 12.7% to 43.4%) |
| 25 to <50 mg | 54 | 41 | 25.0 mg | 43/54 (79.6%; 67.1% to 88.2%) | 16/54 (29.6%; 19.1% to 42.8%) |
| 50 to <100 mg | 25 | 16 | 50.0 mg | 15/25 (60.0%; 40.7% to 76.6%) | 11/25 (44.0%; 26.7% to 62.9%) |
| >=100 mg | 11 | 9 | 100.0 mg | 10/11 (90.9%; 62.3% to 98.4%) | 1/11 (9.1%; 1.6% to 37.7%) |

## Combined route descriptives

| Route | Episodes | Authors | Positive sentiment | Mapped side effect reported |
|---|---|---|---|---|
| nasal mucosal | 11 | 7 | 10/11 (90.9%; 62.3% to 98.4%) | 1/11 (9.1%; 1.6% to 37.7%) |
| oral mucosal | 123 | 73 | 95/123 (77.2%; 69.1% to 83.8%) | 32/123 (26.0%; 19.1% to 34.4%) |
| other explicit route | 1 | 1 | 1/1 (100.0%; 20.7% to 100.0%) | 0/1 (0.0%; 0.0% to 79.3%) |
| swallowed oral | 24 | 21 | 21/24 (87.5%; 69.0% to 95.7%) | 4/24 (16.7%; 6.7% to 35.9%) |

## Combined explicit-reason descriptives

| Reason | Episodes | Authors | Positive sentiment | Mapped side effect reported |
|---|---|---|---|---|
| anxiety or stress | 16 | 11 | 16/16 (100.0%; 80.6% to 100.0%) | 2/16 (12.5%; 3.5% to 36.0%) |
| cardiovascular or autonomic | 1 | 1 | 1/1 (100.0%; 20.7% to 100.0%) | 0/1 (0.0%; 0.0% to 79.3%) |
| cognition or brain fog | 16 | 14 | 15/16 (93.8%; 71.7% to 98.9%) | 4/16 (25.0%; 10.2% to 49.5%) |
| energy or motivation | 18 | 16 | 17/18 (94.4%; 74.2% to 99.0%) | 5/18 (27.8%; 12.5% to 50.9%) |
| focus or attention | 46 | 38 | 44/46 (95.7%; 85.5% to 98.8%) | 8/46 (17.4%; 9.1% to 30.7%) |
| memory or learning | 25 | 14 | 23/25 (92.0%; 75.0% to 97.8%) | 7/25 (28.0%; 14.3% to 47.6%) |
| mood or depression | 74 | 51 | 68/74 (91.9%; 83.4% to 96.2%) | 14/74 (18.9%; 11.6% to 29.3%) |
| neuroprotection or recovery | 11 | 9 | 11/11 (100.0%; 74.1% to 100.0%) | 1/11 (9.1%; 1.6% to 37.7%) |
| other explicit reason | 4 | 3 | 2/4 (50.0%; 15.0% to 85.0%) | 1/4 (25.0%; 4.6% to 69.9%) |
| pain or neurologic symptoms | 3 | 1 | 3/3 (100.0%; 43.8% to 100.0%) | 1/3 (33.3%; 6.1% to 79.2%) |
| sleep or wakefulness | 11 | 10 | 10/11 (90.9%; 62.3% to 98.4%) | 3/11 (27.3%; 9.7% to 56.6%) |
| social functioning | 5 | 5 | 5/5 (100.0%; 56.6% to 100.0%) | 1/5 (20.0%; 3.6% to 62.4%) |
| stimulant recovery or reduction | 11 | 8 | 11/11 (100.0%; 74.1% to 100.0%) | 2/11 (18.2%; 5.1% to 47.7%) |

## Separate subreddit trend estimates

| Subreddit | Outcome | Episodes | Authors | OR per dose doubling | 95% CI | p | Status |
|---|---|---|---|---|---|---|---|
| Nootropics | ordinal sentiment | 59 | 43 | 1.02 | 0.67 to 1.55 | 0.9238 | estimated |
| Nootropics | side-effect reporting | 59 | 43 | 1.25 | 0.77 to 2.01 | 0.3635 | estimated |
| Supplements | ordinal sentiment | 4 | 3 | n/a | n/a | n/a | too sparse for the prespecified model |
| Supplements | side-effect reporting | 4 | 3 | n/a | n/a | n/a | too sparse for the prespecified model |
| Peptides | ordinal sentiment | 0 | 0 | n/a | n/a | n/a | too sparse for the prespecified model |
| Peptides | side-effect reporting | 0 | 0 | n/a | n/a | n/a | too sparse for the prespecified model |
| NootropicsDepot | ordinal sentiment | 42 | 29 | 0.60 | 0.32 to 1.12 | 0.1063 | estimated |
| NootropicsDepot | side-effect reporting | 42 | 29 | 0.93 | 0.41 to 2.14 | 0.8718 | estimated |
| NooTopics | ordinal sentiment | 9 | 9 | n/a | n/a | n/a | too sparse for the prespecified model |
| NooTopics | side-effect reporting | 9 | 9 | n/a | n/a | n/a | too sparse for the prespecified model |
| depressionregimens | ordinal sentiment | 0 | 0 | n/a | n/a | n/a | too sparse for the prespecified model |
| depressionregimens | side-effect reporting | 0 | 0 | n/a | n/a | n/a | too sparse for the prespecified model |
| StackAdvice | ordinal sentiment | 8 | 6 | n/a | n/a | n/a | too sparse for the prespecified model |
| StackAdvice | side-effect reporting | 8 | 6 | n/a | n/a | n/a | too sparse for the prespecified model |
| Longevity | ordinal sentiment | 0 | 0 | n/a | n/a | n/a | too sparse for the prespecified model |
| Longevity | side-effect reporting | 0 | 0 | n/a | n/a | n/a | too sparse for the prespecified model |
| Psilocybin | ordinal sentiment | 0 | 0 | n/a | n/a | n/a | too sparse for the prespecified model |
| Psilocybin | side-effect reporting | 0 | 0 | n/a | n/a | n/a | too sparse for the prespecified model |

These subreddit-specific models are secondary and report raw p-values only.

## Interpretation boundaries

This is an observational reporting analysis. Dose is self-reported, and formulation, frequency, treatment duration, co-treatments, reason for use, indication severity, and selective posting remain potential confounders. Same-post attribution removes cross-report exposure and outcome mismatch but does not establish timing within the post. The dose-complete set contained only 40 episodes with an explicit reason and 64 with a single route, so adding those variables to the primary model would sharply reduce the sample and condition on selective reporting. They remain secondary descriptives. The between-compound sentiment mean is not used in the primary regression; subreddit fixed effects address community-level sentiment differences without mixing comparator compounds into the within-7,8-DHF dose test.

## Reproducibility

Generated at `2026-09-02T21:38:40.298858+00:00`. Private episode records and caches remain external. No source text, post identifier, or author identifier is included.

| Subreddit | Database | SHA-256 |
|---|---|---|
| Nootropics | combined.db | 47bd9f879b53356724ba0d7b6a58422ba66827bfd00d1e9db94718909339831f |
| Supplements | combined.db | 9d49ad9ec26ff0eb751743e426df88e9bde5462a6f637c7961acfa10d706b393 |
| Peptides | combined.db | 3927c22da7bc802f6c8dee93d4ffd53f373e25d942f6a1f71b42c77c4a0cf299 |
| NootropicsDepot | combined.db | 9967720039935e1fa855fe1cdaf9f9ae123362b10e9653effdd781f49d343a7b |
| NooTopics | combined.db | a593595e57d70702eb8684b4de2ae69fbbcb436d975b5ff00cbd6f65cc46cace |
| depressionregimens | combined.db | b9c29799d6de03248f6c059122afa2f253ca7563c192d129988ae299ace65cac |
| StackAdvice | combined.db | 53a3e303a4313143f1d778c079b9419f2d79b01e6671acde73354660af28d61d |
| Longevity | combined.db | 471515cde8a89bdda0f6adf18816222c5e73798881840560647a102cda52ecda |
| Psilocybin | combined.db | 2c1fe504858914b676ef6897f5dc751e84a0695a3610825dfa0265479441edc9 |

| Episode artifact | SHA-256 |
|---|---|
| episode_records.jsonl | 1df095a6a7a9a1a2250bd4fb32f7bf3ca20bb4f3d84ffdcf9ec44cfad63bdd37 |
| episode_manifest.json | ee4d2d67fd16d9dcf90314f8694781f60afe2788b8fd4bf79efab12c9df1eb32 |

Episode extraction: provider `openrouter`; model `deepseek/deepseek-v4-flash`; code commit `8ae2f4dea3d03f79c0dcdde247f336f232e206e3`; prompt `78dhf_episode_v1.txt` with SHA-256 `4db1319d7805b496fb4d6640f1cd57a2724389f17757d477ae08a7e3b081a331`; batch sizes used 8, 1; completed 1,828/1,828 episodes; 824 explicit personal-use episodes; 122 single-dose episodes; 159 single-route episodes; 1,133,849 provider-reported tokens; completed at `2026-09-02T21:32:58.656281+00:00`.
