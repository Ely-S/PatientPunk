# 7,8-DHF comparator-cohort analysis: r/Peptides

This report answers the OMF collaboration questions with aggregate r/Peptides self-reports. It measures reporting patterns, not efficacy, adverse-event incidence, causal dose-response, or medical safety. Every comparator uses the same source population, classifier, context handling, and one-vote-per-author rule.

## Extraction coverage and recall checks

The retention column compares retained classified authors with authors found by deterministic alias matching. It is a recall proxy, not gold-standard sensitivity, because model eligibility and alias matching are different measurement stages.

| Compound | Alias-matched items | Alias-matched authors | Reports | Classified authors | Observed retention | Sample warning |
|---|---|---|---|---|---|---|
| 7,8-DHF | 26 | 12 | 5 | 4 | 33.3% | too sparse for inference |
| 4'-DMA-7,8-DHF | 2 | 2 | 1 | 1 | 50.0% | too sparse for inference |
| Semax | 4634 | 2421 | 1812 | 1007 | 41.6% | adequate for description |
| Cerebrolysin | 1548 | 777 | 387 | 201 | 25.9% | adequate for description |
| Selank | 4041 | 2127 | 1639 | 888 | 41.7% | adequate for description |
| NSI-189 | 98 | 69 | 36 | 26 | 37.7% | adequate for description |
| Dihexa | 492 | 277 | 114 | 68 | 24.5% | adequate for description |
| Lion's mane | 288 | 205 | 83 | 69 | 33.7% | adequate for description |
| 9-MBC | 19 | 14 | 7 | 4 | 28.6% | too sparse for inference |
| BPC-157 | 29780 | 12774 | 17265 | 6440 | 50.4% | adequate for description |

Pipeline B produced 5,539 records from 5,539 selected authors (100.0%) and 135,741 source segments.

OpenRouter models: sentiment `deepseek/deepseek-v4-flash` / `deepseek/deepseek-v4-flash`; variables `deepseek/deepseek-v4-flash`. Provider-reported token totals: sentiment 43,902,365; variables 28,316,519. Text caps were 1,500 upstream characters and 8,000 Pipeline B characters, with a 32,768-token Pipeline B output ceiling.

Source SHA-256 values: comments `5b56aba081d088331596d955ab939a23876670d366ea0219c5a23eebf498fa89`; posts `033b585eb74e044c848943600cae76e520d6cea1049415b65a8c79d0422cad16`. Code commits: sentiment `eadb46d6763c1ba4d6d9ef3871625be38ce6e0bf`; variables `eadb46d6763c1ba4d6d9ef3871625be38ce6e0bf`.

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
| 7,8-DHF | target | target | 4 | 3 | 0 | 1 | 0 | 75.0% | 30.1% to 95.4% | too sparse for inference |
| 4'-DMA-7,8-DHF | chemical analogue | primary | 1 | 1 | 0 | 0 | 0 | 100.0% | 20.7% to 100.0% | too sparse for inference |
| Semax | BDNF/TrkB related | primary | 1007 | 661 | 321 | 23 | 2 | 65.6% | 62.7% to 68.5% | descriptive only |
| Cerebrolysin | BDNF/TrkB related | primary | 201 | 157 | 39 | 5 | 0 | 78.1% | 71.9% to 83.3% | descriptive only |
| Selank | BDNF/TrkB related | primary | 888 | 602 | 267 | 19 | 0 | 67.8% | 64.6% to 70.8% | descriptive only |
| NSI-189 | broader neurotrophic | secondary | 26 | 18 | 6 | 2 | 0 | 69.2% | 50.0% to 83.5% | descriptive only |
| Dihexa | broader neurotrophic | secondary | 68 | 44 | 22 | 2 | 0 | 64.7% | 52.8% to 75.0% | descriptive only |
| Lion's mane | broader neurotrophic | secondary | 69 | 54 | 13 | 2 | 0 | 78.3% | 67.2% to 86.4% | descriptive only |
| 9-MBC | broader neurotrophic | exploratory | 4 | 4 | 0 | 0 | 0 | 100.0% | 51.0% to 100.0% | too sparse for inference |
| BPC-157 | negative control | control | 6440 | 4568 | 1666 | 199 | 7 | 70.9% | 69.8% to 72.0% | descriptive only |

## Comparisons with 7,8-DHF

The positive-rate difference is 7,8-DHF minus comparator, so positive values favor a higher 7,8-DHF positive-reporting share. Fisher tests use mutually exclusive authors and report 7,8-DHF/comparator odds ratios. BH q-values are corrected across comparators. Matched results use authors who reported both compounds; the discordant column is 7,8-DHF-only positive / comparator-only positive. Matched q-values are corrected separately.

| Comparator | 7,8-DHF minus comparator | Exclusive OR | Exclusive p | Exclusive BH q | Exclusive 7,8-DHF authors | Exclusive comparator authors | Matched authors | Discordant | Matched p | Matched BH q | Inference status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4'-DMA-7,8-DHF | -25.0 points | nan | 1.0000 | 1.0000 | 3 | 0 | 1 | 0/1 | 1.0000 | 1.0000 | too sparse for inference |
| Semax | +9.4 points | 0.00 | 0.3433 | 1.0000 | 1 | 1004 | 3 | 2/0 | 0.5000 | 1.0000 | too sparse for inference |
| Cerebrolysin | -3.1 points | 0.56 | 0.5305 | 1.0000 | 3 | 200 | 1 | 0/0 | n/a | n/a | too sparse for inference |
| Selank | +7.2 points | 0.95 | 1.0000 | 1.0000 | 3 | 887 | 1 | 1/0 | 1.0000 | 1.0000 | too sparse for inference |
| NSI-189 | +5.8 points | 0.94 | 1.0000 | 1.0000 | 3 | 25 | 1 | 0/0 | n/a | n/a | too sparse for inference |
| Dihexa | +10.3 points | 1.12 | 1.0000 | 1.0000 | 3 | 67 | 1 | 0/0 | n/a | n/a | too sparse for inference |
| Lion's mane | -3.3 points | 0.57 | 0.5410 | 1.0000 | 3 | 68 | 1 | 0/0 | n/a | n/a | too sparse for inference |
| 9-MBC | -25.0 points | 0.00 | 1.0000 | 1.0000 | 4 | 4 | 0 | 0/0 | n/a | n/a | too sparse for inference |
| BPC-157 | +4.1 points | inf | 1.0000 | 1.0000 | 1 | 6437 | 3 | 0/0 | n/a | n/a | too sparse for inference |

## Treatment-linked side-effect signals

These are the eight most frequently reported canonical effects per compound, deduplicated by author within each effect. Because every pipeline row is linked to one target treatment, the former 7,8-DHF / 4'-DMA blending is removed. Counts remain reporting proportions, not incidence.

| Compound | Canonical effect | Safety domain | Authors | Share of classified authors | Mentions |
|---|---|---|---|---|---|
| 7,8-DHF | cognitive or perceptual disturbance | neurologic | 1 | 25.0% | 1 |
| 7,8-DHF | fatigue or sedation | fatigue or sedation | 1 | 25.0% | 1 |
| 4'-DMA-7,8-DHF | fatigue or sedation | fatigue or sedation | 1 | 100.0% | 1 |
| Semax | other reported effect | other | 133 | 13.2% | 242 |
| Semax | anxiety or panic | activation or anxiety | 39 | 3.9% | 48 |
| Semax | insomnia or sleep disruption | sleep | 36 | 3.6% | 50 |
| Semax | headache or migraine | neurologic | 24 | 2.4% | 28 |
| Semax | activation or irritability | activation or anxiety | 22 | 2.2% | 25 |
| Semax | hair loss or thinning | hair or skin | 22 | 2.2% | 27 |
| Semax | cardiovascular or autonomic | cardiovascular or autonomic | 15 | 1.5% | 16 |
| Semax | fatigue or sedation | fatigue or sedation | 14 | 1.4% | 17 |
| Cerebrolysin | other reported effect | other | 31 | 15.4% | 50 |
| Cerebrolysin | cognitive or perceptual disturbance | neurologic | 11 | 5.5% | 16 |
| Cerebrolysin | insomnia or sleep disruption | sleep | 10 | 5.0% | 11 |
| Cerebrolysin | headache or migraine | neurologic | 6 | 3.0% | 11 |
| Cerebrolysin | anxiety or panic | activation or anxiety | 4 | 2.0% | 7 |
| Cerebrolysin | fatigue or sedation | fatigue or sedation | 4 | 2.0% | 4 |
| Cerebrolysin | hair loss or thinning | hair or skin | 3 | 1.5% | 5 |
| Cerebrolysin | activation or irritability | activation or anxiety | 2 | 1.0% | 3 |
| Selank | other reported effect | other | 98 | 11.0% | 195 |
| Selank | insomnia or sleep disruption | sleep | 30 | 3.4% | 39 |
| Selank | anxiety or panic | activation or anxiety | 24 | 2.7% | 29 |
| Selank | fatigue or sedation | fatigue or sedation | 19 | 2.1% | 27 |
| Selank | headache or migraine | neurologic | 18 | 2.0% | 18 |
| Selank | cognitive or perceptual disturbance | neurologic | 14 | 1.6% | 15 |
| Selank | activation or irritability | activation or anxiety | 12 | 1.4% | 12 |
| Selank | cardiovascular or autonomic | cardiovascular or autonomic | 12 | 1.4% | 15 |
| NSI-189 | other reported effect | other | 5 | 19.2% | 7 |
| NSI-189 | activation or irritability | activation or anxiety | 1 | 3.8% | 2 |
| NSI-189 | anxiety or panic | activation or anxiety | 1 | 3.8% | 2 |
| NSI-189 | depressed or flattened mood | mood | 1 | 3.8% | 1 |
| Dihexa | other reported effect | other | 16 | 23.5% | 27 |
| Dihexa | anxiety or panic | activation or anxiety | 3 | 4.4% | 3 |
| Dihexa | insomnia or sleep disruption | sleep | 2 | 2.9% | 2 |
| Dihexa | activation or irritability | activation or anxiety | 1 | 1.5% | 1 |
| Dihexa | cardiovascular or autonomic | cardiovascular or autonomic | 1 | 1.5% | 2 |
| Dihexa | cognitive or perceptual disturbance | neurologic | 1 | 1.5% | 1 |
| Dihexa | depressed or flattened mood | mood | 1 | 1.5% | 1 |
| Dihexa | fatigue or sedation | fatigue or sedation | 1 | 1.5% | 1 |
| Lion's mane | other reported effect | other | 7 | 10.1% | 8 |
| Lion's mane | depressed or flattened mood | mood | 4 | 5.8% | 4 |
| Lion's mane | insomnia or sleep disruption | sleep | 3 | 4.3% | 3 |
| Lion's mane | sexual | sexual | 3 | 4.3% | 5 |
| Lion's mane | anxiety or panic | activation or anxiety | 2 | 2.9% | 2 |
| Lion's mane | cognitive or perceptual disturbance | neurologic | 1 | 1.4% | 1 |
| Lion's mane | fatigue or sedation | fatigue or sedation | 1 | 1.4% | 1 |
| 9-MBC | other reported effect | other | 1 | 25.0% | 2 |
| BPC-157 | other reported effect | other | 1640 | 25.5% | 4536 |
| BPC-157 | depressed or flattened mood | mood | 291 | 4.5% | 621 |
| BPC-157 | insomnia or sleep disruption | sleep | 282 | 4.4% | 394 |
| BPC-157 | fatigue or sedation | fatigue or sedation | 279 | 4.3% | 471 |
| BPC-157 | anxiety or panic | activation or anxiety | 257 | 4.0% | 510 |
| BPC-157 | gastrointestinal | gastrointestinal | 182 | 2.8% | 277 |
| BPC-157 | cardiovascular or autonomic | cardiovascular or autonomic | 178 | 2.8% | 294 |
| BPC-157 | headache or migraine | neurologic | 153 | 2.4% | 241 |

## Post-level compound, dose, and outcome links

This stricter view keeps only treatment-specific sentiment reports where exactly one quantitative mass dose appears near that compound in the same post or comment. Authors receive one vote per compound and dose band. It is descriptive and does not establish a dose-response relationship.

| Compound | Dose band | Posts | Authors | Positive authors | Side-effect authors | Inference status |
|---|---|---|---|---|---|---|
| 9-MBC | 10 to <25 mg | 1 | 1 | 0/1 (0.0%) | 1/1 (100.0%) | too sparse for inference |
| BPC-157 | <5 mg | 678 | 522 | 365/522 (69.9%) | 177/522 (33.9%) | descriptive only |
| BPC-157 | 5 to <10 mg | 74 | 69 | 51/69 (73.9%) | 19/69 (27.5%) | descriptive only |
| BPC-157 | 10 to <25 mg | 62 | 57 | 43/57 (75.4%) | 16/57 (28.1%) | descriptive only |
| BPC-157 | 25 to <50 mg | 14 | 14 | 10/14 (71.4%) | 3/14 (21.4%) | descriptive only |
| BPC-157 | 50 to <100 mg | 15 | 15 | 11/15 (73.3%) | 4/15 (26.7%) | descriptive only |
| BPC-157 | >=100 mg | 87 | 78 | 50/78 (64.1%) | 25/78 (32.1%) | descriptive only |
| Cerebrolysin | <5 mg | 4 | 4 | 4/4 (100.0%) | 0/4 (0.0%) | too sparse for inference |
| Cerebrolysin | 5 to <10 mg | 3 | 3 | 1/3 (33.3%) | 0/3 (0.0%) | too sparse for inference |
| Cerebrolysin | 10 to <25 mg | 4 | 4 | 4/4 (100.0%) | 0/4 (0.0%) | too sparse for inference |
| Cerebrolysin | >=100 mg | 5 | 4 | 3/4 (75.0%) | 0/4 (0.0%) | too sparse for inference |
| Dihexa | 5 to <10 mg | 1 | 1 | 1/1 (100.0%) | 1/1 (100.0%) | too sparse for inference |
| Dihexa | 10 to <25 mg | 4 | 4 | 3/4 (75.0%) | 0/4 (0.0%) | too sparse for inference |
| Dihexa | 25 to <50 mg | 2 | 2 | 2/2 (100.0%) | 2/2 (100.0%) | too sparse for inference |
| Dihexa | >=100 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Lion's mane | <5 mg | 3 | 3 | 3/3 (100.0%) | 0/3 (0.0%) | too sparse for inference |
| Lion's mane | 5 to <10 mg | 1 | 1 | 1/1 (100.0%) | 1/1 (100.0%) | too sparse for inference |
| Lion's mane | 10 to <25 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Lion's mane | >=100 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| NSI-189 | 10 to <25 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| NSI-189 | 25 to <50 mg | 1 | 1 | 0/1 (0.0%) | 1/1 (100.0%) | too sparse for inference |
| NSI-189 | >=100 mg | 1 | 1 | 0/1 (0.0%) | 1/1 (100.0%) | too sparse for inference |
| Selank | <5 mg | 107 | 87 | 64/87 (73.6%) | 21/87 (24.1%) | descriptive only |
| Selank | 5 to <10 mg | 8 | 8 | 7/8 (87.5%) | 0/8 (0.0%) | too sparse for inference |
| Selank | 10 to <25 mg | 14 | 13 | 9/13 (69.2%) | 2/13 (15.4%) | descriptive only |
| Selank | 25 to <50 mg | 4 | 4 | 3/4 (75.0%) | 0/4 (0.0%) | too sparse for inference |
| Selank | 50 to <100 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Selank | >=100 mg | 10 | 10 | 7/10 (70.0%) | 1/10 (10.0%) | descriptive only |
| Semax | <5 mg | 107 | 91 | 74/91 (81.3%) | 16/91 (17.6%) | descriptive only |
| Semax | 5 to <10 mg | 7 | 7 | 5/7 (71.4%) | 2/7 (28.6%) | too sparse for inference |
| Semax | 10 to <25 mg | 13 | 13 | 10/13 (76.9%) | 0/13 (0.0%) | descriptive only |
| Semax | 25 to <50 mg | 5 | 5 | 5/5 (100.0%) | 0/5 (0.0%) | too sparse for inference |
| Semax | 50 to <100 mg | 2 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Semax | >=100 mg | 12 | 12 | 9/12 (75.0%) | 1/12 (8.3%) | descriptive only |

## Dose and route attribution checks

| Field | Status | Rows |
|---|---|---|
| Dose | corroborated | 1642 |
| Dose | unsupported | 1588 |
| Route | corroborated | 1893 |
| Route | unsupported | 1643 |

## Dose-stratified side-effect reporting

Side-effect reporting is joined by hashed author and compound across all of that author's reports. The denominator is every distinct author in the dose or route bucket. Classifier coverage shows how many denominator authors also had a retained comparator report. These are cross-report associations, not administration-event links, incidence estimates, or dose-response evidence. Dose and route rows are included only when the extracted value and compound were found near each other in the same source segment.

| Compound | Dose band | Observations | Authors | Classifier coverage | Any side effect | Leading mapped effects |
|---|---|---|---|---|---|---|
| 4'-DMA | 10 to <25 mg | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | fatigue or sedation: 1/1 (100.0%) |
| BPC-157 | <5 mg | 1226 | 966 | 954/966 | 417/966 (43.2%; 95% CI 40.1% to 46.3%) | insomnia or sleep disruption: 81/966 (8.4%); fatigue or sedation: 77/966 (8.0%); anxiety or panic: 52/966 (5.4%) |
| BPC-157 | 5 to <10 mg | 38 | 38 | 38/38 | 20/38 (52.6%; 95% CI 37.3% to 67.5%) | fatigue or sedation: 7/38 (18.4%); depressed or flattened mood: 4/38 (10.5%); insomnia or sleep disruption: 4/38 (10.5%) |
| BPC-157 | 10 to <25 mg | 29 | 27 | 26/27 | 14/27 (51.9%; 95% CI 34.0% to 69.3%) | depressed or flattened mood: 5/27 (18.5%); insomnia or sleep disruption: 5/27 (18.5%); cardiovascular or autonomic: 3/27 (11.1%) |
| BPC-157 | 25 to <50 mg | 3 | 3 | 3/3 | 2/3 (66.7%; 95% CI 20.8% to 93.9%) | anxiety or panic: 1/3 (33.3%); cognitive or perceptual disturbance: 1/3 (33.3%) |
| BPC-157 | 50 to <100 mg | 4 | 4 | 4/4 | 2/4 (50.0%; 95% CI 15.0% to 85.0%) | depressed or flattened mood: 2/4 (50.0%); cardiovascular or autonomic: 1/4 (25.0%); insomnia or sleep disruption: 1/4 (25.0%) |
| BPC-157 | >=100 mg | 61 | 56 | 56/56 | 26/56 (46.4%; 95% CI 34.0% to 59.3%) | fatigue or sedation: 7/56 (12.5%); headache or migraine: 7/56 (12.5%); depressed or flattened mood: 6/56 (10.7%) |
| Cerebrolysin | 5 to <10 mg | 3 | 3 | 3/3 | 0/3 (0.0%; 95% CI 0.0% to 56.2%) | none mapped |
| Dihexa | 5 to <10 mg | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | insomnia or sleep disruption: 1/1 (100.0%) |
| Dihexa | 10 to <25 mg | 3 | 3 | 3/3 | 1/3 (33.3%; 95% CI 6.1% to 79.2%) | none mapped |
| Lion's mane | >=100 mg | 3 | 3 | 2/3 | 0/3 (0.0%; 95% CI 0.0% to 56.2%) | none mapped |
| NSI-189 | <5 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| NSI-189 | 25 to <50 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Selank | <5 mg | 122 | 98 | 90/98 | 25/98 (25.5%; 95% CI 17.9% to 35.0%) | anxiety or panic: 5/98 (5.1%); fatigue or sedation: 5/98 (5.1%); insomnia or sleep disruption: 4/98 (4.1%) |
| Selank | 5 to <10 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Selank | 10 to <25 mg | 6 | 6 | 4/6 | 1/6 (16.7%; 95% CI 3.0% to 56.4%) | none mapped |
| Selank | >=100 mg | 2 | 2 | 2/2 | 0/2 (0.0%; 95% CI 0.0% to 65.8%) | none mapped |
| Semax | <5 mg | 129 | 107 | 103/107 | 32/107 (29.9%; 95% CI 22.1% to 39.2%) | anxiety or panic: 10/107 (9.3%); insomnia or sleep disruption: 8/107 (7.5%); headache or migraine: 5/107 (4.7%) |
| Semax | 5 to <10 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Semax | 10 to <25 mg | 2 | 2 | 2/2 | 0/2 (0.0%; 95% CI 0.0% to 65.8%) | none mapped |
| Semax | 25 to <50 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Semax | >=100 mg | 4 | 4 | 4/4 | 1/4 (25.0%; 95% CI 4.6% to 69.9%) | crash or rebound: 1/4 (25.0%) |

## Route-stratified side-effect reporting

Side-effect reporting is joined by hashed author and compound across all of that author's reports. The denominator is every distinct author in the dose or route bucket. Classifier coverage shows how many denominator authors also had a retained comparator report. These are cross-report associations, not administration-event links, incidence estimates, or dose-response evidence. Dose and route rows are included only when the extracted value and compound were found near each other in the same source segment.

| Compound | Route family | Observations | Authors | Classifier coverage | Any side effect | Leading mapped effects |
|---|---|---|---|---|---|---|
| BPC-157 | dermal | 15 | 15 | 15/15 | 5/15 (33.3%; 95% CI 15.2% to 58.3%) | anxiety or panic: 1/15 (6.7%); insomnia or sleep disruption: 1/15 (6.7%) |
| BPC-157 | nasal mucosal | 69 | 69 | 67/69 | 29/69 (42.0%; 95% CI 31.1% to 53.8%) | anxiety or panic: 5/69 (7.2%); cardiovascular or autonomic: 5/69 (7.2%); cognitive or perceptual disturbance: 5/69 (7.2%) |
| BPC-157 | oral mucosal | 35 | 35 | 35/35 | 14/35 (40.0%; 95% CI 25.6% to 56.4%) | depressed or flattened mood: 3/35 (8.6%); insomnia or sleep disruption: 3/35 (8.6%); activation or irritability: 2/35 (5.7%) |
| BPC-157 | parenteral | 934 | 905 | 897/905 | 399/905 (44.1%; 95% CI 40.9% to 47.3%) | insomnia or sleep disruption: 61/905 (6.7%); fatigue or sedation: 59/905 (6.5%); depressed or flattened mood: 49/905 (5.4%) |
| BPC-157 | swallowed oral | 387 | 386 | 383/386 | 159/386 (41.2%; 95% CI 36.4% to 46.2%) | fatigue or sedation: 33/386 (8.5%); depressed or flattened mood: 30/386 (7.8%); gastrointestinal: 28/386 (7.3%) |
| Cerebrolysin | nasal mucosal | 2 | 2 | 2/2 | 0/2 (0.0%; 95% CI 0.0% to 65.8%) | none mapped |
| Cerebrolysin | parenteral | 23 | 23 | 22/23 | 4/23 (17.4%; 95% CI 7.0% to 37.1%) | cognitive or perceptual disturbance: 2/23 (8.7%); headache or migraine: 2/23 (8.7%); gastrointestinal: 1/23 (4.3%) |
| Cerebrolysin | swallowed oral | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Dihexa | dermal | 3 | 3 | 2/3 | 0/3 (0.0%; 95% CI 0.0% to 56.2%) | none mapped |
| Dihexa | nasal mucosal | 1 | 1 | 0/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Dihexa | oral mucosal | 2 | 2 | 2/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | none mapped |
| Dihexa | swallowed oral | 3 | 3 | 3/3 | 1/3 (33.3%; 95% CI 6.1% to 79.2%) | insomnia or sleep disruption: 1/3 (33.3%) |
| NSI-189 | oral mucosal | 2 | 2 | 2/2 | 0/2 (0.0%; 95% CI 0.0% to 65.8%) | none mapped |
| Selank | nasal mucosal | 121 | 119 | 105/119 | 32/119 (26.9%; 95% CI 19.7% to 35.5%) | fatigue or sedation: 8/119 (6.7%); anxiety or panic: 5/119 (4.2%); cognitive or perceptual disturbance: 4/119 (3.4%) |
| Selank | oral mucosal | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | activation or irritability: 1/1 (100.0%) |
| Selank | parenteral | 75 | 73 | 68/73 | 20/73 (27.4%; 95% CI 18.5% to 38.6%) | anxiety or panic: 5/73 (6.8%); headache or migraine: 4/73 (5.5%); fatigue or sedation: 3/73 (4.1%) |
| Semax | nasal mucosal | 128 | 125 | 110/125 | 23/125 (18.4%; 95% CI 12.6% to 26.1%) | headache or migraine: 6/125 (4.8%); anxiety or panic: 4/125 (3.2%); insomnia or sleep disruption: 4/125 (3.2%) |
| Semax | oral mucosal | 2 | 2 | 2/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | activation or irritability: 1/2 (50.0%) |
| Semax | parenteral | 89 | 87 | 82/87 | 22/87 (25.3%; 95% CI 17.3% to 35.3%) | anxiety or panic: 3/87 (3.4%); insomnia or sleep disruption: 3/87 (3.4%); activation or irritability: 2/87 (2.3%) |

## Symptom-linked outcomes

Explicit PEM target coverage: 2 treatment-linked outcome entries. General fatigue remains a separate endpoint bucket.

| Compound | Target symptom | Authors | Helped | No effect | Worsened |
|---|---|---|---|---|---|
| 4'-DMA | energy or motivation | 1 | 1 | 0 | 0 |
| 4'-DMA | other specified result | 1 | 1 | 0 | 0 |
| 4'-DMA | sleep or wakefulness | 1 | 1 | 0 | 0 |
| 9-MBC | focus or attention | 1 | 1 | 0 | 0 |
| BPC-157 | other specified result | 1437 | 1432 | 233 | 396 |
| BPC-157 | pain or neurologic symptoms | 1245 | 1189 | 167 | 176 |
| BPC-157 | mood or depression | 209 | 92 | 5 | 146 |
| BPC-157 | neuroprotection or recovery | 200 | 193 | 17 | 4 |
| BPC-157 | gastrointestinal | 198 | 142 | 15 | 42 |
| BPC-157 | sleep or wakefulness | 188 | 103 | 12 | 74 |
| BPC-157 | anxiety or stress | 151 | 59 | 3 | 102 |
| BPC-157 | general fatigue | 122 | 17 | 3 | 100 |
| BPC-157 | cognition or brain fog | 74 | 44 | 4 | 28 |
| BPC-157 | hair or skin | 57 | 47 | 5 | 14 |
| BPC-157 | energy or motivation | 51 | 39 | 3 | 10 |
| BPC-157 | cardiovascular or autonomic | 43 | 3 | 1 | 40 |
| BPC-157 | sexual function | 29 | 12 | 1 | 15 |
| BPC-157 | focus or attention | 22 | 12 | 1 | 12 |
| BPC-157 | stimulant recovery or reduction | 9 | 1 | 0 | 8 |
| BPC-157 | memory or learning | 6 | 4 | 0 | 2 |
| BPC-157 | post-exertional malaise | 2 | 1 | 1 | 0 |
| Cerebrolysin | other specified result | 21 | 25 | 1 | 6 |
| Cerebrolysin | cognition or brain fog | 19 | 16 | 1 | 3 |
| Cerebrolysin | mood or depression | 10 | 12 | 0 | 0 |
| Cerebrolysin | focus or attention | 9 | 8 | 1 | 0 |
| Cerebrolysin | anxiety or stress | 8 | 8 | 0 | 1 |
| Cerebrolysin | sleep or wakefulness | 7 | 6 | 0 | 1 |
| Cerebrolysin | memory or learning | 4 | 4 | 0 | 0 |
| Cerebrolysin | pain or neurologic symptoms | 4 | 2 | 1 | 1 |
| Cerebrolysin | energy or motivation | 3 | 2 | 0 | 1 |
| Cerebrolysin | general fatigue | 2 | 1 | 0 | 1 |
| Cerebrolysin | hair or skin | 1 | 0 | 0 | 1 |
| Cerebrolysin | neuroprotection or recovery | 1 | 1 | 0 | 0 |
| Dihexa | cognition or brain fog | 8 | 8 | 0 | 0 |
| Dihexa | other specified result | 6 | 3 | 0 | 3 |
| Dihexa | sleep or wakefulness | 3 | 2 | 0 | 1 |
| Dihexa | anxiety or stress | 2 | 0 | 0 | 2 |
| Dihexa | memory or learning | 2 | 2 | 0 | 0 |
| Dihexa | focus or attention | 1 | 2 | 0 | 0 |
| Dihexa | hair or skin | 1 | 0 | 0 | 1 |
| Dihexa | mood or depression | 1 | 0 | 0 | 1 |
| Dihexa | pain or neurologic symptoms | 1 | 1 | 0 | 0 |
| Lion's mane | other specified result | 7 | 4 | 2 | 2 |
| Lion's mane | cognition or brain fog | 5 | 4 | 1 | 0 |
| Lion's mane | memory or learning | 5 | 5 | 0 | 0 |
| Lion's mane | mood or depression | 3 | 2 | 0 | 2 |
| Lion's mane | focus or attention | 2 | 2 | 0 | 0 |
| Lion's mane | anxiety or stress | 1 | 0 | 0 | 1 |
| Lion's mane | energy or motivation | 1 | 0 | 1 | 0 |
| Lion's mane | general fatigue | 1 | 0 | 0 | 1 |
| Lion's mane | sleep or wakefulness | 1 | 0 | 0 | 1 |
| NSI-189 | other specified result | 3 | 4 | 0 | 1 |
| NSI-189 | mood or depression | 2 | 1 | 1 | 0 |
| NSI-189 | energy or motivation | 1 | 1 | 0 | 0 |
| Selank | anxiety or stress | 165 | 164 | 8 | 12 |
| Selank | other specified result | 74 | 62 | 4 | 24 |
| Selank | sleep or wakefulness | 46 | 34 | 5 | 10 |
| Selank | mood or depression | 34 | 30 | 1 | 4 |
| Selank | focus or attention | 25 | 22 | 3 | 0 |
| Selank | cognition or brain fog | 17 | 11 | 3 | 3 |
| Selank | pain or neurologic symptoms | 10 | 2 | 0 | 8 |
| Selank | memory or learning | 8 | 9 | 0 | 0 |
| Selank | general fatigue | 6 | 0 | 0 | 7 |
| Selank | energy or motivation | 5 | 5 | 0 | 1 |
| Selank | gastrointestinal | 5 | 2 | 0 | 3 |
| Selank | hair or skin | 4 | 1 | 0 | 3 |
| Selank | cardiovascular or autonomic | 3 | 1 | 0 | 2 |
| Selank | neuroprotection or recovery | 2 | 2 | 0 | 0 |
| Selank | sexual function | 2 | 0 | 0 | 2 |
| Selank | social functioning | 2 | 2 | 0 | 0 |
| Selank | stimulant recovery or reduction | 1 | 0 | 0 | 1 |
| Semax | focus or attention | 94 | 89 | 7 | 1 |
| Semax | other specified result | 91 | 61 | 4 | 37 |
| Semax | cognition or brain fog | 68 | 71 | 4 | 1 |
| Semax | energy or motivation | 43 | 41 | 3 | 3 |
| Semax | anxiety or stress | 40 | 31 | 1 | 14 |
| Semax | mood or depression | 35 | 32 | 0 | 8 |
| Semax | memory or learning | 24 | 24 | 0 | 0 |
| Semax | sleep or wakefulness | 20 | 7 | 2 | 11 |
| Semax | pain or neurologic symptoms | 19 | 3 | 0 | 16 |
| Semax | hair or skin | 12 | 1 | 1 | 10 |
| Semax | general fatigue | 10 | 4 | 0 | 6 |
| Semax | cardiovascular or autonomic | 4 | 0 | 0 | 4 |
| Semax | gastrointestinal | 3 | 1 | 0 | 2 |
| Semax | neuroprotection or recovery | 3 | 2 | 0 | 1 |
| Semax | social functioning | 2 | 2 | 0 | 0 |
| Semax | stimulant recovery or reduction | 2 | 1 | 0 | 0 |
| Semax | sexual function | 1 | 0 | 0 | 1 |

## Interpretation boundaries

- Keep 7,8-DHF and 4'-DMA-7,8-DHF separate.
- Treat PEM as distinct from general fatigue when it is explicitly stated.
- Do not infer that dose, route, outcome, and side effect belong to one administration event unless the source explicitly links them.
- Use matched-author results as a sensitivity analysis, not as the primary estimand, because overlap can be sparse.
- The direct TrkB-agonist interpretation of 7,8-DHF remains disputed; the cohort is tiered rather than presented as one homogeneous mechanism class.

## Reproducibility

- Sentiment database: `sentiment.db`; SHA-256 `4e239ef5971c8f08389bd30ec26321ac118443406a01e3c3933b16564a2e180b`
- Study database: `combined.db`; SHA-256 `3927c22da7bc802f6c8dee93d4ffd53f373e25d942f6a1f71b42c77c4a0cf299`
- Cohort configuration: `comparator_cohort.json`; SHA-256 `c420e12d450b0b2637983121cd1db06c56c62e9567e002fb257f01887cfc8063`
