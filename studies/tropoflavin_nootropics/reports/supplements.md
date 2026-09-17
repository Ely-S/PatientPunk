# 7,8-DHF comparator-cohort analysis: r/Supplements

This report answers the OMF collaboration questions with aggregate r/Supplements self-reports. It measures reporting patterns, not efficacy, adverse-event incidence, causal dose-response, or medical safety. Every comparator uses the same source population, classifier, context handling, and one-vote-per-author rule.

## Extraction coverage and recall checks

The retention column compares retained classified authors with authors found by deterministic alias matching. It is a recall proxy, not gold-standard sensitivity, because model eligibility and alias matching are different measurement stages.

| Compound | Alias-matched items | Alias-matched authors | Reports | Classified authors | Observed retention | Sample warning |
|---|---|---|---|---|---|---|
| 7,8-DHF | 126 | 84 | 43 | 31 | 36.9% | adequate for description |
| 4'-DMA-7,8-DHF | 18 | 17 | 7 | 7 | 41.2% | too sparse for inference |
| Semax | 82 | 66 | 21 | 19 | 28.8% | adequate for description |
| Cerebrolysin | 83 | 60 | 9 | 8 | 13.3% | too sparse for inference |
| Selank | 42 | 37 | 7 | 6 | 16.2% | too sparse for inference |
| NSI-189 | 59 | 46 | 12 | 9 | 19.6% | too sparse for inference |
| Dihexa | 7 | 6 | 0 | 0 | 0.0% | too sparse for inference |
| Lion's mane | 9468 | 5628 | 3676 | 2424 | 43.1% | adequate for description |
| 9-MBC | 6 | 6 | 1 | 1 | 16.7% | too sparse for inference |
| BPC-157 | 195 | 172 | 60 | 49 | 28.5% | adequate for description |

Pipeline B produced 2,038 records from 2,038 selected authors (100.0%) and 28,078 source segments.

OpenRouter models: sentiment `deepseek/deepseek-v4-flash` / `deepseek/deepseek-v4-flash`; variables `deepseek/deepseek-v4-flash`. Provider-reported token totals: sentiment 10,023,425; variables 8,018,335. Text caps were 1,500 upstream characters and 8,000 Pipeline B characters, with a 16,384-token Pipeline B output ceiling.

Source SHA-256 values: comments `32865a4a04367e1af2841839d734a430cb2d1080e66ef4a94358a26833584d61`; posts `b2cee5f818f20ef6dd0ebb61c64257bdbf9d0524a8280718000ee80f88c8a0ce`. Code commits: sentiment `eadb46d6763c1ba4d6d9ef3871625be38ce6e0bf`; variables `eadb46d6763c1ba4d6d9ef3871625be38ce6e0bf`.

## Comparator definitions

| Compound | Tier | Role | Mechanistic rationale |
|---|---|---|---|
| 7,8-DHF | target | target | Parent flavone and putative BDNF/TrkB-modulating compound |
| 4'-DMA-7,8-DHF | chemical analogue | primary | Closest chemical derivative and primary analogue comparison |
| Semax | BDNF/TrkB related | primary | Peptide reported to alter BDNF and TrkB expression in preclinical work |
| Cerebrolysin | BDNF/TrkB related | primary | Neurotrophic peptide mixture with pathway evidence that varies by model |
| Selank | BDNF/TrkB related | primary | Peptide comparator with indirect neurotrophic-pathway rationale |
| NSI-189 | broader neurotrophic | secondary | Proneurogenic comparator without assuming direct TrkB agonism |
| Dihexa | broader neurotrophic | secondary | HGF/c-Met neurotrophic comparator with a distinct proximal mechanism |
| Lion's mane | broader neurotrophic | secondary | Heterogeneous mushroom and erinacine product class used as an indirect neurotrophic comparator |
| 9-MBC | broader neurotrophic | exploratory | Lower-volume exploratory neurorestorative comparator |
| BPC-157 | negative control | control | Same adjacent peptide/nootropic market without a BDNF/TrkB cohort claim |

## Author-level sentiment

| Compound | Tier | Role | Users | Positive | Negative | Mixed | Neutral | Positive share | 95% Wilson CI | Inference status |
|---|---|---|---|---|---|---|---|---|---|---|
| 7,8-DHF | target | target | 31 | 24 | 6 | 1 | 0 | 77.4% | 60.2% to 88.6% | descriptive only |
| 4'-DMA-7,8-DHF | chemical analogue | primary | 7 | 6 | 1 | 0 | 0 | 85.7% | 48.7% to 97.4% | too sparse for inference |
| Semax | BDNF/TrkB related | primary | 19 | 12 | 7 | 0 | 0 | 63.2% | 41.0% to 80.9% | descriptive only |
| Cerebrolysin | BDNF/TrkB related | primary | 8 | 8 | 0 | 0 | 0 | 100.0% | 67.6% to 100.0% | too sparse for inference |
| Selank | BDNF/TrkB related | primary | 6 | 5 | 1 | 0 | 0 | 83.3% | 43.6% to 97.0% | too sparse for inference |
| NSI-189 | broader neurotrophic | secondary | 9 | 8 | 1 | 0 | 0 | 88.9% | 56.5% to 98.0% | too sparse for inference |
| Dihexa | broader neurotrophic | secondary | 0 | 0 | 0 | 0 | 0 | 0.0% | 0.0% to 0.0% | too sparse for inference |
| Lion's mane | broader neurotrophic | secondary | 2424 | 1581 | 770 | 73 | 0 | 65.2% | 63.3% to 67.1% | descriptive only |
| 9-MBC | broader neurotrophic | exploratory | 1 | 1 | 0 | 0 | 0 | 100.0% | 20.7% to 100.0% | too sparse for inference |
| BPC-157 | negative control | control | 49 | 42 | 7 | 0 | 0 | 85.7% | 73.3% to 92.9% | descriptive only |

## Comparisons with 7,8-DHF

The positive-rate difference is 7,8-DHF minus comparator, so positive values favor a higher 7,8-DHF positive-reporting share. Fisher tests use mutually exclusive authors and report 7,8-DHF/comparator odds ratios. BH q-values are corrected across comparators. Matched results use authors who reported both compounds; the discordant column is 7,8-DHF-only positive / comparator-only positive. Matched q-values are corrected separately.

| Comparator | 7,8-DHF minus comparator | Exclusive OR | Exclusive p | Exclusive BH q | Exclusive 7,8-DHF authors | Exclusive comparator authors | Matched authors | Discordant | Matched p | Matched BH q | Inference status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4'-DMA-7,8-DHF | -8.3 points | 0.00 | 1.0000 | 1.0000 | 26 | 2 | 5 | 0/0 | n/a | n/a | too sparse for inference |
| Semax | +14.3 points | 2.20 | 0.3215 | 0.8481 | 29 | 17 | 2 | 0/0 | n/a | n/a | sensitivity analysis |
| Cerebrolysin | -22.6 points | 0.00 | 0.3077 | 0.8481 | 31 | 8 | 0 | 0/0 | n/a | n/a | too sparse for inference |
| Selank | -5.9 points | 0.69 | 1.0000 | 1.0000 | 31 | 6 | 0 | 0/0 | n/a | n/a | too sparse for inference |
| NSI-189 | -11.5 points | 0.43 | 0.6553 | 1.0000 | 31 | 9 | 0 | 0/0 | n/a | n/a | too sparse for inference |
| Dihexa | +77.4 points | nan | 1.0000 | 1.0000 | 31 | 0 | 0 | 0/0 | n/a | n/a | too sparse for inference |
| Lion's mane | +12.2 points | 1.82 | 0.2694 | 0.8481 | 22 | 2415 | 9 | 2/2 | 1.0000 | 1.0000 | sensitivity analysis |
| 9-MBC | -22.6 points | 0.00 | 1.0000 | 1.0000 | 31 | 1 | 0 | 0/0 | n/a | n/a | too sparse for inference |
| BPC-157 | -8.3 points | 0.57 | 0.3769 | 0.8481 | 31 | 49 | 0 | 0/0 | n/a | n/a | sensitivity analysis |

## Treatment-linked side-effect signals

These are the eight most frequently reported canonical effects per compound, deduplicated by author within each effect. Because every pipeline row is linked to one target treatment, the former 7,8-DHF / 4'-DMA blending is removed. Counts remain reporting proportions, not incidence.

| Compound | Canonical effect | Safety domain | Authors | Share of classified authors | Mentions |
|---|---|---|---|---|---|
| 7,8-DHF | other reported effect | other | 8 | 25.8% | 17 |
| 7,8-DHF | activation or irritability | activation or anxiety | 2 | 6.5% | 4 |
| 7,8-DHF | anxiety or panic | activation or anxiety | 2 | 6.5% | 2 |
| 7,8-DHF | depressed or flattened mood | mood | 2 | 6.5% | 3 |
| 7,8-DHF | insomnia or sleep disruption | sleep | 2 | 6.5% | 5 |
| 7,8-DHF | gastrointestinal | gastrointestinal | 1 | 3.2% | 1 |
| 4'-DMA-7,8-DHF | other reported effect | other | 2 | 28.6% | 2 |
| Semax | activation or irritability | activation or anxiety | 2 | 10.5% | 2 |
| Semax | fatigue or sedation | fatigue or sedation | 2 | 10.5% | 2 |
| Semax | insomnia or sleep disruption | sleep | 2 | 10.5% | 2 |
| Semax | other reported effect | other | 2 | 10.5% | 3 |
| Semax | anxiety or panic | activation or anxiety | 1 | 5.3% | 1 |
| Semax | headache or migraine | neurologic | 1 | 5.3% | 1 |
| Cerebrolysin | cognitive or perceptual disturbance | neurologic | 1 | 12.5% | 1 |
| Cerebrolysin | other reported effect | other | 1 | 12.5% | 1 |
| NSI-189 | other reported effect | other | 1 | 11.1% | 1 |
| Lion's mane | other reported effect | other | 492 | 20.3% | 855 |
| Lion's mane | sexual | sexual | 124 | 5.1% | 189 |
| Lion's mane | insomnia or sleep disruption | sleep | 114 | 4.7% | 138 |
| Lion's mane | anxiety or panic | activation or anxiety | 97 | 4.0% | 132 |
| Lion's mane | cognitive or perceptual disturbance | neurologic | 74 | 3.1% | 90 |
| Lion's mane | depressed or flattened mood | mood | 67 | 2.8% | 90 |
| Lion's mane | fatigue or sedation | fatigue or sedation | 44 | 1.8% | 49 |
| Lion's mane | headache or migraine | neurologic | 42 | 1.7% | 51 |
| BPC-157 | other reported effect | other | 2 | 4.1% | 2 |

## Post-level compound, dose, and outcome links

This stricter view keeps only treatment-specific sentiment reports where exactly one quantitative mass dose appears near that compound in the same post or comment. Authors receive one vote per compound and dose band. It is descriptive and does not establish a dose-response relationship.

| Compound | Dose band | Posts | Authors | Positive authors | Side-effect authors | Inference status |
|---|---|---|---|---|---|---|
| 7,8-DHF | <5 mg | 1 | 1 | 1/1 (100.0%) | 1/1 (100.0%) | too sparse for inference |
| 7,8-DHF | 10 to <25 mg | 2 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| 7,8-DHF | 25 to <50 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| BPC-157 | <5 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| BPC-157 | >=100 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Lion's mane | <5 mg | 10 | 10 | 6/10 (60.0%) | 3/10 (30.0%) | descriptive only |
| Lion's mane | 5 to <10 mg | 2 | 2 | 1/2 (50.0%) | 1/2 (50.0%) | too sparse for inference |
| Lion's mane | 10 to <25 mg | 3 | 3 | 2/3 (66.7%) | 1/3 (33.3%) | too sparse for inference |
| Lion's mane | 25 to <50 mg | 2 | 2 | 2/2 (100.0%) | 0/2 (0.0%) | too sparse for inference |
| Lion's mane | 50 to <100 mg | 4 | 4 | 4/4 (100.0%) | 0/4 (0.0%) | too sparse for inference |
| Lion's mane | >=100 mg | 147 | 137 | 102/137 (74.5%) | 33/137 (24.1%) | descriptive only |
| NSI-189 | 50 to <100 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Selank | >=100 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Semax | >=100 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |

## Dose and route attribution checks

| Field | Status | Rows |
|---|---|---|
| Dose | corroborated | 168 |
| Dose | unsupported | 98 |
| Route | corroborated | 22 |
| Route | unsupported | 61 |

## Dose-stratified side-effect reporting

Side-effect reporting is joined by hashed author and compound across all of that author's reports. The denominator is every distinct author in the dose or route bucket. Classifier coverage shows how many denominator authors also had a retained comparator report. These are cross-report associations, not administration-event links, incidence estimates, or dose-response evidence. Dose and route rows are included only when the extracted value and compound were found near each other in the same source segment.

| Compound | Dose band | Observations | Authors | Classifier coverage | Any side effect | Leading mapped effects |
|---|---|---|---|---|---|---|
| 7,8-DHF | <5 mg | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | activation or irritability: 1/1 (100.0%); anxiety or panic: 1/1 (100.0%); insomnia or sleep disruption: 1/1 (100.0%) |
| 7,8-DHF | 10 to <25 mg | 2 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | none mapped |
| BPC-157 | <5 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| BPC-157 | >=100 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Lion's mane | <5 mg | 2 | 2 | 2/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | gastrointestinal: 1/2 (50.0%) |
| Lion's mane | 50 to <100 mg | 2 | 2 | 2/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | anxiety or panic: 1/2 (50.0%); cognitive or perceptual disturbance: 1/2 (50.0%) |
| Lion's mane | >=100 mg | 159 | 147 | 147/147 | 45/147 (30.6%; 95% CI 23.7% to 38.5%) | insomnia or sleep disruption: 11/147 (7.5%); anxiety or panic: 8/147 (5.4%); cognitive or perceptual disturbance: 8/147 (5.4%) |

## Route-stratified side-effect reporting

Side-effect reporting is joined by hashed author and compound across all of that author's reports. The denominator is every distinct author in the dose or route bucket. Classifier coverage shows how many denominator authors also had a retained comparator report. These are cross-report associations, not administration-event links, incidence estimates, or dose-response evidence. Dose and route rows are included only when the extracted value and compound were found near each other in the same source segment.

| Compound | Route family | Observations | Authors | Classifier coverage | Any side effect | Leading mapped effects |
|---|---|---|---|---|---|---|
| 7,8-DHF | oral mucosal | 2 | 2 | 2/2 | 2/2 (100.0%; 95% CI 34.2% to 100.0%) | activation or irritability: 1/2 (50.0%); anxiety or panic: 1/2 (50.0%); insomnia or sleep disruption: 1/2 (50.0%) |
| BPC-157 | oral mucosal | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| BPC-157 | swallowed oral | 4 | 4 | 4/4 | 0/4 (0.0%; 95% CI 0.0% to 49.0%) | none mapped |
| Cerebrolysin | parenteral | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Lion's mane | swallowed oral | 12 | 12 | 12/12 | 5/12 (41.7%; 95% CI 19.3% to 68.0%) | insomnia or sleep disruption: 2/12 (16.7%); anxiety or panic: 1/12 (8.3%); cognitive or perceptual disturbance: 1/12 (8.3%) |
| Selank | nasal mucosal | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Semax | nasal mucosal | 1 | 1 | 0/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |

## Symptom-linked outcomes

Explicit PEM target coverage: 0 treatment-linked outcome entries. General fatigue remains a separate endpoint bucket.

| Compound | Target symptom | Authors | Helped | No effect | Worsened |
|---|---|---|---|---|---|
| 4'-DMA | mood or depression | 2 | 2 | 0 | 0 |
| 4'-DMA | memory or learning | 1 | 1 | 0 | 0 |
| 4'-DMA | other specified result | 1 | 1 | 0 | 0 |
| 7,8-DHF | mood or depression | 5 | 3 | 1 | 3 |
| 7,8-DHF | focus or attention | 3 | 3 | 0 | 0 |
| 7,8-DHF | cognition or brain fog | 2 | 2 | 0 | 0 |
| 7,8-DHF | energy or motivation | 2 | 3 | 0 | 0 |
| 7,8-DHF | other specified result | 2 | 1 | 0 | 1 |
| 7,8-DHF | anxiety or stress | 1 | 0 | 0 | 1 |
| 7,8-DHF | memory or learning | 1 | 1 | 0 | 0 |
| 7,8-DHF | pain or neurologic symptoms | 1 | 1 | 0 | 0 |
| 7,8-DHF | sleep or wakefulness | 1 | 0 | 0 | 1 |
| BPC-157 | other specified result | 7 | 8 | 0 | 1 |
| BPC-157 | pain or neurologic symptoms | 5 | 6 | 0 | 0 |
| BPC-157 | gastrointestinal | 3 | 3 | 0 | 0 |
| BPC-157 | anxiety or stress | 1 | 2 | 0 | 0 |
| BPC-157 | energy or motivation | 1 | 1 | 0 | 0 |
| BPC-157 | mood or depression | 1 | 1 | 0 | 0 |
| BPC-157 | neuroprotection or recovery | 1 | 1 | 0 | 0 |
| BPC-157 | sleep or wakefulness | 1 | 1 | 0 | 0 |
| Cerebrolysin | cognition or brain fog | 1 | 1 | 0 | 0 |
| Lion's mane | other specified result | 248 | 138 | 0 | 150 |
| Lion's mane | cognition or brain fog | 202 | 186 | 7 | 12 |
| Lion's mane | focus or attention | 150 | 144 | 6 | 3 |
| Lion's mane | memory or learning | 116 | 112 | 4 | 4 |
| Lion's mane | mood or depression | 115 | 75 | 3 | 42 |
| Lion's mane | anxiety or stress | 96 | 46 | 2 | 51 |
| Lion's mane | energy or motivation | 70 | 58 | 2 | 14 |
| Lion's mane | sexual function | 69 | 7 | 3 | 62 |
| Lion's mane | sleep or wakefulness | 64 | 27 | 1 | 34 |
| Lion's mane | pain or neurologic symptoms | 53 | 16 | 0 | 37 |
| Lion's mane | general fatigue | 25 | 8 | 0 | 17 |
| Lion's mane | gastrointestinal | 10 | 1 | 0 | 9 |
| Lion's mane | cardiovascular or autonomic | 9 | 0 | 0 | 9 |
| Lion's mane | hair or skin | 8 | 0 | 0 | 7 |
| Lion's mane | social functioning | 3 | 3 | 0 | 0 |
| Lion's mane | neuroprotection or recovery | 2 | 1 | 0 | 1 |
| NSI-189 | mood or depression | 3 | 2 | 0 | 0 |
| NSI-189 | focus or attention | 1 | 1 | 0 | 0 |
| NSI-189 | memory or learning | 1 | 1 | 0 | 0 |
| Selank | anxiety or stress | 1 | 1 | 0 | 0 |
| Semax | cognition or brain fog | 2 | 2 | 0 | 0 |
| Semax | other specified result | 1 | 0 | 0 | 1 |

## Interpretation boundaries

- Keep 7,8-DHF and 4'-DMA-7,8-DHF separate.
- Treat PEM as distinct from general fatigue when it is explicitly stated.
- Do not infer that dose, route, outcome, and side effect belong to one administration event unless the source explicitly links them.
- Use matched-author results as a sensitivity analysis, not as the primary estimand, because overlap can be sparse.
- The direct TrkB-agonist interpretation of 7,8-DHF remains disputed; the cohort is tiered rather than presented as one homogeneous mechanism class.

## Reproducibility

- Sentiment database: `sentiment.db`; SHA-256 `b2d6ca3e8b14444918798c2ce2769b5627689ebcbe73fefeb3b87c9add8558b3`
- Study database: `combined.db`; SHA-256 `9d49ad9ec26ff0eb751743e426df88e9bde5462a6f637c7961acfa10d706b393`
- Cohort configuration: `comparator_cohort.json`; SHA-256 `c420e12d450b0b2637983121cd1db06c56c62e9567e002fb257f01887cfc8063`
