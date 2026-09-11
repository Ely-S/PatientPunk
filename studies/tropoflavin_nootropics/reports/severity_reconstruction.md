# Reconstructed side-effect models: methods and reproducibility status

Validated on 2026-09-11 against the 19 preserved September 3 community databases. All 19 database SHA-256 hashes match the saved fine-grained analysis manifest. This is a newly implemented analysis of the same inputs. It does **not** reproduce every historical eligibility decision or coefficient, and it does not replace the frozen September 3 reports.

The original fine-grained model scripts were not recovered in the available Git history. Saved manifests, aggregate eligibility tables, coefficients, and methods descriptions provided the reconstruction specification. Differences are recorded below rather than hidden behind the original report date.

## What can be reproduced

All ten compounds' classified-author, affected-author, explicitly graded-author, and explicitly graded-effect totals match the saved results exactly. The analysis globally deduplicates the same author and compound across communities. For a repeated canonical side effect, it retains the highest explicitly stated grade; different effects remain separate.

| Compound | Classified authors | Authors reporting an effect | Authors with explicit severity | Explicitly graded effects |
| --- | ---: | ---: | ---: | ---: |
| 4'-DMA | 250 | 92 | 3 | 4 |
| 7,8-DHF | 684 | 275 | 22 | 27 |
| 9-MBC | 255 | 119 | 10 | 12 |
| BPC-157 | 7,227 | 2,441 | 285 | 335 |
| Cerebrolysin | 940 | 299 | 29 | 33 |
| Dihexa | 435 | 182 | 11 | 11 |
| Lion's mane | 9,530 | 3,660 | 284 | 312 |
| NSI-189 | 1,182 | 615 | 96 | 114 |
| Selank | 2,243 | 577 | 54 | 59 |
| Semax | 3,755 | 1,277 | 128 | 147 |

An ungraded side effect remains missing for severity analysis. A report without a mapped side effect contributes zero to the occurrence/count outcome, which means no mapped effect was reported, not that the author was confirmed free of side effects.

## Dose eligibility is not an exact historical reproduction

The reconstruction consumes the saved numeric mg midpoints. It does not reparse the original text or claim improved dose attribution. It requires exactly one original numeric dose band after pooling an author's exposure records across communities, takes the geometric mean of distinct positive midpoints, and screens doses within each compound among classified authors meeting that band rule. When at least 20 such authors are present, the screen is median log2 dose plus or minus four scaled median absolute deviations. A zero median absolute deviation produces no statistical screen. The explicit primary exclusion of 7,8-DHF at or above 100 mg still applies. Route-only analyses retain authors whose dose is excluded.

The saved manifests do not fully specify the original order of screening and eligibility operations. The original exclusion tables include additional numeric-dose exposures before final outcome eligibility. This reconstruction's conservative band eligibility and screening population produce the following differences. Historical entries come from `severity_model_eligibility.csv`; reconstructed counts precede rare-route model filtering.

| Compound | Historical graded + dose | Reconstructed graded + dose | Historical graded + dose + route | Reconstructed graded + dose + route |
| --- | ---: | ---: | ---: | ---: |
| 4'-DMA | 1 | 0 | 1 | 0 |
| 7,8-DHF | 2 | 1 | 2 | 1 |
| 9-MBC | 0 | 0 | 0 | 0 |
| BPC-157 | 65 | 65 | 35 | 35 |
| Cerebrolysin | 0 | 0 | 0 | 0 |
| Dihexa | 2 | 2 | 1 | 1 |
| Lion's mane | 23 | 22 | 0 | 0 |
| NSI-189 | 10 | 10 | 2 | 2 |
| Selank | 5 | 5 | 3 | 3 |
| Semax | 10 | 10 | 4 | 4 |

Overall numeric-dose author counts also differ for 4'-DMA (15 historical, 16 reconstructed), 7,8-DHF (48, 46), 9-MBC (8, 7), and Lion's mane (460, 459). The other six compounds match. These differences must be resolved before claiming exact reproduction of the September 3 model estimates.

Cerebrolysin's zero graded numeric-mg sample is not a claim that nobody reported a dose. Volume-based doses require a separate analysis with verified formulation information. This reconstruction does not convert mL to mg. Upstream numeric-unit parsing and dose attribution remain inherited limitations, including any ambiguity in dose schedules or mass-per-bodyweight expressions.

## Models and feasibility rules

Each outcome is attempted separately by treatment and pooled with compound fixed effects, using dose alone, route alone, both predictors, and their interaction. Numeric dose is log2 mg, so its coefficient describes a dose doubling. The pooled slope is a common within-compound association, not a comparison of equal mg across different drugs.

| Outcome | Unit and model | Interpretation |
| --- | --- | --- |
| Any mapped side effect | One author-treatment row; binomial GEE clustered by author | Odds of reporting any mapped effect |
| Distinct mapped side effects | One author-treatment row; negative-binomial GEE, alpha fixed to 1, clustered by author | Relative number of distinct canonical effects reported |
| Explicit severity | One author-treatment-effect row; proportional-odds ordinal GEE clustered by author | Odds of a higher reported grade |
| Maximum explicit severity | One graded author-treatment row; OLS | Change in maximum grade points |
| Average explicit severity | One graded author-treatment row; OLS | Change in mean grade points across that author's distinct graded effects |
| Moderate-or-worse severity | One explicitly graded author-treatment row; binomial GEE clustered by author | Odds of maximum grade at least moderate among authors with explicit severity |

Grades are mild=1, moderate=2, severe=3, life-threatening=4. GEE uses an independence working correlation and author-robust covariance. Treatment-specific OLS uses HC3 covariance; pooled OLS uses author-clustered covariance. All exported coefficient intervals are 95% confidence intervals. They are not individual prediction intervals. Linear models impose equal spacing on ordinal grades, which is why they remain secondary summaries.

The reconstruction requires at least 20 independent authors, rather than 20 effect rows. Routes require five authors per retained level and at least two supported levels. Binary outcomes and every ordinal threshold require five authors on each side. An interaction also requires five authors in each of two compound-specific dose strata within every represented compound-route cell. These are minimum feasibility checks, not a power calculation or evidence that a fitted model is clinically useful.

Ordinal safety-domain adjustment is attempted only when every included domain has at least five authors. Rank-deficient designs, no outcome or dose variation, nonconvergence, separation, and nonfinite estimates or confidence limits suppress coefficient export. Models whose domain adjustment is not supported are explicitly marked `domain_adjustment=false` in the status artifact. This behavior differs from the original saved description of ordinal models with domain fixed effects.

## Results of the offline validation run

The reconstruction evaluated 264 outcome/design/compound combinations: 63 fitted, 196 were not estimable under the declared support rules, and five failed numerical checks. Numerical failures are recorded as failures and have no exported coefficients. No exposure model can estimate 7,8-DHF severity credibly from this sample, whether using the historical two jointly eligible authors or the reconstructed one.

BPC-157 retained 35 jointly eligible graded authors before route filtering. The joint ordinal model retained 33 authors and estimated an odds ratio of 0.61 per dose doubling, with a 95% confidence interval of 0.28 to 1.33. Its safety-domain adjustment was not supported. This interval does not establish an association. The joint mean-severity model estimated -0.23 grade points per doubling (95% CI -0.65 to 0.18); maximum severity estimated -0.29 (-0.69 to 0.12).

Reconstructed pooled mean and maximum coefficients also differ from the saved estimates. The joint mean-severity coefficient is +0.07 points (95% CI -0.27 to 0.42); maximum severity is +0.05 (-0.31 to 0.41). Their intervals include zero. Pooled ordinal fits failed numerical checks. The direction of a historical pooled coefficient should therefore not be presented as a validated, reproducible dose relationship.

These are exploratory associations with author-level links, potentially across different episodes. There is no held-out predictive validation, no multiple-testing correction, and no causal interpretation. Missing dose, route, and explicit severity remain the central study limitations.

## Reproduce and verify

Run from the repository root after `uv sync --locked`. In PowerShell, resolve the external data directory while honoring the existing override:

```powershell
$studyData = if ($env:PATIENTPUNK_DATA) { $env:PATIENTPUNK_DATA } else { Join-Path (Split-Path (Get-Location) -Parent) 'PatientPunk_data' }
$studyRuns = Join-Path $studyData 'studies/tropoflavin_nootropics/runs'
uv run --no-sync python -m studies.tropoflavin_nootropics.severity_models --run-root (Join-Path $studyRuns '2026-09-03-side-effect-severity') --output-dir (Join-Path $studyRuns 'pr140-severity-reconstruction/aggregate')
uv run --no-sync pytest tests/test_severity_models.py
uv run --no-sync ruff check studies/tropoflavin_nootropics/severity_models.py studies/tropoflavin_nootropics/severity_model_data.py studies/tropoflavin_nootropics/severity_model_contracts.py tests/test_severity_models.py
uv run --no-sync mypy studies/tropoflavin_nootropics/severity_models.py studies/tropoflavin_nootropics/severity_model_data.py studies/tropoflavin_nootropics/severity_model_contracts.py
```

The source databases are opened read-only. The runner refuses an output directory inside the repository and writes four aggregate files:

- `severity_reconstructed_manifest.json`: typed settings, methods, limitations, source-database hashes, code hashes, package versions, and aggregate dose exclusions.
- `severity_reconstructed_eligibility.csv`: denominators before model-specific rare-route filtering.
- `severity_reconstructed_status.csv`: every attempted model, its eligible observation/author counts, and its fit or exclusion reason.
- `severity_reconstructed_coefficients.csv`: only finite coefficient estimates with their scales, intervals, and exploratory p values.

Tests cover all six model outcomes, pooled compound adjustment, cluster support, missing severity, deduplication, ambiguous exposures, the 100 mg exclusion, source immutability, artifact privacy, and CLI validation. The validation run passed 16 tests with 94.66% coverage across the three new modules, plus scoped Ruff and mypy checks.

## Exact validation provenance

The local validation manifest was generated at `2026-09-11T20:14:37.143666+00:00`. It records all 19 input database hashes. Packages: NumPy 2.4.6, pandas 3.0.3, SciPy 1.17.1, statsmodels 0.14.6, Patsy 1.0.2, Pydantic 2.12.5.

SHA-256 hashes below identify the source bytes for that validation run; subsequent source changes require a new manifest and rerun.

| Source | SHA-256 |
| --- | --- |
| `severity_models.py` | `35b29ff3971569bbc97d79a705fa43ff29086779a49ad9c9cfcf96be6d050958` |
| `severity_model_data.py` | `0662707d14a9c98038d181420a5931877247af9a910421e8b86a8fa268010b6f` |
| `severity_model_contracts.py` | `0f47633d43d9bb5718eebb27f58a3faee67905ca320675a4535d814478943ae5` |
| `analyze_side_effect_severity.py` | `3c942f776efaf3444b634dfa110eac196bfe1af52b9266002b9e560016e3d0c1` |
| `study_support.py` | `a72620edbed1147430a1e81c1d7f7c360bff9e84757cd7d55d5d882ae6ea426d` |
| `comparator_support.py` | `18828abb1e7b0b9ea6ce907330900d561ca6049e6d2ce0fe8f479a9053c17566` |
| Cohort configuration | `c420e12d450b0b2637983121cd1db06c56c62e9567e002fb257f01887cfc8063` |
