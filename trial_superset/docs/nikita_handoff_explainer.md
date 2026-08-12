# Trial Superset Handoff: Bugs, Pull Process, And CSV Contents

This is a draft explainer for the Long COVID trial superset work. It is written so pieces can be
lifted into a note, email, or methods section.

## One-Sentence Summary

We built a Long COVID benchmark and prospective target list for NATURAL-v2 by reproducing Nikita's
trial-selection path, identifying several issues in the pinned `naturalv2` pipeline, then adding a
cleaner condition classifier, paper-rescued labels, registry-adapted Long COVID trials, and CSV exports
that make the resulting benchmark auditable.

## Important Framing

NATURAL does not train a pooled model on trial rows. It estimates each trial independently from that
trial's own patient-community text, then compares the text-derived estimate with the trial's real
outcome. The trial files here are therefore a benchmark plus target inventory, not supervised training
data for a cross-trial predictor.

That framing matters for the CSVs:

- `master_pulled_data.csv` is the primary Long COVID benchmark and target export.
- `cluster_benchmark.csv` is a separate adjacent-condition benchmark, not data that helps Long COVID
  prediction.
- `training_set_manifest_augmented.csv` is the pipeline manifest used to build the condition-specific
  NATURAL-compatible study files.
- `labels_sidecar.csv` is a corrected, model-ready label export. Pinned `naturalv2` does not consume
  it unless the evaluation path is changed to read it.

## What We Found In Natural

These are the main issues in pinned `naturalv2` at commit
`16ca17819e7b6310f9d9799238f4ff8b11b4c6f5`. Current upstream `main` is the same commit, so these are
still present upstream as of this review.

### 1. Long COVID Condition Matching Admits Acute COVID Trials

Nikita's condition matcher keeps a trial if either side is a substring of the other:

- condition string in trial condition term, or
- trial condition term in condition string.

For Long COVID, the condition string is `"Long Covid"`. Because `"covid"` is a substring of
`"long covid"`, any trial tagged only as generic COVID can be pulled into the Long COVID study. In the
current audit, the faithful matcher returned 22 Long COVID matches, only 10 of which looked genuinely
Long COVID. It admitted 12 acute-COVID or acute-hospitalization trials and also missed genuine
post-COVID trials tagged as things like `"post-acute covid-19 syndrome"` or `"post covid syndrome"`.

This means the faithful reproduction of Nikita's original Long COVID set is not a clean Long COVID
benchmark. It is useful because it reproduces her shared study, but it inherits acute-COVID
contamination from her matcher.

Our canonical mode replaces this with a condition-specific keyword classifier. For Long COVID, the
classifier requires long-COVID or post-COVID language such as `long covid`, `post-covid`, `pasc`, or
`post-acute sequelae`, and it drops plain acute COVID.

### 2. `notbinary` Divides Continuous Means By N

Pinned `naturalv2` computes `avg_potential_outcome` as:

- `value / 100` if the unit says percent,
- otherwise `value / N`.

That is reasonable for binary count endpoints, where `value / N` is a response rate. It is wrong for
continuous mean endpoints. Examples verified from the generated `Experiment` objects:

| Trial | Endpoint | Raw value | Natural label |
|---|---:|---:|---:|
| `NCT02499302` | steps/day | 7217, n=21 | 343.67 |
| `NCT04158427` | VAS fatigue | 72.8, n=5 | 14.56 |
| `NCT05559021` | FIQ score | 44.07, n=8 | 5.51 |

The CSV sidecar fixes this for downstream use by keeping:

- `raw_value`
- `n`
- `endpoint_type`
- `clean_outcome`, where continuous endpoints keep the raw mean instead of mean divided by N
- `scale_proportion` where a bounded scale can be oriented into `[0,1]`

The caveat is important: native `naturalv2` still uses its own `Experiment.avg_potential_outcomes`
unless patched.

### 3. Factorial Arms Named `X/Placebo` Are Dropped

Pinned `naturalv2` filters arms by checking whether the arm title contains the word `placebo`. That
drops valid factorial main-effect arms if the title contains a placebo component.

For LIFT (`NCT06366724`):

| LIFT arm | Meaning | Native Natural keeps it? |
|---|---|---|
| `Pyridostigmine/LDN` | stacked active arm | yes |
| `Pyridostigmine/Placebo` | pyridostigmine main effect | no |
| `Placebo/LDN` | LDN main effect | no |
| `Placebo/Placebo` | control | no, correctly |

The eval CSV relabels factorial arms to their non-placebo component, but a relabeled JSON or
Experiment file is still needed if pinned `naturalv2` should run directly on the LIFT main-effect arms.

### 4. Pinned Test Universe Does Not Match Her Shared Test Set

Pinned `naturalv2` downloads test trials using `results:without,status:act`, which currently returns
active-not-recruiting trials and omits recruiting trials like LIFT. The reproduced strict Long COVID
test set has 13 trials. The recruiting-inclusive relaxed universe has 50 Long COVID rows in
`relaxed_test_universe.csv`, and the broader eval set has 88 Long COVID trials / 153 target arms in
`long_covid_eval_set.csv`.

This is best described as a canonicality or configuration mismatch rather than a pure code bug. It
may be defensible to restrict to active-not-recruiting trials, but her shared test artifact appears
recruiting-inclusive, so the pinned repo does not reproduce that test set.

## What We Pulled

The final artifacts combine several source layers.

### Layer 1: ClinicalTrials.gov Structured Results

For each condition, we staged CT.gov trial JSONs and called Nikita's `check_trial`, `Study`, and
`Experiment` code unchanged. Completed trials with structured CT.gov results are the cleanest source
because the outcome module is already present.

For Long COVID, this contributes 21 train/val benchmark trials in `master_pulled_data.csv`.

### Layer 2: ClinicalTrials.gov Trials Without Posted Results, Rescued From Papers

Many completed trials never post structured results to CT.gov. For those, we:

1. identified eligible CT.gov no-results trials,
2. linked candidate result papers through Europe PMC,
3. pulled open-access full text when available,
4. used an LLM extractor to get the per-arm primary outcome,
5. synthesized a CT.gov-shaped `resultsSection`,
6. reran Natural's `Study` and `Experiment` machinery over the augmented JSONs.

These are marked `paper_extracted` in the manifest and `paper` in the master CSV.

For Long COVID, this contributes 23 train/val benchmark trials. Across all conditions, there are
88 paper-extracted train/val trials in the augmented manifest.

### Layer 3: Non-CT.gov Registry-Adapted Long COVID Trials

We also explored non-CT.gov registries, mainly ISRCTN and EudraCT. Six Long COVID trials were adapted
into CT.gov-shaped JSON records by using registry trial metadata plus paper-derived outcomes. These
are marked `registry_adapted`.

For Long COVID, this contributes 6 train/val benchmark trials.

### Layer 4: Recruiting-Inclusive Prospective Targets

For prediction targets, we used a relaxed active-test universe that includes:

- `ACTIVE_NOT_RECRUITING`
- `RECRUITING`
- `ENROLLING_BY_INVITATION`

This is how LIFT appears. The arm-level target export is `long_covid_eval_set.csv`, with 88 trials
and 153 prediction-target arms.

## How We Pulled It

The pipeline has two modes:

### Faithful Mode

Faithful mode uses Nikita's condition matcher and trial filters as-is. Its purpose is regression and
attribution: it proves we can reproduce the original shared Long COVID completed set. It also shows
that the original faithful Long COVID set includes acute-COVID trials because of the substring matcher.

### Improved / Canonical Mode

Canonical mode keeps Nikita's design filters and `Study` / `Experiment` objects, but replaces the
condition assignment step with a cleaner keyword classifier in `seed_terms.py`.

The classifier is deliberately conservative:

- Long COVID requires post-COVID / PASC / long-COVID language.
- ME/CFS accepts myalgic encephalomyelitis, chronic fatigue syndrome, ME/CFS, post-viral fatigue,
  and related terms.
- Fibromyalgia accepts fibromyalgia terms.
- Dysautonomia accepts dysautonomia, orthostatic, POTS, autonomic, and related terms.
- Chronic Lyme accepts Lyme, Borrelia, neuroborreliosis, and related terms.

After that, `build_augmented.py` injects paper and registry labels, `build_labels_sidecar.py` builds
the corrected labels, `endpoint_classify.py` and `drug_classify.py` add endpoint/intervention metadata,
and `build_master_csv.py` writes the final Long COVID and adjacent-condition CSVs.

## Main CSVs And What They Contain

### `training_set_manifest_augmented.csv`

Purpose: pipeline manifest for all five conditions.

Current shape:

- 315 rows
- 151 train, 104 val, 60 test
- 255 train/val rows
- 88 paper-extracted train/val rows
- 6 registry-adapted train/val rows

Columns:

| Column | Meaning |
|---|---|
| `condition` | condition slug, such as `long_covid` or `fibromyalgia` |
| `split` | `train`, `val`, or `test` |
| `nct` | NCT ID, or adapted registry ID for registry-adapted rows |
| `label_source` | `ctgov_structured`, `paper_extracted`, or `registry_adapted` |
| `date` | results-publication or result-posting date used by the temporal split |
| `title` | trial title |

Use this when you need to understand which trial IDs went into each condition-specific Natural study.

### `master_pulled_data.csv`

Purpose: primary Long COVID benchmark and target export.

Current shape:

- 210 rows
- Long COVID only
- 50 train/val benchmark trials
- train/val sources: 21 trial listing, 23 paper, 6 registry-adapted
- 9 corpus-learnable train/val trials overall: 8 CT.gov-structured + 1 paper-rescued
- 3 prospective target trials: LIFT, Tirzepatide, IVIG

Grain:

- train/val rows are label-level: one row per trial, outcome, arm label
- test rows are outcome-level in the master CSV
- arm-level target rows, especially for LIFT, are in `long_covid_eval_set.csv`

Important columns:

| Column group | Columns | Meaning |
|---|---|---|
| identifiers | `nct`, `condition`, `split`, `title` | trial identity and split |
| provenance | `data_source`, `paper_pmcid`, `paper_link_via`, `llm_confidence` | where the label came from |
| target flags | `is_prediction_target`, `in_nikita_seed`, `has_label` | whether the row is a target, appeared in Nikita's seed, or has an outcome label |
| trial metadata | `phase`, `overall_status`, `enrollment`, `primary_completion_date`, `results_public_date` | trial status/timing metadata |
| intervention metadata | `interventions`, `primary_intervention`, `intervention_types`, `drug_class`, `drug_accessibility`, `is_candidate_drug`, `candidate_drug` | intervention and drug-accessibility annotations |
| design flags | `masking`, `is_open_label`, `comparator_type`, `is_combination_arm`, `underpowered`, `cross_condition_duplicate` | design caveats and duplicate flags |
| outcome label | `outcome`, `arm`, `endpoint_type`, `is_change_from_baseline`, `representation`, `raw_value`, `n`, `clean_outcome`, `scale_proportion` | model-ready outcome fields |
| endpoint metadata | `endpoint_domain`, `endpoint_modality`, `self_reportable`, `instrument`, `endpoint_match_to_test` | endpoint type and whether it is learnable from patient text |
| NATURAL premise | `is_corpus_learnable`, `corpus_learnable_tier` | whether NATURAL's premise plausibly holds for the row |

Use this as the main Long COVID table.

### `cluster_benchmark.csv`

Purpose: adjacent-condition benchmark, kept separate from Long COVID.

Current shape:

- 581 rows
- conditions: ME/CFS, fibromyalgia, dysautonomia, chronic Lyme
- same schema as `master_pulled_data.csv`
- train/val trials: ME/CFS 18, fibromyalgia 142, dysautonomia 41, chronic Lyme 4

This is not pooled with the Long COVID benchmark because NATURAL does not train across trials.

### `labels_sidecar.csv`

Purpose: corrected label export for train/val rows.

Current shape:

- 689 rows
- 582 continuous, 66 binary, 41 percentage
- 167 Long COVID rows
- 179 paper-extracted rows, 12 registry-adapted rows, 498 CT.gov-structured rows

Columns:

| Column | Meaning |
|---|---|
| `nct`, `condition`, `split`, `label_source` | trial identity and provenance |
| `outcome`, `arm` | primary outcome and non-placebo arm |
| `endpoint_type` | `binary`, `percentage`, or `continuous` |
| `is_change_from_baseline` | continuous endpoint is a change/delta rather than an absolute score |
| `raw_value` | the raw per-arm outcome value |
| `n` | denominator or arm size |
| `clean_outcome` | rate for binary/percentage, raw mean for continuous |
| `scale_proportion` | oriented `[0,1]` value when a bounded scale is available |

Use this if you need a model-ready outcome rather than pinned Natural's native `value/N` field.

### `endpoint_classification.csv`

Purpose: endpoint metadata.

Columns:

- `endpoint_text`
- `endpoint_domain`
- `endpoint_modality`
- `self_reportable`
- `instrument`

This feeds the endpoint fields in the master and cluster CSVs.

### `drug_classification.csv`

Purpose: intervention metadata.

Columns:

- `intervention`
- `drug_class`
- `drug_accessibility`

This feeds `drug_class` and `drug_accessibility`, which are part of the corpus-learnability verdict.

### `long_covid_eval_set.csv`

Purpose: arm-level Long COVID prospective target inventory.

Current shape:

- 153 rows
- 88 unique trials
- status mix: recruiting, active-not-recruiting, enrolling-by-invitation
- includes LIFT factorial arms after relabeling

Columns:

| Column | Meaning |
|---|---|
| `nct` | NCT ID |
| `status` | current recruitment status in the relaxed target universe |
| `is_lift` | whether this row is LIFT |
| `title` | trial title |
| `prediction_target_arm` | arm to predict |
| `corpus_drug` | matched drug name in the Long COVID corpus |
| `corpus_signal_authors` | distinct-author signal for that drug |
| `primary_outcome` | registered primary outcome |

Use this for target selection and LIFT-specific arm analysis.

## What Is Actually In The Long COVID Master CSV

The Long COVID master table should be read as:

- 50 completed benchmark trials with ground-truth labels
- 3 prospective target trials
- 9 train/val trials that fit NATURAL's premise well enough to be the real core benchmark
  (8 CT.gov-structured + 1 paper-rescued)
- many off-premise rows that are useful as an inventory, but not necessarily suitable for NATURAL
  estimation from patient-community text

The 9 corpus-learnable benchmark trials are the most important number for Natural-style evaluation.
The 50-trial count is the broader Long COVID outcome benchmark pool.
If discussing only the 21 CT.gov-structured trials, use 8 corpus-learnable trials.

## What To Say About Nikita's Original Long COVID Set

The faithful reproduction is useful because it shows we can run her pinned code and recover her
completed Long COVID set. But it should not be presented as a clean Long COVID benchmark.

The condition matcher admits acute COVID because a trial condition term like `covid` is treated as a
match for the condition string `long covid`. In the current audit, the faithful Long COVID matcher
kept 12 acute-COVID or acute-hospitalization trials and missed genuine post-COVID trials. The canonical
dataset fixes that by requiring post-COVID / PASC / long-COVID terms.

Suggested wording:

> We first reproduced Nikita's shared Long COVID study faithfully. That reproduction surfaced a
> condition-matching issue: the original matcher includes acute COVID trials because it treats
> generic `covid` as matching `Long Covid`, while also missing trials tagged as post-COVID or PASC.
> Our canonical Long COVID benchmark therefore uses the same Natural design filters, but replaces
> the substring condition matcher with a stricter Long COVID classifier.

## Caveats To Keep In The Write-Up

- Do not call this training data for NATURAL. It is a benchmark plus target set.
- Do not say the sidecar fixes native Natural output unless the Natural evaluation code is changed to
  consume it.
- LIFT's relabeled arms are represented in `long_covid_eval_set.csv`; direct pinned-Natural execution
  still needs relabeled JSON or Experiment files.
- Paper-extracted labels are measured as conservative but noisy. The validation run found roughly
  75% full match and 88% match-or-partial among committed extractions against CT.gov ground truth.
- Non-CT.gov registry-adapted trials expand the Long COVID benchmark but cross the original CT.gov-only
  boundary. They are marked explicitly as `registry_adapted`.
- Acute-COVID contamination is a faithful-mode/Nikita-seed issue, not part of the canonical Long COVID
  master export.
