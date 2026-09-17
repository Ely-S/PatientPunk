# 7,8-DHF comparator-cohort analysis: r/Nootropics

This report answers the OMF collaboration questions with aggregate r/Nootropics self-reports. It measures reporting patterns, not efficacy, adverse-event incidence, causal dose-response, or medical safety. Every comparator uses the same source population, classifier, context handling, and one-vote-per-author rule.

## Extraction coverage and provenance

This is the legacy cohort, so it predates the complete run-manifest contract used
for the eight new cohorts. Its derived corpus manifest is available externally and
has SHA-256 `d03e57f1a25762d1c63d13a16b55ce4debe59d061c70cfe383cbef1964f101b2`.
The comments source still at the location recorded by that manifest has SHA-256
`c5f0b64d0f0a6fdae3348d0b7e07e95a1ed778147a7ca4c7d85b5879e16e5882`.
The raw posts source recorded by the legacy manifest is no longer present at that
location, so its original source hash cannot be independently recovered. The
aggregate results remain reproducible from the externally retained databases whose
hashes are listed below.

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
| 7,8-DHF | target | target | 279 | 199 | 71 | 9 | 0 | 71.3% | 65.8% to 76.3% | descriptive only |
| 4'-DMA-7,8-DHF | chemical analogue | primary | 88 | 65 | 22 | 0 | 1 | 73.9% | 63.8% to 81.9% | descriptive only |
| Semax | BDNF/TrkB related | primary | 2133 | 1425 | 631 | 72 | 5 | 66.8% | 64.8% to 68.8% | descriptive only |
| Cerebrolysin | BDNF/TrkB related | primary | 572 | 389 | 160 | 22 | 1 | 68.0% | 64.1% to 71.7% | descriptive only |
| Selank | BDNF/TrkB related | primary | 992 | 671 | 294 | 25 | 2 | 67.6% | 64.7% to 70.5% | descriptive only |
| NSI-189 | broader neurotrophic | secondary | 879 | 525 | 291 | 63 | 0 | 59.7% | 56.4% to 62.9% | descriptive only |
| Dihexa | broader neurotrophic | secondary | 272 | 170 | 93 | 8 | 1 | 62.5% | 56.6% to 68.0% | descriptive only |
| Lion's mane | broader neurotrophic | secondary | 5215 | 3109 | 1821 | 266 | 19 | 59.6% | 58.3% to 60.9% | descriptive only |
| 9-MBC | broader neurotrophic | exploratory | 177 | 127 | 43 | 7 | 0 | 71.8% | 64.7% to 77.9% | descriptive only |
| BPC-157 | negative control | control | 515 | 351 | 148 | 16 | 0 | 68.2% | 64.0% to 72.0% | descriptive only |

## Comparisons with 7,8-DHF

The positive-rate difference is 7,8-DHF minus comparator, so positive values favor a higher 7,8-DHF positive-reporting share. Fisher tests use mutually exclusive authors and report 7,8-DHF/comparator odds ratios. BH q-values are corrected across comparators. Matched results use authors who reported both compounds; the discordant column is 7,8-DHF-only positive / comparator-only positive. Matched q-values are corrected separately.

| Comparator | 7,8-DHF minus comparator | Exclusive OR | Exclusive p | Exclusive BH q | Exclusive 7,8-DHF authors | Exclusive comparator authors | Matched authors | Discordant | Matched p | Matched BH q | Inference status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4'-DMA-7,8-DHF | -2.5 points | 1.08 | 0.8439 | 0.9119 | 225 | 34 | 54 | 2/1 | 1.0000 | 1.0000 | sensitivity analysis |
| Semax | +4.5 points | 1.17 | 0.3489 | 0.5234 | 203 | 2057 | 76 | 12/11 | 1.0000 | 1.0000 | sensitivity analysis |
| Cerebrolysin | +3.3 points | 1.25 | 0.2169 | 0.3905 | 254 | 547 | 25 | 3/6 | 0.5078 | 0.9141 | sensitivity analysis |
| Selank | +3.7 points | 1.25 | 0.1843 | 0.3905 | 237 | 950 | 42 | 8/10 | 0.8145 | 1.0000 | sensitivity analysis |
| NSI-189 | +11.6 points | 1.63 | 0.0025 | 0.0115 | 227 | 827 | 52 | 12/3 | 0.0352 | 0.2396 | sensitivity analysis |
| Dihexa | +8.8 points | 1.45 | 0.0560 | 0.1679 | 249 | 242 | 30 | 6/2 | 0.2891 | 0.6504 | sensitivity analysis |
| Lion's mane | +11.7 points | 1.83 | 0.0002 | 0.0021 | 186 | 5122 | 93 | 26/13 | 0.0533 | 0.2396 | sensitivity analysis |
| 9-MBC | -0.4 points | 1.03 | 0.9119 | 0.9119 | 258 | 156 | 21 | 1/2 | 1.0000 | 1.0000 | sensitivity analysis |
| BPC-157 | +3.2 points | 1.10 | 0.6174 | 0.7938 | 256 | 492 | 23 | 6/2 | 0.2891 | 0.6504 | sensitivity analysis |

## Treatment-linked side-effect signals

These are the eight most frequently reported canonical effects per compound, deduplicated by author within each effect. Because every pipeline row is linked to one target treatment, the former 7,8-DHF / 4'-DMA blending is removed. Counts remain reporting proportions, not incidence.

| Compound | Canonical effect | Safety domain | Authors | Share of classified authors | Mentions |
|---|---|---|---|---|---|
| 7,8-DHF | other reported effect | other | 41 | 14.7% | 74 |
| 7,8-DHF | insomnia or sleep disruption | sleep | 31 | 11.1% | 42 |
| 7,8-DHF | cognitive or perceptual disturbance | neurologic | 20 | 7.2% | 35 |
| 7,8-DHF | activation or irritability | activation or anxiety | 17 | 6.1% | 24 |
| 7,8-DHF | anxiety or panic | activation or anxiety | 17 | 6.1% | 19 |
| 7,8-DHF | headache or migraine | neurologic | 15 | 5.4% | 20 |
| 7,8-DHF | depressed or flattened mood | mood | 12 | 4.3% | 18 |
| 7,8-DHF | cardiovascular or autonomic | cardiovascular or autonomic | 5 | 1.8% | 7 |
| 4'-DMA-7,8-DHF | other reported effect | other | 10 | 11.4% | 17 |
| 4'-DMA-7,8-DHF | insomnia or sleep disruption | sleep | 7 | 8.0% | 9 |
| 4'-DMA-7,8-DHF | anxiety or panic | activation or anxiety | 5 | 5.7% | 6 |
| 4'-DMA-7,8-DHF | cognitive or perceptual disturbance | neurologic | 5 | 5.7% | 6 |
| 4'-DMA-7,8-DHF | activation or irritability | activation or anxiety | 4 | 4.5% | 7 |
| 4'-DMA-7,8-DHF | headache or migraine | neurologic | 3 | 3.4% | 3 |
| 4'-DMA-7,8-DHF | appetite change | appetite or weight | 1 | 1.1% | 1 |
| 4'-DMA-7,8-DHF | cardiovascular or autonomic | cardiovascular or autonomic | 1 | 1.1% | 2 |
| Semax | other reported effect | other | 522 | 24.5% | 1225 |
| Semax | insomnia or sleep disruption | sleep | 150 | 7.0% | 207 |
| Semax | anxiety or panic | activation or anxiety | 121 | 5.7% | 164 |
| Semax | cognitive or perceptual disturbance | neurologic | 118 | 5.5% | 172 |
| Semax | activation or irritability | activation or anxiety | 105 | 4.9% | 134 |
| Semax | hair loss or thinning | hair or skin | 92 | 4.3% | 194 |
| Semax | fatigue or sedation | fatigue or sedation | 82 | 3.8% | 112 |
| Semax | headache or migraine | neurologic | 75 | 3.5% | 97 |
| Cerebrolysin | other reported effect | other | 134 | 23.4% | 302 |
| Cerebrolysin | cognitive or perceptual disturbance | neurologic | 53 | 9.3% | 81 |
| Cerebrolysin | insomnia or sleep disruption | sleep | 43 | 7.5% | 52 |
| Cerebrolysin | fatigue or sedation | fatigue or sedation | 27 | 4.7% | 42 |
| Cerebrolysin | depressed or flattened mood | mood | 20 | 3.5% | 25 |
| Cerebrolysin | anxiety or panic | activation or anxiety | 13 | 2.3% | 22 |
| Cerebrolysin | headache or migraine | neurologic | 12 | 2.1% | 12 |
| Cerebrolysin | activation or irritability | activation or anxiety | 11 | 1.9% | 13 |
| Selank | other reported effect | other | 181 | 18.2% | 377 |
| Selank | anxiety or panic | activation or anxiety | 49 | 4.9% | 58 |
| Selank | fatigue or sedation | fatigue or sedation | 47 | 4.7% | 58 |
| Selank | insomnia or sleep disruption | sleep | 46 | 4.6% | 55 |
| Selank | cognitive or perceptual disturbance | neurologic | 43 | 4.3% | 62 |
| Selank | headache or migraine | neurologic | 27 | 2.7% | 38 |
| Selank | depressed or flattened mood | mood | 25 | 2.5% | 40 |
| Selank | activation or irritability | activation or anxiety | 20 | 2.0% | 22 |
| NSI-189 | other reported effect | other | 335 | 38.1% | 1088 |
| NSI-189 | anxiety or panic | activation or anxiety | 131 | 14.9% | 235 |
| NSI-189 | insomnia or sleep disruption | sleep | 85 | 9.7% | 138 |
| NSI-189 | cognitive or perceptual disturbance | neurologic | 61 | 6.9% | 86 |
| NSI-189 | activation or irritability | activation or anxiety | 52 | 5.9% | 76 |
| NSI-189 | headache or migraine | neurologic | 51 | 5.8% | 65 |
| NSI-189 | fatigue or sedation | fatigue or sedation | 50 | 5.7% | 79 |
| NSI-189 | depressed or flattened mood | mood | 35 | 4.0% | 43 |
| Dihexa | other reported effect | other | 95 | 34.9% | 225 |
| Dihexa | insomnia or sleep disruption | sleep | 16 | 5.9% | 22 |
| Dihexa | depressed or flattened mood | mood | 9 | 3.3% | 14 |
| Dihexa | cognitive or perceptual disturbance | neurologic | 8 | 2.9% | 11 |
| Dihexa | activation or irritability | activation or anxiety | 7 | 2.6% | 10 |
| Dihexa | anxiety or panic | activation or anxiety | 7 | 2.6% | 7 |
| Dihexa | fatigue or sedation | fatigue or sedation | 6 | 2.2% | 6 |
| Dihexa | headache or migraine | neurologic | 6 | 2.2% | 7 |
| Lion's mane | other reported effect | other | 1404 | 26.9% | 3171 |
| Lion's mane | insomnia or sleep disruption | sleep | 418 | 8.0% | 636 |
| Lion's mane | sexual | sexual | 390 | 7.5% | 652 |
| Lion's mane | anxiety or panic | activation or anxiety | 279 | 5.3% | 445 |
| Lion's mane | depressed or flattened mood | mood | 248 | 4.8% | 387 |
| Lion's mane | cognitive or perceptual disturbance | neurologic | 212 | 4.1% | 299 |
| Lion's mane | headache or migraine | neurologic | 165 | 3.2% | 227 |
| Lion's mane | fatigue or sedation | fatigue or sedation | 143 | 2.7% | 196 |
| 9-MBC | other reported effect | other | 62 | 35.0% | 133 |
| 9-MBC | cognitive or perceptual disturbance | neurologic | 16 | 9.0% | 24 |
| 9-MBC | anxiety or panic | activation or anxiety | 12 | 6.8% | 14 |
| 9-MBC | insomnia or sleep disruption | sleep | 12 | 6.8% | 14 |
| 9-MBC | cardiovascular or autonomic | cardiovascular or autonomic | 9 | 5.1% | 9 |
| 9-MBC | fatigue or sedation | fatigue or sedation | 7 | 4.0% | 8 |
| 9-MBC | headache or migraine | neurologic | 6 | 3.4% | 10 |
| 9-MBC | activation or irritability | activation or anxiety | 4 | 2.3% | 4 |
| BPC-157 | other reported effect | other | 126 | 24.5% | 279 |
| BPC-157 | fatigue or sedation | fatigue or sedation | 44 | 8.5% | 80 |
| BPC-157 | depressed or flattened mood | mood | 36 | 7.0% | 48 |
| BPC-157 | insomnia or sleep disruption | sleep | 24 | 4.7% | 35 |
| BPC-157 | anxiety or panic | activation or anxiety | 23 | 4.5% | 33 |
| BPC-157 | cognitive or perceptual disturbance | neurologic | 21 | 4.1% | 29 |
| BPC-157 | gastrointestinal | gastrointestinal | 13 | 2.5% | 22 |
| BPC-157 | headache or migraine | neurologic | 10 | 1.9% | 13 |

## Post-level compound, dose, and outcome links

This stricter view keeps only treatment-specific sentiment reports where exactly one quantitative mass dose appears near that compound in the same post or comment. Authors receive one vote per compound and dose band. It is descriptive and does not establish a dose-response relationship.

| Compound | Dose band | Posts | Authors | Positive authors | Side-effect authors | Inference status |
|---|---|---|---|---|---|---|
| 4'-DMA-7,8-DHF | <5 mg | 3 | 3 | 2/3 (66.7%) | 2/3 (66.7%) | too sparse for inference |
| 4'-DMA-7,8-DHF | 5 to <10 mg | 1 | 1 | 1/1 (100.0%) | 1/1 (100.0%) | too sparse for inference |
| 4'-DMA-7,8-DHF | 10 to <25 mg | 1 | 1 | 0/1 (0.0%) | 1/1 (100.0%) | too sparse for inference |
| 4'-DMA-7,8-DHF | 25 to <50 mg | 1 | 1 | 0/1 (0.0%) | 0/1 (0.0%) | too sparse for inference |
| 4'-DMA-7,8-DHF | >=100 mg | 2 | 2 | 2/2 (100.0%) | 0/2 (0.0%) | too sparse for inference |
| 7,8-DHF | <5 mg | 2 | 2 | 2/2 (100.0%) | 0/2 (0.0%) | too sparse for inference |
| 7,8-DHF | 5 to <10 mg | 5 | 5 | 4/5 (80.0%) | 2/5 (40.0%) | too sparse for inference |
| 7,8-DHF | 10 to <25 mg | 11 | 11 | 7/11 (63.6%) | 4/11 (36.4%) | descriptive only |
| 7,8-DHF | 25 to <50 mg | 12 | 12 | 9/12 (75.0%) | 3/12 (25.0%) | descriptive only |
| 7,8-DHF | 50 to <100 mg | 7 | 6 | 4/6 (66.7%) | 2/6 (33.3%) | too sparse for inference |
| 7,8-DHF | >=100 mg | 13 | 11 | 7/11 (63.6%) | 2/11 (18.2%) | descriptive only |
| 9-MBC | <5 mg | 2 | 2 | 1/2 (50.0%) | 1/2 (50.0%) | too sparse for inference |
| 9-MBC | 5 to <10 mg | 2 | 2 | 1/2 (50.0%) | 1/2 (50.0%) | too sparse for inference |
| 9-MBC | 10 to <25 mg | 10 | 9 | 6/9 (66.7%) | 4/9 (44.4%) | too sparse for inference |
| 9-MBC | 25 to <50 mg | 6 | 5 | 4/5 (80.0%) | 3/5 (60.0%) | too sparse for inference |
| 9-MBC | 50 to <100 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| 9-MBC | >=100 mg | 8 | 5 | 4/5 (80.0%) | 2/5 (40.0%) | too sparse for inference |
| BPC-157 | <5 mg | 44 | 38 | 26/38 (68.4%) | 12/38 (31.6%) | descriptive only |
| BPC-157 | 5 to <10 mg | 11 | 11 | 8/11 (72.7%) | 4/11 (36.4%) | descriptive only |
| BPC-157 | 10 to <25 mg | 13 | 13 | 9/13 (69.2%) | 3/13 (23.1%) | descriptive only |
| BPC-157 | 25 to <50 mg | 7 | 5 | 3/5 (60.0%) | 1/5 (20.0%) | too sparse for inference |
| BPC-157 | 50 to <100 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| BPC-157 | >=100 mg | 11 | 10 | 10/10 (100.0%) | 0/10 (0.0%) | descriptive only |
| Cerebrolysin | <5 mg | 7 | 5 | 4/5 (80.0%) | 3/5 (60.0%) | too sparse for inference |
| Cerebrolysin | 5 to <10 mg | 9 | 9 | 6/9 (66.7%) | 3/9 (33.3%) | too sparse for inference |
| Cerebrolysin | 10 to <25 mg | 10 | 9 | 7/9 (77.8%) | 0/9 (0.0%) | too sparse for inference |
| Cerebrolysin | 25 to <50 mg | 5 | 4 | 3/4 (75.0%) | 1/4 (25.0%) | too sparse for inference |
| Cerebrolysin | 50 to <100 mg | 4 | 4 | 3/4 (75.0%) | 1/4 (25.0%) | too sparse for inference |
| Cerebrolysin | >=100 mg | 18 | 16 | 13/16 (81.2%) | 4/16 (25.0%) | descriptive only |
| Dihexa | <5 mg | 8 | 6 | 6/6 (100.0%) | 1/6 (16.7%) | too sparse for inference |
| Dihexa | 5 to <10 mg | 12 | 11 | 10/11 (90.9%) | 5/11 (45.5%) | descriptive only |
| Dihexa | 10 to <25 mg | 14 | 11 | 8/11 (72.7%) | 5/11 (45.5%) | descriptive only |
| Dihexa | 25 to <50 mg | 14 | 8 | 5/8 (62.5%) | 4/8 (50.0%) | too sparse for inference |
| Dihexa | 50 to <100 mg | 5 | 3 | 1/3 (33.3%) | 2/3 (66.7%) | too sparse for inference |
| Dihexa | >=100 mg | 15 | 14 | 9/14 (64.3%) | 3/14 (21.4%) | descriptive only |
| Lion's mane | <5 mg | 26 | 26 | 18/26 (69.2%) | 12/26 (46.2%) | descriptive only |
| Lion's mane | 5 to <10 mg | 8 | 8 | 6/8 (75.0%) | 1/8 (12.5%) | too sparse for inference |
| Lion's mane | 10 to <25 mg | 18 | 18 | 12/18 (66.7%) | 6/18 (33.3%) | descriptive only |
| Lion's mane | 25 to <50 mg | 14 | 14 | 8/14 (57.1%) | 3/14 (21.4%) | descriptive only |
| Lion's mane | 50 to <100 mg | 10 | 10 | 6/10 (60.0%) | 4/10 (40.0%) | descriptive only |
| Lion's mane | >=100 mg | 543 | 472 | 312/472 (66.1%) | 181/472 (38.3%) | descriptive only |
| NSI-189 | <5 mg | 7 | 7 | 5/7 (71.4%) | 2/7 (28.6%) | too sparse for inference |
| NSI-189 | 5 to <10 mg | 10 | 8 | 6/8 (75.0%) | 4/8 (50.0%) | too sparse for inference |
| NSI-189 | 10 to <25 mg | 58 | 51 | 25/51 (49.0%) | 31/51 (60.8%) | descriptive only |
| NSI-189 | 25 to <50 mg | 102 | 81 | 48/81 (59.3%) | 47/81 (58.0%) | descriptive only |
| NSI-189 | 50 to <100 mg | 21 | 21 | 11/21 (52.4%) | 11/21 (52.4%) | descriptive only |
| NSI-189 | >=100 mg | 34 | 22 | 15/22 (68.2%) | 10/22 (45.5%) | descriptive only |
| Selank | <5 mg | 109 | 88 | 66/88 (75.0%) | 24/88 (27.3%) | descriptive only |
| Selank | 5 to <10 mg | 8 | 8 | 4/8 (50.0%) | 4/8 (50.0%) | too sparse for inference |
| Selank | 10 to <25 mg | 8 | 8 | 7/8 (87.5%) | 2/8 (25.0%) | too sparse for inference |
| Selank | 25 to <50 mg | 12 | 11 | 9/11 (81.8%) | 1/11 (9.1%) | descriptive only |
| Selank | 50 to <100 mg | 9 | 9 | 7/9 (77.8%) | 1/9 (11.1%) | too sparse for inference |
| Selank | >=100 mg | 33 | 33 | 21/33 (63.6%) | 9/33 (27.3%) | descriptive only |
| Semax | <5 mg | 277 | 206 | 148/206 (71.8%) | 86/206 (41.7%) | descriptive only |
| Semax | 5 to <10 mg | 18 | 18 | 13/18 (72.2%) | 4/18 (22.2%) | descriptive only |
| Semax | 10 to <25 mg | 47 | 41 | 28/41 (68.3%) | 11/41 (26.8%) | descriptive only |
| Semax | 25 to <50 mg | 33 | 31 | 25/31 (80.6%) | 8/31 (25.8%) | descriptive only |
| Semax | 50 to <100 mg | 26 | 21 | 17/21 (81.0%) | 4/21 (19.0%) | descriptive only |
| Semax | >=100 mg | 84 | 72 | 52/72 (72.2%) | 17/72 (23.6%) | descriptive only |

## Dose and route attribution checks

| Field | Status | Rows |
|---|---|---|
| Dose | corroborated | 87 |
| Dose | unsupported | 54 |
| Route | corroborated | 63 |
| Route | unsupported | 28 |

## Dose-stratified side-effect reporting

Side-effect reporting is joined by hashed author and compound across all of that author's reports. The denominator is every distinct author in the dose or route bucket. Classifier coverage shows how many denominator authors also had a retained comparator report. These are cross-report associations, not administration-event links, incidence estimates, or dose-response evidence. Dose and route rows are included only when the extracted value and compound were found near each other in the same source segment.

| Compound | Dose band | Observations | Authors | Classifier coverage | Any side effect | Leading mapped effects |
|---|---|---|---|---|---|---|
| 4'-DMA | <5 mg | 3 | 2 | 2/2 | 2/2 (100.0%; 95% CI 34.2% to 100.0%) | activation or irritability: 1/2 (50.0%); anxiety or panic: 1/2 (50.0%); cognitive or perceptual disturbance: 1/2 (50.0%) |
| 4'-DMA | 5 to <10 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| 4'-DMA | 10 to <25 mg | 5 | 5 | 2/5 | 1/5 (20.0%; 95% CI 3.6% to 62.4%) | activation or irritability: 1/5 (20.0%); cognitive or perceptual disturbance: 1/5 (20.0%) |
| 4'-DMA | 25 to <50 mg | 2 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| 7,8-DHF | <5 mg | 2 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | insomnia or sleep disruption: 1/1 (100.0%) |
| 7,8-DHF | 5 to <10 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| 7,8-DHF | 10 to <25 mg | 11 | 11 | 10/11 | 4/11 (36.4%; 95% CI 15.2% to 64.6%) | cognitive or perceptual disturbance: 2/11 (18.2%); headache or migraine: 2/11 (18.2%); activation or irritability: 1/11 (9.1%) |
| 7,8-DHF | 25 to <50 mg | 20 | 19 | 14/19 | 7/19 (36.8%; 95% CI 19.1% to 59.0%) | headache or migraine: 3/19 (15.8%); insomnia or sleep disruption: 2/19 (10.5%); appetite change: 1/19 (5.3%) |
| 7,8-DHF | 50 to <100 mg | 7 | 7 | 6/7 | 5/7 (71.4%; 95% CI 35.9% to 91.8%) | headache or migraine: 4/7 (57.1%); cognitive or perceptual disturbance: 3/7 (42.9%); activation or irritability: 1/7 (14.3%) |
| 7,8-DHF | >=100 mg | 3 | 3 | 2/3 | 2/3 (66.7%; 95% CI 20.8% to 93.9%) | headache or migraine: 2/3 (66.7%); cognitive or perceptual disturbance: 1/3 (33.3%) |
| 9-MBC | 5 to <10 mg | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | none mapped |
| 9-MBC | 10 to <25 mg | 3 | 2 | 2/2 | 2/2 (100.0%; 95% CI 34.2% to 100.0%) | none mapped |
| Dihexa | 10 to <25 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Dihexa | 25 to <50 mg | 2 | 2 | 2/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | fatigue or sedation: 1/2 (50.0%) |
| Lion's mane | >=100 mg | 10 | 9 | 8/9 | 1/9 (11.1%; 95% CI 2.0% to 43.5%) | hair loss or thinning: 1/9 (11.1%) |
| NSI-189 | 5 to <10 mg | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | anxiety or panic: 1/1 (100.0%) |
| NSI-189 | 10 to <25 mg | 4 | 4 | 4/4 | 4/4 (100.0%; 95% CI 51.0% to 100.0%) | activation or irritability: 2/4 (50.0%); anxiety or panic: 2/4 (50.0%); appetite change: 1/4 (25.0%) |
| NSI-189 | 25 to <50 mg | 7 | 7 | 7/7 | 5/7 (71.4%; 95% CI 35.9% to 91.8%) | anxiety or panic: 5/7 (71.4%); depressed or flattened mood: 2/7 (28.6%); headache or migraine: 2/7 (28.6%) |
| Selank | <5 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Semax | <5 mg | 2 | 2 | 2/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | activation or irritability: 1/2 (50.0%); cognitive or perceptual disturbance: 1/2 (50.0%); depressed or flattened mood: 1/2 (50.0%) |

## Route-stratified side-effect reporting

Side-effect reporting is joined by hashed author and compound across all of that author's reports. The denominator is every distinct author in the dose or route bucket. Classifier coverage shows how many denominator authors also had a retained comparator report. These are cross-report associations, not administration-event links, incidence estimates, or dose-response evidence. Dose and route rows are included only when the extracted value and compound were found near each other in the same source segment.

| Compound | Route family | Observations | Authors | Classifier coverage | Any side effect | Leading mapped effects |
|---|---|---|---|---|---|---|
| 4'-DMA | oral mucosal | 9 | 9 | 8/9 | 2/9 (22.2%; 95% CI 6.3% to 54.7%) | activation or irritability: 1/9 (11.1%) |
| 7,8-DHF | dermal | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| 7,8-DHF | nasal mucosal | 2 | 2 | 2/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | headache or migraine: 1/2 (50.0%) |
| 7,8-DHF | oral mucosal | 26 | 26 | 24/26 | 11/26 (42.3%; 95% CI 25.5% to 61.1%) | insomnia or sleep disruption: 6/26 (23.1%); headache or migraine: 4/26 (15.4%); activation or irritability: 2/26 (7.7%) |
| 7,8-DHF | swallowed oral | 5 | 5 | 3/5 | 2/5 (40.0%; 95% CI 11.8% to 76.9%) | headache or migraine: 2/5 (40.0%) |
| Cerebrolysin | nasal mucosal | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | cognitive or perceptual disturbance: 1/1 (100.0%) |
| Dihexa | dermal | 3 | 3 | 3/3 | 2/3 (66.7%; 95% CI 20.8% to 93.9%) | activation or irritability: 1/3 (33.3%); fatigue or sedation: 1/3 (33.3%); gastrointestinal: 1/3 (33.3%) |
| Dihexa | oral mucosal | 3 | 3 | 3/3 | 2/3 (66.7%; 95% CI 20.8% to 93.9%) | appetite change: 1/3 (33.3%); fatigue or sedation: 1/3 (33.3%); insomnia or sleep disruption: 1/3 (33.3%) |
| Dihexa | swallowed oral | 4 | 4 | 4/4 | 1/4 (25.0%; 95% CI 4.6% to 69.9%) | fatigue or sedation: 1/4 (25.0%) |
| Lion's mane | swallowed oral | 1 | 1 | 0/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| NSI-189 | oral mucosal | 3 | 3 | 3/3 | 3/3 (100.0%; 95% CI 43.8% to 100.0%) | anxiety or panic: 2/3 (66.7%); insomnia or sleep disruption: 1/3 (33.3%); sexual: 1/3 (33.3%) |
| NSI-189 | swallowed oral | 3 | 3 | 3/3 | 1/3 (33.3%; 95% CI 6.1% to 79.2%) | anxiety or panic: 1/3 (33.3%) |
| Semax | nasal mucosal | 2 | 2 | 2/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | anxiety or panic: 1/2 (50.0%); cognitive or perceptual disturbance: 1/2 (50.0%); depressed or flattened mood: 1/2 (50.0%) |

## Symptom-linked outcomes

Explicit PEM target coverage: 0 treatment-linked outcome entries. General fatigue remains a separate endpoint bucket.

| Compound | Target symptom | Authors | Helped | No effect | Worsened |
|---|---|---|---|---|---|
| 4'-DMA | mood or depression | 11 | 13 | 0 | 0 |
| 4'-DMA | anxiety or stress | 5 | 2 | 0 | 3 |
| 4'-DMA | cognition or brain fog | 5 | 4 | 0 | 1 |
| 4'-DMA | energy or motivation | 5 | 4 | 0 | 0 |
| 4'-DMA | focus or attention | 5 | 4 | 0 | 1 |
| 4'-DMA | sleep or wakefulness | 5 | 1 | 0 | 5 |
| 4'-DMA | cardiovascular or autonomic | 3 | 1 | 0 | 3 |
| 4'-DMA | general fatigue | 2 | 1 | 0 | 1 |
| 4'-DMA | memory or learning | 2 | 2 | 0 | 0 |
| 4'-DMA | pain or neurologic symptoms | 2 | 1 | 0 | 1 |
| 4'-DMA | gastrointestinal | 1 | 0 | 1 | 0 |
| 4'-DMA | other specified result | 1 | 1 | 0 | 0 |
| 7,8-DHF | mood or depression | 22 | 22 | 0 | 2 |
| 7,8-DHF | anxiety or stress | 13 | 11 | 0 | 4 |
| 7,8-DHF | focus or attention | 13 | 16 | 0 | 0 |
| 7,8-DHF | sleep or wakefulness | 12 | 4 | 0 | 8 |
| 7,8-DHF | cognition or brain fog | 11 | 11 | 1 | 0 |
| 7,8-DHF | pain or neurologic symptoms | 11 | 8 | 1 | 8 |
| 7,8-DHF | energy or motivation | 10 | 10 | 1 | 0 |
| 7,8-DHF | other specified result | 9 | 4 | 2 | 4 |
| 7,8-DHF | hair or skin | 5 | 0 | 0 | 8 |
| 7,8-DHF | general fatigue | 4 | 4 | 0 | 1 |
| 7,8-DHF | memory or learning | 4 | 4 | 0 | 1 |
| 7,8-DHF | neuroprotection or recovery | 2 | 2 | 0 | 1 |
| 7,8-DHF | stimulant recovery or reduction | 2 | 2 | 0 | 0 |
| 7,8-DHF | cardiovascular or autonomic | 1 | 0 | 0 | 2 |
| 7,8-DHF | gastrointestinal | 1 | 0 | 0 | 1 |
| 7,8-DHF | sexual function | 1 | 0 | 0 | 1 |
| 7,8-DHF | social functioning | 1 | 1 | 0 | 0 |
| 9-MBC | mood or depression | 1 | 1 | 0 | 1 |
| BPC-157 | mood or depression | 2 | 1 | 0 | 1 |
| Cerebrolysin | sleep or wakefulness | 2 | 2 | 0 | 0 |
| Cerebrolysin | cognition or brain fog | 1 | 1 | 0 | 0 |
| Cerebrolysin | energy or motivation | 1 | 0 | 0 | 1 |
| Cerebrolysin | sexual function | 1 | 0 | 0 | 1 |
| Dihexa | cognition or brain fog | 2 | 2 | 0 | 0 |
| Dihexa | mood or depression | 2 | 3 | 0 | 0 |
| Dihexa | other specified result | 2 | 1 | 0 | 1 |
| Dihexa | hair or skin | 1 | 0 | 0 | 1 |
| Lion's mane | energy or motivation | 2 | 1 | 0 | 1 |
| Lion's mane | memory or learning | 2 | 2 | 0 | 0 |
| Lion's mane | other specified result | 2 | 2 | 0 | 0 |
| Lion's mane | anxiety or stress | 1 | 1 | 0 | 0 |
| Lion's mane | cognition or brain fog | 1 | 1 | 0 | 0 |
| Lion's mane | focus or attention | 1 | 1 | 0 | 0 |
| Lion's mane | hair or skin | 1 | 0 | 0 | 1 |
| Lion's mane | mood or depression | 1 | 0 | 0 | 1 |
| Lion's mane | sexual function | 1 | 0 | 0 | 1 |
| NSI-189 | mood or depression | 11 | 12 | 0 | 2 |
| NSI-189 | other specified result | 6 | 3 | 0 | 3 |
| NSI-189 | memory or learning | 4 | 4 | 0 | 0 |
| NSI-189 | anxiety or stress | 3 | 1 | 0 | 2 |
| NSI-189 | cognition or brain fog | 3 | 3 | 0 | 0 |
| NSI-189 | focus or attention | 2 | 1 | 1 | 0 |
| NSI-189 | general fatigue | 2 | 1 | 0 | 1 |
| NSI-189 | pain or neurologic symptoms | 1 | 0 | 0 | 1 |
| Selank | energy or motivation | 1 | 1 | 0 | 0 |
| Semax | mood or depression | 3 | 3 | 0 | 0 |
| Semax | cognition or brain fog | 2 | 2 | 0 | 0 |
| Semax | energy or motivation | 2 | 3 | 0 | 0 |
| Semax | memory or learning | 2 | 1 | 0 | 1 |
| Semax | anxiety or stress | 1 | 0 | 0 | 1 |
| Semax | focus or attention | 1 | 1 | 0 | 0 |
| Semax | other specified result | 1 | 0 | 0 | 1 |
| Semax | sexual function | 1 | 0 | 0 | 1 |
| Semax | sleep or wakefulness | 1 | 1 | 0 | 0 |

## Interpretation boundaries

- Keep 7,8-DHF and 4'-DMA-7,8-DHF separate.
- Treat PEM as distinct from general fatigue when it is explicitly stated.
- Do not infer that dose, route, outcome, and side effect belong to one administration event unless the source explicitly links them.
- Use matched-author results as a sensitivity analysis, not as the primary estimand, because overlap can be sparse.
- The direct TrkB-agonist interpretation of 7,8-DHF remains disputed; the cohort is tiered rather than presented as one homogeneous mechanism class.

## Reproducibility

- Sentiment database: `comparators.db`; SHA-256 `ac321297811718cf1be0e0393d91e5b3a49f9bdbe92217115fb31dee927b595a`
- Study database: `combined.db`; SHA-256 `47bd9f879b53356724ba0d7b6a58422ba66827bfd00d1e9db94718909339831f`
- Cohort configuration: `comparator_cohort.json`; SHA-256 `c420e12d450b0b2637983121cd1db06c56c62e9567e002fb257f01887cfc8063`
