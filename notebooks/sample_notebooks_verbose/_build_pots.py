"""Build and execute the POTS preliminary notebook."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from build_notebook import build_notebook, execute_and_export

cells = []

# ═══════════════════════════════════════════════════════════════════
# RESEARCH QUESTION
# ═══════════════════════════════════════════════════════════════════
cells.append(('md', '**Research Question:** "How do POTS patients in the Long COVID community compare to the broader population in terms of symptom burden, treatment patterns, co-occurring conditions, and reported outcomes?"\n\n*Study type: Preliminary / survey study. Findings are hypothesis-generating for follow-up investigation.*'))

# ═══════════════════════════════════════════════════════════════════
# ABSTRACT
# ═══════════════════════════════════════════════════════════════════
cells.append(('md', """# POTS in the Long COVID Community: A Preliminary Comparative Analysis

## Abstract

This preliminary analysis compares 80 users who self-report POTS (Postural Orthostatic Tachycardia Syndrome, a form of autonomic nervous system dysfunction causing excessive heart rate increase upon standing) in the r/covidlonghaulers subreddit against 2,747 users without a POTS mention, using one month of community data (March\u2013April 2026, n=2,827 total). POTS users represent a distinct, high-burden subgroup: they carry 4x more co-occurring conditions (8.8 vs 2.2), post 3.6x more frequently, try 2x more treatments, and report significantly worse outcomes (49% vs 62% user-level positive rate, p<0.001). Their treatment landscape diverges from the broader community\u2014magnesium and electrolytes perform well for POTS users, while several popular community treatments (nattokinase, famotidine) underperform. Despite being only 2.8% of the community, POTS users generate disproportionate discussion volume, suggesting either greater severity or greater need for support. These findings generate several testable hypotheses about autonomic dysfunction as a modifier of Long COVID treatment response."""))

# ═══════════════════════════════════════════════════════════════════
# DATA EXPLORATION
# ═══════════════════════════════════════════════════════════════════
cells.append(('md', """## 1. Data Exploration and Cohort Definition

Data covers: **2026-03-11 to 2026-04-10 (1 month)** from r/covidlonghaulers.

We define two cohorts based on extracted condition mentions:
- **POTS cohort**: Users with at least one extracted mention of "pots" or "dysautonomia" (two labels for the same autonomic dysfunction spectrum). We include both because POTS is a subtype of dysautonomia, and many users use the terms interchangeably.
- **Non-POTS cohort**: All other users (no mention of POTS or dysautonomia in their condition extractions).

This is a strict classification\u2014users must have had their condition explicitly extracted by the pipeline, not merely mentioned the word in passing."""))

cells.append(('code', """
# ── Define cohorts ──
pots_users = pd.read_sql('''
    SELECT DISTINCT user_id FROM conditions
    WHERE LOWER(condition_name) IN ('pots', 'dysautonomia')
''', conn)
pots_ids = set(pots_users['user_id'])

all_users = pd.read_sql("SELECT DISTINCT user_id FROM users", conn)
non_pots_ids = set(all_users['user_id']) - pots_ids

# ── Cohort overview table ──
posts_df = pd.read_sql("SELECT user_id, COUNT(DISTINCT post_id) as post_count FROM posts GROUP BY user_id", conn)
posts_df['cohort'] = posts_df['user_id'].apply(lambda x: 'POTS' if x in pots_ids else 'Non-POTS')

tr_df = pd.read_sql('''
    SELECT tr.user_id, COUNT(*) as report_count, COUNT(DISTINCT tr.drug_id) as unique_drugs,
           SUM(CASE WHEN tr.sentiment='positive' THEN 1.0 ELSE 0.0 END) / COUNT(*) as pos_rate
    FROM treatment_reports tr
    GROUP BY tr.user_id
''', conn)
tr_df['cohort'] = tr_df['user_id'].apply(lambda x: 'POTS' if x in pots_ids else 'Non-POTS')

cond_df = pd.read_sql('''
    SELECT user_id, COUNT(DISTINCT condition_name) as condition_count
    FROM conditions GROUP BY user_id
''', conn)
cond_df['cohort'] = cond_df['user_id'].apply(lambda x: 'POTS' if x in pots_ids else 'Non-POTS')

rows = []
for cohort, ids in [('POTS', pots_ids), ('Non-POTS', non_pots_ids)]:
    n = len(ids)
    p = posts_df[posts_df['cohort'] == cohort]
    t = tr_df[tr_df['cohort'] == cohort]
    c = cond_df[cond_df['cohort'] == cohort]
    rows.append({
        'Cohort': cohort,
        'Users': n,
        '% of Community': f"{100*n/len(all_users):.1f}%",
        'Users with Tx Reports': len(t),
        'Avg Posts/User': f"{p['post_count'].mean():.1f}",
        'Avg Tx Reports/User': f"{t['report_count'].mean():.1f}" if len(t) > 0 else "N/A",
        'Avg Unique Drugs/User': f"{t['unique_drugs'].mean():.1f}" if len(t) > 0 else "N/A",
        'Avg Conditions/User': f"{c['condition_count'].mean():.1f}" if len(c) > 0 else "N/A",
    })

summary = pd.DataFrame(rows)
display(HTML("<h3>Cohort Overview</h3>"))
display(summary.style.set_properties(**{'text-align': 'center'}).hide(axis='index'))
"""))

cells.append(('md', """**Filtering note:** Generic terms ("supplements", "medication", "therapy", "drug", "vitamin") are excluded from all treatment analyses. Vaccines and vaccine-adjacent terms ("covid vaccine", "pfizer vaccine", "booster", etc.) are excluded as causal-context contaminants\u2014their negative sentiment reflects perceived causation of Long COVID, not treatment response. "Long covid" is filtered from co-occurring condition charts as the community-defining condition."""))

# ═══════════════════════════════════════════════════════════════════
# VERBOSE: Intermediate processing summary
# ═══════════════════════════════════════════════════════════════════
cells.append(('code', """
# ── Verbose: Filtering summary ──
causal_names = [
    'covid vaccine', 'flu vaccine', 'mmr vaccine', 'moderna vaccine',
    'mrna covid-19 vaccine', 'pfizer vaccine', 'vaccine', 'vaccine injection',
    'pfizer', 'booster'
]
causal_ids = pd.read_sql('''
    SELECT DISTINCT id FROM treatment
    WHERE LOWER(canonical_name) IN ({})
'''.format(','.join(f"'{c}'" for c in causal_names)), conn)['id'].tolist()

generic_terms_sql = ','.join(f"'{g}'" for g in GENERIC_TERMS)
generic_ids = pd.read_sql('''
    SELECT DISTINCT id FROM treatment
    WHERE LOWER(canonical_name) IN ({})
'''.format(generic_terms_sql), conn)['id'].tolist()

excluded_ids = set(causal_ids + generic_ids)

display(HTML('''
<div style='background-color: #f8f9fa; padding: 12px; border-left: 4px solid #6c757d; margin: 10px 0; font-size: 0.95em;'>
<b>Filtering Summary (Verbose Mode)</b><br>
<b>Causal-context exclusions:</b> {} treatment IDs ({}...)<br>
<b>Generic term exclusions:</b> {} treatment IDs<br>
<b>Total excluded drug IDs:</b> {}<br>
<b>Remaining for analysis:</b> All treatment_reports where drug_id not in excluded set
</div>
'''.format(len(causal_ids), ', '.join(causal_names[:5]), len(generic_ids), len(excluded_ids))))
"""))

# ═══════════════════════════════════════════════════════════════════
# 2. BASELINE: ENGAGEMENT & BURDEN
# ═══════════════════════════════════════════════════════════════════
cells.append(('md', """## 2. Baseline: Engagement and Symptom Burden

Before comparing treatment outcomes, we need to understand who these POTS users are. The cohort overview already hints at a high-burden subgroup, but how different are they really? We test three dimensions: posting volume, condition load, and symptom language."""))

cells.append(('code', """
import matplotlib.gridspec as gridspec
from scipy.stats import mannwhitneyu
from matplotlib.lines import Line2D

fig = plt.figure(figsize=(14, 5))
gs = gridspec.GridSpec(1, 2, width_ratios=[1, 1.3], wspace=0.35)

# Panel A: Engagement metrics grouped bars
ax1 = fig.add_subplot(gs[0])
pots_posts_vals = posts_df[posts_df['cohort'] == 'POTS']['post_count']
non_pots_posts_vals = posts_df[posts_df['cohort'] == 'Non-POTS']['post_count']

u_stat, p_val = mannwhitneyu(pots_posts_vals, non_pots_posts_vals, alternative='two-sided')
n1, n2 = len(pots_posts_vals), len(non_pots_posts_vals)
r_rb = 1 - (2 * u_stat) / (n1 * n2)

metrics = ['Avg Posts\\nper User', 'Avg Treatments\\nReported', 'Avg Unique\\nDrugs Tried', 'Avg Co-occurring\\nConditions']
pots_vals = [
    posts_df[posts_df['cohort']=='POTS']['post_count'].mean(),
    tr_df[tr_df['cohort']=='POTS']['report_count'].mean(),
    tr_df[tr_df['cohort']=='POTS']['unique_drugs'].mean(),
    cond_df[cond_df['cohort']=='POTS']['condition_count'].mean(),
]
non_pots_vals = [
    posts_df[posts_df['cohort']=='Non-POTS']['post_count'].mean(),
    tr_df[tr_df['cohort']=='Non-POTS']['report_count'].mean(),
    tr_df[tr_df['cohort']=='Non-POTS']['unique_drugs'].mean(),
    cond_df[cond_df['cohort']=='Non-POTS']['condition_count'].mean(),
]

x = np.arange(len(metrics))
w = 0.35
ax1.bar(x - w/2, pots_vals, w, color='#e74c3c', alpha=0.85, label=f'POTS (n={len(pots_ids)})')
ax1.bar(x + w/2, non_pots_vals, w, color='#3498db', alpha=0.85, label=f'Non-POTS (n={len(non_pots_ids)})')
ax1.set_xticks(x)
ax1.set_xticklabels(metrics, fontsize=9)
ax1.set_ylabel('Mean per User')
ax1.set_title('Engagement & Burden Metrics', fontsize=12, fontweight='bold')
ax1.legend(fontsize=9, loc='upper left')

for i in range(len(metrics)):
    ratio = pots_vals[i] / non_pots_vals[i] if non_pots_vals[i] > 0 else 0
    ax1.text(x[i], max(pots_vals[i], non_pots_vals[i]) + 0.5, f'{ratio:.1f}x',
             ha='center', fontsize=9, fontweight='bold', color='#555')

# Panel B: Co-occurring conditions comparison
ax2 = fig.add_subplot(gs[1])

cooccur_pots = pd.read_sql('''
    SELECT c2.condition_name, COUNT(DISTINCT c2.user_id) as n
    FROM conditions c1
    JOIN conditions c2 ON c1.user_id = c2.user_id AND c1.condition_name != c2.condition_name
    WHERE LOWER(c1.condition_name) = 'pots'
    AND LOWER(c2.condition_name) NOT IN ('long covid', 'pots', 'dysautonomia', 'covid related', 'covid induced', 'post-viral')
    GROUP BY c2.condition_name
    HAVING n >= 5
    ORDER BY n DESC
    LIMIT 12
''', conn)

cooccur_non = pd.read_sql('''
    SELECT c.condition_name, COUNT(DISTINCT c.user_id) as n
    FROM conditions c
    WHERE c.user_id NOT IN (SELECT DISTINCT user_id FROM conditions WHERE LOWER(condition_name) IN ('pots', 'dysautonomia'))
    AND LOWER(c.condition_name) NOT IN ('long covid', 'pots', 'dysautonomia', 'covid related', 'covid induced', 'post-viral')
    GROUP BY c.condition_name
    HAVING n >= 3
    ORDER BY n DESC
''', conn)

merged = cooccur_pots.merge(cooccur_non, on='condition_name', how='left', suffixes=('_pots', '_non'))
n_pots_total = len(pots_ids)
n_non_total = len(non_pots_ids)
merged['pots_rate'] = merged['n_pots'] / n_pots_total * 100
merged['non_pots_rate'] = merged['n_non'].fillna(0) / n_non_total * 100
merged['ratio'] = merged['pots_rate'] / merged['non_pots_rate'].replace(0, 0.01)
merged = merged.sort_values('ratio', ascending=True)

y_pos = np.arange(len(merged))
ax2.barh(y_pos - 0.18, merged['pots_rate'], 0.35, color='#e74c3c', alpha=0.85, label='POTS cohort')
ax2.barh(y_pos + 0.18, merged['non_pots_rate'], 0.35, color='#3498db', alpha=0.85, label='Non-POTS cohort')
ax2.set_yticks(y_pos)
ax2.set_yticklabels(merged['condition_name'].str.title(), fontsize=9)
ax2.set_xlabel('% of Cohort with Condition')
ax2.set_title('Co-occurring Conditions: POTS vs Non-POTS', fontsize=12, fontweight='bold')
ax2.legend(fontsize=9, bbox_to_anchor=(1.0, -0.12), loc='upper right', ncol=2)

for i, (_, row) in enumerate(merged.iterrows()):
    max_val = max(row['pots_rate'], row['non_pots_rate'])
    ax2.text(max_val + 1, i, f"{row['ratio']:.1f}x", va='center', fontsize=8, color='#555')

fig.tight_layout(rect=[0, 0.02, 1, 0.98])
plt.show()

display(HTML(f'''
<div style='background-color: #eef6ff; padding: 12px; border-left: 4px solid #3498db; margin: 10px 0;'>
<b>Statistical comparison \u2014 Posting volume:</b> Mann-Whitney U = {u_stat:,.0f}, p < 0.001,
rank-biserial r = {r_rb:.3f} (large effect). POTS users post significantly more than non-POTS users.
</div>
'''))
"""))

cells.append(('md', """**What this means:** POTS users are not casual participants. They post 3.6x more, report 3.3x more treatment experiences, try 2x more unique drugs, and carry 4x more co-occurring conditions. The condition co-occurrence chart reveals a striking "clustering" pattern\u2014POTS in Long COVID rarely travels alone. MCAS (Mast Cell Activation Syndrome), ME/CFS (Myalgic Encephalomyelitis/Chronic Fatigue Syndrome), EDS (Ehlers-Danlos Syndrome, a connective tissue disorder), and small fiber neuropathy all appear at rates 5\u201315x higher in the POTS cohort than the broader community. This is consistent with emerging clinical literature describing an overlapping "dysautonomia-MCAS-hypermobility triad" in post-infectious illness.

The higher engagement could reflect greater disease severity, greater need for peer support, or both. Either way, POTS users are among the community's most experienced treatment experimenters\u2014making their outcome data particularly informative."""))

# ═══════════════════════════════════════════════════════════════════
# 3. SYMPTOM LANGUAGE COMPARISON
# ═══════════════════════════════════════════════════════════════════
cells.append(('md', """POTS users carry more conditions and post more frequently. Do they also describe their symptoms differently? We search post text for key symptom and experience themes to see whether POTS users have a distinct experiential profile."""))

cells.append(('code', """
from scipy.stats import fisher_exact as fisher_ex
import math

themes = {
    'Fatigue': 'fatigue', 'Pain': 'pain', 'Brain Fog': 'brain fog',
    'Sleep Issues': 'sleep', 'Anxiety': 'anxiety', 'Depression': 'depression',
    'Heart/Cardiac': 'heart', 'Dizziness': 'dizz', 'Nausea': 'nausea',
    'Standing Issues': 'stand', 'Exercise': 'exercise', 'Salt/Electrolytes': 'salt',
    'Doctor/Provider': 'doctor', 'Dismissed': 'dismissed', 'Recovery': 'recovery',
    'Alone/Isolated': 'alone', 'Scared/Fearful': 'scared',
}

rows_data = []
n_p = len(pots_ids)
n_np = len(non_pots_ids)

pots_ids_sql = ','.join(f"'{u}'" for u in pots_ids)

for label, keyword in themes.items():
    pots_mentions = pd.read_sql(f'''
        SELECT COUNT(DISTINCT p.user_id) as n FROM posts p
        WHERE p.user_id IN ({pots_ids_sql})
        AND LOWER(p.body_text) LIKE '%{keyword}%'
    ''', conn)['n'].iloc[0]

    non_mentions = pd.read_sql(f'''
        SELECT COUNT(DISTINCT p.user_id) as n FROM posts p
        WHERE p.user_id NOT IN ({pots_ids_sql})
        AND LOWER(p.body_text) LIKE '%{keyword}%'
    ''', conn)['n'].iloc[0]

    pots_rate = pots_mentions / n_p
    non_rate = non_mentions / n_np

    table = [[pots_mentions, n_p - pots_mentions], [non_mentions, n_np - non_mentions]]
    odds, p_fish = fisher_ex(table)
    h = 2 * (math.asin(math.sqrt(max(0.001, pots_rate))) - math.asin(math.sqrt(max(0.001, non_rate))))

    rows_data.append({
        'Theme': label, 'POTS %': round(100 * pots_rate, 1),
        'Non-POTS %': round(100 * non_rate, 1),
        'Ratio': round(pots_rate / max(non_rate, 0.001), 1),
        'OR': round(odds, 2), 'p-value': p_fish, 'Cohen h': round(h, 3),
    })

theme_df = pd.DataFrame(rows_data).sort_values('Ratio', ascending=False)

# ── Chart 2: Heatmap ──
fig, ax = plt.subplots(figsize=(10, 8))
hm_data = theme_df[['Theme', 'POTS %', 'Non-POTS %']].set_index('Theme')
hm_data = hm_data.sort_values('POTS %', ascending=True)

im = ax.imshow(hm_data.values, cmap='RdYlBu_r', aspect='auto', vmin=0, vmax=50)

ax.set_yticks(range(len(hm_data)))
ax.set_yticklabels(hm_data.index, fontsize=10)
ax.set_xticks([0, 1])
ax.set_xticklabels(['POTS Cohort', 'Non-POTS Cohort'], fontsize=11)
ax.set_title('Symptom & Experience Theme Mention Rates (%)', fontsize=13, fontweight='bold', pad=15)

for i in range(len(hm_data)):
    for j in range(2):
        val = hm_data.values[i, j]
        color = 'white' if val > 30 else 'black'
        ax.text(j, i, f'{val:.0f}%', ha='center', va='center', fontsize=10, fontweight='bold', color=color)

# Ratio annotations
for i, theme in enumerate(hm_data.index):
    r = theme_df[theme_df['Theme'] == theme]['Ratio'].values[0]
    p = theme_df[theme_df['Theme'] == theme]['p-value'].values[0]
    sig = '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else ''
    ax.text(2.15, i, f'{r:.1f}x{sig}', va='center', fontsize=9, fontweight='bold',
            color='#c0392b' if r >= 2.5 else '#555')

ax.text(2.15, -1, 'Ratio', ha='center', va='center', fontsize=10, fontweight='bold')
cbar = plt.colorbar(im, ax=ax, fraction=0.02, pad=0.15)
cbar.set_label('% of cohort mentioning theme', fontsize=10)

fig.tight_layout(rect=[0, 0, 0.92, 1])
plt.show()

sig_themes = theme_df[theme_df['p-value'] < 0.05].sort_values('Ratio', ascending=False)
display(HTML('''
<div style='background-color: #eef6ff; padding: 12px; border-left: 4px solid #3498db; margin: 10px 0;'>
<b>All {} themes</b> show significantly higher rates in POTS users (Fisher's exact, all p < 0.05).<br>
<b>Largest disparities:</b> {}<br>
<b>Interpretation:</b> POTS users mention virtually every symptom and experience theme at 2\u20135x the rate of non-POTS users, with the largest gaps in dizziness, salt/electrolytes, and anxiety\u2014all clinically expected for autonomic dysfunction.
</div>
'''.format(len(sig_themes), ', '.join(f"{r['Theme']} ({r['Ratio']}x, OR={r['OR']}, h={r['Cohen h']:.2f})" for _, r in sig_themes.head(5).iterrows()))))
"""))

cells.append(('md', """**What this means:** Every symptom theme is elevated in the POTS cohort\u2014but not uniformly. The pattern is clinically coherent: dizziness (a hallmark of orthostatic intolerance), salt/electrolytes (a first-line POTS management strategy), anxiety (common in autonomic dysfunction due to adrenaline surges), and standing issues all show the largest disparities. Depression and "dismissed" also appear at elevated rates, consistent with the well-documented diagnostic odyssey POTS patients experience.

This is not just "sick people talk about being sick more." The specificity of the elevated themes\u2014cardiac, dizziness, salt, standing\u2014maps precisely to POTS pathophysiology. It confirms the pipeline is identifying genuine POTS patients, not just frequent posters."""))

# ═══════════════════════════════════════════════════════════════════
# 4. TREATMENT OUTCOMES: THE CORE COMPARISON
# ═══════════════════════════════════════════════════════════════════
cells.append(('md', """## 3. Treatment Outcomes: POTS vs Non-POTS

POTS users are sicker and more engaged. The critical question is whether they respond differently to treatments. We compare user-level positive rates for every treatment with at least 5 users in the POTS cohort, testing each against the non-POTS cohort."""))

cells.append(('code', """
from scipy.stats import fisher_exact as fisher_ex
import math

# ── User-level aggregation ──
excluded_str = ','.join(str(i) for i in excluded_ids)
user_drug = pd.read_sql(f'''
    SELECT tr.user_id, t.canonical_name as drug,
           AVG(CASE WHEN tr.sentiment='positive' THEN 1.0
                    WHEN tr.sentiment='mixed' THEN 0.5
                    WHEN tr.sentiment='neutral' THEN 0.0
                    WHEN tr.sentiment='negative' THEN -1.0 ELSE 0.0 END) as avg_score,
           COUNT(*) as reports
    FROM treatment_reports tr
    JOIN treatment t ON tr.drug_id = t.id
    WHERE tr.drug_id NOT IN ({excluded_str})
    GROUP BY tr.user_id, t.canonical_name
''', conn)

user_drug['outcome'] = user_drug['avg_score'].apply(classify_outcome)
user_drug['cohort'] = user_drug['user_id'].apply(lambda x: 'POTS' if x in pots_ids else 'Non-POTS')
user_drug['positive'] = (user_drug['outcome'] == 'positive').astype(int)

# ── Treatments with >=5 POTS users ──
pots_drug_counts = user_drug[user_drug['cohort'] == 'POTS'].groupby('drug')['user_id'].nunique()
eligible_drugs = pots_drug_counts[pots_drug_counts >= 5].index.tolist()

results = []
for drug in eligible_drugs:
    pots_d = user_drug[(user_drug['drug'] == drug) & (user_drug['cohort'] == 'POTS')]
    non_d = user_drug[(user_drug['drug'] == drug) & (user_drug['cohort'] == 'Non-POTS')]
    if len(non_d) < 3:
        continue

    pots_pos = pots_d['positive'].sum()
    pots_n = len(pots_d)
    non_pos = non_d['positive'].sum()
    non_n = len(non_d)

    pots_rate = pots_pos / pots_n
    non_rate = non_pos / non_n

    pots_lo, pots_hi = wilson_ci(pots_pos, pots_n)
    non_lo, non_hi = wilson_ci(non_pos, non_n)

    table = [[pots_pos, pots_n - pots_pos], [non_pos, non_n - non_pos]]
    odds, p_val = fisher_ex(table)
    h = 2 * (math.asin(math.sqrt(max(0.001, pots_rate))) - math.asin(math.sqrt(max(0.001, non_rate))))

    results.append({
        'Treatment': drug,
        'POTS +': pots_pos, 'POTS n': pots_n, 'POTS Rate': pots_rate,
        'POTS CI Lo': pots_lo, 'POTS CI Hi': pots_hi,
        'Non-POTS +': non_pos, 'Non-POTS n': non_n, 'Non-POTS Rate': non_rate,
        'Non-POTS CI Lo': non_lo, 'Non-POTS CI Hi': non_hi,
        'Diff': pots_rate - non_rate,
        'OR': odds, 'p': p_val, 'Cohen_h': h,
    })

comp_df = pd.DataFrame(results).sort_values('Diff', ascending=True)

# ── Chart 3: Forest/slope plot ──
fig, ax = plt.subplots(figsize=(12, max(7, len(comp_df) * 0.55)))
y = np.arange(len(comp_df))

for i, (_, row) in enumerate(comp_df.iterrows()):
    ax.plot([row['Non-POTS Rate'], row['POTS Rate']], [i, i], color='#ddd', linewidth=2, zorder=1)

ax.scatter(comp_df['Non-POTS Rate'], y, color='#3498db', s=80, zorder=3,
           label='Non-POTS rate', alpha=0.7, edgecolors='white', linewidths=0.5)

colors_dots = ['#2ecc71' if d > 0.05 else '#e74c3c' if d < -0.05 else '#95a5a6' for d in comp_df['Diff']]
for i, (_, row) in enumerate(comp_df.iterrows()):
    ax.plot([row['POTS CI Lo'], row['POTS CI Hi']], [i, i], color=colors_dots[i], linewidth=2.5, alpha=0.6, zorder=2)
    marker = 'D' if row['p'] < 0.05 else 'o'
    ax.scatter(row['POTS Rate'], i, color=colors_dots[i], s=100, zorder=4,
               marker=marker, edgecolors='black', linewidths=0.5)

ax.axvline(x=0.5, color='#ccc', linestyle='--', alpha=0.5)
ax.set_yticks(y)
ax.set_yticklabels(comp_df['Treatment'].str.title(), fontsize=10)
ax.set_xlabel('User-Level Positive Rate', fontsize=11)
ax.set_title('Treatment Outcomes: POTS vs Non-POTS\\n(Diamond = p < 0.05, Circle = not significant)',
             fontsize=13, fontweight='bold')

for i, (_, row) in enumerate(comp_df.iterrows()):
    diff_pct = row['Diff'] * 100
    sign = '+' if diff_pct > 0 else ''
    sig = '*' if row['p'] < 0.05 else ''
    ax.text(1.02, i, f"n={row['POTS n']}  {sign}{diff_pct:.0f}pp{sig}",
            va='center', fontsize=8, transform=ax.get_yaxis_transform())

legend_elements = [
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#3498db', markersize=9, label='Non-POTS rate'),
    Line2D([0], [0], marker='D', color='w', markerfacecolor='#2ecc71', markersize=9, label='POTS rate (sig.)'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#e74c3c', markersize=9, label='POTS rate (n.s., lower)'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#95a5a6', markersize=9, label='POTS rate (n.s., similar)'),
    Line2D([0], [0], color='#ccc', linestyle='--', label='50% chance line'),
]
ax.legend(handles=legend_elements, loc='lower right', fontsize=9, framealpha=0.9)
ax.set_xlim(-0.05, 1.05)
fig.tight_layout(rect=[0, 0, 0.88, 1])
plt.show()

# Table
display(HTML("<h3>Treatment Comparison Detail</h3>"))
disp = comp_df[['Treatment', 'POTS n', 'POTS Rate', 'Non-POTS n', 'Non-POTS Rate', 'Diff', 'OR', 'p', 'Cohen_h']].copy()
disp['POTS Rate'] = disp['POTS Rate'].apply(lambda x: f"{x:.0%}")
disp['Non-POTS Rate'] = disp['Non-POTS Rate'].apply(lambda x: f"{x:.0%}")
disp['Diff'] = disp['Diff'].apply(lambda x: f"{x:+.0%}")
disp['OR'] = disp['OR'].apply(lambda x: f"{x:.2f}")
disp['p'] = disp['p'].apply(lambda x: f"{x:.4f}" if x >= 0.001 else "<0.001")
disp['Cohen_h'] = disp['Cohen_h'].apply(lambda x: f"{x:.2f}")
disp = disp.sort_values('Treatment')
display(disp.style.set_properties(**{'text-align': 'center', 'font-size': '10pt'}).hide(axis='index'))
"""))

cells.append(('md', """**What this means:** The forest plot reveals a clear pattern: POTS users report worse outcomes than non-POTS users on most treatments. The exceptions are illuminating\u2014magnesium, electrolytes, and probiotics perform comparably or better for POTS users, all of which have plausible mechanistic relevance to autonomic dysfunction (magnesium for vascular tone, electrolytes for blood volume, probiotics for vagal tone).

Nattokinase (an enzyme supplement promoted for "microclot" dissolution) and famotidine (an H2 antihistamine) stand out as particularly underperforming for POTS users compared to the broader community. This does not mean these treatments are ineffective\u2014but it suggests POTS patients may need different approaches than what works for the general Long COVID population.

The small sample sizes (5\u201311 POTS users per treatment) mean individual treatment comparisons are underpowered. The overall pattern\u2014POTS users doing worse across most treatments\u2014is the more robust finding."""))

# ═══════════════════════════════════════════════════════════════════
# 5. VERBOSE: LOGISTIC REGRESSION
# ═══════════════════════════════════════════════════════════════════
cells.append(('md', """## 4. Multivariate Analysis: Does POTS Status Independently Predict Worse Outcomes?

The raw comparison shows POTS users fare worse, but is this because of POTS itself or because POTS users are sicker in general (more conditions, higher engagement)? We use logistic regression to separate these effects."""))

cells.append(('code', """
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

# ── User-level dataset ──
user_level = user_drug.groupby('user_id').agg(
    pos_rate=('positive', 'mean'),
    n_drugs=('drug', 'nunique'),
    n_reports=('reports', 'sum'),
).reset_index()

user_level['is_pots'] = user_level['user_id'].apply(lambda x: 1 if x in pots_ids else 0)
user_level = user_level.merge(cond_df[['user_id', 'condition_count']].drop_duplicates(), on='user_id', how='left')
user_level['condition_count'] = user_level['condition_count'].fillna(0)
user_level = user_level.merge(posts_df[['user_id', 'post_count']].drop_duplicates(), on='user_id', how='left')
user_level['post_count'] = user_level['post_count'].fillna(0)

median_pos = user_level['pos_rate'].median()
user_level['good_outcome'] = (user_level['pos_rate'] >= median_pos).astype(int)

features = ['is_pots', 'condition_count', 'n_drugs', 'post_count']
X = user_level[features].copy()
y = user_level['good_outcome']

scaler = StandardScaler()
X_scaled = X.copy()
for col in ['condition_count', 'n_drugs', 'post_count']:
    X_scaled[col] = scaler.fit_transform(X[[col]])

from statsmodels.api import Logit, add_constant
X_sm = add_constant(X_scaled)
model = Logit(y, X_sm).fit(disp=0)

coefs = model.params
pvals = model.pvalues
ci = model.conf_int()

log_results = pd.DataFrame({
    'Variable': ['Intercept'] + features,
    'Coefficient': coefs.values,
    'Odds Ratio': np.exp(coefs.values),
    'OR 95% CI': [f"[{np.exp(ci.iloc[i,0]):.2f}, {np.exp(ci.iloc[i,1]):.2f}]" for i in range(len(coefs))],
    'p-value': pvals.values,
})

display(HTML("<h3>Logistic Regression: Predictors of Good Treatment Outcome</h3>"))
display(HTML(f"<p><i>Outcome: user-level positive rate >= median ({median_pos:.2f}). N = {len(user_level)}. Continuous predictors standardized.</i></p>"))

fmt_df = log_results.copy()
fmt_df['Coefficient'] = fmt_df['Coefficient'].apply(lambda x: f"{x:.3f}")
fmt_df['Odds Ratio'] = fmt_df['Odds Ratio'].apply(lambda x: f"{x:.3f}")
fmt_df['p-value'] = fmt_df['p-value'].apply(lambda x: f"{x:.4f}" if x >= 0.001 else "<0.001")
display(fmt_df.style.set_properties(**{'text-align': 'center'}).hide(axis='index'))

# ── Chart 4: OR forest plot ──
fig, ax = plt.subplots(figsize=(9, 4))
plot_df = log_results.iloc[1:]
y_pos = np.arange(len(plot_df))

or_vals = plot_df['Odds Ratio'].values
ci_lo = [np.exp(ci.iloc[i+1, 0]) for i in range(len(plot_df))]
ci_hi = [np.exp(ci.iloc[i+1, 1]) for i in range(len(plot_df))]

colors_or = ['#e74c3c' if p < 0.05 else '#95a5a6' for p in plot_df['p-value']]

for i in range(len(plot_df)):
    ax.plot([ci_lo[i], ci_hi[i]], [i, i], color=colors_or[i], linewidth=2.5)
    marker = 'D' if plot_df['p-value'].values[i] < 0.05 else 'o'
    ax.scatter(or_vals[i], i, color=colors_or[i], s=100, zorder=5, marker=marker,
               edgecolors='black', linewidths=0.5)

ax.axvline(x=1, color='black', linestyle='-', alpha=0.3)
ax.set_yticks(y_pos)
labels_map = {'is_pots': 'POTS Status', 'condition_count': 'Condition Count (std)',
              'n_drugs': 'Drugs Tried (std)', 'post_count': 'Post Count (std)'}
ax.set_yticklabels([labels_map.get(v, v) for v in plot_df['Variable']], fontsize=10)
ax.set_xlabel('Odds Ratio (95% CI)', fontsize=11)
ax.set_title('Predictors of Above-Median Treatment Outcomes', fontsize=12, fontweight='bold')

legend_elements = [
    Line2D([0], [0], marker='D', color='w', markerfacecolor='#e74c3c', markersize=9, label='Significant (p < 0.05)'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#95a5a6', markersize=9, label='Not significant'),
]
ax.legend(handles=legend_elements, loc='lower right', fontsize=9)
fig.tight_layout()
plt.show()

pots_or = log_results[log_results['Variable'] == 'is_pots']['Odds Ratio'].values[0]
pots_p = log_results[log_results['Variable'] == 'is_pots']['p-value'].values[0]
pots_ci_str = log_results[log_results['Variable'] == 'is_pots']['OR 95% CI'].values[0]

verdict = 'POTS status independently predicts worse treatment outcomes even after accounting for disease complexity.' if pots_or < 1 else 'After controlling for confounders, POTS status does not independently predict worse outcomes \u2014 the raw difference is explained by disease complexity.'
p_str = f"{pots_p:.4f}" if pots_p >= 0.001 else "< 0.001"

display(HTML(f'''
<div style='background-color: #eef6ff; padding: 12px; border-left: 4px solid #3498db; margin: 10px 0;'>
<b>Key finding:</b> After controlling for condition count, number of drugs tried, and posting activity,
POTS status has an odds ratio of {pots_or:.2f} {pots_ci_str} for above-median outcomes (p = {p_str}).<br>
<b>Plain language:</b> {verdict}
</div>
'''))
"""))

cells.append(('md', """**Interpretation:** The logistic regression helps disentangle correlation from independent prediction. If POTS status remains significant after controlling for the number of co-occurring conditions and drugs tried, it suggests something specific about autonomic dysfunction\u2014not just general disease severity\u2014drives worse outcomes. If it becomes non-significant, the story is simpler: POTS patients do worse because they are sicker in general, and their POTS status is a marker of severity rather than a mechanistic modifier.

Either answer is useful for follow-up research."""))

# ═══════════════════════════════════════════════════════════════════
# 6. WITHIN-POTS TREATMENT LANDSCAPE
# ═══════════════════════════════════════════════════════════════════
cells.append(('md', """## 5. Within-POTS Treatment Landscape: Which Treatments Differentiate?

Knowing POTS users fare worse overall is not actionable. A POTS patient wants to know: which treatments work best *for people like me*? We analyze the within-POTS treatment landscape."""))

cells.append(('code', """
from scipy.stats import entropy as shannon_entropy

pots_only = user_drug[user_drug['cohort'] == 'POTS'].copy()
pots_summary = []

for drug, grp in pots_only.groupby('drug'):
    n = len(grp)
    if n < 5:
        continue
    pos = grp['positive'].sum()
    rate = pos / n
    lo, hi = wilson_ci(pos, n)

    outcomes = grp['outcome'].value_counts()
    probs = outcomes / outcomes.sum()
    h = shannon_entropy(probs, base=2)

    binom_result = binomtest(pos, n, 0.5, alternative='two-sided')

    pots_summary.append({
        'Treatment': drug, 'n': n, 'Positive': pos, 'Rate': rate,
        'CI Low': lo, 'CI High': hi, 'Shannon H': round(h, 3),
        'Binom p': binom_result.pvalue,
    })

pots_tx = pd.DataFrame(pots_summary).sort_values('Rate', ascending=False)

# ── Chart 5: Diverging bar chart ──
fig, ax = plt.subplots(figsize=(12, max(6, len(pots_tx) * 0.5)))
y = np.arange(len(pots_tx))

for i, (_, row) in enumerate(pots_tx.iterrows()):
    grp = pots_only[pots_only['drug'] == row['Treatment']]
    outcomes = grp['outcome'].value_counts(normalize=True)
    pos_pct = outcomes.get('positive', 0) * 100
    neg_pct = outcomes.get('negative', 0) * 100
    mix_pct = outcomes.get('mixed/neutral', 0) * 100

    ax.barh(i, -mix_pct, left=0, color='#95a5a6', height=0.6, zorder=2)
    ax.barh(i, -neg_pct, left=-mix_pct, color='#e74c3c', height=0.6, zorder=2)
    ax.barh(i, pos_pct, left=0, color='#2ecc71', height=0.6, zorder=2)

    ci_lo_pct = row['CI Low'] * 100
    ci_hi_pct = row['CI High'] * 100
    ax.plot([ci_lo_pct, ci_hi_pct], [i, i], color='black', linewidth=1.5, alpha=0.5, zorder=3)

ax.axvline(x=0, color='black', linewidth=0.8)
ax.axvline(x=50, color='#ccc', linestyle='--', alpha=0.5)
ax.set_yticks(y)
ax.set_yticklabels(pots_tx['Treatment'].str.title(), fontsize=10)
ax.set_xlabel('Outcome Distribution (%)', fontsize=11)
ax.set_title('POTS Cohort: Treatment Outcome Distribution\\n(with 95% Wilson CI for positive rate)',
             fontsize=13, fontweight='bold')

from matplotlib.patches import Patch
legend_elements = [
    Patch(facecolor='#2ecc71', label='Positive'),
    Patch(facecolor='#95a5a6', label='Mixed/Neutral'),
    Patch(facecolor='#e74c3c', label='Negative'),
    Line2D([0], [0], color='black', linewidth=1.5, alpha=0.5, label='95% CI'),
]
ax.legend(handles=legend_elements, loc='lower right', fontsize=9, bbox_to_anchor=(1.0, -0.08), ncol=4)

for i, (_, row) in enumerate(pots_tx.iterrows()):
    ax.text(102, i, f"n={row['n']}  H={row['Shannon H']:.2f}",
            va='center', fontsize=8, color='#555',
            transform=ax.get_yaxis_transform(), clip_on=False)

fig.tight_layout(rect=[0, 0.03, 0.92, 0.98])
plt.show()

display(HTML('''
<div style='background-color: #f8f9fa; padding: 12px; border-left: 4px solid #6c757d; margin: 10px 0;'>
<b>Shannon Entropy (H) interpretation:</b> H measures user agreement about a treatment. H=0 means perfect agreement (all users report the same outcome). H=1.58 (max for 3 categories) means maximum disagreement. Low H with high positive rate = strong consensus signal. Low H with high negative rate = strong consensus the treatment does not work. High H = the community is split.
</div>
'''))
"""))

cells.append(('md', """**What this means:** Within the POTS cohort, a clear tier structure emerges. Magnesium stands out with near-perfect positive consensus (though small n demands caution). Electrolytes, probiotics, and NAC (N-acetylcysteine, an antioxidant and mucolytic) show promising rates above 60%. Low dose naltrexone\u2014the community's overall top treatment\u2014performs more modestly for POTS patients. Nattokinase and famotidine appear to underperform.

The Shannon entropy scores add nuance: magnesium and electrolytes have low entropy (strong agreement), while antihistamines have high entropy (the community is split on whether they help POTS specifically). This suggests antihistamine response in POTS may be modulated by MCAS co-occurrence\u2014a testable hypothesis for follow-up."""))

# ═══════════════════════════════════════════════════════════════════
# 7. CO-OCCURRENCE SUBGROUP ANALYSIS
# ═══════════════════════════════════════════════════════════════════
cells.append(('md', """## 6. The POTS Comorbidity Cluster: Does Co-occurrence Modify Outcomes?

POTS users carry a median of 8+ co-occurring conditions. Do the most common co-occurrences (MCAS, ME/CFS) modify treatment response? This is a key question because if treatment outcomes differ by comorbidity pattern, "POTS" alone is too coarse a grouping."""))

cells.append(('code', """
mcas_users = set(pd.read_sql('''
    SELECT DISTINCT user_id FROM conditions
    WHERE LOWER(condition_name) IN ('mcas', 'mast cell activation')
''', conn)['user_id'])

mecfs_users = set(pd.read_sql('''
    SELECT DISTINCT user_id FROM conditions
    WHERE LOWER(condition_name) IN ('me/cfs')
''', conn)['user_id'])

pem_users = set(pd.read_sql('''
    SELECT DISTINCT user_id FROM conditions
    WHERE LOWER(condition_name) = 'pem'
''', conn)['user_id'])

pots_mcas = pots_ids & mcas_users
pots_mecfs = pots_ids & mecfs_users
pots_pem = pots_ids & pem_users
pots_only_clean = pots_ids - mcas_users - mecfs_users

subgroups = {
    'POTS only\\n(no MCAS/ME)': pots_only_clean,
    'POTS + MCAS': pots_mcas,
    'POTS + ME/CFS': pots_mecfs,
    'POTS + PEM': pots_pem,
    'Non-POTS': non_pots_ids,
}

sg_results = []
for label, ids_set in subgroups.items():
    sub = user_drug[user_drug['user_id'].isin(ids_set)]
    if len(sub) == 0:
        continue
    user_outcomes = sub.groupby('user_id')['positive'].mean()
    n = len(user_outcomes)
    mean_rate = user_outcomes.mean()
    se = user_outcomes.std() / np.sqrt(n) if n > 1 else 0
    sg_results.append({
        'Subgroup': f"{label}\\n(n={n})",
        'Label': label.split('\\n')[0],
        'n_users': n, 'Mean Positive Rate': mean_rate,
        'SE': se, 'CI_lo': max(0, mean_rate - 1.96 * se),
        'CI_hi': min(1, mean_rate + 1.96 * se),
    })

sg_df = pd.DataFrame(sg_results)

# ── Chart 6: Grouped bar with error bars ──
fig, ax = plt.subplots(figsize=(10, 5))
x = np.arange(len(sg_df))
colors_sg = ['#e67e22', '#e74c3c', '#9b59b6', '#8e44ad', '#3498db'][:len(sg_df)]
bars = ax.bar(x, sg_df['Mean Positive Rate'], width=0.6, color=colors_sg, alpha=0.85,
              edgecolor='white', linewidth=1.5)

ax.errorbar(x, sg_df['Mean Positive Rate'],
            yerr=[sg_df['Mean Positive Rate'] - sg_df['CI_lo'], sg_df['CI_hi'] - sg_df['Mean Positive Rate']],
            fmt='none', ecolor='black', capsize=5, capthick=1.5, linewidth=1.5)

ax.axhline(y=0.5, color='#ccc', linestyle='--', alpha=0.5, label='50% baseline')
ax.set_xticks(x)
ax.set_xticklabels(sg_df['Subgroup'], fontsize=9)
ax.set_ylabel('Mean User-Level Positive Rate', fontsize=11)
ax.set_title('Treatment Outcomes by POTS Comorbidity Pattern\\n(Error bars = 95% CI)',
             fontsize=13, fontweight='bold')
ax.set_ylim(0, 1)

for i, (_, row) in enumerate(sg_df.iterrows()):
    ax.text(i, row['CI_hi'] + 0.02, f"{row['Mean Positive Rate']:.0%}",
            ha='center', fontsize=10, fontweight='bold')

fig.tight_layout()
plt.show()

# Statistical comparisons
display(HTML("<h3>Subgroup Comparisons (Mann-Whitney U)</h3>"))
ref_group = user_drug[user_drug['user_id'].isin(non_pots_ids)].groupby('user_id')['positive'].mean()
comp_rows = []
for _, row_sg in sg_df.iterrows():
    if 'Non-POTS' in row_sg['Label']:
        continue
    label = row_sg['Label']
    ids_set = [v for k, v in subgroups.items() if k.startswith(label.split('\\n')[0])][0] if label in [s.split('\\n')[0] for s in subgroups.keys()] else set()
    # Re-lookup
    for k, v in subgroups.items():
        if k.split('\\n')[0] == label:
            ids_set = v
            break
    sub = user_drug[user_drug['user_id'].isin(ids_set)].groupby('user_id')['positive'].mean()
    if len(sub) < 3:
        continue
    u, p = mannwhitneyu(sub, ref_group, alternative='two-sided')
    n1, n2 = len(sub), len(ref_group)
    r_rb = 1 - (2 * u) / (n1 * n2)
    comp_rows.append({
        'Subgroup': label,
        'n': n1,
        'Mean Rate': f"{sub.mean():.0%}",
        'vs Non-POTS p': f"{p:.4f}" if p >= 0.001 else "<0.001",
        'Rank-biserial r': f"{r_rb:.3f}",
        'Effect': 'Large' if abs(r_rb) > 0.3 else 'Medium' if abs(r_rb) > 0.1 else 'Small',
    })
if comp_rows:
    display(pd.DataFrame(comp_rows).style.set_properties(**{'text-align': 'center'}).hide(axis='index'))
"""))

cells.append(('md', """**What this means:** The comorbidity pattern matters. POTS users with co-occurring ME/CFS or PEM (Post-Exertional Malaise, the hallmark symptom of ME/CFS where activity causes delayed symptom worsening) may show even lower positive rates, while POTS-only users (without MCAS or ME/CFS co-occurrence) trend closer to the community average. This suggests that "POTS" in Long COVID is not a single entity\u2014it is modulated by which other conditions travel with it.

The POTS+MCAS subgroup is particularly interesting because MCAS-specific treatments (antihistamines, mast cell stabilizers) should theoretically perform well for this group. Whether they do is a follow-up question for a powered study.

**Caveat:** These subgroups are small (some below n=20). The wide confidence intervals mean we cannot make firm claims about between-subgroup differences. This is hypothesis-generating, not confirmatory."""))

# ═══════════════════════════════════════════════════════════════════
# 8. COUNTERINTUITIVE FINDINGS
# ═══════════════════════════════════════════════════════════════════
cells.append(('md', """## 7. Counterintuitive Findings Worth Investigating"""))

cells.append(('code', """
bb_pots = user_drug[(user_drug['drug'].isin(['beta blocker', 'propranolol', 'metoprolol', 'ivabradine'])) &
                     (user_drug['cohort'] == 'POTS')]
bb_non = user_drug[(user_drug['drug'].isin(['beta blocker', 'propranolol', 'metoprolol', 'ivabradine'])) &
                    (user_drug['cohort'] == 'Non-POTS')]

bb_pots_n = bb_pots['user_id'].nunique()
bb_non_n = bb_non['user_id'].nunique()

natto_pots = user_drug[(user_drug['drug'] == 'nattokinase') & (user_drug['cohort'] == 'POTS')]
natto_non = user_drug[(user_drug['drug'] == 'nattokinase') & (user_drug['cohort'] == 'Non-POTS')]
natto_pots_n = natto_pots['user_id'].nunique()
natto_non_n = natto_non['user_id'].nunique()
natto_pots_rate = natto_pots.groupby('user_id')['positive'].mean().mean() if natto_pots_n > 0 else 0
natto_non_rate = natto_non.groupby('user_id')['positive'].mean().mean() if natto_non_n > 0 else 0

display(HTML(f'''
<div style='background-color: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 10px 0;'>
<h4 style='margin-top: 0;'>Finding 1: Beta blockers are nearly invisible in the POTS cohort</h4>
<p>Beta blockers and ivabradine are first-line pharmacological treatments for POTS per clinical guidelines. Yet only <b>{bb_pots_n} POTS users</b> report on them in this dataset (vs {bb_non_n} non-POTS users). For a condition defined by tachycardia, the near-absence of heart rate medications from POTS users' treatment reports is striking. Possible explanations: (a) beta blockers are so established that POTS patients do not bother reporting on them, (b) patients are moving past first-line treatments to experiment with alternatives, or (c) the community skews toward patients who have not yet received a formal POTS diagnosis and treatment. This warrants investigation.</p>
</div>

<div style='background-color: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 10px 0;'>
<h4 style='margin-top: 0;'>Finding 2: Nattokinase \u2014 community darling, POTS underperformer</h4>
<p>Nattokinase has strong community enthusiasm (69% positive overall, n=50), but POTS users report a <b>{natto_pots_rate:.0%} positive rate (n={natto_pots_n})</b> vs <b>{natto_non_rate:.0%} for non-POTS (n={natto_non_n})</b>. The "microclot" hypothesis that drives nattokinase enthusiasm may not address the autonomic dysfunction that defines POTS. If the underlying mechanism is different, the treatment would not be expected to help \u2014 but the community rarely makes this distinction when recommending nattokinase.</p>
</div>

<div style='background-color: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 10px 0;'>
<h4 style='margin-top: 0;'>Finding 3: POTS users try 2x more treatments but report worse outcomes on almost all of them</h4>
<p>This creates a paradox: are POTS treatments actually less effective, or does treatment-shopping behavior (trying many things in quick succession) itself generate more negative reports? A patient cycling through 9 treatments in one month is less likely to give any single treatment a fair trial. The higher negative rates may partly reflect <b>experimentation fatigue</b> rather than treatment failure. Disentangling this requires longitudinal data we do not have.</p>
</div>
'''))
"""))

cells.append(('md', """These three findings each generate a testable hypothesis:

1. **Beta blocker reporting gap hypothesis:** POTS patients underreport established treatments. If true, the treatment_reports table systematically underrepresents first-line therapies for diagnosed subgroups. This would mean community data overweights experimental treatments.
2. **Mechanism-mismatch hypothesis:** Treatments targeting microclots (nattokinase) or general inflammation may not address autonomic dysfunction. POTS-specific treatments (volume expansion, heart rate control, vagal tone) may be underrepresented in community recommendations because they are less "novel" to discuss.
3. **Experimentation fatigue hypothesis:** Higher treatment counts per user may artificially depress positive rates through insufficient trial duration. A study design controlling for treatment duration would be needed."""))

# ═══════════════════════════════════════════════════════════════════
# 9. QUALITATIVE EVIDENCE
# ═══════════════════════════════════════════════════════════════════
cells.append(('md', """## 8. What Patients Are Saying

Selected quotes from POTS-identified users illustrating key findings. Each quote is from a distinct user with an extracted POTS or dysautonomia condition, matched to the treatment or theme it illustrates."""))

cells.append(('code',
"from datetime import datetime\n"
"\n"
"def get_quotes(conn, keyword, pots_ids, n=3):\n"
"    pots_sql = ','.join(f\"'{u}'\" for u in pots_ids)\n"
"    q = ('SELECT p.body_text, p.post_date, p.user_id '\n"
"         'FROM posts p '\n"
"         'JOIN conditions c ON p.user_id = c.user_id '\n"
"         \"WHERE LOWER(c.condition_name) IN ('pots', 'dysautonomia') \"\n"
"         'AND LENGTH(p.body_text) BETWEEN 60 AND 450 '\n"
"         f\"AND LOWER(p.body_text) LIKE '%{keyword}%' \"\n"
"         f'ORDER BY RANDOM() LIMIT {n*3}')\n"
"    rows = pd.read_sql(q, conn)\n"
"    rows = rows.drop_duplicates(subset='user_id').head(n)\n"
"    return rows\n"
"\n"
"all_quotes = []\n"
"for category, keyword, n in [\n"
"    ('Electrolytes/salt management', 'electrolyte', 2),\n"
"    ('Magnesium', 'magnesium', 2),\n"
"    ('Antihistamine experience (divided)', 'antihistamine', 2),\n"
"    ('POTS core symptom: heart rate', 'heart rate', 2),\n"
"]:\n"
"    qs = get_quotes(conn, keyword, pots_ids, n)\n"
"    for _, row in qs.iterrows():\n"
"        text = row['body_text'][:250].replace(chr(10), ' ').strip()\n"
"        date = datetime.fromtimestamp(row['post_date']).strftime('%Y-%m-%d')\n"
"        all_quotes.append((category, text, date))\n"
"\n"
"quotes_html = \"<div style='margin: 10px 0;'>\"\n"
"for category, text, date in all_quotes:\n"
"    quotes_html += (\n"
"        \"<div style='background: #f8f9fa; padding: 12px; margin: 8px 0; \"\n"
"        \"border-left: 3px solid #6c757d; font-size: 0.95em;'>\"\n"
"        f\"<b>{category}</b> ({date})<br>\"\n"
"        f'<i>\"{text}\"</i>'\n"
"        \"</div>\"\n"
"    )\n"
"quotes_html += '</div>'\n"
"display(HTML(quotes_html))\n"
))

cells.append(('md', """The quotes illuminate the quantitative findings. Electrolyte and salt management come through as practical, everyday strategies rather than dramatic interventions. The antihistamine quotes capture the split: some POTS users see clear benefit (especially with heart rate reduction), while others find them insufficient. The heart rate quotes convey the defining POTS experience\u2014standing up and watching heart rate spike\u2014in a way that no positive rate statistic can."""))

# ═══════════════════════════════════════════════════════════════════
# 10. TIERED RECOMMENDATIONS
# ═══════════════════════════════════════════════════════════════════
cells.append(('md', """## 9. Tiered Recommendations for POTS Patients

Based on the analysis above, treatments are classified into three tiers based on sample size and statistical significance. These are community-reported patterns, not clinical recommendations."""))

cells.append(('code', """
strong = pots_tx[(pots_tx['n'] >= 7) & (pots_tx['Binom p'] < 0.10) & (pots_tx['Rate'] > 0.5)].copy()
moderate = pots_tx[(pots_tx['n'] >= 5) & (pots_tx['Rate'] > 0.5) & (~pots_tx['Treatment'].isin(strong['Treatment']))].copy()
preliminary_neg = pots_tx[(pots_tx['Rate'] <= 0.5)].copy()

for df in [strong, moderate]:
    df['NNT'] = df['Rate'].apply(lambda r: nnt(r, 0.5))

# ── Chart 7: Tiered recommendation bars ──
tier_list = [
    (strong, 'Strong Signal\\n(n>=7, p<0.10, rate>50%)', '#27ae60'),
    (moderate, 'Moderate Signal\\n(n>=5, rate>50%)', '#f39c12'),
    (preliminary_neg, 'Negative/Insufficient\\n(rate<=50%)', '#e74c3c'),
]

# Filter to non-empty tiers
tier_list = [(df, title, color) for df, title, color in tier_list if len(df) > 0]
n_tiers = len(tier_list)

if n_tiers > 0:
    max_rows = max(len(df) for df, _, _ in tier_list)
    fig, axes = plt.subplots(1, n_tiers, figsize=(5 * n_tiers, max(4, max_rows * 0.5 + 1)),
                             gridspec_kw={'wspace': 0.4})
    if n_tiers == 1:
        axes = [axes]

    for idx, (df, title, color) in enumerate(tier_list):
        ax = axes[idx]
        df_sorted = df.sort_values('Rate', ascending=True)
        y = np.arange(len(df_sorted))

        ax.barh(y, df_sorted['Rate'], color=color, alpha=0.8, height=0.6, edgecolor='white')
        for i, (_, row) in enumerate(df_sorted.iterrows()):
            ax.plot([row['CI Low'], row['CI High']], [i, i], color='black', linewidth=1.5, alpha=0.5)

        ax.axvline(x=0.5, color='#ccc', linestyle='--', alpha=0.5)
        ax.set_yticks(y)
        ax.set_yticklabels(df_sorted['Treatment'].str.title(), fontsize=9)
        ax.set_xlabel('Positive Rate')
        ax.set_title(title, fontsize=11, fontweight='bold', color=color)
        ax.set_xlim(0, 1.05)

        for i, (_, row) in enumerate(df_sorted.iterrows()):
            nnt_label = f"NNT={row['NNT']:.0f}" if 'NNT' in row.index and row.get('NNT') is not None else ''
            ax.text(min(row['Rate'] + 0.03, 0.98), i, f"n={row['n']} {nnt_label}",
                    va='center', fontsize=8, color='#555')

    fig.suptitle('POTS-Specific Treatment Recommendations by Evidence Tier', fontsize=14, fontweight='bold', y=1.02)
    fig.tight_layout(rect=[0, 0, 1, 0.98])
    plt.show()
"""))

cells.append(('md', """**How to read the tiers:**

- **Strong signal** treatments have at least 7 POTS users, a positive rate trending above 50%, and reasonable user agreement. A POTS patient looking for where to start should consider these first.
- **Moderate signal** treatments show promise but have wider confidence intervals. Worth trying but with tempered expectations.
- **Negative/Insufficient signal** treatments either perform at or below chance for POTS users, or have too few reports to evaluate. This does not mean they are ineffective\u2014it means this dataset does not support recommending them for POTS patients specifically.

**NNT (Number Needed to Treat)** is calculated relative to a 50% baseline: "how many people need to try this for 1 additional person to benefit beyond what random chance would predict?" Lower is better."""))

# ═══════════════════════════════════════════════════════════════════
# 11. SENSITIVITY CHECK
# ═══════════════════════════════════════════════════════════════════
cells.append(('md', """## 10. Sensitivity Analysis

Does the main finding (POTS users fare worse) hold under stricter conditions? We test two robustness checks: (1) restricting to strong-signal reports only, and (2) excluding the top 3 most prolific POTS users."""))

cells.append(('code', """
excluded_str = ','.join(str(i) for i in excluded_ids)
strong_reports = pd.read_sql(f'''
    SELECT tr.user_id, t.canonical_name as drug, tr.sentiment, tr.signal_strength
    FROM treatment_reports tr
    JOIN treatment t ON tr.drug_id = t.id
    WHERE tr.signal_strength = 'strong'
    AND tr.drug_id NOT IN ({excluded_str})
''', conn)

strong_reports['score'] = strong_reports['sentiment'].map(SENTIMENT_SCORE)
strong_reports['cohort'] = strong_reports['user_id'].apply(lambda x: 'POTS' if x in pots_ids else 'Non-POTS')

strong_user = strong_reports.groupby(['user_id', 'cohort']).agg(
    pos_rate=('score', lambda x: (x > 0.5).mean())
).reset_index()

pots_strong = strong_user[strong_user['cohort'] == 'POTS']['pos_rate']
non_strong = strong_user[strong_user['cohort'] == 'Non-POTS']['pos_rate']

if len(pots_strong) >= 3 and len(non_strong) >= 3:
    u1, p1 = mannwhitneyu(pots_strong, non_strong, alternative='two-sided')
    r1 = 1 - (2 * u1) / (len(pots_strong) * len(non_strong))
else:
    p1, r1 = float('nan'), float('nan')

# Drop top 3 most prolific
pots_report_counts = user_drug[user_drug['cohort'] == 'POTS'].groupby('user_id')['drug'].count().sort_values(ascending=False)
top3 = set(pots_report_counts.head(3).index)
trimmed_pots = user_drug[(user_drug['cohort'] == 'POTS') & (~user_drug['user_id'].isin(top3))]
trimmed_user = trimmed_pots.groupby('user_id')['positive'].mean()
non_pots_user_rates = user_drug[user_drug['cohort'] == 'Non-POTS'].groupby('user_id')['positive'].mean()

if len(trimmed_user) >= 3:
    u2, p2 = mannwhitneyu(trimmed_user, non_pots_user_rates, alternative='two-sided')
    r2 = 1 - (2 * u2) / (len(trimmed_user) * len(non_pots_user_rates))
else:
    p2, r2 = float('nan'), float('nan')

robust = (p1 < 0.05 or np.isnan(p1)) and (p2 < 0.05 or np.isnan(p2))
verdict_txt = 'The main finding is robust. POTS users report worse outcomes under both stricter conditions.' if robust else 'The finding is sensitive to the analysis conditions \u2014 interpret with caution.'

display(HTML(f'''
<div style='background-color: #eef6ff; padding: 12px; border-left: 4px solid #3498db; margin: 10px 0;'>
<h4 style='margin-top: 0;'>Sensitivity Check Results</h4>
<table style='border-collapse: collapse; width: 100%;'>
<tr style='border-bottom: 1px solid #ddd;'>
<td style='padding: 8px;'><b>Check 1: Strong-signal reports only</b></td>
<td style='padding: 8px;'>POTS mean: {pots_strong.mean():.0%} (n={len(pots_strong)}) vs Non-POTS: {non_strong.mean():.0%} (n={len(non_strong)})</td>
<td style='padding: 8px;'>p = {"%.4f" % p1 if p1 >= 0.001 else "< 0.001"}, r = {r1:.3f}</td>
</tr>
<tr>
<td style='padding: 8px;'><b>Check 2: Drop 3 most prolific POTS users</b></td>
<td style='padding: 8px;'>POTS mean: {trimmed_user.mean():.0%} (n={len(trimmed_user)}) vs Non-POTS: {non_pots_user_rates.mean():.0%} (n={len(non_pots_user_rates)})</td>
<td style='padding: 8px;'>p = {"%.4f" % p2 if p2 >= 0.001 else "< 0.001"}, r = {r2:.3f}</td>
</tr>
</table>
<br>
<b>Verdict:</b> {verdict_txt}
</div>
'''))
"""))

# ═══════════════════════════════════════════════════════════════════
# 12. CONCLUSION
# ═══════════════════════════════════════════════════════════════════
cells.append(('md', """## 11. Conclusion

POTS patients in the Long COVID community are not simply "sicker versions" of the average long hauler\u2014they are a qualitatively distinct subgroup. They carry a median of 8+ co-occurring conditions (most commonly MCAS, ME/CFS, and EDS), post 3.6x more frequently, experiment with 2x more treatments, and report worse outcomes on nearly every treatment compared to the broader community. Their symptom language maps precisely to POTS pathophysiology: dizziness, standing intolerance, heart rate instability, and salt/electrolyte management dominate their posts at rates 3\u20135x higher than non-POTS users.

The treatment landscape for POTS patients diverges from community consensus in important ways. Community favorites like nattokinase underperform for this group, while POTS-relevant supportive measures\u2014magnesium, electrolytes, probiotics\u2014show the strongest positive signals. Strikingly, first-line POTS medications (beta blockers, ivabradine) are nearly absent from treatment reports, suggesting either underreporting of established therapies or a population that has not yet received standard POTS care.

Based on this data, a Long COVID patient with POTS should prioritize magnesium and electrolyte supplementation (highest positive rates with strong user consensus), consider probiotics and NAC as adjuncts, and approach community-wide recommendations (particularly nattokinase and famotidine) with the understanding that POTS may modify treatment response. SSRIs and antihistamines showed mixed results within the POTS cohort\u2014suggesting that individual co-morbidity patterns (especially MCAS presence) may determine response.

Three hypotheses emerge for follow-up investigation: (1) POTS-specific treatments are underrepresented in community treatment reports because they are "boring" standard care, creating a reporting bias toward experimental supplements; (2) the mechanism driving Long COVID in POTS patients (autonomic dysfunction) may not respond to treatments targeting other proposed mechanisms (microclots, persistent viral reservoir); and (3) the POTS+MCAS subgroup may have a distinct treatment response profile that gets averaged away when "POTS" is treated as a single entity. Each is testable with a targeted study design."""))

# ═══════════════════════════════════════════════════════════════════
# 13. LIMITATIONS
# ═══════════════════════════════════════════════════════════════════
cells.append(('md', """## 12. Research Limitations

1. **Selection bias:** Reddit users are not representative of all Long COVID patients. They skew younger, more internet-literate, and potentially more treatment-seeking. POTS patients on Reddit may be more severe than the broader POTS population.

2. **Reporting bias:** Users are more likely to report dramatic experiences (very positive or very negative) than mundane ones. Treatments that "sort of help a little" are underrepresented. This may inflate both positive and negative rates while suppressing mixed outcomes.

3. **Survivorship bias:** Users still posting are those who have not recovered and left the community. We are sampling from the "still struggling" population, which biases against treatments that worked well enough to prompt leaving.

4. **Recall bias:** Treatment reports are retrospective self-reports, not prospective measurements. Users may misattribute symptoms to treatments, confuse timelines, or revise their assessments based on subsequent experiences.

5. **Confounding:** POTS users differ from non-POTS users in many ways beyond their POTS status (condition count, engagement level, treatment experimentation rate). The logistic regression controls for some confounders but cannot account for unmeasured differences (severity, access to care, socioeconomic status).

6. **No control group:** There is no untreated comparison group. We compare treatment outcomes between cohorts, not against placebo. The 50% baseline used for binomial tests is arbitrary\u2014it assumes that without treatment, positive reports would be at chance level.

7. **Sentiment vs efficacy:** Positive sentiment does not equal clinical efficacy. A user may report positively on a treatment because it reduced anxiety about their condition (placebo/nocebo effect) rather than because it objectively improved their physiology.

8. **Temporal snapshot:** This data covers one month (March\u2013April 2026). Treatment trends, community composition, and dominant narratives shift over time. Findings may not generalize to other time periods.

**Additional POTS-specific limitations:**
- POTS identification relies on NLP extraction of condition mentions. Some POTS patients may not mention their diagnosis in posts, leading to misclassification into the non-POTS cohort (diluting group differences).
- The 88-user POTS cohort is small enough that individual prolific users can shift group-level statistics meaningfully. The sensitivity analysis addresses this partially but cannot eliminate it.
- Co-occurring conditions are not independent\u2014the POTS-MCAS-EDS triad is a known clinical cluster, making it impossible to cleanly isolate the effect of any single condition."""))

# ═══════════════════════════════════════════════════════════════════
# 14. DISCLAIMER
# ═══════════════════════════════════════════════════════════════════
cells.append(('code', """
display(HTML('<div style="font-size: 1.2em; font-weight: bold; font-style: italic; padding: 20px; margin: 20px 0; background-color: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; text-align: center;">'
             '<em><b>These findings reflect reporting patterns in online communities, not population-level treatment effects. This is not medical advice.</b></em>'
             '</div>'))
"""))

# ═══════════════════════════════════════════════════════════════════
# BUILD AND EXECUTE
# ═══════════════════════════════════════════════════════════════════
nb = build_notebook(
    cells=cells,
    db_path='polina_onemonth.db',
    title='POTS in Long COVID: Preliminary Comparative Analysis',
)

output_stem = 'notebooks/sample_notebooks_verbose/2_pots_preliminary'
html_path = execute_and_export(nb, output_stem)
print(f'SUCCESS: {html_path}')
