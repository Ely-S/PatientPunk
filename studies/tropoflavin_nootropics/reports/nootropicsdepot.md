# 7,8-DHF comparator-cohort analysis: r/NootropicsDepot

This report answers the OMF collaboration questions with aggregate r/NootropicsDepot self-reports. It measures reporting patterns, not efficacy, adverse-event incidence, causal dose-response, or medical safety. Every comparator uses the same source population, classifier, context handling, and one-vote-per-author rule.

## Extraction coverage and recall checks

The retention column compares retained classified authors with authors found by deterministic alias matching. It is a recall proxy, not gold-standard sensitivity, because model eligibility and alias matching are different measurement stages.

| Compound | Alias-matched items | Alias-matched authors | Reports | Classified authors | Observed retention | Sample warning |
|---|---|---|---|---|---|---|
| 7,8-DHF | 1666 | 585 | 829 | 348 | 59.5% | adequate for description |
| 4'-DMA-7,8-DHF | 294 | 153 | 240 | 133 | 86.9% | adequate for description |
| Semax | 320 | 187 | 90 | 54 | 28.9% | adequate for description |
| Cerebrolysin | 202 | 104 | 48 | 19 | 18.3% | adequate for description |
| Selank | 141 | 97 | 28 | 19 | 19.6% | adequate for description |
| NSI-189 | 54 | 42 | 16 | 11 | 26.2% | adequate for description |
| Dihexa | 35 | 30 | 5 | 5 | 16.7% | too sparse for inference |
| Lion's mane | 4243 | 1391 | 1664 | 702 | 50.5% | adequate for description |
| 9-MBC | 19 | 13 | 9 | 8 | 61.5% | too sparse for inference |
| BPC-157 | 195 | 139 | 60 | 45 | 32.4% | adequate for description |

Pipeline B produced 896 records from 896 selected authors (100.0%) and 35,538 source segments.

OpenRouter models: sentiment `deepseek/deepseek-v4-flash` / `deepseek/deepseek-v4-flash`; variables `deepseek/deepseek-v4-flash`. Provider-reported token totals: sentiment 7,561,361; variables 10,465,016. Text caps were 1,500 upstream characters and 8,000 Pipeline B characters, with a 32,768-token Pipeline B output ceiling.

Source SHA-256 values: comments `edb06537c89e3c91fddf8f03febd3f0a8b937aa903e725cc808d830f2af931e9`; posts `f4b1bda6740bc8f422c8e507928a3c9024e5162855f2b2fa06d7b8e237ac9b8f`. Code commits: sentiment `cb6c35576b37ba36773b4fbd5963c186c06f85d9`; variables `eadb46d6763c1ba4d6d9ef3871625be38ce6e0bf`.

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
| 7,8-DHF | target | target | 348 | 259 | 82 | 7 | 0 | 74.4% | 69.6% to 78.7% | descriptive only |
| 4'-DMA-7,8-DHF | chemical analogue | primary | 133 | 100 | 27 | 6 | 0 | 75.2% | 67.2% to 81.8% | descriptive only |
| Semax | BDNF/TrkB related | primary | 54 | 38 | 16 | 0 | 0 | 70.4% | 57.2% to 80.9% | descriptive only |
| Cerebrolysin | BDNF/TrkB related | primary | 19 | 17 | 1 | 0 | 1 | 89.5% | 68.6% to 97.1% | descriptive only |
| Selank | BDNF/TrkB related | primary | 19 | 15 | 3 | 1 | 0 | 78.9% | 56.7% to 91.5% | descriptive only |
| NSI-189 | broader neurotrophic | secondary | 11 | 10 | 1 | 0 | 0 | 90.9% | 62.3% to 98.4% | descriptive only |
| Dihexa | broader neurotrophic | secondary | 5 | 2 | 2 | 1 | 0 | 40.0% | 11.8% to 76.9% | too sparse for inference |
| Lion's mane | broader neurotrophic | secondary | 702 | 447 | 224 | 27 | 4 | 63.7% | 60.1% to 67.1% | descriptive only |
| 9-MBC | broader neurotrophic | exploratory | 8 | 3 | 5 | 0 | 0 | 37.5% | 13.7% to 69.4% | too sparse for inference |
| BPC-157 | negative control | control | 45 | 32 | 11 | 2 | 0 | 71.1% | 56.6% to 82.3% | descriptive only |

## Comparisons with 7,8-DHF

The positive-rate difference is 7,8-DHF minus comparator, so positive values favor a higher 7,8-DHF positive-reporting share. Fisher tests use mutually exclusive authors and report 7,8-DHF/comparator odds ratios. BH q-values are corrected across comparators. Matched results use authors who reported both compounds; the discordant column is 7,8-DHF-only positive / comparator-only positive. Matched q-values are corrected separately.

| Comparator | 7,8-DHF minus comparator | Exclusive OR | Exclusive p | Exclusive BH q | Exclusive 7,8-DHF authors | Exclusive comparator authors | Matched authors | Discordant | Matched p | Matched BH q | Inference status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4'-DMA-7,8-DHF | -0.8 points | 1.05 | 0.8496 | 0.8496 | 254 | 39 | 94 | 10/8 | 0.8145 | 1.0000 | sensitivity analysis |
| Semax | +4.1 points | 1.13 | 0.8402 | 0.8496 | 329 | 35 | 19 | 4/1 | 0.3750 | 1.0000 | sensitivity analysis |
| Cerebrolysin | -15.0 points | 0.52 | 0.5281 | 0.8496 | 342 | 13 | 6 | 0/0 | n/a | n/a | sensitivity analysis |
| Selank | -4.5 points | 0.67 | 0.7697 | 0.8496 | 345 | 16 | 3 | 0/0 | n/a | n/a | sensitivity analysis |
| NSI-189 | -16.5 points | 0.41 | 0.6852 | 0.8496 | 345 | 8 | 3 | 0/0 | n/a | n/a | too sparse for inference |
| Dihexa | +34.4 points | 5.78 | 0.1677 | 0.5031 | 346 | 3 | 2 | 1/0 | 1.0000 | 1.0000 | too sparse for inference |
| Lion's mane | +10.8 points | 1.59 | 0.0068 | 0.0611 | 234 | 588 | 114 | 31/15 | 0.0259 | 0.2331 | sensitivity analysis |
| 9-MBC | +36.9 points | 3.92 | 0.0780 | 0.3510 | 347 | 7 | 1 | 0/0 | n/a | n/a | too sparse for inference |
| BPC-157 | +3.3 points | 1.30 | 0.4480 | 0.8496 | 342 | 39 | 6 | 1/2 | 1.0000 | 1.0000 | sensitivity analysis |

## Treatment-linked side-effect signals

These are the eight most frequently reported canonical effects per compound, deduplicated by author within each effect. Because every pipeline row is linked to one target treatment, the former 7,8-DHF / 4'-DMA blending is removed. Counts remain reporting proportions, not incidence.

| Compound | Canonical effect | Safety domain | Authors | Share of classified authors | Mentions |
|---|---|---|---|---|---|
| 7,8-DHF | other reported effect | other | 61 | 17.5% | 118 |
| 7,8-DHF | insomnia or sleep disruption | sleep | 60 | 17.2% | 92 |
| 7,8-DHF | activation or irritability | activation or anxiety | 17 | 4.9% | 24 |
| 7,8-DHF | headache or migraine | neurologic | 15 | 4.3% | 15 |
| 7,8-DHF | fatigue or sedation | fatigue or sedation | 10 | 2.9% | 11 |
| 7,8-DHF | anxiety or panic | activation or anxiety | 8 | 2.3% | 9 |
| 7,8-DHF | cognitive or perceptual disturbance | neurologic | 7 | 2.0% | 7 |
| 7,8-DHF | crash or rebound | activation or anxiety | 4 | 1.1% | 5 |
| 4'-DMA-7,8-DHF | other reported effect | other | 27 | 20.3% | 35 |
| 4'-DMA-7,8-DHF | insomnia or sleep disruption | sleep | 22 | 16.5% | 33 |
| 4'-DMA-7,8-DHF | activation or irritability | activation or anxiety | 7 | 5.3% | 9 |
| 4'-DMA-7,8-DHF | cognitive or perceptual disturbance | neurologic | 6 | 4.5% | 6 |
| 4'-DMA-7,8-DHF | anxiety or panic | activation or anxiety | 5 | 3.8% | 5 |
| 4'-DMA-7,8-DHF | fatigue or sedation | fatigue or sedation | 5 | 3.8% | 8 |
| 4'-DMA-7,8-DHF | headache or migraine | neurologic | 3 | 2.3% | 3 |
| 4'-DMA-7,8-DHF | depressed or flattened mood | mood | 2 | 1.5% | 2 |
| Semax | other reported effect | other | 8 | 14.8% | 10 |
| Semax | insomnia or sleep disruption | sleep | 4 | 7.4% | 4 |
| Semax | hair loss or thinning | hair or skin | 3 | 5.6% | 6 |
| Semax | cognitive or perceptual disturbance | neurologic | 2 | 3.7% | 2 |
| Semax | fatigue or sedation | fatigue or sedation | 2 | 3.7% | 2 |
| Semax | headache or migraine | neurologic | 2 | 3.7% | 2 |
| Semax | anxiety or panic | activation or anxiety | 1 | 1.9% | 1 |
| Semax | local irritation or odor | local irritation | 1 | 1.9% | 1 |
| Selank | cognitive or perceptual disturbance | neurologic | 1 | 5.3% | 1 |
| Selank | fatigue or sedation | fatigue or sedation | 1 | 5.3% | 1 |
| Selank | headache or migraine | neurologic | 1 | 5.3% | 1 |
| Selank | other reported effect | other | 1 | 5.3% | 1 |
| Selank | sexual | sexual | 1 | 5.3% | 1 |
| NSI-189 | other reported effect | other | 1 | 9.1% | 3 |
| Dihexa | other reported effect | other | 4 | 80.0% | 7 |
| Dihexa | cognitive or perceptual disturbance | neurologic | 1 | 20.0% | 1 |
| Lion's mane | other reported effect | other | 171 | 24.4% | 334 |
| Lion's mane | insomnia or sleep disruption | sleep | 67 | 9.5% | 90 |
| Lion's mane | sexual | sexual | 67 | 9.5% | 104 |
| Lion's mane | depressed or flattened mood | mood | 50 | 7.1% | 76 |
| Lion's mane | fatigue or sedation | fatigue or sedation | 30 | 4.3% | 36 |
| Lion's mane | anxiety or panic | activation or anxiety | 28 | 4.0% | 33 |
| Lion's mane | headache or migraine | neurologic | 24 | 3.4% | 40 |
| Lion's mane | cognitive or perceptual disturbance | neurologic | 23 | 3.3% | 30 |
| 9-MBC | other reported effect | other | 4 | 50.0% | 6 |
| 9-MBC | anxiety or panic | activation or anxiety | 1 | 12.5% | 1 |
| 9-MBC | depressed or flattened mood | mood | 1 | 12.5% | 2 |
| 9-MBC | fatigue or sedation | fatigue or sedation | 1 | 12.5% | 1 |
| 9-MBC | insomnia or sleep disruption | sleep | 1 | 12.5% | 1 |
| BPC-157 | other reported effect | other | 10 | 22.2% | 14 |
| BPC-157 | depressed or flattened mood | mood | 4 | 8.9% | 6 |

## Post-level compound, dose, and outcome links

This stricter view keeps only treatment-specific sentiment reports where exactly one quantitative mass dose appears near that compound in the same post or comment. Authors receive one vote per compound and dose band. It is descriptive and does not establish a dose-response relationship.

| Compound | Dose band | Posts | Authors | Positive authors | Side-effect authors | Inference status |
|---|---|---|---|---|---|---|
| 4'-DMA-7,8-DHF | 5 to <10 mg | 2 | 2 | 2/2 (100.0%) | 1/2 (50.0%) | too sparse for inference |
| 4'-DMA-7,8-DHF | 10 to <25 mg | 4 | 3 | 3/3 (100.0%) | 0/3 (0.0%) | too sparse for inference |
| 4'-DMA-7,8-DHF | 50 to <100 mg | 1 | 1 | 1/1 (100.0%) | 1/1 (100.0%) | too sparse for inference |
| 4'-DMA-7,8-DHF | >=100 mg | 2 | 2 | 2/2 (100.0%) | 0/2 (0.0%) | too sparse for inference |
| 7,8-DHF | 5 to <10 mg | 6 | 6 | 5/6 (83.3%) | 2/6 (33.3%) | too sparse for inference |
| 7,8-DHF | 10 to <25 mg | 6 | 6 | 5/6 (83.3%) | 1/6 (16.7%) | too sparse for inference |
| 7,8-DHF | 25 to <50 mg | 15 | 13 | 11/13 (84.6%) | 4/13 (30.8%) | descriptive only |
| 7,8-DHF | 50 to <100 mg | 3 | 3 | 3/3 (100.0%) | 1/3 (33.3%) | too sparse for inference |
| 7,8-DHF | >=100 mg | 16 | 14 | 13/14 (92.9%) | 2/14 (14.3%) | descriptive only |
| BPC-157 | <5 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| BPC-157 | 5 to <10 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| BPC-157 | >=100 mg | 2 | 2 | 1/2 (50.0%) | 1/2 (50.0%) | too sparse for inference |
| Lion's mane | <5 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Lion's mane | 5 to <10 mg | 2 | 2 | 2/2 (100.0%) | 0/2 (0.0%) | too sparse for inference |
| Lion's mane | 10 to <25 mg | 1 | 1 | 0/1 (0.0%) | 1/1 (100.0%) | too sparse for inference |
| Lion's mane | >=100 mg | 66 | 59 | 42/59 (71.2%) | 20/59 (33.9%) | descriptive only |
| NSI-189 | 25 to <50 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Selank | <5 mg | 6 | 4 | 3/4 (75.0%) | 1/4 (25.0%) | too sparse for inference |
| Selank | 5 to <10 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Semax | <5 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Semax | 10 to <25 mg | 3 | 2 | 2/2 (100.0%) | 0/2 (0.0%) | too sparse for inference |
| Semax | >=100 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |

## Dose and route attribution checks

| Field | Status | Rows |
|---|---|---|
| Dose | corroborated | 129 |
| Dose | unsupported | 99 |
| Route | corroborated | 83 |
| Route | unsupported | 46 |

## Dose-stratified side-effect reporting

Side-effect reporting is joined by hashed author and compound across all of that author's reports. The denominator is every distinct author in the dose or route bucket. Classifier coverage shows how many denominator authors also had a retained comparator report. These are cross-report associations, not administration-event links, incidence estimates, or dose-response evidence. Dose and route rows are included only when the extracted value and compound were found near each other in the same source segment.

| Compound | Dose band | Observations | Authors | Classifier coverage | Any side effect | Leading mapped effects |
|---|---|---|---|---|---|---|
| 4'-DMA | 5 to <10 mg | 4 | 4 | 4/4 | 1/4 (25.0%; 95% CI 4.6% to 69.9%) | cognitive or perceptual disturbance: 1/4 (25.0%); fatigue or sedation: 1/4 (25.0%); insomnia or sleep disruption: 1/4 (25.0%) |
| 4'-DMA | 10 to <25 mg | 6 | 5 | 5/5 | 1/5 (20.0%; 95% CI 3.6% to 62.4%) | depressed or flattened mood: 1/5 (20.0%); insomnia or sleep disruption: 1/5 (20.0%) |
| 7,8-DHF | 5 to <10 mg | 3 | 3 | 3/3 | 2/3 (66.7%; 95% CI 20.8% to 93.9%) | activation or irritability: 2/3 (66.7%); anxiety or panic: 1/3 (33.3%); insomnia or sleep disruption: 1/3 (33.3%) |
| 7,8-DHF | 10 to <25 mg | 7 | 6 | 5/6 | 2/6 (33.3%; 95% CI 9.7% to 70.0%) | activation or irritability: 1/6 (16.7%); anxiety or panic: 1/6 (16.7%); insomnia or sleep disruption: 1/6 (16.7%) |
| 7,8-DHF | 25 to <50 mg | 15 | 15 | 15/15 | 10/15 (66.7%; 95% CI 41.7% to 84.8%) | insomnia or sleep disruption: 5/15 (33.3%); activation or irritability: 2/15 (13.3%); headache or migraine: 2/15 (13.3%) |
| 7,8-DHF | 50 to <100 mg | 8 | 8 | 6/8 | 2/8 (25.0%; 95% CI 7.1% to 59.1%) | activation or irritability: 1/8 (12.5%); anxiety or panic: 1/8 (12.5%); insomnia or sleep disruption: 1/8 (12.5%) |
| 7,8-DHF | >=100 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| 9-MBC | 10 to <25 mg | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | none mapped |
| BPC-157 | <5 mg | 2 | 2 | 2/2 | 0/2 (0.0%; 95% CI 0.0% to 65.8%) | none mapped |
| Lion's mane | <5 mg | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | none mapped |
| Lion's mane | 50 to <100 mg | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | muscle cramps: 1/1 (100.0%) |
| Lion's mane | >=100 mg | 73 | 61 | 59/61 | 31/61 (50.8%; 95% CI 38.6% to 62.9%) | sexual: 10/61 (16.4%); insomnia or sleep disruption: 9/61 (14.8%); activation or irritability: 5/61 (8.2%) |
| Selank | <5 mg | 4 | 3 | 3/3 | 2/3 (66.7%; 95% CI 20.8% to 93.9%) | cognitive or perceptual disturbance: 1/3 (33.3%); fatigue or sedation: 1/3 (33.3%); headache or migraine: 1/3 (33.3%) |
| Semax | <5 mg | 3 | 3 | 3/3 | 1/3 (33.3%; 95% CI 6.1% to 79.2%) | insomnia or sleep disruption: 1/3 (33.3%) |

## Route-stratified side-effect reporting

Side-effect reporting is joined by hashed author and compound across all of that author's reports. The denominator is every distinct author in the dose or route bucket. Classifier coverage shows how many denominator authors also had a retained comparator report. These are cross-report associations, not administration-event links, incidence estimates, or dose-response evidence. Dose and route rows are included only when the extracted value and compound were found near each other in the same source segment.

| Compound | Route family | Observations | Authors | Classifier coverage | Any side effect | Leading mapped effects |
|---|---|---|---|---|---|---|
| 4'-DMA | oral mucosal | 5 | 5 | 4/5 | 2/5 (40.0%; 95% CI 11.8% to 76.9%) | activation or irritability: 1/5 (20.0%); cognitive or perceptual disturbance: 1/5 (20.0%); depressed or flattened mood: 1/5 (20.0%) |
| 4'-DMA | swallowed oral | 3 | 3 | 3/3 | 2/3 (66.7%; 95% CI 20.8% to 93.9%) | insomnia or sleep disruption: 2/3 (66.7%); cognitive or perceptual disturbance: 1/3 (33.3%); fatigue or sedation: 1/3 (33.3%) |
| 7,8-DHF | nasal mucosal | 2 | 2 | 2/2 | 0/2 (0.0%; 95% CI 0.0% to 65.8%) | none mapped |
| 7,8-DHF | oral mucosal | 27 | 27 | 26/27 | 14/27 (51.9%; 95% CI 34.0% to 69.3%) | insomnia or sleep disruption: 8/27 (29.6%); activation or irritability: 3/27 (11.1%); anxiety or panic: 1/27 (3.7%) |
| 7,8-DHF | swallowed oral | 13 | 12 | 10/12 | 6/12 (50.0%; 95% CI 25.4% to 74.6%) | insomnia or sleep disruption: 4/12 (33.3%); anxiety or panic: 1/12 (8.3%); headache or migraine: 1/12 (8.3%) |
| BPC-157 | nasal mucosal | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | none mapped |
| BPC-157 | parenteral | 4 | 4 | 4/4 | 1/4 (25.0%; 95% CI 4.6% to 69.9%) | depressed or flattened mood: 1/4 (25.0%) |
| BPC-157 | swallowed oral | 5 | 5 | 5/5 | 2/5 (40.0%; 95% CI 11.8% to 76.9%) | depressed or flattened mood: 1/5 (20.0%) |
| Cerebrolysin | parenteral | 3 | 3 | 1/3 | 0/3 (0.0%; 95% CI 0.0% to 56.2%) | none mapped |
| Lion's mane | oral mucosal | 2 | 2 | 2/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | anxiety or panic: 1/2 (50.0%); cognitive or perceptual disturbance: 1/2 (50.0%); depressed or flattened mood: 1/2 (50.0%) |
| Lion's mane | swallowed oral | 8 | 7 | 6/7 | 3/7 (42.9%; 95% CI 15.8% to 75.0%) | sexual: 2/7 (28.6%); activation or irritability: 1/7 (14.3%); gastrointestinal: 1/7 (14.3%) |
| Selank | nasal mucosal | 4 | 4 | 3/4 | 1/4 (25.0%; 95% CI 4.6% to 69.9%) | cognitive or perceptual disturbance: 1/4 (25.0%); fatigue or sedation: 1/4 (25.0%); headache or migraine: 1/4 (25.0%) |
| Selank | swallowed oral | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Semax | nasal mucosal | 3 | 3 | 2/3 | 0/3 (0.0%; 95% CI 0.0% to 56.2%) | none mapped |
| Semax | parenteral | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Semax | swallowed oral | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |

## Symptom-linked outcomes

Explicit PEM target coverage: 0 treatment-linked outcome entries. General fatigue remains a separate endpoint bucket.

| Compound | Target symptom | Authors | Helped | No effect | Worsened |
|---|---|---|---|---|---|
| 4'-DMA | focus or attention | 13 | 13 | 0 | 0 |
| 4'-DMA | mood or depression | 13 | 13 | 0 | 1 |
| 4'-DMA | cognition or brain fog | 10 | 7 | 0 | 3 |
| 4'-DMA | other specified result | 10 | 9 | 0 | 4 |
| 4'-DMA | energy or motivation | 9 | 10 | 0 | 0 |
| 4'-DMA | anxiety or stress | 8 | 8 | 0 | 1 |
| 4'-DMA | memory or learning | 6 | 6 | 0 | 0 |
| 4'-DMA | sleep or wakefulness | 5 | 1 | 0 | 4 |
| 4'-DMA | general fatigue | 2 | 0 | 0 | 2 |
| 4'-DMA | cardiovascular or autonomic | 1 | 1 | 0 | 0 |
| 4'-DMA | pain or neurologic symptoms | 1 | 0 | 0 | 1 |
| 7,8-DHF | mood or depression | 26 | 25 | 0 | 3 |
| 7,8-DHF | other specified result | 22 | 19 | 1 | 7 |
| 7,8-DHF | anxiety or stress | 12 | 12 | 1 | 0 |
| 7,8-DHF | sleep or wakefulness | 11 | 3 | 0 | 9 |
| 7,8-DHF | focus or attention | 10 | 10 | 2 | 0 |
| 7,8-DHF | memory or learning | 9 | 8 | 2 | 0 |
| 7,8-DHF | cognition or brain fog | 8 | 6 | 0 | 2 |
| 7,8-DHF | energy or motivation | 8 | 8 | 0 | 0 |
| 7,8-DHF | pain or neurologic symptoms | 4 | 0 | 1 | 3 |
| 7,8-DHF | general fatigue | 3 | 1 | 0 | 2 |
| 7,8-DHF | cardiovascular or autonomic | 1 | 0 | 0 | 1 |
| 7,8-DHF | neuroprotection or recovery | 1 | 1 | 0 | 0 |
| BPC-157 | other specified result | 9 | 6 | 2 | 1 |
| BPC-157 | gastrointestinal | 3 | 3 | 0 | 0 |
| BPC-157 | mood or depression | 3 | 0 | 0 | 4 |
| BPC-157 | pain or neurologic symptoms | 2 | 2 | 1 | 0 |
| BPC-157 | sleep or wakefulness | 2 | 2 | 0 | 0 |
| BPC-157 | focus or attention | 1 | 1 | 0 | 0 |
| BPC-157 | hair or skin | 1 | 1 | 0 | 0 |
| Cerebrolysin | cognition or brain fog | 2 | 2 | 0 | 0 |
| Cerebrolysin | energy or motivation | 2 | 2 | 0 | 0 |
| Cerebrolysin | mood or depression | 2 | 3 | 0 | 0 |
| Cerebrolysin | neuroprotection or recovery | 2 | 2 | 0 | 0 |
| Cerebrolysin | other specified result | 2 | 2 | 0 | 0 |
| Cerebrolysin | anxiety or stress | 1 | 1 | 0 | 0 |
| Cerebrolysin | pain or neurologic symptoms | 1 | 1 | 0 | 0 |
| Cerebrolysin | sexual function | 1 | 1 | 0 | 0 |
| Cerebrolysin | sleep or wakefulness | 1 | 1 | 0 | 0 |
| Dihexa | other specified result | 1 | 0 | 0 | 1 |
| Lion's mane | other specified result | 84 | 37 | 1 | 51 |
| Lion's mane | cognition or brain fog | 56 | 41 | 1 | 8 |
| Lion's mane | mood or depression | 56 | 23 | 0 | 30 |
| Lion's mane | memory or learning | 54 | 46 | 3 | 2 |
| Lion's mane | sexual function | 51 | 10 | 3 | 34 |
| Lion's mane | anxiety or stress | 34 | 21 | 1 | 12 |
| Lion's mane | focus or attention | 30 | 28 | 0 | 2 |
| Lion's mane | sleep or wakefulness | 30 | 9 | 0 | 16 |
| Lion's mane | pain or neurologic symptoms | 24 | 6 | 0 | 19 |
| Lion's mane | energy or motivation | 20 | 14 | 1 | 5 |
| Lion's mane | general fatigue | 11 | 3 | 0 | 8 |
| Lion's mane | gastrointestinal | 5 | 1 | 1 | 4 |
| Lion's mane | neuroprotection or recovery | 3 | 3 | 0 | 0 |
| Lion's mane | social functioning | 3 | 3 | 0 | 0 |
| Lion's mane | hair or skin | 2 | 1 | 0 | 1 |
| NSI-189 | mood or depression | 2 | 2 | 0 | 0 |
| NSI-189 | other specified result | 2 | 3 | 0 | 0 |
| NSI-189 | anxiety or stress | 1 | 1 | 0 | 0 |
| NSI-189 | pain or neurologic symptoms | 1 | 0 | 0 | 1 |
| Selank | anxiety or stress | 7 | 8 | 0 | 0 |
| Selank | mood or depression | 4 | 5 | 0 | 0 |
| Selank | other specified result | 3 | 2 | 0 | 1 |
| Selank | cognition or brain fog | 2 | 1 | 0 | 1 |
| Selank | pain or neurologic symptoms | 2 | 1 | 0 | 1 |
| Selank | general fatigue | 1 | 0 | 0 | 1 |
| Selank | memory or learning | 1 | 1 | 0 | 0 |
| Selank | sexual function | 1 | 0 | 0 | 1 |
| Selank | sleep or wakefulness | 1 | 0 | 0 | 1 |
| Semax | other specified result | 6 | 2 | 0 | 4 |
| Semax | mood or depression | 5 | 4 | 0 | 1 |
| Semax | sleep or wakefulness | 3 | 0 | 0 | 3 |
| Semax | cognition or brain fog | 2 | 2 | 0 | 0 |
| Semax | energy or motivation | 2 | 3 | 0 | 0 |
| Semax | hair or skin | 2 | 0 | 0 | 2 |
| Semax | anxiety or stress | 1 | 0 | 0 | 1 |
| Semax | focus or attention | 1 | 1 | 0 | 0 |
| Semax | general fatigue | 1 | 0 | 0 | 1 |

## Interpretation boundaries

- Keep 7,8-DHF and 4'-DMA-7,8-DHF separate.
- Treat PEM as distinct from general fatigue when it is explicitly stated.
- Do not infer that dose, route, outcome, and side effect belong to one administration event unless the source explicitly links them.
- Use matched-author results as a sensitivity analysis, not as the primary estimand, because overlap can be sparse.
- The direct TrkB-agonist interpretation of 7,8-DHF remains disputed; the cohort is tiered rather than presented as one homogeneous mechanism class.

## Reproducibility

- Sentiment database: `sentiment.db`; SHA-256 `ad41435c6415187f15ff703b3534aa93aa70f21cbca5abd5a623ce07ae6ec476`
- Study database: `combined.db`; SHA-256 `9967720039935e1fa855fe1cdaf9f9ae123362b10e9653effdd781f49d343a7b`
- Cohort configuration: `comparator_cohort.json`; SHA-256 `c420e12d450b0b2637983121cd1db06c56c62e9567e002fb257f01887cfc8063`
