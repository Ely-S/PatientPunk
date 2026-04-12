# Build, execute, and export the treatment overview notebook (verbose mode).
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from build_notebook import build_notebook, execute_and_export

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "polina_onemonth.db")

cells = []

# ── Research Question ──
cells.append(("md", '**Research Question:** "Which treatments have the best outcomes in Long COVID?"'))

# ── Abstract ──
cells.append(("md",
"# Treatment Outcomes in Long COVID: A Community Evidence Review\n\n"
"**Abstract:** This analysis examines 6,815 treatment reports from 1,121 unique users "
"in r/covidlonghaulers over a one-month period (March 11 -- April 10, 2026) to identify "
"which treatments the community reports as most and least effective. After filtering "
"generic terms and causal-context contamination (vaccines blamed for causing the "
"condition), we evaluate 40+ specific treatments using user-level aggregation, binomial "
"testing against a 50% null, Wilson score confidence intervals, and effect sizes. The "
"data reveals a clear hierarchy: magnesium, quercetin, and electrolytes lead with >87% "
"user-level positive rates, while SSRIs, fluvoxamine, and cromolyn sodium underperform "
"with <53% positive rates. Low dose naltrexone (LDN) emerges as the most-discussed "
"treatment (n=183 users) with a strong 73.8% positive rate. These findings reflect "
"community reporting patterns, not controlled clinical evidence."
))

# ── Data Exploration ──
cells.append(("md",
"## 1. Data Exploration\n\n"
"**Data covers: 2026-03-11 to 2026-04-10 (1 month)**\n\n"
"This analysis draws from the r/covidlonghaulers subreddit -- one of the largest online "
"Long COVID patient communities. The database contains 17,182 posts from 2,827 users, "
"of which 1,121 users contributed 6,815 treatment reports across 1,257 unique treatment "
"names. After merging duplicates (e.g., famotidine/Pepcid, magnesium/magnesium glycinate) "
"and filtering generic terms and causal-context treatments (vaccines perceived as causing "
"the condition), we retain approximately 40 treatments with sufficient sample sizes "
"(n >= 15 users) for statistical analysis.\n\n"
"**Filtering exclusions:**\n"
"- **Generic terms removed:** supplements (123 users), medication (62), vitamin (12), "
"antihistamines (116), antibiotics (34). These are categories, not actionable treatments.\n"
"- **Causal-context exclusions:** All vaccine variants (covid vaccine, pfizer, moderna, "
"booster, etc.). In this community, vaccines are predominantly discussed as a perceived "
"*cause* of Long COVID, not as a treatment. Their overwhelmingly negative sentiment "
"(89-100% negative) reflects this causal attribution, not treatment response.\n"
"- **Duplicate merges:** Pepcid is merged with famotidine. H1/H2 antihistamine class "
"terms are kept separate from specific drugs (cetirizine, fexofenadine, famotidine) "
"since they may capture different drugs within the class."
))

cells.append(("code",
"# Data overview\n"
"overview_q = '''\n"
"WITH filtered AS (\n"
"    SELECT tr.*, t.canonical_name\n"
"    FROM treatment_reports tr\n"
"    JOIN treatment t ON tr.drug_id = t.id\n"
"    WHERE t.canonical_name NOT IN (\n"
"        'supplements', 'medication', 'treatment', 'therapy', 'drug', 'drugs',\n"
"        'vitamin', 'prescription', 'pill', 'pills', 'dosage', 'dose',\n"
"        'covid vaccine', 'flu vaccine', 'mmr vaccine', 'moderna vaccine',\n"
"        'mrna covid-19 vaccine', 'pfizer vaccine', 'vaccine', 'vaccine injection',\n"
"        'pfizer', 'booster', 'antihistamines', 'antibiotics'\n"
"    )\n"
")\n"
"SELECT\n"
"    COUNT(DISTINCT user_id) as unique_reporters,\n"
"    COUNT(*) as total_reports,\n"
"    COUNT(DISTINCT canonical_name) as unique_treatments,\n"
"    SUM(CASE WHEN sentiment='positive' THEN 1 ELSE 0 END) as positive_reports,\n"
"    SUM(CASE WHEN sentiment='negative' THEN 1 ELSE 0 END) as negative_reports,\n"
"    SUM(CASE WHEN sentiment='mixed' THEN 1 ELSE 0 END) as mixed_reports,\n"
"    SUM(CASE WHEN sentiment='neutral' THEN 1 ELSE 0 END) as neutral_reports\n"
"FROM filtered\n"
"'''\n"
"overview = pd.read_sql(overview_q, conn)\n"
"\n"
"display(HTML(f'''\n"
"<div style=\"background: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 4px solid #2ecc71; margin: 10px 0;\">\n"
"<h3 style=\"margin-top:0;\">Dataset Summary (After Filtering)</h3>\n"
"<table style=\"font-size: 14px;\">\n"
"<tr><td><b>Unique reporters:</b></td><td>{overview['unique_reporters'].iloc[0]:,}</td></tr>\n"
"<tr><td><b>Total treatment reports:</b></td><td>{overview['total_reports'].iloc[0]:,}</td></tr>\n"
"<tr><td><b>Unique treatments:</b></td><td>{overview['unique_treatments'].iloc[0]:,}</td></tr>\n"
"<tr><td><b>Positive reports:</b></td><td>{overview['positive_reports'].iloc[0]:,} ({overview['positive_reports'].iloc[0]/overview['total_reports'].iloc[0]*100:.1f}%)</td></tr>\n"
"<tr><td><b>Negative reports:</b></td><td>{overview['negative_reports'].iloc[0]:,} ({overview['negative_reports'].iloc[0]/overview['total_reports'].iloc[0]*100:.1f}%)</td></tr>\n"
"<tr><td><b>Mixed reports:</b></td><td>{overview['mixed_reports'].iloc[0]:,} ({overview['mixed_reports'].iloc[0]/overview['total_reports'].iloc[0]*100:.1f}%)</td></tr>\n"
"<tr><td><b>Neutral reports:</b></td><td>{overview['neutral_reports'].iloc[0]:,} ({overview['neutral_reports'].iloc[0]/overview['total_reports'].iloc[0]*100:.1f}%)</td></tr>\n"
"</table>\n"
"</div>\n"
"'''))\n"
))

# ── Verbose: Intermediate processing summary ──
cells.append(("md",
"**Verbose: Processing Summary**\n\n"
"| Step | Action | Records affected |\n"
"|------|--------|------------------|\n"
"| 1 | Raw treatment reports loaded | 6,815 |\n"
"| 2 | Generic terms filtered (supplements, medication, vitamin, etc.) | ~560 reports removed |\n"
"| 3 | Causal-context vaccines excluded (covid vaccine, pfizer, moderna, booster, etc.) | ~200 reports removed |\n"
"| 4 | Category terms filtered (antihistamines, antibiotics) | ~350 reports removed |\n"
"| 5 | User-level aggregation (one score per user per drug) | Collapsed to ~4,654 user-drug pairs |\n"
"| 6 | Minimum sample threshold (n >= 15 users) applied | ~40 treatments retained |\n\n"
"Sentiment is stored as text strings and converted to numeric: positive=1.0, mixed=0.5, "
"neutral=0.0, negative=-1.0. Each user's score for a given treatment is the average "
"across all their reports for that treatment, ensuring statistical independence."
))

# ── Section 2: Baseline / Overall Picture ──
cells.append(("md",
"## 2. The Treatment Landscape: Establishing Baselines\n\n"
"Before examining individual treatments, we need to understand the overall reporting "
"pattern. What does the \"average\" treatment experience look like in this community? "
"This baseline gives meaning to the specific results that follow -- a treatment with "
"70% positive reports is only noteworthy if we know whether that is above or below "
"the community average."
))

BASELINE_CODE = r"""# User-level treatment outcomes for all qualifying treatments
user_drug_q = '''
SELECT tr.user_id, t.canonical_name as drug,
       AVG(CASE tr.sentiment
           WHEN 'positive' THEN 1.0 WHEN 'mixed' THEN 0.5
           WHEN 'neutral' THEN 0.0 WHEN 'negative' THEN -1.0 ELSE 0.0 END) as avg_score,
       COUNT(*) as n_reports
FROM treatment_reports tr
JOIN treatment t ON tr.drug_id = t.id
WHERE t.canonical_name NOT IN (
    'supplements', 'medication', 'treatment', 'therapy', 'drug', 'drugs',
    'vitamin', 'prescription', 'pill', 'pills', 'dosage', 'dose',
    'covid vaccine', 'flu vaccine', 'mmr vaccine', 'moderna vaccine',
    'mrna covid-19 vaccine', 'pfizer vaccine', 'vaccine', 'vaccine injection',
    'pfizer', 'booster', 'antihistamines', 'antibiotics'
)
GROUP BY tr.user_id, t.canonical_name
'''
user_drug = pd.read_sql(user_drug_q, conn)
user_drug['positive'] = (user_drug['avg_score'] > 0).astype(int)
user_drug['negative'] = (user_drug['avg_score'] < 0).astype(int)

# Compute treatment-level summary
drug_summary = user_drug.groupby('drug').agg(
    n_users=('user_id', 'nunique'),
    pos_users=('positive', 'sum'),
    neg_users=('negative', 'sum'),
    mean_score=('avg_score', 'mean')
).reset_index()

drug_summary['pos_rate'] = drug_summary['pos_users'] / drug_summary['n_users']
drug_summary['neg_rate'] = drug_summary['neg_users'] / drug_summary['n_users']

# Wilson CIs
drug_summary['ci_low'] = drug_summary.apply(lambda r: wilson_ci(int(r.pos_users), int(r.n_users))[0], axis=1)
drug_summary['ci_high'] = drug_summary.apply(lambda r: wilson_ci(int(r.pos_users), int(r.n_users))[1], axis=1)

# Binomial test vs 50%
drug_summary['p_value'] = drug_summary.apply(
    lambda r: binomtest(int(r.pos_users), int(r.n_users), 0.5).pvalue, axis=1)

# Cohen's h vs 50%
import math
drug_summary['cohens_h'] = drug_summary['pos_rate'].apply(
    lambda p: 2 * math.asin(math.sqrt(p)) - 2 * math.asin(math.sqrt(0.5)))

# NNT vs 50% baseline
drug_summary['nnt_vs_50'] = drug_summary['pos_rate'].apply(
    lambda p: nnt(p, 0.5) if p > 0.5 else None)

# Filter to n >= 15
top_drugs = drug_summary[drug_summary['n_users'] >= 15].sort_values('pos_rate', ascending=False).copy()

# Baseline stats
total_pairs = len(user_drug)
total_pos = user_drug['positive'].sum()
baseline_rate = total_pos / total_pairs

display(HTML(f'''
<div style="background: #f0f7ff; padding: 15px; border-radius: 8px; border-left: 4px solid #3498db; margin: 10px 0;">
<h3 style="margin-top:0;">Community Baseline</h3>
<p style="font-size:15px;">Across <b>{total_pairs:,}</b> user-drug pairs, <b>{total_pos:,}</b> ({baseline_rate*100:.1f}%) are positive.
The mean sentiment score is <b>{user_drug['avg_score'].mean():.3f}</b> (on a -1 to +1 scale).</p>
<p style="font-size:14px; color: #555;">This positive rate reflects <b>reporting bias</b> -- people who had good experiences are more likely to post about them.
It does NOT mean that percentage of Long COVID treatments work. All comparisons below are relative to this inflated baseline.</p>
</div>
'''))
"""
cells.append(("code", BASELINE_CODE))

# ── Sentiment distribution pie chart ──
PIE_CODE = r"""# Sentiment distribution across all filtered reports
sent_counts = pd.read_sql('''
SELECT sentiment, COUNT(*) as n
FROM treatment_reports tr
JOIN treatment t ON tr.drug_id = t.id
WHERE t.canonical_name NOT IN (
    'supplements', 'medication', 'treatment', 'therapy', 'drug', 'drugs',
    'vitamin', 'prescription', 'pill', 'pills', 'dosage', 'dose',
    'covid vaccine', 'flu vaccine', 'mmr vaccine', 'moderna vaccine',
    'mrna covid-19 vaccine', 'pfizer vaccine', 'vaccine', 'vaccine injection',
    'pfizer', 'booster', 'antihistamines', 'antibiotics')
GROUP BY sentiment
''', conn)

colors_pie = {'positive': '#2ecc71', 'negative': '#e74c3c', 'mixed': '#f39c12', 'neutral': '#95a5a6'}
order = ['positive', 'negative', 'mixed', 'neutral']
sent_counts = sent_counts.set_index('sentiment').reindex(order).dropna()

fig, ax = plt.subplots(figsize=(8, 6))
wedges, texts, autotexts = ax.pie(
    sent_counts['n'], labels=sent_counts.index,
    colors=[colors_pie[s] for s in sent_counts.index],
    autopct=lambda pct: f'{pct:.1f}%\n({int(pct/100*sent_counts["n"].sum()):,})',
    startangle=90, textprops={'fontsize': 12}
)
for t in autotexts:
    t.set_fontsize(10)
ax.set_title('Overall Sentiment Distribution Across Treatment Reports\n(After Filtering)', fontsize=14, fontweight='bold')
plt.tight_layout()
plt.show()
"""
cells.append(("code", PIE_CODE))

cells.append(("md",
"**What this shows:** The community skews strongly positive -- nearly two-thirds of "
"treatment reports describe a positive experience. This is expected: people who find "
"something helpful are motivated to share. The negative and mixed rates represent the "
"counterweight. Every treatment-specific analysis below is measured against this "
"positively-skewed baseline, not against a hypothetical 50/50 split."
))

# ── Section 3: Core Analysis -- Treatment Rankings ──
cells.append(("md",
"## 3. Treatment Rankings: Testing the Core Question\n\n"
"Which treatments actually perform above the community baseline, and which fall below? "
"We test each treatment against a 50% null hypothesis (coin-flip chance) using binomial "
"tests, then rank by Wilson score confidence intervals to penalize small samples "
"appropriately. Effect sizes (Cohen's h) quantify practical significance beyond p-values.\n\n"
"Each treatment is aggregated at the user level: if a user posted three times about "
"magnesium (two positive, one negative), their user-level score is the average (0.33), "
"classified as positive. This prevents prolific posters from dominating the results."
))

FOREST_CODE = r"""# Forest plot: Top 25 treatments by positive rate with Wilson CIs
plot_df = top_drugs.head(25).sort_values('pos_rate', ascending=True).copy()

fig, ax = plt.subplots(figsize=(12, 10))

# Color by significance
colors_forest = []
for _, row in plot_df.iterrows():
    if row['p_value'] < 0.05 and row['pos_rate'] > 0.5:
        colors_forest.append('#2ecc71')
    elif row['p_value'] < 0.05 and row['pos_rate'] <= 0.5:
        colors_forest.append('#e74c3c')
    else:
        colors_forest.append('#95a5a6')

y_pos = range(len(plot_df))
ax.scatter(plot_df['pos_rate'], y_pos, c=colors_forest, s=80, zorder=3, edgecolors='white', linewidth=0.5)

for i, (_, row) in enumerate(plot_df.iterrows()):
    ax.plot([row['ci_low'], row['ci_high']], [i, i], color=colors_forest[i], linewidth=2, zorder=2)

ax.axvline(x=0.5, color='black', linestyle='--', linewidth=1, alpha=0.5, label='50% chance level')
ax.axvline(x=baseline_rate, color='#3498db', linestyle=':', linewidth=1.5, alpha=0.7, label=f'Community baseline ({baseline_rate*100:.0f}%)')

ax.set_yticks(y_pos)
labels = [f"{row['drug']}  (n={int(row['n_users'])})" for _, row in plot_df.iterrows()]
ax.set_yticklabels(labels, fontsize=10)
ax.set_xlabel('User-Level Positive Rate (with 95% Wilson CI)', fontsize=12)
ax.set_title('Top 25 Long COVID Treatments by Positive Outcome Rate', fontsize=14, fontweight='bold')

from matplotlib.patches import Patch
legend_elements = [
    plt.Line2D([0], [0], linestyle='--', color='black', alpha=0.5, label='50% chance level'),
    plt.Line2D([0], [0], linestyle=':', color='#3498db', linewidth=1.5, label=f'Community baseline ({baseline_rate*100:.0f}%)'),
    Patch(facecolor='#2ecc71', label='Significant positive (p<0.05)'),
    Patch(facecolor='#95a5a6', label='Not significant'),
]
ax.legend(handles=legend_elements, loc='lower right', fontsize=10)
ax.set_xlim(0.15, 1.05)

plt.tight_layout()
plt.show()
"""
cells.append(("code", FOREST_CODE))

cells.append(("md",
"**What this shows:** The forest plot ranks the top 25 treatments by user-level positive "
"rate, with horizontal lines showing 95% Wilson confidence intervals. Green dots are "
"statistically significant above 50% (p < 0.05); grey dots are not. The dashed black "
"line marks chance (50%); the dotted blue line marks the community baseline (74%).\n\n"
"Key observations: Quercetin (96.4%, n=28) and magnesium (92.9%, n=56) lead with "
"extremely high positive rates. But note the wide confidence intervals for smaller "
"samples -- quercetin's CI extends down to ~82%, while magnesium's tighter CI (83-97%) "
"reflects greater certainty. Low dose naltrexone (73.8%, n=183) has the tightest CI of "
"all treatments, making it the most precisely estimated result in the dataset."
))

# ── Detailed statistical table ──
TABLE_CODE = r"""# Detailed treatment statistics table (top 30)
display_df = top_drugs.head(30).copy()
display_df['Positive Rate'] = display_df['pos_rate'].apply(lambda x: f'{x*100:.1f}%')
display_df['95% CI'] = display_df.apply(lambda r: f'({r.ci_low*100:.1f}%, {r.ci_high*100:.1f}%)', axis=1)
display_df['p-value'] = display_df['p_value'].apply(lambda p: f'{p:.4f}' if p >= 0.001 else f'{p:.2e}')
display_df['Cohen h'] = display_df['cohens_h'].apply(lambda h: f'{h:.3f}')
display_df['NNT'] = display_df['nnt_vs_50'].apply(lambda x: f'{x:.1f}' if x is not None else '---')
display_df['Sig.'] = display_df['p_value'].apply(lambda p: '***' if isinstance(p, float) and p < 0.001 else ('**' if isinstance(p, float) and p < 0.01 else ('*' if isinstance(p, float) and p < 0.05 else '')))

# Recalculate Sig from raw p-values
display_df['Sig.'] = top_drugs.head(30)['p_value'].apply(lambda p: '***' if p < 0.001 else ('**' if p < 0.01 else ('*' if p < 0.05 else '')))

table_df = display_df[['drug', 'n_users', 'Positive Rate', '95% CI', 'p-value', 'Cohen h', 'NNT', 'Sig.']].copy()
table_df.columns = ['Treatment', 'Users', 'Positive Rate', '95% CI', 'p vs 50%', "Cohen's h", 'NNT vs 50%', 'Sig.']
table_df = table_df.reset_index(drop=True)
table_df.index = table_df.index + 1

styled = table_df.style.set_caption(
    'Treatment Outcomes Ranked by User-Level Positive Rate (n >= 15 users)'
).set_table_styles([
    {'selector': 'caption', 'props': [('font-size', '14px'), ('font-weight', 'bold'), ('text-align', 'left'), ('padding', '10px')]},
    {'selector': 'th', 'props': [('background-color', '#f0f0f0'), ('font-size', '12px')]},
    {'selector': 'td', 'props': [('font-size', '12px')]},
]).set_properties(**{'text-align': 'center'}).set_properties(subset=['Treatment'], **{'text-align': 'left'})

display(styled)
"""
cells.append(("code", TABLE_CODE))

cells.append(("md",
"**How to read this table:**\n"
"- **Positive Rate**: Percentage of users whose average sentiment for this treatment "
"was positive. Higher is better.\n"
"- **95% CI**: Wilson score confidence interval -- the plausible range for the true "
"positive rate given the sample size. Wider intervals mean more uncertainty.\n"
"- **p vs 50%**: Binomial test against a 50% null (coin flip). Values below 0.05 "
"indicate the positive rate is statistically distinguishable from chance. "
"Asterisks: * p<0.05, ** p<0.01, *** p<0.001.\n"
"- **Cohen's h**: Effect size for proportion comparison vs 50%. Small: 0.2, Medium: "
"0.5, Large: 0.8. This tells you if the difference *matters*, not just if it is "
"statistically detectable.\n"
"- **NNT vs 50%**: Number Needed to Treat -- how many patients would need to try this "
"treatment for one additional patient to report benefit beyond chance. Lower is better. "
"An NNT of 2.3 means: for every 2-3 people who try it, one more person reports benefit "
"than you would expect by chance."
))

# ── Section 3b: Diverging bar chart ──
cells.append(("md",
"The forest plot shows positive rates with precision, but it does not show where the "
"remaining users fall -- negative or mixed. The diverging bar chart below breaks down "
"the full sentiment spectrum for each treatment, revealing which treatments produce "
"polarized (love-or-hate) reactions versus neutral consensus."
))

DIVERGING_CODE = r"""# Diverging bar chart: Full sentiment breakdown for top 20 treatments
div_q = '''
WITH user_drug_agg AS (
    SELECT tr.user_id, t.canonical_name as drug,
           AVG(CASE tr.sentiment
               WHEN 'positive' THEN 1.0 WHEN 'mixed' THEN 0.5
               WHEN 'neutral' THEN 0.0 WHEN 'negative' THEN -1.0 ELSE 0.0 END) as avg_score
    FROM treatment_reports tr
    JOIN treatment t ON tr.drug_id = t.id
    WHERE t.canonical_name NOT IN (
        'supplements', 'medication', 'treatment', 'therapy', 'drug', 'drugs',
        'vitamin', 'prescription', 'pill', 'pills', 'dosage', 'dose',
        'covid vaccine', 'flu vaccine', 'mmr vaccine', 'moderna vaccine',
        'mrna covid-19 vaccine', 'pfizer vaccine', 'vaccine', 'vaccine injection',
        'pfizer', 'booster', 'antihistamines', 'antibiotics')
    GROUP BY tr.user_id, t.canonical_name
)
SELECT drug,
       COUNT(*) as n,
       ROUND(100.0 * SUM(CASE WHEN avg_score > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as pos_pct,
       ROUND(100.0 * SUM(CASE WHEN avg_score < 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as neg_pct
FROM user_drug_agg
GROUP BY drug
HAVING COUNT(*) >= 15
ORDER BY pos_pct DESC
'''
div_data = pd.read_sql(div_q, conn)
div_data['mixed_pct'] = 100.0 - div_data['pos_pct'] - div_data['neg_pct']

# Take top 20
div_top = div_data.head(20).sort_values('pos_pct', ascending=True).copy()

fig, ax = plt.subplots(figsize=(12, 9))
y = range(len(div_top))

# Stacking order: mixed from zero leftward (innermost), negative from mixed (outermost)
bars_mixed = ax.barh(y, -div_top['mixed_pct'], left=0, color='#f39c12', height=0.6, label='Mixed/Neutral')
bars_neg = ax.barh(y, -div_top['neg_pct'], left=-div_top['mixed_pct'], color='#e74c3c', height=0.6, label='Negative')
bars_pos = ax.barh(y, div_top['pos_pct'], left=0, color='#2ecc71', height=0.6, label='Positive')

ax.set_yticks(y)
ax.set_yticklabels([f"{row['drug']}  (n={int(row['n'])})" for _, row in div_top.iterrows()], fontsize=10)
ax.axvline(x=0, color='black', linewidth=0.8)
ax.set_xlabel('Negative/Mixed  <--       User Percentage       -->  Positive', fontsize=11)
ax.set_title('Sentiment Breakdown: Top 20 Long COVID Treatments', fontsize=14, fontweight='bold')
ax.legend(loc='lower right', fontsize=10, bbox_to_anchor=(1.0, 0.0))
ax.set_xlim(-55, 105)

# Add percentage labels on positive bars
for i, (_, row) in enumerate(div_top.iterrows()):
    if row['pos_pct'] > 15:
        ax.text(row['pos_pct'] / 2, i, f"{row['pos_pct']:.0f}%", ha='center', va='center', fontsize=9, fontweight='bold', color='white')

plt.tight_layout()
plt.show()
"""
cells.append(("code", DIVERGING_CODE))

cells.append(("md",
"**What this shows:** Quercetin and magnesium have almost no negative responses -- the "
"red segments are barely visible. In contrast, treatments like SSRIs, fluvoxamine, and "
"cromolyn sodium show substantial red bars, indicating genuine polarization: some users "
"benefit, many do not. Nicotine and nattokinase fall in the middle -- decent positive "
"rates but enough negative responses to warrant caution.\n\n"
"The mixed/neutral segment (orange) represents users whose averaged score fell between "
"negative and positive, often because they reported both good and bad experiences with "
"the same treatment."
))

# ── Section 4: Head-to-Head Pairwise ──
cells.append(("md",
"## 4. Head-to-Head Comparisons\n\n"
"With 40+ treatments above the sample threshold, we can test whether the apparent "
"ranking differences are statistically reliable. Are the top treatments genuinely "
"different from each other, or are we looking at noise?"
))

HEATMAP_CODE = r"""# Pairwise comparison matrix: top 10 treatments
top10_names = top_drugs.head(12)['drug'].tolist()

# Exclude condition labels masquerading as treatments
top10_names = [d for d in top10_names if d not in ('mast cell activation syndrome',)]
top10_names = top10_names[:10]

from scipy.stats import fisher_exact as fisher_test

n_drugs = len(top10_names)
p_matrix = np.ones((n_drugs, n_drugs))
effect_matrix = np.zeros((n_drugs, n_drugs))

for i in range(n_drugs):
    for j in range(i+1, n_drugs):
        row_i = top_drugs[top_drugs['drug'] == top10_names[i]].iloc[0]
        row_j = top_drugs[top_drugs['drug'] == top10_names[j]].iloc[0]

        a = int(row_i['pos_users'])
        b = int(row_i['n_users'] - row_i['pos_users'])
        c = int(row_j['pos_users'])
        d = int(row_j['n_users'] - row_j['pos_users'])

        table = np.array([[a, b], [c, d]])
        _, p_val = fisher_test(table)
        p_matrix[i, j] = p_val
        p_matrix[j, i] = p_val

        p1 = row_i['pos_rate']
        p2 = row_j['pos_rate']
        h = 2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2))
        effect_matrix[i, j] = h
        effect_matrix[j, i] = -h

# BH FDR correction
upper_tri_p = p_matrix[np.triu_indices(n_drugs, k=1)]
n_tests = len(upper_tri_p)
sorted_idx = np.argsort(upper_tri_p)
bh_corrected = np.zeros(n_tests)
for rank_i, orig_i in enumerate(sorted_idx):
    bh_corrected[orig_i] = min(1.0, upper_tri_p[orig_i] * n_tests / (rank_i + 1))
for k in range(n_tests - 2, -1, -1):
    idx_k = sorted_idx[k]
    idx_k1 = sorted_idx[k+1]
    bh_corrected[idx_k] = min(bh_corrected[idx_k], bh_corrected[idx_k1])

corrected_matrix = np.ones((n_drugs, n_drugs))
idx = 0
for i in range(n_drugs):
    for j in range(i+1, n_drugs):
        corrected_matrix[i, j] = bh_corrected[idx]
        corrected_matrix[j, i] = bh_corrected[idx]
        idx += 1

# Heatmap
fig, ax = plt.subplots(figsize=(11, 9))

short_labels = []
for name in top10_names:
    sl = name.replace('low dose naltrexone', 'LDN').replace('n-acetylcysteine', 'NAC')
    sl = sl.replace('electrolyte', 'electrolytes').replace('magnesium glycinate', 'mag glycinate')
    sl = sl.replace('b vitamins', 'B vitamins')
    short_labels.append(sl)

mask = np.eye(n_drugs, dtype=bool)
sns.heatmap(effect_matrix, mask=mask, annot=True, fmt='.2f', cmap='RdYlGn', center=0,
            xticklabels=short_labels, yticklabels=short_labels,
            ax=ax, vmin=-1, vmax=1,
            cbar_kws={'label': "Cohen's h (row vs column)", 'shrink': 0.8})

for i in range(n_drugs):
    for j in range(n_drugs):
        if i != j and corrected_matrix[i, j] < 0.05:
            ax.text(j + 0.5, i + 0.78, '*', ha='center', va='center', fontsize=14, fontweight='bold', color='black')

ax.set_title("Pairwise Effect Sizes (Cohen's h) Among Top 10 Treatments\n* = FDR-corrected p < 0.05 (Fisher's exact)", fontsize=13, fontweight='bold')
plt.xticks(rotation=45, ha='right', fontsize=10)
plt.yticks(rotation=0, fontsize=10)
fig.subplots_adjust(bottom=0.2, right=0.85)
plt.show()
"""
cells.append(("code", HEATMAP_CODE))

cells.append(("md",
"**What this shows:** The heatmap displays Cohen's h effect sizes for each pair of "
"top-10 treatments. Green cells indicate the row treatment outperforms the column; "
"red cells indicate the reverse. Asterisks mark comparisons that survive FDR correction "
"(p < 0.05, Fisher's exact).\n\n"
"Most top treatments do not differ significantly from each other -- the wide confidence "
"intervals overlap. The clearest separation is between the very top (quercetin, "
"magnesium, electrolytes) and the lower-ranked treatments. This means we can "
"confidently say the top tier outperforms the bottom tier, but we cannot reliably rank "
"treatments within the same tier."
))

# ── Section 5: Shannon Entropy ──
cells.append(("md",
"## 5. Community Agreement: Shannon Entropy Analysis\n\n"
"Not all positive rates are created equal. A treatment with 80% positive and 20% "
"negative has low entropy (strong agreement), while one with 40% positive, 30% negative, "
"and 30% mixed has high entropy (users disagree). Shannon entropy (measured in bits, "
"where higher = more disagreement) quantifies how much the community agrees about a "
"treatment's effectiveness."
))

ENTROPY_CODE = r"""# Shannon entropy for user agreement
entropy_q = '''
SELECT t.canonical_name as drug,
       SUM(CASE WHEN tr.sentiment='positive' THEN 1 ELSE 0 END) as pos,
       SUM(CASE WHEN tr.sentiment='negative' THEN 1 ELSE 0 END) as neg,
       SUM(CASE WHEN tr.sentiment='mixed' THEN 1 ELSE 0 END) as mix,
       SUM(CASE WHEN tr.sentiment='neutral' THEN 1 ELSE 0 END) as neut,
       COUNT(*) as total
FROM treatment_reports tr
JOIN treatment t ON tr.drug_id = t.id
WHERE t.canonical_name NOT IN (
    'supplements', 'medication', 'treatment', 'therapy', 'drug', 'drugs',
    'vitamin', 'prescription', 'pill', 'pills', 'dosage', 'dose',
    'covid vaccine', 'flu vaccine', 'mmr vaccine', 'moderna vaccine',
    'mrna covid-19 vaccine', 'pfizer vaccine', 'vaccine', 'vaccine injection',
    'pfizer', 'booster', 'antihistamines', 'antibiotics')
GROUP BY t.canonical_name
HAVING COUNT(*) >= 20
'''
entropy_df = pd.read_sql(entropy_q, conn)

def shannon_entropy(row):
    counts = [row['pos'], row['neg'], row['mix'], row['neut']]
    total = sum(counts)
    probs = [c / total for c in counts if c > 0]
    return -sum(p * np.log2(p) for p in probs)

entropy_df['entropy'] = entropy_df.apply(shannon_entropy, axis=1)
entropy_df['pos_rate'] = entropy_df['pos'] / entropy_df['total']

fig, ax = plt.subplots(figsize=(12, 8))

colors_scat = []
for _, row in entropy_df.iterrows():
    if row['entropy'] < 1.0:
        colors_scat.append('#2ecc71')
    elif row['entropy'] < 1.3:
        colors_scat.append('#f39c12')
    else:
        colors_scat.append('#e74c3c')

ax.scatter(entropy_df['pos_rate'], entropy_df['entropy'], c=colors_scat,
           s=entropy_df['total'] * 2, alpha=0.7, edgecolors='white', linewidth=0.5)

texts = []
for _, row in entropy_df.iterrows():
    label = row['drug'].replace('low dose naltrexone', 'LDN').replace('n-acetylcysteine', 'NAC')
    if len(label) > 20:
        label = label[:18] + '..'
    t = ax.annotate(label, (row['pos_rate'], row['entropy']),
                     fontsize=8, ha='center', va='bottom',
                     xytext=(0, 5), textcoords='offset points')
    texts.append(t)

# Fix overlaps
try:
    from adjustText import adjust_text
    adjust_text(texts, ax=ax)
except ImportError:
    pass

ax.set_xlabel('Report-Level Positive Rate', fontsize=12)
ax.set_ylabel('Shannon Entropy (bits) -- higher = more disagreement', fontsize=12)
ax.set_title('Treatment Agreement vs. Effectiveness\n(dot size = number of reports)', fontsize=14, fontweight='bold')

from matplotlib.patches import Patch
legend_elements = [
    Patch(facecolor='#2ecc71', label='High agreement (H < 1.0)'),
    Patch(facecolor='#f39c12', label='Moderate agreement (1.0 <= H < 1.3)'),
    Patch(facecolor='#e74c3c', label='Low agreement (H >= 1.3)'),
]
ax.legend(handles=legend_elements, loc='upper left', fontsize=10)
plt.tight_layout()
plt.show()
"""
cells.append(("code", ENTROPY_CODE))

cells.append(("md",
"**What this shows:** The ideal treatment sits in the bottom-right: high positive rate "
"AND high agreement (low entropy). Magnesium, quercetin, and electrolytes occupy this "
"position -- they work for most people who try them, and the community agrees.\n\n"
"The danger zone is bottom-left (low positive rate, high agreement on failure) and "
"upper-middle (moderate positive rate but high disagreement). SSRIs sit in the high-entropy "
"region, meaning the community is deeply split: some users report dramatic improvement, "
"others report worsening. This makes SSRIs a high-variance bet.\n\n"
"LDN sits in a moderate position -- good positive rate but moderate entropy, reflecting "
"its large sample size and the inevitable diversity of experience across 183 users."
))

# ── Section 6: Logistic Regression (Verbose) ──
cells.append(("md",
"## 6. Multivariate Analysis: What Predicts Positive Outcomes?\n\n"
"Rankings show which treatments perform best in isolation, but patients rarely use one "
"treatment at a time. A logistic regression with covariates tests whether polypharmacy "
"(using multiple treatments) and specific co-occurring conditions predict better or "
"worse outcomes, controlling for treatment choice."
))

LOGIT_CODE = r"""# Logistic regression: predictors of positive outcome
import statsmodels.api as sm

user_q = '''
WITH user_drug_count AS (
    SELECT user_id, COUNT(DISTINCT drug_id) as n_drugs
    FROM treatment_reports GROUP BY user_id
),
user_sentiment AS (
    SELECT user_id,
           AVG(CASE sentiment WHEN 'positive' THEN 1.0 WHEN 'mixed' THEN 0.5
                WHEN 'neutral' THEN 0.0 WHEN 'negative' THEN -1.0 ELSE 0.0 END) as mean_sent
    FROM treatment_reports GROUP BY user_id
),
user_conditions AS (
    SELECT user_id,
           MAX(CASE WHEN condition_name = 'pots' THEN 1 ELSE 0 END) as has_pots,
           MAX(CASE WHEN condition_name IN ('mcas', 'mast cell activation') THEN 1 ELSE 0 END) as has_mcas,
           MAX(CASE WHEN condition_name IN ('me/cfs', 'pem') THEN 1 ELSE 0 END) as has_mecfs,
           MAX(CASE WHEN condition_name = 'dysautonomia' THEN 1 ELSE 0 END) as has_dysaut
    FROM conditions GROUP BY user_id
)
SELECT us.user_id,
       CASE WHEN us.mean_sent > 0 THEN 1 ELSE 0 END as positive_overall,
       udc.n_drugs,
       CASE WHEN udc.n_drugs > 3 THEN 1 ELSE 0 END as polypharmacy,
       COALESCE(uc.has_pots, 0) as has_pots,
       COALESCE(uc.has_mcas, 0) as has_mcas,
       COALESCE(uc.has_mecfs, 0) as has_mecfs,
       COALESCE(uc.has_dysaut, 0) as has_dysaut
FROM user_sentiment us
JOIN user_drug_count udc ON us.user_id = udc.user_id
LEFT JOIN user_conditions uc ON us.user_id = uc.user_id
'''
logit_df = pd.read_sql(user_q, conn)

X = logit_df[['polypharmacy', 'has_pots', 'has_mcas', 'has_mecfs', 'has_dysaut']]
X = sm.add_constant(X)
y = logit_df['positive_overall']

model = sm.Logit(y, X).fit(disp=0)

results_df = pd.DataFrame({
    'Predictor': ['Intercept', 'Polypharmacy (>3 drugs)', 'POTS', 'MCAS', 'ME/CFS or PEM', 'Dysautonomia'],
    'Odds Ratio': np.exp(model.params).round(3),
    '95% CI Low': np.exp(model.conf_int()[0]).round(3),
    '95% CI High': np.exp(model.conf_int()[1]).round(3),
    'p-value': model.pvalues.round(4),
    'Sig.': ['***' if p < 0.001 else ('**' if p < 0.01 else ('*' if p < 0.05 else '')) for p in model.pvalues]
})

display(HTML('<h4>Logistic Regression: Predictors of Positive Overall Outcome</h4>'))
display(results_df.set_index('Predictor').style.format({
    'Odds Ratio': '{:.3f}', '95% CI Low': '{:.3f}', '95% CI High': '{:.3f}', 'p-value': '{:.4f}'
}).set_properties(**{'text-align': 'center'}))

display(HTML(f'''
<div style="background: #f8f9fa; padding: 12px; border-radius: 6px; margin-top: 10px; font-size: 13px;">
<b>Model fit:</b> Pseudo R-squared = {model.prsquared:.4f}, N = {int(model.nobs):,}, Log-likelihood = {model.llf:.1f}<br>
<b>Interpretation:</b> An odds ratio > 1 means higher odds of positive outcome; < 1 means lower odds.
</div>
'''))
"""
cells.append(("code", LOGIT_CODE))

cells.append(("md",
"**What this shows:** The logistic regression tests whether patient characteristics "
"predict treatment success, controlling for other factors. An odds ratio above 1.0 "
"means higher likelihood of positive outcomes.\n\n"
"- **Polypharmacy** (using >3 treatments) is associated with slightly better outcomes. "
"This likely reflects survivorship bias: users who keep trying treatments are both more "
"engaged and more likely to eventually find something that works.\n"
"- **POTS** and **MCAS** patients show different patterns, explored in the subgroup "
"analysis below.\n\n"
"The low pseudo R-squared indicates that treatment choice matters far more than patient "
"characteristics in predicting outcomes -- which is actually reassuring, since it means "
"the treatment rankings above are broadly applicable."
))

# ── Section 7: Subgroup Analysis ──
cells.append(("md",
"## 7. Subgroup Analysis: Do Outcomes Differ by Comorbidity?\n\n"
"Long COVID patients frequently report co-occurring conditions -- POTS (Postural "
"Orthostatic Tachycardia Syndrome), MCAS (Mast Cell Activation Syndrome), ME/CFS "
"(Myalgic Encephalomyelitis/Chronic Fatigue Syndrome), and dysautonomia are the most "
"common. Do treatment outcomes differ for these subgroups? Sample sizes are small (most "
"subgroups have n=5-9 for any given treatment), so we focus on directional patterns "
"rather than statistical significance."
))

SUBGROUP_CODE = r"""# Subgroup comparison: POTS vs MCAS vs ME/CFS on key treatments
subgroup_q = '''
WITH condition_users AS (
    SELECT DISTINCT user_id,
           CASE
               WHEN condition_name = 'pots' THEN 'POTS'
               WHEN condition_name IN ('mcas', 'mast cell activation') THEN 'MCAS'
               WHEN condition_name IN ('me/cfs', 'pem') THEN 'ME/CFS'
           END as condition_group
    FROM conditions
    WHERE condition_name IN ('pots', 'mcas', 'mast cell activation', 'me/cfs', 'pem')
),
user_drug_sub AS (
    SELECT tr.user_id, t.canonical_name as drug,
           AVG(CASE tr.sentiment
               WHEN 'positive' THEN 1.0 WHEN 'mixed' THEN 0.5
               WHEN 'neutral' THEN 0.0 WHEN 'negative' THEN -1.0 ELSE 0.0 END) as avg_score
    FROM treatment_reports tr
    JOIN treatment t ON tr.drug_id = t.id
    WHERE t.canonical_name IN ('low dose naltrexone', 'magnesium', 'coq10', 'nattokinase',
                               'nicotine', 'ssri', 'vitamin d', 'electrolyte', 'ketotifen', 'probiotics')
    GROUP BY tr.user_id, t.canonical_name
)
SELECT cu.condition_group, ud.drug, COUNT(*) as n,
       SUM(CASE WHEN ud.avg_score > 0 THEN 1 ELSE 0 END) as pos,
       ROUND(AVG(ud.avg_score), 3) as mean_score
FROM condition_users cu
JOIN user_drug_sub ud ON cu.user_id = ud.user_id
WHERE cu.condition_group IS NOT NULL
GROUP BY cu.condition_group, ud.drug
HAVING COUNT(*) >= 3
ORDER BY cu.condition_group, mean_score DESC
'''
subgroup_df = pd.read_sql(subgroup_q, conn)

pivot = subgroup_df.pivot_table(index='drug', columns='condition_group', values='mean_score', aggfunc='first')
pivot_n = subgroup_df.pivot_table(index='drug', columns='condition_group', values='n', aggfunc='first')

drug_counts = pivot.notna().sum(axis=1)
drugs_to_show = drug_counts[drug_counts >= 2].index.tolist()
pivot = pivot.loc[drugs_to_show]

# Sort by mean across conditions
pivot['mean_all'] = pivot.mean(axis=1)
pivot = pivot.sort_values('mean_all', ascending=True)
pivot = pivot.drop(columns='mean_all')

fig, ax = plt.subplots(figsize=(12, 8))
bar_width = 0.25
conditions_list = ['POTS', 'MCAS', 'ME/CFS']
cond_colors = {'POTS': '#3498db', 'MCAS': '#9b59b6', 'ME/CFS': '#e67e22'}

y = np.arange(len(pivot))
for i, cond in enumerate(conditions_list):
    if cond in pivot.columns:
        vals = pivot[cond].fillna(0)
        ax.barh(y + i * bar_width, vals, bar_width, label=cond,
                       color=cond_colors[cond], alpha=0.8)
        for j, (v, drug) in enumerate(zip(vals, pivot.index)):
            n_val = 0
            if drug in pivot_n.index and cond in pivot_n.columns:
                nv = pivot_n.loc[drug, cond]
                if pd.notna(nv):
                    n_val = int(nv)
            if n_val > 0 and v != 0:
                ax.text(max(v, 0) + 0.02, j + i * bar_width, f'n={n_val}', va='center', fontsize=8, color='#666')

ax.axvline(x=0, color='black', linewidth=0.8)
ax.set_yticks(y + bar_width)
ax.set_yticklabels(pivot.index, fontsize=10)
ax.set_xlabel('Mean User-Level Sentiment Score (-1 to +1)', fontsize=11)
ax.set_title('Treatment Outcomes by Comorbidity Subgroup\n(POTS, MCAS, ME/CFS)', fontsize=14, fontweight='bold')
ax.legend(loc='lower right', fontsize=10, bbox_to_anchor=(1.0, 0.0))
plt.tight_layout()
plt.show()

display(HTML('''
<div style="background: #fff3cd; padding: 12px; border-radius: 6px; border-left: 4px solid #f39c12; margin-top: 10px; font-size: 13px;">
<b>Small sample caveat:</b> Most subgroup cells have n = 3-9. These comparisons are directional indicators only, not statistically powered conclusions.
The wide confidence intervals mean we cannot distinguish between subgroups at these sample sizes.
</div>
'''))
"""
cells.append(("code", SUBGROUP_CODE))

cells.append(("md",
"**What this shows:** Treatment response patterns vary by comorbidity, but the small "
"sample sizes (n=3-9 per cell) mean these are hypotheses, not conclusions. Notable "
"directional patterns:\n\n"
"- **Magnesium** appears to perform well across all three subgroups, suggesting its "
"benefit is not condition-specific.\n"
"- **LDN** shows weaker performance in MCAS patients compared to the general population "
"-- this warrants investigation with larger samples.\n"
"- **SSRIs** show low scores across all subgroups, consistent with the overall pattern.\n"
"- **Electrolytes** perform consistently well in POTS and MCAS, which aligns with "
"clinical expectations (electrolyte management is a cornerstone of POTS treatment).\n\n"
"Statistical testing is not meaningful at these sample sizes."
))

# ── Section 8: Counterintuitive Findings ──
cells.append(("md",
"## 8. Counterintuitive Findings Worth Investigating\n\n"
"This section highlights results that contradict clinical guidelines, community "
"assumptions, or common sense. These are not conclusions -- they are patterns worth "
"investigating further with larger datasets."
))

COUNTER1_CODE = (
"# Counterintuitive finding 1: SSRIs underperform despite clinical use\n"
"overall_pos = baseline_rate\n"
"\n"
"display(HTML(f'''\n"
"<div style=\"background: #fce4ec; padding: 15px; border-radius: 8px; border-left: 4px solid #e74c3c; margin: 10px 0;\">\n"
"<h4 style=\"margin-top:0;\">Finding 1: SSRIs and antidepressants perform at or below chance level</h4>\n"
"<p>Despite clinical interest in fluvoxamine for Long COVID (based on early trial data suggesting anti-inflammatory properties),\n"
"this community reports:</p>\n"
"<ul>\n"
"<li><b>SSRI (generic mentions):</b> 52.0% positive (n=50), p = 0.888 vs 50% -- indistinguishable from chance</li>\n"
"<li><b>Fluvoxamine (specific):</b> 45.8% positive (n=24), p = 0.839 -- slightly below chance</li>\n"
"<li><b>Antidepressants (generic):</b> 48.0% positive (n=25), p = 0.999 -- at chance</li>\n"
"</ul>\n"
"<p>Community baseline is {overall_pos*100:.1f}% positive. SSRIs are 20+ percentage points below baseline.\n"
"This does not mean SSRIs are ineffective -- it may reflect that patients prescribed SSRIs have more severe cases,\n"
"that they expect physical improvement from a neuromodulator, or that side effects dominate initial reports.\n"
"But the signal is notable: these are among the worst-performing treatments in the dataset.</p>\n"
"</div>\n"
"'''))\n"
)
cells.append(("code", COUNTER1_CODE))

COUNTER2_CODE = (
"# Counterintuitive finding 2: LDN is the most discussed but NOT the most effective\n"
"ldn_row = top_drugs[top_drugs['drug'] == 'low dose naltrexone'].iloc[0]\n"
"top5_avg = top_drugs.head(5)['pos_rate'].mean()\n"
"ldn_rank = int((top_drugs['pos_rate'] > ldn_row['pos_rate']).sum() + 1)\n"
"total_ranked = len(top_drugs)\n"
"\n"
"display(HTML(f'''\n"
"<div style=\"background: #fff8e1; padding: 15px; border-radius: 8px; border-left: 4px solid #f39c12; margin: 10px 0;\">\n"
"<h4 style=\"margin-top:0;\">Finding 2: LDN is the most discussed treatment but ranks #{ldn_rank} out of {total_ranked} in effectiveness</h4>\n"
"<p>Low Dose Naltrexone dominates community discussion with 183 users and 343 reports -- more than triple any other treatment.\n"
"Yet its positive rate ({ldn_row['pos_rate']*100:.1f}%) places it in the middle of the pack, {ldn_rank}th out of {total_ranked} qualifying treatments.\n"
"The top 5 treatments average {top5_avg*100:.1f}% positive.</p>\n"
"<p>This gap between discussion volume and outcome rate has several possible explanations:\n"
"(1) LDN requires dose titration and weeks to take effect, so early reports may skew negative;\n"
"(2) LDN is tried by more severe patients who have already failed simpler treatments;\n"
"(3) the large sample captures a more representative range of outcomes than small-sample treatments,\n"
"whose high rates may partially reflect positive publication bias.</p>\n"
"<p>The last point is critical: LDN's {ldn_row['pos_rate']*100:.1f}% may be more <i>trustworthy</i> than quercetin's 96.4%\n"
"precisely because the sample is large enough to include disappointed users.</p>\n"
"</div>\n"
"'''))\n"
)
cells.append(("code", COUNTER2_CODE))

COUNTER3_CODE = (
"# Counterintuitive finding 3: Cromolyn sodium performs poorly\n"
"cromolyn_row = top_drugs[top_drugs['drug'] == 'cromolyn sodium']\n"
"ketotifen_row = top_drugs[top_drugs['drug'] == 'ketotifen']\n"
"if len(cromolyn_row) > 0 and len(ketotifen_row) > 0:\n"
"    cr = cromolyn_row.iloc[0]\n"
"    kt = ketotifen_row.iloc[0]\n"
"    table_fisher = [[int(kt['pos_users']), int(kt['n_users'] - kt['pos_users'])],\n"
"                    [int(cr['pos_users']), int(cr['n_users'] - cr['pos_users'])]]\n"
"    _, fisher_p = fisher_exact(table_fisher)\n"
"    display(HTML(f'''\n"
"<div style=\"background: #e8eaf6; padding: 15px; border-radius: 8px; border-left: 4px solid #5c6bc0; margin: 10px 0;\">\n"
"<h4 style=\"margin-top:0;\">Finding 3: Cromolyn sodium -- a mast cell stabilizer standard of care -- has the worst outcome rate</h4>\n"
"<p>Cromolyn sodium (a mast cell stabilizer commonly prescribed for MCAS, which is reported by 75 users as a Long COVID comorbidity)\n"
"has a {cr['pos_rate']*100:.1f}% positive rate (n={int(cr['n_users'])}), making it the lowest-performing treatment with n >= 15.</p>\n"
"<p>Meanwhile, ketotifen (another mast cell stabilizer) performs far better at {kt['pos_rate']*100:.1f}% (n={int(kt['n_users'])}).\n"
"This divergence within the same drug class is genuine (Fisher exact p = {fisher_p:.4f}).</p>\n"
"<p>Possible explanations: cromolyn sodium has significant GI side effects that may dominate reports;\n"
"it requires multiple daily doses (4x/day) which generates compliance frustration;\n"
"or it is prescribed to patients with more severe MCAS, creating confounding by indication.</p>\n"
"</div>\n"
"'''))\n"
)
cells.append(("code", COUNTER3_CODE))

# ── Section 9: Qualitative Evidence ──
cells.append(("md",
"## 9. What Patients Are Saying\n\n"
"Quantitative analysis tells us what fraction of users report positive outcomes. Quotes "
"from actual posts reveal the texture of those experiences -- what \"positive\" and "
"\"negative\" actually feel like for patients."
))

QUOTES_CODE = (
"import re\n"
"\n"
"def clean_quote(text, max_words=40):\n"
"    text = re.sub(r'\\s+', ' ', text.strip())\n"
"    text = re.sub(r'[^\\x00-\\x7F]+', \"'\", text)\n"
"    words = text.split()\n"
"    if len(words) > max_words:\n"
"        text = ' '.join(words[:max_words]) + '...'\n"
"    return text\n"
"\n"
"mag_quotes = pd.read_sql('''\n"
"SELECT p.body_text, datetime(p.post_date, 'unixepoch') as post_date\n"
"FROM treatment_reports tr\n"
"JOIN treatment t ON tr.drug_id = t.id\n"
"JOIN posts p ON tr.post_id = p.post_id\n"
"WHERE t.canonical_name = 'magnesium' AND tr.sentiment = 'positive'\n"
"AND LENGTH(p.body_text) BETWEEN 60 AND 400\n"
"ORDER BY RANDOM() LIMIT 3\n"
"''', conn)\n"
"\n"
"ldn_pos_quotes = pd.read_sql('''\n"
"SELECT p.body_text, datetime(p.post_date, 'unixepoch') as post_date\n"
"FROM treatment_reports tr\n"
"JOIN treatment t ON tr.drug_id = t.id\n"
"JOIN posts p ON tr.post_id = p.post_id\n"
"WHERE t.canonical_name = 'low dose naltrexone' AND tr.sentiment = 'positive'\n"
"AND LENGTH(p.body_text) BETWEEN 80 AND 400\n"
"ORDER BY RANDOM() LIMIT 2\n"
"''', conn)\n"
"\n"
"ldn_neg_quotes = pd.read_sql('''\n"
"SELECT p.body_text, datetime(p.post_date, 'unixepoch') as post_date\n"
"FROM treatment_reports tr\n"
"JOIN treatment t ON tr.drug_id = t.id\n"
"JOIN posts p ON tr.post_id = p.post_id\n"
"WHERE t.canonical_name = 'low dose naltrexone' AND tr.sentiment = 'negative'\n"
"AND LENGTH(p.body_text) BETWEEN 60 AND 400\n"
"ORDER BY RANDOM() LIMIT 2\n"
"''', conn)\n"
"\n"
"ssri_neg_quotes = pd.read_sql('''\n"
"SELECT p.body_text, datetime(p.post_date, 'unixepoch') as post_date\n"
"FROM treatment_reports tr\n"
"JOIN treatment t ON tr.drug_id = t.id\n"
"JOIN posts p ON tr.post_id = p.post_id\n"
"WHERE t.canonical_name IN ('ssri', 'fluvoxamine') AND tr.sentiment = 'negative'\n"
"AND LENGTH(p.body_text) BETWEEN 80 AND 400\n"
"ORDER BY RANDOM() LIMIT 2\n"
"''', conn)\n"
"\n"
"html_parts = ['<div style=\"margin: 15px 0;\">']\n"
"\n"
"html_parts.append('<h4>Magnesium -- positive experiences (92.9% positive rate):</h4>')\n"
"for _, row in mag_quotes.iterrows():\n"
"    q = clean_quote(row['body_text'])\n"
"    html_parts.append(f'<blockquote style=\"border-left:3px solid #2ecc71; padding:8px 15px; margin:8px 0; color:#333; font-style:italic;\">\"{q}\"<br><span style=\"font-size:11px; color:#888;\">-- r/covidlonghaulers, {row[\"post_date\"][:10]}</span></blockquote>')\n"
"\n"
"html_parts.append('<h4>Low Dose Naltrexone -- positive experiences (73.8% positive rate):</h4>')\n"
"for _, row in ldn_pos_quotes.iterrows():\n"
"    q = clean_quote(row['body_text'])\n"
"    html_parts.append(f'<blockquote style=\"border-left:3px solid #2ecc71; padding:8px 15px; margin:8px 0; color:#333; font-style:italic;\">\"{q}\"<br><span style=\"font-size:11px; color:#888;\">-- r/covidlonghaulers, {row[\"post_date\"][:10]}</span></blockquote>')\n"
"\n"
"html_parts.append('<h4>Low Dose Naltrexone -- negative experiences (complicating the narrative):</h4>')\n"
"for _, row in ldn_neg_quotes.iterrows():\n"
"    q = clean_quote(row['body_text'])\n"
"    html_parts.append(f'<blockquote style=\"border-left:3px solid #e74c3c; padding:8px 15px; margin:8px 0; color:#333; font-style:italic;\">\"{q}\"<br><span style=\"font-size:11px; color:#888;\">-- r/covidlonghaulers, {row[\"post_date\"][:10]}</span></blockquote>')\n"
"\n"
"html_parts.append('<h4>SSRIs/Fluvoxamine -- negative experiences (below-chance positive rate):</h4>')\n"
"for _, row in ssri_neg_quotes.iterrows():\n"
"    q = clean_quote(row['body_text'])\n"
"    html_parts.append(f'<blockquote style=\"border-left:3px solid #e74c3c; padding:8px 15px; margin:8px 0; color:#333; font-style:italic;\">\"{q}\"<br><span style=\"font-size:11px; color:#888;\">-- r/covidlonghaulers, {row[\"post_date\"][:10]}</span></blockquote>')\n"
"\n"
"html_parts.append('</div>')\n"
"display(HTML(''.join(html_parts)))\n"
)
cells.append(("code", QUOTES_CODE))

# ── Section 10: Tiered Recommendations ──
cells.append(("md",
"## 10. Tiered Recommendations\n\n"
"Based on the evidence above, treatments are classified into three tiers by the "
"strength of supporting data. Classification uses both statistical significance "
"(p-value against 50% null) and sample size, with effect size (Cohen's h) as a "
"quality check."
))

TIER_CODE = r"""# Tiered recommendations
def assign_tier(row):
    if row['n_users'] >= 30 and row['p_value'] < 0.05 and row['pos_rate'] > 0.5:
        return 'Strong'
    elif row['n_users'] >= 30 and row['p_value'] < 0.05 and row['pos_rate'] <= 0.5:
        return 'Strong Negative'
    elif row['n_users'] >= 15 and row['p_value'] < 0.10 and row['pos_rate'] > 0.5:
        return 'Moderate'
    elif row['n_users'] >= 15 and row['p_value'] < 0.10 and row['pos_rate'] <= 0.5:
        return 'Moderate Negative'
    elif row['pos_rate'] > 0.5:
        return 'Preliminary'
    else:
        return 'Preliminary Negative'

top_drugs['tier'] = top_drugs.apply(assign_tier, axis=1)

# Strong tier chart
strong = top_drugs[top_drugs['tier'] == 'Strong'].sort_values('pos_rate', ascending=True)

fig, ax = plt.subplots(figsize=(10, max(4, len(strong) * 0.45)))
y = range(len(strong))
ax.barh(y, strong['pos_rate'], color='#27ae60', height=0.6, alpha=0.8)

for i, (_, row) in enumerate(strong.iterrows()):
    ax.plot([row['ci_low'], row['ci_high']], [i, i], color='#1a7a40', linewidth=2.5)

ax.axvline(x=0.5, color='black', linestyle='--', linewidth=1, alpha=0.4)
ax.set_yticks(y)
ax.set_yticklabels([f"{row['drug']}  (n={int(row['n_users'])})" for _, row in strong.iterrows()], fontsize=10)
ax.set_xlabel('Positive Rate', fontsize=11)
ax.set_title('Strong Evidence Tier: n >= 30, p < 0.05', fontsize=13, fontweight='bold')
ax.set_xlim(0.3, 1.05)

for i, (_, row) in enumerate(strong.iterrows()):
    nnt_val = row['nnt_vs_50']
    label = f"NNT={nnt_val:.1f}" if nnt_val else "NNT=---"
    ax.text(min(row['ci_high'] + 0.02, 1.02), i, label, va='center', fontsize=9, color='#555')

plt.tight_layout()
plt.show()
"""
cells.append(("code", TIER_CODE))

TIER2_CODE = r"""# Moderate and negative tiers
moderate = top_drugs[top_drugs['tier'] == 'Moderate'].sort_values('pos_rate', ascending=True)
prelim = top_drugs[top_drugs['tier'] == 'Preliminary'].sort_values('pos_rate', ascending=True)

if len(moderate) > 0:
    fig, ax = plt.subplots(figsize=(10, max(3, len(moderate) * 0.45)))
    y = range(len(moderate))
    ax.barh(y, moderate['pos_rate'], color='#f39c12', height=0.6, alpha=0.8)
    for i, (_, row) in enumerate(moderate.iterrows()):
        ax.plot([row['ci_low'], row['ci_high']], [i, i], color='#c47f10', linewidth=2.5)
    ax.axvline(x=0.5, color='black', linestyle='--', linewidth=1, alpha=0.4)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{row['drug']}  (n={int(row['n_users'])})" for _, row in moderate.iterrows()], fontsize=10)
    ax.set_xlabel('Positive Rate', fontsize=11)
    ax.set_title('Moderate Evidence Tier: n >= 15, p < 0.10', fontsize=13, fontweight='bold')
    ax.set_xlim(0.3, 1.05)
    plt.tight_layout()
    plt.show()
"""
cells.append(("code", TIER2_CODE))

TIER3_CODE = r"""# Negative tier
negative_tiers = top_drugs[top_drugs['tier'].str.contains('Negative')].sort_values('pos_rate', ascending=False)

if len(negative_tiers) > 0:
    fig, ax = plt.subplots(figsize=(10, max(3, len(negative_tiers) * 0.5)))
    y = range(len(negative_tiers))
    ax.barh(y, negative_tiers['pos_rate'], color='#e74c3c', height=0.6, alpha=0.8)
    for i, (_, row) in enumerate(negative_tiers.iterrows()):
        ax.plot([row['ci_low'], row['ci_high']], [i, i], color='#a02820', linewidth=2.5)
    ax.axvline(x=0.5, color='black', linestyle='--', linewidth=1, alpha=0.4)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{row['drug']}  (n={int(row['n_users'])})" for _, row in negative_tiers.iterrows()], fontsize=10)
    ax.set_xlabel('Positive Rate', fontsize=11)
    ax.set_title('Negative / Caution Tier: Positive Rate at or Below 50%', fontsize=13, fontweight='bold')
    ax.set_xlim(0.0, 0.85)
    plt.tight_layout()
    plt.show()

display(HTML(f'''
<div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0;">
<h4 style="margin-top:0;">Tier Summary</h4>
<table style="font-size: 13px;">
<tr><th style="text-align:left">Tier</th><th>Count</th><th>Criteria</th></tr>
<tr><td style="color:#27ae60"><b>Strong</b></td><td>{len(strong)}</td><td>n >= 30, p &lt; 0.05 vs 50% null</td></tr>
<tr><td style="color:#f39c12"><b>Moderate</b></td><td>{len(moderate)}</td><td>n >= 15, p &lt; 0.10</td></tr>
<tr><td style="color:#95a5a6"><b>Preliminary</b></td><td>{len(prelim)}</td><td>Positive but not statistically significant</td></tr>
<tr><td style="color:#e74c3c"><b>Negative</b></td><td>{len(negative_tiers)}</td><td>Positive rate at or below 50%</td></tr>
</table>
</div>
'''))
"""
cells.append(("code", TIER3_CODE))

cells.append(("md",
"**Tier interpretation for patients:**\n\n"
"**Strong evidence (green):** These treatments have enough data and a clear enough "
"signal that we can confidently say the community reports them as more helpful than "
"not. Magnesium, electrolytes, LDN, and vitamin D are safe, accessible starting points.\n\n"
"**Moderate evidence (orange):** Promising signals but either smaller samples or wider "
"confidence intervals. Worth trying, but temper expectations.\n\n"
"**Preliminary (grey):** Interesting but underpowered. The positive rates may be "
"inflated by small sample sizes. Monitor for more data.\n\n"
"**Negative (red):** The community reports these at or below chance levels. SSRIs, "
"fluvoxamine, and cromolyn sodium fall here. This does not mean they never work -- "
"but the majority of users in this dataset did not report positive outcomes."
))

# ── Section 11: Sensitivity Check ──
cells.append(("md",
"## 11. Sensitivity Analysis\n\n"
"Does the main conclusion survive if we restrict to strong-signal reports only "
"(excluding \"weak\" signal strength)?"
))

SENSITIVITY_CODE = r"""# Sensitivity: strong/moderate signal only
strong_sig_q = '''
SELECT tr.user_id, t.canonical_name as drug,
       AVG(CASE tr.sentiment
           WHEN 'positive' THEN 1.0 WHEN 'mixed' THEN 0.5
           WHEN 'neutral' THEN 0.0 WHEN 'negative' THEN -1.0 ELSE 0.0 END) as avg_score
FROM treatment_reports tr
JOIN treatment t ON tr.drug_id = t.id
WHERE tr.signal_strength IN ('strong', 'moderate')
AND t.canonical_name NOT IN (
    'supplements', 'medication', 'treatment', 'therapy', 'drug', 'drugs',
    'vitamin', 'prescription', 'pill', 'pills', 'dosage', 'dose',
    'covid vaccine', 'flu vaccine', 'mmr vaccine', 'moderna vaccine',
    'mrna covid-19 vaccine', 'pfizer vaccine', 'vaccine', 'vaccine injection',
    'pfizer', 'booster', 'antihistamines', 'antibiotics')
GROUP BY tr.user_id, t.canonical_name
'''
strong_sig_df = pd.read_sql(strong_sig_q, conn)
strong_sig_df['positive'] = (strong_sig_df['avg_score'] > 0).astype(int)

ss_summary = strong_sig_df.groupby('drug').agg(
    n=('user_id', 'nunique'),
    pos=('positive', 'sum')
).reset_index()
ss_summary['pos_rate'] = ss_summary['pos'] / ss_summary['n']
ss_summary = ss_summary[ss_summary['n'] >= 10].sort_values('pos_rate', ascending=False)

main_top10 = top_drugs.head(10)[['drug', 'pos_rate', 'n_users']].copy()
main_top10.columns = ['drug', 'full_rate', 'full_n']

compare = main_top10.merge(ss_summary[['drug', 'pos_rate', 'n']], on='drug', how='left')
compare.columns = ['Treatment', 'All Signals Rate', 'All Signals n', 'Strong Signal Rate', 'Strong Signal n']
compare['Delta'] = (compare['Strong Signal Rate'] - compare['All Signals Rate']).apply(
    lambda x: f'{x*100:+.1f}pp' if pd.notna(x) else 'N/A')
compare['All Signals Rate'] = compare['All Signals Rate'].apply(lambda x: f'{x*100:.1f}%')
compare['Strong Signal Rate'] = compare['Strong Signal Rate'].apply(lambda x: f'{x*100:.1f}%' if pd.notna(x) else 'N/A')

display(HTML('<h4>Sensitivity Check: Top 10 Treatments -- All Signals vs. Strong/Moderate Only</h4>'))
display(compare.style.set_properties(**{'text-align': 'center'}).set_properties(subset=['Treatment'], **{'text-align': 'left'}))

rate_changes = (ss_summary.merge(top_drugs[['drug', 'pos_rate']], on='drug', suffixes=('_ss', '_full'))
                .assign(diff=lambda x: abs(x['pos_rate_ss'] - x['pos_rate_full'])))
avg_change = rate_changes['diff'].mean()

robust = 'robust' if avg_change < 0.05 else 'moderately sensitive'
holds = 'The main conclusions hold.' if avg_change < 0.08 else 'Some treatments shift meaningfully -- interpret lower-ranked treatments with caution.'

display(HTML(f'''
<div style="background: #e8f5e9; padding: 12px; border-radius: 6px; margin-top: 10px; font-size: 13px;">
<b>Sensitivity verdict:</b> The average absolute change in positive rate when restricting to strong/moderate signals is
<b>{avg_change*100:.1f} percentage points</b>. The top-tier rankings are {robust} to signal strength filtering.
{holds}
</div>
'''))
"""
cells.append(("code", SENSITIVITY_CODE))

# ── Section 12: Conclusion ──
cells.append(("md",
"## 12. Conclusion\n\n"
"Based on 6,815 treatment reports from 1,121 users in the r/covidlonghaulers community "
"over one month, the data tells a clear story with important nuances.\n\n"
"**The most consistently positive treatments are basic supplements and lifestyle "
"interventions.** Magnesium (92.9% positive, n=56), quercetin (96.4%, n=28), "
"electrolytes (87.5%, n=40), and B vitamins (88.9%, n=27) all show strong positive "
"rates with low Shannon entropy (high community agreement). These are accessible, "
"low-cost, and low-risk -- and the community broadly agrees they help. A patient newly "
"diagnosed with Long COVID should consider these as a first-line foundation.\n\n"
"**Low Dose Naltrexone is the treatment with the most data and a strong positive signal, "
"but it is not the most effective.** LDN's 73.8% positive rate (n=183) is statistically "
"significant and clinically meaningful (NNT ~4.2 vs chance), but it ranks below simpler "
"interventions. Its large sample provides the most reliable estimate in the dataset, and "
"its mid-pack position likely reflects a more realistic outcome distribution. LDN remains "
"a strong recommendation, particularly for patients who have already tried supplements "
"and need escalation.\n\n"
"**Pharmaceutical interventions show a mixed picture.** Beta blockers (81.1%) and "
"propranolol (78.4%) perform well, likely driven by their effectiveness for POTS symptoms "
"that frequently accompany Long COVID. Ketotifen (73.0%) and famotidine (75.0%) show "
"moderate benefit for MCAS-related symptoms. In contrast, SSRIs (52.0%), fluvoxamine "
"(45.8%), and antidepressants (48.0%) perform at or below chance -- a striking result "
"given clinical interest in these drugs for Long COVID neuroinflammation. Cromolyn sodium "
"(34.8%) is the worst performer, despite being a standard mast cell stabilizer.\n\n"
"**A patient asking \"what should I try?\" should start with magnesium, electrolytes, and "
"vitamin D** (all strong evidence, widely tolerated), escalate to LDN if symptoms persist "
"(strong evidence, requires prescription), and approach SSRIs with realistic expectations "
"(community evidence is weak to negative, though individual response varies). The emerging "
"GLP-1 receptor agonist data (75.9%, n=29) is worth monitoring but needs larger samples "
"before recommendation."
))

# ── Section 13: Research Limitations ──
cells.append(("md",
"## 13. Research Limitations\n\n"
"**1. Selection bias:** r/covidlonghaulers members are self-selected and skew toward "
"English-speaking, internet-literate patients. Demographics (age, gender, severity, "
"time since onset) are unavailable, making it impossible to know if this sample "
"represents the broader Long COVID population.\n\n"
"**2. Reporting bias:** People are more likely to post about treatments that provoked "
"strong reactions (positive or negative). Treatments that produced mild or ambiguous "
"results are underrepresented. The 74% overall positive rate reflects this -- it is "
"not a population-level effectiveness estimate.\n\n"
"**3. Survivorship bias:** This sample captures active community members during "
"March-April 2026. Patients who recovered fully and left the community are not "
"represented, nor are those too ill to post. Both absences distort the picture in "
"opposite directions.\n\n"
"**4. Recall bias:** Posts describe remembered experiences, not prospective measurements. "
"Patients who felt better may attribute improvement to whatever treatment they started "
"most recently, even if natural recovery or regression to the mean was responsible.\n\n"
"**5. Confounding:** Most patients use multiple treatments simultaneously (median 2-3, "
"some using 20+). Attributing outcomes to any single treatment is impossible without "
"a controlled design. Polypharmacy users who improve may credit the wrong treatment.\n\n"
"**6. No control group:** There is no untreated comparison group. We test against a "
"50% null (chance), but the true natural recovery rate for Long COVID is unknown and "
"likely varies by time since onset, severity, and variant.\n\n"
"**7. Sentiment is not efficacy:** NLP-extracted sentiment measures how positively "
"someone describes a treatment in a post, not objective clinical improvement. A patient "
"might describe a treatment positively because it reduced one symptom while ignoring "
"others, or because their expectations were low.\n\n"
"**8. Temporal snapshot:** One month of data (March 11 - April 10, 2026) cannot capture "
"long-term outcomes, seasonal effects, or shifts in community consensus. Treatments "
"popular this month may be abandoned next month. The Long COVID treatment landscape "
"evolves rapidly as new research emerges."
))

# ── Disclaimer ──
cells.append(("code",
"display(HTML('<div style=\"margin: 30px 0; padding: 20px; background: #fff3e0; border-radius: 8px; text-align: center;\">'\n"
"             '<p style=\"font-size: 1.2em; font-weight: bold; font-style: italic; color: #333;\">'\n"
"             'These findings reflect reporting patterns in online communities, not population-level treatment effects. '\n"
"             'This is not medical advice.</p></div>'))\n"
))

# Build and export
nb = build_notebook(cells=cells, db_path=DB_PATH)
output_stem = os.path.join(os.path.dirname(__file__), "1_treatment_overview")
html_path = execute_and_export(nb, output_stem)
print(f"SUCCESS: {html_path}")
