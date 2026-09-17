# 7,8-DHF and comparator study

This study asks which treatment experiences deserve closer investigation, and
whether reported dose, route, and reason for use help explain sentiment and side
effects. It began with r/Nootropics and expanded to ten compounds across nine
nootropic-adjacent communities and ten ME/CFS or Long COVID communities.

Start with the [study summary](reports/study_summary.md), then the
[saved severity checkpoint](reports/severity_checkpoint.md),
[exposure tables](reports/severity_checkpoint_exposures.md), and
[model tables](reports/severity_checkpoint_models.md). The
[new reconstruction](reports/severity_reconstruction.md) records differences from
the saved checkpoint. The [runbook](RUNBOOK.md) describes reproduction. These are observational reporting
analyses: positive sentiment is a perceived-benefit proxy, and an unmentioned
side effect is not confirmed absence of an adverse event.

## Work completed so far

| Stage | Work completed | Where to look |
| --- | --- | --- |
| Corpus construction | Intervention-name screening, parent-thread context, hashed authors, and separate community corpora | `build_comparator_corpus.py`, `build_sqlite_comparator_corpora.py` |
| Extraction | Personal-use screening; treatment sentiment; linked dose and route; explicit reason for taking 7,8-DHF | `run_comparator_pipeline.py`, `run_variable_pipeline.py`, `extract_78dhf_reasons.py` |
| Comparator analysis | Ten configured compounds; independent and matched-author sentiment comparisons; multiple-testing correction | [Original comparator report](comparator_analysis.md), `analyze_comparator_cohort.py` |
| Community overlap | Independent community estimates plus separate globally deduplicated summaries | [Overlap](reports/author_overlap.md), [Independent cohorts](reports/unpooled_summary.md) |
| Predictor analysis | Dose, route, and explicit reason versus sentiment and side-effect reporting; between-compound sentiment normalization | [Predictor report](reports/78dhf_predictor_analysis.md) |
| Same-post episodes | Exposure and outcome attribution within a post; author-clustered sentiment and any-side-effect models | [Episode report and dose-audit notice](reports/78dhf_episode_analysis.md) |
| Severity extraction | Optional explicit grades persisted with each side effect; rerun across 19 community databases | `analyze_side_effect_severity.py`, `build_combined_db.py` |
| Severity outcomes | Distinct author-treatment-effect observations; author mean and maximum severity; moderate-or-worse outcomes; dose and route models and 95% intervals | [Saved checkpoint](reports/severity_checkpoint.md), [new reconstruction](reports/severity_reconstruction.md) |
| Audit and presentation | Corrected high-dose descriptive result; dated report index; portable provenance; aggregate tables and figures | This README, [study summary](reports/study_summary.md), [runbook](RUNBOOK.md) |

The shared severity extraction schema is supplied by PR #144. PR #140 adds the
study-specific integration, analyses, and reports on top of it. The statistical
reconstruction added in this update is labeled separately from the saved
September 3 results. It does not imply that the lost historical modeling scripts
were recovered or that every coefficient was reproduced exactly.

## Compounds

The source of truth for names, aliases, exclusions, and study roles is
[`comparator_cohort.json`](comparator_cohort.json). A study role is a comparison
rationale, not evidence of efficacy or a shared clinical indication.

| Compound | Role in this study |
| --- | --- |
| 7,8-DHF (tropoflavin) | Target; kept distinct from the 4'-DMA derivative |
| 4'-DMA-7,8-DHF (eutropoflavin) | Closest chemical analogue |
| Cerebrolysin | Primary neurotrophic comparator |
| Semax | Primary comparator |
| Selank | Primary comparator |
| NSI-189 | Secondary comparator |
| Dihexa | Secondary comparator |
| Lion's mane | Secondary comparator; product formulations are heterogeneous |
| 9-MBC | Exploratory comparator |
| BPC-157 | Adjacent-market comparison; not an established negative control |

Membership in this list does not mean all ten are recommended for a subsequent
trial. BPC-157 has much more usable exposure information than several other
compounds, which makes some models feasible without making it the preferred
treatment candidate.

## Communities and coverage

| Source group | Communities | Processing scope |
| --- | --- | --- |
| Nootropic-adjacent | r/Nootropics, r/Supplements, r/Peptides, r/NootropicsDepot, r/NooTopics, r/depressionregimens, r/StackAdvice, r/Longevity, r/Psilocybin | Independent comparator pipelines and linked-variable analyses; later explicit-severity rerun |
| ME/CFS and Long COVID | r/cfs, r/cfsme, r/cfsrecovery, r/CFSScience, r/covidlonghaulers, r/LongCovid, r/LongCovid_MECFS_DE, r/Longcovidgutdysbiosis, r/LongHaulersRecovery, r/mecfs | Intervention-first screen of existing datasets, followed by personal-experience classification and explicit-severity extraction |

The September 3 severity checkpoint includes 19 community databases. That does
not mean 19 complete variable-extraction cohorts, 19 equally informative samples,
or exhaustive coverage of each community's history. Community membership does not
establish a diagnosis or indicate that a respondent is healthy.

## How observations are counted

- **Community author:** one author-treatment observation within a community.
- **Combined author:** the same hashed account is deduplicated across communities
  for each treatment. Different accounts belonging to one person cannot be
  reliably identified, so these are account counts, not verified patient counts.
- **Episode:** one globally unique author-post pair. Several episodes from one
  author remain dependent; episode regression uses author-clustered uncertainty.
- **Distinct side effect:** one author-treatment-canonical-effect tuple. Repeated
  mentions retain the highest explicit grade for that effect; different effects
  remain separate. Mean and maximum severity are secondary author summaries.

Unknown severity stays missing. The grades are mild, moderate, severe, and
life-threatening. Coding them 1 through 4 for a secondary linear summary is a
modeling convention; it does not establish equal distances between grades.

Dose and route links in the severity analyses are from author histories and may
not refer to the same administration episode. The same-post analysis provides a
different, more restricted attribution design. These datasets must not be
silently merged or their denominators interchanged.

## Current severity sample availability

These are the saved September 3 author-level linear-model eligibility counts,
after the primary dose screen. The final column is before excluding unsupported
route levels for regression. It is not the number of independent clinical
patients or the number of distinct side effects.

| Treatment | Classified authors | Authors with explicit severity | Severity + numeric dose | Severity + route | Severity + dose + route |
| --- | ---: | ---: | ---: | ---: | ---: |
| 7,8-DHF | 684 | 22 | 2 | 4 | 2 |
| 4'-DMA-7,8-DHF | 250 | 3 | 1 | 1 | 1 |
| Cerebrolysin | 940 | 29 | 0 | 1 | 0 |
| Semax | 3,755 | 128 | 10 | 10 | 4 |
| Selank | 2,243 | 54 | 5 | 6 | 3 |
| NSI-189 | 1,182 | 96 | 10 | 5 | 2 |
| Dihexa | 435 | 11 | 2 | 3 | 1 |
| Lion's mane | 9,530 | 284 | 23 | 0 | 0 |
| 9-MBC | 255 | 10 | 0 | 1 | 0 |
| BPC-157 | 7,227 | 285 | 65 | 87 | 35 |

The joint linear model retained 33 BPC-157 authors and 40 authors in the pooled
analysis after route support checks. The 7,8-DHF sample cannot support a separate
dose-severity model even when route is omitted. A zero in the numeric-dose column
can reflect unit or linkage ineligibility, not a complete absence of dosing
discussion. Volume-only reports are not converted to milligrams without a
verified concentration and formulation.

## Report versions

| Checkpoint | Meaning and status |
| --- | --- |
| August 18-19 | Original exploration in [NOTES](NOTES.md); historical, includes broader alias and attribution decisions |
| August 31-September 2 | Comparator, independent-community, normalized-predictor, and episode reports; retain their original source populations and extraction versions |
| September 3 | Severity rerun, linear models, distinct-effect models, moderate-or-worse analysis, and final document figures; saved aggregate checkpoint |
| This PR update | Audit correction, validated publication of saved aggregates, offline model reconstruction, tests, README, and updated run instructions |

The old 7,8-DHF >=100 mg bucket had 11 candidate episodes. Source review excluded
four doses attributed to another compound and one range crossing the boundary.
The audited descriptive result is six episodes from four authors: 5/6 positive,
1/6 with a mapped side effect, and no explicitly graded effects. The old
122-episode regression was not repaired by changing that one table row; its
historical status is explicitly marked in the episode report.

## Reproduction and data handling

Use the [runbook](RUNBOOK.md) for exact commands. Inputs and generated analysis
outputs live under the sibling `PatientPunk_data/` directory, or the directory
selected by `PATIENTPUNK_DATA`. New analysis runs should use a new output directory
to preserve the September 3 checkpoint. Reusing existing extractions is offline;
rerunning the model-based extraction pipeline is a separate, paid operation.

Only code, synthetic tests, small configuration/provenance artifacts, aggregate
Markdown, and aggregate figures belong in this study's Git diff. Raw posts,
author rows or identifiers, databases, per-record model responses, CSV exports,
and Word workbooks/documents stay external. Public reports do not contain private
storage URLs or machine-specific paths.

## What remains open

An opt-in survey could improve missing dose, route, duration, indication, and
explicit severity information. It remains a proposal: no recruitment or survey
results are represented here. Questionnaire design, participation burden,
deduplication, product identity, and the applicable OMF process remain to be
settled. More complete reporting would improve analysis but would not remove
self-selection, recall bias, or confounding.
