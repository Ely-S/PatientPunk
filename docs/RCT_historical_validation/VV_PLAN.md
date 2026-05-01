# Verification and Validation Plan for RCT Historical Validation

## Purpose

This plan defines the checks needed to verify and validate the Reddit-derived treatment-signal analysis used in the paper, *A Methodology for Gathering Real-World Evidence at Scale: Using NLP-Extracted Community Treatment Reports to Predict Clinical Trial Outcomes*.

The analysis asks whether pre-publication reports from `r/covidlonghaulers` identify the same direction of treatment effect later observed in paired clinical studies. The primary outputs are the responder/non-responder charts and tables in `analysis.ipynb` and the reproducibility package in `output/`.

## Scope

The V&V scope covers:

- Data provenance from Arctic Shift downloads through SQLite analysis databases.
- Reply-chain reconstruction and upstream drug context propagation.
- Drug mention extraction, treatment-use filtering, canonicalization, and sentiment classification.
- One-user-per-drug deduplication.
- Statistical calculations used in Figure 1 and the response-composition tables.
- Agreement between the generated figures/tables and the claims made in the paper.

The plan does not validate Reddit as a representative sample of all Long COVID patients. That limitation should be reported separately as a study limitation.

## Primary Claims to Verify

| Claim | Evidence required |
|---|---|
| All included Reddit data predates the paired clinical result. | Sampling-window audit, publication/cutoff audit, and timestamp checks. |
| Each treatment report is counted at most once per user per drug. | Deduplication query audit and spot checks of repeated users. |
| Positive sentiment is grouped as responder; negative, neutral, and mixed are grouped as non-responder. | Classification-label audit and analysis-code review. |
| Figure 1 and the tables use Wilson 95% confidence intervals and two-sided binomial tests against `p = 0.50`. | Independent statistical recomputation. |
| Drugs paired with positive trials show significantly positive community signal; drugs paired with null trials do not. | Recomputed p-values, confidence intervals, and clinical-outcome mapping review. |
| The result is not an artifact of broken reply context, synonym handling, duplicate reports, or LLM labeling drift. | Targeted pipeline audits, blinded manual review, and sensitivity analyses. |

## Verification Activities

### V1. Data Provenance and Freeze

Objective: confirm that the analyzed datasets are the intended Arctic Shift samples and that the final paper uses a frozen, reproducible data snapshot.

Checks:

- Record the Arctic Shift source URL, download command/configuration, subreddit, date range, and scrape date for each dataset.
- Record file names, sizes, and SHA-256 hashes for raw JSON files and processed SQLite databases.
- Confirm the five analysis databases match the reproducibility package:
  - `famotidine_loratadine_prednisone_may_sept_2021.db`
  - `paxlovid_pre_stop_pasc_4mo.db`
  - `colchicine_naltrexone_year_2021.db`
  - `naltrexone_jan_2022.db`
  - `corpus_baseline_onemonth.db`
- Confirm that the analysis code and notebooks record the git commit, model names, prompt versions, run IDs, and database hashes used for the final figures.

Acceptance criteria:

- Every final figure/table can be traced to immutable input files and a specific code revision.
- No final database has an unknown source, missing hash, or unrecorded processing step.

### V2. Sampling Window and Leakage Audit

Objective: verify that Reddit posts/comments used for each drug predate the paired clinical result.

Checks:

- Independently query `MIN(post_date)` and `MAX(post_date)` for all posts included in each drug-specific analysis.
- Confirm that all included posts fall within the intended windows:

| Drug | Window | Paired result cutoff |
|---|---|---|
| famotidine | 2021-05-01 to 2021-09-30 | Glynne et al. 2021 |
| loratadine | 2021-05-01 to 2021-09-30 | Glynne et al. 2021 |
| prednisone | 2021-05-01 to 2021-09-30 | Utrero-Rico et al. 2021 / later null evidence |
| paxlovid | 2024-03-01 to 2024-06-06 | STOP-PASC Jun 2024 |
| colchicine | 2021-01-01 to 2021-12-31 | Bassi et al. 2025 |
| naltrexone | 2021-01-01 to 2022-01-30 | O'Kelly et al. Jul 2022 |

- Search sampled text for explicit discussion of the paired trial result where feasible, especially near cutoff dates.
- Confirm that date filters are applied before deduplication and aggregation.

Acceptance criteria:

- No analyzed report occurs after the stated cutoff.
- Any borderline post is manually reviewed and either excluded or documented.

### V3. Reddit Thread Reconstruction

Objective: verify that parent-child context is preserved well enough for comments such as "it helped me too" to be attributed to the correct treatment.

Checks:

- Count comments with missing or orphaned `parent_id` references before and after cleaning.
- Randomly sample at least 50 reply chains across short, medium, and deep threads.
- For each sampled chain, verify:
  - parent order is correct;
  - upstream text belongs to the same thread;
  - upstream drug mentions are inherited only from ancestors, not unrelated comments;
  - question-only parent posts can provide drug context to child replies without entering sentiment classification themselves.
- Compare results using one, two, and unlimited upstream-context depth for a sample of classifications.

Acceptance criteria:

- No sampled chain contains a broken or cross-thread parent linkage.
- Drug context errors are rare enough not to change any primary drug-level conclusion; any systematic error must be corrected before submission.

### V4. Drug Mention Extraction

Objective: verify that the extraction step captures target treatment mentions while avoiding obvious false positives.

Checks:

- Create a blinded manual review sample for each target drug:
  - 50 extracted mentions per drug, stratified by direct mention vs inherited context where possible.
  - 50 non-extracted posts/comments from each sampling window enriched for likely synonyms or misspellings.
- Measure precision and recall against manual review.
- Confirm that batch-output length mismatches cause retry/splitting and do not silently truncate records.
- Confirm pure question posts are excluded from downstream sentiment classification while still contributing drug context to replies.

Acceptance criteria:

- Target-drug extraction precision is at least 95% on reviewed extracted mentions.
- No high-frequency synonym, brand name, abbreviation, or misspelling is missing from the target alias list.
- Any false negative pattern affecting more than one reviewed item is corrected or explicitly documented.

### V5. Canonicalization and Alias Handling

Objective: verify that surface forms are grouped into the correct compound without collapsing specific drugs into broad categories.

Checks:

- Review canonical mappings and alias lists for all six target drugs.
- Confirm expected mappings such as:
  - `Pepcid`, `pepcid ac`, and informal famotidine variants to `famotidine`;
  - `LDN` and `low dose naltrexone` to `naltrexone` or the chosen canonical naltrexone bucket;
  - relevant brand/generic/misspelling variants for `paxlovid`, `loratadine`, `prednisone`, and `colchicine`.
- Confirm broad categories remain separate from specific compounds, e.g. `antihistamines` is not merged into `famotidine` or `loratadine`.
- Re-run the per-drug counts after alias edits and compare deltas.

Acceptance criteria:

- All target-drug aliases used in the final query are manually reviewed.
- No reviewed mapping collapses a specific compound into a broader class or a different compound.
- Count changes after alias review are recorded and propagated to final figures/tables.

### V6. Treatment-Use Filtering and Sentiment Classification

Objective: verify that only personal treatment experiences enter the primary analysis and that sentiment labels match the paper's definitions.

Checks:

- Conduct blinded manual adjudication of at least:
  - 50 positive labels per high-volume drug where available;
  - 25 negative/neutral/mixed labels per drug where available;
  - all labels for low-volume edge cases if fewer than 25 exist.
- Each sampled item should be reviewed with the same upstream context available to the classifier.
- Reviewers should assign:
  - personal-use flag;
  - sentiment: positive, negative, mixed, neutral;
  - signal strength: strong, moderate, weak, or n/a;
  - whether upstream context was necessary.
- Resolve disagreements by adjudication and record final labels.
- Compute agreement between LLM labels and adjudicated labels.
- Special attention should be paid to:
  - research/article citations;
  - encouragement without personal use;
  - hypothetical or planned use;
  - dose questions;
  - side effects with net benefit;
  - mixed outcomes across different symptoms.

Acceptance criteria:

- At least 90% agreement on personal-use inclusion in the adjudicated sample.
- At least 85% agreement on responder vs non-responder status.
- Any systematic labeling error is corrected by prompt revision or post-hoc exclusion rules, followed by reclassification and re-analysis.

### V7. Deduplication Audit

Objective: verify that prolific users do not dominate the result and that the "best report" rule is implemented as described.

Checks:

- Independently query the number of raw treatment reports and unique users per drug.
- Confirm the expected final unique-user counts:

| Drug | Expected unique users |
|---|---:|
| famotidine | 207 |
| loratadine | 107 |
| prednisone | 176 |
| paxlovid | 153 |
| colchicine | 40 |
| naltrexone | 76 |

- For users with multiple reports for the same drug, sample at least 30 user-drug pairs and verify the retained report follows:
  - sentiment priority: positive > mixed > neutral > negative;
  - signal-strength tiebreak: strong > moderate > weak.
- Quantify how many users changed class because of deduplication.

Acceptance criteria:

- Each final row represents one user-drug pair.
- Sampled retained reports match the documented priority rule.
- The effect of deduplication is reported, including whether it materially changes responder percentages.

### V8. Statistical Recalculation

Objective: verify that the reported percentages, confidence intervals, and p-values are correct.

Checks:

- Recompute all primary statistics independently from the final deduplicated counts using a separate script or notebook.
- Confirm:
  - responder percentage = `positive / n`;
  - non-responder percentage = `(negative + neutral + mixed) / n`;
  - confidence intervals are 95% Wilson score intervals;
  - p-values are two-sided exact binomial tests against `p = 0.50`;
  - responder and non-responder counts sum to `n`;
  - Figure 1 and table values are generated from the same `resp_df`.
- Verify the expected final values:

| Drug | n | % responders | p vs 50% |
|---|---:|---:|---:|
| famotidine | 207 | 78.7% | 2.88e-17 |
| loratadine | 107 | 68.2% | 2.06e-04 |
| naltrexone | 76 | 65.8% | 0.0079 |
| colchicine | 40 | 62.5% | 0.1539 |
| paxlovid | 153 | 52.3% | 0.6278 |
| prednisone | 176 | 52.3% | 0.5979 |

Acceptance criteria:

- Independent recomputation matches displayed values within rounding tolerance.
- Any discrepancy between notebook, figure, table, or manuscript text is corrected before submission.

### V9. Figure and Table Verification

Objective: verify that figures and tables faithfully display the analyzed data.

Checks:

- Confirm Figure 1 uses the final deduplicated user-level table, not raw report counts.
- Confirm labels, color legend, confidence intervals, trial-direction annotations, and `n` values are correct.
- Confirm captions state:
  - data are pre-publication;
  - responders are positive sentiment reports;
  - non-responders include negative, neutral, and mixed reports;
  - confidence intervals are Wilson 95% intervals;
  - p-values are two-sided binomial tests against 50%.
- Compare generated `analysis.ipynb`, `output/paper_figures.html`, and `output/figure1.png` for consistency.

Acceptance criteria:

- Every number in the manuscript figure/table can be traced to the final analysis table.
- Captions do not overstate statistical significance or imply representativeness beyond the sampled Reddit population.

### V10. Reproducibility Test

Objective: verify that another analyst can regenerate the primary outputs from the frozen databases and code.

Checks:

- Start from a clean checkout and install `docs/RCT_historical_validation/requirements.txt`.
- Place the five frozen databases in `docs/RCT_historical_validation/data/`.
- Run:

```bash
cd docs/RCT_historical_validation
python _build_paper_figures.py
```

- Confirm the build produces:
  - `output/paper_figures.ipynb`;
  - `output/paper_figures_executed.ipynb`;
  - `output/paper_figures.html`;
  - `output/figure1.png`.
- Compare recomputed statistics with the frozen expected-output table.

Acceptance criteria:

- The notebook executes without manual intervention.
- Reproduced values match the submitted values within rounding tolerance.

## Validation Activities

### VA1. Clinical Trial Pairing Review

Objective: validate that each Reddit drug signal is compared with an appropriate clinical reference.

Checks:

- Confirm that each paired study evaluates the same or sufficiently similar intervention and outcome domain.
- Confirm trial direction labels are justified as `positive` or `null`.
- Record trial sample size, endpoint, publication date, and why it is the relevant comparison.
- For prednisone, explicitly document the distinction between the small early positive study and the later null/meta-analytic evidence.

Acceptance criteria:

- A clinically knowledgeable reviewer agrees with the intervention mapping and trial-direction labels.
- Any ambiguous pairing is disclosed in the manuscript.

### VA2. Construct Validity of "Responder"

Objective: validate that the binary responder variable is a defensible proxy for patient-perceived benefit.

Checks:

- Review a stratified sample of positive, mixed, neutral, and negative reports.
- Confirm that "positive" reports generally describe meaningful symptom improvement, quality-of-life improvement, or continued use due to benefit.
- Confirm that mixed reports are not being incorrectly counted as responders when the outcome is ambiguous or trade-off-heavy.
- Compare the primary result with sensitivity definitions:
  - positive only vs all others, primary;
  - positive + mixed vs all others;
  - positive vs negative only, excluding neutral/mixed;
  - strong/moderate signal only.

Acceptance criteria:

- The primary conclusions are qualitatively stable under reasonable sensitivity definitions, or exceptions are reported.
- The manuscript clearly states that "responder" means self-reported perceived benefit, not clinician-measured recovery.

### VA3. LLM Labeling Robustness

Objective: validate that results are not dependent on one unstable model pass.

Checks:

- Reclassify an adjudication subset with a second model or a repeated call using locked prompts.
- Compare responder/non-responder agreement and drug-level responder percentages.
- Record model names, dates, temperatures, prompts, and parser failures.
- Confirm batch failures are retried or fall back to smaller units rather than silently dropping outputs.

Acceptance criteria:

- Repeated or alternate-model labels do not change the trial-direction match for any drug.
- Any unstable label category is described as a limitation and, if material, adjudicated manually.

### VA4. Bias and Confounding Review

Objective: validate that the paper's interpretation is appropriately bounded.

Checks:

- Evaluate likely biases:
  - self-selection into Reddit and into treatment discussion;
  - placebo/nocebo effects;
  - concurrent treatments;
  - severity and symptom heterogeneity;
  - repeated community narratives and hype cycles;
  - survivorship and posting-frequency bias;
  - deleted accounts or missing comments;
  - trial-publication leakage.
- Confirm that the manuscript presents the method as a fast, low-cost signal-generation approach, not as a substitute for randomized trials.

Acceptance criteria:

- Limitations section explicitly covers sampling bias, observational design, LLM-labeling error, and outcome heterogeneity.
- Discussion claims do not imply causal efficacy from Reddit data alone.

### VA5. External Plausibility and Negative Controls

Objective: validate that the observed signal is not simply "Reddit is positive about everything."

Checks:

- Compare target-drug positive rates against a broad corpus baseline when available.
- Include null-trial drugs as negative controls.
- Consider adding additional drugs with known null or harmful trial results if data volume permits.
- Examine whether positive-trial and null-trial pools separate under an aggregate test, while noting that only six drugs are included.

Acceptance criteria:

- The paper reports that positive-trial drugs and null-trial drugs behave differently in this sample.
- The small number of drug-level comparisons is acknowledged.

## Evidence Log Template

| ID | Activity | Owner | Date | Inputs | Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|
| V1 | Data provenance and freeze |  |  |  |  |  |  |
| V2 | Sampling-window audit |  |  |  |  |  |  |
| V3 | Thread reconstruction audit |  |  |  |  |  |  |
| V4 | Drug extraction audit |  |  |  |  |  |  |
| V5 | Canonicalization review |  |  |  |  |  |  |
| V6 | Sentiment adjudication |  |  |  |  |  |  |
| V7 | Deduplication audit |  |  |  |  |  |  |
| V8 | Statistical recalculation |  |  |  |  |  |  |
| V9 | Figure/table verification |  |  |  |  |  |  |
| V10 | Reproducibility test |  |  |  |  |  |  |
| VA1 | Trial pairing review |  |  |  |  |  |  |
| VA2 | Responder construct validation |  |  |  |  |  |  |
| VA3 | LLM robustness check |  |  |  |  |  |  |
| VA4 | Bias and confounding review |  |  |  |  |  |  |
| VA5 | External plausibility checks |  |  |  |  |  |  |

## Submission Quality Gate

Before manuscript submission, the study package should include:

- Frozen raw and processed data hashes.
- Final run IDs, prompts, model names, and git commit.
- Executed analysis notebook and exported HTML.
- Manual adjudication sample and agreement summary.
- Independent statistical recalculation output.
- Figure/table cross-check against manuscript text.
- A limitations statement covering representativeness, observational inference, LLM error, and symptom heterogeneity.

The paper should be considered ready for submission only after all verification activities pass or any unresolved failures are explicitly disclosed as limitations.
