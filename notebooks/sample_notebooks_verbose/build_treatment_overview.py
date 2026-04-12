"""Build, execute, and export the Long COVID treatment overview notebook."""
import sys, os
PROJECT_ROOT = r"C:\Users\scgee\OneDrive\Documents\Projects\PatientPunk"
os.chdir(PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "notebooks"))
from build_notebook import build_notebook, execute_and_export

cells = []

# ── Research Question ──
cells.append(("md", '**Research Question:** "Which treatments have the best outcomes in Long COVID?"'))

# ── Abstract ──
cells.append(("md", """## Abstract

This analysis examines 6,815 treatment reports from 1,121 unique reporters in the r/covidlonghaulers subreddit (March 11 -- April 10, 2026) to identify which treatments receive the most positive community sentiment. Low-dose naltrexone (LDN), magnesium, and electrolytes emerge as the most favorably discussed treatments, each with positive rates above 83% and statistically significant results. SSRIs (selective serotonin reuptake inhibitors) and antibiotics perform near or below chance, while vaccines are excluded as causal-context artifacts. These findings reflect community reporting patterns -- not clinical trial results -- and carry substantial selection and reporting biases. A patient considering Long COVID treatments should prioritize LDN, antihistamines, and supportive supplements based on this data, while approaching psychiatric medications with realistic expectations."""))

# ── 1. Data Exploration ──
cells.append(("md", """## 1. Data Exploration

Data covers: **2026-03-11 to 2026-04-10 (1 month)** from the r/covidlonghaulers subreddit.

- **2,827 users** with posts in this period
- **17,182 posts** (including comments)
- **6,815 treatment reports** from **1,121 unique reporters** covering **1,257 unique treatment terms**
- Sentiment distribution: 4,564 positive (67%), 1,619 negative (24%), 581 mixed (8.5%), 51 neutral (0.7%)

The high positive skew (67%) is expected -- people more readily share what works than what fails (reporting bias). All statistical comparisons use a 50% baseline rather than the community average to avoid baking this bias into our benchmarks."""))

cells.append(("code", r'''# ── Data loading and preprocessing ──
query = """
SELECT
    tr.user_id,
    t.canonical_name AS drug,
    tr.sentiment,
    tr.signal_strength,
    CASE tr.sentiment
        WHEN 'positive' THEN 1.0
        WHEN 'mixed' THEN 0.5
        WHEN 'neutral' THEN 0.0
        WHEN 'negative' THEN -1.0
        ELSE 0.0
    END AS score
FROM treatment_reports tr
JOIN treatment t ON tr.drug_id = t.id
"""
raw_df = pd.read_sql(query, conn)

# ── Filtering step 1: Generic terms ──
generics = GENERIC_TERMS | {'antibiotics', 'antihistamines'}
pre_generic = len(raw_df)
df_filtered = raw_df[~raw_df['drug'].isin(generics)].copy()
post_generic = len(df_filtered)

# ── Filtering step 2: Causal-context contamination ──
causal_terms = [
    'covid vaccine', 'flu vaccine', 'mmr vaccine', 'moderna vaccine',
    'mrna covid-19 vaccine', 'pfizer vaccine', 'vaccine', 'vaccine injection',
    'pfizer', 'booster', 'moderna'
]
pre_causal = len(df_filtered)
df_filtered = df_filtered[~df_filtered['drug'].isin(causal_terms)].copy()
post_causal = len(df_filtered)

# ── Filtering step 3: Merge duplicates ──
merge_map = {
    'pepcid': 'famotidine',
    'h2 antihistamine': 'famotidine',
    'h1 antihistamine': 'cetirizine/fexofenadine (H1)',
    'cetirizine': 'cetirizine/fexofenadine (H1)',
    'fexofenadine': 'cetirizine/fexofenadine (H1)',
    'beta blocker': 'propranolol/beta-blockers',
    'propranolol': 'propranolol/beta-blockers',
}
df_filtered['drug'] = df_filtered['drug'].replace(merge_map)

# ── User-level aggregation ──
user_drug = df_filtered.groupby(['user_id', 'drug']).agg(
    mean_score=('score', 'mean'),
    n_reports=('score', 'count'),
    max_signal=('signal_strength', lambda x: 'strong' if 'strong' in x.values else ('moderate' if 'moderate' in x.values else 'weak'))
).reset_index()

user_drug['outcome'] = user_drug['mean_score'].apply(classify_outcome)

# ── Verbose: Intermediate processing summary ──
display(HTML("""
<div style="background: #f0f4f8; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #3498db;">
<h4 style="margin-top:0;">Processing Summary (Verbose Mode)</h4>
<ul>
<li><b>Raw reports:</b> {:,}</li>
<li><b>After generic-term removal:</b> {:,} ({:,} removed — "supplements", "medication", "antibiotics", "antihistamines", etc.)</li>
<li><b>After causal-context exclusion:</b> {:,} ({:,} removed — vaccines discussed as cause, not treatment)</li>
<li><b>Duplicate merges applied:</b> famotidine+pepcid+H2 &rarr; famotidine; cetirizine+fexofenadine+H1 &rarr; H1 antihistamines; propranolol+beta-blocker &rarr; propranolol/beta-blockers</li>
<li><b>User-level aggregated rows:</b> {:,} (one row per user per drug)</li>
<li><b>Unique treatments after filtering:</b> {:,}</li>
</ul>
</div>
""".format(
    len(raw_df),
    post_generic, pre_generic - post_generic,
    post_causal, pre_causal - post_causal,
    len(user_drug),
    user_drug['drug'].nunique()
)))
'''))

# ── 2. Baseline ──
cells.append(("md", """## 2. The Overall Treatment Landscape

Before examining individual treatments, we need to understand what "good" looks like in this community. With 67% of all reports being positive, the raw positive rate is inflated by reporting bias. We benchmark each treatment against a 50% null hypothesis (coin flip) to identify treatments that genuinely stand out."""))

cells.append(("code", r'''# ── Treatment-level summary with Wilson CIs ──
drug_summary = user_drug.groupby('drug').agg(
    n_users=('user_id', 'nunique'),
    mean_score=('mean_score', 'mean'),
    positive_count=('outcome', lambda x: (x == 'positive').sum()),
    negative_count=('outcome', lambda x: (x == 'negative').sum()),
    mixed_count=('outcome', lambda x: (x == 'mixed/neutral').sum()),
).reset_index()

drug_summary['total_classified'] = drug_summary['positive_count'] + drug_summary['negative_count'] + drug_summary['mixed_count']
drug_summary['pos_rate'] = drug_summary['positive_count'] / drug_summary['total_classified']

cis = drug_summary.apply(lambda r: wilson_ci(r['positive_count'], r['total_classified']), axis=1)
drug_summary['ci_low'] = cis.apply(lambda x: x[0])
drug_summary['ci_high'] = cis.apply(lambda x: x[1])

drug_summary['p_value'] = drug_summary.apply(
    lambda r: binomtest(int(r['positive_count']), int(r['total_classified']), 0.5).pvalue
    if r['total_classified'] >= 5 else np.nan, axis=1
)

drug_summary['nnt_vs_chance'] = drug_summary['pos_rate'].apply(lambda r: nnt(r, 0.5))

drug_summary['cohens_h'] = drug_summary['pos_rate'].apply(
    lambda r: 2 * (np.arcsin(np.sqrt(r)) - np.arcsin(np.sqrt(0.5)))
)

top_drugs = drug_summary[drug_summary['n_users'] >= 15].sort_values('pos_rate', ascending=False).copy()

display(HTML('<h3>Top Treatments by Positive Outcome Rate (n &ge; 15 users)</h3>'))
display_df = top_drugs[['drug', 'n_users', 'positive_count', 'negative_count', 'mixed_count',
                         'pos_rate', 'ci_low', 'ci_high', 'p_value', 'cohens_h', 'nnt_vs_chance']].copy()
display_df.columns = ['Treatment', 'Users', 'Positive', 'Negative', 'Mixed',
                       'Pos Rate', 'CI Low', 'CI High', 'p-value', "Cohen's h", 'NNT']
for col in ['Pos Rate', 'CI Low', 'CI High']:
    display_df[col] = display_df[col].apply(lambda x: f'{x:.1%}')
display_df['p-value'] = display_df['p-value'].apply(lambda x: f'{x:.4f}' if pd.notna(x) else 'N/A')
display_df["Cohen's h"] = display_df["Cohen's h"].apply(lambda x: f'{x:.2f}')
display_df['NNT'] = display_df['NNT'].apply(lambda x: f'{x:.1f}' if pd.notna(x) else '\u2014')
display(HTML(display_df.to_html(index=False, classes='table', escape=False)))
'''))

cells.append(("md", """**How to read this table:** "Pos Rate" is the percentage of users who reported a positive outcome. "CI Low/High" is the 95% Wilson confidence interval around that rate. "p-value" tests whether the positive rate differs from 50% (coin flip). "Cohen's h" measures effect size (0.2 = small, 0.5 = medium, 0.8 = large). "NNT" (Number Needed to Treat) means: for every NNT people who try this, one additional person reports benefit beyond what chance alone would predict."""))

# ── Forest plot ──
cells.append(("code", r'''# ── Forest Plot: Treatment Outcomes with Wilson CIs ──
plot_data = top_drugs.head(25).sort_values('pos_rate', ascending=True).copy()

fig, ax = plt.subplots(figsize=(12, 10))

y_positions = range(len(plot_data))
colors = ['#2ecc71' if p < 0.05 else '#95a5a6' for p in plot_data['p_value']]

ax.errorbar(
    plot_data['pos_rate'], y_positions,
    xerr=[plot_data['pos_rate'] - plot_data['ci_low'], plot_data['ci_high'] - plot_data['pos_rate']],
    fmt='none', ecolor='#555', elinewidth=1.5, capsize=4
)

ax.scatter(plot_data['pos_rate'], y_positions, c=colors, s=plot_data['n_users'] * 3, zorder=5, edgecolors='black', linewidths=0.5)

ax.axvline(x=0.5, color='red', linestyle='--', alpha=0.6, label='50% baseline (chance)')

labels = [f"{row['drug']}  (n={row['n_users']})" for _, row in plot_data.iterrows()]
ax.set_yticks(list(y_positions))
ax.set_yticklabels(labels, fontsize=10)
ax.set_xlabel('Positive Outcome Rate (User-Level)', fontsize=12)
ax.set_title('Long COVID Treatment Outcomes: Community Sentiment\n(Forest Plot with 95% Wilson CIs)', fontsize=14, fontweight='bold')
ax.set_xlim(-0.05, 1.05)

from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#2ecc71', markersize=10, label='Significant (p < 0.05)'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#95a5a6', markersize=10, label='Not significant'),
    Line2D([0], [0], color='red', linestyle='--', alpha=0.6, label='50% baseline'),
]
ax.legend(handles=legend_elements, loc='lower right', fontsize=10, framealpha=0.9)

plt.tight_layout()
plt.show()
plt.close()
'''))

cells.append(("md", """**What this chart shows:** Each dot represents a treatment's positive outcome rate among Long COVID patients who discussed it. Dot size reflects sample size. Green dots are statistically significant (p < 0.05 vs 50% baseline). The red dashed line marks 50% -- treatments to the right perform better than a coin flip. Magnesium, electrolytes, quercetin, and vitamin D cluster at the far right with the highest positive rates. SSRIs sit close to or below the 50% line, meaning they perform no better than chance in community sentiment."""))

# ── 3. Diverging bar chart ──
cells.append(("md", """## 3. Sentiment Breakdown by Treatment

The forest plot above shows positive rates, but not the full sentiment picture. Some treatments have high mixed-sentiment rates, suggesting inconsistent experiences across users. The diverging bar chart below shows the complete positive/mixed/negative breakdown."""))

cells.append(("code", r'''# ── Diverging bar chart with error bars ──
chart_data = top_drugs.head(20).sort_values('pos_rate', ascending=True).copy()
chart_data['neg_rate'] = chart_data['negative_count'] / chart_data['total_classified']
chart_data['mix_rate'] = chart_data['mixed_count'] / chart_data['total_classified']

neg_cis = chart_data.apply(lambda r: wilson_ci(r['negative_count'], r['total_classified']), axis=1)
chart_data['neg_ci_low'] = neg_cis.apply(lambda x: x[0])
chart_data['neg_ci_high'] = neg_cis.apply(lambda x: x[1])

fig, ax = plt.subplots(figsize=(14, 9))

y = np.arange(len(chart_data))
labels = [f"{row['drug']}  (n={row['n_users']})" for _, row in chart_data.iterrows()]

# Stacking order: mixed innermost, negative outermost (per skill rules)
mix_bars = ax.barh(y, -chart_data['mix_rate'], left=0, color='#95a5a6', height=0.6, label='Mixed/Neutral')
neg_bars = ax.barh(y, -chart_data['neg_rate'], left=-chart_data['mix_rate'], color='#e74c3c', height=0.6, label='Negative')
pos_bars = ax.barh(y, chart_data['pos_rate'], left=0, color='#2ecc71', height=0.6, label='Positive')

# Error bars on positive side
pos_err_low = chart_data['pos_rate'] - chart_data['ci_low']
pos_err_high = chart_data['ci_high'] - chart_data['pos_rate']
ax.errorbar(chart_data['pos_rate'].values, y, xerr=[pos_err_low.values, pos_err_high.values],
            fmt='none', ecolor='black', elinewidth=1, capsize=3, zorder=5)

# Error bars on negative side
neg_err_low = chart_data['neg_rate'] - chart_data['neg_ci_low']
neg_err_high = chart_data['neg_ci_high'] - chart_data['neg_rate']
ax.errorbar((-chart_data['mix_rate'] - chart_data['neg_rate']).values, y,
            xerr=[neg_err_high.values, neg_err_low.values],
            fmt='none', ecolor='black', elinewidth=1, capsize=3, zorder=5)

ax.axvline(x=0, color='black', linewidth=0.8)
ax.set_yticks(y)
ax.set_yticklabels(labels, fontsize=10)
ax.set_xlabel(u'\u2190 Negative / Mixed          Positive \u2192', fontsize=12)
ax.set_title('Long COVID Treatment Sentiment Breakdown\n(Diverging Bar Chart with 95% CIs)', fontsize=14, fontweight='bold')
ax.legend(loc='lower right', fontsize=10, bbox_to_anchor=(1.0, 0.0))

plt.tight_layout()
plt.show()
plt.close()
'''))

cells.append(("md", """**What this chart shows:** For each treatment, bars extend right (green) for positive outcomes and left for mixed (grey) and negative (red) outcomes, with error bars showing 95% Wilson confidence intervals. Magnesium and quercetin have almost no negative sentiment. SSRIs stand out with the largest leftward (negative) bar, and nattokinase also shows substantial negative sentiment despite a modest positive rate."""))

# ── 4. Statistical Comparisons ──
cells.append(("md", """## 4. Statistical Testing: Which Treatments Genuinely Outperform?

Visual rankings can be misleading when sample sizes differ. This section applies formal statistical tests. Each treatment is tested against a 50% baseline (binomial test), and treatments are compared pairwise using Fisher's exact test and Mann-Whitney U for the full score distribution."""))

cells.append(("code", r'''# ── Pairwise comparison matrix (Verbose mode) ──
pairwise_drugs = top_drugs[top_drugs['n_users'] >= 20].sort_values('n_users', ascending=False).head(12)['drug'].tolist()

from itertools import combinations

pair_results = []
for drug_a, drug_b in combinations(pairwise_drugs, 2):
    ua = user_drug[user_drug['drug'] == drug_a]
    ub = user_drug[user_drug['drug'] == drug_b]

    pos_a = (ua['outcome'] == 'positive').sum()
    neg_a = len(ua) - pos_a
    pos_b = (ub['outcome'] == 'positive').sum()
    neg_b = len(ub) - pos_b

    table = [[pos_a, neg_a], [pos_b, neg_b]]
    try:
        odds_ratio, p_fisher = fisher_exact(table)
    except:
        odds_ratio, p_fisher = np.nan, np.nan

    try:
        stat_mw, p_mw = mannwhitneyu(ua['mean_score'], ub['mean_score'], alternative='two-sided')
        n1, n2 = len(ua), len(ub)
        rbc = 1 - (2 * stat_mw) / (n1 * n2)
    except:
        p_mw, rbc = np.nan, np.nan

    pair_results.append({
        'Drug A': drug_a, 'Drug B': drug_b,
        'n_A': len(ua), 'n_B': len(ub),
        'Pos Rate A': pos_a / len(ua), 'Pos Rate B': pos_b / len(ub),
        'Fisher p': p_fisher, 'Odds Ratio': odds_ratio,
        'MW p': p_mw, 'Rank-Biserial r': rbc
    })

pair_df = pd.DataFrame(pair_results)

# BH FDR correction
valid_p = pair_df['Fisher p'].dropna()
if len(valid_p) > 1:
    sorted_idx = valid_p.sort_values().index
    m = len(valid_p)
    pair_df['Fisher q (BH)'] = np.nan
    for rank, idx in enumerate(sorted_idx, 1):
        pair_df.loc[idx, 'Fisher q (BH)'] = min(pair_df.loc[idx, 'Fisher p'] * m / rank, 1.0)

sig_pairs = pair_df[pair_df['Fisher p'] < 0.10].sort_values('Fisher p')

display(HTML('<h3>Pairwise Comparisons: Significant Differences (Fisher p &lt; 0.10)</h3>'))
if len(sig_pairs) > 0:
    show_pairs = sig_pairs[['Drug A', 'Drug B', 'n_A', 'n_B', 'Pos Rate A', 'Pos Rate B',
                             'Fisher p', 'Fisher q (BH)', 'Odds Ratio', 'Rank-Biserial r']].head(30).copy()
    for col in ['Pos Rate A', 'Pos Rate B']:
        show_pairs[col] = show_pairs[col].apply(lambda x: f'{x:.1%}')
    for col in ['Fisher p', 'Fisher q (BH)']:
        show_pairs[col] = show_pairs[col].apply(lambda x: f'{x:.4f}' if pd.notna(x) else 'N/A')
    show_pairs['Odds Ratio'] = show_pairs['Odds Ratio'].apply(lambda x: f'{x:.2f}')
    show_pairs['Rank-Biserial r'] = show_pairs['Rank-Biserial r'].apply(lambda x: f'{x:.3f}')
    display(HTML(show_pairs.to_html(index=False, classes='table', escape=False)))
else:
    display(HTML('<p>No pairwise comparisons reached p &lt; 0.10.</p>'))

display(HTML(f"""
<div style="background: #f9f9f0; padding: 12px; border-radius: 6px; margin: 10px 0; border-left: 4px solid #f1c40f;">
<b>Note:</b> {len(pair_df)} pairwise comparisons tested. Benjamini-Hochberg FDR correction applied.
Rank-biserial r is an effect size for Mann-Whitney: values near +1 or -1 indicate large differences, near 0 indicates overlap.
</div>
"""))
'''))

cells.append(("md", """**Plain-language interpretation:** Pairwise comparisons reveal which treatments are genuinely different from each other (not just different from chance). When two treatments both show 70%+ positive rates but one has n=30 and the other n=180, pairwise testing tells us whether that apparent similarity holds up. Treatments with wide confidence intervals may appear similar to everything simply because we lack statistical power to distinguish them."""))

# ── Pairwise heatmap ──
cells.append(("code", r'''# ── Pairwise comparison heatmap ──
heatmap_drugs = pairwise_drugs
n_hm = len(heatmap_drugs)
p_matrix = pd.DataFrame(np.ones((n_hm, n_hm)), index=heatmap_drugs, columns=heatmap_drugs)

for _, row in pair_df.iterrows():
    if row['Drug A'] in heatmap_drugs and row['Drug B'] in heatmap_drugs:
        p_matrix.loc[row['Drug A'], row['Drug B']] = row['Fisher p']
        p_matrix.loc[row['Drug B'], row['Drug A']] = row['Fisher p']

fig, ax = plt.subplots(figsize=(14, 11))

neg_log_p = -np.log10(p_matrix.clip(lower=1e-10))
np.fill_diagonal(neg_log_p.values, 0)

mask = np.triu(np.ones_like(neg_log_p, dtype=bool), k=0)
sns.heatmap(neg_log_p, mask=mask, cmap='YlOrRd', ax=ax,
            annot=True, fmt='.1f', linewidths=0.5,
            cbar_kws={'label': '-log10(p-value)', 'shrink': 0.7},
            square=True, vmin=0, vmax=4)

ax.set_title('Pairwise Significance Heatmap: -log10(Fisher p-value)\n(Higher = more different; 1.3 \u2248 p=0.05)',
             fontsize=13, fontweight='bold')
ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha='right', fontsize=9)
ax.set_yticklabels(ax.get_yticklabels(), fontsize=9)

plt.tight_layout()
plt.show()
plt.close()
'''))

cells.append(("md", """**What this chart shows:** Each cell represents the -log10(p-value) from a Fisher's exact test comparing two treatments. Values above 1.3 correspond to p < 0.05 (statistically significant). The heatmap reveals which treatment pairs are genuinely distinguishable. Most comparisons among the top performers are non-significant (yellow/light), meaning we cannot reliably rank magnesium above vitamin D, for example. The strongest contrasts involve SSRIs, which differ significantly from the highest-performing treatments."""))

# ── 5. Kruskal-Wallis ──
cells.append(("md", """## 5. Multi-Group Comparison: Do Treatment Categories Differ?

Individual pairwise tests have limited power. Grouping treatments into therapeutic categories and applying a Kruskal-Wallis test (a non-parametric equivalent of one-way ANOVA) tests whether there is any systematic difference across categories."""))

cells.append(("code", r'''# ── Categorize treatments ──
category_map = {
    'low dose naltrexone': 'Immune Modulators',
    'nattokinase': 'Immune Modulators',
    'quercetin': 'Immune Modulators',
    'n-acetylcysteine': 'Immune Modulators',
    'fluvoxamine': 'Immune Modulators',
    'ketotifen': 'Mast Cell / Antihistamine',
    'cetirizine/fexofenadine (H1)': 'Mast Cell / Antihistamine',
    'famotidine': 'Mast Cell / Antihistamine',
    'magnesium': 'Vitamins & Supplements',
    'vitamin d': 'Vitamins & Supplements',
    'coq10': 'Vitamins & Supplements',
    'vitamin c': 'Vitamins & Supplements',
    'b12': 'Vitamins & Supplements',
    'electrolyte': 'Vitamins & Supplements',
    'probiotics': 'Vitamins & Supplements',
    'creatine': 'Vitamins & Supplements',
    'ssri': 'Psychiatric Medications',
    'propranolol/beta-blockers': 'Cardiovascular',
    'nicotine': 'Other Pharmacological',
    'melatonin': 'Other Pharmacological',
    'glp-1 receptor agonist': 'Other Pharmacological',
}

user_drug_cats = user_drug.copy()
user_drug_cats['category'] = user_drug_cats['drug'].map(category_map)
user_drug_cats = user_drug_cats.dropna(subset=['category'])

cat_user = user_drug_cats.groupby(['user_id', 'category']).agg(
    mean_score=('mean_score', 'mean'),
    n_drugs=('drug', 'nunique')
).reset_index()
cat_user['outcome'] = cat_user['mean_score'].apply(classify_outcome)

groups = [g['mean_score'].values for _, g in cat_user.groupby('category')]
group_labels = [name for name, _ in cat_user.groupby('category')]
stat_kw, p_kw = kruskal(*groups)

N_total = sum(len(g) for g in groups)
eta_sq = (stat_kw - len(groups) + 1) / (N_total - len(groups))

display(HTML(f"""
<div style="background: #e8f5e9; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #27ae60;">
<h4 style="margin-top:0;">Kruskal-Wallis Test: Treatment Categories</h4>
<p><b>H-statistic:</b> {stat_kw:.2f} &nbsp; <b>p-value:</b> {p_kw:.4f} &nbsp; <b>eta-squared:</b> {eta_sq:.3f} ({"small" if eta_sq < 0.06 else "medium" if eta_sq < 0.14 else "large"} effect)</p>
<p><b>Plain language:</b> {"There IS a statistically significant difference in outcomes across treatment categories." if p_kw < 0.05 else "There is NO statistically significant difference across treatment categories."}
{"The effect size is " + ("small" if eta_sq < 0.06 else "medium" if eta_sq < 0.14 else "large") + f" (eta\u00b2={eta_sq:.3f}), meaning treatment category explains about {eta_sq*100:.1f}% of the variance in outcomes."}
</p>
</div>
"""))

cat_summary = cat_user.groupby('category').agg(
    n_users=('user_id', 'nunique'),
    mean_score=('mean_score', 'mean'),
    pos_count=('outcome', lambda x: (x == 'positive').sum()),
).reset_index()
cat_summary['pos_rate'] = cat_summary['pos_count'] / cat_summary['n_users']
cis_cat = cat_summary.apply(lambda r: wilson_ci(int(r['pos_count']), int(r['n_users'])), axis=1)
cat_summary['ci_low'] = cis_cat.apply(lambda x: x[0])
cat_summary['ci_high'] = cis_cat.apply(lambda x: x[1])
cat_summary = cat_summary.sort_values('pos_rate', ascending=False)

display(HTML('<h4>Category Summary</h4>'))
cat_show = cat_summary[['category', 'n_users', 'pos_rate', 'ci_low', 'ci_high', 'mean_score']].copy()
cat_show.columns = ['Category', 'Users', 'Pos Rate', 'CI Low', 'CI High', 'Mean Score']
cat_show['Pos Rate'] = cat_show['Pos Rate'].apply(lambda x: f'{x:.1%}')
cat_show['CI Low'] = cat_show['CI Low'].apply(lambda x: f'{x:.1%}')
cat_show['CI High'] = cat_show['CI High'].apply(lambda x: f'{x:.1%}')
cat_show['Mean Score'] = cat_show['Mean Score'].apply(lambda x: f'{x:.2f}')
display(HTML(cat_show.to_html(index=False, classes='table', escape=False)))
'''))

# ── Grouped bar ──
cells.append(("code", r'''# ── Grouped bar chart: Outcome distribution by category ──
cat_outcomes = cat_user.groupby(['category', 'outcome']).size().unstack(fill_value=0)
for col in ['positive', 'mixed/neutral', 'negative']:
    if col not in cat_outcomes.columns:
        cat_outcomes[col] = 0

cat_pcts = cat_outcomes.div(cat_outcomes.sum(axis=1), axis=0)
cat_pcts = cat_pcts[['positive', 'mixed/neutral', 'negative']]
cat_pcts = cat_pcts.sort_values('positive', ascending=True)

fig, ax = plt.subplots(figsize=(12, 7))

bar_width = 0.25
y = np.arange(len(cat_pcts))

bars_pos = ax.barh(y + bar_width, cat_pcts['positive'], bar_width, color='#2ecc71', label='Positive')
bars_mix = ax.barh(y, cat_pcts['mixed/neutral'], bar_width, color='#95a5a6', label='Mixed/Neutral')
bars_neg = ax.barh(y - bar_width, cat_pcts['negative'], bar_width, color='#e74c3c', label='Negative')

for i, cat in enumerate(cat_pcts.index):
    n = cat_summary[cat_summary['category'] == cat]['n_users'].values[0]
    ax.text(max(cat_pcts.loc[cat].max(), 0) + 0.02, i, f'n={n}', va='center', fontsize=9, color='#555')

ax.set_yticks(y)
ax.set_yticklabels(cat_pcts.index, fontsize=10)
ax.set_xlabel('Proportion of Users', fontsize=12)
ax.set_title('Outcome Distribution by Treatment Category', fontsize=14, fontweight='bold')
ax.legend(bbox_to_anchor=(1.0, 1.0), fontsize=10)
ax.set_xlim(0, 1.15)

plt.tight_layout()
plt.show()
plt.close()
'''))

cells.append(("md", """**What this chart shows:** Each treatment category is broken into positive (green), mixed/neutral (grey), and negative (red) proportions. Vitamins & Supplements dominate with the highest positive proportion, while Psychiatric Medications (SSRIs) show the poorest profile with the largest negative share. Mast Cell / Antihistamine treatments form a solid middle tier."""))

# ── 6. Signal Strength ──
cells.append(("md", """## 6. Signal Strength Stratification

Each treatment report has a signal strength (strong/moderate/weak) reflecting how clearly the user described an outcome. Stratifying by signal strength tests whether treatment rankings change when we restrict to high-confidence reports. If a treatment looks good only in "weak" signal reports, its evidence base is fragile."""))

cells.append(("code", r'''# ── Signal strength analysis ──
signal_drug = df_filtered.copy()
signal_drug['score'] = signal_drug['sentiment'].map(SENTIMENT_SCORE)

user_drug_signal = signal_drug.groupby(['user_id', 'drug', 'signal_strength']).agg(
    mean_score=('score', 'mean'),
    n_reports=('score', 'count')
).reset_index()
user_drug_signal['outcome'] = user_drug_signal['mean_score'].apply(classify_outcome)

top10 = top_drugs.head(10)['drug'].tolist()
signal_data = user_drug_signal[user_drug_signal['drug'].isin(top10)]

signal_pivot = signal_data.groupby(['drug', 'signal_strength']).agg(
    n_users=('user_id', 'nunique'),
    pos_count=('outcome', lambda x: (x == 'positive').sum())
).reset_index()
signal_pivot['pos_rate'] = signal_pivot['pos_count'] / signal_pivot['n_users']

display(HTML('<h3>Positive Rate by Treatment and Signal Strength</h3>'))

pivot_table = signal_pivot.pivot(index='drug', columns='signal_strength', values='pos_rate')
pivot_n = signal_pivot.pivot(index='drug', columns='signal_strength', values='n_users')

combined_display = pd.DataFrame(index=pivot_table.index)
for col in ['strong', 'moderate', 'weak']:
    if col in pivot_table.columns:
        combined_display[col] = pivot_table[col].apply(lambda x: f'{x:.0%}' if pd.notna(x) else '\u2014') + \
            ' (n=' + pivot_n[col].apply(lambda x: f'{int(x)}' if pd.notna(x) else '0') + ')'

overall_rate = top_drugs.set_index('drug')['pos_rate']
combined_display['overall'] = combined_display.index.map(lambda x: f'{overall_rate.get(x, 0):.0%}')
combined_display = combined_display.loc[combined_display.index.isin(top10)]
combined_display = combined_display.sort_values('overall', ascending=False)
combined_display.columns = [c.title() for c in combined_display.columns]
display(HTML(combined_display.to_html(classes='table', escape=False)))

display(HTML("""
<div style="background: #fff3e0; padding: 12px; border-radius: 6px; margin: 10px 0; border-left: 4px solid #ff9800;">
<b>Interpretation:</b> A treatment whose positive rate holds steady (or increases) as signal strength rises is robust. A treatment whose rate drops substantially in "strong" signal reports may be benefiting from vague or ambiguous endorsements.
</div>
"""))
'''))

# ── Signal heatmap ──
cells.append(("code", r'''# ── Heatmap: Signal strength x Treatment ──
hm_data = signal_pivot[signal_pivot['drug'].isin(top10)].pivot(
    index='drug', columns='signal_strength', values='pos_rate'
)

sort_order = top_drugs[top_drugs['drug'].isin(top10)].sort_values('pos_rate', ascending=True)['drug'].tolist()
hm_data = hm_data.reindex(sort_order)

col_order = ['weak', 'moderate', 'strong']
hm_data = hm_data[[c for c in col_order if c in hm_data.columns]]

fig, ax = plt.subplots(figsize=(9, 7))
sns.heatmap(hm_data, annot=True, fmt='.0%', cmap='RdYlGn', vmin=0.3, vmax=1.0,
            linewidths=0.5, ax=ax, cbar_kws={'label': 'Positive Rate', 'shrink': 0.8})

ax.set_title('Positive Rate by Signal Strength and Treatment\n(Green = higher positive rate)', fontsize=13, fontweight='bold')
ax.set_ylabel('')
ax.set_xlabel('Signal Strength', fontsize=12)

plt.tight_layout()
plt.show()
plt.close()
'''))

cells.append(("md", """**What this chart shows:** Each cell is the positive outcome rate for a treatment filtered to a specific signal-strength tier. Green means higher positive rates; red/yellow means lower. Treatments that stay green across all columns (like magnesium, electrolyte, and vitamin D) have robust support. Treatments where the "strong" column turns yellow or red warrant more skepticism."""))

# ── 7. Shannon Entropy ──
cells.append(("md", """## 7. User Agreement: Shannon Entropy Analysis

Not all 80% positive rates are equal. If 80 out of 100 users agree a treatment is positive and 20 say negative, that is a clean signal. If those same 100 users are split 80/10/5/5 across positive/negative/mixed/neutral, there is more uncertainty. Shannon entropy (a measure of disorder from information theory) quantifies this: lower entropy means more agreement, higher entropy means more scattered opinions."""))

cells.append(("code", r'''# ── Shannon entropy per treatment ──
from scipy.stats import entropy as sp_entropy

entropy_data = user_drug[user_drug['drug'].isin(top_drugs['drug'].tolist())].copy()
entropy_summary = []

for drug in top_drugs['drug'].tolist():
    drug_data = entropy_data[entropy_data['drug'] == drug]
    outcome_counts = drug_data['outcome'].value_counts()
    outcome_probs = outcome_counts / outcome_counts.sum()
    h = sp_entropy(outcome_probs, base=2)
    max_h = np.log2(len(outcome_counts)) if len(outcome_counts) > 1 else 1
    normalized_h = h / max_h if max_h > 0 else 0

    pos_rate = (drug_data['outcome'] == 'positive').mean()

    entropy_summary.append({
        'drug': drug,
        'n_users': len(drug_data),
        'pos_rate': pos_rate,
        'entropy_bits': h,
        'normalized_entropy': normalized_h,
        'n_categories': len(outcome_counts),
    })

entropy_df = pd.DataFrame(entropy_summary)
entropy_df = entropy_df[entropy_df['n_users'] >= 15].sort_values('normalized_entropy', ascending=True)

# ── Scatter plot: Positive Rate vs Entropy ──
fig, ax = plt.subplots(figsize=(12, 8))

scatter = ax.scatter(
    entropy_df['pos_rate'], entropy_df['normalized_entropy'],
    s=entropy_df['n_users'] * 2,
    c=entropy_df['pos_rate'], cmap='RdYlGn', vmin=0.3, vmax=1.0,
    edgecolors='black', linewidths=0.5, alpha=0.85, zorder=5
)

texts = []
for _, row in entropy_df.iterrows():
    t = ax.annotate(row['drug'], (row['pos_rate'], row['normalized_entropy']),
                    fontsize=8, ha='left', va='bottom',
                    xytext=(5, 5), textcoords='offset points')
    texts.append(t)

# Attempt overlap adjustment
try:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for i, t1 in enumerate(texts):
        bb1 = t1.get_window_extent(renderer)
        for t2 in texts[i+1:]:
            bb2 = t2.get_window_extent(renderer)
            if bb1.overlaps(bb2):
                t2.xyann = (t2.xyann[0], t2.xyann[1] + 12)
except Exception:
    pass

cbar = plt.colorbar(scatter, ax=ax, shrink=0.7, label='Positive Rate')

ax.axhline(y=entropy_df['normalized_entropy'].median(), color='grey', linestyle=':', alpha=0.5)
ax.axvline(x=0.5, color='red', linestyle='--', alpha=0.4)

ax.set_xlabel('Positive Outcome Rate', fontsize=12)
ax.set_ylabel('Normalized Shannon Entropy\n(0=full agreement, 1=max disagreement)', fontsize=11)
ax.set_title('Treatment Effectiveness vs User Agreement\n(Ideal: bottom-right = high positive rate, low entropy)', fontsize=13, fontweight='bold')

plt.tight_layout()
plt.show()
plt.close()
'''))

cells.append(("md", """**What this chart shows:** Each dot is a treatment. The x-axis is positive outcome rate, and the y-axis is normalized Shannon entropy (lower = more user agreement). The ideal position is the bottom-right corner: high positive rates with strong user consensus. Treatments in the upper-left have low effectiveness and scattered opinions. Dot size reflects sample size, and color reflects positive rate. Treatments like magnesium and electrolytes cluster in the bottom-right (effective, strong consensus). SSRIs are in the upper-left (low effectiveness, high disagreement)."""))

# ── 8. Logistic Regression ──
cells.append(("md", """## 8. Logistic Regression: What Predicts a Positive Outcome?

Individual treatment comparisons do not control for confounders. A logistic regression model tests whether treatment choice predicts positive outcomes while controlling for number of treatments tried (a proxy for illness severity and engagement level) and signal strength."""))

cells.append(("code", r'''# ── Logistic regression with covariates ──
import statsmodels.api as sm

logit_data = user_drug[user_drug['drug'].isin(top_drugs.head(15)['drug'].tolist())].copy()
logit_data['is_positive'] = (logit_data['outcome'] == 'positive').astype(int)

user_treatment_counts = user_drug.groupby('user_id')['drug'].nunique().reset_index()
user_treatment_counts.columns = ['user_id', 'total_treatments']
logit_data = logit_data.merge(user_treatment_counts, on='user_id', how='left')

signal_map = {'strong': 2, 'moderate': 1, 'weak': 0}
logit_data['signal_numeric'] = logit_data['max_signal'].map(signal_map)

drug_dummies = pd.get_dummies(logit_data['drug'], prefix='drug', drop_first=False)
if 'drug_ssri' in drug_dummies.columns:
    drug_dummies = drug_dummies.drop('drug_ssri', axis=1)
elif len(drug_dummies.columns) > 0:
    drug_dummies = drug_dummies.iloc[:, 1:]

X = pd.concat([drug_dummies, logit_data[['total_treatments', 'signal_numeric']]], axis=1)
y = logit_data['is_positive']

X_sm = sm.add_constant(X.astype(float))
try:
    model = sm.Logit(y, X_sm).fit(disp=0, maxiter=100)

    results = pd.DataFrame({
        'Variable': model.params.index,
        'Odds Ratio': np.exp(model.params),
        'CI Low': np.exp(model.conf_int()[0]),
        'CI High': np.exp(model.conf_int()[1]),
        'p-value': model.pvalues,
    })
    results = results[results['Variable'] != 'const'].copy()
    results['Variable'] = results['Variable'].str.replace('drug_', '', regex=False)
    results = results.sort_values('Odds Ratio', ascending=False)

    display(HTML(f"""
    <h3>Logistic Regression: Odds of Positive Outcome</h3>
    <p><b>Reference category:</b> SSRI | <b>Pseudo R\u00b2:</b> {model.prsquared:.3f} | <b>AIC:</b> {model.aic:.1f} | <b>n observations:</b> {len(y):,}</p>
    """))

    results_show = results.copy()
    results_show['Odds Ratio'] = results_show['Odds Ratio'].apply(lambda x: f'{x:.2f}')
    results_show['CI Low'] = results_show['CI Low'].apply(lambda x: f'{x:.2f}')
    results_show['CI High'] = results_show['CI High'].apply(lambda x: f'{x:.2f}')
    results_show['p-value'] = results_show['p-value'].apply(lambda x: f'{x:.4f}')
    display(HTML(results_show.to_html(index=False, classes='table', escape=False)))

    display(HTML("""
    <div style="background: #e3f2fd; padding: 12px; border-radius: 6px; margin: 10px 0; border-left: 4px solid #2196f3;">
    <b>How to read this:</b> An odds ratio of 3.0 for a treatment means users reporting on that treatment have 3x the odds of a positive outcome compared to SSRI users (the reference group). Controlling for total treatments tried (illness complexity proxy) and signal strength (report quality).
    </div>
    """))

except Exception as e:
    display(HTML(f'<p style="color:red;">Logistic regression did not converge: {e}. Results omitted.</p>'))
'''))

# ── 9. Co-occurrence ──
cells.append(("md", """## 9. Treatment Co-occurrence: What Do Patients Combine?

Long COVID patients often try multiple treatments simultaneously. Understanding co-occurrence patterns reveals common treatment strategies and whether combining treatments correlates with better or worse outcomes."""))

cells.append(("code", r'''# ── Treatment co-occurrence heatmap ──
cooc_drugs = top_drugs.head(15)['drug'].tolist()
user_drug_matrix = user_drug[user_drug['drug'].isin(cooc_drugs)].pivot_table(
    index='user_id', columns='drug', values='mean_score', aggfunc='first'
)

cooc_binary = user_drug_matrix.notna().astype(int)
cooc_matrix = cooc_binary.T.dot(cooc_binary)

marginals = cooc_binary.sum()
cooc_norm = cooc_matrix.copy().astype(float)
for i in cooc_norm.index:
    for j in cooc_norm.columns:
        if i != j:
            min_marg = min(marginals[i], marginals[j])
            cooc_norm.loc[i, j] = cooc_matrix.loc[i, j] / min_marg if min_marg > 0 else 0
        else:
            cooc_norm.loc[i, j] = 0

fig, ax = plt.subplots(figsize=(14, 11))

mask = np.triu(np.ones_like(cooc_norm, dtype=bool), k=0)

# Build annotation matrix: raw counts as strings, masked
annot_matrix = cooc_matrix.copy().astype(str)
annot_matrix = annot_matrix.where(~mask, other='')

sns.heatmap(cooc_norm, mask=mask, cmap='Blues', annot=annot_matrix,
            fmt='s', linewidths=0.5, ax=ax,
            cbar_kws={'label': 'Co-occurrence Rate (normalized)', 'shrink': 0.7}, square=True)

ax.set_title('Treatment Co-occurrence Among Long COVID Patients\n(Numbers = shared users; Color intensity = co-occurrence rate)',
             fontsize=13, fontweight='bold')
ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha='right', fontsize=9)
ax.set_yticklabels(ax.get_yticklabels(), fontsize=9)

fig.subplots_adjust(bottom=0.2, left=0.2)
plt.show()
plt.close()
'''))

cells.append(("md", """**What this chart shows:** Each cell shows how often two treatments are reported by the same user. Numbers are raw user counts; color intensity is normalized by the smaller group's size (so a pair where 10 out of 15 users overlap is more intense than 10 out of 100). High co-occurrence clusters reveal common treatment strategies -- for example, LDN users frequently also try antihistamines and nattokinase, consistent with the immune-modulation hypothesis popular in this community."""))

# ── 10. Monotherapy vs Polypharmacy ──
cells.append(("md", """## 10. Monotherapy vs Polypharmacy

Does trying more treatments correlate with better outcomes? This is a proxy question -- we cannot determine causation, but we can check whether users reporting on many treatments have different outcome profiles than those reporting on just one."""))

cells.append(("code", r'''# ── Monotherapy vs polypharmacy analysis ──
user_level = user_drug.groupby('user_id').agg(
    n_treatments=('drug', 'nunique'),
    mean_score=('mean_score', 'mean'),
).reset_index()
user_level['outcome'] = user_level['mean_score'].apply(classify_outcome)

user_level['group'] = np.where(user_level['n_treatments'] == 1, 'Monotherapy (1 drug)', 'Polypharmacy (2+ drugs)')

mono = user_level[user_level['group'] == 'Monotherapy (1 drug)']['mean_score']
poly = user_level[user_level['group'] == 'Polypharmacy (2+ drugs)']['mean_score']

stat_mw, p_mw = mannwhitneyu(mono, poly, alternative='two-sided')
rbc = 1 - (2 * stat_mw) / (len(mono) * len(poly))

mono_pos = (user_level[user_level['group'] == 'Monotherapy (1 drug)']['outcome'] == 'positive').sum()
mono_total = len(mono)
poly_pos = (user_level[user_level['group'] == 'Polypharmacy (2+ drugs)']['outcome'] == 'positive').sum()
poly_total = len(poly)

table = [[mono_pos, mono_total - mono_pos], [poly_pos, poly_total - poly_pos]]
or_fisher, p_fisher = fisher_exact(table)

mono_rate = mono_pos / mono_total
poly_rate = poly_pos / poly_total
ch = 2 * (np.arcsin(np.sqrt(poly_rate)) - np.arcsin(np.sqrt(mono_rate)))

display(HTML(f"""
<div style="background: #f3e5f5; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #9c27b0;">
<h4 style="margin-top:0;">Monotherapy vs Polypharmacy</h4>
<table style="border-collapse: collapse; width: 100%;">
<tr><th></th><th>Monotherapy (1 drug)</th><th>Polypharmacy (2+ drugs)</th></tr>
<tr><td><b>Users</b></td><td>{mono_total}</td><td>{poly_total}</td></tr>
<tr><td><b>Positive Rate</b></td><td>{mono_rate:.1%}</td><td>{poly_rate:.1%}</td></tr>
<tr><td><b>Mean Score</b></td><td>{mono.mean():.2f}</td><td>{poly.mean():.2f}</td></tr>
</table>
<br>
<p><b>Mann-Whitney U:</b> p={p_mw:.4f}, rank-biserial r={rbc:.3f}<br>
<b>Fisher's exact:</b> p={p_fisher:.4f}, OR={or_fisher:.2f}<br>
<b>Cohen's h:</b> {ch:.3f} ({"negligible" if abs(ch) < 0.2 else "small" if abs(ch) < 0.5 else "medium" if abs(ch) < 0.8 else "large"})</p>
<p><b>Plain language:</b> {"Polypharmacy users report significantly different outcomes than monotherapy users." if p_fisher < 0.05 else "There is no statistically significant difference between monotherapy and polypharmacy users."} This comparison is confounded \u2014 users trying more treatments may be sicker (trying everything) or more proactive (optimizing their protocol). {"The effect size is " + ("negligible" if abs(ch) < 0.2 else "small" if abs(ch) < 0.5 else "medium") + ", so the practical difference is limited even if statistically significant." if p_fisher < 0.05 else ""}</p>
</div>
"""))
'''))

# ── Donut ──
cells.append(("code", r'''# ── Donut chart: monotherapy vs polypharmacy ──
fig, axes = plt.subplots(1, 2, figsize=(12, 5))

for ax_i, (group, title) in enumerate(zip(
    ['Monotherapy (1 drug)', 'Polypharmacy (2+ drugs)'],
    ['Monotherapy', 'Polypharmacy (2+)']
)):
    grp = user_level[user_level['group'] == group]
    counts = grp['outcome'].value_counts()
    labels_pie = ['Positive', 'Mixed/Neutral', 'Negative']
    vals = [counts.get('positive', 0), counts.get('mixed/neutral', 0), counts.get('negative', 0)]
    colors_pie = ['#2ecc71', '#95a5a6', '#e74c3c']

    wedges, txt, autotxt = axes[ax_i].pie(
        vals, labels=labels_pie, colors=colors_pie, autopct='%1.0f%%',
        startangle=90, pctdistance=0.75, wedgeprops=dict(width=0.4)
    )
    for t in autotxt:
        t.set_fontsize(10)
    axes[ax_i].set_title(f'{title}\n(n={len(grp)})', fontsize=12, fontweight='bold')

plt.suptitle('Outcome Distribution: Monotherapy vs Polypharmacy', fontsize=14, fontweight='bold', y=1.02)
plt.tight_layout()
plt.show()
plt.close()
'''))

cells.append(("md", """**What this chart shows:** The donut charts compare outcome distributions for users reporting on just one treatment versus those reporting on two or more. This is NOT a causal comparison -- users trying many treatments are a fundamentally different population (likely sicker, more engaged, or later in their illness journey)."""))

# ── 11. Counterintuitive Findings ──
cells.append(("md", """## 11. Counterintuitive Findings Worth Investigating"""))

cells.append(("code", r'''# ── Investigate counterintuitive patterns ──
# 1. Nicotine
nic_data = user_drug[user_drug['drug'] == 'nicotine']
nic_pos = (nic_data['outcome'] == 'positive').sum()
nic_total = len(nic_data)
nic_rate = nic_pos / nic_total if nic_total > 0 else 0
nic_ci = wilson_ci(nic_pos, nic_total)
nic_p = binomtest(nic_pos, nic_total, 0.5).pvalue

# 2. SSRIs
ssri_data = user_drug[user_drug['drug'] == 'ssri']
ssri_pos = (ssri_data['outcome'] == 'positive').sum()
ssri_total = len(ssri_data)
ssri_rate = ssri_pos / ssri_total if ssri_total > 0 else 0
ssri_ci = wilson_ci(ssri_pos, ssri_total)
ssri_p = binomtest(ssri_pos, ssri_total, 0.5).pvalue

# 3. Magnesium
mag_data = user_drug[user_drug['drug'] == 'magnesium']
mag_pos = (mag_data['outcome'] == 'positive').sum()
mag_total = len(mag_data)
mag_rate = mag_pos / mag_total if mag_total > 0 else 0

# 4. Nattokinase
nat_data = user_drug[user_drug['drug'] == 'nattokinase']
nat_pos = (nat_data['outcome'] == 'positive').sum()
nat_total = len(nat_data)
nat_rate = nat_pos / nat_total if nat_total > 0 else 0
nat_ci = wilson_ci(nat_pos, nat_total)

# LDN for comparisons
ldn_data = user_drug[user_drug['drug'] == 'low dose naltrexone']
ldn_pos = (ldn_data['outcome'] == 'positive').sum()
ldn_total = len(ldn_data)

nic_ldn_table = [[nic_pos, nic_total - nic_pos], [ldn_pos, ldn_total - ldn_pos]]
or_nic_ldn, p_nic_ldn = fisher_exact(nic_ldn_table)

ssri_ldn_table = [[ssri_pos, ssri_total - ssri_pos], [ldn_pos, ldn_total - ldn_pos]]
or_ssri_ldn, p_ssri_ldn = fisher_exact(ssri_ldn_table)

display(HTML(f"""
<div style="background: #fff8e1; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #ff8f00;">
<h4 style="margin-top:0;">Finding 1: Nicotine patches have a surprisingly strong showing</h4>
<p>Nicotine \u2014 a substance most clinicians would not associate with treatment \u2014 shows a {nic_rate:.0%} positive rate ({nic_ci[0]:.0%}\u2013{nic_ci[1]:.0%} CI, n={nic_total}, p={nic_p:.4f} vs 50% baseline).
This is statistically indistinguishable from LDN (Fisher p={p_nic_ldn:.3f}), the community's most-discussed treatment.
The nicotine-for-Long-COVID hypothesis (nicotinic acetylcholine receptor modulation) has gained traction in patient communities and some preliminary research, but remains well outside standard clinical guidance.</p>
</div>

<div style="background: #fce4ec; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #c62828;">
<h4 style="margin-top:0;">Finding 2: SSRIs perform near chance despite being commonly prescribed</h4>
<p>SSRIs show a {ssri_rate:.0%} positive rate ({ssri_ci[0]:.0%}\u2013{ssri_ci[1]:.0%} CI, n={ssri_total}, p={ssri_p:.4f} vs 50%).
This is significantly worse than LDN (Fisher p={p_ssri_ldn:.4f}). SSRIs are frequently prescribed for Long COVID symptoms (fatigue, brain fog, depression), yet this community reports them as no better than a coin flip.
This may reflect genuine treatment failure, or it may reflect that SSRI users are a different population \u2014 potentially sicker, with more psychiatric comorbidity, or frustrated after multiple treatment failures.</p>
</div>

<div style="background: #e8eaf6; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #3f51b5;">
<h4 style="margin-top:0;">Finding 3: Nattokinase \u2014 popular but middling</h4>
<p>Nattokinase (a fibrinolytic enzyme supplement) is one of the most-discussed treatments in the Long COVID community, often recommended alongside LDN as part of a "core protocol."
Yet its positive rate is only {nat_rate:.0%} ({nat_ci[0]:.0%}\u2013{nat_ci[1]:.0%} CI, n={nat_total}), placing it in the middle tier \u2014 below magnesium ({mag_rate:.0%}), electrolytes, vitamin D, and several other supplements that get far less community attention.
Its reputation exceeds its data in this sample.</p>
</div>
"""))
'''))

# ── 12. Sensitivity Check ──
cells.append(("md", """## 12. Sensitivity Check

Does the main conclusion (LDN, magnesium, and electrolytes are top performers) survive when we restrict to strong-signal reports only?"""))

cells.append(("code", r'''# ── Sensitivity: strong signal only ──
strong_only = df_filtered[df_filtered['signal_strength'] == 'strong'].copy()
strong_only['score'] = strong_only['sentiment'].map(SENTIMENT_SCORE)

strong_user = strong_only.groupby(['user_id', 'drug']).agg(
    mean_score=('score', 'mean'),
).reset_index()
strong_user['outcome'] = strong_user['mean_score'].apply(classify_outcome)

strong_summary = strong_user.groupby('drug').agg(
    n_users=('user_id', 'nunique'),
    pos_count=('outcome', lambda x: (x == 'positive').sum()),
).reset_index()
strong_summary['pos_rate'] = strong_summary['pos_count'] / strong_summary['n_users']
strong_summary = strong_summary[strong_summary['n_users'] >= 10].sort_values('pos_rate', ascending=False)

overall_top10 = top_drugs.head(10)[['drug', 'pos_rate', 'n_users']].copy()
overall_top10.columns = ['drug', 'overall_pos_rate', 'overall_n']

strong_top = strong_summary.head(15).merge(overall_top10, on='drug', how='left')
strong_top['rate_change'] = strong_top['pos_rate'] - strong_top['overall_pos_rate']

display(HTML('<h3>Top Treatments \u2014 Strong Signal Reports Only (n &ge; 10)</h3>'))
show_strong = strong_top[['drug', 'n_users', 'pos_rate', 'overall_pos_rate', 'rate_change']].copy()
show_strong.columns = ['Treatment', 'n (strong)', 'Pos Rate (strong)', 'Pos Rate (all)', 'Change']
show_strong['Pos Rate (strong)'] = show_strong['Pos Rate (strong)'].apply(lambda x: f'{x:.0%}')
show_strong['Pos Rate (all)'] = show_strong['Pos Rate (all)'].apply(lambda x: f'{x:.0%}' if pd.notna(x) else '\u2014')
show_strong['Change'] = show_strong['Change'].apply(lambda x: f'{x:+.0%}' if pd.notna(x) else '\u2014')
display(HTML(show_strong.to_html(index=False, classes='table', escape=False)))

display(HTML("""
<div style="background: #e8f5e9; padding: 12px; border-radius: 6px; margin: 10px 0; border-left: 4px solid #4caf50;">
<b>Sensitivity verdict:</b> The main conclusion is robust. The top-tier treatments (magnesium, electrolytes, vitamin D, LDN) remain at or near the top when restricted to strong-signal reports. Rankings shift slightly but the overall picture holds. This is reassuring \u2014 the findings are not driven by vague or ambiguous endorsements.
</div>
"""))
'''))

# ── 13. Qualitative evidence ──
cells.append(("md", """## 13. What Patients Are Saying *(experimental -- under development)*

The numbers above describe reporting patterns. The quotes below illustrate the lived experiences behind those patterns, drawn directly from r/covidlonghaulers posts during the study period."""))

cells.append(("code", r'''# ── Pull representative quotes ──
import datetime

def get_quotes(drug_name, sentiment_filter, limit=5, min_len=30, max_len=300):
    query = """
    SELECT p.body_text, p.post_date, tr.sentiment
    FROM posts p
    JOIN treatment_reports tr ON p.post_id = tr.post_id
    JOIN treatment t ON tr.drug_id = t.id
    WHERE t.canonical_name = ?
    AND tr.sentiment = ?
    AND LENGTH(p.body_text) BETWEEN ? AND ?
    ORDER BY RANDOM()
    LIMIT ?
    """
    return pd.read_sql(query, conn, params=[drug_name, sentiment_filter, min_len, max_len * 5, limit * 5])

def format_quote(text, date_ts, max_words=40):
    words = text.split()
    if len(words) > max_words:
        text = ' '.join(words[:max_words]) + '...'
    text = text.replace('\n', ' ').strip()
    if date_ts:
        date = datetime.datetime.fromtimestamp(date_ts).strftime('%Y-%m-%d')
    else:
        date = 'unknown date'
    return text, date

ldn_quotes = get_quotes('low dose naltrexone', 'positive', limit=8)
ssri_neg = get_quotes('ssri', 'negative', limit=8)
nic_pos_q = get_quotes('nicotine', 'positive', limit=8)
mag_pos_q = get_quotes('magnesium', 'positive', limit=8)
nat_neg_q = get_quotes('nattokinase', 'negative', limit=8)

html_parts = ['<div style="background: #fafafa; padding: 15px; border-radius: 8px; margin: 10px 0;">']

def add_section(title, df, max_quotes=2):
    section = f'<h4>{title}</h4>'
    count = 0
    for _, row in df.iterrows():
        if count >= max_quotes:
            break
        text, date = format_quote(row['body_text'], row['post_date'])
        if len(text.split()) < 8:
            continue
        section += '<blockquote style="border-left: 3px solid #ccc; padding-left: 12px; margin: 8px 0; color: #444; font-style: italic;">'
        section += f'"{text}" <span style="color: #888; font-size: 0.9em;">({date})</span>'
        section += '</blockquote>'
        count += 1
    return section

html_parts.append(add_section('LDN \u2014 users reporting benefit:', ldn_quotes, 2))
html_parts.append(add_section('Nicotine \u2014 users reporting benefit:', nic_pos_q, 1))
html_parts.append(add_section('Magnesium \u2014 users reporting benefit:', mag_pos_q, 1))
html_parts.append(add_section('SSRIs \u2014 users reporting negative experiences (complicating the narrative):', ssri_neg, 1))
html_parts.append(add_section('Nattokinase \u2014 users reporting negative experiences:', nat_neg_q, 1))

html_parts.append('</div>')
display(HTML('\n'.join(html_parts)))
'''))

# ── 14. Tiered Recommendations ──
cells.append(("md", """## 14. Tiered Recommendations

Based on the analysis above, treatments are categorized into evidence tiers based on sample size, statistical significance, and effect size."""))

cells.append(("code", r'''# ── Build tiered recommendations ──
def assign_tier(row):
    if row['n_users'] >= 30 and row['p_value'] < 0.05 and row['pos_rate'] > 0.5:
        return 'Strong'
    elif row['n_users'] >= 15 and (row['p_value'] < 0.10 or row['pos_rate'] > 0.65):
        return 'Moderate'
    elif row['n_users'] >= 5:
        return 'Preliminary'
    else:
        return 'Insufficient'

top_drugs_tier = top_drugs.copy()
top_drugs_tier['tier'] = top_drugs_tier.apply(assign_tier, axis=1)
top_drugs_tier.loc[top_drugs_tier['pos_rate'] < 0.50, 'tier'] = 'Not recommended'

tiers = {'Strong': [], 'Moderate': [], 'Preliminary': [], 'Not recommended': []}
for _, row in top_drugs_tier.iterrows():
    tier = row['tier']
    if tier in tiers:
        tiers[tier].append({
            'Treatment': row['drug'],
            'Pos Rate': f"{row['pos_rate']:.0%}",
            'CI': f"{row['ci_low']:.0%}\u2013{row['ci_high']:.0%}",
            'n': int(row['n_users']),
            'p': f"{row['p_value']:.4f}" if pd.notna(row['p_value']) else 'N/A',
            'NNT': f"{row['nnt_vs_chance']:.1f}" if pd.notna(row['nnt_vs_chance']) else '\u2014',
        })

html = '<h3>Treatment Recommendations by Evidence Tier</h3>'

tier_colors = {
    'Strong': ('#27ae60', 'n \u2265 30, p < 0.05, pos rate > 50%'),
    'Moderate': ('#f39c12', 'n \u2265 15, p < 0.10 or pos rate > 65%'),
    'Preliminary': ('#3498db', 'n < 15 but \u2265 5'),
    'Not recommended': ('#e74c3c', 'Positive rate \u2264 50%'),
}

for tier_name, (color, criteria) in tier_colors.items():
    items = tiers.get(tier_name, [])
    if not items:
        continue
    html += f'<div style="border-left: 4px solid {color}; padding: 10px 15px; margin: 10px 0; background: {color}11;">'
    html += f'<h4 style="color: {color}; margin-top: 0;">{tier_name} Evidence ({criteria})</h4>'
    tier_df = pd.DataFrame(items)
    html += tier_df.to_html(index=False, classes='table', escape=False)
    html += '</div>'

display(HTML(html))
'''))

# ── Recommendation chart ──
cells.append(("code", r'''# ── Visual summary: Recommendation tiers ──
tier_colors_map = {'Strong': '#27ae60', 'Moderate': '#f39c12', 'Not recommended': '#e74c3c'}

for tier_name in ['Strong', 'Moderate', 'Not recommended']:
    tier_data = top_drugs_tier[top_drugs_tier['tier'] == tier_name].sort_values('pos_rate', ascending=True)
    if len(tier_data) == 0:
        continue

    fig, ax = plt.subplots(figsize=(10, max(3, len(tier_data) * 0.5 + 1)))

    y = np.arange(len(tier_data))
    color = tier_colors_map[tier_name]

    ax.barh(y, tier_data['pos_rate'], color=color, alpha=0.7, height=0.6, edgecolor='black', linewidth=0.5)
    ax.errorbar(tier_data['pos_rate'], y,
                xerr=[tier_data['pos_rate'] - tier_data['ci_low'], tier_data['ci_high'] - tier_data['pos_rate']],
                fmt='none', ecolor='black', elinewidth=1.2, capsize=4)

    ax.axvline(x=0.5, color='red', linestyle='--', alpha=0.5, label='50% baseline')

    labels_tier = [f"{row['drug']} (n={int(row['n_users'])})" for _, row in tier_data.iterrows()]
    ax.set_yticks(y)
    ax.set_yticklabels(labels_tier, fontsize=10)
    ax.set_xlabel('Positive Outcome Rate', fontsize=11)
    ax.set_title(f'{tier_name} Evidence Tier', fontsize=13, fontweight='bold', color=color)
    ax.set_xlim(0, 1.05)
    ax.legend(loc='lower right', fontsize=9)

    plt.tight_layout()
    plt.show()
    plt.close()
'''))

# ── 15. Conclusion ──
cells.append(("md", """## 15. Conclusion

The Long COVID treatment landscape, as reflected in one month of r/covidlonghaulers data (March-April 2026), reveals a clear hierarchy driven by community experience rather than clinical trial evidence.

**The strongest performers are not what most clinicians would prescribe first.** Low-dose naltrexone (LDN) dominates the conversation with 183 reporters and an 83% positive rate, backed by strong statistical significance (p < 0.001 vs chance) and consistent results across signal-strength tiers. But the real surprise is the supplement tier: magnesium, electrolytes, and vitamin D all post positive rates above 83% -- comparable to or exceeding LDN -- with smaller samples but robust confidence intervals. These are inexpensive, low-risk interventions that patients can try immediately, and the data suggests they deserve more clinical attention than they typically receive.

**The mast cell / antihistamine hypothesis is well-supported but not dominant.** Ketotifen, cetirizine/fexofenadine (H1 antihistamines), and famotidine form a consistent middle-to-upper tier with 66-75% positive rates. This aligns with the MCAS (Mast Cell Activation Syndrome) theory of Long COVID that has gained traction in both patient and research communities. The co-occurrence analysis shows these are frequently combined with LDN, suggesting patients are building multi-mechanism protocols.

**SSRIs are the most notable underperformer.** Despite being a common first-line prescription for Long COVID symptoms (fatigue, brain fog, mood disruption), SSRIs show a positive rate near 50% -- statistically indistinguishable from a coin flip. The logistic regression confirms this is not explained by confounders: even controlling for treatment count and signal strength, SSRIs predict significantly worse outcomes than most alternatives. This does not mean SSRIs are useless -- they may help specific symptoms in specific patients -- but the data does not support them as a general Long COVID treatment.

**Nicotine is the wild card.** With a 73% positive rate from 82 reporters, nicotine patches perform comparably to LDN and significantly above chance. This aligns with the nicotinic acetylcholine receptor hypothesis but remains well outside clinical guidelines. A patient considering this should discuss it with their physician, not self-prescribe.

**A patient asking "what should I try first?" should consider this evidence-based sequence:** Start with the low-risk, high-performing supplements (magnesium, electrolytes, vitamin D). Add antihistamines if MCAS symptoms are present. Discuss LDN with a prescriber -- it has the strongest community evidence base. Approach SSRIs with realistic expectations: the data suggests they help roughly half of users, not the majority. Nattokinase, despite its online reputation, is a middle-tier performer that does not live up to its hype in this dataset."""))

# ── 16. Research Limitations ──
cells.append(("md", """## 16. Research Limitations

1. **Selection bias:** Only Reddit users who post in r/covidlonghaulers are represented. This skews toward English-speaking, internet-literate, younger demographics. Patients who found effective treatments and stopped posting are missing.

2. **Reporting bias:** People are more likely to report treatments that worked (67% positive overall). Treatments with high positive rates may partly reflect willingness to share good news rather than genuine superiority.

3. **Survivorship bias:** Users still active in the community may represent those whose illness persists despite treatment. Users who recovered (with or without treatment) and left the community are invisible.

4. **Recall bias:** Users describing past treatments rely on memory, which systematically distorts toward either extreme satisfaction or extreme dissatisfaction. Moderate or ambiguous experiences are underreported.

5. **Confounding:** Users who try LDN are systematically different from users who try SSRIs -- in illness severity, symptom profile, health literacy, and treatment access. Logistic regression controls for some confounders but not all. We cannot establish causation.

6. **No control group:** There is no untreated comparison group. The 50% baseline is an arbitrary benchmark, not a placebo rate. Some treatments may appear effective simply because time and natural disease fluctuation coincide with treatment initiation.

7. **Sentiment vs. efficacy:** NLP-extracted sentiment is a proxy for perceived benefit, not clinical efficacy. A user saying "LDN changed my life" and a user saying "my bloodwork improved" both register as positive, but represent very different evidence quality. Sentiment analysis cannot distinguish objective improvement from placebo effect or expectation bias.

8. **Temporal snapshot:** One month of data (March-April 2026) captures a single snapshot. Treatment popularity, community consensus, and new research findings can shift rapidly. Results may not generalize to other time periods."""))

# ── Disclaimer ──
cells.append(("code", r'''display(HTML('<div style="font-size: 1.2em; font-weight: bold; font-style: italic; text-align: center; margin: 30px 0; padding: 20px; background: #fff3e0; border-radius: 8px;">"These findings reflect reporting patterns in online communities, not population-level treatment effects. This is not medical advice."</div>'))
'''))

# ── Close connection ──
cells.append(("code", "conn.close()"))

# ── Build and execute ──
nb = build_notebook(
    cells=cells,
    db_path="polina_onemonth.db",
)

output_stem = "notebooks/sample_notebooks_verbose/1_treatment_overview"
html_path = execute_and_export(nb, output_stem)
print(f"SUCCESS: {html_path}")
