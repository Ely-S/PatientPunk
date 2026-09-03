# 7,8-DHF comparator-cohort analysis: r/StackAdvice

This report answers the OMF collaboration questions with aggregate r/StackAdvice self-reports. It measures reporting patterns, not efficacy, adverse-event incidence, causal dose-response, or medical safety. Every comparator uses the same source population, classifier, context handling, and one-vote-per-author rule.

## Extraction coverage and recall checks

The retention column compares retained classified authors with authors found by deterministic alias matching. It is a recall proxy, not gold-standard sensitivity, because model eligibility and alias matching are different measurement stages.

| Compound | Alias-matched items | Alias-matched authors | Reports | Classified authors | Observed retention | Sample warning |
|---|---|---|---|---|---|---|
| 7,8-DHF | 414 | 220 | 102 | 62 | 28.2% | adequate for description |
| 4'-DMA-7,8-DHF | 67 | 50 | 26 | 19 | 38.0% | adequate for description |
| Semax | 3437 | 1432 | 834 | 386 | 27.0% | adequate for description |
| Cerebrolysin | 809 | 438 | 107 | 80 | 18.3% | adequate for description |
| Selank | 1187 | 609 | 277 | 161 | 26.4% | adequate for description |
| NSI-189 | 1032 | 570 | 320 | 166 | 29.1% | adequate for description |
| Dihexa | 258 | 153 | 35 | 25 | 16.3% | adequate for description |
| Lion's mane | 7876 | 4060 | 2033 | 1232 | 30.3% | adequate for description |
| 9-MBC | 189 | 101 | 72 | 42 | 41.6% | adequate for description |
| BPC-157 | 1066 | 418 | 195 | 117 | 28.0% | adequate for description |

Pipeline B produced 1,790 records from 1,790 selected authors (100.0%) and 32,523 source segments.

OpenRouter models: sentiment `deepseek/deepseek-v4-flash` / `deepseek/deepseek-v4-flash`; variables `deepseek/deepseek-v4-flash`. Provider-reported token totals: sentiment 17,208,000; variables 9,289,382. Text caps were 1,500 upstream characters and 8,000 Pipeline B characters, with a 32,768-token Pipeline B output ceiling.

Source SHA-256 values: comments `251d8bb20d72f7802ea67c9af83708332a0b90899ca071f70a563f51f572f3fa`; posts `2e2d3900faed03494a94a606335982948e6f60181cbc40ec4f345258fafe37aa`. Code commits: sentiment `eadb46d6763c1ba4d6d9ef3871625be38ce6e0bf`; variables `eadb46d6763c1ba4d6d9ef3871625be38ce6e0bf`.

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
| 7,8-DHF | target | target | 62 | 46 | 12 | 1 | 3 | 74.2% | 62.1% to 83.4% | descriptive only |
| 4'-DMA-7,8-DHF | chemical analogue | primary | 19 | 16 | 2 | 1 | 0 | 84.2% | 62.4% to 94.5% | descriptive only |
| Semax | BDNF/TrkB related | primary | 386 | 289 | 81 | 16 | 0 | 74.9% | 70.3% to 78.9% | descriptive only |
| Cerebrolysin | BDNF/TrkB related | primary | 80 | 60 | 16 | 4 | 0 | 75.0% | 64.5% to 83.2% | descriptive only |
| Selank | BDNF/TrkB related | primary | 161 | 125 | 32 | 4 | 0 | 77.6% | 70.6% to 83.4% | descriptive only |
| NSI-189 | broader neurotrophic | secondary | 166 | 119 | 38 | 9 | 0 | 71.7% | 64.4% to 78.0% | descriptive only |
| Dihexa | broader neurotrophic | secondary | 25 | 19 | 5 | 1 | 0 | 76.0% | 56.6% to 88.5% | descriptive only |
| Lion's mane | broader neurotrophic | secondary | 1232 | 869 | 328 | 34 | 1 | 70.5% | 67.9% to 73.0% | descriptive only |
| 9-MBC | broader neurotrophic | exploratory | 42 | 26 | 15 | 1 | 0 | 61.9% | 46.8% to 75.0% | descriptive only |
| BPC-157 | negative control | control | 117 | 85 | 28 | 4 | 0 | 72.6% | 63.9% to 79.9% | descriptive only |

## Comparisons with 7,8-DHF

The positive-rate difference is 7,8-DHF minus comparator, so positive values favor a higher 7,8-DHF positive-reporting share. Fisher tests use mutually exclusive authors and report 7,8-DHF/comparator odds ratios. BH q-values are corrected across comparators. Matched results use authors who reported both compounds; the discordant column is 7,8-DHF-only positive / comparator-only positive. Matched q-values are corrected separately.

| Comparator | 7,8-DHF minus comparator | Exclusive OR | Exclusive p | Exclusive BH q | Exclusive 7,8-DHF authors | Exclusive comparator authors | Matched authors | Discordant | Matched p | Matched BH q | Inference status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4'-DMA-7,8-DHF | -10.0 points | 0.29 | 0.4332 | 0.9714 | 54 | 11 | 8 | 0/0 | n/a | n/a | sensitivity analysis |
| Semax | -0.7 points | 0.77 | 0.4865 | 0.9714 | 48 | 372 | 14 | 1/1 | 1.0000 | 1.0000 | sensitivity analysis |
| Cerebrolysin | -0.8 points | 0.82 | 0.6910 | 0.9714 | 59 | 77 | 3 | 2/0 | 0.5000 | 1.0000 | sensitivity analysis |
| Selank | -3.4 points | 0.77 | 0.4654 | 0.9714 | 54 | 153 | 8 | 1/1 | 1.0000 | 1.0000 | sensitivity analysis |
| NSI-189 | +2.5 points | 0.95 | 0.8634 | 0.9714 | 54 | 158 | 8 | 2/0 | 0.5000 | 1.0000 | sensitivity analysis |
| Dihexa | -1.8 points | 0.76 | 0.7812 | 0.9714 | 60 | 23 | 2 | 1/0 | 1.0000 | 1.0000 | sensitivity analysis |
| Lion's mane | +3.7 points | 0.97 | 1.0000 | 1.0000 | 47 | 1217 | 15 | 5/0 | 0.0625 | 0.5625 | sensitivity analysis |
| 9-MBC | +12.3 points | 1.70 | 0.2605 | 0.9714 | 57 | 37 | 5 | 1/0 | 1.0000 | 1.0000 | sensitivity analysis |
| BPC-157 | +1.5 points | 0.89 | 0.8529 | 0.9714 | 53 | 108 | 9 | 2/0 | 0.5000 | 1.0000 | sensitivity analysis |

## Treatment-linked side-effect signals

These are the eight most frequently reported canonical effects per compound, deduplicated by author within each effect. Because every pipeline row is linked to one target treatment, the former 7,8-DHF / 4'-DMA blending is removed. Counts remain reporting proportions, not incidence.

| Compound | Canonical effect | Safety domain | Authors | Share of classified authors | Mentions |
|---|---|---|---|---|---|
| 7,8-DHF | other reported effect | other | 10 | 16.1% | 18 |
| 7,8-DHF | insomnia or sleep disruption | sleep | 3 | 4.8% | 4 |
| 7,8-DHF | activation or irritability | activation or anxiety | 2 | 3.2% | 2 |
| 7,8-DHF | cognitive or perceptual disturbance | neurologic | 2 | 3.2% | 2 |
| 7,8-DHF | depressed or flattened mood | mood | 2 | 3.2% | 4 |
| 7,8-DHF | cardiovascular or autonomic | cardiovascular or autonomic | 1 | 1.6% | 1 |
| 7,8-DHF | dizziness or vertigo | neurologic | 1 | 1.6% | 1 |
| 7,8-DHF | gastrointestinal | gastrointestinal | 1 | 1.6% | 1 |
| 4'-DMA-7,8-DHF | insomnia or sleep disruption | sleep | 3 | 15.8% | 3 |
| 4'-DMA-7,8-DHF | activation or irritability | activation or anxiety | 1 | 5.3% | 1 |
| 4'-DMA-7,8-DHF | other reported effect | other | 1 | 5.3% | 1 |
| Semax | other reported effect | other | 52 | 13.5% | 84 |
| Semax | activation or irritability | activation or anxiety | 15 | 3.9% | 20 |
| Semax | headache or migraine | neurologic | 15 | 3.9% | 15 |
| Semax | insomnia or sleep disruption | sleep | 15 | 3.9% | 17 |
| Semax | anxiety or panic | activation or anxiety | 11 | 2.8% | 13 |
| Semax | fatigue or sedation | fatigue or sedation | 9 | 2.3% | 10 |
| Semax | cognitive or perceptual disturbance | neurologic | 5 | 1.3% | 6 |
| Semax | hair loss or thinning | hair or skin | 5 | 1.3% | 5 |
| Cerebrolysin | other reported effect | other | 7 | 8.8% | 12 |
| Cerebrolysin | cognitive or perceptual disturbance | neurologic | 3 | 3.8% | 3 |
| Cerebrolysin | activation or irritability | activation or anxiety | 1 | 1.2% | 1 |
| Cerebrolysin | anxiety or panic | activation or anxiety | 1 | 1.2% | 1 |
| Cerebrolysin | depressed or flattened mood | mood | 1 | 1.2% | 1 |
| Cerebrolysin | dizziness or vertigo | neurologic | 1 | 1.2% | 1 |
| Cerebrolysin | fatigue or sedation | fatigue or sedation | 1 | 1.2% | 1 |
| Cerebrolysin | gastrointestinal | gastrointestinal | 1 | 1.2% | 1 |
| Selank | other reported effect | other | 9 | 5.6% | 17 |
| Selank | insomnia or sleep disruption | sleep | 5 | 3.1% | 5 |
| Selank | fatigue or sedation | fatigue or sedation | 4 | 2.5% | 4 |
| Selank | headache or migraine | neurologic | 3 | 1.9% | 3 |
| Selank | cognitive or perceptual disturbance | neurologic | 2 | 1.2% | 2 |
| Selank | activation or irritability | activation or anxiety | 1 | 0.6% | 1 |
| Selank | anxiety or panic | activation or anxiety | 1 | 0.6% | 1 |
| Selank | crash or rebound | activation or anxiety | 1 | 0.6% | 1 |
| NSI-189 | other reported effect | other | 38 | 22.9% | 96 |
| NSI-189 | anxiety or panic | activation or anxiety | 18 | 10.8% | 24 |
| NSI-189 | depressed or flattened mood | mood | 7 | 4.2% | 8 |
| NSI-189 | fatigue or sedation | fatigue or sedation | 6 | 3.6% | 6 |
| NSI-189 | activation or irritability | activation or anxiety | 4 | 2.4% | 4 |
| NSI-189 | cognitive or perceptual disturbance | neurologic | 4 | 2.4% | 5 |
| NSI-189 | headache or migraine | neurologic | 4 | 2.4% | 4 |
| NSI-189 | appetite change | appetite or weight | 2 | 1.2% | 2 |
| Dihexa | other reported effect | other | 5 | 20.0% | 10 |
| Dihexa | insomnia or sleep disruption | sleep | 2 | 8.0% | 2 |
| Dihexa | activation or irritability | activation or anxiety | 1 | 4.0% | 1 |
| Dihexa | anxiety or panic | activation or anxiety | 1 | 4.0% | 1 |
| Dihexa | gastrointestinal | gastrointestinal | 1 | 4.0% | 1 |
| Dihexa | hair loss or thinning | hair or skin | 1 | 4.0% | 1 |
| Lion's mane | other reported effect | other | 190 | 15.4% | 349 |
| Lion's mane | insomnia or sleep disruption | sleep | 55 | 4.5% | 79 |
| Lion's mane | sexual | sexual | 52 | 4.2% | 57 |
| Lion's mane | cognitive or perceptual disturbance | neurologic | 42 | 3.4% | 49 |
| Lion's mane | anxiety or panic | activation or anxiety | 39 | 3.2% | 44 |
| Lion's mane | depressed or flattened mood | mood | 31 | 2.5% | 44 |
| Lion's mane | fatigue or sedation | fatigue or sedation | 26 | 2.1% | 33 |
| Lion's mane | headache or migraine | neurologic | 25 | 2.0% | 29 |
| 9-MBC | other reported effect | other | 8 | 19.0% | 37 |
| 9-MBC | sexual | sexual | 4 | 9.5% | 4 |
| 9-MBC | cognitive or perceptual disturbance | neurologic | 3 | 7.1% | 5 |
| 9-MBC | anxiety or panic | activation or anxiety | 1 | 2.4% | 1 |
| 9-MBC | cardiovascular or autonomic | cardiovascular or autonomic | 1 | 2.4% | 1 |
| 9-MBC | fatigue or sedation | fatigue or sedation | 1 | 2.4% | 1 |
| BPC-157 | other reported effect | other | 30 | 25.6% | 43 |
| BPC-157 | depressed or flattened mood | mood | 10 | 8.5% | 14 |
| BPC-157 | fatigue or sedation | fatigue or sedation | 9 | 7.7% | 11 |
| BPC-157 | anxiety or panic | activation or anxiety | 4 | 3.4% | 6 |
| BPC-157 | cognitive or perceptual disturbance | neurologic | 4 | 3.4% | 5 |
| BPC-157 | insomnia or sleep disruption | sleep | 4 | 3.4% | 5 |
| BPC-157 | headache or migraine | neurologic | 3 | 2.6% | 4 |
| BPC-157 | cardiovascular or autonomic | cardiovascular or autonomic | 2 | 1.7% | 3 |

## Post-level compound, dose, and outcome links

This stricter view keeps only treatment-specific sentiment reports where exactly one quantitative mass dose appears near that compound in the same post or comment. Authors receive one vote per compound and dose band. It is descriptive and does not establish a dose-response relationship.

| Compound | Dose band | Posts | Authors | Positive authors | Side-effect authors | Inference status |
|---|---|---|---|---|---|---|
| 4'-DMA-7,8-DHF | 25 to <50 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| 7,8-DHF | <5 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| 7,8-DHF | 10 to <25 mg | 1 | 1 | 0/1 (0.0%) | 1/1 (100.0%) | too sparse for inference |
| 7,8-DHF | 25 to <50 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| 7,8-DHF | >=100 mg | 1 | 1 | 0/1 (0.0%) | 1/1 (100.0%) | too sparse for inference |
| 9-MBC | 5 to <10 mg | 1 | 1 | 0/1 (0.0%) | 1/1 (100.0%) | too sparse for inference |
| 9-MBC | 10 to <25 mg | 3 | 3 | 1/3 (33.3%) | 1/3 (33.3%) | too sparse for inference |
| 9-MBC | 25 to <50 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| 9-MBC | >=100 mg | 2 | 2 | 2/2 (100.0%) | 0/2 (0.0%) | too sparse for inference |
| BPC-157 | <5 mg | 8 | 7 | 3/7 (42.9%) | 3/7 (42.9%) | too sparse for inference |
| BPC-157 | 5 to <10 mg | 2 | 2 | 2/2 (100.0%) | 0/2 (0.0%) | too sparse for inference |
| BPC-157 | 10 to <25 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| BPC-157 | >=100 mg | 4 | 4 | 3/4 (75.0%) | 2/4 (50.0%) | too sparse for inference |
| Cerebrolysin | <5 mg | 1 | 1 | 0/1 (0.0%) | 0/1 (0.0%) | too sparse for inference |
| Cerebrolysin | 10 to <25 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Cerebrolysin | 50 to <100 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Cerebrolysin | >=100 mg | 4 | 4 | 3/4 (75.0%) | 0/4 (0.0%) | too sparse for inference |
| Dihexa | 5 to <10 mg | 3 | 3 | 2/3 (66.7%) | 2/3 (66.7%) | too sparse for inference |
| Dihexa | 10 to <25 mg | 1 | 1 | 1/1 (100.0%) | 1/1 (100.0%) | too sparse for inference |
| Dihexa | 25 to <50 mg | 1 | 1 | 0/1 (0.0%) | 1/1 (100.0%) | too sparse for inference |
| Dihexa | >=100 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Lion's mane | <5 mg | 10 | 10 | 9/10 (90.0%) | 2/10 (20.0%) | descriptive only |
| Lion's mane | 5 to <10 mg | 3 | 3 | 3/3 (100.0%) | 1/3 (33.3%) | too sparse for inference |
| Lion's mane | 10 to <25 mg | 14 | 13 | 11/13 (84.6%) | 2/13 (15.4%) | descriptive only |
| Lion's mane | 25 to <50 mg | 5 | 5 | 4/5 (80.0%) | 1/5 (20.0%) | too sparse for inference |
| Lion's mane | 50 to <100 mg | 5 | 5 | 5/5 (100.0%) | 0/5 (0.0%) | too sparse for inference |
| Lion's mane | >=100 mg | 136 | 128 | 98/128 (76.6%) | 31/128 (24.2%) | descriptive only |
| NSI-189 | 5 to <10 mg | 1 | 1 | 0/1 (0.0%) | 0/1 (0.0%) | too sparse for inference |
| NSI-189 | 10 to <25 mg | 5 | 5 | 5/5 (100.0%) | 0/5 (0.0%) | too sparse for inference |
| NSI-189 | 25 to <50 mg | 8 | 7 | 5/7 (71.4%) | 1/7 (14.3%) | too sparse for inference |
| NSI-189 | 50 to <100 mg | 1 | 1 | 0/1 (0.0%) | 1/1 (100.0%) | too sparse for inference |
| NSI-189 | >=100 mg | 5 | 5 | 5/5 (100.0%) | 0/5 (0.0%) | too sparse for inference |
| Selank | <5 mg | 6 | 6 | 6/6 (100.0%) | 1/6 (16.7%) | too sparse for inference |
| Selank | 10 to <25 mg | 2 | 2 | 1/2 (50.0%) | 1/2 (50.0%) | too sparse for inference |
| Selank | 25 to <50 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Selank | 50 to <100 mg | 2 | 2 | 2/2 (100.0%) | 1/2 (50.0%) | too sparse for inference |
| Selank | >=100 mg | 5 | 5 | 3/5 (60.0%) | 1/5 (20.0%) | too sparse for inference |
| Semax | <5 mg | 28 | 22 | 20/22 (90.9%) | 6/22 (27.3%) | descriptive only |
| Semax | 5 to <10 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Semax | 10 to <25 mg | 5 | 5 | 4/5 (80.0%) | 1/5 (20.0%) | too sparse for inference |
| Semax | 25 to <50 mg | 3 | 2 | 1/2 (50.0%) | 0/2 (0.0%) | too sparse for inference |
| Semax | 50 to <100 mg | 2 | 2 | 1/2 (50.0%) | 0/2 (0.0%) | too sparse for inference |
| Semax | >=100 mg | 19 | 15 | 9/15 (60.0%) | 3/15 (20.0%) | descriptive only |

## Dose and route attribution checks

| Field | Status | Rows |
|---|---|---|
| Dose | corroborated | 448 |
| Dose | unsupported | 163 |
| Route | corroborated | 153 |
| Route | unsupported | 120 |

## Dose-stratified side-effect reporting

Side-effect reporting is joined by hashed author and compound across all of that author's reports. The denominator is every distinct author in the dose or route bucket. Classifier coverage shows how many denominator authors also had a retained comparator report. These are cross-report associations, not administration-event links, incidence estimates, or dose-response evidence. Dose and route rows are included only when the extracted value and compound were found near each other in the same source segment.

| Compound | Dose band | Observations | Authors | Classifier coverage | Any side effect | Leading mapped effects |
|---|---|---|---|---|---|---|
| 4'-DMA | 10 to <25 mg | 1 | 1 | 0/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| 7,8-DHF | 10 to <25 mg | 6 | 6 | 5/6 | 1/6 (16.7%; 95% CI 3.0% to 56.4%) | none mapped |
| 7,8-DHF | 25 to <50 mg | 3 | 3 | 3/3 | 0/3 (0.0%; 95% CI 0.0% to 56.2%) | none mapped |
| 7,8-DHF | 50 to <100 mg | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | activation or irritability: 1/1 (100.0%); cardiovascular or autonomic: 1/1 (100.0%); cognitive or perceptual disturbance: 1/1 (100.0%) |
| 7,8-DHF | >=100 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| 9-MBC | 5 to <10 mg | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | cognitive or perceptual disturbance: 1/1 (100.0%); sexual: 1/1 (100.0%) |
| 9-MBC | 10 to <25 mg | 6 | 5 | 4/5 | 2/5 (40.0%; 95% CI 11.8% to 76.9%) | cognitive or perceptual disturbance: 1/5 (20.0%); fatigue or sedation: 1/5 (20.0%); sexual: 1/5 (20.0%) |
| 9-MBC | 25 to <50 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| BPC-157 | <5 mg | 11 | 9 | 6/9 | 3/9 (33.3%; 95% CI 12.1% to 64.6%) | depressed or flattened mood: 2/9 (22.2%); anxiety or panic: 1/9 (11.1%); cardiovascular or autonomic: 1/9 (11.1%) |
| BPC-157 | 5 to <10 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| BPC-157 | >=100 mg | 1 | 1 | 0/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Dihexa | 5 to <10 mg | 3 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | insomnia or sleep disruption: 1/1 (100.0%) |
| Dihexa | 10 to <25 mg | 2 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Dihexa | 25 to <50 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Lion's mane | <5 mg | 3 | 3 | 3/3 | 0/3 (0.0%; 95% CI 0.0% to 56.2%) | none mapped |
| Lion's mane | 5 to <10 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Lion's mane | >=100 mg | 276 | 254 | 246/254 | 55/254 (21.7%; 95% CI 17.0% to 27.1%) | insomnia or sleep disruption: 21/254 (8.3%); headache or migraine: 10/254 (3.9%); fatigue or sedation: 8/254 (3.1%) |
| NSI-189 | 10 to <25 mg | 12 | 11 | 11/11 | 4/11 (36.4%; 95% CI 15.2% to 64.6%) | activation or irritability: 1/11 (9.1%); anxiety or panic: 1/11 (9.1%); gastrointestinal: 1/11 (9.1%) |
| NSI-189 | 25 to <50 mg | 23 | 23 | 21/23 | 7/23 (30.4%; 95% CI 15.6% to 50.9%) | anxiety or panic: 3/23 (13.0%); activation or irritability: 1/23 (4.3%); depressed or flattened mood: 1/23 (4.3%) |
| NSI-189 | 50 to <100 mg | 5 | 5 | 5/5 | 3/5 (60.0%; 95% CI 23.1% to 88.2%) | none mapped |
| NSI-189 | >=100 mg | 2 | 2 | 2/2 | 0/2 (0.0%; 95% CI 0.0% to 65.8%) | none mapped |
| Selank | <5 mg | 23 | 21 | 18/21 | 3/21 (14.3%; 95% CI 5.0% to 34.6%) | crash or rebound: 1/21 (4.8%); headache or migraine: 1/21 (4.8%); insomnia or sleep disruption: 1/21 (4.8%) |
| Selank | 10 to <25 mg | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | none mapped |
| Semax | <5 mg | 61 | 50 | 48/50 | 15/50 (30.0%; 95% CI 19.1% to 43.8%) | activation or irritability: 3/50 (6.0%); depressed or flattened mood: 3/50 (6.0%); insomnia or sleep disruption: 3/50 (6.0%) |
| Semax | 10 to <25 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Semax | >=100 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |

## Route-stratified side-effect reporting

Side-effect reporting is joined by hashed author and compound across all of that author's reports. The denominator is every distinct author in the dose or route bucket. Classifier coverage shows how many denominator authors also had a retained comparator report. These are cross-report associations, not administration-event links, incidence estimates, or dose-response evidence. Dose and route rows are included only when the extracted value and compound were found near each other in the same source segment.

| Compound | Route family | Observations | Authors | Classifier coverage | Any side effect | Leading mapped effects |
|---|---|---|---|---|---|---|
| 7,8-DHF | nasal mucosal | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| 7,8-DHF | oral mucosal | 3 | 3 | 3/3 | 0/3 (0.0%; 95% CI 0.0% to 56.2%) | none mapped |
| 7,8-DHF | swallowed oral | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| 9-MBC | oral mucosal | 2 | 2 | 2/2 | 0/2 (0.0%; 95% CI 0.0% to 65.8%) | none mapped |
| 9-MBC | swallowed oral | 2 | 2 | 2/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | cognitive or perceptual disturbance: 1/2 (50.0%); sexual: 1/2 (50.0%) |
| BPC-157 | nasal mucosal | 1 | 1 | 0/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| BPC-157 | oral mucosal | 1 | 1 | 0/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| BPC-157 | parenteral | 14 | 14 | 12/14 | 4/14 (28.6%; 95% CI 11.7% to 54.6%) | depressed or flattened mood: 3/14 (21.4%); anxiety or panic: 1/14 (7.1%); cardiovascular or autonomic: 1/14 (7.1%) |
| BPC-157 | swallowed oral | 4 | 4 | 4/4 | 1/4 (25.0%; 95% CI 4.6% to 69.9%) | cardiovascular or autonomic: 1/4 (25.0%); depressed or flattened mood: 1/4 (25.0%); insomnia or sleep disruption: 1/4 (25.0%) |
| Cerebrolysin | nasal mucosal | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Cerebrolysin | parenteral | 15 | 15 | 14/15 | 2/15 (13.3%; 95% CI 3.7% to 37.9%) | cognitive or perceptual disturbance: 1/15 (6.7%); depressed or flattened mood: 1/15 (6.7%); dizziness or vertigo: 1/15 (6.7%) |
| Dihexa | nasal mucosal | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | none mapped |
| Dihexa | parenteral | 1 | 1 | 0/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Dihexa | swallowed oral | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | activation or irritability: 1/1 (100.0%) |
| Lion's mane | swallowed oral | 4 | 4 | 4/4 | 2/4 (50.0%; 95% CI 15.0% to 85.0%) | cognitive or perceptual disturbance: 2/4 (50.0%); anxiety or panic: 1/4 (25.0%); insomnia or sleep disruption: 1/4 (25.0%) |
| NSI-189 | nasal mucosal | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | none mapped |
| NSI-189 | oral mucosal | 7 | 7 | 7/7 | 2/7 (28.6%; 95% CI 8.2% to 64.1%) | anxiety or panic: 2/7 (28.6%) |
| NSI-189 | swallowed oral | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | none mapped |
| Selank | nasal mucosal | 21 | 21 | 20/21 | 4/21 (19.0%; 95% CI 7.7% to 40.0%) | activation or irritability: 1/21 (4.8%); cognitive or perceptual disturbance: 1/21 (4.8%); headache or migraine: 1/21 (4.8%) |
| Selank | parenteral | 7 | 7 | 7/7 | 2/7 (28.6%; 95% CI 8.2% to 64.1%) | anxiety or panic: 1/7 (14.3%); insomnia or sleep disruption: 1/7 (14.3%) |
| Semax | nasal mucosal | 50 | 47 | 43/47 | 18/47 (38.3%; 95% CI 25.8% to 52.6%) | insomnia or sleep disruption: 6/47 (12.8%); activation or irritability: 3/47 (6.4%); fatigue or sedation: 3/47 (6.4%) |
| Semax | oral mucosal | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | insomnia or sleep disruption: 1/1 (100.0%) |
| Semax | parenteral | 13 | 12 | 12/12 | 3/12 (25.0%; 95% CI 8.9% to 53.2%) | insomnia or sleep disruption: 2/12 (16.7%); anxiety or panic: 1/12 (8.3%); depressed or flattened mood: 1/12 (8.3%) |

## Symptom-linked outcomes

Explicit PEM target coverage: 0 treatment-linked outcome entries. General fatigue remains a separate endpoint bucket.

| Compound | Target symptom | Authors | Helped | No effect | Worsened |
|---|---|---|---|---|---|
| 4'-DMA | mood or depression | 2 | 2 | 0 | 0 |
| 4'-DMA | other specified result | 2 | 2 | 0 | 0 |
| 4'-DMA | anxiety or stress | 1 | 1 | 0 | 0 |
| 4'-DMA | cognition or brain fog | 1 | 0 | 0 | 1 |
| 4'-DMA | energy or motivation | 1 | 2 | 0 | 0 |
| 4'-DMA | focus or attention | 1 | 1 | 0 | 1 |
| 4'-DMA | memory or learning | 1 | 1 | 0 | 0 |
| 4'-DMA | sleep or wakefulness | 1 | 0 | 0 | 1 |
| 7,8-DHF | anxiety or stress | 6 | 5 | 0 | 1 |
| 7,8-DHF | other specified result | 5 | 3 | 0 | 2 |
| 7,8-DHF | energy or motivation | 4 | 4 | 0 | 0 |
| 7,8-DHF | mood or depression | 4 | 4 | 0 | 0 |
| 7,8-DHF | sleep or wakefulness | 4 | 1 | 0 | 3 |
| 7,8-DHF | cognition or brain fog | 3 | 2 | 0 | 1 |
| 7,8-DHF | memory or learning | 3 | 3 | 0 | 0 |
| 7,8-DHF | focus or attention | 1 | 1 | 0 | 0 |
| 7,8-DHF | pain or neurologic symptoms | 1 | 0 | 0 | 1 |
| 9-MBC | mood or depression | 3 | 3 | 1 | 0 |
| 9-MBC | energy or motivation | 2 | 3 | 0 | 0 |
| 9-MBC | focus or attention | 2 | 4 | 0 | 0 |
| 9-MBC | other specified result | 2 | 1 | 1 | 0 |
| 9-MBC | anxiety or stress | 1 | 0 | 1 | 0 |
| 9-MBC | cognition or brain fog | 1 | 0 | 0 | 3 |
| 9-MBC | memory or learning | 1 | 0 | 1 | 0 |
| 9-MBC | sexual function | 1 | 0 | 0 | 1 |
| BPC-157 | other specified result | 16 | 13 | 1 | 6 |
| BPC-157 | mood or depression | 14 | 7 | 0 | 10 |
| BPC-157 | pain or neurologic symptoms | 9 | 6 | 1 | 2 |
| BPC-157 | cognition or brain fog | 6 | 4 | 0 | 2 |
| BPC-157 | sleep or wakefulness | 5 | 4 | 0 | 1 |
| BPC-157 | anxiety or stress | 3 | 3 | 0 | 2 |
| BPC-157 | gastrointestinal | 3 | 0 | 1 | 2 |
| BPC-157 | cardiovascular or autonomic | 2 | 0 | 0 | 2 |
| BPC-157 | general fatigue | 2 | 0 | 0 | 2 |
| BPC-157 | neuroprotection or recovery | 2 | 2 | 0 | 0 |
| BPC-157 | energy or motivation | 1 | 1 | 0 | 0 |
| BPC-157 | focus or attention | 1 | 0 | 1 | 0 |
| BPC-157 | memory or learning | 1 | 0 | 0 | 1 |
| Cerebrolysin | other specified result | 7 | 5 | 0 | 2 |
| Cerebrolysin | cognition or brain fog | 6 | 7 | 0 | 1 |
| Cerebrolysin | energy or motivation | 5 | 3 | 1 | 0 |
| Cerebrolysin | mood or depression | 5 | 6 | 0 | 1 |
| Cerebrolysin | anxiety or stress | 3 | 4 | 0 | 0 |
| Cerebrolysin | memory or learning | 3 | 3 | 0 | 0 |
| Cerebrolysin | focus or attention | 2 | 2 | 0 | 0 |
| Cerebrolysin | general fatigue | 2 | 2 | 0 | 0 |
| Cerebrolysin | pain or neurologic symptoms | 1 | 0 | 1 | 0 |
| Cerebrolysin | sleep or wakefulness | 1 | 1 | 0 | 0 |
| Dihexa | cognition or brain fog | 2 | 1 | 0 | 0 |
| Dihexa | memory or learning | 2 | 1 | 0 | 0 |
| Dihexa | other specified result | 2 | 1 | 0 | 1 |
| Dihexa | anxiety or stress | 1 | 1 | 0 | 0 |
| Dihexa | energy or motivation | 1 | 1 | 0 | 0 |
| Lion's mane | other specified result | 101 | 64 | 2 | 54 |
| Lion's mane | cognition or brain fog | 76 | 60 | 6 | 9 |
| Lion's mane | memory or learning | 68 | 59 | 7 | 6 |
| Lion's mane | anxiety or stress | 64 | 40 | 4 | 23 |
| Lion's mane | focus or attention | 63 | 57 | 4 | 4 |
| Lion's mane | mood or depression | 58 | 47 | 2 | 11 |
| Lion's mane | sexual function | 34 | 1 | 2 | 31 |
| Lion's mane | energy or motivation | 33 | 31 | 0 | 5 |
| Lion's mane | sleep or wakefulness | 30 | 12 | 0 | 18 |
| Lion's mane | pain or neurologic symptoms | 21 | 6 | 1 | 13 |
| Lion's mane | general fatigue | 14 | 4 | 2 | 8 |
| Lion's mane | hair or skin | 7 | 1 | 1 | 5 |
| Lion's mane | neuroprotection or recovery | 4 | 3 | 0 | 0 |
| Lion's mane | gastrointestinal | 3 | 2 | 0 | 1 |
| Lion's mane | social functioning | 3 | 3 | 0 | 0 |
| Lion's mane | cardiovascular or autonomic | 1 | 1 | 0 | 0 |
| NSI-189 | mood or depression | 41 | 34 | 1 | 4 |
| NSI-189 | other specified result | 23 | 21 | 0 | 8 |
| NSI-189 | anxiety or stress | 13 | 4 | 1 | 7 |
| NSI-189 | cognition or brain fog | 11 | 9 | 0 | 1 |
| NSI-189 | focus or attention | 10 | 8 | 0 | 2 |
| NSI-189 | memory or learning | 8 | 7 | 2 | 0 |
| NSI-189 | energy or motivation | 4 | 4 | 0 | 0 |
| NSI-189 | pain or neurologic symptoms | 3 | 0 | 0 | 3 |
| NSI-189 | social functioning | 3 | 3 | 0 | 0 |
| NSI-189 | cardiovascular or autonomic | 1 | 0 | 0 | 1 |
| NSI-189 | general fatigue | 1 | 0 | 0 | 1 |
| NSI-189 | sleep or wakefulness | 1 | 1 | 0 | 0 |
| Selank | anxiety or stress | 33 | 32 | 4 | 1 |
| Selank | other specified result | 14 | 12 | 1 | 1 |
| Selank | mood or depression | 12 | 11 | 2 | 0 |
| Selank | cognition or brain fog | 6 | 5 | 0 | 1 |
| Selank | focus or attention | 5 | 5 | 0 | 0 |
| Selank | pain or neurologic symptoms | 3 | 2 | 0 | 1 |
| Selank | energy or motivation | 1 | 1 | 0 | 0 |
| Selank | general fatigue | 1 | 0 | 0 | 1 |
| Selank | memory or learning | 1 | 1 | 0 | 0 |
| Selank | sleep or wakefulness | 1 | 1 | 0 | 0 |
| Selank | social functioning | 1 | 1 | 0 | 0 |
| Semax | other specified result | 37 | 23 | 4 | 14 |
| Semax | cognition or brain fog | 36 | 35 | 0 | 3 |
| Semax | focus or attention | 34 | 33 | 1 | 2 |
| Semax | mood or depression | 27 | 27 | 1 | 1 |
| Semax | anxiety or stress | 24 | 16 | 3 | 5 |
| Semax | energy or motivation | 13 | 16 | 0 | 0 |
| Semax | pain or neurologic symptoms | 11 | 1 | 0 | 11 |
| Semax | memory or learning | 10 | 8 | 2 | 0 |
| Semax | sleep or wakefulness | 10 | 5 | 0 | 5 |
| Semax | general fatigue | 8 | 2 | 1 | 5 |
| Semax | neuroprotection or recovery | 2 | 2 | 0 | 0 |
| Semax | hair or skin | 1 | 0 | 0 | 1 |
| Semax | social functioning | 1 | 1 | 0 | 0 |

## Interpretation boundaries

- Keep 7,8-DHF and 4'-DMA-7,8-DHF separate.
- Treat PEM as distinct from general fatigue when it is explicitly stated.
- Do not infer that dose, route, outcome, and side effect belong to one administration event unless the source explicitly links them.
- Use matched-author results as a sensitivity analysis, not as the primary estimand, because overlap can be sparse.
- The direct TrkB-agonist interpretation of 7,8-DHF remains disputed; the cohort is tiered rather than presented as one homogeneous mechanism class.

## Reproducibility

- Sentiment database: `sentiment.db`; SHA-256 `5c0bf29b8515012b1cc96c6d545b2c31d26b5fae01f13e9706e522d112bda8a2`
- Study database: `combined.db`; SHA-256 `53a3e303a4313143f1d778c079b9419f2d79b01e6671acde73354660af28d61d`
- Cohort configuration: `comparator_cohort.json`; SHA-256 `c420e12d450b0b2637983121cd1db06c56c62e9567e002fb257f01887cfc8063`
