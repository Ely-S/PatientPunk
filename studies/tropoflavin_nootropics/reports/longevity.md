# 7,8-DHF comparator-cohort analysis: r/Longevity

This report answers the OMF collaboration questions with aggregate r/Longevity self-reports. It measures reporting patterns, not efficacy, adverse-event incidence, causal dose-response, or medical safety. Every comparator uses the same source population, classifier, context handling, and one-vote-per-author rule.

## Extraction coverage and recall checks

The retention column compares retained classified authors with authors found by deterministic alias matching. It is a recall proxy, not gold-standard sensitivity, because model eligibility and alias matching are different measurement stages.

| Compound | Alias-matched items | Alias-matched authors | Reports | Classified authors | Observed retention | Sample warning |
|---|---|---|---|---|---|---|
| 7,8-DHF | 2 | 2 | 0 | 0 | 0.0% | too sparse for inference |
| 4'-DMA-7,8-DHF | 0 | 0 | 0 | 0 | n/a | too sparse for inference |
| Semax | 3 | 2 | 0 | 0 | 0.0% | too sparse for inference |
| Cerebrolysin | 6 | 6 | 0 | 0 | 0.0% | too sparse for inference |
| Selank | 0 | 0 | 0 | 0 | n/a | too sparse for inference |
| NSI-189 | 3 | 3 | 0 | 0 | 0.0% | too sparse for inference |
| Dihexa | 0 | 0 | 0 | 0 | n/a | too sparse for inference |
| Lion's mane | 32 | 22 | 2 | 2 | 9.1% | too sparse for inference |
| 9-MBC | 0 | 0 | 0 | 0 | n/a | too sparse for inference |
| BPC-157 | 28 | 27 | 3 | 3 | 11.1% | too sparse for inference |

Pipeline B produced 5 records from 5 selected authors (100.0%) and 30 source segments.

OpenRouter models: sentiment `deepseek/deepseek-v4-flash` / `deepseek/deepseek-v4-flash`; variables `deepseek/deepseek-v4-flash`. Provider-reported token totals: sentiment 37,946; variables 14,909. Text caps were 1,500 upstream characters and 8,000 Pipeline B characters, with a 8,192-token Pipeline B output ceiling.

Source SHA-256 values: comments `7e2f5f2c46f4bdf074a19554036035739c3e0ed43cb00c6255adafc07ff33de0`; posts `2da3b8ac1e029d96c76a405b0d9e637c58c6d25283afc421d7d5f0f68e4b7beb`. Code commits: sentiment `9ad1e13ea997918fd02da9f857829e437105e1a3`; variables `060f4251e7b5ec5ab4081d4b496a9060729827f6`.

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
| 7,8-DHF | target | target | 0 | 0 | 0 | 0 | 0 | 0.0% | 0.0% to 0.0% | too sparse for inference |
| 4'-DMA-7,8-DHF | chemical analogue | primary | 0 | 0 | 0 | 0 | 0 | 0.0% | 0.0% to 0.0% | too sparse for inference |
| Semax | BDNF/TrkB related | primary | 0 | 0 | 0 | 0 | 0 | 0.0% | 0.0% to 0.0% | too sparse for inference |
| Cerebrolysin | BDNF/TrkB related | primary | 0 | 0 | 0 | 0 | 0 | 0.0% | 0.0% to 0.0% | too sparse for inference |
| Selank | BDNF/TrkB related | primary | 0 | 0 | 0 | 0 | 0 | 0.0% | 0.0% to 0.0% | too sparse for inference |
| NSI-189 | broader neurotrophic | secondary | 0 | 0 | 0 | 0 | 0 | 0.0% | 0.0% to 0.0% | too sparse for inference |
| Dihexa | broader neurotrophic | secondary | 0 | 0 | 0 | 0 | 0 | 0.0% | 0.0% to 0.0% | too sparse for inference |
| Lion's mane | broader neurotrophic | secondary | 2 | 1 | 1 | 0 | 0 | 50.0% | 9.5% to 90.5% | too sparse for inference |
| 9-MBC | broader neurotrophic | exploratory | 0 | 0 | 0 | 0 | 0 | 0.0% | 0.0% to 0.0% | too sparse for inference |
| BPC-157 | negative control | control | 3 | 2 | 1 | 0 | 0 | 66.7% | 20.8% to 93.9% | too sparse for inference |

## Comparisons with 7,8-DHF

The positive-rate difference is 7,8-DHF minus comparator, so positive values favor a higher 7,8-DHF positive-reporting share. Fisher tests use mutually exclusive authors and report 7,8-DHF/comparator odds ratios. BH q-values are corrected across comparators. Matched results use authors who reported both compounds; the discordant column is 7,8-DHF-only positive / comparator-only positive. Matched q-values are corrected separately.

| Comparator | 7,8-DHF minus comparator | Exclusive OR | Exclusive p | Exclusive BH q | Exclusive 7,8-DHF authors | Exclusive comparator authors | Matched authors | Discordant | Matched p | Matched BH q | Inference status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4'-DMA-7,8-DHF | +0.0 points | nan | 1.0000 | 1.0000 | 0 | 0 | 0 | 0/0 | n/a | n/a | too sparse for inference |
| Semax | +0.0 points | nan | 1.0000 | 1.0000 | 0 | 0 | 0 | 0/0 | n/a | n/a | too sparse for inference |
| Cerebrolysin | +0.0 points | nan | 1.0000 | 1.0000 | 0 | 0 | 0 | 0/0 | n/a | n/a | too sparse for inference |
| Selank | +0.0 points | nan | 1.0000 | 1.0000 | 0 | 0 | 0 | 0/0 | n/a | n/a | too sparse for inference |
| NSI-189 | +0.0 points | nan | 1.0000 | 1.0000 | 0 | 0 | 0 | 0/0 | n/a | n/a | too sparse for inference |
| Dihexa | +0.0 points | nan | 1.0000 | 1.0000 | 0 | 0 | 0 | 0/0 | n/a | n/a | too sparse for inference |
| Lion's mane | -50.0 points | nan | 1.0000 | 1.0000 | 0 | 2 | 0 | 0/0 | n/a | n/a | too sparse for inference |
| 9-MBC | +0.0 points | nan | 1.0000 | 1.0000 | 0 | 0 | 0 | 0/0 | n/a | n/a | too sparse for inference |
| BPC-157 | -66.7 points | nan | 1.0000 | 1.0000 | 0 | 3 | 0 | 0/0 | n/a | n/a | too sparse for inference |

## Treatment-linked side-effect signals

These are the eight most frequently reported canonical effects per compound, deduplicated by author within each effect. Because every pipeline row is linked to one target treatment, the former 7,8-DHF / 4'-DMA blending is removed. Counts remain reporting proportions, not incidence.

| Compound | Canonical effect | Safety domain | Authors | Share of classified authors | Mentions |
|---|---|---|---|---|---|
| Lion's mane | headache or migraine | neurologic | 1 | 50.0% | 1 |

## Post-level compound, dose, and outcome links

This stricter view keeps only treatment-specific sentiment reports where exactly one quantitative mass dose appears near that compound in the same post or comment. Authors receive one vote per compound and dose band. It is descriptive and does not establish a dose-response relationship.

| Compound | Dose band | Posts | Authors | Positive authors | Side-effect authors | Inference status |
|---|---|---|---|---|---|---|
| BPC-157 | <5 mg | 1 | 1 | 0/1 (0.0%) | 0/1 (0.0%) | too sparse for inference |

## Dose and route attribution checks

| Field | Status | Rows |
|---|---|---|
| Dose | corroborated | 1 |
| Route | unsupported | 1 |

## Dose-stratified side-effect reporting

Side-effect reporting is joined by hashed author and compound across all of that author's reports. The denominator is every distinct author in the dose or route bucket. Classifier coverage shows how many denominator authors also had a retained comparator report. These are cross-report associations, not administration-event links, incidence estimates, or dose-response evidence. Dose and route rows are included only when the extracted value and compound were found near each other in the same source segment.

| Compound | Dose band | Observations | Authors | Classifier coverage | Any side effect | Leading mapped effects |
|---|---|---|---|---|---|---|
| BPC-157 | <5 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |

## Route-stratified side-effect reporting

Side-effect reporting is joined by hashed author and compound across all of that author's reports. The denominator is every distinct author in the dose or route bucket. Classifier coverage shows how many denominator authors also had a retained comparator report. These are cross-report associations, not administration-event links, incidence estimates, or dose-response evidence. Dose and route rows are included only when the extracted value and compound were found near each other in the same source segment.

| Compound | Route family | Observations | Authors | Classifier coverage | Any side effect | Leading mapped effects |
|---|---|---|---|---|---|---|

## Symptom-linked outcomes

Explicit PEM target coverage: 0 treatment-linked outcome entries. General fatigue remains a separate endpoint bucket.

| Compound | Target symptom | Authors | Helped | No effect | Worsened |
|---|---|---|---|---|---|
| BPC-157 | other specified result | 1 | 0 | 1 | 0 |
| BPC-157 | pain or neurologic symptoms | 1 | 1 | 0 | 0 |
| Lion's mane | focus or attention | 1 | 1 | 0 | 0 |
| Lion's mane | other specified result | 1 | 2 | 0 | 0 |
| Lion's mane | pain or neurologic symptoms | 1 | 0 | 0 | 1 |
| Lion's mane | sleep or wakefulness | 1 | 1 | 0 | 0 |

## Interpretation boundaries

- Keep 7,8-DHF and 4'-DMA-7,8-DHF separate.
- Treat PEM as distinct from general fatigue when it is explicitly stated.
- Do not infer that dose, route, outcome, and side effect belong to one administration event unless the source explicitly links them.
- Use matched-author results as a sensitivity analysis, not as the primary estimand, because overlap can be sparse.
- The direct TrkB-agonist interpretation of 7,8-DHF remains disputed; the cohort is tiered rather than presented as one homogeneous mechanism class.

## Reproducibility

- Sentiment database: `sentiment.db`; SHA-256 `94b8b2eaa92de97e1e462371caeaefffbb1395d0f57e4717492177b5f328234c`
- Study database: `combined.db`; SHA-256 `471515cde8a89bdda0f6adf18816222c5e73798881840560647a102cda52ecda`
- Cohort configuration: `comparator_cohort.json`; SHA-256 `c420e12d450b0b2637983121cd1db06c56c62e9567e002fb257f01887cfc8063`
