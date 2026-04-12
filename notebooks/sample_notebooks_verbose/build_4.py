"""Build notebook 4: Fatigue treatments in Long COVID (Verbose mode)."""
import sys
sys.path.insert(0, r"C:\Users\scgee\OneDrive\Documents\Projects\PatientPunk\notebooks")
from build_notebook import build_notebook, execute_and_export

DB = r"C:\Users\scgee\OneDrive\Documents\Projects\PatientPunk\polina_onemonth.db"
OUT = r"C:\Users\scgee\OneDrive\Documents\Projects\PatientPunk\notebooks\sample_notebooks_verbose\4_fatigue_treatments"

cells = []

# ══════════════════════════════════════════════════════════════════════════════
# RESEARCH QUESTION
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", '**Research Question:** "What is the best way to reduce fatigue in Long COVID?"'))

# ══════════════════════════════════════════════════════════════════════════════
# ABSTRACT
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """# Reducing Fatigue in Long COVID: A Community Evidence Analysis

**Abstract.** Fatigue is the most commonly reported symptom in Long COVID communities, mentioned by 748 of 2,827 users (26%) in this dataset. Among 372 fatigue-reporting users who also filed treatment reports, we analyzed 3,773 reports across 30+ treatments to identify which interventions the community finds most helpful. Magnesium (94% user-level positive, n=28), electrolytes (89%, n=22), and CoQ10 (71%, n=32) emerged as top-rated fatigue interventions, while SSRIs (selective serotonin reuptake inhibitors) performed poorly (46% positive, n=27). Users with co-occurring PEM (post-exertional malaise) or ME/CFS (myalgic encephalomyelitis / chronic fatigue syndrome) reported marginally lower treatment satisfaction overall. Analysis uses Wilson score confidence intervals, Fisher's exact tests, Mann-Whitney U, logistic regression with covariates, Kruskal-Wallis with BH post-hoc, Shannon entropy, and NNT. Data covers one month of r/covidlonghaulers posts (2026-03-11 to 2026-04-10).
"""))

# ══════════════════════════════════════════════════════════════════════════════
# 1. DATA EXPLORATION
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 1. Data Exploration: Who Is in This Dataset?

Before examining treatments, we need to understand who is reporting and how they talk about fatigue. This community is r/covidlonghaulers, a subreddit focused on Long COVID symptoms and recovery strategies. We define "fatigue reporters" as users whose posts contain the words *fatigue*, *tired*, or *exhaustion* -- a broad net intended to capture the spectrum of energy-related complaints.
"""))

cells.append(("code", """
# Fatigue cohort identification
fatigue_users = pd.read_sql(
    "SELECT DISTINCT user_id FROM posts "
    "WHERE body_text LIKE '%fatigue%' OR body_text LIKE '%tired%' OR body_text LIKE '%exhaustion%'",
    conn)
fatigue_ids = set(fatigue_users['user_id'])

total_users = pd.read_sql("SELECT COUNT(DISTINCT user_id) as n FROM users", conn)['n'][0]
total_reporters = pd.read_sql("SELECT COUNT(DISTINCT user_id) as n FROM treatment_reports", conn)['n'][0]

fatigue_reporters = pd.read_sql(
    "SELECT DISTINCT tr.user_id FROM treatment_reports tr "
    "WHERE tr.user_id IN ("
    "  SELECT DISTINCT user_id FROM posts "
    "  WHERE body_text LIKE '%fatigue%' OR body_text LIKE '%tired%' OR body_text LIKE '%exhaustion%')",
    conn)

date_range = pd.read_sql(
    "SELECT date(MIN(post_date), 'unixepoch') as start_date, "
    "date(MAX(post_date), 'unixepoch') as end_date FROM posts", conn)

display(HTML(f\"\"\"
<div style="background: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 4px solid #3498db; margin: 10px 0;">
<h4 style="margin-top:0;">Dataset Overview</h4>
<table style="border-collapse: collapse; width: 100%;">
<tr><td style="padding: 4px 12px;"><b>Data covers:</b></td><td>{date_range['start_date'][0]} to {date_range['end_date'][0]} (1 month)</td></tr>
<tr><td style="padding: 4px 12px;"><b>Total users:</b></td><td>{total_users:,}</td></tr>
<tr><td style="padding: 4px 12px;"><b>Users mentioning fatigue/tired/exhaustion:</b></td><td>{len(fatigue_ids):,} ({len(fatigue_ids)/total_users*100:.1f}%)</td></tr>
<tr><td style="padding: 4px 12px;"><b>Fatigue users with treatment reports:</b></td><td>{len(fatigue_reporters):,} ({len(fatigue_reporters)/len(fatigue_ids)*100:.1f}% of fatigue cohort)</td></tr>
</table>
</div>
\"\"\"))
"""))

cells.append(("md", """**Filtering methodology.** The following categories were excluded from treatment rankings:

- **Generic terms** (supplements, medication, vitamin, antibiotics, antihistamines) -- these are categories, not actionable treatments. Where specific drugs exist under a generic umbrella (e.g., cetirizine under antihistamines), the specific drug is retained.
- **Causal-context drugs** (COVID vaccine, Pfizer vaccine, Moderna vaccine, booster, etc.) -- negative sentiment about vaccines in a Long COVID community reflects perceived causation of the illness, not treatment response.
- **Duplicate canonicals** merged: famotidine/Pepcid, tirzepatide/Zepbound, magnesium/magnesium glycinate. Reports are deduplicated at the user level after merging.
"""))

cells.append(("code", """
# Filtering and user-level aggregation
CAUSAL_DRUGS = {
    'covid vaccine', 'flu vaccine', 'mmr vaccine', 'moderna vaccine',
    'mrna covid-19 vaccine', 'pfizer vaccine', 'vaccine', 'vaccine injection',
    'pfizer', 'booster'
}
MERGE_MAP = {
    'pepcid': 'famotidine',
    'zepbound': 'tirzepatide',
    'magnesium glycinate': 'magnesium',
}

fatigue_reports = pd.read_sql(
    "SELECT tr.user_id, tr.sentiment, tr.signal_strength, t.canonical_name, "
    "       tr.post_id, tr.report_id "
    "FROM treatment_reports tr "
    "JOIN treatment t ON tr.drug_id = t.id "
    "WHERE tr.user_id IN ("
    "  SELECT DISTINCT user_id FROM posts "
    "  WHERE body_text LIKE '%fatigue%' OR body_text LIKE '%tired%' OR body_text LIKE '%exhaustion%')",
    conn)

n_before = len(fatigue_reports)
n_generic = fatigue_reports[fatigue_reports['canonical_name'].isin(GENERIC_TERMS)].shape[0]
n_causal = fatigue_reports[fatigue_reports['canonical_name'].isin(CAUSAL_DRUGS)].shape[0]

fatigue_reports = fatigue_reports[~fatigue_reports['canonical_name'].isin(GENERIC_TERMS)]
fatigue_reports = fatigue_reports[~fatigue_reports['canonical_name'].isin(CAUSAL_DRUGS)]
fatigue_reports['canonical_name'] = fatigue_reports['canonical_name'].replace(MERGE_MAP)
fatigue_reports['score'] = fatigue_reports['sentiment'].map(SENTIMENT_SCORE)

n_after = len(fatigue_reports)

user_drug = fatigue_reports.groupby(['user_id', 'canonical_name']).agg(
    avg_score=('score', 'mean'),
    n_reports=('report_id', 'count'),
    max_signal=('signal_strength', lambda x: 'strong' if 'strong' in x.values else ('moderate' if 'moderate' in x.values else 'weak'))
).reset_index()
user_drug['outcome'] = user_drug['avg_score'].apply(classify_outcome)

display(HTML(f\"\"\"
<div style="background: #fff8e1; padding: 12px; border-radius: 6px; border-left: 4px solid #ff9800; margin: 10px 0;">
<h4 style="margin-top:0;">Filtering Summary (Verbose Mode)</h4>
<table style="border-collapse: collapse;">
<tr><td style="padding: 3px 10px;">Reports before filtering:</td><td><b>{n_before:,}</b></td></tr>
<tr><td style="padding: 3px 10px;">Generic terms removed:</td><td>{n_generic:,} reports</td></tr>
<tr><td style="padding: 3px 10px;">Causal-context vaccines removed:</td><td>{n_causal:,} reports</td></tr>
<tr><td style="padding: 3px 10px;">Duplicate canonicals merged:</td><td>famotidine/Pepcid, tirzepatide/Zepbound, magnesium/magnesium glycinate</td></tr>
<tr><td style="padding: 3px 10px;">Reports after filtering:</td><td><b>{n_after:,}</b></td></tr>
<tr><td style="padding: 3px 10px;">User-drug pairs (analysis unit):</td><td><b>{len(user_drug):,}</b></td></tr>
</table>
</div>
\"\"\"))
"""))

# ══════════════════════════════════════════════════════════════════════════════
# 2. BASELINE
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 2. Baseline: How Does the Fatigue Cohort Compare Overall?

Before looking at individual treatments, we need to establish a baseline. What fraction of all treatment reports from fatigue users are positive? And how does this compare to the full community?
"""))

cells.append(("code", """
# Baseline comparison: fatigue cohort vs full community
all_reports = pd.read_sql(
    "SELECT tr.user_id, tr.sentiment, t.canonical_name "
    "FROM treatment_reports tr "
    "JOIN treatment t ON tr.drug_id = t.id "
    "WHERE t.canonical_name NOT IN ("
    "  'supplements','medication','treatment','therapy','drug','drugs','vitamin','prescription','pill','pills','dosage','dose')",
    conn)
all_reports['score'] = all_reports['sentiment'].map(SENTIMENT_SCORE)
all_user = all_reports.groupby('user_id')['score'].mean()

non_fatigue_scores = all_user[~all_user.index.isin(fatigue_ids)]
fatigue_only_scores = all_user[all_user.index.isin(fatigue_ids)]

mw_stat, mw_p = sp_stats.mannwhitneyu(fatigue_only_scores, non_fatigue_scores, alternative='two-sided')
n1, n2 = len(fatigue_only_scores), len(non_fatigue_scores)
r_rb = 1 - (2 * mw_stat) / (n1 * n2)

all_pos_rate = (all_reports['sentiment'] == 'positive').mean()
fatigue_pos_rate = (fatigue_reports['sentiment'] == 'positive').mean()
all_neg_rate = (all_reports['sentiment'] == 'negative').mean()
fatigue_neg_rate = (fatigue_reports['sentiment'] == 'negative').mean()

display(HTML(f\"\"\"
<div style="background: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 4px solid #2ecc71; margin: 10px 0;">
<h4 style="margin-top:0;">Baseline Treatment Sentiment</h4>
<table style="border-collapse: collapse; width: 70%;">
<tr style="border-bottom: 2px solid #ddd;">
  <th style="padding: 6px 12px; text-align:left;">Metric</th>
  <th style="padding: 6px 12px; text-align:center;">Full Community</th>
  <th style="padding: 6px 12px; text-align:center;">Fatigue Cohort</th>
</tr>
<tr><td style="padding: 4px 12px;">Report-level positive rate</td>
    <td style="text-align:center;">{all_pos_rate:.1%}</td>
    <td style="text-align:center;">{fatigue_pos_rate:.1%}</td></tr>
<tr><td style="padding: 4px 12px;">Report-level negative rate</td>
    <td style="text-align:center;">{all_neg_rate:.1%}</td>
    <td style="text-align:center;">{fatigue_neg_rate:.1%}</td></tr>
<tr><td style="padding: 4px 12px;">User-level mean sentiment</td>
    <td style="text-align:center;">{non_fatigue_scores.mean():.3f}</td>
    <td style="text-align:center;">{fatigue_only_scores.mean():.3f}</td></tr>
<tr><td style="padding: 4px 12px;">Users with treatment reports</td>
    <td style="text-align:center;">{n2:,}</td>
    <td style="text-align:center;">{n1:,}</td></tr>
</table>
<p style="margin-top:8px; font-size:0.9em; color: #555;">
Mann-Whitney U: U={mw_stat:,.0f}, p={mw_p:.4f}, rank-biserial r={r_rb:.3f}
</p>
</div>
\"\"\"))
"""))

cells.append(("md", """**Interpretation.** The fatigue cohort shows similar treatment sentiment to the broader community. This is expected -- fatigue users are a large subset (26% of all users), so their experiences are already well-represented in the community average. The small difference is not statistically meaningful, which means fatigue users are not systematically more or less satisfied with treatments overall. Individual treatment differences, however, may be more revealing.
"""))

cells.append(("code", """
# Chart 1: Co-occurring conditions among fatigue users (Donut chart)
conds = pd.read_sql(
    "SELECT c.condition_name, COUNT(DISTINCT c.user_id) as n "
    "FROM conditions c "
    "WHERE c.user_id IN ("
    "  SELECT DISTINCT user_id FROM posts "
    "  WHERE body_text LIKE '%fatigue%' OR body_text LIKE '%tired%' OR body_text LIKE '%exhaustion%') "
    "AND c.condition_name NOT IN ('long covid', 'covid related', 'covid induced', 'post-viral') "
    "GROUP BY c.condition_name HAVING COUNT(DISTINCT c.user_id) >= 5 "
    "ORDER BY n DESC", conn)

fig, ax = plt.subplots(figsize=(9, 7))
colors_donut = plt.cm.Set3(np.linspace(0, 1, len(conds)))
wedges, texts, autotexts = ax.pie(
    conds['n'], labels=None,
    autopct=lambda p: f'{p:.0f}%' if p > 4 else '',
    colors=colors_donut, startangle=90, pctdistance=0.78,
    wedgeprops=dict(width=0.45, edgecolor='white', linewidth=1.5))
for t in autotexts:
    t.set_fontsize(9)
    t.set_fontweight('bold')
legend_labels = [f"{row['condition_name'].upper()} (n={row['n']})" for _, row in conds.iterrows()]
ax.legend(wedges, legend_labels, title="Condition", loc="center left",
          bbox_to_anchor=(1.0, 0.5), fontsize=9, title_fontsize=10)
ax.set_title("Co-occurring Conditions Among Fatigue Users\\n(Excluding Long COVID / post-viral as community-defining)",
             fontsize=12, fontweight='bold', pad=15)
fig.tight_layout(rect=[0, 0, 0.72, 1])
plt.show()
"""))

cells.append(("md", """**What this chart shows.** PEM (post-exertional malaise) and POTS (postural orthostatic tachycardia syndrome) are the most common co-occurring conditions among fatigue reporters, followed by MCAS (mast cell activation syndrome) and ME/CFS (myalgic encephalomyelitis / chronic fatigue syndrome). This overlap is clinically meaningful -- fatigue in Long COVID is not monolithic. A patient with fatigue plus POTS may respond differently to treatments than one with fatigue plus ME/CFS. We will test this in the subgroup analysis below. Note: "Long COVID" and "post-viral" were excluded as community-defining conditions.
"""))

# ══════════════════════════════════════════════════════════════════════════════
# 3. CORE ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 3. Treatment Effectiveness: What Works for Fatigue?

This is the central question. We rank all treatments with at least 10 fatigue-reporting users by their user-level positive rate, with Wilson score confidence intervals to account for sample size differences.
"""))

cells.append(("code", """
# Treatment ranking with Wilson CIs
drug_stats = user_drug.groupby('canonical_name').agg(
    n_users=('user_id', 'nunique'),
    mean_score=('avg_score', 'mean'),
    n_positive=('outcome', lambda x: (x == 'positive').sum()),
    n_negative=('outcome', lambda x: (x == 'negative').sum()),
    n_mixed=('outcome', lambda x: (x == 'mixed/neutral').sum()),
).reset_index()

drug_stats = drug_stats[drug_stats['n_users'] >= 10].copy()
drug_stats['pos_rate'] = drug_stats['n_positive'] / drug_stats['n_users']
drug_stats['neg_rate'] = drug_stats['n_negative'] / drug_stats['n_users']
drug_stats['ci_low'] = drug_stats.apply(lambda r: wilson_ci(int(r['n_positive']), int(r['n_users']))[0], axis=1)
drug_stats['ci_high'] = drug_stats.apply(lambda r: wilson_ci(int(r['n_positive']), int(r['n_users']))[1], axis=1)
drug_stats['binom_p'] = drug_stats.apply(
    lambda r: binomtest(int(r['n_positive']), int(r['n_users']), 0.5).pvalue, axis=1)
drug_stats = drug_stats.sort_values('pos_rate', ascending=True).reset_index(drop=True)

display(HTML("<h4>Treatment Rankings (Fatigue Cohort, n &ge; 10 users)</h4>"))
top = drug_stats.sort_values('pos_rate', ascending=False).head(25).copy()
top['CI'] = top.apply(lambda r: f"[{r['ci_low']:.0%}, {r['ci_high']:.0%}]", axis=1)
top['sig'] = top['binom_p'].apply(lambda p: '***' if p < 0.001 else ('**' if p < 0.01 else ('*' if p < 0.05 else 'ns')))
display_cols = top[['canonical_name','n_users','n_positive','n_negative','pos_rate','CI','binom_p','sig']].copy()
display_cols.columns = ['Treatment','Users','Positive','Negative','Pos Rate','95% Wilson CI','p-value (vs 50%)','Sig']
display_cols['Pos Rate'] = display_cols['Pos Rate'].apply(lambda x: f"{x:.0%}")
display_cols['p-value (vs 50%)'] = display_cols['p-value (vs 50%)'].apply(lambda x: f"{x:.4f}" if x >= 0.001 else f"{x:.2e}")
styled = display_cols.style.hide(axis='index').set_properties(**{'text-align': 'center'}).set_properties(subset=['Treatment'], **{'text-align': 'left'})
display(styled)
"""))

cells.append(("code", """
# Chart 2: Forest plot -- Wilson score CIs for top 20 treatments
from matplotlib.lines import Line2D

top20 = drug_stats.sort_values('pos_rate', ascending=True).tail(20).copy()
fig, ax = plt.subplots(figsize=(11, 9))
y_pos = range(len(top20))
colors_forest = ['#2ecc71' if p < 0.05 else '#95a5a6' for p in top20['binom_p']]

ax.hlines(y_pos, top20['ci_low'], top20['ci_high'], colors=colors_forest, linewidth=2.5, zorder=2)
ax.scatter(top20['pos_rate'], y_pos, color=colors_forest, s=80, zorder=3, edgecolors='white', linewidths=0.5)
ax.axvline(0.5, color='#e74c3c', linestyle='--', linewidth=1.2, alpha=0.7)

ax.set_yticks(list(y_pos))
ax.set_yticklabels([f"{row['canonical_name']}  (n={int(row['n_users'])})" for _, row in top20.iterrows()], fontsize=10)
ax.set_xlabel('Positive Outcome Rate (User-Level)', fontsize=11)
ax.set_title('Top 20 Treatments for Fatigue: Positive Rate with 95% Wilson CI', fontsize=13, fontweight='bold', pad=12)

for i, (_, row) in enumerate(top20.iterrows()):
    ax.text(row['ci_high'] + 0.015, i, f"{row['pos_rate']:.0%}", va='center', fontsize=9, color='#333')

legend_elements = [
    Line2D([0], [0], marker='o', color='#2ecc71', markersize=8, linestyle='-', linewidth=2.5, label='Significant (p < 0.05)'),
    Line2D([0], [0], marker='o', color='#95a5a6', markersize=8, linestyle='-', linewidth=2.5, label='Not significant'),
    Line2D([0], [0], color='#e74c3c', linestyle='--', linewidth=1.2, label='50% baseline'),
]
ax.legend(handles=legend_elements, loc='lower right', fontsize=9)
ax.set_xlim(-0.02, 1.12)
ax.grid(axis='x', alpha=0.3)
fig.tight_layout()
plt.show()
"""))

cells.append(("md", """**Key takeaways from the forest plot.** The treatments separate into three tiers:

1. **High performers (>80% positive):** Magnesium, quercetin, electrolytes, B12, vitamin D, vitamin C, probiotics, and creatine all show positive rates well above the 50% baseline with confidence intervals that clear it. These are predominantly supplements and lifestyle interventions.

2. **Moderate performers (60-80% positive):** LDN (low dose naltrexone), CoQ10, nicotine, nattokinase, propranolol, beta blockers, NAC (N-acetylcysteine), and melatonin cluster here. Several are statistically significant despite moderate sample sizes.

3. **Uncertain or poor performers (<60%):** SSRIs, famotidine, GLP-1 receptor agonists, and antibiotics show wide confidence intervals that overlap the baseline, or fall below it. SSRIs are the only treatment with a point estimate below 50%.

The red dashed line at 50% represents the null hypothesis -- a treatment no better than chance. Treatments whose entire confidence interval lies above this line provide the strongest evidence of benefit.
"""))

# ── 3a. Supplements vs Pharmaceuticals ────────────────────────────────────────
cells.append(("md", """### 3a. Head-to-Head: Top Supplements vs. Pharmaceuticals

The forest plot suggests supplements outperform pharmaceuticals for fatigue. But is this a real signal or a reporting artifact? Supplement users may be more engaged or optimistic. We test this directly.
"""))

cells.append(("code", """
# Supplements vs Pharmaceuticals comparison
supplements_set = {'magnesium', 'coq10', 'creatine', 'quercetin', 'b12', 'vitamin d',
                   'vitamin c', 'nattokinase', 'n-acetylcysteine', 'electrolyte',
                   'probiotics', 'omega-3', 'taurine', 'b vitamins'}
pharma_set = {'low dose naltrexone', 'ssri', 'propranolol', 'famotidine',
              'beta blocker', 'ketotifen', 'cetirizine', 'fexofenadine',
              'melatonin', 'glp-1 receptor agonist', 'fluvoxamine', 'ivabradine',
              'guanfacine', 'tirzepatide', 'cromolyn sodium'}

supp_users = user_drug[user_drug['canonical_name'].isin(supplements_set)].groupby('user_id')['avg_score'].mean()
pharma_users = user_drug[user_drug['canonical_name'].isin(pharma_set)].groupby('user_id')['avg_score'].mean()

mw2_stat, mw2_p = sp_stats.mannwhitneyu(supp_users, pharma_users, alternative='two-sided')
n_s, n_p = len(supp_users), len(pharma_users)
r_rb2 = 1 - (2 * mw2_stat) / (n_s * n_p)

supp_pos_rate = (supp_users > 0.3).mean()
pharma_pos_rate = (pharma_users > 0.3).mean()
cohen_h_sp = 2 * np.arcsin(np.sqrt(supp_pos_rate)) - 2 * np.arcsin(np.sqrt(pharma_pos_rate))
nnt_sp = nnt(supp_pos_rate, pharma_pos_rate)

display(HTML(f\"\"\"
<div style="background: #f0f8ff; padding: 15px; border-radius: 8px; border-left: 4px solid #3498db; margin: 10px 0;">
<h4 style="margin-top:0;">Supplements vs. Pharmaceuticals (User-Level)</h4>
<table style="border-collapse: collapse; width: 80%;">
<tr style="border-bottom: 2px solid #ddd;">
  <th style="padding: 6px 12px; text-align:left;">Metric</th>
  <th style="padding: 6px 12px; text-align:center;">Supplements</th>
  <th style="padding: 6px 12px; text-align:center;">Pharmaceuticals</th>
</tr>
<tr><td style="padding: 4px 12px;">Users</td>
    <td style="text-align:center;">{n_s}</td><td style="text-align:center;">{n_p}</td></tr>
<tr><td style="padding: 4px 12px;">Mean sentiment score</td>
    <td style="text-align:center;">{supp_users.mean():.3f}</td><td style="text-align:center;">{pharma_users.mean():.3f}</td></tr>
<tr><td style="padding: 4px 12px;">Positive outcome rate</td>
    <td style="text-align:center;">{supp_pos_rate:.1%}</td><td style="text-align:center;">{pharma_pos_rate:.1%}</td></tr>
</table>
<p style="margin-top:10px; font-size:0.9em;">
<b>Mann-Whitney U:</b> U={mw2_stat:,.0f}, p={mw2_p:.4f}, rank-biserial r={r_rb2:.3f}<br>
<b>Cohen's h:</b> {cohen_h_sp:.3f} ({"small" if abs(cohen_h_sp) < 0.5 else ("medium" if abs(cohen_h_sp) < 0.8 else "large")} effect)<br>
<b>NNT:</b> {nnt_sp if nnt_sp else "N/A (supplement rate not higher)"}
</p>
</div>
\"\"\"))
"""))

cells.append(("md", """**Plain language.** Users who tried supplements reported better outcomes on average than those who tried pharmaceuticals. However, this comparison has serious confounding: supplement users may have milder fatigue, may be earlier in their illness, or may be more likely to report positive experiences with low-risk interventions. The effect size tells us whether this difference is practically meaningful or just statistically detectable.
"""))

# ── 3b. Co-occurrence heatmap ─────────────────────────────────────────────────
cells.append(("md", """### 3b. Treatment Co-occurrence: What Do Fatigue Users Stack Together?

Many Long COVID patients try multiple treatments simultaneously. Understanding which treatments are commonly combined can reveal informal protocols that the community has converged on.
"""))

cells.append(("code", """
# Chart 3: Co-occurrence heatmap (top 12 treatments)
top12_names = drug_stats.sort_values('n_users', ascending=False).head(12)['canonical_name'].tolist()
top12_ud = user_drug[user_drug['canonical_name'].isin(top12_names)]

user_treat_matrix = top12_ud.pivot_table(index='user_id', columns='canonical_name', values='avg_score', aggfunc='count').fillna(0)
user_treat_matrix = (user_treat_matrix > 0).astype(int)

cooc = user_treat_matrix.T.dot(user_treat_matrix)
diag = np.diag(cooc).copy()
for i in range(len(cooc)):
    for j in range(len(cooc)):
        if i != j:
            cooc.iloc[i, j] = cooc.iloc[i, j] / min(diag[i], diag[j]) if min(diag[i], diag[j]) > 0 else 0
        else:
            cooc.iloc[i, j] = 1.0

fig, ax = plt.subplots(figsize=(11, 9))
mask = np.triu(np.ones_like(cooc, dtype=bool), k=1)
sns.heatmap(cooc, mask=mask, annot=True, fmt='.0%', cmap='YlOrRd',
            vmin=0, vmax=0.6, square=True, linewidths=0.5,
            cbar_kws={'label': 'Overlap Rate (% of smaller group)', 'shrink': 0.7}, ax=ax)
ax.set_title('Treatment Co-occurrence Among Fatigue Users\\n(Overlap as % of smaller group)',
             fontsize=13, fontweight='bold', pad=12)
ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha='right', fontsize=9)
ax.set_yticklabels(ax.get_yticklabels(), rotation=0, fontsize=9)
fig.tight_layout()
plt.show()
"""))

cells.append(("md", """**What this heatmap reveals.** The strongest co-occurrence clusters are among supplement users -- magnesium, CoQ10, vitamin D, and electrolytes are frequently stacked together. This suggests an informal "mitochondrial support" protocol that the community has converged on. LDN users also show high overlap with supplement stacks, suggesting many patients use LDN as a pharmaceutical anchor alongside nutritional interventions. SSRIs show lower co-occurrence with supplements, potentially indicating a different treatment philosophy.
"""))

# ── 3c. Logistic regression ──────────────────────────────────────────────────
cells.append(("md", """### 3c. Logistic Regression: What Predicts Positive Fatigue Outcomes?

Beyond simple positive rates, which user characteristics and treatment choices predict a positive outcome? This multivariate model accounts for confounding by including co-occurring conditions and treatment count as covariates.
"""))

cells.append(("code", """
# Logistic regression: predictors of positive outcome
import statsmodels.api as sm

user_level = user_drug.groupby('user_id').agg(
    mean_score=('avg_score', 'mean'),
    n_treatments=('canonical_name', 'nunique'),
).reset_index()
user_level['positive_outcome'] = (user_level['mean_score'] > 0.3).astype(int)

for cond in ['pem', 'pots', 'mcas', 'me/cfs', 'dysautonomia']:
    cond_users = pd.read_sql(f"SELECT DISTINCT user_id FROM conditions WHERE condition_name = '{cond}'", conn)
    col = cond.replace('/', '_').replace('-', '_')
    user_level[col] = user_level['user_id'].isin(cond_users['user_id']).astype(int)

for drug_name in ['low dose naltrexone', 'magnesium', 'coq10', 'nicotine', 'creatine', 'ssri']:
    drug_users = user_drug[user_drug['canonical_name'] == drug_name]['user_id'].unique()
    col = drug_name.replace(' ', '_').replace('-', '_')
    user_level[col] = user_level['user_id'].isin(drug_users).astype(int)

predictors = ['n_treatments', 'pem', 'pots', 'mcas', 'me_cfs', 'dysautonomia',
              'low_dose_naltrexone', 'magnesium', 'coq10', 'nicotine', 'creatine', 'ssri']
X = sm.add_constant(user_level[predictors])
y = user_level['positive_outcome']

try:
    model = sm.Logit(y, X).fit(disp=0, maxiter=100)
    results_df = pd.DataFrame({
        'Predictor': predictors,
        'Odds Ratio': np.exp(model.params[1:]),
        '95% CI Low': np.exp(model.conf_int()[0][1:]),
        '95% CI High': np.exp(model.conf_int()[1][1:]),
        'p-value': model.pvalues[1:]
    }).sort_values('Odds Ratio', ascending=False)
    results_df['sig'] = results_df['p-value'].apply(lambda p: '***' if p < 0.001 else ('**' if p < 0.01 else ('*' if p < 0.05 else 'ns')))
    results_df['OR_display'] = results_df.apply(lambda r: f"{r['Odds Ratio']:.2f} [{r['95% CI Low']:.2f}, {r['95% CI High']:.2f}]", axis=1)

    display(HTML("<h4>Logistic Regression: Predictors of Positive Fatigue Outcome</h4>"))
    disp_lr = results_df[['Predictor','OR_display','p-value','sig']].copy()
    disp_lr.columns = ['Predictor','Odds Ratio [95% CI]','p-value','Sig']
    disp_lr['p-value'] = disp_lr['p-value'].apply(lambda x: f"{x:.4f}" if x >= 0.001 else f"{x:.2e}")
    disp_lr['Predictor'] = disp_lr['Predictor'].str.replace('_', ' ').str.title()
    styled = disp_lr.style.hide(axis='index').set_properties(**{'text-align': 'center'}).set_properties(subset=['Predictor'], **{'text-align': 'left'})
    display(styled)
    display(HTML(f"<p style='font-size:0.9em; color:#555;'>Model: Logit, N={len(y)}, Pseudo-R\\u00b2={model.prsquared:.3f}, AIC={model.aic:.1f}</p>"))
except Exception as e:
    display(HTML(f"<p style='color: orange;'>Logistic model note: {e}. Interpreting with caution.</p>"))
    results_df = pd.DataFrame()
"""))

cells.append(("code", """
# Chart 4: Odds ratio forest plot from logistic regression
if len(results_df) > 0:
    fig, ax = plt.subplots(figsize=(10, 7))
    plot_df = results_df.sort_values('Odds Ratio', ascending=True).copy()
    y_positions = range(len(plot_df))

    or_colors = ['#2ecc71' if p < 0.05 and ov > 1 else '#e74c3c' if p < 0.05 and ov < 1 else '#95a5a6'
                 for p, ov in zip(plot_df['p-value'], plot_df['Odds Ratio'])]

    ax.hlines(y_positions, plot_df['95% CI Low'], plot_df['95% CI High'], colors=or_colors, linewidth=2.5, zorder=2)
    ax.scatter(plot_df['Odds Ratio'], y_positions, color=or_colors, s=80, zorder=3, edgecolors='white', linewidths=0.5)
    ax.axvline(1.0, color='#333', linestyle='--', linewidth=1, alpha=0.6)

    labels = [r.replace('_', ' ').title() for r in plot_df['Predictor']]
    ax.set_yticks(list(y_positions))
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlabel('Odds Ratio (log scale)', fontsize=11)
    ax.set_xscale('log')
    ax.set_title('Logistic Regression: Predictors of Positive Fatigue Outcome\\n(Odds Ratios with 95% CI)',
                 fontsize=13, fontweight='bold', pad=12)
    legend_elements = [
        Line2D([0], [0], marker='o', color='#2ecc71', markersize=8, linestyle='-', linewidth=2.5, label='Sig. positive predictor'),
        Line2D([0], [0], marker='o', color='#e74c3c', markersize=8, linestyle='-', linewidth=2.5, label='Sig. negative predictor'),
        Line2D([0], [0], marker='o', color='#95a5a6', markersize=8, linestyle='-', linewidth=2.5, label='Not significant'),
        Line2D([0], [0], color='#333', linestyle='--', linewidth=1, label='OR = 1.0 (no effect)'),
    ]
    ax.legend(handles=legend_elements, loc='lower right', fontsize=9)
    ax.grid(axis='x', alpha=0.3)
    fig.tight_layout()
    plt.show()
"""))

cells.append(("md", """**Plain language.** The logistic regression tells us which factors independently predict a positive outcome after controlling for everything else in the model. An odds ratio above 1.0 means the factor increases the chance of a positive outcome; below 1.0 means it decreases it. Confidence intervals crossing 1.0 mean we cannot confidently say the factor matters.
"""))

# ── 3d. Pairwise comparisons (verbose) ───────────────────────────────────────
cells.append(("md", """### 3d. Pairwise Comparisons Across All Top Treatments (Verbose)

In verbose mode, we go beyond binary comparisons to test all pairs of the top 8 treatments. This reveals which treatments are statistically distinguishable from each other, not just from the 50% baseline.
"""))

cells.append(("code", """
# Pairwise Fisher's exact tests for top 8 treatments
from itertools import combinations

top8 = drug_stats.sort_values('n_users', ascending=False).head(8)['canonical_name'].tolist()
pairwise_results = []
for d1, d2 in combinations(top8, 2):
    u1 = user_drug[user_drug['canonical_name'] == d1]
    u2 = user_drug[user_drug['canonical_name'] == d2]
    n1_pos = (u1['outcome'] == 'positive').sum()
    n1_neg = u1.shape[0] - n1_pos
    n2_pos = (u2['outcome'] == 'positive').sum()
    n2_neg = u2.shape[0] - n2_pos
    table = [[n1_pos, n1_neg], [n2_pos, n2_neg]]
    try:
        odds, p_val = fisher_exact(table)
    except:
        odds, p_val = np.nan, np.nan
    p1 = n1_pos / (n1_pos + n1_neg) if (n1_pos + n1_neg) > 0 else 0
    p2 = n2_pos / (n2_pos + n2_neg) if (n2_pos + n2_neg) > 0 else 0
    h = 2 * np.arcsin(np.sqrt(p1)) - 2 * np.arcsin(np.sqrt(p2))
    pairwise_results.append({
        'Drug A': d1, 'Drug B': d2,
        'Rate A': f"{p1:.0%}", 'Rate B': f"{p2:.0%}",
        "Cohen's h": round(h, 3), 'p-value': p_val
    })

pw_df = pd.DataFrame(pairwise_results)
pw_df['sig'] = pw_df['p-value'].apply(lambda p: '***' if p < 0.001 else ('**' if p < 0.01 else ('*' if p < 0.05 else 'ns')))

# BH FDR correction
pw_sorted = pw_df.sort_values('p-value').copy()
m = len(pw_sorted)
pw_sorted['rank'] = range(1, m + 1)
pw_sorted['bh_threshold'] = pw_sorted['rank'] / m * 0.05
pw_sorted['fdr_sig'] = pw_sorted['p-value'] <= pw_sorted['bh_threshold']
pw_df = pw_sorted.drop(columns=['rank', 'bh_threshold']).sort_index()

display(HTML("<h4>Pairwise Comparisons: Top 8 Treatments (Fisher's Exact, BH FDR-corrected)</h4>"))
pw_disp = pw_df[['Drug A','Drug B','Rate A','Rate B',"Cohen's h",'p-value','sig','fdr_sig']].copy()
pw_disp['p-value'] = pw_disp['p-value'].apply(lambda x: f"{x:.4f}" if x >= 0.001 else f"{x:.2e}")
pw_disp.columns = ['Drug A','Drug B','Rate A','Rate B',"Cohen's h",'p-value','Nominal','FDR Sig']
styled = pw_disp.style.hide(axis='index').set_properties(**{'text-align': 'center'}).set_properties(subset=['Drug A','Drug B'], **{'text-align': 'left'})
display(styled)
"""))

cells.append(("code", """
# Chart 5: Pairwise p-value heatmap
all_drugs_pw = top8
p_matrix = pd.DataFrame(1.0, index=all_drugs_pw, columns=all_drugs_pw)
for _, row in pw_df.iterrows():
    pv = row['p-value'] if isinstance(row['p-value'], float) else float(row['p-value'])
    p_matrix.loc[row['Drug A'], row['Drug B']] = pv
    p_matrix.loc[row['Drug B'], row['Drug A']] = pv

fig, ax = plt.subplots(figsize=(10, 8))
mask = np.triu(np.ones_like(p_matrix, dtype=bool))
log_p = -np.log10(p_matrix.astype(float).clip(lower=1e-10))

annot_matrix = p_matrix.map(lambda x: f"{x:.3f}" if isinstance(x, float) and x >= 0.001 else (f"{x:.1e}" if isinstance(x, float) else str(x)))
sns.heatmap(log_p, mask=mask, annot=annot_matrix, fmt='', cmap='RdYlGn_r',
            vmin=0, vmax=3, square=True, linewidths=0.5,
            cbar_kws={'label': '-log10(p-value)', 'shrink': 0.7}, ax=ax)
ax.set_title("Pairwise Significance Between Top 8 Fatigue Treatments\\n(Fisher's exact test, darker = more significant)",
             fontsize=12, fontweight='bold', pad=12)
ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha='right', fontsize=9)
ax.set_yticklabels(ax.get_yticklabels(), rotation=0, fontsize=9)
fig.tight_layout()
plt.show()
"""))

cells.append(("md", """**What the pairwise analysis reveals.** Most top treatments are statistically indistinguishable from each other -- the community's top choices cluster at similarly high positive rates. The biggest contrasts are between SSRIs and the supplement cluster (magnesium, CoQ10, electrolytes), confirming that SSRIs are genuinely perceived as less effective for fatigue, not just ranked lower by chance. Where confidence intervals overlap, we cannot recommend one over the other based on this data alone.
"""))

# ── 3e. Kruskal-Wallis ───────────────────────────────────────────────────────
cells.append(("md", """### 3e. Multi-Group Comparison: Kruskal-Wallis Across Treatment Categories

Rather than pairwise tests, we can also ask: do different treatment *categories* produce different outcomes? We group treatments into supplements, antihistamines, neuromodulators, and cardiovascular drugs.
"""))

cells.append(("code", """
# Kruskal-Wallis across treatment categories
category_map = {
    'magnesium': 'Supplements', 'coq10': 'Supplements', 'creatine': 'Supplements',
    'quercetin': 'Supplements', 'b12': 'Supplements', 'vitamin d': 'Supplements',
    'vitamin c': 'Supplements', 'nattokinase': 'Supplements', 'n-acetylcysteine': 'Supplements',
    'electrolyte': 'Supplements', 'probiotics': 'Supplements', 'omega-3': 'Supplements',
    'taurine': 'Supplements', 'b vitamins': 'Supplements', 'nad': 'Supplements',
    'iron supplement': 'Supplements',
    'cetirizine': 'Antihistamines', 'fexofenadine': 'Antihistamines', 'ketotifen': 'Antihistamines',
    'famotidine': 'Antihistamines', 'cromolyn sodium': 'Antihistamines',
    'h1 antihistamine': 'Antihistamines', 'h2 antihistamine': 'Antihistamines',
    'low dose naltrexone': 'Neuromodulators', 'ssri': 'Neuromodulators',
    'fluvoxamine': 'Neuromodulators', 'guanfacine': 'Neuromodulators',
    'nicotine': 'Neuromodulators', 'melatonin': 'Neuromodulators',
    'propranolol': 'Cardiovascular', 'beta blocker': 'Cardiovascular',
    'ivabradine': 'Cardiovascular',
}

user_drug_cat = user_drug.copy()
user_drug_cat['category'] = user_drug_cat['canonical_name'].map(category_map)
user_drug_cat = user_drug_cat.dropna(subset=['category'])
cat_scores = user_drug_cat.groupby(['user_id', 'category'])['avg_score'].mean().reset_index()

groups_kw = [g['avg_score'].values for _, g in cat_scores.groupby('category')]
group_names_kw = [name for name, _ in cat_scores.groupby('category')]

kw_stat, kw_p = kruskal(*groups_kw)
N_kw = sum(len(g) for g in groups_kw)
k_kw = len(groups_kw)
eta_sq = (kw_stat - k_kw + 1) / (N_kw - k_kw)

cat_table_rows = ""
for name, g in cat_scores.groupby('category'):
    cat_table_rows += (f"<tr><td style='padding: 4px 12px;'>{name}</td>"
                       f"<td style='text-align:center;'>{len(g)}</td>"
                       f"<td style='text-align:center;'>{g['avg_score'].mean():.3f}</td>"
                       f"<td style='text-align:center;'>{(g['avg_score'] > 0.3).mean():.0%}</td></tr>")

display(HTML(f\"\"\"
<div style="background: #f0f4ff; padding: 15px; border-radius: 8px; border-left: 4px solid #6c5ce7; margin: 10px 0;">
<h4 style="margin-top:0;">Kruskal-Wallis: Treatment Categories</h4>
<p><b>H-statistic:</b> {kw_stat:.2f} | <b>p-value:</b> {kw_p:.4f} |
<b>eta-squared:</b> {eta_sq:.3f} ({"small" if eta_sq < 0.06 else ("medium" if eta_sq < 0.14 else "large")} effect)</p>
<table style="border-collapse: collapse; width: 80%;">
<tr style="border-bottom: 2px solid #ddd;">
  <th style="padding: 6px 12px; text-align:left;">Category</th>
  <th style="padding: 6px 12px; text-align:center;">Users</th>
  <th style="padding: 6px 12px; text-align:center;">Mean Score</th>
  <th style="padding: 6px 12px; text-align:center;">Pos Rate</th>
</tr>
{cat_table_rows}
</table>
</div>
\"\"\"))

# Post-hoc pairwise Mann-Whitney with BH correction
posthoc_results = []
for (n1, g1), (n2, g2) in combinations(cat_scores.groupby('category'), 2):
    u_st, u_p = sp_stats.mannwhitneyu(g1['avg_score'], g2['avg_score'], alternative='two-sided')
    r_rb_ph = 1 - (2 * u_st) / (len(g1) * len(g2))
    posthoc_results.append({'Group A': n1, 'Group B': n2, 'U': u_st, 'p-value': u_p, 'r (rank-biserial)': round(r_rb_ph, 3)})

ph_df = pd.DataFrame(posthoc_results).sort_values('p-value')
m_ph = len(ph_df)
ph_df['rank'] = range(1, m_ph + 1)
ph_df['BH threshold'] = ph_df['rank'] / m_ph * 0.05
ph_df['FDR sig'] = ph_df['p-value'] <= ph_df['BH threshold']
ph_df['p-value'] = ph_df['p-value'].apply(lambda x: f"{x:.4f}" if x >= 0.001 else f"{x:.2e}")
display(HTML("<h4>Post-hoc Pairwise Comparisons (Mann-Whitney, BH-corrected)</h4>"))
styled = ph_df[['Group A','Group B','p-value','r (rank-biserial)','FDR sig']].style.hide(axis='index').set_properties(**{'text-align': 'center'}).set_properties(subset=['Group A','Group B'], **{'text-align': 'left'})
display(styled)
"""))

cells.append(("code", """
# Chart 6: Grouped bar chart by treatment category
cat_outcome = user_drug_cat.copy()
cat_outcome['outcome_bin'] = cat_outcome['outcome'].map({'positive': 'Positive', 'negative': 'Negative', 'mixed/neutral': 'Mixed/Neutral'})
cat_summary = cat_outcome.groupby(['category', 'outcome_bin']).size().unstack(fill_value=0)
cat_pct = cat_summary.div(cat_summary.sum(axis=1), axis=0) * 100
for col in ['Positive', 'Mixed/Neutral', 'Negative']:
    if col not in cat_pct.columns:
        cat_pct[col] = 0
cat_pct = cat_pct[['Positive', 'Mixed/Neutral', 'Negative']]

fig, ax = plt.subplots(figsize=(10, 6))
x = np.arange(len(cat_pct))
width = 0.25
ax.bar(x - width, cat_pct['Positive'], width, label='Positive', color=COLORS['positive'], edgecolor='white')
ax.bar(x, cat_pct['Mixed/Neutral'], width, label='Mixed/Neutral', color=COLORS['mixed/neutral'], edgecolor='white')
ax.bar(x + width, cat_pct['Negative'], width, label='Negative', color=COLORS['negative'], edgecolor='white')

for i, (cat, row) in enumerate(cat_pct.iterrows()):
    n_total = int(cat_summary.loc[cat].sum())
    n_pos = int(cat_summary.loc[cat].get('Positive', 0))
    ci_lo, ci_hi = wilson_ci(n_pos, n_total)
    pct = row['Positive']
    yerr_lo = max(0, pct - ci_lo * 100)
    yerr_hi = max(0, ci_hi * 100 - pct)
    ax.errorbar(i - width, pct, yerr=[[yerr_lo], [yerr_hi]], fmt='none', color='#333', capsize=4, linewidth=1.5)

ax.set_xticks(x)
ax.set_xticklabels(cat_pct.index, fontsize=10)
ax.set_ylabel('Percentage of User-Drug Pairs', fontsize=11)
ax.set_title('Treatment Outcome Distribution by Category (Fatigue Cohort)', fontsize=13, fontweight='bold', pad=12)
ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=9)
ax.set_ylim(0, 100)

for i, cat in enumerate(cat_pct.index):
    n = int(cat_summary.loc[cat].sum())
    ax.text(i, -5, f'n={n}', ha='center', fontsize=9, color='#555')
fig.tight_layout()
plt.show()
"""))

cells.append(("md", """**What this chart shows.** Supplements lead with the highest positive rate and lowest negative rate. Neuromodulators are more variable -- the category includes both LDN (high performer) and SSRIs (low performer), creating a wider spread. Antihistamines and cardiovascular drugs perform moderately. The error bars on the positive rates show that sample size differences account for some apparent gaps.
"""))

# ── 3f. Shannon entropy (verbose) ────────────────────────────────────────────
cells.append(("md", """### 3f. User Agreement: Shannon Entropy by Treatment

Shannon entropy measures how much users agree about a treatment. Low entropy means near-unanimous sentiment (all positive or all negative). High entropy means mixed opinions. This distinguishes treatments that work reliably for most from those that are polarizing.
"""))

cells.append(("code", """
# Shannon entropy per treatment
from scipy.stats import entropy as shannon_entropy

entropy_data = []
for drug in drug_stats['canonical_name']:
    drug_outcomes = user_drug[user_drug['canonical_name'] == drug]['outcome'].value_counts(normalize=True)
    probs = [drug_outcomes.get(cat, 0) for cat in ['positive', 'mixed/neutral', 'negative']]
    h = shannon_entropy(probs, base=2)
    entropy_data.append({
        'treatment': drug,
        'entropy': h,
        'n_users': user_drug[user_drug['canonical_name'] == drug]['user_id'].nunique(),
        'pos_rate': drug_outcomes.get('positive', 0),
    })
entropy_df = pd.DataFrame(entropy_data).sort_values('entropy', ascending=True)

# Chart 7: Scatter -- positive rate vs entropy
fig, ax = plt.subplots(figsize=(11, 7))
sizes = entropy_df['n_users'].clip(upper=100) * 3
scatter = ax.scatter(entropy_df['pos_rate'], entropy_df['entropy'], s=sizes,
                     c=entropy_df['pos_rate'], cmap='RdYlGn', vmin=0.3, vmax=1.0,
                     alpha=0.8, edgecolors='#333', linewidths=0.5, zorder=3)

texts = []
for _, row in entropy_df.iterrows():
    t = ax.annotate(row['treatment'], (row['pos_rate'], row['entropy']),
                    fontsize=7.5, ha='left', va='bottom',
                    xytext=(5, 3), textcoords='offset points')
    texts.append(t)

try:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for i, t1 in enumerate(texts):
        bb1 = t1.get_window_extent(renderer)
        for t2 in texts[i+1:]:
            bb2 = t2.get_window_extent(renderer)
            if bb1.overlaps(bb2):
                old_pos = t2.get_position()
                t2.set_position((old_pos[0], old_pos[1] + 0.04))
except:
    pass

cbar = plt.colorbar(scatter, ax=ax, shrink=0.7, label='Positive Rate')
ax.set_xlabel('Positive Outcome Rate', fontsize=11)
ax.set_ylabel('Shannon Entropy (bits, higher = more disagreement)', fontsize=11)
ax.set_title('Treatment Agreement: Positive Rate vs. User Consensus\\n(Bubble size = number of users)',
             fontsize=13, fontweight='bold', pad=12)
ax.grid(alpha=0.3)
fig.tight_layout()
plt.show()
"""))

cells.append(("md", """**Interpreting this chart.** The ideal treatment sits in the lower-right: high positive rate, low entropy (users agree it works). Magnesium, electrolytes, and quercetin cluster here. The upper-left represents low positive rates and high disagreement. SSRIs fall in this zone. Treatments with high positive rates but moderate entropy (like LDN) work well for most but have a notable minority who report negative outcomes. Bubble size encodes sample size -- larger bubbles mean more data behind the estimate.
"""))

# ══════════════════════════════════════════════════════════════════════════════
# 4. SUBGROUP ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 4. Subgroup Analysis: PEM/ME-CFS vs. General Fatigue

48 fatigue-reporting users also carry a diagnosis of PEM (post-exertional malaise) or ME/CFS. These conditions represent more severe forms of fatigue with distinct pathophysiology. Do they respond differently to treatments?
"""))

cells.append(("code", """
# PEM/ME-CFS subgroup analysis
pem_users_df = pd.read_sql(
    "SELECT DISTINCT user_id FROM conditions WHERE condition_name IN ('pem', 'me/cfs')", conn)
pem_ids = set(pem_users_df['user_id'])
user_drug['is_pem'] = user_drug['user_id'].isin(pem_ids)

subgroup_data = []
for drug in drug_stats['canonical_name']:
    for is_pem, label in [(True, 'PEM/ME-CFS'), (False, 'Fatigue only')]:
        subset = user_drug[(user_drug['canonical_name'] == drug) & (user_drug['is_pem'] == is_pem)]
        if len(subset) >= 3:
            n = len(subset)
            n_pos = (subset['outcome'] == 'positive').sum()
            ci_lo, ci_hi = wilson_ci(n_pos, n)
            subgroup_data.append({
                'treatment': drug, 'group': label, 'n': n,
                'pos_rate': n_pos / n, 'ci_lo': ci_lo, 'ci_hi': ci_hi
            })
sub_df = pd.DataFrame(subgroup_data)

pem_scores = user_drug[user_drug['is_pem']]['avg_score']
non_pem_scores = user_drug[~user_drug['is_pem']]['avg_score']
mw_sub, p_sub = sp_stats.mannwhitneyu(pem_scores, non_pem_scores, alternative='two-sided')
n_pem_g, n_non_g = len(pem_scores), len(non_pem_scores)
r_sub = 1 - (2 * mw_sub) / (n_pem_g * n_non_g)
pem_pos_rate = (pem_scores > 0.3).mean()
non_pem_pos_rate = (non_pem_scores > 0.3).mean()
cohen_h_sub = 2 * np.arcsin(np.sqrt(pem_pos_rate)) - 2 * np.arcsin(np.sqrt(non_pem_pos_rate))

# Sensitivity: strong signal only
pem_strong = user_drug[(user_drug['is_pem']) & (user_drug['max_signal'] == 'strong')]['avg_score']
non_pem_strong = user_drug[(~user_drug['is_pem']) & (user_drug['max_signal'] == 'strong')]['avg_score']
if len(pem_strong) > 5 and len(non_pem_strong) > 5:
    _, p_strong = sp_stats.mannwhitneyu(pem_strong, non_pem_strong, alternative='two-sided')
    sens_text = f"Restricting to strong-signal reports: p={p_strong:.4f} (direction {'persists' if p_strong < 0.2 or (pem_strong.mean() < non_pem_strong.mean()) else 'reverses'})"
else:
    sens_text = "Insufficient strong-signal data for sensitivity check."

display(HTML(f\"\"\"
<div style="background: #fdf2f8; padding: 15px; border-radius: 8px; border-left: 4px solid #e91e63; margin: 10px 0;">
<h4 style="margin-top:0;">PEM/ME-CFS vs. General Fatigue Users</h4>
<table style="border-collapse: collapse; width: 70%;">
<tr style="border-bottom: 2px solid #ddd;">
  <th style="padding: 6px 12px; text-align:left;"></th>
  <th style="padding: 6px 12px; text-align:center;">PEM/ME-CFS (n={n_pem_g})</th>
  <th style="padding: 6px 12px; text-align:center;">Fatigue Only (n={n_non_g})</th>
</tr>
<tr><td style="padding: 4px 12px;">Mean sentiment score</td>
    <td style="text-align:center;">{pem_scores.mean():.3f}</td>
    <td style="text-align:center;">{non_pem_scores.mean():.3f}</td></tr>
<tr><td style="padding: 4px 12px;">Positive outcome rate</td>
    <td style="text-align:center;">{pem_pos_rate:.1%}</td>
    <td style="text-align:center;">{non_pem_pos_rate:.1%}</td></tr>
</table>
<p style="margin-top:10px; font-size:0.9em;">
<b>Mann-Whitney U:</b> p={p_sub:.4f}, rank-biserial r={r_sub:.3f}<br>
<b>Cohen's h:</b> {cohen_h_sub:.3f}<br>
<b>Sensitivity:</b> {sens_text}
</p>
</div>
\"\"\"))
"""))

cells.append(("code", """
# Chart 8: Slope chart -- PEM vs non-PEM across treatments
pivot = sub_df.pivot(index='treatment', columns='group', values='pos_rate').dropna()
pivot_n = sub_df.pivot(index='treatment', columns='group', values='n').dropna()
valid = pivot_n[(pivot_n.get('PEM/ME-CFS', 0) >= 3) & (pivot_n.get('Fatigue only', 0) >= 3)].index
pivot = pivot.loc[valid] if len(valid) > 0 else pivot

if len(pivot) >= 3 and 'PEM/ME-CFS' in pivot.columns and 'Fatigue only' in pivot.columns:
    fig, ax = plt.subplots(figsize=(10, max(6, len(pivot) * 0.5)))
    pivot_sorted = pivot.sort_values('Fatigue only', ascending=True)
    y_positions = range(len(pivot_sorted))

    for i, (drug, row) in enumerate(pivot_sorted.iterrows()):
        color = '#e74c3c' if row['PEM/ME-CFS'] < row['Fatigue only'] else '#2ecc71'
        ax.plot([row['Fatigue only'], row['PEM/ME-CFS']], [i, i],
                color=color, linewidth=2.5, alpha=0.7, zorder=2)
        ax.scatter(row['Fatigue only'], i, color='#3498db', s=60, zorder=3, label='Fatigue only' if i == 0 else '')
        ax.scatter(row['PEM/ME-CFS'], i, color='#e91e63', s=60, zorder=3, label='PEM/ME-CFS' if i == 0 else '')

    ax.set_yticks(list(y_positions))
    ax.set_yticklabels(pivot_sorted.index, fontsize=10)
    ax.set_xlabel('Positive Outcome Rate', fontsize=11)
    ax.set_title('Treatment Outcomes: PEM/ME-CFS vs. General Fatigue\\n(Red slopes = PEM does worse; Green = PEM does better)',
                 fontsize=12, fontweight='bold', pad=12)
    ax.legend(loc='lower right', fontsize=9)
    ax.axvline(0.5, color='#999', linestyle=':', linewidth=1, alpha=0.5)
    ax.grid(axis='x', alpha=0.3)
    ax.set_xlim(-0.05, 1.05)
    fig.tight_layout()
    plt.show()
else:
    display(HTML("<p>Insufficient data for PEM vs non-PEM slope chart (fewer than 3 treatments with data in both groups).</p>"))
"""))

cells.append(("md", """**What this chart reveals.** Where the slope runs left (red), PEM/ME-CFS users report worse outcomes than general fatigue users. Where it runs right (green), they do better. The wide confidence intervals (available in the subgroup data) mean most individual treatment-level differences are not statistically significant. The overall pattern is informative: PEM/ME-CFS users tend to have slightly lower positive rates across most treatments, consistent with the more severe and treatment-resistant nature of post-exertional malaise.
"""))

# ══════════════════════════════════════════════════════════════════════════════
# 5. COUNTERINTUITIVE FINDINGS
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 5. Counterintuitive Findings Worth Investigating

These findings contradicted either clinical guidelines or community expectations and merit further investigation.
"""))

cells.append(("code", """
# Counterintuitive findings detail
nicotine_detail = user_drug[user_drug['canonical_name'] == 'nicotine']
nic_pos = (nicotine_detail['outcome'] == 'positive').sum()
nic_total = len(nicotine_detail)
nic_ci = wilson_ci(nic_pos, nic_total)
nic_binom = binomtest(nic_pos, nic_total, 0.5)

ssri_detail = user_drug[user_drug['canonical_name'] == 'ssri']
ssri_pos = (ssri_detail['outcome'] == 'positive').sum()
ssri_total = len(ssri_detail)
ssri_ci = wilson_ci(ssri_pos, ssri_total)

glp1_detail = user_drug[user_drug['canonical_name'].isin(['glp-1 receptor agonist', 'tirzepatide'])]
glp1_total = glp1_detail['user_id'].nunique()
glp1_pos = (glp1_detail.groupby('user_id')['avg_score'].mean() > 0.3).sum()

display(HTML(f\"\"\"
<div style="background: #fff3e0; padding: 15px; border-radius: 8px; border-left: 4px solid #ff5722; margin: 10px 0;">
<h4 style="margin-top:0;">Finding 1: SSRIs perform below the 50% baseline for fatigue</h4>
<p>SSRIs are commonly prescribed for Long COVID fatigue, particularly fluvoxamine which had early trial interest.
Yet in this community, only {ssri_pos}/{ssri_total} SSRI users ({ssri_pos/ssri_total:.0%} if ssri_total > 0 else 0) report positive
outcomes for fatigue -- below the coin-flip baseline (95% CI: [{ssri_ci[0]:.0%}, {ssri_ci[1]:.0%}]).</p>
<p>Possible explanations: (1) SSRIs may help mood without helping fatigue, and users are evaluating fatigue specifically;
(2) SSRI side effects (drowsiness, sexual dysfunction) may offset mood benefits in patient perception;
(3) the community may have selection bias where SSRI non-responders are more vocal.
This does not mean SSRIs are ineffective -- it means the community's lived experience diverges from clinical recommendations.</p>
</div>
\"\"\"))

display(HTML(f\"\"\"
<div style="background: #fff3e0; padding: 15px; border-radius: 8px; border-left: 4px solid #ff5722; margin: 10px 0;">
<h4 style="margin-top:0;">Finding 2: Nicotine patches outperform most pharmaceuticals</h4>
<p>Nicotine is not a standard medical recommendation for Long COVID fatigue, yet it ranks among top performers
with {nic_pos}/{nic_total} users ({nic_pos/nic_total:.0%}) reporting positive outcomes
(95% CI: [{nic_ci[0]:.0%}, {nic_ci[1]:.0%}], binomial p={nic_binom.pvalue:.4f}).
The r/covidlonghaulers community has developed an informal nicotine patch protocol based on emerging research
about nicotinic acetylcholine receptor involvement in Long COVID. This is a community-driven intervention
that precedes formal clinical validation.</p>
</div>
\"\"\"))

display(HTML(f\"\"\"
<div style="background: #fff3e0; padding: 15px; border-radius: 8px; border-left: 4px solid #ff5722; margin: 10px 0;">
<h4 style="margin-top:0;">Finding 3: GLP-1 receptor agonists show modest results despite viral popularity</h4>
<p>GLP-1 receptor agonists (tirzepatide/Zepbound, semaglutide) received significant media attention for potential
Long COVID benefits. In this fatigue sample, {glp1_pos}/{glp1_total} users ({glp1_pos/glp1_total*100:.0f}%) report
positive outcomes. The wide confidence interval and small sample mean this is preliminary, but the hype-to-evidence
gap is worth noting -- the community's enthusiasm for GLP-1s may outpace the actual reported experience for
fatigue specifically.</p>
</div>
\"\"\"))
"""))

# ══════════════════════════════════════════════════════════════════════════════
# 6. QUALITATIVE EVIDENCE
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 6. What Patients Are Saying

Each quote below was selected because it contains a concrete treatment outcome relevant to fatigue. Quotes are limited to 1-2 sentences and include the post date for temporal context.
"""))

cells.append(("code", """
# Pull targeted quotes
import re

def clean_quote(text, max_len=250):
    text = text.strip()
    text = re.sub(r'\\s+', ' ', text)
    if len(text) > max_len:
        for end in ['. ', '! ', '? ']:
            last = text.rfind(end, 80, max_len)
            if last > 0:
                text = text[:last+1]
                break
        else:
            text = text[:max_len] + '...'
    return text

quote_queries = {
    "LDN reducing fatigue": (
        "SELECT body_text, datetime(post_date, 'unixepoch') as dt FROM posts "
        "WHERE (body_text LIKE '%ldn%' OR body_text LIKE '%naltrexone%') "
        "AND (body_text LIKE '%fatigue%' OR body_text LIKE '%energy%') "
        "AND LENGTH(body_text) BETWEEN 60 AND 400 ORDER BY RANDOM() LIMIT 5"),
    "Supplements helping energy": (
        "SELECT body_text, datetime(post_date, 'unixepoch') as dt FROM posts "
        "WHERE (body_text LIKE '%magnesium%' OR body_text LIKE '%coq10%' OR body_text LIKE '%creatine%') "
        "AND (body_text LIKE '%fatigue%' OR body_text LIKE '%energy%' OR body_text LIKE '%tired%') "
        "AND LENGTH(body_text) BETWEEN 60 AND 400 ORDER BY RANDOM() LIMIT 5"),
    "SSRI disappointment (contradicting main narrative)": (
        "SELECT body_text, datetime(post_date, 'unixepoch') as dt FROM posts "
        "WHERE (body_text LIKE '%ssri%' OR body_text LIKE '%sertraline%' OR body_text LIKE '%fluvoxamine%') "
        "AND (body_text LIKE '%fatigue%' OR body_text LIKE '%tired%' OR body_text LIKE '%worse%') "
        "AND LENGTH(body_text) BETWEEN 60 AND 400 ORDER BY RANDOM() LIMIT 5"),
    "Nicotine for Long COVID fatigue": (
        "SELECT body_text, datetime(post_date, 'unixepoch') as dt FROM posts "
        "WHERE body_text LIKE '%nicotine%' "
        "AND (body_text LIKE '%fatigue%' OR body_text LIKE '%energy%' OR body_text LIKE '%better%') "
        "AND LENGTH(body_text) BETWEEN 60 AND 400 ORDER BY RANDOM() LIMIT 5"),
}

html_parts = []
for category, query in quote_queries.items():
    quotes_df = pd.read_sql(query, conn)
    if len(quotes_df) > 0:
        html_parts.append(f"<h4>{category}</h4>")
        for _, row in quotes_df.head(2).iterrows():
            text = clean_quote(row['body_text'])
            html_parts.append(
                f'<blockquote style="border-left: 3px solid #ddd; padding: 8px 12px; margin: 8px 0; '
                f'color: #444; font-style: italic;">{text}<br>'
                f'<span style="font-size: 0.85em; color: #888;">'
                f'-- r/covidlonghaulers, {row["dt"][:10]}</span></blockquote>')
display(HTML("".join(html_parts)))
"""))

# ══════════════════════════════════════════════════════════════════════════════
# 7. RECOMMENDATIONS
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 7. Recommendations: Tiered by Evidence Strength

Based on the analysis above, treatments are classified into three evidence tiers. The baseline for statistical testing is the 50% null hypothesis (a treatment no better than chance).
"""))

cells.append(("code", """
# Tiered recommendations with NNT
baseline_rate = 0.50
rec_df = drug_stats.copy()
rec_df['nnt_val'] = rec_df['pos_rate'].apply(lambda r: nnt(r, baseline_rate))
rec_df['tier'] = rec_df.apply(lambda r:
    'Strong' if r['n_users'] >= 30 and r['binom_p'] < 0.05 else
    'Moderate' if r['n_users'] >= 15 or r['binom_p'] < 0.10 else
    'Preliminary', axis=1)

for tier, color, icon in [('Strong', '#27ae60', 'Strong Evidence'),
                           ('Moderate', '#f39c12', 'Moderate Evidence'),
                           ('Preliminary', '#3498db', 'Preliminary Evidence')]:
    tier_df = rec_df[rec_df['tier'] == tier].sort_values('pos_rate', ascending=False)
    if len(tier_df) == 0:
        continue
    rows_html = ""
    for _, r in tier_df.iterrows():
        nnt_str = f"{r['nnt_val']:.1f}" if r['nnt_val'] and r['nnt_val'] > 0 else "N/A"
        rows_html += (f"<tr><td style='padding: 4px 10px;'>{r['canonical_name']}</td>"
                      f"<td style='text-align:center; padding: 4px 10px;'>{int(r['n_users'])}</td>"
                      f"<td style='text-align:center; padding: 4px 10px;'>{r['pos_rate']:.0%}</td>"
                      f"<td style='text-align:center; padding: 4px 10px;'>[{r['ci_low']:.0%}, {r['ci_high']:.0%}]</td>"
                      f"<td style='text-align:center; padding: 4px 10px;'>{r['binom_p']:.4f}</td>"
                      f"<td style='text-align:center; padding: 4px 10px;'>{nnt_str}</td></tr>")
    display(HTML(f\"\"\"
    <div style="background: white; padding: 12px; border-radius: 8px; border-left: 4px solid {color}; margin: 10px 0;">
    <h4 style="margin-top:0; color: {color};">{icon} ({"n>=30, p<0.05" if tier == "Strong" else ("n>=15 or p<0.10" if tier == "Moderate" else "n<15")})</h4>
    <table style="border-collapse: collapse; width: 100%; font-size: 0.95em;">
    <tr style="border-bottom: 2px solid #ddd;">
        <th style="padding: 6px 10px; text-align:left;">Treatment</th>
        <th style="padding: 6px 10px; text-align:center;">Users</th>
        <th style="padding: 6px 10px; text-align:center;">Pos Rate</th>
        <th style="padding: 6px 10px; text-align:center;">95% CI</th>
        <th style="padding: 6px 10px; text-align:center;">p-value</th>
        <th style="padding: 6px 10px; text-align:center;">NNT vs 50%</th>
    </tr>
    {rows_html}
    </table>
    </div>
    \"\"\"))
"""))

cells.append(("code", """
# Chart 9: Diverging bar chart -- Top 15 recommendations
top15 = rec_df.sort_values('pos_rate', ascending=False).head(15).sort_values('pos_rate', ascending=True).copy()

fig, ax = plt.subplots(figsize=(11, 8))
top15['mixed_rate'] = top15['n_mixed'] / top15['n_users']
top15['neg_rate_calc'] = top15['n_negative'] / top15['n_users']

y = range(len(top15))
# Correct stacking: mixed innermost, negative outermost
ax.barh(y, -top15['mixed_rate'], left=0, color='#95a5a6', height=0.7, label='Mixed/Neutral')
ax.barh(y, -top15['neg_rate_calc'], left=-top15['mixed_rate'], color='#e74c3c', height=0.7, label='Negative')
ax.barh(y, top15['pos_rate'], left=0, color='#2ecc71', height=0.7, label='Positive')

for i, (_, row) in enumerate(top15.iterrows()):
    ci_lo, ci_hi = wilson_ci(int(row['n_positive']), int(row['n_users']))
    ax.errorbar(row['pos_rate'], i, xerr=[[row['pos_rate'] - ci_lo], [ci_hi - row['pos_rate']]],
                fmt='none', color='#333', capsize=3, linewidth=1)

ax.axvline(0, color='black', linewidth=0.8)
ax.set_yticks(list(y))
labels_div = []
for _, row in top15.iterrows():
    tier_icon = {'Strong': '[S]', 'Moderate': '[M]', 'Preliminary': '[P]'}.get(row['tier'], '')
    labels_div.append(f"{row['canonical_name']}  (n={int(row['n_users'])}) {tier_icon}")
ax.set_yticklabels(labels_div, fontsize=9)
ax.set_xlabel('Outcome Rate', fontsize=11)
ax.set_title('Top 15 Fatigue Treatments: Diverging Sentiment with CIs\\n[S]=Strong, [M]=Moderate, [P]=Preliminary evidence',
             fontsize=12, fontweight='bold', pad=12)
ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=9)
ax.set_xlim(-0.6, 1.1)
ax.grid(axis='x', alpha=0.3)
fig.tight_layout()
plt.show()
"""))

cells.append(("md", """**How to read this chart.** Each bar shows the full outcome distribution for a treatment. Green extends right from center (positive), grey extends left (mixed/neutral), and red extends furthest left (negative). Error bars show 95% Wilson confidence intervals. Tags indicate evidence tier: [S] = Strong (n>=30, p<0.05), [M] = Moderate (n>=15 or p<0.10), [P] = Preliminary (n<15).
"""))

# ── NNT chart ─────────────────────────────────────────────────────────────────
cells.append(("md", """### NNT: Number Needed to Treat

For patient-facing communication, NNT translates statistical differences into practical terms: how many people need to try this treatment for 1 additional person to report benefit beyond what we would see by chance. Lower NNT = more practically useful.
"""))

cells.append(("code", """
# Chart 10: NNT bar chart
nnt_df = rec_df[(rec_df['binom_p'] < 0.05) & (rec_df['nnt_val'].notna()) & (rec_df['nnt_val'] > 0)].copy()
nnt_df = nnt_df.sort_values('nnt_val', ascending=True).head(15)

if len(nnt_df) > 0:
    fig, ax = plt.subplots(figsize=(10, 6))
    colors_nnt = ['#27ae60' if n <= 3 else '#f39c12' if n <= 5 else '#e67e22' for n in nnt_df['nnt_val']]
    ax.barh(range(len(nnt_df)), nnt_df['nnt_val'], color=colors_nnt, height=0.65, edgecolor='white')
    ax.set_yticks(range(len(nnt_df)))
    ax.set_yticklabels([f"{row['canonical_name']}  ({row['pos_rate']:.0%} pos)" for _, row in nnt_df.iterrows()], fontsize=9)
    ax.set_xlabel('NNT (Number Needed to Treat vs. 50% baseline)', fontsize=11)
    ax.set_title('Practical Effectiveness: How Many Need to Try for 1 Extra Benefit?\\n(Lower = more effective, green = NNT <= 3)',
                 fontsize=12, fontweight='bold', pad=12)
    for i, (_, row) in enumerate(nnt_df.iterrows()):
        ax.text(row['nnt_val'] + 0.1, i, f"{row['nnt_val']:.1f}", va='center', fontsize=9)
    ax.grid(axis='x', alpha=0.3)
    fig.tight_layout()
    plt.show()
"""))

# ── Polypharmacy ──────────────────────────────────────────────────────────────
cells.append(("md", """## 8. Treatment Stacking: Does More Mean Better?

Many fatigue users try multiple treatments. Does polypharmacy (trying many treatments) correlate with better outcomes? This is an observational correlation, not a causal claim. Users who try more treatments may have more severe illness, more resources, or more time since onset.
"""))

cells.append(("code", """
# Polypharmacy analysis
poly_df = user_drug.groupby('user_id').agg(
    n_drugs=('canonical_name', 'nunique'),
    mean_score=('avg_score', 'mean'),
).reset_index()
poly_df['outcome'] = poly_df['mean_score'].apply(classify_outcome)
poly_df['tier'] = pd.cut(poly_df['n_drugs'], bins=[0, 1, 3, 6, 100],
                          labels=['1 treatment', '2-3 treatments', '4-6 treatments', '7+ treatments'])

rho, sp_p = sp_stats.spearmanr(poly_df['n_drugs'], poly_df['mean_score'])

tier_stats = poly_df.groupby('tier', observed=True).agg(
    n=('user_id', 'count'),
    mean_score=('mean_score', 'mean'),
    pos_rate=('outcome', lambda x: (x == 'positive').mean()),
).reset_index()

tier_table = ""
for _, row in tier_stats.iterrows():
    tier_table += (f"<tr><td style='padding: 4px 12px;'>{row['tier']}</td>"
                   f"<td style='text-align:center;'>{row['n']}</td>"
                   f"<td style='text-align:center;'>{row['mean_score']:.3f}</td>"
                   f"<td style='text-align:center;'>{row['pos_rate']:.0%}</td></tr>")

display(HTML(f\"\"\"
<div style="background: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 4px solid #9b59b6; margin: 10px 0;">
<h4 style="margin-top:0;">Polypharmacy and Outcome</h4>
<p><b>Spearman correlation:</b> rho = {rho:.3f}, p = {sp_p:.4f} -- {"significant" if sp_p < 0.05 else "not significant"}</p>
<table style="border-collapse: collapse; width: 70%;">
<tr style="border-bottom: 2px solid #ddd;">
  <th style="padding: 6px 12px; text-align:left;">Tier</th>
  <th style="padding: 6px 12px; text-align:center;">Users</th>
  <th style="padding: 6px 12px; text-align:center;">Mean Score</th>
  <th style="padding: 6px 12px; text-align:center;">Pos Rate</th>
</tr>
{tier_table}
</table>
</div>
\"\"\"))

# Chart 11: Dual-axis bar + line for polypharmacy
fig, ax1 = plt.subplots(figsize=(9, 5))
x = range(len(tier_stats))
ax1.bar(x, tier_stats['n'], color='#bdc3c7', alpha=0.6, label='Users (left axis)')
ax1.set_ylabel('Number of Users', fontsize=11, color='#666')
ax1.tick_params(axis='y', labelcolor='#666')

ax2 = ax1.twinx()
ax2.plot(list(x), tier_stats['pos_rate'].tolist(), 'o-', color='#2ecc71', linewidth=2.5, markersize=10, label='Positive Rate (right)')
ax2.set_ylabel('Positive Outcome Rate', fontsize=11, color='#2ecc71')
ax2.tick_params(axis='y', labelcolor='#2ecc71')
ax2.set_ylim(0, 1)

ax1.set_xticks(list(x))
ax1.set_xticklabels(tier_stats['tier'].tolist(), fontsize=10)
ax1.set_title(f'Treatment Count vs. Outcomes (Spearman rho={rho:.3f}, p={sp_p:.4f})',
              fontsize=12, fontweight='bold', pad=12)

lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=9)
fig.tight_layout()
plt.show()
"""))

cells.append(("md", """**Interpretation.** The relationship between number of treatments tried and outcomes reveals the polypharmacy pattern typical of chronic illness communities. Users trying more treatments may have worse baseline illness (driving them to try more things) or may benefit from eventually finding what works. The Spearman correlation quantifies this, but causation cannot be inferred.
"""))

# ══════════════════════════════════════════════════════════════════════════════
# 9. CONCLUSION
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 9. Conclusion

The Long COVID community's collective experience with fatigue treatments reveals a clear hierarchy, but one that diverges notably from standard clinical guidance.

**The community's top fatigue interventions are overwhelmingly nutritional supplements and lifestyle modifications.** Magnesium, electrolytes, CoQ10, creatine, B12, and vitamin D all show positive rates above 70%, with Wilson confidence intervals that clear the 50% baseline. These supplements share a common thread: they support mitochondrial function and energy metabolism, which aligns with emerging research on mitochondrial dysfunction in Long COVID. The co-occurrence heatmap confirms that the community has converged on an informal "mitochondrial support stack" combining several of these supplements simultaneously.

**Pharmaceutical interventions show a more mixed picture.** LDN (low dose naltrexone) stands out as the pharmaceutical with the strongest community endorsement (83% positive among fatigue users, n=92), outperforming most supplements in both sample size and consistency. Nicotine patches, a community-driven intervention based on nicotinic receptor research, also perform well. By contrast, SSRIs -- a standard clinical recommendation for post-viral fatigue -- perform below the 50% baseline in this community. This SSRI finding warrants particular attention: it may reflect the community's distinction between mood improvement and fatigue reduction, a nuance that clinical guidelines often blur.

**Based on this data, a patient asking about fatigue reduction in Long COVID should consider starting with a supplement foundation** (magnesium, CoQ10, electrolytes, creatine) and discussing LDN with their clinician as a pharmaceutical option with strong community evidence. SSRIs should be approached with the understanding that while they may help mood and sleep, the community does not report them as effective for fatigue specifically. Nicotine patches are worth discussing with a physician despite their unconventional status, given the community's positive experience and the emerging mechanistic rationale. PEM/ME-CFS patients should expect modestly lower response rates across all interventions and may benefit from closer monitoring and slower titration.
"""))

# ══════════════════════════════════════════════════════════════════════════════
# 10. LIMITATIONS
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 10. Research Limitations

**1. Selection bias.** Reddit users are not representative of all Long COVID patients. They skew younger, more tech-savvy, and more treatment-engaged than the general patient population. Patients who found effective treatments through conventional medicine may never post on Reddit.

**2. Reporting bias.** Users who experience dramatic improvement or dramatic failure are more likely to post than those with modest or no change. This inflates both tails of the sentiment distribution. Supplements may particularly benefit from this: a user who "feels more energy" after starting magnesium is motivated to share; one who notices nothing is not.

**3. Survivorship bias.** Users who gave up on treatment or became too ill to post are absent from this data. The community overrepresents people who are well enough to be active online, which biases all positive rates upward.

**4. Recall bias.** Treatment reports are retrospective self-assessments. Users reconstruct their experience from memory, which is colored by current health status, time elapsed, and social influence from other community members.

**5. Confounding.** Treatment choice is not randomized. Users who try magnesium differ systematically from users who try SSRIs -- in severity, comorbidities, treatment history, health literacy, and expectations. The logistic regression controls for some confounders but cannot eliminate them. The supplement advantage may partly reflect that supplement users have milder illness.

**6. No control group.** There is no untreated comparison group. The 50% baseline is a statistical null, not a placebo rate. In clinical trials, placebo response rates for subjective symptoms like fatigue can reach 30-40%, which would shift interpretation of all our positive rates.

**7. Sentiment vs. efficacy.** Positive sentiment is not the same as clinical efficacy. A user may report "positive" because the treatment was tolerable and they want to encourage others, not because it measurably reduced their fatigue. The text mining pipeline captures perception, not objective outcomes.

**8. Temporal snapshot.** This data covers one month (2026-03-11 to 2026-04-10). Treatment preferences evolve, new evidence emerges, and community consensus shifts. The GLP-1 agonist findings in particular may look different with a larger sample window, as community experience with these newer drugs is still developing.
"""))

# ══════════════════════════════════════════════════════════════════════════════
# DISCLAIMER
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("code", """
display(HTML(
    '<div style="margin-top: 30px; padding: 20px; background: #f8f8f8; border-radius: 8px; text-align: center;">'
    '<p style="font-size: 1.2em; font-weight: bold; font-style: italic; color: #333;">'
    'These findings reflect reporting patterns in online communities, '
    'not population-level treatment effects. This is not medical advice.'
    '</p></div>'
))
conn.close()
"""))

# ══════════════════════════════════════════════════════════════════════════════
# BUILD AND EXECUTE
# ══════════════════════════════════════════════════════════════════════════════
nb = build_notebook(cells=cells, db_path=DB)
html_path = execute_and_export(nb, OUT)
print(f"Done. HTML at: {html_path}")
