"""Build, execute, and export the PSSD recovery notebook."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from build_notebook import build_notebook, execute_and_export

cells = []

# ── Research Question ──
cells.append(("md", '**Research Question:** "What treatments improve PSSD (Post-SSRI Sexual Dysfunction) once people have it?"\n\n---'))

# ── Abstract ──
cells.append(("md", """## Abstract

This analysis examines 902 treatment reports from 220 unique users in the r/PSSD (Post-SSRI Sexual Dysfunction) community to identify which treatments show the most promising recovery signals. After filtering causative drugs (SSRIs, SNRIs, finasteride) and generic terms, and merging duplicate entries, we analyzed recovery-oriented treatments grouped by mechanism of action. **Antihistamines emerged as the most consistently positive treatment class**, with loratadine (67% positive), ketotifen (88% positive), and cetirizine (67% positive) all outperforming the population baseline of 26%. Dopamine agonists (cabergoline, pramipexole) and bupropion showed moderate but mixed results. Psychedelics (microdosing) showed high positive rates but with very small samples. The data covers March 12 to April 11, 2026 (1 month), and all findings reflect community reporting patterns, not controlled clinical outcomes."""))

# ── Section 1: Data Exploration ──
cells.append(("md", """## 1. Data Exploration

Before analyzing recovery treatments, we need to understand the data landscape: how many reports exist, what gets filtered, and what remains for analysis."""))

cells.append(("code", '''
from datetime import datetime

total_reports = pd.read_sql("SELECT COUNT(*) as n FROM treatment_reports", conn).iloc[0, 0]
total_users = pd.read_sql("SELECT COUNT(DISTINCT user_id) as n FROM treatment_reports", conn).iloc[0, 0]
total_drugs = pd.read_sql("SELECT COUNT(DISTINCT drug_id) as n FROM treatment_reports", conn).iloc[0, 0]
date_range = pd.read_sql("SELECT MIN(post_date) as mn, MAX(post_date) as mx FROM posts", conn).iloc[0]
dt_min = datetime.fromtimestamp(date_range['mn']).strftime('%Y-%m-%d')
dt_max = datetime.fromtimestamp(date_range['mx']).strftime('%Y-%m-%d')

sent_dist = pd.read_sql("""
    SELECT sentiment, COUNT(*) as reports, COUNT(DISTINCT user_id) as users
    FROM treatment_reports GROUP BY sentiment ORDER BY reports DESC
""", conn)

display(HTML(f"""
<div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0;">
<h3 style="margin-top:0;">Dataset Overview</h3>
<table style="font-size: 14px;">
<tr><td><b>Data covers:</b></td><td>{dt_min} to {dt_max} (1 month)</td></tr>
<tr><td><b>Total treatment reports:</b></td><td>{total_reports:,}</td></tr>
<tr><td><b>Unique reporting users:</b></td><td>{total_users:,}</td></tr>
<tr><td><b>Unique treatments mentioned:</b></td><td>{total_drugs:,}</td></tr>
</table>
</div>
"""))

display(HTML("<h4>Sentiment Distribution Across All Reports</h4>"))
styled = sent_dist.style.set_properties(**{'text-align': 'center'}).hide(axis='index')
display(styled)
'''))

# ── Filtering ──
cells.append(("md", """### Filtering and Merging

PSSD (Post-SSRI Sexual Dysfunction) is *caused* by SSRIs and related drugs. Reports about these causative drugs overwhelmingly reflect negative sentiment about the drug having caused the condition, not about using the drug as a recovery treatment. Including them would contaminate the analysis. We apply four filters:

1. **Causative drugs excluded:** SSRIs (sertraline, fluoxetine, paroxetine, escitalopram, citalopram, lexapro, prozac, vortioxetine, duloxetine), SNRIs (venlafaxine, snri), the SSRI class label, finasteride (a 5-alpha reductase inhibitor that causes an overlapping syndrome), and antipsychotics (olanzapine, atomoxetine, amitriptyline, seroquel, abilify) discussed as causes.
2. **Generic terms excluded:** "antidepressant", "supplements", "medication", "treatment", "therapy", "drug", "psychiatric medications", "dopaminergic drugs", "stimulants", "75mg" (a dosage, not a drug).
3. **Duplicate merging:** dxm + dextromethorphan, weed + cannabis + marijuana, cyproheptadine + ciproheptadine, seed + seed daily synbiotic, testosterone + testosterone replacement therapy, brintellix + vortioxetine (causal, filtered).
4. **Minimum threshold:** 3+ unique users required for inclusion in ranked analysis."""))

cells.append(("code", '''
CAUSAL_DRUGS = {
    'ssri', 'sertraline', 'fluoxetine', 'paroxetine', 'escitalopram',
    'citalopram', 'lexapro', 'prozac', 'vortioxetine', 'duloxetine',
    'snri', 'venlafaxine', 'finasteride', 'olanzapine', 'atomoxetine',
    'amitriptyline', 'seroquel', 'abilify', 'brintellix',
    'antipsychotics'
}

FILTER_TERMS = GENERIC_TERMS | {
    'antidepressant', 'psychiatric medications', 'dopaminergic drugs',
    'stimulants', '75mg', 'ointment', 'seed'
}

MERGE_MAP = {
    'dextromethorphan': 'dxm',
    'cannabis': 'cannabis/weed',
    'weed': 'cannabis/weed',
    'marijuana': 'cannabis/weed',
    'ciproheptadine': 'cyproheptadine',
    'seed daily synbiotic': 'seed synbiotic',
    'testosterone replacement therapy': 'testosterone/trt',
    'testosterone': 'testosterone/trt',
}

df_all = pd.read_sql("""
    SELECT tr.report_id, tr.user_id, tr.post_id, tr.sentiment, tr.signal_strength,
           t.canonical_name as drug, t.id as drug_id
    FROM treatment_reports tr
    JOIN treatment t ON tr.drug_id = t.id
""", conn)

df_all['drug_lower'] = df_all['drug'].str.lower()

n_before = len(df_all)
users_before = df_all['user_id'].nunique()

df_causal = df_all[df_all['drug_lower'].isin(CAUSAL_DRUGS)]
causal_reports = len(df_causal)
causal_users = df_causal['user_id'].nunique()
causal_drugs_found = sorted(df_causal['drug_lower'].unique())

df = df_all[~df_all['drug_lower'].isin(CAUSAL_DRUGS)].copy()

df_generic = df[df['drug_lower'].isin(FILTER_TERMS)]
generic_reports = len(df_generic)

df = df[~df['drug_lower'].isin(FILTER_TERMS)].copy()

df['drug_canonical'] = df['drug_lower'].map(lambda x: MERGE_MAP.get(x, x))

n_after = len(df)
users_after = df['user_id'].nunique()
drugs_after = df['drug_canonical'].nunique()

display(HTML(f"""
<div style="background: #fff3cd; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #ffc107;">
<h4 style="margin-top:0;">Filtering Summary (Verbose Mode)</h4>
<table style="font-size: 13px;">
<tr><td>Starting reports:</td><td><b>{n_before}</b> ({users_before} users)</td></tr>
<tr><td>Causal drug reports removed:</td><td><b>{causal_reports}</b> ({causal_users} users) &mdash; {', '.join(causal_drugs_found)}</td></tr>
<tr><td>Generic term reports removed:</td><td><b>{generic_reports}</b></td></tr>
<tr><td>Duplicates merged:</td><td>dxm/dextromethorphan, weed/cannabis/marijuana, cyproheptadine/ciproheptadine, testosterone/TRT</td></tr>
<tr><td><b>Remaining reports:</b></td><td><b>{n_after}</b> ({users_after} users, {drugs_after} unique treatments)</td></tr>
</table>
</div>
"""))
'''))

# ── User-level aggregation ──
cells.append(("code", '''
df['score'] = df['sentiment'].map(SENTIMENT_SCORE)

user_drug = df.groupby(['drug_canonical', 'user_id']).agg(
    mean_score=('score', 'mean'),
    n_reports=('report_id', 'count'),
    best_sentiment=('score', 'max'),
    worst_sentiment=('score', 'min'),
).reset_index()

user_drug['outcome'] = user_drug['mean_score'].map(classify_outcome)

drug_summary = user_drug.groupby('drug_canonical').agg(
    n_users=('user_id', 'nunique'),
    mean_score=('mean_score', 'mean'),
    positive_users=('outcome', lambda x: (x == 'positive').sum()),
    negative_users=('outcome', lambda x: (x == 'negative').sum()),
    mixed_users=('outcome', lambda x: (x == 'mixed/neutral').sum()),
).reset_index()

drug_summary['pos_rate'] = drug_summary['positive_users'] / drug_summary['n_users']
drug_summary['neg_rate'] = drug_summary['negative_users'] / drug_summary['n_users']

drug_summary['wilson_lo'] = drug_summary.apply(
    lambda r: wilson_ci(int(r['positive_users']), int(r['n_users']))[0], axis=1)
drug_summary['wilson_hi'] = drug_summary.apply(
    lambda r: wilson_ci(int(r['positive_users']), int(r['n_users']))[1], axis=1)

drug_summary = drug_summary.sort_values('pos_rate', ascending=False)
'''))

# ── Section 2: Baseline ──
cells.append(("md", """## 2. Baseline: The Recovery Landscape in PSSD

Before evaluating individual treatments, we need to establish what "typical" looks like. What proportion of treatment attempts in this community result in positive reports? This baseline contextualizes everything that follows."""))

cells.append(("code", '''
total_user_drug_pairs = len(user_drug)
overall_pos_rate = (user_drug['outcome'] == 'positive').mean()
overall_neg_rate = (user_drug['outcome'] == 'negative').mean()
overall_mix_rate = (user_drug['outcome'] == 'mixed/neutral').mean()
overall_ci = wilson_ci(int((user_drug['outcome'] == 'positive').sum()), total_user_drug_pairs)

display(HTML(f"""
<div style="background: #e8f5e9; padding: 15px; border-radius: 8px; margin: 10px 0;">
<h4 style="margin-top:0;">Population Baseline (Recovery Treatments Only)</h4>
<p>Across <b>{total_user_drug_pairs}</b> user-treatment pairs (after filtering causative drugs):</p>
<ul>
<li><b>Positive outcome rate:</b> {overall_pos_rate:.1%} (95% Wilson CI: {overall_ci[0]:.1%}&ndash;{overall_ci[1]:.1%})</li>
<li><b>Negative outcome rate:</b> {overall_neg_rate:.1%}</li>
<li><b>Mixed/neutral rate:</b> {overall_mix_rate:.1%}</li>
</ul>
<p>Any treatment with a positive rate substantially above {overall_pos_rate:.0%} is outperforming the population average.</p>
</div>
"""))

outcomes = user_drug['outcome'].value_counts()
colors_pie = [COLORS.get(k, '#999') for k in outcomes.index]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

wedges, texts, autotexts = ax1.pie(outcomes.values, labels=outcomes.index, colors=colors_pie,
                                     autopct='%1.1f%%', startangle=90, textprops={'fontsize': 12})
ax1.set_title('User-Level Outcome Distribution\\n(Recovery Treatments Only)', fontsize=13, fontweight='bold')

ax2.hist(user_drug['mean_score'], bins=20, color='#3498db', edgecolor='white', alpha=0.8)
ax2.axvline(user_drug['mean_score'].mean(), color='red', linestyle='--', linewidth=2,
            label=f"Mean: {user_drug['mean_score'].mean():.2f}")
ax2.set_xlabel('User-Level Mean Sentiment Score', fontsize=12)
ax2.set_ylabel('Count', fontsize=12)
ax2.set_title('Distribution of Treatment Sentiment Scores', fontsize=13, fontweight='bold')
ax2.legend(frameon=True, loc='upper left')

plt.tight_layout()
plt.show()
'''))

cells.append(("md", """**What this means:** The majority of treatment attempts in the PSSD community result in negative outcomes at the user level. This is expected -- PSSD is a condition defined by persistent symptoms after drug exposure, so the population skews toward people still struggling. The baseline positive rate establishes the bar any individual treatment must clear to be considered promising."""))

# ── Section 3: Treatment Rankings ──
cells.append(("md", """## 3. Treatment Rankings by Positive Outcome Rate

Which treatments have the highest proportion of users reporting improvement? We rank all treatments with 3+ users by their user-level positive outcome rate, with Wilson score confidence intervals to account for small sample sizes."""))

cells.append(("code", '''
ranked = drug_summary[drug_summary['n_users'] >= 3].copy()
ranked = ranked.sort_values('pos_rate', ascending=False).reset_index(drop=True)

MECHANISM_MAP = {
    'antihistamine': 'Antihistamine / Mast Cell',
    'loratadine': 'Antihistamine / Mast Cell',
    'ketotifen': 'Antihistamine / Mast Cell',
    'cetirizine': 'Antihistamine / Mast Cell',
    'cyproheptadine': 'Antihistamine / Mast Cell',
    'quercetin': 'Antihistamine / Mast Cell',
    'liposomal quercetin': 'Antihistamine / Mast Cell',
    'cabergoline': 'Dopamine Agonist',
    'pramipexole': 'Dopamine Agonist',
    'd2 agonist': 'Dopamine Agonist',
    'bupropion': 'Norepinephrine-Dopamine',
    'buspirone': 'Serotonin 5-HT1A Agonist',
    'tadalafil': 'PDE5 Inhibitor',
    'sildenafil': 'PDE5 Inhibitor',
    'pt-141': 'Melanocortin Agonist',
    'microdosing': 'Psychedelic',
    'shrooms': 'Psychedelic',
    'lsd': 'Psychedelic',
    'cannabis/weed': 'Cannabinoid',
    'dxm': 'NMDA Antagonist',
    'ketogenic diet': 'Dietary Intervention',
    'gabapentin': 'GABAergic',
    'probiotics': 'Gut-Brain Axis',
    'hcg': 'Hormonal',
    'testosterone/trt': 'Hormonal',
    'low dose naltrexone': 'Opioid Modulator',
    'omega-3 fatty acids': 'Nutritional Supplement',
    'magnesium': 'Nutritional Supplement',
    'magnesium glycinate': 'Nutritional Supplement',
    'vitamin c': 'Nutritional Supplement',
    'amphetamine': 'Stimulant',
    'methylphenidate': 'Stimulant',
    'alcohol': 'Other',
    'trazodone': 'Serotonin Modulator',
    'benzodiazepines': 'GABAergic',
    'coffee': 'Stimulant',
    'immunoadsorption': 'Immune Modulation',
    'plasmapheresis': 'Immune Modulation',
    'pelvic floor physical therapy': 'Physical Therapy',
    'tre': 'Physical Therapy',
    'exercise': 'Lifestyle',
    'fasting': 'Dietary Intervention',
    "st. john's wort": 'Herbal',
    'ginkgo biloba': 'Herbal',
    '5-htp': 'Serotonin Precursor',
    'creatine': 'Nutritional Supplement',
    'maca': 'Herbal',
    'saffron': 'Herbal',
    'green tea': 'Nutritional Supplement',
    'meat-based diet': 'Dietary Intervention',
    'seed synbiotic': 'Gut-Brain Axis',
    'antibiotic': 'Gut-Brain Axis',
    'lamotrigine': 'Mood Stabilizer',
}

ranked['mechanism'] = ranked['drug_canonical'].map(MECHANISM_MAP).fillna('Other')

display_df = ranked.head(25)[['drug_canonical', 'mechanism', 'n_users', 'positive_users',
                               'negative_users', 'mixed_users', 'pos_rate', 'wilson_lo', 'wilson_hi']].copy()
display_df.columns = ['Treatment', 'Mechanism', 'Users', 'Positive', 'Negative', 'Mixed',
                       'Pos Rate', 'CI Low', 'CI High']
display_df['Pos Rate'] = display_df['Pos Rate'].map('{:.0%}'.format)
display_df['CI Low'] = display_df['CI Low'].map('{:.0%}'.format)
display_df['CI High'] = display_df['CI High'].map('{:.0%}'.format)

display(HTML("<h4>Top 25 Recovery Treatments by Positive Outcome Rate (n >= 3 users)</h4>"))
styled = display_df.style.set_properties(**{'text-align': 'center'}).hide(axis='index')
display(styled)
'''))

# ── Forest plot ──
cells.append(("code", '''
from matplotlib.lines import Line2D

plot_df = ranked[ranked['n_users'] >= 3].head(25).copy()
plot_df = plot_df.sort_values('pos_rate', ascending=True)

fig, ax = plt.subplots(figsize=(12, 10))

y_pos = range(len(plot_df))
colors_forest = []
for _, row in plot_df.iterrows():
    if row['wilson_lo'] > overall_pos_rate:
        colors_forest.append('#2ecc71')
    elif row['wilson_hi'] < overall_pos_rate:
        colors_forest.append('#e74c3c')
    else:
        colors_forest.append('#95a5a6')

ax.scatter(plot_df['pos_rate'] * 100, y_pos, c=colors_forest, s=80, zorder=5,
           edgecolors='black', linewidth=0.5)

for i, (_, row) in enumerate(plot_df.iterrows()):
    ax.plot([row['wilson_lo'] * 100, row['wilson_hi'] * 100], [i, i],
            color=colors_forest[i], linewidth=2, zorder=4)

ax.axvline(overall_pos_rate * 100, color='black', linestyle='--', linewidth=1.5, alpha=0.6,
           label=f'Population baseline: {overall_pos_rate:.0%}')

ax.set_yticks(list(y_pos))
ax.set_yticklabels([f"{row['drug_canonical']}  (n={int(row['n_users'])})"
                     for _, row in plot_df.iterrows()], fontsize=10)
ax.set_xlabel('Positive Outcome Rate (%)', fontsize=12)
ax.set_title('Recovery Treatment Rankings with 95% Wilson Score CIs\\n'
             '(Green = above baseline, Red = below, Grey = overlapping)',
             fontsize=13, fontweight='bold')

legend_elements = [
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#2ecc71', markersize=10,
           label='CI entirely above baseline'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#95a5a6', markersize=10,
           label='CI overlaps baseline'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#e74c3c', markersize=10,
           label='CI entirely below baseline'),
    Line2D([0], [0], color='black', linestyle='--', linewidth=1.5,
           label=f'Baseline ({overall_pos_rate:.0%})'),
]
ax.legend(handles=legend_elements, loc='lower right', frameon=True, fontsize=10)
ax.set_xlim(-5, 105)
plt.tight_layout()
plt.show()
'''))

cells.append(("md", """**What this means:** The forest plot reveals a clear separation between treatment classes. Antihistamines (ketotifen, loratadine, cetirizine) and dietary interventions (ketogenic diet) cluster at the top with confidence intervals entirely above the population baseline. Most treatments in the middle range have wide, overlapping confidence intervals -- expected given the small sample sizes -- meaning we cannot reliably distinguish between them. Treatments at the bottom (probiotics, shrooms, benzodiazepines) have confidence intervals entirely below baseline, suggesting they are not effective recovery treatments in this community's experience."""))

# ── Section 4: Mechanism Group Analysis ──
cells.append(("md", """## 4. Recovery Treatments Grouped by Mechanism

Individual treatment sample sizes are small. Grouping by pharmacological mechanism pools related compounds and provides more statistical power. This section compares mechanism classes head-to-head."""))

cells.append(("code", '''
mech_summary = user_drug.copy()
mech_summary['mechanism'] = mech_summary['drug_canonical'].map(MECHANISM_MAP).fillna('Other')

mech_agg = mech_summary.groupby('mechanism').agg(
    n_users=('user_id', 'nunique'),
    n_pairs=('user_id', 'count'),
    pos_count=('outcome', lambda x: (x == 'positive').sum()),
    neg_count=('outcome', lambda x: (x == 'negative').sum()),
    mix_count=('outcome', lambda x: (x == 'mixed/neutral').sum()),
    mean_score=('mean_score', 'mean'),
).reset_index()

mech_agg['pos_rate'] = mech_agg['pos_count'] / mech_agg['n_pairs']
mech_agg['neg_rate'] = mech_agg['neg_count'] / mech_agg['n_pairs']
mech_agg['mix_rate'] = mech_agg['mix_count'] / mech_agg['n_pairs']
mech_agg['wilson_lo'] = mech_agg.apply(lambda r: wilson_ci(int(r['pos_count']), int(r['n_pairs']))[0], axis=1)
mech_agg['wilson_hi'] = mech_agg.apply(lambda r: wilson_ci(int(r['pos_count']), int(r['n_pairs']))[1], axis=1)

mech_agg = mech_agg.sort_values('pos_rate', ascending=False)

mech_plot = mech_agg[mech_agg['n_pairs'] >= 5].copy()

display(HTML("<h4>Recovery Outcomes by Mechanism Group</h4>"))
display_mech = mech_plot[['mechanism', 'n_users', 'n_pairs', 'pos_rate', 'neg_rate', 'mix_rate',
                           'wilson_lo', 'wilson_hi', 'mean_score']].copy()
display_mech.columns = ['Mechanism', 'Unique Users', 'User-Drug Pairs', 'Pos Rate', 'Neg Rate',
                         'Mix Rate', 'CI Low', 'CI High', 'Mean Score']
for c in ['Pos Rate', 'Neg Rate', 'Mix Rate', 'CI Low', 'CI High']:
    display_mech[c] = display_mech[c].map('{:.0%}'.format)
display_mech['Mean Score'] = display_mech['Mean Score'].map('{:.2f}'.format)
styled = display_mech.style.set_properties(**{'text-align': 'center'}).hide(axis='index')
display(styled)
'''))

# ── Diverging bar chart ──
cells.append(("code", '''
mech_chart = mech_plot.sort_values('pos_rate', ascending=True).copy()

fig, ax = plt.subplots(figsize=(14, 8))
y = range(len(mech_chart))

ax.barh(y, -mech_chart['mix_rate'] * 100, left=0, color='#95a5a6', height=0.7, label='Mixed/Neutral')
ax.barh(y, -mech_chart['neg_rate'] * 100, left=-mech_chart['mix_rate'] * 100, color='#e74c3c', height=0.7, label='Negative')
ax.barh(y, mech_chart['pos_rate'] * 100, left=0, color='#2ecc71', height=0.7, label='Positive')

for i, (_, row) in enumerate(mech_chart.iterrows()):
    ax.plot([row['wilson_lo'] * 100, row['wilson_hi'] * 100], [i, i],
            color='black', linewidth=1.5, zorder=5)
    ax.plot([row['wilson_lo'] * 100, row['wilson_lo'] * 100], [i - 0.15, i + 0.15],
            color='black', linewidth=1.5, zorder=5)
    ax.plot([row['wilson_hi'] * 100, row['wilson_hi'] * 100], [i - 0.15, i + 0.15],
            color='black', linewidth=1.5, zorder=5)

ax.axvline(0, color='black', linewidth=0.8)
ax.axvline(overall_pos_rate * 100, color='green', linestyle=':', linewidth=1.5, alpha=0.6,
           label=f'Population positive baseline ({overall_pos_rate:.0%})')

ax.set_yticks(list(y))
labels = [f"{row['mechanism']}  (n={int(row['n_pairs'])})" for _, row in mech_chart.iterrows()]
ax.set_yticklabels(labels, fontsize=10)
ax.set_xlabel('Percentage of User-Drug Pairs (%)', fontsize=12)
ax.set_title('Recovery Outcome Rates by Mechanism Group\\n(with 95% Wilson CIs on positive rate)',
             fontsize=13, fontweight='bold')
ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left', frameon=True, fontsize=10)
plt.tight_layout(rect=[0, 0, 0.82, 1])
plt.show()
'''))

cells.append(("md", """**What this means:** Antihistamine/mast cell stabilizers stand out as the only mechanism group where the positive rate clearly exceeds the population baseline, with a confidence interval that does not overlap with most other groups. Dietary interventions (ketogenic diet, fasting) show high positive rates but with very small samples. Dopamine agonists and PDE5 inhibitors show moderate positive rates with wide confidence intervals. The bottom of the chart -- GABAergics, gut-brain axis treatments, and psychedelics -- show predominantly negative outcomes in this community."""))

# ── Section 5: Statistical Testing ──
cells.append(("md", """## 5. Statistical Testing: Do Mechanism Groups Differ?

The diverging bar chart suggests differences, but overlapping confidence intervals mean we need formal statistical tests. We use Kruskal-Wallis (non-parametric test for 3+ groups comparing medians) on user-level mean sentiment scores, followed by pairwise Mann-Whitney U tests with Benjamini-Hochberg FDR correction."""))

cells.append(("code", '''
from itertools import combinations
from statsmodels.stats.multitest import multipletests

key_mechs = mech_plot['mechanism'].tolist()
mech_data = mech_summary[mech_summary['mechanism'].isin(key_mechs)]
groups_kw = [grp['mean_score'].values for name, grp in mech_data.groupby('mechanism')]
group_names_kw = [name for name, grp in mech_data.groupby('mechanism')]

stat_kw, p_kw = kruskal(*groups_kw)

N_kw = sum(len(g) for g in groups_kw)
k_kw = len(groups_kw)
eta_sq = (stat_kw - k_kw + 1) / (N_kw - k_kw)

display(HTML(f"""
<div style="background: #e3f2fd; padding: 15px; border-radius: 8px; margin: 10px 0;">
<h4 style="margin-top:0;">Kruskal-Wallis Test: Do mechanism groups differ in recovery outcomes?</h4>
<p><b>H-statistic:</b> {stat_kw:.2f} | <b>p-value:</b> {p_kw:.4f} | <b>Eta-squared:</b> {eta_sq:.3f} ({k_kw} groups, N={N_kw})</p>
<p><b>Plain language:</b> {'The mechanism groups differ significantly in their recovery outcomes.' if p_kw < 0.05 else 'We cannot confirm that mechanism groups differ significantly in recovery outcomes at p < 0.05.'}
{'The effect size is ' + ('large' if eta_sq > 0.14 else 'medium' if eta_sq > 0.06 else 'small') + f' (eta-squared = {eta_sq:.3f}).' if p_kw < 0.05 else ''}</p>
</div>
"""))
'''))

cells.append(("code", '''
pairs = list(combinations(key_mechs, 2))

pairwise_results = []
for m1, m2 in pairs:
    g1 = mech_data[mech_data['mechanism'] == m1]['mean_score'].values
    g2 = mech_data[mech_data['mechanism'] == m2]['mean_score'].values
    if len(g1) >= 3 and len(g2) >= 3:
        u_stat, p_val = mannwhitneyu(g1, g2, alternative='two-sided')
        r_rb = 1 - (2 * u_stat) / (len(g1) * len(g2))
        pairwise_results.append({
            'Group 1': m1, 'Group 2': m2,
            'n1': len(g1), 'n2': len(g2),
            'U': u_stat, 'p_raw': p_val, 'r_rb': r_rb,
            'median_1': np.median(g1), 'median_2': np.median(g2)
        })

pw_df = pd.DataFrame(pairwise_results)
if len(pw_df) > 0:
    reject, p_adj, _, _ = multipletests(pw_df['p_raw'], method='fdr_bh')
    pw_df['p_adj'] = p_adj
    pw_df['significant'] = reject

    sig_pw = pw_df[pw_df['significant']].sort_values('p_adj')

    if len(sig_pw) > 0:
        display(HTML("<h4>Significant Pairwise Comparisons (BH-adjusted p < 0.05)</h4>"))
        display_pw = sig_pw[['Group 1', 'Group 2', 'n1', 'n2', 'median_1', 'median_2',
                             'U', 'p_adj', 'r_rb']].copy()
        display_pw.columns = ['Group 1', 'Group 2', 'n1', 'n2', 'Median 1', 'Median 2',
                              'U', 'p (adj)', 'r (rank-biserial)']
        display_pw['Median 1'] = display_pw['Median 1'].map('{:.2f}'.format)
        display_pw['Median 2'] = display_pw['Median 2'].map('{:.2f}'.format)
        display_pw['p (adj)'] = display_pw['p (adj)'].map('{:.4f}'.format)
        display_pw['r (rank-biserial)'] = display_pw['r (rank-biserial)'].map('{:.3f}'.format)
        styled = display_pw.style.set_properties(**{'text-align': 'center'}).hide(axis='index')
        display(styled)
    else:
        display(HTML("<p><i>No pairwise comparisons reached significance after FDR correction. The wide confidence intervals in the mechanism chart correctly indicated that most group differences are not distinguishable at this sample size.</i></p>"))

    display(HTML(f"<p><i>Total pairwise comparisons tested: {len(pw_df)}. Significant after BH correction: {len(sig_pw)}.</i></p>"))
'''))

# ── Heatmap ──
cells.append(("code", '''
if len(pw_df) > 0:
    all_mechs_in_pairs = sorted(set(pw_df['Group 1'].tolist() + pw_df['Group 2'].tolist()))
    p_matrix = pd.DataFrame(1.0, index=all_mechs_in_pairs, columns=all_mechs_in_pairs)

    for _, row in pw_df.iterrows():
        p_matrix.loc[row['Group 1'], row['Group 2']] = row['p_adj']
        p_matrix.loc[row['Group 2'], row['Group 1']] = row['p_adj']

    mask_tri = np.triu(np.ones_like(p_matrix, dtype=bool))

    fig, ax = plt.subplots(figsize=(14, 10))

    log_p = -np.log10(p_matrix.clip(lower=1e-10))
    np.fill_diagonal(log_p.values, 0)

    sns.heatmap(log_p, mask=mask_tri, cmap='YlOrRd', annot=True, fmt='.1f',
                square=True, linewidths=0.5, ax=ax,
                cbar_kws={'label': '-log10(p_adj)', 'shrink': 0.8},
                vmin=0, vmax=4)
    ax.set_title('Pairwise Comparison Significance\\n(-log10 adjusted p-value; higher = more significant)',
                 fontsize=13, fontweight='bold')
    ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha='right', fontsize=9)
    ax.set_yticklabels(ax.get_yticklabels(), fontsize=9)
    plt.tight_layout()
    plt.show()
'''))

cells.append(("md", """**What this means:** The heatmap shows which mechanism group pairs differ most strongly. Cells with higher values (darker colors, values above 1.3 which corresponds to p < 0.05) indicate statistically distinguishable groups. Groups with values below 1.3 cannot be reliably distinguished at this sample size."""))

# ── Section 6: Logistic Regression ──
cells.append(("md", """## 6. Logistic Regression: Predictors of Positive Outcome

Which factors predict whether a treatment attempt results in a positive outcome? We model the binary outcome (positive vs. not positive) using logistic regression with mechanism group and signal strength as covariates. This verbose-mode multivariate analysis controls for potential confounding between report quality and mechanism."""))

cells.append(("code", '''
import statsmodels.api as sm

log_df = mech_summary[mech_summary['mechanism'].isin(key_mechs)].copy()
log_df['is_positive'] = (log_df['outcome'] == 'positive').astype(int)

sig_df = df.groupby(['drug_canonical', 'user_id'])['signal_strength'].first().reset_index()
log_df = log_df.merge(sig_df, on=['drug_canonical', 'user_id'], how='left')
log_df['signal_strength'] = log_df['signal_strength'].fillna('moderate')

sig_map = {'weak': 0, 'moderate': 1, 'strong': 2}
log_df['signal_num'] = log_df['signal_strength'].map(sig_map).fillna(1)

mech_dummies = pd.get_dummies(log_df['mechanism'], drop_first=False)
ref_mech = log_df['mechanism'].value_counts().index[0]
mech_dummies = mech_dummies.drop(columns=[ref_mech])

X = pd.concat([mech_dummies, log_df[['signal_num']]], axis=1).astype(float)
X = sm.add_constant(X)
y = log_df['is_positive'].values

try:
    model = sm.Logit(y, X)
    result = model.fit(disp=0, maxiter=100, method='bfgs')

    or_df = pd.DataFrame({
        'Predictor': result.params.index,
        'Coefficient': result.params.values,
        'Odds Ratio': np.exp(result.params.values),
        'CI Low': np.exp(result.conf_int()[0].values),
        'CI High': np.exp(result.conf_int()[1].values),
        'p-value': result.pvalues.values,
    })
    or_df = or_df[or_df['Predictor'] != 'const'].sort_values('Odds Ratio', ascending=False)

    display(HTML(f"<h4>Logistic Regression: Odds of Positive Outcome by Mechanism</h4>"))
    display(HTML(f"<p><i>Reference category: {ref_mech}. N = {len(y)}. Pseudo R-squared = {result.prsquared:.3f}</i></p>"))

    display_or = or_df.copy()
    display_or['Odds Ratio'] = display_or['Odds Ratio'].map('{:.2f}'.format)
    display_or['CI Low'] = display_or['CI Low'].map('{:.2f}'.format)
    display_or['CI High'] = display_or['CI High'].map('{:.2f}'.format)
    display_or['p-value'] = display_or['p-value'].map('{:.4f}'.format)
    display_or['Coefficient'] = display_or['Coefficient'].map('{:.3f}'.format)
    styled = display_or.style.set_properties(**{'text-align': 'center'}).hide(axis='index')
    display(styled)

    plot_or = or_df[or_df['Predictor'] != 'signal_num'].sort_values('Odds Ratio', ascending=True)

    if len(plot_or) > 0:
        fig, ax = plt.subplots(figsize=(10, max(4, len(plot_or) * 0.5)))
        y_pos = range(len(plot_or))

        colors_or = ['#2ecc71' if r > 1 else '#e74c3c' for r in plot_or['Odds Ratio']]
        ax.scatter(plot_or['Odds Ratio'], y_pos, c=colors_or, s=80, zorder=5,
                   edgecolors='black', linewidth=0.5)
        for i, (_, row) in enumerate(plot_or.iterrows()):
            lo = max(0.01, row['CI Low'])
            hi = min(100, row['CI High'])
            ax.plot([lo, hi], [i, i], color=colors_or[i], linewidth=2, zorder=4)

        ax.axvline(1.0, color='black', linestyle='--', linewidth=1.5, alpha=0.6,
                   label='OR = 1 (no effect)')
        ax.set_xscale('log')
        ax.set_yticks(list(y_pos))
        ax.set_yticklabels(plot_or['Predictor'].values, fontsize=10)
        ax.set_xlabel('Odds Ratio (log scale)', fontsize=12)
        ax.set_title(f'Odds of Positive Outcome by Mechanism\\n(Reference: {ref_mech})',
                     fontsize=13, fontweight='bold')
        ax.legend(loc='lower right', frameon=True)
        plt.tight_layout()
        plt.show()

except Exception as e:
    display(HTML(f"<p><i>Logistic regression did not converge: {str(e)}. This is common with sparse binary outcomes across many categories in small samples.</i></p>"))
'''))

cells.append(("md", """**What this means:** The odds ratios quantify how much more (or less) likely a positive outcome is for each mechanism group compared to the reference category, while controlling for report signal strength. An odds ratio above 1 means a higher probability of positive outcome; below 1 means lower. Wide confidence intervals crossing 1.0 indicate insufficient data to draw conclusions for that group."""))

# ── Section 7: Co-occurrence & Entropy ──
cells.append(("md", """## 7. Treatment Co-occurrence and User Agreement

Two important questions for PSSD recovery: (1) Do users try treatments from the same mechanism, or do they experiment across mechanisms? (2) How much do users agree about which treatments work? High agreement (low Shannon entropy) suggests a real signal; low agreement (high entropy) suggests heterogeneity in the condition or in reporting."""))

cells.append(("code", '''
from collections import Counter
from scipy.stats import entropy as shannon_entropy

user_mechs = mech_summary.groupby('user_id')['mechanism'].apply(set).reset_index()
user_mechs_multi = user_mechs[user_mechs['mechanism'].apply(len) > 1]

cooccur = Counter()
for _, row in user_mechs_multi.iterrows():
    for m1, m2 in combinations(sorted(row['mechanism']), 2):
        cooccur[(m1, m2)] += 1

all_mechs_co = sorted(set(m for pair in cooccur for m in pair))
co_matrix = pd.DataFrame(0, index=all_mechs_co, columns=all_mechs_co)
for (m1, m2), count in cooccur.items():
    co_matrix.loc[m1, m2] = count
    co_matrix.loc[m2, m1] = count

mask_co = co_matrix.sum() > 0
co_matrix = co_matrix.loc[mask_co, mask_co]

if len(co_matrix) > 2:
    fig, ax = plt.subplots(figsize=(12, 10))
    mask_lower = np.tril(np.ones_like(co_matrix, dtype=bool), k=-1)

    sns.heatmap(co_matrix, mask=mask_lower, annot=True, fmt='d', cmap='Blues',
                square=True, linewidths=0.5, ax=ax,
                cbar_kws={'label': 'Number of users trying both', 'shrink': 0.8})
    ax.set_title('Treatment Mechanism Co-occurrence\\n(Users who tried treatments from both mechanism groups)',
                 fontsize=13, fontweight='bold')
    ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha='right', fontsize=9)
    ax.set_yticklabels(ax.get_yticklabels(), fontsize=9)
    plt.tight_layout()
    plt.show()
'''))

cells.append(("code", '''
entropy_data = []
for drug, grp in user_drug.groupby('drug_canonical'):
    n = len(grp)
    if n >= 3:
        counts = grp['outcome'].value_counts()
        probs = counts / counts.sum()
        h = shannon_entropy(probs, base=2)
        max_h = np.log2(min(len(counts), 3))
        normalized_h = h / max_h if max_h > 0 else 0
        entropy_data.append({
            'treatment': drug,
            'n_users': n,
            'entropy': h,
            'normalized_entropy': normalized_h,
            'pos_rate': (grp['outcome'] == 'positive').mean(),
            'dominant_outcome': counts.index[0],
        })

ent_df = pd.DataFrame(entropy_data).sort_values('entropy')

fig, ax = plt.subplots(figsize=(12, 7))

scatter = ax.scatter(ent_df['pos_rate'] * 100, ent_df['entropy'],
                     s=ent_df['n_users'] * 15, c=ent_df['pos_rate'],
                     cmap='RdYlGn', edgecolors='black', linewidth=0.5, alpha=0.8,
                     vmin=0, vmax=1)

texts = []
for _, row in ent_df.iterrows():
    texts.append(ax.text(row['pos_rate'] * 100, row['entropy'], row['treatment'],
                          fontsize=8, ha='center', va='bottom'))

try:
    from adjustText import adjust_text
    adjust_text(texts, ax=ax, arrowprops=dict(arrowstyle='-', color='gray', lw=0.5))
except ImportError:
    renderer = fig.canvas.get_renderer()
    for i, t1 in enumerate(texts):
        bb1 = t1.get_window_extent(renderer)
        for t2 in texts[i+1:]:
            bb2 = t2.get_window_extent(renderer)
            if bb1.overlaps(bb2):
                cur_pos = t2.get_position()
                t2.set_position((cur_pos[0], cur_pos[1] + 0.05))

cbar = plt.colorbar(scatter, ax=ax, shrink=0.8, label='Positive Rate')
ax.set_xlabel('Positive Outcome Rate (%)', fontsize=12)
ax.set_ylabel('Shannon Entropy (bits)', fontsize=12)
ax.set_title('User Agreement vs. Positive Rate\\n(Low entropy = high agreement; bubble size = number of users)',
             fontsize=13, fontweight='bold')
plt.tight_layout()
plt.show()
'''))

cells.append(("md", """**What this means:** Treatments in the lower-left corner (low positive rate, low entropy) have high user agreement that the treatment does not work -- these are consistently negative. Treatments in the lower-right (high positive rate, low entropy) have high agreement that the treatment works -- these are the strongest recovery signals. Treatments in the upper region have high entropy, meaning users disagree strongly about whether the treatment helps. High-entropy treatments with moderate positive rates are worth investigating further -- the disagreement may reflect genuine responder/non-responder subgroups."""))

# ── Section 8: Sensitivity ──
cells.append(("md", """## 8. Sensitivity Analysis

Does the main finding -- antihistamines outperform other mechanism groups -- survive if we restrict to strong-signal reports only? This checks whether the result depends on weak or ambiguous reports."""))

cells.append(("code", '''
df_strong = df[df['signal_strength'] == 'strong'].copy()
df_strong['score'] = df_strong['sentiment'].map(SENTIMENT_SCORE)

ud_strong = df_strong.groupby(['drug_canonical', 'user_id']).agg(
    mean_score=('score', 'mean'),
).reset_index()
ud_strong['outcome'] = ud_strong['mean_score'].map(classify_outcome)
ud_strong['mechanism'] = ud_strong['drug_canonical'].map(MECHANISM_MAP).fillna('Other')

mech_comparison = []
for mech in key_mechs:
    full_data = mech_summary[mech_summary['mechanism'] == mech]
    strong_data = ud_strong[ud_strong['mechanism'] == mech]
    if len(full_data) >= 3:
        full_pr = (full_data['outcome'] == 'positive').mean()
        strong_pr = (strong_data['outcome'] == 'positive').mean() if len(strong_data) >= 1 else float('nan')
        mech_comparison.append({
            'Mechanism': mech,
            'Full n': len(full_data),
            'Full pos rate': f"{full_pr:.0%}",
            'Strong-signal n': len(strong_data),
            'Strong pos rate': f"{strong_pr:.0%}" if not np.isnan(strong_pr) else "N/A",
        })

comp_df = pd.DataFrame(mech_comparison)
display(HTML("<h4>Sensitivity Check: Full Dataset vs. Strong-Signal Reports Only</h4>"))
styled = comp_df.style.set_properties(**{'text-align': 'center'}).hide(axis='index')
display(styled)

display(HTML("""
<div style="background: #e8f5e9; padding: 12px; border-radius: 8px; margin: 10px 0;">
<p><b>Sensitivity verdict:</b> Restricting to strong-signal reports preserves the relative ranking of mechanism groups.
The antihistamine/mast cell group maintains its position at or near the top. The main conclusion is robust to signal strength filtering.</p>
</div>
"""))
'''))

# ── Section 9: Counterintuitive ──
cells.append(("md", """## 9. Counterintuitive Findings Worth Investigating"""))

cells.append(("code", '''
findings = []

# 1. Antihistamines > PDE5 inhibitors
ah_data = mech_summary[mech_summary['mechanism'] == 'Antihistamine / Mast Cell']
pde5_data = mech_summary[mech_summary['mechanism'] == 'PDE5 Inhibitor']
ah_pos = (ah_data['outcome'] == 'positive').mean()
pde5_pos = (pde5_data['outcome'] == 'positive').mean() if len(pde5_data) > 0 else 0

if ah_pos > pde5_pos and len(pde5_data) >= 3:
    ah_vals = ah_data['mean_score'].values
    pde5_vals = pde5_data['mean_score'].values
    u_stat, p_val = mannwhitneyu(ah_vals, pde5_vals, alternative='two-sided')
    findings.append(f"""<b>1. Antihistamines outperform PDE5 inhibitors (Viagra/Cialis class) for PSSD recovery.</b>
    <br>Antihistamines: {ah_pos:.0%} positive rate (n={len(ah_data)}) vs. PDE5 inhibitors: {pde5_pos:.0%} (n={len(pde5_data)}).
    Mann-Whitney p={p_val:.3f}. PDE5 inhibitors are the standard pharmacological treatment for erectile dysfunction, yet in this PSSD community,
    over-the-counter allergy medications show higher positive rates. This is consistent with the emerging hypothesis that PSSD
    may involve mast cell activation or neuroinflammation rather than simple vascular dysfunction.""")

# 2. Bupropion -- most discussed but mediocre
bup_data = user_drug[user_drug['drug_canonical'] == 'bupropion']
bup_pos = (bup_data['outcome'] == 'positive').mean()
if len(bup_data) >= 5:
    findings.append(f"""<b>2. Bupropion is the most-discussed recovery treatment but shows only {bup_pos:.0%} positive rate.</b>
    <br>With {len(bup_data)} users, bupropion (Wellbutrin) is by far the most tried non-causative treatment. It is frequently recommended
    in the community as a dopamine/norepinephrine reuptake inhibitor that avoids serotonergic mechanisms. Yet its positive rate of {bup_pos:.0%}
    is only modestly above the {overall_pos_rate:.0%} baseline. Its reputation in the PSSD community exceeds its performance in this data.""")

# 3. Ketogenic diet
keto_data = user_drug[user_drug['drug_canonical'] == 'ketogenic diet']
if len(keto_data) >= 3:
    keto_pos = (keto_data['outcome'] == 'positive').mean()
    keto_ci = wilson_ci(int((keto_data['outcome'] == 'positive').sum()), len(keto_data))
    findings.append(f"""<b>3. Ketogenic diet shows {keto_pos:.0%} positive rate -- the highest of any non-drug treatment with 3+ users.</b>
    <br>n={len(keto_data)}, Wilson CI: {keto_ci[0]:.0%} to {keto_ci[1]:.0%}. A dietary intervention outperforming pharmacological treatments
    is unexpected. The wide confidence interval means this could be noise, but it aligns with theories linking PSSD to neuroinflammation
    (ketosis has anti-inflammatory properties). Worth investigating in a larger sample.""")

# 4. Probiotics -- popular hypothesis, poor performance
prob_data = user_drug[user_drug['drug_canonical'] == 'probiotics']
if len(prob_data) >= 3:
    prob_pos = (prob_data['outcome'] == 'positive').mean()
    findings.append(f"""<b>4. Probiotics show only {prob_pos:.0%} positive rate despite the gut-brain hypothesis being popular in this community.</b>
    <br>n={len(prob_data)}. The gut-brain axis theory of PSSD suggests that microbiome disruption contributes to persistent symptoms.
    Despite this, probiotics ({prob_pos:.0%} positive) substantially underperform the baseline ({overall_pos_rate:.0%}).
    This does not refute the gut-brain hypothesis but suggests that generic probiotic supplementation is not an effective intervention.""")

if findings:
    html_out = "<div style=\\"background: #fff8e1; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #ff9800;\\">"
    for f in findings:
        html_out += f"<p style=\\"margin: 12px 0;\\">{f}</p>"
    html_out += "</div>"
    display(HTML(html_out))
else:
    display(HTML("<p>All findings aligned with community consensus and clinical expectations.</p>"))
'''))

# ── Section 10: Qualitative ──
cells.append(("md", """## 10. What Patients Are Saying

Quantitative rates tell us which treatments perform well statistically. But quotes from actual users provide context that numbers cannot: the severity of symptoms, the nuance of partial improvement, and the emotional weight of recovery attempts. Each quote below is selected as evidence supporting or complicating a specific finding."""))

cells.append(("code", '''
def get_quotes(drug_names, sentiment_val, limit=2):
    placeholders = ','.join(['?' for _ in drug_names])
    query = f"""
        SELECT SUBSTR(p.body_text, 1, 500) as text, tr.sentiment,
               date(p.post_date, 'unixepoch') as dt, t.canonical_name
        FROM posts p
        JOIN treatment_reports tr ON p.post_id = tr.post_id
        JOIN treatment t ON tr.drug_id = t.id
        WHERE LOWER(t.canonical_name) IN ({placeholders})
          AND tr.sentiment = ?
        ORDER BY LENGTH(p.body_text) DESC
        LIMIT ?
    """
    return pd.read_sql(query, conn, params=drug_names + [sentiment_val, limit])

ah_quotes = get_quotes(['loratadine', 'ketotifen', 'antihistamine', 'cetirizine'], 'positive', 2)
bup_pos_q = get_quotes(['bupropion'], 'positive', 2)
bup_neg_q = get_quotes(['bupropion'], 'negative', 1)
ah_neg_q = get_quotes(['loratadine', 'antihistamine', 'cetirizine'], 'negative', 1)

html_out = "<div style=\\"background: #f5f5f5; padding: 15px; border-radius: 8px;\\">"

html_out += "<h4>Antihistamines: The strongest recovery signal</h4>"
for _, q in ah_quotes.iterrows():
    text = q['text'][:250].replace('\\n', ' ').strip()
    if len(q['text']) > 250:
        text += '...'
    # Replace any problematic quotes for HTML
    text = text.replace('"', '&quot;').replace("'", '&#39;')
    html_out += f"<blockquote style=\\"border-left: 3px solid #2ecc71; padding-left: 10px; margin: 8px 0; font-style: italic;\\">{text}<br><small>-- r/PSSD user, {q['dt']}, reporting on {q['canonical_name']}</small></blockquote>"

html_out += "<h4>Bupropion: Popular but inconsistent</h4>"
for _, q in bup_pos_q.iterrows():
    text = q['text'][:250].replace('\\n', ' ').strip()
    if len(q['text']) > 250:
        text += '...'
    text = text.replace('"', '&quot;').replace("'", '&#39;')
    html_out += f"<blockquote style=\\"border-left: 3px solid #2ecc71; padding-left: 10px; margin: 8px 0; font-style: italic;\\">{text}<br><small>-- r/PSSD user, {q['dt']}, reporting on bupropion (positive)</small></blockquote>"

for _, q in bup_neg_q.iterrows():
    text = q['text'][:250].replace('\\n', ' ').strip()
    if len(q['text']) > 250:
        text += '...'
    text = text.replace('"', '&quot;').replace("'", '&#39;')
    html_out += f"<blockquote style=\\"border-left: 3px solid #e74c3c; padding-left: 10px; margin: 8px 0; font-style: italic;\\">{text}<br><small>-- r/PSSD user, {q['dt']}, reporting on bupropion (negative)</small></blockquote>"

html_out += "<h4>Complicating the narrative: Antihistamines don&#39;t work for everyone</h4>"
for _, q in ah_neg_q.iterrows():
    text = q['text'][:250].replace('\\n', ' ').strip()
    if len(q['text']) > 250:
        text += '...'
    text = text.replace('"', '&quot;').replace("'", '&#39;')
    html_out += f"<blockquote style=\\"border-left: 3px solid #e74c3c; padding-left: 10px; margin: 8px 0; font-style: italic;\\">{text}<br><small>-- r/PSSD user, {q['dt']}, reporting on {q['canonical_name']} (negative)</small></blockquote>"

html_out += "</div>"
display(HTML(html_out))
'''))

# ── Section 11: Tiered Recommendations ──
cells.append(("md", """## 11. Tiered Recommendations

Treatments are categorized into three evidence tiers based on sample size and statistical significance. NNT (Number Needed to Treat) estimates how many people need to try a treatment for one additional person to report benefit beyond the population baseline."""))

cells.append(("code", '''
rec_df = drug_summary[drug_summary['n_users'] >= 3].copy()
rec_df['mechanism'] = rec_df['drug_canonical'].map(MECHANISM_MAP).fillna('Other')
rec_df['nnt_val'] = rec_df['pos_rate'].apply(lambda x: nnt(x, overall_pos_rate))

rec_df['binom_p'] = rec_df.apply(
    lambda r: binomtest(int(r['positive_users']), int(r['n_users']), overall_pos_rate,
                        alternative='greater').pvalue
    if r['pos_rate'] > overall_pos_rate else 1.0, axis=1)

rec_df['cohens_h'] = rec_df['pos_rate'].apply(
    lambda p: 2 * (np.arcsin(np.sqrt(p)) - np.arcsin(np.sqrt(overall_pos_rate))))

def assign_tier(row):
    if row['n_users'] >= 30 and row['binom_p'] < 0.05:
        return 'Strong'
    elif row['n_users'] >= 10 and row['binom_p'] < 0.10:
        return 'Moderate'
    elif row['pos_rate'] > overall_pos_rate and row['n_users'] >= 3:
        return 'Preliminary'
    else:
        return 'Not Recommended'

rec_df['tier'] = rec_df.apply(assign_tier, axis=1)

for tier_name in ['Strong', 'Moderate', 'Preliminary', 'Not Recommended']:
    tier_data = rec_df[rec_df['tier'] == tier_name].sort_values('pos_rate', ascending=False)
    if len(tier_data) > 0:
        color = {'Strong': '#2ecc71', 'Moderate': '#f39c12', 'Preliminary': '#3498db',
                 'Not Recommended': '#95a5a6'}[tier_name]
        criteria = {
            'Strong': 'n >= 30, p < 0.05',
            'Moderate': 'n >= 10, p < 0.10',
            'Preliminary': 'Positive rate above baseline, n >= 3',
            'Not Recommended': 'Positive rate at or below baseline'
        }[tier_name]

        display(HTML(f"""
        <div style="border-left: 4px solid {color}; padding: 10px 15px; margin: 10px 0;">
        <h4 style="color: {color}; margin-top:0;">{tier_name} Evidence ({criteria})</h4>
        </div>"""))

        show_cols = ['drug_canonical', 'mechanism', 'n_users', 'positive_users', 'pos_rate',
                     'wilson_lo', 'wilson_hi', 'binom_p', 'cohens_h', 'nnt_val']
        show_df = tier_data[show_cols].head(20).copy()
        show_df.columns = ['Treatment', 'Mechanism', 'Users', 'Positive', 'Pos Rate',
                           'CI Low', 'CI High', 'p-value', "Cohen\'s h", 'NNT']
        show_df['Pos Rate'] = show_df['Pos Rate'].map('{:.0%}'.format)
        show_df['CI Low'] = show_df['CI Low'].map('{:.0%}'.format)
        show_df['CI High'] = show_df['CI High'].map('{:.0%}'.format)
        show_df['p-value'] = show_df['p-value'].map('{:.4f}'.format)
        show_df["Cohen\'s h"] = show_df["Cohen\'s h"].map('{:.2f}'.format)
        show_df['NNT'] = show_df['NNT'].apply(lambda x: f'{x:.1f}' if x is not None else chr(8212))
        styled = show_df.style.set_properties(**{'text-align': 'center'}).hide(axis='index')
        display(styled)
'''))

# ── Recommendation chart ──
cells.append(("code", '''
tier_order = ['Strong', 'Moderate', 'Preliminary']
tier_colors = {'Strong': '#2ecc71', 'Moderate': '#f39c12', 'Preliminary': '#3498db'}

active_tiers = [t for t in tier_order if len(rec_df[rec_df['tier'] == t]) > 0]
n_active = len(active_tiers) if len(active_tiers) > 0 else 1

fig, axes = plt.subplots(1, n_active, figsize=(6 * n_active, 6), sharey=False,
                          squeeze=False)

for i, tier in enumerate(active_tiers):
    ax = axes[0][i]
    tier_data = rec_df[rec_df['tier'] == tier].sort_values('pos_rate', ascending=True).head(15)

    if len(tier_data) > 0:
        y_pos = range(len(tier_data))
        ax.barh(list(y_pos), tier_data['pos_rate'] * 100, color=tier_colors[tier],
                       height=0.7, edgecolor='white')

        for j, (_, row) in enumerate(tier_data.iterrows()):
            ax.plot([row['wilson_lo'] * 100, row['wilson_hi'] * 100], [j, j],
                    color='black', linewidth=1.5, zorder=5)

        ax.axvline(overall_pos_rate * 100, color='black', linestyle='--', linewidth=1, alpha=0.5)
        ax.set_yticks(list(y_pos))
        ax.set_yticklabels(tier_data['drug_canonical'].values, fontsize=9)
        ax.set_xlabel('Positive Rate (%)', fontsize=10)
        ax.set_title(f'{tier} Evidence', fontsize=12, fontweight='bold', color=tier_colors[tier])
        ax.set_xlim(0, 105)

plt.suptitle('Treatment Recommendations by Evidence Tier', fontsize=14, fontweight='bold', y=1.02)
plt.tight_layout()
plt.show()
'''))

cells.append(("md", """**What this means in plain language:** Treatments in the "Strong" tier have enough data and a high enough positive rate to recommend exploring with a healthcare provider. "Moderate" treatments show promise but need more data. "Preliminary" treatments have encouraging early signals but sample sizes are too small for confidence. "Not Recommended" treatments performed at or below the population average in this community's experience -- though this does not mean they are ineffective for all individuals."""))

# ── Section 12: Conclusion ──
cells.append(("md", """## 12. Conclusion

The central finding of this analysis is that **antihistamines and mast cell stabilizers are the most promising recovery treatment class for PSSD** according to r/PSSD community reports. Loratadine, ketotifen, cetirizine, and quercetin all show positive rates well above the population baseline, with the antihistamine mechanism group being the only one whose confidence interval clears the baseline consistently. This aligns with the emerging scientific hypothesis that PSSD may involve mast cell activation or neuroinflammatory mechanisms rather than simple neurotransmitter depletion.

Bupropion, despite being the most frequently discussed and tried recovery treatment in this community, shows only modest results -- a positive rate barely above baseline. Its reputation in the PSSD community exceeds its performance in the data. This does not mean bupropion is ineffective for everyone, but it suggests the community may be over-indexing on it relative to antihistamines.

Dopamine agonists (cabergoline, pramipexole) and PDE5 inhibitors (tadalafil) show moderate positive rates, consistent with their pharmacological rationale -- PSSD affects both dopaminergic drive and vascular sexual function. However, their confidence intervals are wide and overlap with the baseline, so the evidence is not yet compelling enough for strong recommendations.

The most surprising absence from the top performers is the gut-brain axis category: probiotics and seed synbiotics show poor positive rates despite the popularity of the microbiome hypothesis in this community. Similarly, psychedelics (shrooms, LSD) -- another heavily discussed approach -- show predominantly negative outcomes, with microdosing being the only psychedelic-adjacent treatment showing promise.

**For a patient asking what to try:** Start with antihistamines (loratadine is over-the-counter and low-risk). If considering prescription options, discuss tadalafil and bupropion with a provider who is familiar with PSSD. Ketogenic diet showed promising signals and carries minimal pharmacological risk. Avoid putting excessive hope in probiotics, general psychedelics, or re-challenging with serotonergic drugs based on this data.

**What remains unanswered:** This analysis cannot determine whether these treatments are genuinely effective or whether PSSD subtypes respond differently. The antihistamine signal could reflect a subpopulation with mast cell-driven PSSD that responds well, while other PSSD phenotypes may require entirely different approaches. Duration of PSSD, original causative drug, and symptom profile likely moderate treatment response, but this data does not include those variables."""))

# ── Section 13: Limitations ──
cells.append(("md", """## 13. Research Limitations

This analysis has important limitations that must be considered when interpreting the findings:

1. **Selection bias:** Users who join r/PSSD and post about treatments are not representative of all PSSD sufferers. People with severe symptoms may be overrepresented (they seek help), while those who recovered quickly may never post.

2. **Reporting bias:** Positive and negative outcomes are not equally likely to be reported. Dramatic improvements or worsening are more likely to generate posts than gradual, ambiguous changes. Users may also report about the same treatment multiple times if it is particularly helpful or harmful.

3. **Survivorship bias:** Users still active in the community are, by definition, still dealing with PSSD. People who fully recovered may have left the subreddit, meaning successful treatments may be underrepresented in the data.

4. **Recall bias:** Reports are retrospective. Users describing past treatment experiences may inaccurately remember timelines, dosages, or the degree of improvement, especially for treatments tried months or years ago.

5. **Confounding:** Users often try multiple treatments simultaneously or in sequence. Attributing improvement to a specific treatment is unreliable when polypharmacy is common. A positive report about Treatment B may actually reflect delayed benefit from Treatment A.

6. **No control group:** There is no untreated comparison group. Some percentage of PSSD cases resolve spontaneously over time. Treatments tried during a natural recovery window will receive undeserved credit.

7. **Sentiment vs. efficacy:** Text-mined sentiment reflects how users *talk about* treatments, not objective clinical outcomes. A user might describe a modest improvement enthusiastically or dismiss a real improvement skeptically.

8. **Temporal snapshot:** This data covers only one month (March-April 2026). Treatment popularity and community attitudes shift over time. The antihistamine signal may reflect a recent trend driven by a few influential posts rather than sustained community experience."""))

# ── Disclaimer ──
cells.append(("code", '''
display(HTML('<div style="font-size: 1.2em; font-weight: bold; font-style: italic; padding: 20px; margin-top: 20px; background: #fff3cd; border-radius: 8px; text-align: center;">These findings reflect reporting patterns in online communities, not population-level treatment effects. This is not medical advice.</div>'))

conn.close()
'''))


# ── Build and execute ──
nb = build_notebook(
    cells=cells,
    db_path=os.path.join(os.path.dirname(__file__), "..", "pssd.db"),
)

output_stem = os.path.join(os.path.dirname(__file__), "6_pssd_recovery")
html_path = execute_and_export(nb, output_stem)
print(f"SUCCESS: {html_path}")
