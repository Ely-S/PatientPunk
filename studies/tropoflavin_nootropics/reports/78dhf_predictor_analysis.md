# 7,8-DHF dose, route, reason, sentiment, and side-effect analysis

This focused analysis treats dose, administration route, and a directly stated reason for use as predictors. Outcomes are author-level sentiment and whether the author ever reported at least one mapped 7,8-DHF side effect. It is observational and estimates reporting associations, not efficacy, incidence, causation, or a dose-response relationship.

## Cross-compound normalization

Normalization is between compounds. Within each subreddit, the baseline is the unweighted mean of the author-level positive rates for the other nine compounds that have at least 10 authors. 7,8-DHF is excluded. Giving each eligible compound one vote prevents high-volume compounds from defining the mean. `Versus compound mean` is the 7,8-DHF subgroup positive rate minus that baseline in percentage points. `Sentiment z` uses negative = -1, mixed/neutral = 0, and positive = +1, then expresses the subgroup mean relative to the mean and standard deviation across eligible comparator-compound means. This z-score is a sensitivity analysis because sentiment categories are not a validated interval scale.

## Explicit reason for use

Reason categories come from a dedicated extraction pass over retained 7,8-DHF report text. The extractor records only a directly stated purpose or indication. It does not infer a reason from a reported benefit, adverse effect, mechanism discussion, or another compound. Authors may explicitly state more than one reason.

## Coverage

| Cohort | 7,8-DHF authors | Positive | Any mapped side effect | Single dose band | Single route | Explicit reason | Baseline compounds | Comparator mean positive | 7,8-DHF versus mean |
|---|---|---|---|---|---|---|---|---|---|
| Nootropics | 278 | 198/278 (71.2%) | 107/278 (38.5%) | 24/278 (8.6%) | 23/278 (8.3%) | 57/278 (20.5%) | 9 | 66.5% | +4.8 points |
| Supplements | 30 | 23/30 (76.7%) | 10/30 (33.3%) | 2/30 (6.7%) | 2/30 (6.7%) | 9/30 (30.0%) | 3 | 71.4% | +5.3 points |
| Peptides | 4 | 3/4 (75.0%) | 1/4 (25.0%) | 0/4 (0.0%) | 0/4 (0.0%) | 1/4 (25.0%) | 7 | 70.9% | +4.1 points |
| NootropicsDepot | 347 | 258/347 (74.4%) | 135/347 (38.9%) | 21/347 (6.1%) | 30/347 (8.6%) | 58/347 (16.7%) | 7 | 77.4% | -3.0 points |
| NooTopics | 105 | 77/105 (73.3%) | 43/105 (41.0%) | 3/105 (2.9%) | 7/105 (6.7%) | 25/105 (23.8%) | 9 | 66.0% | +7.4 points |
| depressionregimens | 8 | 7/8 (87.5%) | 1/8 (12.5%) | 1/8 (12.5%) | 1/8 (12.5%) | 3/8 (37.5%) | 5 | 66.9% | +20.6 points |
| StackAdvice | 61 | 45/61 (73.8%) | 16/61 (26.2%) | 10/61 (16.4%) | 2/61 (3.3%) | 12/61 (19.7%) | 9 | 74.0% | -0.2 points |
| Longevity | 0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 0 | n/a | n/a |
| Psilocybin | 0 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 | 1 | 85.7% | n/a |
| Combined, deduplicated | 673 | 482/673 (71.6%) | 268/673 (39.8%) | 52/673 (7.7%) | 54/673 (8.0%) | 149/673 (22.1%) | 9 | 66.9% | +4.7 points |

## Main findings

Across 673 globally distinct 7,8-DHF authors, 482/673 (71.6%) were classified positive and 268/673 (39.8%) reported at least one mapped side effect. The positive share was +4.7 percentage points relative to the unweighted mean across 9 eligible comparator compounds.

Predictor coverage was limited: 52 authors had one usable dose band, 54 had one usable route, and 149 had at least one explicit reason for use. No combined dose, route, or explicit-reason association with sentiment or side-effect reporting passed Benjamini-Hochberg correction at q < 0.05.

## Combined cross-compound baseline

| Compound | Globally distinct authors | Positive share | Mean sentiment score | In comparator mean |
|---|---|---|---|---|
| 7,8-DHF | 673 | 71.6% | +0.461 | no |
| 4'-DMA-7,8-DHF | 255 | 71.8% | +0.475 | yes |
| Semax | 3701 | 65.9% | +0.353 | yes |
| Cerebrolysin | 927 | 72.5% | +0.485 | yes |
| Selank | 2225 | 68.2% | +0.389 | yes |
| NSI-189 | 1184 | 61.2% | +0.288 | yes |
| Dihexa | 434 | 62.2% | +0.295 | yes |
| Lion's mane | 9064 | 62.8% | +0.299 | yes |
| 9-MBC | 250 | 66.8% | +0.360 | yes |
| BPC-157 | 7019 | 70.9% | +0.451 | yes |

## Combined analysis, globally deduplicated

Only identifiable hashed authors are included, and each contributes once. When an author appears in multiple cohorts, the latest 7,8-DHF sentiment report is selected and their dose, route, reason, and mapped side-effect sets are combined. `Community-standardized` subtracts the selected report's subreddit-specific cross-compound mean before averaging. The Mantel-Haenszel odds ratios are stratified by that selected subreddit.

### Combined: Dosage

| Level | Authors | Positive | Positive share | Versus compound mean | Community-standardized | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|---|
| <5 mg | 2 | 1/2 | 50.0% (9.5% to 90.5%) | -16.9 points | -19.1 points | -4.85 | 1/2 (50.0%; 9.5% to 90.5%) | activation or irritability: 1/2 (50.0%); anxiety or panic: 1/2 (50.0%); other reported effect: 1/2 (50.0%) | too sparse for inference |
| 5 to <10 mg | 2 | 2/2 | 100.0% (34.2% to 100.0%) | +33.1 points | +28.1 points | 8.00 | 1/2 (50.0%; 9.5% to 90.5%) | activation or irritability: 1/2 (50.0%) | too sparse for inference |
| 10 to <25 mg | 16 | 11/16 | 68.8% (44.4% to 85.8%) | +1.8 points | -1.8 points | 0.77 | 6/16 (37.5%; 18.5% to 61.4%) | other reported effect: 4/16 (25.0%); cognitive or perceptual disturbance: 3/16 (18.8%); insomnia or sleep disruption: 2/16 (12.5%) | estimable association; not causal |
| 25 to <50 mg | 22 | 17/22 | 77.3% (56.6% to 89.9%) | +10.3 points | +4.4 points | 2.75 | 13/22 (59.1%; 38.7% to 76.7%) | insomnia or sleep disruption: 6/22 (27.3%); other reported effect: 5/22 (22.7%); headache or migraine: 2/22 (9.1%) | estimable association; not causal |
| 50 to <100 mg | 8 | 6/8 | 75.0% (40.9% to 92.9%) | +8.1 points | +3.2 points | 1.58 | 4/8 (50.0%; 21.5% to 78.5%) | other reported effect: 2/8 (25.0%); activation or irritability: 2/8 (25.0%); headache or migraine: 1/8 (12.5%) | too sparse for inference |
| >=100 mg | 2 | 2/2 | 100.0% (34.2% to 100.0%) | +33.1 points | +33.8 points | 8.00 | 1/2 (50.0%; 9.5% to 90.5%) | headache or migraine: 1/2 (50.0%); other reported effect: 1/2 (50.0%) | too sparse for inference |
| multiple dose bands | 9 | 5/9 | 55.6% (26.7% to 81.1%) | -11.4 points | -16.5 points | -1.99 | 5/9 (55.6%; 26.7% to 81.1%) | other reported effect: 5/9 (55.6%); headache or migraine: 4/9 (44.4%); cognitive or perceptual disturbance: 3/9 (33.3%) | descriptive only; multiple reported values |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q | Subreddit-adjusted positive OR | Adjusted p | Subreddit-adjusted side-effect OR | Adjusted SE p |
|---|---|---|---|---|---|---|---|---|---|---|---|
| <5 mg | 50 | 0.32 | 0.4412 | n/a | 1.00 | 1.0000 | n/a | 0.00 | 0.3173 | inf | 0.3173 |
| 5 to <10 mg | 50 | inf | 1.0000 | n/a | 1.00 | 1.0000 | n/a | inf | 0.4362 | 0.83 | 0.9176 |
| 10 to <25 mg | 36 | 0.63 | 0.5060 | 1.0000 | 0.48 | 0.3678 | 0.4001 | 0.60 | 0.5028 | 0.56 | 0.3945 |
| 25 to <50 mg | 30 | 1.24 | 1.0000 | 1.0000 | 1.89 | 0.4001 | 0.4001 | 1.10 | 0.8917 | 1.74 | 0.3503 |
| 50 to <100 mg | 44 | 1.00 | 1.0000 | n/a | 1.00 | 1.0000 | n/a | 1.12 | 0.9106 | 0.70 | 0.6102 |
| >=100 mg | 50 | inf | 1.0000 | n/a | 1.00 | 1.0000 | n/a | inf | 0.3141 | 0.96 | 0.9759 |
| multiple dose bands | 52 | 0.42 | 0.2489 | n/a | 1.25 | 1.0000 | n/a | 0.41 | 0.2228 | 1.15 | 0.8288 |

### Combined: Administration route

| Level | Authors | Positive | Positive share | Versus compound mean | Community-standardized | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|---|
| multiple route families | 10 | 8/10 | 80.0% (49.0% to 94.3%) | +13.1 points | +6.6 points | 2.86 | 6/10 (60.0%; 31.3% to 83.2%) | insomnia or sleep disruption: 3/10 (30.0%); other reported effect: 2/10 (20.0%); headache or migraine: 2/10 (20.0%) | descriptive only; multiple reported values |
| nasal mucosal | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +33.1 points | +22.6 points | 8.00 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | too sparse for inference |
| oral mucosal | 45 | 32/45 | 71.1% (56.6% to 82.3%) | +4.2 points | -1.2 points | 1.44 | 24/45 (53.3%; 39.1% to 67.1%) | other reported effect: 12/45 (26.7%); insomnia or sleep disruption: 12/45 (26.7%); activation or irritability: 7/45 (15.6%) | too sparse for inference |
| swallowed oral | 8 | 6/8 | 75.0% (40.9% to 92.9%) | +8.1 points | +3.2 points | 1.58 | 3/8 (37.5%; 13.7% to 69.4%) | insomnia or sleep disruption: 2/8 (25.0%); headache or migraine: 1/8 (12.5%); depressed or flattened mood: 1/8 (12.5%) | too sparse for inference |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q | Subreddit-adjusted positive OR | Adjusted p | Subreddit-adjusted side-effect OR | Adjusted SE p |
|---|---|---|---|---|---|---|---|---|---|---|---|
| multiple route families | 54 | 1.54 | 1.0000 | n/a | 1.50 | 0.7338 | n/a | 1.82 | 0.5120 | 1.82 | 0.3808 |
| nasal mucosal | 53 | inf | 1.0000 | n/a | 0.00 | 1.0000 | n/a | inf | 0.6767 | 0.00 | 0.3352 |
| oral mucosal | 9 | 0.70 | 1.0000 | n/a | 2.29 | 0.4672 | n/a | 0.49 | 0.4434 | 6.15 | 0.0951 |
| swallowed oral | 46 | 1.18 | 1.0000 | n/a | 0.55 | 0.7040 | n/a | 1.80 | 0.5195 | 0.22 | 0.1804 |

### Combined: Explicit reason for use

| Level | Authors | Positive | Positive share | Versus compound mean | Community-standardized | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|---|
| anxiety or stress | 24 | 22/24 | 91.7% (74.2% to 97.7%) | +24.7 points | +19.6 points | 6.40 | 8/24 (33.3%; 18.0% to 53.3%) | other reported effect: 6/24 (25.0%); insomnia or sleep disruption: 3/24 (12.5%); activation or irritability: 3/24 (12.5%) | estimable association; not causal |
| cardiovascular or autonomic | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +33.1 points | +26.0 points | 8.00 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | too sparse for inference |
| cognition or brain fog | 24 | 18/24 | 75.0% (55.1% to 88.0%) | +8.1 points | +2.6 points | 2.65 | 8/24 (33.3%; 18.0% to 53.3%) | other reported effect: 6/24 (25.0%); insomnia or sleep disruption: 5/24 (20.8%); depressed or flattened mood: 2/24 (8.3%) | estimable association; not causal |
| energy or motivation | 37 | 28/37 | 75.7% (59.9% to 86.6%) | +8.7 points | +2.0 points | 2.10 | 20/37 (54.1%; 38.4% to 69.0%) | other reported effect: 13/37 (35.1%); insomnia or sleep disruption: 10/37 (27.0%); activation or irritability: 6/37 (16.2%) | estimable association; not causal |
| focus or attention | 49 | 42/49 | 85.7% (73.3% to 92.9%) | +18.8 points | +13.0 points | 4.33 | 23/49 (46.9%; 33.7% to 60.6%) | other reported effect: 14/49 (28.6%); insomnia or sleep disruption: 11/49 (22.4%); activation or irritability: 6/49 (12.2%) | estimable association; not causal |
| memory or learning | 17 | 16/17 | 94.1% (73.0% to 99.0%) | +27.2 points | +20.4 points | 6.49 | 5/17 (29.4%; 13.3% to 53.1%) | other reported effect: 4/17 (23.5%); insomnia or sleep disruption: 1/17 (5.9%); activation or irritability: 1/17 (5.9%) | estimable association; not causal |
| mood or depression | 62 | 55/62 | 88.7% (78.5% to 94.4%) | +21.8 points | +16.1 points | 5.52 | 22/62 (35.5%; 24.7% to 47.9%) | other reported effect: 15/62 (24.2%); insomnia or sleep disruption: 5/62 (8.1%); activation or irritability: 5/62 (8.1%) | estimable association; not causal |
| neuroprotection or recovery | 15 | 13/15 | 86.7% (62.1% to 96.3%) | +19.7 points | +15.8 points | 5.43 | 6/15 (40.0%; 19.8% to 64.3%) | other reported effect: 6/15 (40.0%); appetite change: 2/15 (13.3%); activation or irritability: 1/15 (6.7%) | estimable association; not causal |
| other explicit reason | 13 | 10/13 | 76.9% (49.7% to 91.8%) | +10.0 points | +4.8 points | 2.07 | 5/13 (38.5%; 17.7% to 64.5%) | other reported effect: 4/13 (30.8%); headache or migraine: 3/13 (23.1%); cognitive or perceptual disturbance: 2/13 (15.4%) | estimable association; not causal |
| pain or neurologic symptoms | 3 | 2/3 | 66.7% (20.8% to 93.9%) | -0.3 points | -4.7 points | -0.56 | 2/3 (66.7%; 20.8% to 93.9%) | other reported effect: 2/3 (66.7%); cardiovascular or autonomic: 1/3 (33.3%); insomnia or sleep disruption: 1/3 (33.3%) | too sparse for inference |
| sleep or wakefulness | 9 | 8/9 | 88.9% (56.5% to 98.0%) | +22.0 points | +17.9 points | 5.15 | 5/9 (55.6%; 26.7% to 81.1%) | insomnia or sleep disruption: 3/9 (33.3%); headache or migraine: 2/9 (22.2%); cognitive or perceptual disturbance: 2/9 (22.2%) | too sparse for inference |
| social functioning | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +33.1 points | +34.0 points | 8.00 | 1/1 (100.0%; 20.7% to 100.0%) | headache or migraine: 1/1 (100.0%); insomnia or sleep disruption: 1/1 (100.0%) | too sparse for inference |
| stimulant recovery or reduction | 15 | 15/15 | 100.0% (79.6% to 100.0%) | +33.1 points | +30.3 points | 8.00 | 8/15 (53.3%; 30.1% to 75.2%) | other reported effect: 4/15 (26.7%); insomnia or sleep disruption: 4/15 (26.7%); headache or migraine: 2/15 (13.3%) | estimable association; not causal |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q | Subreddit-adjusted positive OR | Adjusted p | Subreddit-adjusted side-effect OR | Adjusted SE p |
|---|---|---|---|---|---|---|---|---|---|---|---|
| anxiety or stress | 125 | 2.48 | 0.3703 | 0.5554 | 0.80 | 0.8185 | 1.0000 | 2.47 | 0.2341 | 0.83 | 0.6967 |
| cardiovascular or autonomic | 148 | inf | 1.0000 | n/a | 0.00 | 1.0000 | n/a | inf | 0.6374 | 0.00 | 0.4497 |
| cognition or brain fog | 125 | 0.54 | 0.2421 | 0.5446 | 0.80 | 0.8185 | 1.0000 | 0.49 | 0.1842 | 0.84 | 0.7233 |
| energy or motivation | 112 | 0.52 | 0.2033 | 0.5446 | 2.48 | 0.0199 | 0.1793 | 0.49 | 0.1276 | 2.41 | 0.0276 |
| focus or attention | 100 | 1.32 | 0.6465 | 0.7273 | 1.80 | 0.1084 | 0.4878 | 1.34 | 0.5589 | 1.70 | 0.1298 |
| memory or learning | 132 | 3.56 | 0.3076 | 0.5537 | 0.66 | 0.5976 | 1.0000 | 3.48 | 0.2118 | 0.72 | 0.5659 |
| mood or depression | 87 | 2.05 | 0.1819 | 0.5446 | 0.86 | 0.7324 | 1.0000 | 2.02 | 0.1547 | 0.85 | 0.6474 |
| neuroprotection or recovery | 134 | 1.35 | 1.0000 | 1.0000 | 1.12 | 1.0000 | 1.0000 | 1.45 | 0.6479 | 1.11 | 0.8500 |
| other explicit reason | 136 | 0.64 | 0.4584 | 0.5893 | 1.04 | 1.0000 | 1.0000 | 0.66 | 0.5533 | 1.12 | 0.8478 |
| pain or neurologic symptoms | 146 | 0.39 | 0.4260 | n/a | 3.41 | 0.5566 | n/a | 0.27 | 0.3774 | 4.12 | 0.2946 |
| sleep or wakefulness | 140 | 1.66 | 1.0000 | n/a | 2.18 | 0.2971 | n/a | 1.83 | 0.5901 | 2.37 | 0.2113 |
| social functioning | 148 | inf | 1.0000 | n/a | inf | 0.3758 | n/a | inf | 0.7316 | inf | 0.2410 |
| stimulant recovery or reduction | 134 | inf | 0.0760 | 0.5446 | 2.05 | 0.2604 | 0.7811 | inf | 0.0761 | 2.08 | 0.1882 |

## Separate subreddit analyses

### r/Nootropics

7,8-DHF has 278 classified authors and a raw positive share of 71.2%. The leave-target-out comparator mean uses 9 compounds and is 66.5%.

#### Dosage

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| <5 mg | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +33.5 points | 7.31 | 1/1 (100.0%; 20.7% to 100.0%) | other reported effect: 1/1 (100.0%); insomnia or sleep disruption: 1/1 (100.0%) | too sparse for inference |
| 5 to <10 mg | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +33.5 points | 7.31 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | too sparse for inference |
| 10 to <25 mg | 7 | 4/7 | 57.1% (25.0% to 84.2%) | -9.3 points | -2.60 | 2/7 (28.6%; 8.2% to 64.1%) | cognitive or perceptual disturbance: 2/7 (28.6%); other reported effect: 1/7 (14.3%); activation or irritability: 1/7 (14.3%) | too sparse for inference |
| 25 to <50 mg | 10 | 8/10 | 80.0% (49.0% to 94.3%) | +13.5 points | 2.69 | 4/10 (40.0%; 16.8% to 68.7%) | insomnia or sleep disruption: 2/10 (20.0%); other reported effect: 1/10 (10.0%); sexual: 1/10 (10.0%) | estimable association; not causal |
| 50 to <100 mg | 4 | 3/4 | 75.0% (30.1% to 95.4%) | +8.5 points | 4.42 | 3/4 (75.0%; 30.1% to 95.4%) | headache or migraine: 2/4 (50.0%); cognitive or perceptual disturbance: 2/4 (50.0%); other reported effect: 1/4 (25.0%) | too sparse for inference |
| >=100 mg | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +33.5 points | 7.31 | 1/1 (100.0%; 20.7% to 100.0%) | headache or migraine: 1/1 (100.0%); other reported effect: 1/1 (100.0%) | too sparse for inference |
| multiple dose bands | 4 | 2/4 | 50.0% (15.0% to 85.0%) | -16.5 points | -4.25 | 3/4 (75.0%; 30.1% to 95.4%) | headache or migraine: 3/4 (75.0%); other reported effect: 1/4 (25.0%); cognitive or perceptual disturbance: 1/4 (25.0%) | descriptive only; multiple reported values |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| <5 mg | 23 | inf | 1.0000 | n/a | inf | 0.4583 | n/a |
| 5 to <10 mg | 23 | inf | 1.0000 | n/a | 0.00 | 1.0000 | n/a |
| 10 to <25 mg | 17 | 0.29 | 0.3068 | n/a | 0.36 | 0.3864 | n/a |
| 25 to <50 mg | 14 | 1.60 | 1.0000 | 1.0000 | 0.67 | 0.6968 | 0.6968 |
| 50 to <100 mg | 20 | 1.00 | 1.0000 | n/a | 4.50 | 0.3002 | n/a |
| >=100 mg | 23 | inf | 1.0000 | n/a | inf | 0.4583 | n/a |
| multiple dose bands | 24 | 0.33 | 0.5546 | n/a | 3.55 | 0.5956 | n/a |

#### Administration route

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| dermal | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +33.5 points | 7.31 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | too sparse for inference |
| multiple route families | 3 | 2/3 | 66.7% (20.8% to 93.9%) | +0.2 points | -0.40 | 2/3 (66.7%; 20.8% to 93.9%) | headache or migraine: 2/3 (66.7%) | descriptive only; multiple reported values |
| oral mucosal | 22 | 17/22 | 77.3% (56.6% to 89.9%) | +10.8 points | 2.05 | 10/22 (45.5%; 26.9% to 65.3%) | insomnia or sleep disruption: 6/22 (27.3%); headache or migraine: 3/22 (13.6%); other reported effect: 2/22 (9.1%) | too sparse for inference |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| dermal | 22 | inf | 1.0000 | n/a | 0.00 | 1.0000 | n/a |
| multiple route families | 23 | 0.56 | 1.0000 | n/a | 2.60 | 0.5800 | n/a |
| oral mucosal | 1 | 0.00 | 1.0000 | n/a | inf | 1.0000 | n/a |

#### Explicit reason for use

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| anxiety or stress | 11 | 11/11 | 100.0% (74.1% to 100.0%) | +33.5 points | 7.31 | 4/11 (36.4%; 15.2% to 64.6%) | activation or irritability: 2/11 (18.2%); other reported effect: 2/11 (18.2%); insomnia or sleep disruption: 2/11 (18.2%) | estimable association; not causal |
| cognition or brain fog | 7 | 5/7 | 71.4% (35.9% to 91.8%) | +5.0 points | 0.70 | 2/7 (28.6%; 8.2% to 64.1%) | depressed or flattened mood: 1/7 (14.3%); other reported effect: 1/7 (14.3%); cognitive or perceptual disturbance: 1/7 (14.3%) | too sparse for inference |
| energy or motivation | 10 | 7/10 | 70.0% (39.7% to 89.2%) | +3.5 points | 1.53 | 5/10 (50.0%; 23.7% to 76.3%) | insomnia or sleep disruption: 4/10 (40.0%); other reported effect: 2/10 (20.0%); activation or irritability: 2/10 (20.0%) | estimable association; not causal |
| focus or attention | 19 | 18/19 | 94.7% (75.4% to 99.1%) | +28.3 points | 6.09 | 5/19 (26.3%; 11.8% to 48.8%) | insomnia or sleep disruption: 5/19 (26.3%); activation or irritability: 2/19 (10.5%); other reported effect: 2/19 (10.5%) | estimable association; not causal |
| memory or learning | 5 | 5/5 | 100.0% (56.6% to 100.0%) | +33.5 points | 7.31 | 1/5 (20.0%; 3.6% to 62.4%) | activation or irritability: 1/5 (20.0%); insomnia or sleep disruption: 1/5 (20.0%) | too sparse for inference |
| mood or depression | 22 | 21/22 | 95.5% (78.2% to 99.2%) | +29.0 points | 6.26 | 6/22 (27.3%; 13.2% to 48.2%) | headache or migraine: 4/22 (18.2%); other reported effect: 3/22 (13.6%); insomnia or sleep disruption: 3/22 (13.6%) | estimable association; not causal |
| neuroprotection or recovery | 8 | 7/8 | 87.5% (52.9% to 97.8%) | +21.0 points | 4.42 | 2/8 (25.0%; 7.1% to 59.1%) | other reported effect: 1/8 (12.5%); appetite change: 1/8 (12.5%); headache or migraine: 1/8 (12.5%) | too sparse for inference |
| other explicit reason | 6 | 4/6 | 66.7% (30.0% to 90.3%) | +0.2 points | -0.40 | 2/6 (33.3%; 9.7% to 70.0%) | headache or migraine: 2/6 (33.3%); other reported effect: 2/6 (33.3%); cognitive or perceptual disturbance: 2/6 (33.3%) | too sparse for inference |
| pain or neurologic symptoms | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +33.5 points | 7.31 | 1/1 (100.0%; 20.7% to 100.0%) | cardiovascular or autonomic: 1/1 (100.0%) | too sparse for inference |
| sleep or wakefulness | 5 | 4/5 | 80.0% (37.6% to 96.4%) | +13.5 points | 2.69 | 2/5 (40.0%; 11.8% to 76.9%) | insomnia or sleep disruption: 1/5 (20.0%); cognitive or perceptual disturbance: 1/5 (20.0%); anxiety or panic: 1/5 (20.0%) | too sparse for inference |
| social functioning | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +33.5 points | 7.31 | 1/1 (100.0%; 20.7% to 100.0%) | headache or migraine: 1/1 (100.0%); insomnia or sleep disruption: 1/1 (100.0%) | too sparse for inference |
| stimulant recovery or reduction | 9 | 9/9 | 100.0% (70.1% to 100.0%) | +33.5 points | 7.31 | 5/9 (55.6%; 26.7% to 81.1%) | insomnia or sleep disruption: 3/9 (33.3%); activation or irritability: 1/9 (11.1%); headache or migraine: 1/9 (11.1%) | too sparse for inference |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| anxiety or stress | 46 | inf | 0.3319 | 0.3319 | 1.45 | 0.7166 | 0.7758 |
| cognition or brain fog | 50 | 0.34 | 0.2520 | n/a | 0.93 | 1.0000 | n/a |
| energy or motivation | 47 | 0.28 | 0.1367 | 0.2734 | 2.92 | 0.1450 | 0.5801 |
| focus or attention | 38 | 4.06 | 0.2468 | 0.3291 | 0.77 | 0.7662 | 0.7758 |
| memory or learning | 52 | inf | 1.0000 | n/a | 0.56 | 1.0000 | n/a |
| mood or depression | 35 | 5.25 | 0.1344 | 0.2734 | 0.82 | 0.7758 | 0.7758 |
| neuroprotection or recovery | 49 | 1.17 | 1.0000 | n/a | 0.76 | 1.0000 | n/a |
| other explicit reason | 51 | 0.27 | 0.1943 | n/a | 1.20 | 1.0000 | n/a |
| pain or neurologic symptoms | 56 | inf | 1.0000 | n/a | inf | 0.2982 | n/a |
| sleep or wakefulness | 52 | 0.62 | 0.5446 | n/a | 1.64 | 0.6289 | n/a |
| social functioning | 56 | inf | 1.0000 | n/a | inf | 0.2982 | n/a |
| stimulant recovery or reduction | 48 | inf | 0.3316 | n/a | 3.75 | 0.1086 | n/a |

### r/Supplements

7,8-DHF has 30 classified authors and a raw positive share of 76.7%. The leave-target-out comparator mean uses 3 compounds and is 71.4%.

#### Dosage

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| <5 mg | 1 | 0/1 | 0.0% (0.0% to 79.3%) | -71.4 points | -5.93 | 1/1 (100.0%; 20.7% to 100.0%) | activation or irritability: 1/1 (100.0%); anxiety or panic: 1/1 (100.0%); other reported effect: 1/1 (100.0%) | too sparse for inference |
| 10 to <25 mg | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +28.6 points | 2.32 | 1/1 (100.0%; 20.7% to 100.0%) | other reported effect: 1/1 (100.0%) | too sparse for inference |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| <5 mg | 1 | 0.00 | 1.0000 | n/a | n/a | 1.0000 | n/a |
| 10 to <25 mg | 1 | inf | 1.0000 | n/a | n/a | 1.0000 | n/a |

#### Administration route

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| oral mucosal | 2 | 1/2 | 50.0% (9.5% to 90.5%) | -21.4 points | -1.80 | 2/2 (100.0%; 34.2% to 100.0%) | other reported effect: 2/2 (100.0%); activation or irritability: 1/2 (50.0%); anxiety or panic: 1/2 (50.0%) | too sparse for inference |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| oral mucosal | 0 | n/a | n/a | n/a | n/a | n/a | n/a |

#### Explicit reason for use

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| anxiety or stress | 1 | 0/1 | 0.0% (0.0% to 79.3%) | -71.4 points | -5.93 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | too sparse for inference |
| cognition or brain fog | 3 | 2/3 | 66.7% (20.8% to 93.9%) | -4.7 points | -0.43 | 0/3 (0.0%; 0.0% to 56.2%) | none mapped | too sparse for inference |
| energy or motivation | 4 | 3/4 | 75.0% (30.1% to 95.4%) | +3.6 points | 0.26 | 2/4 (50.0%; 15.0% to 85.0%) | activation or irritability: 2/4 (50.0%); other reported effect: 2/4 (50.0%); anxiety or panic: 1/4 (25.0%) | too sparse for inference |
| focus or attention | 3 | 2/3 | 66.7% (20.8% to 93.9%) | -4.7 points | -0.43 | 1/3 (33.3%; 6.1% to 79.2%) | activation or irritability: 1/3 (33.3%); anxiety or panic: 1/3 (33.3%); other reported effect: 1/3 (33.3%) | too sparse for inference |
| memory or learning | 2 | 2/2 | 100.0% (34.2% to 100.0%) | +28.6 points | 2.32 | 1/2 (50.0%; 9.5% to 90.5%) | other reported effect: 1/2 (50.0%) | too sparse for inference |
| mood or depression | 6 | 5/6 | 83.3% (43.6% to 97.0%) | +12.0 points | 0.95 | 2/6 (33.3%; 9.7% to 70.0%) | depressed or flattened mood: 1/6 (16.7%); other reported effect: 1/6 (16.7%) | too sparse for inference |
| other explicit reason | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +28.6 points | 2.32 | 1/1 (100.0%; 20.7% to 100.0%) | other reported effect: 1/1 (100.0%) | too sparse for inference |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| anxiety or stress | 8 | 0.00 | 0.2222 | n/a | 0.00 | 1.0000 | n/a |
| cognition or brain fog | 6 | 0.40 | 1.0000 | n/a | 0.00 | 0.1667 | n/a |
| energy or motivation | 5 | 0.75 | 1.0000 | n/a | 1.50 | 1.0000 | n/a |
| focus or attention | 6 | 0.40 | 1.0000 | n/a | 0.50 | 1.0000 | n/a |
| memory or learning | 7 | inf | 1.0000 | n/a | 1.33 | 1.0000 | n/a |
| mood or depression | 3 | 2.50 | 1.0000 | n/a | 0.25 | 0.5238 | n/a |
| other explicit reason | 8 | inf | 1.0000 | n/a | inf | 0.4444 | n/a |

### r/Peptides

7,8-DHF has 4 classified authors and a raw positive share of 75.0%. The leave-target-out comparator mean uses 7 compounds and is 70.9%.

#### Dosage

No eligible 7,8-DHF authors had this predictor extracted.

#### Administration route

No eligible 7,8-DHF authors had this predictor extracted.

#### Explicit reason for use

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| cognition or brain fog | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +29.1 points | 4.66 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | too sparse for inference |
| memory or learning | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +29.1 points | 4.66 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | too sparse for inference |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| cognition or brain fog | 0 | n/a | n/a | n/a | n/a | n/a | n/a |
| memory or learning | 0 | n/a | n/a | n/a | n/a | n/a | n/a |

### r/NootropicsDepot

7,8-DHF has 347 classified authors and a raw positive share of 74.4%. The leave-target-out comparator mean uses 7 compounds and is 77.4%.

#### Dosage

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| 5 to <10 mg | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +22.6 points | 2.14 | 1/1 (100.0%; 20.7% to 100.0%) | activation or irritability: 1/1 (100.0%) | too sparse for inference |
| 10 to <25 mg | 3 | 3/3 | 100.0% (43.8% to 100.0%) | +22.6 points | 2.14 | 1/3 (33.3%; 6.1% to 79.2%) | other reported effect: 1/3 (33.3%) | too sparse for inference |
| 25 to <50 mg | 12 | 9/12 | 75.0% (46.8% to 91.1%) | -2.4 points | 0.01 | 9/12 (75.0%; 46.8% to 91.1%) | insomnia or sleep disruption: 4/12 (33.3%); other reported effect: 3/12 (25.0%); headache or migraine: 2/12 (16.7%) | too sparse for inference |
| 50 to <100 mg | 5 | 4/5 | 80.0% (37.6% to 96.4%) | +2.6 points | 0.10 | 1/5 (20.0%; 3.6% to 62.4%) | other reported effect: 1/5 (20.0%) | too sparse for inference |
| multiple dose bands | 3 | 2/3 | 66.7% (20.8% to 93.9%) | -10.7 points | -1.26 | 1/3 (33.3%; 6.1% to 79.2%) | anxiety or panic: 1/3 (33.3%); other reported effect: 1/3 (33.3%); insomnia or sleep disruption: 1/3 (33.3%) | descriptive only; multiple reported values |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| 5 to <10 mg | 20 | inf | 1.0000 | n/a | inf | 1.0000 | n/a |
| 10 to <25 mg | 18 | inf | 1.0000 | n/a | 0.32 | 0.5534 | n/a |
| 25 to <50 mg | 9 | 0.38 | 0.6030 | n/a | 6.00 | 0.0872 | n/a |
| 50 to <100 mg | 16 | 0.92 | 1.0000 | n/a | 0.11 | 0.1194 | n/a |
| multiple dose bands | 21 | 0.47 | 0.5212 | n/a | 0.38 | 0.5761 | n/a |

#### Administration route

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| multiple route families | 4 | 3/4 | 75.0% (30.1% to 95.4%) | -2.4 points | -0.41 | 4/4 (100.0%; 51.0% to 100.0%) | insomnia or sleep disruption: 3/4 (75.0%); anxiety or panic: 1/4 (25.0%); other reported effect: 1/4 (25.0%) | descriptive only; multiple reported values |
| nasal mucosal | 2 | 2/2 | 100.0% (34.2% to 100.0%) | +22.6 points | 2.14 | 0/2 (0.0%; 0.0% to 65.8%) | none mapped | too sparse for inference |
| oral mucosal | 22 | 19/22 | 86.4% (66.7% to 95.3%) | +9.0 points | 0.98 | 10/22 (45.5%; 26.9% to 65.3%) | insomnia or sleep disruption: 5/22 (22.7%); other reported effect: 4/22 (18.2%); activation or irritability: 3/22 (13.6%) | too sparse for inference |
| swallowed oral | 6 | 4/6 | 66.7% (30.0% to 90.3%) | -10.7 points | -1.26 | 2/6 (33.3%; 9.7% to 70.0%) | headache or migraine: 1/6 (16.7%); insomnia or sleep disruption: 1/6 (16.7%) | too sparse for inference |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| multiple route families | 30 | 0.60 | 0.5585 | n/a | inf | 0.0392 | n/a |
| nasal mucosal | 28 | inf | 1.0000 | n/a | 0.00 | 0.5034 | n/a |
| oral mucosal | 8 | 2.11 | 0.5894 | n/a | 2.50 | 0.4192 | n/a |
| swallowed oral | 24 | 0.29 | 0.2543 | n/a | 0.70 | 1.0000 | n/a |

#### Explicit reason for use

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| anxiety or stress | 8 | 8/8 | 100.0% (67.6% to 100.0%) | +22.6 points | 2.14 | 4/8 (50.0%; 21.5% to 78.5%) | other reported effect: 3/8 (37.5%); anxiety or panic: 2/8 (25.0%); insomnia or sleep disruption: 1/8 (12.5%) | too sparse for inference |
| cognition or brain fog | 9 | 8/9 | 88.9% (56.5% to 98.0%) | +11.5 points | 1.00 | 2/9 (22.2%; 6.3% to 54.7%) | other reported effect: 2/9 (22.2%) | too sparse for inference |
| energy or motivation | 15 | 11/15 | 73.3% (48.0% to 89.1%) | -4.0 points | -0.58 | 6/15 (40.0%; 19.8% to 64.3%) | other reported effect: 3/15 (20.0%); insomnia or sleep disruption: 3/15 (20.0%); activation or irritability: 1/15 (6.7%) | estimable association; not causal |
| focus or attention | 22 | 17/22 | 77.3% (56.6% to 89.9%) | -0.1 points | -0.18 | 13/22 (59.1%; 38.7% to 76.7%) | other reported effect: 7/22 (31.8%); insomnia or sleep disruption: 5/22 (22.7%); activation or irritability: 2/22 (9.1%) | estimable association; not causal |
| memory or learning | 6 | 5/6 | 83.3% (43.6% to 97.0%) | +6.0 points | 0.44 | 1/6 (16.7%; 3.0% to 56.4%) | other reported effect: 1/6 (16.7%) | too sparse for inference |
| mood or depression | 23 | 19/23 | 82.6% (62.9% to 93.0%) | +5.2 points | 0.81 | 7/23 (30.4%; 15.6% to 50.9%) | other reported effect: 4/23 (17.4%); activation or irritability: 2/23 (8.7%); insomnia or sleep disruption: 2/23 (8.7%) | estimable association; not causal |
| neuroprotection or recovery | 3 | 3/3 | 100.0% (43.8% to 100.0%) | +22.6 points | 2.14 | 1/3 (33.3%; 6.1% to 79.2%) | other reported effect: 1/3 (33.3%) | too sparse for inference |
| other explicit reason | 5 | 4/5 | 80.0% (37.6% to 96.4%) | +2.6 points | 0.10 | 1/5 (20.0%; 3.6% to 62.4%) | other reported effect: 1/5 (20.0%) | too sparse for inference |
| sleep or wakefulness | 3 | 3/3 | 100.0% (43.8% to 100.0%) | +22.6 points | 2.14 | 2/3 (66.7%; 20.8% to 93.9%) | headache or migraine: 1/3 (33.3%); other reported effect: 1/3 (33.3%); insomnia or sleep disruption: 1/3 (33.3%) | too sparse for inference |
| stimulant recovery or reduction | 2 | 2/2 | 100.0% (34.2% to 100.0%) | +22.6 points | 2.14 | 1/2 (50.0%; 9.5% to 90.5%) | other reported effect: 1/2 (50.0%) | too sparse for inference |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| anxiety or stress | 50 | inf | 0.3278 | n/a | 2.12 | 0.4278 | n/a |
| cognition or brain fog | 49 | 1.80 | 1.0000 | n/a | 0.49 | 0.4761 | n/a |
| energy or motivation | 43 | 0.45 | 0.2651 | 0.7209 | 1.38 | 0.7537 | 0.7785 |
| focus or attention | 36 | 0.55 | 0.4806 | 0.7209 | 5.98 | 0.0039 | 0.0116 |
| memory or learning | 52 | 1.05 | 1.0000 | n/a | 0.35 | 0.6535 | n/a |
| mood or depression | 35 | 0.98 | 1.0000 | 1.0000 | 0.74 | 0.7785 | 0.7785 |
| neuroprotection or recovery | 55 | inf | 1.0000 | n/a | 0.95 | 1.0000 | n/a |
| other explicit reason | 53 | 0.82 | 1.0000 | n/a | 0.45 | 0.6502 | n/a |
| sleep or wakefulness | 55 | inf | 1.0000 | n/a | 4.11 | 0.2709 | n/a |
| stimulant recovery or reduction | 56 | inf | 1.0000 | n/a | 1.95 | 1.0000 | n/a |

### r/NooTopics

7,8-DHF has 105 classified authors and a raw positive share of 73.3%. The leave-target-out comparator mean uses 9 compounds and is 66.0%.

#### Dosage

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| 10 to <25 mg | 2 | 1/2 | 50.0% (9.5% to 90.5%) | -16.0 points | -2.29 | 1/2 (50.0%; 9.5% to 90.5%) | cognitive or perceptual disturbance: 1/2 (50.0%); anxiety or panic: 1/2 (50.0%); other reported effect: 1/2 (50.0%) | too sparse for inference |
| 50 to <100 mg | 1 | 0/1 | 0.0% (0.0% to 79.3%) | -66.0 points | -8.75 | 1/1 (100.0%; 20.7% to 100.0%) | anxiety or panic: 1/1 (100.0%); other reported effect: 1/1 (100.0%); activation or irritability: 1/1 (100.0%) | too sparse for inference |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| 10 to <25 mg | 1 | inf | 1.0000 | n/a | 0.00 | 1.0000 | n/a |
| 50 to <100 mg | 2 | 0.00 | 1.0000 | n/a | inf | 1.0000 | n/a |

#### Administration route

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| multiple route families | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +34.0 points | 4.17 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | descriptive only; multiple reported values |
| oral mucosal | 5 | 2/5 | 40.0% (11.8% to 76.9%) | -26.0 points | -3.59 | 4/5 (80.0%; 37.6% to 96.4%) | other reported effect: 3/5 (60.0%); cognitive or perceptual disturbance: 2/5 (40.0%); anxiety or panic: 2/5 (40.0%) | too sparse for inference |
| swallowed oral | 2 | 1/2 | 50.0% (9.5% to 90.5%) | -16.0 points | -2.29 | 1/2 (50.0%; 9.5% to 90.5%) | depressed or flattened mood: 1/2 (50.0%); other reported effect: 1/2 (50.0%); insomnia or sleep disruption: 1/2 (50.0%) | too sparse for inference |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| multiple route families | 7 | inf | 1.0000 | n/a | 0.00 | 0.3750 | n/a |
| oral mucosal | 2 | 0.67 | 1.0000 | n/a | 4.00 | 1.0000 | n/a |
| swallowed oral | 5 | 1.50 | 1.0000 | n/a | 0.25 | 1.0000 | n/a |

#### Explicit reason for use

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| anxiety or stress | 3 | 3/3 | 100.0% (43.8% to 100.0%) | +34.0 points | 4.17 | 0/3 (0.0%; 0.0% to 56.2%) | none mapped | too sparse for inference |
| cognition or brain fog | 3 | 3/3 | 100.0% (43.8% to 100.0%) | +34.0 points | 4.17 | 2/3 (66.7%; 20.8% to 93.9%) | insomnia or sleep disruption: 2/3 (66.7%); fatigue or sedation: 1/3 (33.3%) | too sparse for inference |
| energy or motivation | 8 | 7/8 | 87.5% (52.9% to 97.8%) | +21.5 points | 2.55 | 3/8 (37.5%; 13.7% to 69.4%) | other reported effect: 1/8 (12.5%); headache or migraine: 1/8 (12.5%); fatigue or sedation: 1/8 (12.5%) | too sparse for inference |
| focus or attention | 6 | 6/6 | 100.0% (61.0% to 100.0%) | +34.0 points | 4.17 | 1/6 (16.7%; 3.0% to 56.4%) | other reported effect: 1/6 (16.7%) | too sparse for inference |
| memory or learning | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +34.0 points | 4.17 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | too sparse for inference |
| mood or depression | 14 | 13/14 | 92.9% (68.5% to 98.7%) | +26.9 points | 3.24 | 3/14 (21.4%; 7.6% to 47.6%) | other reported effect: 2/14 (14.3%); headache or migraine: 1/14 (7.1%); fatigue or sedation: 1/14 (7.1%) | estimable association; not causal |
| neuroprotection or recovery | 3 | 3/3 | 100.0% (43.8% to 100.0%) | +34.0 points | 4.17 | 1/3 (33.3%; 6.1% to 79.2%) | insomnia or sleep disruption: 1/3 (33.3%) | too sparse for inference |
| stimulant recovery or reduction | 4 | 4/4 | 100.0% (51.0% to 100.0%) | +34.0 points | 4.17 | 2/4 (50.0%; 15.0% to 85.0%) | other reported effect: 1/4 (25.0%); hair loss or thinning: 1/4 (25.0%); insomnia or sleep disruption: 1/4 (25.0%) | too sparse for inference |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| anxiety or stress | 22 | inf | 1.0000 | n/a | 0.00 | 0.5270 | n/a |
| cognition or brain fog | 22 | inf | 1.0000 | n/a | 5.33 | 0.2313 | n/a |
| energy or motivation | 17 | 0.44 | 1.0000 | n/a | 1.44 | 1.0000 | n/a |
| focus or attention | 19 | inf | 1.0000 | n/a | 0.34 | 0.6237 | n/a |
| memory or learning | 24 | inf | 1.0000 | n/a | 0.00 | 1.0000 | n/a |
| mood or depression | 11 | 1.30 | 1.0000 | 1.0000 | 0.33 | 0.3892 | 0.3892 |
| neuroprotection or recovery | 22 | inf | 1.0000 | n/a | 1.07 | 1.0000 | n/a |
| stimulant recovery or reduction | 21 | inf | 1.0000 | n/a | 2.50 | 0.5700 | n/a |

### r/depressionregimens

7,8-DHF has 8 classified authors and a raw positive share of 87.5%. The leave-target-out comparator mean uses 5 compounds and is 66.9%.

#### Dosage

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| <5 mg | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +33.1 points | 4.73 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | too sparse for inference |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| <5 mg | 0 | n/a | n/a | n/a | n/a | n/a | n/a |

#### Administration route

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| swallowed oral | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +33.1 points | 4.73 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | too sparse for inference |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| swallowed oral | 0 | n/a | n/a | n/a | n/a | n/a | n/a |

#### Explicit reason for use

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| mood or depression | 2 | 2/2 | 100.0% (34.2% to 100.0%) | +33.1 points | 4.73 | 0/2 (0.0%; 0.0% to 65.8%) | none mapped | too sparse for inference |
| neuroprotection or recovery | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +33.1 points | 4.73 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | too sparse for inference |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| mood or depression | 1 | n/a | 1.0000 | n/a | n/a | 1.0000 | n/a |
| neuroprotection or recovery | 2 | n/a | 1.0000 | n/a | n/a | 1.0000 | n/a |

### r/StackAdvice

7,8-DHF has 61 classified authors and a raw positive share of 73.8%. The leave-target-out comparator mean uses 9 compounds and is 74.0%.

#### Dosage

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| 10 to <25 mg | 5 | 4/5 | 80.0% (37.6% to 96.4%) | +6.0 points | 2.20 | 1/5 (20.0%; 3.6% to 62.4%) | other reported effect: 1/5 (20.0%) | too sparse for inference |
| 25 to <50 mg | 3 | 3/3 | 100.0% (43.8% to 100.0%) | +26.0 points | 3.76 | 0/3 (0.0%; 0.0% to 56.2%) | none mapped | too sparse for inference |
| 50 to <100 mg | 1 | 0/1 | 0.0% (0.0% to 79.3%) | -74.0 points | -11.88 | 1/1 (100.0%; 20.7% to 100.0%) | activation or irritability: 1/1 (100.0%); other reported effect: 1/1 (100.0%); headache or migraine: 1/1 (100.0%) | too sparse for inference |
| >=100 mg | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +26.0 points | 3.76 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | too sparse for inference |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| 10 to <25 mg | 5 | 1.00 | 1.0000 | n/a | 1.00 | 1.0000 | n/a |
| 25 to <50 mg | 7 | inf | 1.0000 | n/a | 0.00 | 1.0000 | n/a |
| 50 to <100 mg | 9 | 0.00 | 0.2000 | n/a | inf | 0.2000 | n/a |
| >=100 mg | 9 | inf | 1.0000 | n/a | 0.00 | 1.0000 | n/a |

#### Administration route

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| multiple route families | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +26.0 points | 3.76 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | descriptive only; multiple reported values |
| oral mucosal | 2 | 1/2 | 50.0% (9.5% to 90.5%) | -24.0 points | -0.15 | 0/2 (0.0%; 0.0% to 65.8%) | none mapped | too sparse for inference |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| multiple route families | 2 | inf | 1.0000 | n/a | n/a | 1.0000 | n/a |
| oral mucosal | 0 | n/a | n/a | n/a | n/a | n/a | n/a |

#### Explicit reason for use

| Level | Authors | Positive | Positive share | Versus compound mean | Sentiment z | Any side effect | Leading mapped effects | Status |
|---|---|---|---|---|---|---|---|---|
| anxiety or stress | 3 | 3/3 | 100.0% (43.8% to 100.0%) | +26.0 points | 3.76 | 0/3 (0.0%; 0.0% to 56.2%) | none mapped | too sparse for inference |
| cardiovascular or autonomic | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +26.0 points | 3.76 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | too sparse for inference |
| cognition or brain fog | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +26.0 points | 3.76 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | too sparse for inference |
| energy or motivation | 3 | 3/3 | 100.0% (43.8% to 100.0%) | +26.0 points | 3.76 | 1/3 (33.3%; 6.1% to 79.2%) | other reported effect: 1/3 (33.3%) | too sparse for inference |
| focus or attention | 2 | 2/2 | 100.0% (34.2% to 100.0%) | +26.0 points | 3.76 | 2/2 (100.0%; 34.2% to 100.0%) | hair loss or thinning: 1/2 (50.0%); other reported effect: 1/2 (50.0%) | too sparse for inference |
| memory or learning | 2 | 2/2 | 100.0% (34.2% to 100.0%) | +26.0 points | 3.76 | 1/2 (50.0%; 9.5% to 90.5%) | other reported effect: 1/2 (50.0%) | too sparse for inference |
| mood or depression | 4 | 4/4 | 100.0% (51.0% to 100.0%) | +26.0 points | 3.76 | 1/4 (25.0%; 4.6% to 69.9%) | other reported effect: 1/4 (25.0%) | too sparse for inference |
| neuroprotection or recovery | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +26.0 points | 3.76 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | too sparse for inference |
| other explicit reason | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +26.0 points | 3.76 | 1/1 (100.0%; 20.7% to 100.0%) | hair loss or thinning: 1/1 (100.0%) | too sparse for inference |
| pain or neurologic symptoms | 2 | 1/2 | 50.0% (9.5% to 90.5%) | -24.0 points | -4.06 | 1/2 (50.0%; 9.5% to 90.5%) | other reported effect: 1/2 (50.0%) | too sparse for inference |
| sleep or wakefulness | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +26.0 points | 3.76 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | too sparse for inference |
| stimulant recovery or reduction | 1 | 1/1 | 100.0% (20.7% to 100.0%) | +26.0 points | 3.76 | 0/1 (0.0%; 0.0% to 79.3%) | none mapped | too sparse for inference |

Contrast each level with all other eligible levels for that predictor. Reason levels are multi-label, so the comparison is reason present versus reason absent among authors with at least one explicit reason.

| Level | Other eligible authors | Positive OR | Positive p | Positive BH q | Side-effect OR | Side-effect p | Side-effect BH q |
|---|---|---|---|---|---|---|---|
| anxiety or stress | 9 | inf | 1.0000 | n/a | 0.00 | 1.0000 | n/a |
| cardiovascular or autonomic | 11 | inf | 1.0000 | n/a | 0.00 | 1.0000 | n/a |
| cognition or brain fog | 11 | inf | 1.0000 | n/a | 0.00 | 1.0000 | n/a |
| energy or motivation | 9 | inf | 1.0000 | n/a | 4.00 | 0.4545 | n/a |
| focus or attention | 10 | inf | 1.0000 | n/a | inf | 0.0152 | n/a |
| memory or learning | 10 | inf | 1.0000 | n/a | 9.00 | 0.3182 | n/a |
| mood or depression | 8 | inf | 1.0000 | n/a | 2.33 | 1.0000 | n/a |
| neuroprotection or recovery | 11 | inf | 1.0000 | n/a | 0.00 | 1.0000 | n/a |
| other explicit reason | 11 | inf | 1.0000 | n/a | inf | 0.1667 | n/a |
| pain or neurologic symptoms | 10 | 0.00 | 0.1667 | n/a | 9.00 | 0.3182 | n/a |
| sleep or wakefulness | 11 | inf | 1.0000 | n/a | 0.00 | 1.0000 | n/a |
| stimulant recovery or reduction | 11 | inf | 1.0000 | n/a | 0.00 | 1.0000 | n/a |

### r/Longevity

No 7,8-DHF author-level outcome is available for this cohort.

#### Dosage

No eligible 7,8-DHF authors had this predictor extracted.

#### Administration route

No eligible 7,8-DHF authors had this predictor extracted.

#### Explicit reason for use

No eligible 7,8-DHF authors had this predictor extracted.

### r/Psilocybin

No 7,8-DHF author-level outcome is available for this cohort.

#### Dosage

No eligible 7,8-DHF authors had this predictor extracted.

#### Administration route

No eligible 7,8-DHF authors had this predictor extracted.

#### Explicit reason for use

No eligible 7,8-DHF authors had this predictor extracted.

## Interpretation boundaries

Dose and route values are included only when the value and 7,8-DHF were found near each other in the same source segment, but the author-level sentiment and side-effect outcomes may come from another report by that author. Multi-band and multi-route histories are descriptive only. Reasons are multi-label. Concomitant drugs, formulation, duration, year, community selection, indication severity, and reporting behavior can confound every association. Sparse rows should not be interpreted inferentially.

## Reproducibility

Generated at `2026-09-02T18:19:47.345822+00:00`. Dose, route, sentiment, and side-effect inputs are the external combined databases from the completed subreddit runs. Reason records and their model provenance remain external. No record-level text or author identifier is included.

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

| Reason artifact | SHA-256 |
|---|---|
| reason_records.jsonl | 82d482bd4dc13b77a6425c069df16bebfa9432f512e5b801f6d196683bb00701 |
| reason_manifest.json | 2e07e7c31ec25918e799ad492da79ad22ed040fadbfbd1c1490c1861a172e4b5 |

Reason extraction: provider `openrouter`; model `deepseek/deepseek-v4-flash`; code commit `3b7fab953529e1276cd364aaaa74011400309df1`; prompt `78dhf_reason_v1.txt` with SHA-256 `0ed9dd3f320ac664e09e37e6cc1e38c6f61662f4efb2ec19d7227fddf6f5548f`; 6,000 input characters per author cohort; 2,048 output-token ceiling; batch size 6; completed 833/833 author cohorts; 165 with an explicit reason; 437,765 provider-reported tokens; completed at `2026-09-02T18:19:20.052935+00:00`.
