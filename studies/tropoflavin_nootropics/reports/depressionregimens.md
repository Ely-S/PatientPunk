# 7,8-DHF comparator-cohort analysis: r/depressionregimens

This report answers the OMF collaboration questions with aggregate r/depressionregimens self-reports. It measures reporting patterns, not efficacy, adverse-event incidence, causal dose-response, or medical safety. Every comparator uses the same source population, classifier, context handling, and one-vote-per-author rule.

## Extraction coverage and recall checks

The retention column compares retained classified authors with authors found by deterministic alias matching. It is a recall proxy, not gold-standard sensitivity, because model eligibility and alias matching are different measurement stages.

| Compound | Alias-matched items | Alias-matched authors | Reports | Classified authors | Observed retention | Sample warning |
|---|---|---|---|---|---|---|
| 7,8-DHF | 58 | 30 | 15 | 8 | 26.7% | too sparse for inference |
| 4'-DMA-7,8-DHF | 5 | 4 | 2 | 2 | 50.0% | too sparse for inference |
| Semax | 139 | 87 | 41 | 29 | 33.3% | adequate for description |
| Cerebrolysin | 49 | 34 | 12 | 7 | 20.6% | too sparse for inference |
| Selank | 104 | 65 | 33 | 19 | 29.2% | adequate for description |
| NSI-189 | 571 | 268 | 237 | 104 | 38.8% | adequate for description |
| Dihexa | 11 | 8 | 0 | 0 | 0.0% | too sparse for inference |
| Lion's mane | 236 | 155 | 94 | 68 | 43.9% | adequate for description |
| 9-MBC | 8 | 8 | 1 | 1 | 12.5% | too sparse for inference |
| BPC-157 | 110 | 65 | 37 | 24 | 36.9% | adequate for description |

Pipeline B produced 184 records from 184 selected authors (100.0%) and 3,149 source segments.

OpenRouter models: sentiment `deepseek/deepseek-v4-flash` / `deepseek/deepseek-v4-flash`; variables `deepseek/deepseek-v4-flash`. Provider-reported token totals: sentiment 2,302,759; variables 1,335,589. Text caps were 1,500 upstream characters and 8,000 Pipeline B characters, with a 16,384-token Pipeline B output ceiling.

Source SHA-256 values: comments `94de0ae3dd38752b7a66594ef9e73c25962678717e7357c1f2900fe553941958`; posts `bab31f5bb76f9f0bc58a079e6114bef3b1d08d69ea64f0e95dd91a603f07668c`. Code commits: sentiment `bc6e275f0ed46296688a9b85a9046d67be6f0734`; variables `360f337623173eddcab69958cb9affdbb76d8d3b`.

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
| 7,8-DHF | target | target | 8 | 7 | 1 | 0 | 0 | 87.5% | 52.9% to 97.8% | too sparse for inference |
| 4'-DMA-7,8-DHF | chemical analogue | primary | 2 | 2 | 0 | 0 | 0 | 100.0% | 34.2% to 100.0% | too sparse for inference |
| Semax | BDNF/TrkB related | primary | 29 | 20 | 9 | 0 | 0 | 69.0% | 50.8% to 82.7% | descriptive only |
| Cerebrolysin | BDNF/TrkB related | primary | 7 | 4 | 2 | 1 | 0 | 57.1% | 25.0% to 84.2% | too sparse for inference |
| Selank | BDNF/TrkB related | primary | 19 | 11 | 7 | 1 | 0 | 57.9% | 36.3% to 76.9% | descriptive only |
| NSI-189 | broader neurotrophic | secondary | 104 | 66 | 33 | 4 | 1 | 63.5% | 53.9% to 72.1% | descriptive only |
| Dihexa | broader neurotrophic | secondary | 0 | 0 | 0 | 0 | 0 | 0.0% | 0.0% to 0.0% | too sparse for inference |
| Lion's mane | broader neurotrophic | secondary | 68 | 43 | 21 | 4 | 0 | 63.2% | 51.4% to 73.7% | descriptive only |
| 9-MBC | broader neurotrophic | exploratory | 1 | 1 | 0 | 0 | 0 | 100.0% | 20.7% to 100.0% | too sparse for inference |
| BPC-157 | negative control | control | 24 | 18 | 5 | 1 | 0 | 75.0% | 55.1% to 88.0% | descriptive only |

## Comparisons with 7,8-DHF

The positive-rate difference is 7,8-DHF minus comparator, so positive values favor a higher 7,8-DHF positive-reporting share. Fisher tests use mutually exclusive authors and report 7,8-DHF/comparator odds ratios. BH q-values are corrected across comparators. Matched results use authors who reported both compounds; the discordant column is 7,8-DHF-only positive / comparator-only positive. Matched q-values are corrected separately.

| Comparator | 7,8-DHF minus comparator | Exclusive OR | Exclusive p | Exclusive BH q | Exclusive 7,8-DHF authors | Exclusive comparator authors | Matched authors | Discordant | Matched p | Matched BH q | Inference status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4'-DMA-7,8-DHF | -12.5 points | 0.00 | 1.0000 | 1.0000 | 7 | 1 | 1 | 0/0 | n/a | n/a | too sparse for inference |
| Semax | +18.5 points | 2.84 | 0.6445 | 0.9696 | 7 | 28 | 1 | 0/0 | n/a | n/a | too sparse for inference |
| Cerebrolysin | +30.4 points | 5.25 | 0.2821 | 0.9400 | 8 | 7 | 0 | 0/0 | n/a | n/a | too sparse for inference |
| Selank | +29.6 points | 4.80 | 0.3548 | 0.9400 | 7 | 18 | 1 | 0/0 | n/a | n/a | too sparse for inference |
| NSI-189 | +24.0 points | 3.51 | 0.4178 | 0.9400 | 7 | 103 | 1 | 0/0 | n/a | n/a | too sparse for inference |
| Dihexa | +87.5 points | nan | 1.0000 | 1.0000 | 8 | 0 | 0 | 0/0 | n/a | n/a | too sparse for inference |
| Lion's mane | +24.3 points | 3.35 | 0.4113 | 0.9400 | 7 | 67 | 1 | 1/0 | 1.0000 | 1.0000 | too sparse for inference |
| 9-MBC | -12.5 points | 0.00 | 1.0000 | 1.0000 | 8 | 1 | 0 | 0/0 | n/a | n/a | too sparse for inference |
| BPC-157 | +12.5 points | 2.33 | 0.6464 | 0.9696 | 8 | 24 | 0 | 0/0 | n/a | n/a | too sparse for inference |

## Treatment-linked side-effect signals

These are the eight most frequently reported canonical effects per compound, deduplicated by author within each effect. Because every pipeline row is linked to one target treatment, the former 7,8-DHF / 4'-DMA blending is removed. Counts remain reporting proportions, not incidence.

| Compound | Canonical effect | Safety domain | Authors | Share of classified authors | Mentions |
|---|---|---|---|---|---|
| 7,8-DHF | other reported effect | other | 1 | 12.5% | 1 |
| Semax | other reported effect | other | 5 | 17.2% | 8 |
| Semax | anxiety or panic | activation or anxiety | 2 | 6.9% | 2 |
| Semax | cognitive or perceptual disturbance | neurologic | 2 | 6.9% | 3 |
| Semax | depressed or flattened mood | mood | 2 | 6.9% | 2 |
| Semax | tolerance or short duration | tolerance or duration | 1 | 3.4% | 1 |
| Selank | other reported effect | other | 5 | 26.3% | 11 |
| Selank | fatigue or sedation | fatigue or sedation | 2 | 10.5% | 2 |
| Selank | cognitive or perceptual disturbance | neurologic | 1 | 5.3% | 1 |
| NSI-189 | other reported effect | other | 22 | 21.2% | 37 |
| NSI-189 | anxiety or panic | activation or anxiety | 14 | 13.5% | 16 |
| NSI-189 | insomnia or sleep disruption | sleep | 5 | 4.8% | 5 |
| NSI-189 | depressed or flattened mood | mood | 4 | 3.8% | 4 |
| NSI-189 | sexual | sexual | 4 | 3.8% | 4 |
| NSI-189 | cognitive or perceptual disturbance | neurologic | 3 | 2.9% | 3 |
| NSI-189 | fatigue or sedation | fatigue or sedation | 3 | 2.9% | 3 |
| NSI-189 | headache or migraine | neurologic | 3 | 2.9% | 3 |
| Lion's mane | other reported effect | other | 6 | 8.8% | 8 |
| Lion's mane | anxiety or panic | activation or anxiety | 4 | 5.9% | 4 |
| Lion's mane | depressed or flattened mood | mood | 3 | 4.4% | 3 |
| Lion's mane | gastrointestinal | gastrointestinal | 2 | 2.9% | 2 |
| Lion's mane | activation or irritability | activation or anxiety | 1 | 1.5% | 1 |
| Lion's mane | fatigue or sedation | fatigue or sedation | 1 | 1.5% | 1 |
| Lion's mane | headache or migraine | neurologic | 1 | 1.5% | 1 |
| Lion's mane | insomnia or sleep disruption | sleep | 1 | 1.5% | 1 |
| BPC-157 | other reported effect | other | 4 | 16.7% | 4 |
| BPC-157 | depressed or flattened mood | mood | 2 | 8.3% | 2 |
| BPC-157 | fatigue or sedation | fatigue or sedation | 2 | 8.3% | 2 |
| BPC-157 | anxiety or panic | activation or anxiety | 1 | 4.2% | 1 |
| BPC-157 | appetite change | appetite or weight | 1 | 4.2% | 1 |
| BPC-157 | insomnia or sleep disruption | sleep | 1 | 4.2% | 1 |

## Post-level compound, dose, and outcome links

This stricter view keeps only treatment-specific sentiment reports where exactly one quantitative mass dose appears near that compound in the same post or comment. Authors receive one vote per compound and dose band. It is descriptive and does not establish a dose-response relationship.

| Compound | Dose band | Posts | Authors | Positive authors | Side-effect authors | Inference status |
|---|---|---|---|---|---|---|
| 7,8-DHF | <5 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| BPC-157 | <5 mg | 2 | 2 | 2/2 (100.0%) | 1/2 (50.0%) | too sparse for inference |
| Lion's mane | >=100 mg | 3 | 3 | 3/3 (100.0%) | 0/3 (0.0%) | too sparse for inference |
| NSI-189 | <5 mg | 1 | 1 | 0/1 (0.0%) | 0/1 (0.0%) | too sparse for inference |
| NSI-189 | 5 to <10 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| NSI-189 | 10 to <25 mg | 3 | 3 | 3/3 (100.0%) | 1/3 (33.3%) | too sparse for inference |
| NSI-189 | 25 to <50 mg | 4 | 4 | 3/4 (75.0%) | 0/4 (0.0%) | too sparse for inference |
| NSI-189 | 50 to <100 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| NSI-189 | >=100 mg | 3 | 3 | 3/3 (100.0%) | 1/3 (33.3%) | too sparse for inference |
| Selank | <5 mg | 1 | 1 | 1/1 (100.0%) | 1/1 (100.0%) | too sparse for inference |
| Selank | 10 to <25 mg | 2 | 2 | 2/2 (100.0%) | 0/2 (0.0%) | too sparse for inference |
| Selank | 25 to <50 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Semax | 10 to <25 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Semax | 50 to <100 mg | 1 | 1 | 1/1 (100.0%) | 0/1 (0.0%) | too sparse for inference |
| Semax | >=100 mg | 2 | 2 | 2/2 (100.0%) | 0/2 (0.0%) | too sparse for inference |

## Dose and route attribution checks

| Field | Status | Rows |
|---|---|---|
| Dose | corroborated | 25 |
| Dose | unsupported | 16 |
| Route | corroborated | 14 |
| Route | unsupported | 6 |

## Dose-stratified side-effect reporting

Side-effect reporting is joined by hashed author and compound across all of that author's reports. The denominator is every distinct author in the dose or route bucket. Classifier coverage shows how many denominator authors also had a retained comparator report. These are cross-report associations, not administration-event links, incidence estimates, or dose-response evidence. Dose and route rows are included only when the extracted value and compound were found near each other in the same source segment.

| Compound | Dose band | Observations | Authors | Classifier coverage | Any side effect | Leading mapped effects |
|---|---|---|---|---|---|---|
| 7,8-DHF | <5 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| BPC-157 | <5 mg | 3 | 3 | 3/3 | 2/3 (66.7%; 95% CI 20.8% to 93.9%) | fatigue or sedation: 1/3 (33.3%); insomnia or sleep disruption: 1/3 (33.3%) |
| Lion's mane | >=100 mg | 4 | 3 | 3/3 | 1/3 (33.3%; 95% CI 6.1% to 79.2%) | none mapped |
| NSI-189 | 10 to <25 mg | 3 | 3 | 3/3 | 2/3 (66.7%; 95% CI 20.8% to 93.9%) | anxiety or panic: 1/3 (33.3%) |
| NSI-189 | 25 to <50 mg | 9 | 9 | 9/9 | 4/9 (44.4%; 95% CI 18.9% to 73.3%) | anxiety or panic: 2/9 (22.2%) |
| NSI-189 | 50 to <100 mg | 2 | 2 | 2/2 | 0/2 (0.0%; 95% CI 0.0% to 65.8%) | none mapped |
| NSI-189 | >=100 mg | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| Selank | <5 mg | 2 | 2 | 2/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | none mapped |

## Route-stratified side-effect reporting

Side-effect reporting is joined by hashed author and compound across all of that author's reports. The denominator is every distinct author in the dose or route bucket. Classifier coverage shows how many denominator authors also had a retained comparator report. These are cross-report associations, not administration-event links, incidence estimates, or dose-response evidence. Dose and route rows are included only when the extracted value and compound were found near each other in the same source segment.

| Compound | Route family | Observations | Authors | Classifier coverage | Any side effect | Leading mapped effects |
|---|---|---|---|---|---|---|
| 7,8-DHF | swallowed oral | 1 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| BPC-157 | parenteral | 2 | 2 | 2/2 | 0/2 (0.0%; 95% CI 0.0% to 65.8%) | none mapped |
| BPC-157 | swallowed oral | 2 | 2 | 2/2 | 1/2 (50.0%; 95% CI 9.5% to 90.5%) | fatigue or sedation: 1/2 (50.0%); insomnia or sleep disruption: 1/2 (50.0%) |
| Cerebrolysin | parenteral | 2 | 1 | 1/1 | 0/1 (0.0%; 95% CI 0.0% to 79.3%) | none mapped |
| NSI-189 | oral mucosal | 3 | 3 | 3/3 | 1/3 (33.3%; 95% CI 6.1% to 79.2%) | anxiety or panic: 1/3 (33.3%) |
| Selank | nasal mucosal | 3 | 3 | 3/3 | 2/3 (66.7%; 95% CI 20.8% to 93.9%) | fatigue or sedation: 1/3 (33.3%) |
| Semax | nasal mucosal | 1 | 1 | 1/1 | 1/1 (100.0%; 95% CI 20.7% to 100.0%) | depressed or flattened mood: 1/1 (100.0%) |

## Symptom-linked outcomes

Explicit PEM target coverage: 0 treatment-linked outcome entries. General fatigue remains a separate endpoint bucket.

| Compound | Target symptom | Authors | Helped | No effect | Worsened |
|---|---|---|---|---|---|
| 4'-DMA | anxiety or stress | 1 | 1 | 0 | 0 |
| 7,8-DHF | anxiety or stress | 1 | 1 | 0 | 0 |
| 7,8-DHF | mood or depression | 1 | 2 | 0 | 0 |
| 7,8-DHF | other specified result | 1 | 1 | 0 | 0 |
| BPC-157 | mood or depression | 7 | 3 | 1 | 1 |
| BPC-157 | other specified result | 4 | 4 | 0 | 0 |
| BPC-157 | anxiety or stress | 2 | 1 | 0 | 1 |
| BPC-157 | sleep or wakefulness | 2 | 2 | 0 | 0 |
| BPC-157 | pain or neurologic symptoms | 1 | 1 | 0 | 0 |
| Cerebrolysin | cognition or brain fog | 1 | 1 | 0 | 0 |
| Cerebrolysin | memory or learning | 1 | 1 | 1 | 0 |
| Cerebrolysin | mood or depression | 1 | 1 | 0 | 0 |
| Lion's mane | mood or depression | 13 | 13 | 1 | 0 |
| Lion's mane | anxiety or stress | 6 | 5 | 0 | 1 |
| Lion's mane | cognition or brain fog | 4 | 4 | 0 | 0 |
| Lion's mane | memory or learning | 3 | 3 | 0 | 0 |
| Lion's mane | energy or motivation | 2 | 3 | 0 | 0 |
| Lion's mane | focus or attention | 2 | 2 | 0 | 0 |
| Lion's mane | sleep or wakefulness | 2 | 2 | 0 | 0 |
| Lion's mane | other specified result | 1 | 1 | 0 | 0 |
| Lion's mane | sexual function | 1 | 0 | 0 | 1 |
| NSI-189 | mood or depression | 31 | 33 | 5 | 0 |
| NSI-189 | other specified result | 10 | 9 | 0 | 5 |
| NSI-189 | anxiety or stress | 8 | 1 | 1 | 6 |
| NSI-189 | pain or neurologic symptoms | 5 | 1 | 0 | 5 |
| NSI-189 | cognition or brain fog | 4 | 4 | 0 | 0 |
| NSI-189 | energy or motivation | 4 | 4 | 0 | 0 |
| NSI-189 | memory or learning | 4 | 4 | 0 | 0 |
| NSI-189 | sleep or wakefulness | 4 | 1 | 1 | 2 |
| NSI-189 | focus or attention | 1 | 1 | 0 | 0 |
| NSI-189 | social functioning | 1 | 1 | 0 | 0 |
| Selank | anxiety or stress | 6 | 6 | 1 | 0 |
| Selank | mood or depression | 5 | 3 | 2 | 1 |
| Selank | energy or motivation | 2 | 1 | 0 | 1 |
| Selank | general fatigue | 1 | 0 | 0 | 1 |
| Selank | other specified result | 1 | 1 | 0 | 0 |
| Semax | mood or depression | 6 | 2 | 2 | 1 |
| Semax | anxiety or stress | 5 | 3 | 0 | 2 |
| Semax | energy or motivation | 4 | 5 | 0 | 0 |
| Semax | other specified result | 3 | 2 | 0 | 1 |
| Semax | cognition or brain fog | 2 | 3 | 0 | 0 |
| Semax | focus or attention | 1 | 1 | 0 | 0 |
| Semax | general fatigue | 1 | 2 | 0 | 0 |
| Semax | memory or learning | 1 | 1 | 0 | 0 |
| Semax | sleep or wakefulness | 1 | 1 | 0 | 0 |

## Interpretation boundaries

- Keep 7,8-DHF and 4'-DMA-7,8-DHF separate.
- Treat PEM as distinct from general fatigue when it is explicitly stated.
- Do not infer that dose, route, outcome, and side effect belong to one administration event unless the source explicitly links them.
- Use matched-author results as a sensitivity analysis, not as the primary estimand, because overlap can be sparse.
- The direct TrkB-agonist interpretation of 7,8-DHF remains disputed; the cohort is tiered rather than presented as one homogeneous mechanism class.

## Reproducibility

- Sentiment database: `sentiment.db`; SHA-256 `0e9e3563ca9dcacb835ec22202b15c30e696340ff49dc65cc4c18c04eaa9670c`
- Study database: `combined.db`; SHA-256 `b9c29799d6de03248f6c059122afa2f253ca7563c192d129988ae299ace65cac`
- Cohort configuration: `comparator_cohort.json`; SHA-256 `c420e12d450b0b2637983121cd1db06c56c62e9567e002fb257f01887cfc8063`
