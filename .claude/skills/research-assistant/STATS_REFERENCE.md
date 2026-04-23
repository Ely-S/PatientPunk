# Statistics Reference for the Research-Assistant Skill

Concise catalog of statistical tests the skill uses and the warnings each one must emit. This is prose guidance, not wrapper code — Claude writes the library calls inline in the notebook, then annotates with the relevant warnings as markdown callouts.

## Golden rule: user-level aggregation

**Always aggregate to one data point per user per drug before any test.** Multiple reports from the same user violate independence and will inflate significance. The standard aggregation:

```python
# From treatment_reports joined with treatment table
# sentiment: 'positive' → 1.0, 'mixed' → 0.5, 'neutral' → 0.0, 'negative' → -1.0
user_drug = df.groupby(['user_id', 'drug_clean']).agg(
    avg_score=('score', 'mean'),
    n_reports=('score', 'count'),
).reset_index()
user_drug['outcome'] = user_drug['avg_score'].apply(classify_outcome)
# classify_outcome: >0.7 positive, <-0.3 negative, else mixed/neutral
```

All tests below operate on this user-level DataFrame.

## Warning severities

Every analysis result should list warnings with one of three severities. Surface `caution` and `unreliable` warnings to the reader as markdown callouts (`> ⚠️ ...`). `caveat` can stay inline in the stats table.

| Severity | Meaning | Reader effect |
|---|---|---|
| `caveat` | Minor note, interpretation still valid | Mention, don't belabor |
| `caution` | Interpret carefully — result may be misleading | Surface visibly in prose |
| `unreliable` | Do not trust this result | Show test ran but refuse to draw conclusions |

## Test catalog

### 1. Descriptive summary — single drug
- **Use when:** characterizing one treatment's outcome distribution.
- **Library:** `statsmodels.stats.proportion.proportion_confint(method='wilson')` for the positive-rate CI; pandas `.describe()` for the rest.
- **Report:** n_users, n_posts, pct_positive with Wilson CI, pct_mixed/neutral/negative, mean/median/std of numeric sentiment score.
- **Warnings:** (none specific — size warnings apply at the comparison stage)

### 2. Binomial test — observed rate vs. baseline
- **Use when:** asking "does this drug's positive rate differ from chance (50%) or some known baseline?"
- **Library:** `scipy.stats.binomtest(n_pos, n, p=baseline, alternative='two-sided')`.
- **Effect size:** Cohen's h = `2*arcsin(sqrt(p_obs)) - 2*arcsin(sqrt(p_baseline))`.
- **CI:** Wilson score via `proportion_confint`.
- **Warnings:**
  - `small_sample` (caveat) — `n < 20`.
  - `no_variation` (caution) — all users positive or all negative.
  - `extreme_baseline` (caution) — `baseline` is 0 or 1.

### 3. Two-group comparison — Mann-Whitney U + Fisher's exact / chi-square
- **Use when:** comparing two drugs (or two user subgroups) on sentiment.
- **Library for continuous:** `scipy.stats.mannwhitneyu(a, b, alternative='two-sided')` — or `pingouin.mwu` if pingouin is available (gives rank-biserial correlation directly).
- **Library for categorical (2×2):** `scipy.stats.fisher_exact` if any expected cell < 5, else `scipy.stats.chi2_contingency`. Use `statsmodels.stats.contingency_tables.Table2x2` for the odds ratio + CI.
- **Effect sizes:** rank-biserial correlation `r` for MWU (derive from U: `1 - 2U/(n1*n2)`); Cramér's V for chi-square via `scipy.stats.contingency.association`.
- **Warnings:**
  - `sample_too_small` (unreliable) — either group `n < 5`.
  - `small_sample` (caveat) — either group `5 ≤ n < 15`.
  - `imbalanced_samples` (caveat) — size ratio > 4:1.
  - `no_within_variation` (caution) — one group has zero within-group variation.
  - `identical_distributions` (unreliable) — all values identical across both groups.
  - `single_category` (unreliable) — only one outcome category observed.
  - `sparse_cells` (caveat) — any cell count < 5 in the 2×2.
  - `large_effect_small_n` (caution) — `|r| > 0.5` but total `n < 30` (suspect instability).

### 4. Wilcoxon signed-rank — paired within-subject
- **Use when:** comparing two drugs on the same users (users who tried both).
- **Library:** `scipy.stats.wilcoxon` or `pingouin.wilcoxon`.
- **Effect size:** rank-biserial `r`.
- **Report:** direction (`drug_a_better` / `drug_b_better` / `no_difference`), mean/median difference, n_paired.
- **Warnings:** `sample_too_small` (unreliable) — `n_paired < 5`; `no_variation` (unreliable) — all differences zero.

### 5. Kruskal-Wallis — 3+ group comparison
- **Use when:** comparing sentiment across 3 or more groups (e.g., treatment classes).
- **Library:** `scipy.stats.kruskal(*arrays)` for the omnibus; pairwise Mann-Whitney + BH FDR via `statsmodels.stats.multitest.multipletests(method='fdr_bh')`.
- **Effect size:** eta-squared `η² = (H - k + 1) / (N - k)` where `H` is Kruskal's statistic, `k` is number of groups, `N` is total n.
- **Warnings:**
  - `small_group` (caveat) — any group `n < 10`.
  - `no_within_variation` (caution) — any group has zero within-group variation.
  - `multiple_comparisons` (caveat) — more than 6 pairs tested (Bonferroni gets conservative fast).

### 6. Logistic regression — predictors of positive outcome
- **Use when:** asking "which user/drug attributes predict a positive outcome, controlling for others?"
- **Library:** `statsmodels.api.Logit(y, sm.add_constant(X))`.
- **Report:** per-predictor odds ratio with 95% CI and p-value; pseudo-R² (McFadden); AIC; convergence flag.
- **Warnings:**
  - `no_predictors` (unreliable) — no predictors have sufficient coverage (< 10 non-null each).
  - `zero_variance_predictor` (caveat) — a predictor is constant; dropped.
  - `sparse_predictor` (caveat) — a predictor has < 10 non-null rows.
  - `high_vif` (caution) — any predictor's VIF > 10 via `statsmodels.stats.outliers_influence.variance_inflation_factor` → multicollinearity.
  - `rows_dropped` (caveat) — more than 20% of rows dropped due to missing predictors.
  - `low_epp` (caution) — events per predictor < 10 (rule of thumb for stable logistic fits).
  - `non_convergence` (unreliable) — optimizer didn't converge.
  - `unstable_ll` / `unstable_r2` (unreliable) — log-likelihood or pseudo-R² non-finite.
  - `no_sig_small_n` (caution) — no predictor reached p < 0.05 and `n < 100` (underpowered).

### 7. OLS regression — predictors of numeric sentiment
- **Use when:** predicting continuous sentiment score from predictors.
- **Library:** `statsmodels.api.OLS(y, sm.add_constant(X))`.
- **Report:** per-predictor coefficient with CI and p-value; R², adjusted R²; F-statistic with p-value.
- **Warnings:** same predictor-coverage / VIF / row-drop warnings as logistic; plus `no_variation` (unreliable) if outcome is constant, `unstable_fit` (unreliable) if F-statistic is non-finite.

### 8. Time trend — monthly sentiment over time
- **Use when:** asking "is sentiment for this drug improving or declining over the observation window?"
- **Library:** `scipy.stats.kendalltau(months, avg_sentiment)` for the non-parametric trend test; `scipy.stats.linregress` for the slope estimate.
- **Report:** Kendall's τ, p-value, slope, direction (`improving` / `declining` / `stable`), n_months, per-month data points.
- **Warnings:**
  - `misc` (caveat) — fewer than 3 months of data; trend not meaningful (return early).
  - `short_series` (caution) — fewer than 6 months.
  - `gappy_series` (caution) — non-contiguous months.
  - `no_variation` (caution) — monthly sentiment is constant.

### 9. Survival (Cox PH) — time to positive outcome
- **Use when:** asking "how quickly do users on this drug reach a positive outcome, and which covariates affect that?" (Requires a time-to-event column.)
- **Library:** `lifelines.CoxPHFitter`. **Optional dependency** — if `lifelines` isn't installed, skip this analysis and note why.
- **Report:** per-predictor hazard ratio with CI and p-value; concordance index; n_users, n_events, n_censored; median time.
- **Warnings:** same sample-size warnings as other regression tests; `small_events` (caution) if `n_events < 10`.

### 10. Spearman correlation
- **Use when:** measuring monotonic relationship between two continuous/ordinal variables (e.g., n_reports vs. avg_sentiment).
- **Library:** `scipy.stats.spearmanr(x, y)`.
- **Report:** ρ, p-value, n.
- **Warnings:** `small_sample` (caveat) — `n < 20`; `no_variation` (unreliable) — either variable is constant.

### 11. Propensity score matching — causal comparison
- **Use when:** comparing treated vs. untreated users on outcome while controlling for confounders.
- **Library:** `causalinference.CausalModel`. **Optional dependency** — skip if unavailable.
- **Report:** n_matched, n_unmatched_treated, ATE (average treatment effect) with CI and p-value, balance table (SMD before/after per covariate).
- **Warnings:** `poor_balance` (caution) if any post-match SMD > 0.25; `few_matches` (unreliable) if n_matched < 20.

## Sample-size discipline (applies across all tests)

- Prefer **binary comparisons** (two groups) when any subgroup has `n < 20`. Splitting a small sample into 3+ tiers produces wide CIs that can't distinguish groups.
- Never present a non-significant comparison as a finding. If `p > 0.05` and CIs overlap, say "we don't have enough data to tell" — not "Drug A is similar to Drug B."
- **Every visual group-comparison requires a matching statistical test in the prose.** Placing bars side by side without a test invites false inference.

## Sensitivity check (required on every main finding)

After the primary analysis, re-run on a robustness subset:
- Drop the 3 most extreme users (by `avg_score`).
- OR restrict to `signal_strength == 'strong'` reports only.

Then write one sentence: either "Conclusion holds" or "Conclusion shifts — flagged as fragile."

## Optional dependencies

| Test | Library | Installed by default on `main`? |
|---|---|---|
| Most tests | `scipy`, `statsmodels` | Required — notebook setup assumes these |
| Effect sizes via pingouin | `pingouin` | Optional — fall back to manual rank-biserial computation |
| Survival (Cox PH) | `lifelines` | Optional — skip analysis if missing |
| Propensity matching | `causalinference` | Optional — skip analysis if missing |

If an optional library is missing, the skill should note it in the analysis plan (`"Survival analysis skipped — lifelines not installed"`) rather than failing the notebook build.

## Reporting template for every test

When emitting results, Claude should produce:

1. **One-line headline** — plain language, patient-readable.
   *Example:* "LDN users report a 94% positive rate, significantly higher than the 50% baseline (p < 0.001)."
2. **Formal line** — test name, test statistic, p-value, effect size with name.
   *Example:* "Binomial test: 16/17, p < 0.001, Cohen's h = 0.96."
3. **NNT (if applicable)** — `1 / (treatment_rate - baseline_rate)`, rounded to one decimal.
   *Example:* "NNT = 2.3 — roughly 1 in 2.3 users reports benefit beyond chance."
4. **Warnings** — any `caution`/`unreliable` warnings as markdown callouts:
   ```
   > ⚠️ Small sample (n=17) — interpret with caution.
   ```
5. **Sensitivity sentence** — one line confirming or flagging fragility.
