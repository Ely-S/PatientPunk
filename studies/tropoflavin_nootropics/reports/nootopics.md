# 7,8-DHF comparator-cohort analysis: r/NooTopics

This report answers the OMF collaboration questions with aggregate r/NooTopics self-reports. It measures reporting patterns, not efficacy, adverse-event incidence, causal dose-response, or medical safety. Every comparator uses the same source population, classifier, context handling, and one-vote-per-author rule.

## Extraction coverage and recall checks

The retention column compares retained classified authors with authors found by deterministic alias matching. It is a recall proxy, not gold-standard sensitivity, because model eligibility and alias matching are different measurement stages.

| Compound | Alias-matched items | Alias-matched authors | Reports | Classified authors | Observed retention | Sample warning |
|---|---|---|---|---|---|---|
| 7,8-DHF | 410 | 195 | 221 | 105 | 53.8% | adequate for description |
| 4'-DMA-7,8-DHF | 174 | 67 | 134 | 51 | 76.1% | adequate for description |
| Semax | 3100 | 1557 | 1192 | 601 | 38.6% | adequate for description |
| Cerebrolysin | 1564 | 683 | 444 | 209 | 30.6% | adequate for description |
| Selank | 2083 | 1079 | 725 | 408 | 37.8% | adequate for description |
| NSI-189 | 773 | 377 | 441 | 193 | 51.2% | adequate for description |
| Dihexa | 988 | 515 | 258 | 129 | 25.0% | adequate for description |
| Lion's mane | 1694 | 1110 | 660 | 487 | 43.9% | adequate for description |
| 9-MBC | 184 | 73 | 92 | 44 | 60.3% | adequate for description |
| BPC-157 | 486 | 329 | 195 | 128 | 38.9% | adequate for description |

Pipeline B produced 1,369 records from 1,369 selected authors (100.0%) and 34,201 source segments.

OpenRouter models: sentiment `deepseek/deepseek-v4-flash` / `deepseek/deepseek-v4-flash`; variables `deepseek/deepseek-v4-flash`. Provider-reported token totals: sentiment 14,064,903; variables 6,671,080. Text caps were 1,500 upstream characters and 8,000 Pipeline B characters, with a 32,768-token Pipeline B output ceiling.

Source SHA-256 values: comments `7850e8272546747883e007bcc982dd9badbe464ba691417299164e19d23eac63`; posts `e11f972ac1a3faa82a6e6abf3866b6e3b51b029fea72889a6826353c3c5d3a12`. Code commits: sentiment `eadb46d6763c1ba4d6d9ef3871625be38ce6e0bf`; variables `eadb46d6763c1ba4d6d9ef3871625be38ce6e0bf`.

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
| 7,8-DHF | target | target | 105 | 77 | 26 | 2 | 0 | 73.3% | 64.2% to 80.9% | descriptive only |
| 4'-DMA-7,8-DHF | chemical analogue | primary | 51 | 32 | 15 | 4 | 0 | 62.7% | 49.0% to 74.7% | descriptive only |
| Semax | BDNF/TrkB related | primary | 601 | 414 | 166 | 21 | 0 | 68.9% | 65.1% to 72.5% | descriptive only |
| Cerebrolysin | BDNF/TrkB related | primary | 209 | 169 | 35 | 5 | 0 | 80.9% | 75.0% to 85.6% | descriptive only |
| Selank | BDNF/TrkB related | primary | 408 | 299 | 103 | 6 | 0 | 73.3% | 68.8% to 77.3% | descriptive only |
| NSI-189 | broader neurotrophic | secondary | 193 | 117 | 71 | 4 | 1 | 60.6% | 53.6% to 67.2% | descriptive only |
| Dihexa | broader neurotrophic | secondary | 129 | 83 | 34 | 12 | 0 | 64.3% | 55.8% to 72.1% | descriptive only |
| Lion's mane | broader neurotrophic | secondary | 487 | 306 | 171 | 9 | 1 | 62.8% | 58.5% to 67.0% | descriptive only |
| 9-MBC | broader neurotrophic | exploratory | 44 | 24 | 20 | 0 | 0 | 54.5% | 40.1% to 68.3% | descriptive only |
| BPC-157 | negative control | control | 128 | 84 | 40 | 4 | 0 | 65.6% | 57.0% to 73.3% | descriptive only |

## Comparisons with 7,8-DHF

The positive-rate difference is 7,8-DHF minus comparator, so positive values favor a higher 7,8-DHF positive-reporting share. Fisher tests use mutually exclusive authors and report 7,8-DHF/comparator odds ratios. BH q-values are corrected across comparators. Matched results use authors who reported both compounds; the discordant column is 7,8-DHF-only positive / comparator-only positive. Matched q-values are corrected separately.

| Comparator | 7,8-DHF minus comparator | Exclusive OR | Exclusive p | Exclusive BH q | Exclusive 7,8-DHF authors | Exclusive comparator authors | Matched authors | Discordant | Matched p | Matched BH q | Inference status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4'-DMA-7,8-DHF | +10.6 points | 2.79 | 0.0852 | 0.1918 | 72 | 18 | 33 | 2/1 | 1.0000 | 1.0000 | sensitivity analysis |
| Semax | +4.4 points | 1.04 | 1.0000 | 1.0000 | 75 | 571 | 30 | 7/5 | 0.7744 | 1.0000 | sensitivity analysis |
| Cerebrolysin | -7.5 points | 0.57 | 0.0658 | 0.1918 | 96 | 200 | 9 | 4/1 | 0.3750 | 1.0000 | sensitivity analysis |
| Selank | +0.0 points | 0.89 | 0.6781 | 0.7629 | 80 | 383 | 25 | 6/3 | 0.5078 | 1.0000 | sensitivity analysis |
| NSI-189 | +12.7 points | 1.88 | 0.0364 | 0.1638 | 83 | 171 | 22 | 4/3 | 1.0000 | 1.0000 | sensitivity analysis |
| Dihexa | +9.0 points | 1.62 | 0.1304 | 0.1956 | 95 | 119 | 10 | 2/1 | 1.0000 | 1.0000 | sensitivity analysis |
| Lion's mane | +10.5 points | 1.55 | 0.1090 | 0.1956 | 86 | 468 | 19 | 9/2 | 0.0654 | 0.5889 | sensitivity analysis |
| 9-MBC | +18.8 points | 2.48 | 0.0275 | 0.1638 | 101 | 40 | 4 | 0/0 | n/a | n/a | sensitivity analysis |
| BPC-157 | +7.7 points | 1.34 | 0.3758 | 0.4832 | 95 | 118 | 10 | 3/1 | 0.6250 | 1.0000 | sensitivity analysis |

## Treatment-linked side-effect signals

These are the eight most frequently reported canonical effects per compound, deduplicated by author within each effect. Because every pipeline row is linked to one target treatment, the former 7,8-DHF / 4'-DMA blending is removed. Counts remain reporting proportions, not incidence.

| Compound | Canonical effect | Safety domain | Authors | Share of classified authors | Mentions |
|---|---|---|---|---|---|
| 7,8-DHF | other reported effect | other | 26 | 24.8% | 48 |
| 7,8-DHF | insomnia or sleep disruption | sleep | 12 | 11.4% | 17 |
| 7,8-DHF | activation or irritability | activation or anxiety | 7 | 6.7% | 11 |
| 7,8-DHF | anxiety or panic | activation or anxiety | 7 | 6.7% | 12 |
| 7,8-DHF | cognitive or perceptual disturbance | neurologic | 5 | 4.8% | 14 |
| 7,8-DHF | fatigue or sedation | fatigue or sedation | 5 | 4.8% | 6 |
| 7,8-DHF | tolerance or short duration | tolerance or duration | 3 | 2.9% | 3 |
| 7,8-DHF | depressed or flattened mood | mood | 2 | 1.9% | 7 |
| 4'-DMA-7,8-DHF | other reported effect | other | 9 | 17.6% | 15 |
| 4'-DMA-7,8-DHF | insomnia or sleep disruption | sleep | 5 | 9.8% | 11 |
| 4'-DMA-7,8-DHF | cognitive or perceptual disturbance | neurologic | 4 | 7.8% | 6 |
| 4'-DMA-7,8-DHF | tolerance or short duration | tolerance or duration | 4 | 7.8% | 4 |
| 4'-DMA-7,8-DHF | activation or irritability | activation or anxiety | 3 | 5.9% | 3 |
| 4'-DMA-7,8-DHF | anxiety or panic | activation or anxiety | 2 | 3.9% | 2 |
| 4'-DMA-7,8-DHF | crash or rebound | activation or anxiety | 2 | 3.9% | 2 |
| 4'-DMA-7,8-DHF | depressed or flattened mood | mood | 1 | 2.0% | 1 |
| Semax | other reported effect | other | 86 | 14.3% | 134 |
| Semax | insomnia or sleep disruption | sleep | 26 | 4.3% | 35 |
| Semax | anxiety or panic | activation or anxiety | 20 | 3.3% | 25 |
| Semax | cognitive or perceptual disturbance | neurologic | 20 | 3.3% | 21 |
| Semax | activation or irritability | activation or anxiety | 17 | 2.8% | 18 |
| Semax | fatigue or sedation | fatigue or sedation | 17 | 2.8% | 20 |
| Semax | headache or migraine | neurologic | 14 | 2.3% | 14 |
| Semax | depressed or flattened mood | mood | 13 | 2.2% | 14 |
| Cerebrolysin | other reported effect | other | 28 | 13.4% | 39 |
| Cerebrolysin | cognitive or perceptual disturbance | neurologic | 5 | 2.4% | 8 |
| Cerebrolysin | depressed or flattened mood | mood | 5 | 2.4% | 5 |
| Cerebrolysin | insomnia or sleep disruption | sleep | 4 | 1.9% | 4 |
| Cerebrolysin | activation or irritability | activation or anxiety | 2 | 1.0% | 3 |
| Cerebrolysin | anxiety or panic | activation or anxiety | 2 | 1.0% | 2 |
| Cerebrolysin | cardiovascular or autonomic | cardiovascular or autonomic | 2 | 1.0% | 2 |
| Cerebrolysin | appetite change | appetite or weight | 1 | 0.5% | 1 |
| Selank | other reported effect | other | 40 | 9.8% | 76 |
| Selank | anxiety or panic | activation or anxiety | 11 | 2.7% | 13 |
| Selank | depressed or flattened mood | mood | 10 | 2.5% | 11 |
| Selank | headache or migraine | neurologic | 10 | 2.5% | 20 |
| Selank | gastrointestinal | gastrointestinal | 9 | 2.2% | 13 |
| Selank | insomnia or sleep disruption | sleep | 8 | 2.0% | 10 |
| Selank | fatigue or sedation | fatigue or sedation | 6 | 1.5% | 6 |
| Selank | activation or irritability | activation or anxiety | 5 | 1.2% | 6 |
| NSI-189 | other reported effect | other | 71 | 36.8% | 171 |
| NSI-189 | anxiety or panic | activation or anxiety | 23 | 11.9% | 32 |
| NSI-189 | insomnia or sleep disruption | sleep | 18 | 9.3% | 24 |
| NSI-189 | cognitive or perceptual disturbance | neurologic | 16 | 8.3% | 23 |
| NSI-189 | activation or irritability | activation or anxiety | 7 | 3.6% | 8 |
| NSI-189 | headache or migraine | neurologic | 4 | 2.1% | 4 |
| NSI-189 | fatigue or sedation | fatigue or sedation | 3 | 1.6% | 3 |
| NSI-189 | gastrointestinal | gastrointestinal | 2 | 1.0% | 2 |
| Dihexa | other reported effect | other | 35 | 27.1% | 65 |
| Dihexa | insomnia or sleep disruption | sleep | 8 | 6.2% | 11 |
| Dihexa | cognitive or perceptual disturbance | neurologic | 7 | 5.4% | 10 |
| Dihexa | activation or irritability | activation or anxiety | 4 | 3.1% | 4 |
| Dihexa | depressed or flattened mood | mood | 3 | 2.3% | 3 |
| Dihexa | fatigue or sedation | fatigue or sedation | 3 | 2.3% | 3 |
| Dihexa | anxiety or panic | activation or anxiety | 2 | 1.6% | 2 |
| Dihexa | appetite change | appetite or weight | 2 | 1.6% | 5 |
| Lion's mane | other reported effect | other | 97 | 19.9% | 176 |
| Lion's mane | sexual | sexual | 23 | 4.7% | 31 |
| Lion's mane | anxiety or panic | activation or anxiety | 21 | 4.3% | 27 |
| Lion's mane | cognitive or perceptual disturbance | neurologic | 21 | 4.3% | 37 |
| Lion's mane | depressed or flattened mood | mood | 21 | 4.3% | 34 |
| Lion's mane | headache or migraine | neurologic | 12 | 2.5% | 13 |
| Lion's mane | insomnia or sleep disruption | sleep | 12 | 2.5% | 13 |
| Lion's mane | fatigue or sedation | fatigue or sedation | 7 | 1.4% | 7 |
| 9-MBC | other reported effect | other | 20 | 45.5% | 47 |
| 9-MBC | activation or irritability | activation or anxiety | 3 | 6.8% | 3 |
| 9-MBC | insomnia or sleep disruption | sleep | 3 | 6.8% | 5 |
| 9-MBC | anxiety or panic | activation or anxiety | 2 | 4.5% | 2 |
| 9-MBC | cardiovascular or autonomic | cardiovascular or autonomic | 2 | 4.5% | 2 |
| 9-MBC | headache or migraine | neurologic | 2 | 4.5% | 2 |
| 9-MBC | cognitive or perceptual disturbance | neurologic | 1 | 2.3% | 1 |
| 9-MBC | depressed or flattened mood | mood | 1 | 2.3% | 2 |
| BPC-157 | other reported effect | other | 33 | 25.8% | 55 |
| BPC-157 | depressed or flattened mood | mood | 26 | 20.3% | 40 |
| BPC-157 | cognitive or perceptual disturbance | neurologic | 4 | 3.1% | 5 |
| BPC-157 | fatigue or sedation | fatigue or sedation | 4 | 3.1% | 6 |
| BPC-157 | anxiety or panic | activation or anxiety | 2 | 1.6% | 2 |
| BPC-157 | insomnia or sleep disruption | sleep | 2 | 1.6% | 2 |
| BPC-157 | appetite change | appetite or weight | 1 | 0.8% | 1 |
| BPC-157 | gastrointestinal | gastrointestinal | 1 | 0.8% | 1 |

## Post-level compound, dose, and outcome links

This stricter view keeps only treatment-specific sentiment reports where exactly one quantitative mass dose appears near that compound in the same post or comment. Authors receive one vote per compound and dose band. It is descriptive and does not establish a dose-response relationship.

| Compound | Dose band | Posts | Authors | Positive authors | Side-effect authors | Inference status |
|---|---|---|---|---|---|---|
| 4'-DMA-7,8-DHF | 10 to <25 mg | 2 | 2 | 1/2 (50.0%) | 0/2 (0.0%) | too sparse for inference |
| 4'-DMA-7,8-DHF | 25 to <50 mg | 3 | 1 | 1/1 (100.0%) | 1/1 (100.0%) | too sparse for inference |
| 4'-DMA-7,8-DHF | >=100 mg | 3 | 3 | 3/3 (100.0%) | 1/3 (33.3%) | too sparse for inference |
| 7,8-DHF | <5 mg | 1 | 1 | 0/1 (0.0%) | 1/1 (100.0%) | too sparse for inference |
| 7,8-DHF | 10 to <25 mg | 6 | 6 | 2/6 (33.3%) | 3/6 (50.0%) | too sparse for inference |
| 7,8-DHF | 25 to <50 mg | 2 | 2 | 1/2 (50.0%) | 0/2 (0.0%) | too sparse for inference |
| 7,8-DHF | 50 to <100 mg | 1 | 1 | 0/1 (0.0%) | 1/1 (100.0%) | too sparse for inference |
| 7,8-DHF | >=100 mg | 5 | 3 | 3/3 (100.0%) | 0/3 (0.0%) | too sparse for inference |
| 9-MBC | 5 to <10 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| 9-MBC | 10 to <25 mg | 1 | 1 | 0/1 (0.0%) | 1/1 (100.0%) | too sparse for inference |
| 9-MBC | 25 to <50 mg | 1 | 1 | 1/1 (100.0%) | 1/1 (100.0%) | too sparse for inference |
| BPC-157 | <5 mg | 3 | 3 | 3/3 (100.0%) | 1/3 (33.3%) | too sparse for inference |
| BPC-157 | 25 to <50 mg | 1 | 1 | 0/1 (0.0%) | 1/1 (100.0%) | too sparse for inference |
| BPC-157 | 50 to <100 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| BPC-157 | >=100 mg | 3 | 3 | 1/3 (33.3%) | 1/3 (33.3%) | too sparse for inference |
| Cerebrolysin | <5 mg | 5 | 5 | 4/5 (80.0%) | 0/5 (0.0%) | too sparse for inference |
| Cerebrolysin | 5 to <10 mg | 2 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Cerebrolysin | 10 to <25 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Cerebrolysin | 25 to <50 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Cerebrolysin | 50 to <100 mg | 3 | 3 | 3/3 (100.0%) | 0/3 (0.0%) | too sparse for inference |
| Cerebrolysin | >=100 mg | 6 | 5 | 5/5 (100.0%) | 0/5 (0.0%) | too sparse for inference |
| Dihexa | <5 mg | 2 | 2 | 2/2 (100.0%) | 0/2 (0.0%) | too sparse for inference |
| Dihexa | 5 to <10 mg | 5 | 5 | 4/5 (80.0%) | 2/5 (40.0%) | too sparse for inference |
| Dihexa | 10 to <25 mg | 10 | 10 | 8/10 (80.0%) | 2/10 (20.0%) | descriptive only |
| Dihexa | 25 to <50 mg | 2 | 2 | 1/2 (50.0%) | 2/2 (100.0%) | too sparse for inference |
| Dihexa | 50 to <100 mg | 1 | 1 | 0/1 (0.0%) | 1/1 (100.0%) | too sparse for inference |
| Lion's mane | <5 mg | 4 | 4 | 2/4 (50.0%) | 1/4 (25.0%) | too sparse for inference |
| Lion's mane | 5 to <10 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Lion's mane | 10 to <25 mg | 3 | 3 | 2/3 (66.7%) | 1/3 (33.3%) | too sparse for inference |
| Lion's mane | 25 to <50 mg | 3 | 3 | 0/3 (0.0%) | 1/3 (33.3%) | too sparse for inference |
| Lion's mane | >=100 mg | 26 | 24 | 18/24 (75.0%) | 7/24 (29.2%) | descriptive only |
| NSI-189 | <5 mg | 2 | 2 | 1/2 (50.0%) | 0/2 (0.0%) | too sparse for inference |
| NSI-189 | 5 to <10 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| NSI-189 | 10 to <25 mg | 6 | 6 | 3/6 (50.0%) | 3/6 (50.0%) | too sparse for inference |
| NSI-189 | 25 to <50 mg | 7 | 6 | 6/6 (100.0%) | 1/6 (16.7%) | too sparse for inference |
| NSI-189 | 50 to <100 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| NSI-189 | >=100 mg | 6 | 5 | 4/5 (80.0%) | 1/5 (20.0%) | too sparse for inference |
| Selank | <5 mg | 27 | 22 | 16/22 (72.7%) | 3/22 (13.6%) | descriptive only |
| Selank | 5 to <10 mg | 6 | 5 | 4/5 (80.0%) | 1/5 (20.0%) | too sparse for inference |
| Selank | 10 to <25 mg | 6 | 5 | 5/5 (100.0%) | 0/5 (0.0%) | too sparse for inference |
| Selank | 25 to <50 mg | 2 | 2 | 2/2 (100.0%) | 1/2 (50.0%) | too sparse for inference |
| Selank | 50 to <100 mg | 3 | 3 | 2/3 (66.7%) | 1/3 (33.3%) | too sparse for inference |
| Selank | >=100 mg | 8 | 8 | 7/8 (87.5%) | 0/8 (0.0%) | too sparse for inference |
| Semax | <5 mg | 29 | 26 | 19/26 (73.1%) | 10/26 (38.5%) | descriptive only |
| Semax | 5 to <10 mg | 7 | 7 | 7/7 (100.0%) | 0/7 (0.0%) | too sparse for inference |
| Semax | 10 to <25 mg | 8 | 7 | 7/7 (100.0%) | 0/7 (0.0%) | too sparse for inference |
| Semax | 25 to <50 mg | 1 | 1 | 0/1 (0.0%) | 1/1 (100.0%) | too sparse for inference |
| Semax | 50 to <100 mg | 8 | 7 | 7/7 (100.0%) | 0/7 (0.0%) | too sparse for inference |
| Semax | >=100 mg | 20 | 17 | 15/17 (88.2%) | 4/17 (23.5%) | descriptive only |

## Dose and route attribution checks

| Field | Status | Rows |
|---|---|---|
| Dose | corroborated | 172 |
| Dose | unsupported | 214 |
| Route | corroborated | 264 |
| Route | unsupported | 177 |

## Dose-stratified side-effect reporting

Side-effect reporting is joined by hashed author and compound across all of that author's reports. The denominator is every distinct author in the dose or route bucket. Classifier coverage shows how many denominator authors also had a retained comparator report. These are cross-report associations, not administration-event links, incidence estimates, or dose-response evidence. Dose and route rows are included only when the extracted value and compound were found near each other in the same source segment.

| Compound | Dose band | Observations | Authors | Classifier coverage | Any side effect | Leading mapped effects |
|---|---|---|---|---|---|---|
| 4'-DMA | 10 to <25 mg | 3 | 3 | 2/3 | 0/3 (0.0%; 95% CI 0.0% to 56.2%) | none mapped |
| 4'-DMA | 25 to <50 mg | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | cognitive or perceptual disturbance: 1/1 (100.0%); crash or rebound: 1/1 (100.0%); hair loss or thinning: 1/1 (100.0%) |
| 7,8-DHF | 10 to <25 mg | 2 | 2 | 2/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | anxiety or panic: 1/2 (50.0%); cognitive or perceptual disturbance: 1/2 (50.0%) |
| 7,8-DHF | 50 to <100 mg | 2 | 2 | 1/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | activation or irritability: 1/2 (50.0%); anxiety or panic: 1/2 (50.0%) |
| 9-MBC | 25 to <50 mg | 2 | 2 | 1/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | activation or irritability: 1/2 (50.0%); insomnia or sleep disruption: 1/2 (50.0%) |
| 9-MBC | 50 to <100 mg | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | activation or irritability: 1/1 (100.0%); insomnia or sleep disruption: 1/1 (100.0%) |
| BPC-157 | <5 mg | 3 | 3 | 2/3 | 0/3 (0.0%; 95% CI 0.0% to 56.2%) | none mapped |
| BPC-157 | 10 to <25 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Cerebrolysin | 5 to <10 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Cerebrolysin | 10 to <25 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Dihexa | <5 mg | 3 | 3 | 3/3 | 2/3 (66.7%; 95% CI 20.8% to 93.9%) | none mapped |
| Dihexa | 5 to <10 mg | 7 | 7 | 7/7 | 3/7 (42.9%; 95% CI 15.8% to 75.0%) | depressed or flattened mood: 2/7 (28.6%); insomnia or sleep disruption: 1/7 (14.3%) |
| Dihexa | 10 to <25 mg | 15 | 13 | 13/13 | 6/13 (46.2%; 95% CI 23.2% to 70.9%) | insomnia or sleep disruption: 2/13 (15.4%); activation or irritability: 1/13 (7.7%); appetite change: 1/13 (7.7%) |
| Dihexa | 25 to <50 mg | 2 | 2 | 1/2 | 0/2 (0.0%; 95% CI 0.0% to 65.8%) | none mapped |
| Lion's mane | >=100 mg | 25 | 24 | 24/24 | 4/24 (16.7%; 95% CI 6.7% to 35.9%) | cognitive or perceptual disturbance: 2/24 (8.3%); headache or migraine: 1/24 (4.2%) |
| NSI-189 | <5 mg | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | cognitive or perceptual disturbance: 1/1 (100.0%) |
| NSI-189 | 5 to <10 mg | 2 | 2 | 2/2 | 2/2 (100.0%; 95% CI 34.2% to 100.0%) | activation or irritability: 1/2 (50.0%); anxiety or panic: 1/2 (50.0%); cognitive or perceptual disturbance: 1/2 (50.0%) |
| NSI-189 | 10 to <25 mg | 6 | 5 | 5/5 | 3/5 (60.0%; 95% CI 23.1% to 88.2%) | anxiety or panic: 2/5 (40.0%); cognitive or perceptual disturbance: 2/5 (40.0%); activation or irritability: 1/5 (20.0%) |
| NSI-189 | 25 to <50 mg | 11 | 11 | 11/11 | 3/11 (27.3%; 95% CI 9.7% to 56.6%) | insomnia or sleep disruption: 2/11 (18.2%); activation or irritability: 1/11 (9.1%) |
| NSI-189 | >=100 mg | 2 | 2 | 2/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | cognitive or perceptual disturbance: 1/2 (50.0%); sexual: 1/2 (50.0%); tolerance or short duration: 1/2 (50.0%) |
| Selank | <5 mg | 27 | 24 | 22/24 | 4/24 (16.7%; 95% CI 6.7% to 35.9%) | insomnia or sleep disruption: 2/24 (8.3%); hair loss or thinning: 1/24 (4.2%) |
| Selank | 10 to <25 mg | 3 | 3 | 3/3 | 0/3 (0.0%; 95% CI 0.0% to 56.2%) | none mapped |
| Semax | <5 mg | 48 | 43 | 42/43 | 13/43 (30.2%; 95% CI 18.6% to 45.1%) | cognitive or perceptual disturbance: 3/43 (7.0%); depressed or flattened mood: 3/43 (7.0%); insomnia or sleep disruption: 3/43 (7.0%) |
| Semax | 50 to <100 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Semax | >=100 mg | 2 | 2 | 2/2 | 0/2 (0.0%; 95% CI 0.0% to 65.8%) | none mapped |

## Route-stratified side-effect reporting

Side-effect reporting is joined by hashed author and compound across all of that author's reports. The denominator is every distinct author in the dose or route bucket. Classifier coverage shows how many denominator authors also had a retained comparator report. These are cross-report associations, not administration-event links, incidence estimates, or dose-response evidence. Dose and route rows are included only when the extracted value and compound were found near each other in the same source segment.

| Compound | Route family | Observations | Authors | Classifier coverage | Any side effect | Leading mapped effects |
|---|---|---|---|---|---|---|
| 4'-DMA | oral mucosal | 5 | 5 | 5/5 | 2/5 (40.0%; 95% CI 11.8% to 76.9%) | cognitive or perceptual disturbance: 1/5 (20.0%); crash or rebound: 1/5 (20.0%); hair loss or thinning: 1/5 (20.0%) |
| 4'-DMA | swallowed oral | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| 7,8-DHF | nasal mucosal | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| 7,8-DHF | oral mucosal | 6 | 6 | 6/6 | 4/6 (66.7%; 95% CI 30.0% to 90.3%) | anxiety or panic: 2/6 (33.3%); cognitive or perceptual disturbance: 2/6 (33.3%); insomnia or sleep disruption: 1/6 (16.7%) |
| 7,8-DHF | swallowed oral | 2 | 2 | 2/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | depressed or flattened mood: 1/2 (50.0%); insomnia or sleep disruption: 1/2 (50.0%) |
| 9-MBC | oral mucosal | 3 | 3 | 2/3 | 1/3 (33.3%; 95% CI 6.1% to 79.2%) | activation or irritability: 1/3 (33.3%); insomnia or sleep disruption: 1/3 (33.3%) |
| 9-MBC | swallowed oral | 2 | 2 | 2/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | none mapped |
| BPC-157 | nasal mucosal | 6 | 6 | 6/6 | 0/6 (0.0%; 95% CI 0.0% to 39.0%) | none mapped |
| BPC-157 | oral mucosal | 2 | 2 | 2/2 | 0/2 (0.0%; 95% CI 0.0% to 65.8%) | none mapped |
| BPC-157 | parenteral | 7 | 7 | 6/7 | 0/7 (0.0%; 95% CI 0.0% to 35.4%) | none mapped |
| BPC-157 | swallowed oral | 4 | 4 | 4/4 | 2/4 (50.0%; 95% CI 15.0% to 85.0%) | depressed or flattened mood: 2/4 (50.0%); anxiety or panic: 1/4 (25.0%) |
| Cerebrolysin | nasal mucosal | 12 | 12 | 11/12 | 3/12 (25.0%; 95% CI 8.9% to 53.2%) | cognitive or perceptual disturbance: 1/12 (8.3%); insomnia or sleep disruption: 1/12 (8.3%) |
| Cerebrolysin | parenteral | 32 | 30 | 26/30 | 6/30 (20.0%; 95% CI 9.5% to 37.3%) | anxiety or panic: 1/30 (3.3%); insomnia or sleep disruption: 1/30 (3.3%) |
| Dihexa | dermal | 12 | 12 | 9/12 | 7/12 (58.3%; 95% CI 32.0% to 80.7%) | depressed or flattened mood: 1/12 (8.3%); insomnia or sleep disruption: 1/12 (8.3%) |
| Dihexa | nasal mucosal | 5 | 5 | 4/5 | 1/5 (20.0%; 95% CI 3.6% to 62.4%) | none mapped |
| Dihexa | oral mucosal | 4 | 4 | 4/4 | 2/4 (50.0%; 95% CI 15.0% to 85.0%) | insomnia or sleep disruption: 1/4 (25.0%) |
| Dihexa | parenteral | 2 | 2 | 2/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | none mapped |
| Dihexa | swallowed oral | 11 | 11 | 10/11 | 7/11 (63.6%; 95% CI 35.4% to 84.8%) | activation or irritability: 2/11 (18.2%); appetite change: 1/11 (9.1%); depressed or flattened mood: 1/11 (9.1%) |
| NSI-189 | nasal mucosal | 2 | 2 | 2/2 | 2/2 (100.0%; 95% CI 34.2% to 100.0%) | activation or irritability: 1/2 (50.0%); anxiety or panic: 1/2 (50.0%); headache or migraine: 1/2 (50.0%) |
| NSI-189 | oral mucosal | 4 | 4 | 3/4 | 1/4 (25.0%; 95% CI 4.6% to 69.9%) | anxiety or panic: 1/4 (25.0%) |
| NSI-189 | swallowed oral | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | activation or irritability: 1/1 (100.0%); insomnia or sleep disruption: 1/1 (100.0%) |
| Selank | nasal mucosal | 44 | 44 | 38/44 | 5/44 (11.4%; 95% CI 5.0% to 24.0%) | headache or migraine: 2/44 (4.5%); hair loss or thinning: 1/44 (2.3%); insomnia or sleep disruption: 1/44 (2.3%) |
| Selank | parenteral | 9 | 9 | 9/9 | 0/9 (0.0%; 95% CI 0.0% to 29.9%) | none mapped |
| Semax | nasal mucosal | 71 | 70 | 67/70 | 19/70 (27.1%; 95% CI 18.1% to 38.5%) | insomnia or sleep disruption: 4/70 (5.7%); cognitive or perceptual disturbance: 3/70 (4.3%); depressed or flattened mood: 3/70 (4.3%) |
| Semax | oral mucosal | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | none mapped |
| Semax | parenteral | 15 | 15 | 13/15 | 4/15 (26.7%; 95% CI 10.9% to 52.0%) | insomnia or sleep disruption: 3/15 (20.0%); anxiety or panic: 1/15 (6.7%); cognitive or perceptual disturbance: 1/15 (6.7%) |

## Symptom-linked outcomes

Explicit PEM target coverage: 1 treatment-linked outcome entry. General fatigue remains a separate endpoint bucket.

| Compound | Target symptom | Authors | Helped | No effect | Worsened |
|---|---|---|---|---|---|
| 4'-DMA | mood or depression | 6 | 5 | 0 | 0 |
| 4'-DMA | energy or motivation | 5 | 5 | 0 | 0 |
| 4'-DMA | other specified result | 3 | 0 | 0 | 3 |
| 4'-DMA | cognition or brain fog | 1 | 1 | 0 | 0 |
| 4'-DMA | focus or attention | 1 | 1 | 0 | 0 |
| 4'-DMA | general fatigue | 1 | 1 | 0 | 0 |
| 4'-DMA | memory or learning | 1 | 1 | 0 | 0 |
| 7,8-DHF | mood or depression | 10 | 7 | 0 | 3 |
| 7,8-DHF | other specified result | 10 | 6 | 0 | 5 |
| 7,8-DHF | anxiety or stress | 7 | 4 | 0 | 5 |
| 7,8-DHF | cognition or brain fog | 4 | 3 | 0 | 2 |
| 7,8-DHF | energy or motivation | 4 | 4 | 0 | 0 |
| 7,8-DHF | sleep or wakefulness | 4 | 1 | 0 | 3 |
| 7,8-DHF | focus or attention | 3 | 2 | 0 | 1 |
| 7,8-DHF | general fatigue | 3 | 1 | 0 | 2 |
| 7,8-DHF | pain or neurologic symptoms | 1 | 0 | 0 | 1 |
| 7,8-DHF | social functioning | 1 | 0 | 0 | 1 |
| 9-MBC | other specified result | 6 | 0 | 2 | 6 |
| 9-MBC | energy or motivation | 4 | 5 | 0 | 0 |
| 9-MBC | mood or depression | 4 | 4 | 0 | 0 |
| 9-MBC | general fatigue | 2 | 2 | 0 | 0 |
| 9-MBC | cardiovascular or autonomic | 1 | 0 | 0 | 1 |
| 9-MBC | cognition or brain fog | 1 | 1 | 0 | 0 |
| 9-MBC | gastrointestinal | 1 | 1 | 0 | 0 |
| 9-MBC | memory or learning | 1 | 0 | 0 | 1 |
| 9-MBC | sexual function | 1 | 1 | 0 | 0 |
| BPC-157 | mood or depression | 18 | 2 | 1 | 13 |
| BPC-157 | other specified result | 17 | 14 | 1 | 5 |
| BPC-157 | pain or neurologic symptoms | 7 | 6 | 1 | 0 |
| BPC-157 | general fatigue | 4 | 1 | 0 | 3 |
| BPC-157 | anxiety or stress | 3 | 2 | 0 | 1 |
| BPC-157 | energy or motivation | 3 | 2 | 0 | 1 |
| BPC-157 | gastrointestinal | 3 | 4 | 0 | 0 |
| BPC-157 | neuroprotection or recovery | 2 | 2 | 0 | 0 |
| BPC-157 | sleep or wakefulness | 2 | 1 | 0 | 1 |
| BPC-157 | cognition or brain fog | 1 | 1 | 0 | 0 |
| BPC-157 | memory or learning | 1 | 0 | 1 | 0 |
| BPC-157 | post-exertional malaise | 1 | 0 | 1 | 0 |
| BPC-157 | sexual function | 1 | 0 | 0 | 1 |
| BPC-157 | stimulant recovery or reduction | 1 | 0 | 0 | 1 |
| Cerebrolysin | other specified result | 30 | 36 | 0 | 5 |
| Cerebrolysin | cognition or brain fog | 17 | 14 | 0 | 4 |
| Cerebrolysin | mood or depression | 11 | 13 | 0 | 0 |
| Cerebrolysin | memory or learning | 6 | 6 | 0 | 0 |
| Cerebrolysin | sleep or wakefulness | 6 | 5 | 1 | 1 |
| Cerebrolysin | anxiety or stress | 5 | 4 | 0 | 1 |
| Cerebrolysin | pain or neurologic symptoms | 4 | 1 | 0 | 3 |
| Cerebrolysin | energy or motivation | 3 | 3 | 0 | 0 |
| Cerebrolysin | focus or attention | 3 | 2 | 0 | 0 |
| Cerebrolysin | general fatigue | 2 | 1 | 0 | 1 |
| Cerebrolysin | neuroprotection or recovery | 2 | 2 | 0 | 0 |
| Cerebrolysin | hair or skin | 1 | 0 | 0 | 1 |
| Cerebrolysin | social functioning | 1 | 1 | 0 | 0 |
| Dihexa | other specified result | 14 | 16 | 0 | 4 |
| Dihexa | memory or learning | 10 | 11 | 0 | 0 |
| Dihexa | cognition or brain fog | 8 | 6 | 1 | 2 |
| Dihexa | mood or depression | 7 | 5 | 1 | 1 |
| Dihexa | focus or attention | 6 | 3 | 0 | 3 |
| Dihexa | anxiety or stress | 5 | 3 | 0 | 2 |
| Dihexa | energy or motivation | 3 | 2 | 0 | 1 |
| Dihexa | sleep or wakefulness | 3 | 0 | 0 | 3 |
| Dihexa | neuroprotection or recovery | 1 | 1 | 0 | 0 |
| Dihexa | pain or neurologic symptoms | 1 | 0 | 0 | 1 |
| Lion's mane | other specified result | 49 | 23 | 2 | 23 |
| Lion's mane | cognition or brain fog | 38 | 31 | 1 | 8 |
| Lion's mane | anxiety or stress | 25 | 14 | 0 | 13 |
| Lion's mane | memory or learning | 22 | 24 | 0 | 0 |
| Lion's mane | mood or depression | 20 | 10 | 1 | 12 |
| Lion's mane | focus or attention | 18 | 19 | 0 | 0 |
| Lion's mane | pain or neurologic symptoms | 16 | 3 | 1 | 11 |
| Lion's mane | sleep or wakefulness | 8 | 2 | 0 | 7 |
| Lion's mane | energy or motivation | 7 | 6 | 0 | 2 |
| Lion's mane | sexual function | 7 | 0 | 0 | 7 |
| Lion's mane | gastrointestinal | 3 | 1 | 0 | 2 |
| Lion's mane | cardiovascular or autonomic | 2 | 0 | 0 | 2 |
| Lion's mane | general fatigue | 2 | 2 | 0 | 0 |
| Lion's mane | hair or skin | 2 | 1 | 0 | 1 |
| Lion's mane | social functioning | 1 | 1 | 0 | 0 |
| NSI-189 | mood or depression | 29 | 30 | 1 | 1 |
| NSI-189 | other specified result | 16 | 10 | 0 | 13 |
| NSI-189 | anxiety or stress | 10 | 6 | 1 | 4 |
| NSI-189 | sleep or wakefulness | 8 | 3 | 0 | 5 |
| NSI-189 | cognition or brain fog | 7 | 4 | 0 | 4 |
| NSI-189 | energy or motivation | 5 | 6 | 0 | 0 |
| NSI-189 | focus or attention | 5 | 3 | 0 | 2 |
| NSI-189 | memory or learning | 5 | 6 | 0 | 0 |
| NSI-189 | general fatigue | 3 | 3 | 0 | 0 |
| NSI-189 | pain or neurologic symptoms | 3 | 0 | 0 | 3 |
| NSI-189 | sexual function | 1 | 0 | 0 | 1 |
| Selank | anxiety or stress | 75 | 70 | 4 | 3 |
| Selank | mood or depression | 21 | 18 | 0 | 6 |
| Selank | other specified result | 20 | 18 | 1 | 6 |
| Selank | focus or attention | 13 | 12 | 1 | 0 |
| Selank | sleep or wakefulness | 10 | 9 | 0 | 1 |
| Selank | cognition or brain fog | 8 | 7 | 1 | 0 |
| Selank | energy or motivation | 8 | 9 | 0 | 0 |
| Selank | memory or learning | 6 | 6 | 0 | 0 |
| Selank | pain or neurologic symptoms | 5 | 1 | 0 | 4 |
| Selank | general fatigue | 2 | 1 | 0 | 1 |
| Selank | social functioning | 2 | 2 | 0 | 0 |
| Selank | hair or skin | 1 | 0 | 0 | 1 |
| Selank | neuroprotection or recovery | 1 | 1 | 0 | 0 |
| Semax | cognition or brain fog | 49 | 44 | 2 | 5 |
| Semax | other specified result | 47 | 35 | 0 | 17 |
| Semax | focus or attention | 45 | 44 | 1 | 0 |
| Semax | mood or depression | 33 | 27 | 0 | 8 |
| Semax | energy or motivation | 27 | 27 | 2 | 0 |
| Semax | anxiety or stress | 24 | 16 | 1 | 9 |
| Semax | memory or learning | 11 | 10 | 0 | 2 |
| Semax | sleep or wakefulness | 11 | 1 | 0 | 10 |
| Semax | general fatigue | 8 | 3 | 0 | 5 |
| Semax | hair or skin | 5 | 0 | 0 | 5 |
| Semax | pain or neurologic symptoms | 5 | 1 | 0 | 4 |
| Semax | social functioning | 2 | 2 | 0 | 0 |
| Semax | sexual function | 1 | 1 | 0 | 0 |
| Semax | stimulant recovery or reduction | 1 | 1 | 0 | 0 |

## Interpretation boundaries

- Keep 7,8-DHF and 4'-DMA-7,8-DHF separate.
- Treat PEM as distinct from general fatigue when it is explicitly stated.
- Do not infer that dose, route, outcome, and side effect belong to one administration event unless the source explicitly links them.
- Use matched-author results as a sensitivity analysis, not as the primary estimand, because overlap can be sparse.
- The direct TrkB-agonist interpretation of 7,8-DHF remains disputed; the cohort is tiered rather than presented as one homogeneous mechanism class.

## Reproducibility

- Sentiment database: `sentiment.db`; SHA-256 `bfd47703240b1bf3afa2e3fe32e01a03ed03a73be041e91d51676ebb4dbf6406`
- Study database: `combined.db`; SHA-256 `a593595e57d70702eb8684b4de2ae69fbbcb436d975b5ff00cbd6f65cc46cace`
- Cohort configuration: `comparator_cohort.json`; SHA-256 `c420e12d450b0b2637983121cd1db06c56c62e9567e002fb257f01887cfc8063`
