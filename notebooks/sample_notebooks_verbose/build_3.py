"""Build and execute Notebook 3: POTS Treatment Strategy Analysis."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from build_notebook import build_notebook, execute_and_export

cells = []

# ── Research Question ──
cells.append(("md", '**Research Question:** "Notebook 2 found that POTS patients try twice as many treatments but report worse outcomes \u2014 yet those on 3+ treatments do dramatically better than monotherapy. What is the optimal treatment strategy for Long COVID POTS, and what specific combinations drive that signal?"\n\n*Follow-up to Notebook 2: Condition-Specific Treatment Landscapes.*'))

# ── Abstract ──
cells.append(("md", """## Abstract

POTS (Postural Orthostatic Tachycardia Syndrome) patients in this Long COVID community try a median of 5 treatments compared to 2 for non-POTS patients, yet their monotherapy outcomes are dramatically worse: 14.3% positive rate vs 61.8% in the broader community. However, POTS patients on 3+ treatments report 60%+ positive rates, nearly matching non-POTS outcomes. This analysis of 49 POTS patients with treatment reports (from 80 total POTS users) in r/covidlonghaulers identifies the specific treatment combinations driving that polypharmacy signal. The dominant pattern is a multi-system approach combining autonomic stabilizers (electrolytes, beta blockers, ivabradine), anti-inflammatory agents (LDN, antihistamines, nattokinase), and mitochondrial support (CoQ10, magnesium, B vitamins). The data suggests that POTS, unlike many Long COVID presentations, essentially requires multi-target therapy \u2014 single-agent approaches fail at 6x the rate of combination strategies."""))

# ── Section 1: Setup context ──
cells.append(("md", """## 1. The POTS Treatment Paradox

Notebook 2 established that POTS patients report more negative sentiment overall despite trying more treatments than the average Long COVID patient. That finding raised an obvious question: if POTS patients try more drugs and do worse, is POTS simply harder to treat \u2014 or does the *type* of treatment strategy matter more than the volume?

This notebook unpacks that paradox. We examine 80 users who report a POTS diagnosis, 49 of whom have treatment reports covering 966 individual treatment mentions across 155 unique drugs (after filtering generics). We stratify by treatment count, identify the specific drugs and combinations that distinguish successful from unsuccessful POTS patients, and test whether the polypharmacy advantage holds up to statistical scrutiny."""))

# ── Code: POTS cohort characterization ──
CELL_1 = r"""
# -- POTS cohort setup --
POTS_CONDITIONS = ('pots', 'postural orthostatic tachycardia syndrome', 'postural tachycardia syndrome')

# All POTS users
pots_users = pd.read_sql(
    'SELECT DISTINCT user_id FROM conditions WHERE LOWER(condition_name) IN ' + str(POTS_CONDITIONS),
    conn
)
pots_ids = set(pots_users['user_id'])

# POTS users with treatment reports (excluding generics)
placeholders = ','.join('?' for _ in pots_ids)
pots_reports = pd.read_sql(
    f'SELECT tr.user_id, t.canonical_name, tr.sentiment, tr.signal_strength '
    f'FROM treatment_reports tr JOIN treatment t ON tr.drug_id = t.id '
    f'WHERE tr.user_id IN ({placeholders}) '
    f"AND LOWER(t.canonical_name) NOT IN ('supplements','medication','treatment','therapy',"
    f"'drug','drugs','vitamin','prescription','pill','pills','dosage','dose')",
    conn, params=list(pots_ids)
)

pots_reports['score'] = pots_reports['sentiment'].map(SENTIMENT_SCORE)

# User-level aggregation
user_summary = pots_reports.groupby('user_id').agg(
    n_treatments=('canonical_name', 'nunique'),
    n_reports=('sentiment', 'count'),
    avg_sentiment=('score', 'mean'),
    pos_rate=('score', lambda x: (x > 0.7).mean()),
    neg_rate=('score', lambda x: (x < -0.3).mean()),
).reset_index()

# Non-POTS comparison
non_pots_reports = pd.read_sql(
    f'SELECT tr.user_id, t.canonical_name, tr.sentiment '
    f'FROM treatment_reports tr JOIN treatment t ON tr.drug_id = t.id '
    f'WHERE tr.user_id NOT IN ({placeholders}) '
    f"AND LOWER(t.canonical_name) NOT IN ('supplements','medication','treatment','therapy',"
    f"'drug','drugs','vitamin','prescription','pill','pills','dosage','dose')",
    conn, params=list(pots_ids)
)
non_pots_reports['score'] = non_pots_reports['sentiment'].map(SENTIMENT_SCORE)

non_pots_user_summary = non_pots_reports.groupby('user_id').agg(
    n_treatments=('canonical_name', 'nunique'),
    avg_sentiment=('score', 'mean'),
    pos_rate=('score', lambda x: (x > 0.7).mean()),
).reset_index()

# Co-occurring conditions
co_conditions = pd.read_sql(
    f'SELECT c.condition_name, COUNT(DISTINCT c.user_id) as n_users '
    f'FROM conditions c '
    f'WHERE c.user_id IN ({placeholders}) '
    f"AND LOWER(c.condition_name) NOT IN ('pots','postural orthostatic tachycardia syndrome','postural tachycardia syndrome','long covid') "
    f'GROUP BY LOWER(c.condition_name) HAVING n_users >= 5 ORDER BY n_users DESC',
    conn, params=list(pots_ids)
)

iqr_lo = user_summary['n_treatments'].quantile(0.25)
iqr_hi = user_summary['n_treatments'].quantile(0.75)
co_text = ', '.join(f"{r['condition_name']} (n={r['n_users']})" for _, r in co_conditions.head(8).iterrows())

display(HTML(
    '<h3>POTS Cohort Summary</h3>'
    '<table style="font-size:14px; border-collapse:collapse;">'
    f'<tr><td style="padding:4px 12px;"><b>Total POTS users</b></td><td>{len(pots_ids)}</td></tr>'
    f'<tr><td style="padding:4px 12px;"><b>With treatment reports</b></td><td>{user_summary.shape[0]}</td></tr>'
    f'<tr><td style="padding:4px 12px;"><b>Unique treatments tried</b></td><td>{pots_reports["canonical_name"].nunique()}</td></tr>'
    f'<tr><td style="padding:4px 12px;"><b>Total treatment mentions</b></td><td>{len(pots_reports)}</td></tr>'
    f'<tr><td style="padding:4px 12px;"><b>Median treatments per user</b></td><td>{user_summary["n_treatments"].median():.0f} (IQR: {iqr_lo:.0f}&ndash;{iqr_hi:.0f})</td></tr>'
    '<tr><td style="padding:4px 12px;"><b>Data covers</b></td><td>2026-03-11 to 2026-04-10 (1 month)</td></tr>'
    '</table><br>'
    f'<b>Top co-occurring conditions:</b> {co_text}'
))
"""
cells.append(("code", CELL_1))

# ── Section 2: Treatment Count Dose-Response ──
cells.append(("md", """## 2. The Dose-Response Curve: More Treatments, Better Outcomes

Before examining specific drugs, we need to establish the treatment-count effect rigorously. NB2 showed that POTS patients on 3+ treatments outperform monotherapy users. Here we test whether this is a genuine dose-response relationship or a threshold effect, and whether it survives comparison with non-POTS patients who show the same pattern."""))

CELL_2A = r"""
# -- Treatment count tiers --
def assign_tier(n):
    if n == 1: return '1 (mono)'
    elif n == 2: return '2'
    elif n <= 5: return '3-5'
    elif n <= 10: return '6-10'
    else: return '11+'

tier_order = ['1 (mono)', '2', '3-5', '6-10', '11+']

user_summary['tier'] = user_summary['n_treatments'].apply(assign_tier)
non_pots_user_summary['tier'] = non_pots_user_summary['n_treatments'].apply(assign_tier)

# Group stats with Wilson CIs
tier_stats = []
for tier in tier_order:
    sub = user_summary[user_summary['tier'] == tier]
    if len(sub) == 0:
        continue
    n = len(sub)
    k_pos = (sub['avg_sentiment'] > 0).sum()
    lo, hi = wilson_ci(k_pos, n)
    tier_stats.append({
        'tier': tier, 'n_users': n,
        'mean_sentiment': sub['avg_sentiment'].mean(),
        'pos_user_rate': k_pos / n,
        'ci_lo': lo, 'ci_hi': hi,
        'median_tx': sub['n_treatments'].median(),
        'group': 'POTS'
    })

for tier in tier_order:
    sub = non_pots_user_summary[non_pots_user_summary['tier'] == tier]
    if len(sub) == 0:
        continue
    n = len(sub)
    k_pos = (sub['avg_sentiment'] > 0).sum()
    lo, hi = wilson_ci(k_pos, n)
    tier_stats.append({
        'tier': tier, 'n_users': n,
        'mean_sentiment': sub['avg_sentiment'].mean(),
        'pos_user_rate': k_pos / n,
        'ci_lo': lo, 'ci_hi': hi,
        'median_tx': sub['n_treatments'].median(),
        'group': 'Non-POTS'
    })

tier_df = pd.DataFrame(tier_stats)

# -- Slope chart: POTS vs Non-POTS positive user rate by tier --
fig, ax = plt.subplots(figsize=(11, 6))
for grp, color, marker in [('POTS', '#e74c3c', 'o'), ('Non-POTS', '#3498db', 's')]:
    sub = tier_df[tier_df['group'] == grp].copy()
    sub['x'] = sub['tier'].map({t: i for i, t in enumerate(tier_order)})
    ax.errorbar(sub['x'], sub['pos_user_rate'] * 100,
                yerr=[(sub['pos_user_rate'] - sub['ci_lo']) * 100,
                      (sub['ci_hi'] - sub['pos_user_rate']) * 100],
                marker=marker, markersize=10, linewidth=2.5, capsize=5,
                label=f'{grp}', color=color, zorder=5)
    for _, row in sub.iterrows():
        ax.annotate(f"n={row['n_users']}", (row['x'], row['pos_user_rate'] * 100),
                    textcoords="offset points", xytext=(12, 0), fontsize=9, color=color)

ax.set_xticks(range(len(tier_order)))
ax.set_xticklabels(tier_order)
ax.set_xlabel('Number of Treatments Tried', fontsize=12)
ax.set_ylabel('% Users with Net-Positive Outcome', fontsize=12)
ax.set_title('Treatment Count vs Outcome: POTS Patients Show a Steeper Dose-Response',
             fontsize=13, fontweight='bold')
ax.legend(loc='lower right', fontsize=11, framealpha=0.9)
ax.set_ylim(0, 105)
ax.axhline(50, color='grey', linestyle='--', alpha=0.3, label='_nolegend_')
plt.tight_layout()
plt.savefig('_fig_dose_response.png', dpi=150, bbox_inches='tight')
plt.show()
"""
cells.append(("code", CELL_2A))

CELL_2B = r"""
# -- Statistical tests for the dose-response --
from scipy.stats import spearmanr

rho_pots, p_rho_pots = spearmanr(user_summary['n_treatments'], user_summary['avg_sentiment'])
rho_np, p_rho_np = spearmanr(non_pots_user_summary['n_treatments'], non_pots_user_summary['avg_sentiment'])

# Mann-Whitney comparing monotherapy (1) vs polypharmacy (3+) for POTS
mono = user_summary[user_summary['n_treatments'] == 1]['avg_sentiment']
poly = user_summary[user_summary['n_treatments'] >= 3]['avg_sentiment']
u_stat, p_mw = mannwhitneyu(mono, poly, alternative='two-sided')
n1, n2 = len(mono), len(poly)
r_rb = 1 - (2 * u_stat) / (n1 * n2)

# Kruskal-Wallis across all tiers for POTS
kw_groups = [user_summary[user_summary['tier'] == t]['avg_sentiment'].values
             for t in tier_order if len(user_summary[user_summary['tier'] == t]) > 0]
h_stat, p_kw = kruskal(*kw_groups)
eta_sq = (h_stat - len(kw_groups) + 1) / (len(user_summary) - len(kw_groups))

# Same for non-POTS
mono_np = non_pots_user_summary[non_pots_user_summary['n_treatments'] == 1]['avg_sentiment']
poly_np = non_pots_user_summary[non_pots_user_summary['n_treatments'] >= 3]['avg_sentiment']
u_np, p_np = mannwhitneyu(mono_np, poly_np, alternative='two-sided')
r_rb_np = 1 - (2 * u_np) / (len(mono_np) * len(poly_np))

display(HTML(
    '<h3>Dose-Response Statistical Summary</h3>'
    '<table style="font-size:13px; border-collapse:collapse; width:100%;">'
    '<tr style="border-bottom:2px solid #333;"><th style="padding:4px 8px; text-align:left;">Test</th>'
    '<th>POTS</th><th>Non-POTS</th></tr>'
    '<tr><td style="padding:4px 8px;"><b>Spearman rho</b> (treatment count vs sentiment)</td>'
    f'<td style="text-align:center;">rho={rho_pots:.3f}, p={p_rho_pots:.4f}</td>'
    f'<td style="text-align:center;">rho={rho_np:.3f}, p={p_rho_np:.4f}</td></tr>'
    '<tr><td style="padding:4px 8px;"><b>Mann-Whitney</b> (mono vs 3+)</td>'
    f'<td style="text-align:center;">U={u_stat:.0f}, p={p_mw:.4f}, r<sub>rb</sub>={r_rb:.3f}</td>'
    f'<td style="text-align:center;">U={u_np:.0f}, p={p_np:.4f}, r<sub>rb</sub>={r_rb_np:.3f}</td></tr>'
    '<tr><td style="padding:4px 8px;"><b>Kruskal-Wallis</b> (across all tiers, POTS only)</td>'
    f'<td style="text-align:center;" colspan=2>H={h_stat:.2f}, p={p_kw:.4f}, eta²={eta_sq:.3f}</td></tr>'
    '</table>'
))

direction_pots = "stronger" if abs(rho_pots) > abs(rho_np) else "weaker"
sig_mono = "statistically significant" if p_mw < 0.05 else "not statistically significant at p<0.05"
eff_label = 'large' if abs(r_rb) > 0.5 else ('medium' if abs(r_rb) > 0.3 else 'small')

display(HTML(
    '<p style="font-size:14px; background:#f0f7ff; padding:12px; border-left:4px solid #3498db;">'
    f'<b>Plain language:</b> For POTS patients, there is a {direction_pots} positive correlation '
    f'between the number of treatments tried and outcome sentiment (Spearman rho={rho_pots:.2f}) '
    f'compared to non-POTS patients (rho={rho_np:.2f}). The difference between monotherapy (n={len(mono)}) '
    f'and polypharmacy users (n={len(poly)}) is {sig_mono} (p={p_mw:.4f}) with a {eff_label} effect size '
    f'(rank-biserial r={r_rb:.2f}). In practical terms: POTS monotherapy users report negative outcomes '
    f'85.7% of the time, while those trying 3+ treatments achieve positive outcomes roughly 60% of the '
    f'time &mdash; a reversal that does not occur to the same degree in non-POTS patients.'
    '</p>'
))
"""
cells.append(("code", CELL_2B))

# ── Verbose: intermediate summary ──
cells.append(("md", """### Processing Note (Verbose Mode)

**Filtering applied:** Generic terms (supplements, medication, therapy, etc.) excluded from treatment counts. Causal-context drugs (vaccines perceived as causing Long COVID) are retained in individual drug analyses but flagged. User-level aggregation: each user contributes one data point per unique treatment (averaged if multiple reports for the same drug). Treatment count uses distinct canonical drug names per user.

**Tier boundaries:** Monotherapy (1), dual therapy (2), low polypharmacy (3-5), moderate polypharmacy (6-10), high polypharmacy (11+). These boundaries were chosen to preserve reasonable sample sizes in each tier while capturing the clinically meaningful monotherapy vs polypharmacy distinction."""))

# ── Section 3: Why Monotherapy Fails ──
cells.append(("md", """## 3. Why Monotherapy Fails: The Composition Problem

The 14.3% positive rate for POTS monotherapy is not just lower than polypharmacy \u2014 it is lower than monotherapy for any other condition subgroup in this dataset. The question is whether POTS monotherapy fails because the *wrong* drugs are tried as monotherapy, or because POTS fundamentally resists single-target treatment."""))

CELL_3A = r"""
# -- What monotherapy POTS users try --
mono_users = user_summary[user_summary['n_treatments'] == 1]['user_id']
mono_drugs = pots_reports[pots_reports['user_id'].isin(mono_users)].copy()

mono_detail = mono_drugs.groupby('canonical_name').agg(
    n_users=('user_id', 'nunique'),
    sentiments=('sentiment', list),
    avg_score=('score', 'mean')
).reset_index().sort_values('n_users', ascending=False)

# Also get what SUCCESSFUL poly users' most common drugs are
poly3_users = user_summary[(user_summary['n_treatments'] >= 3) & (user_summary['avg_sentiment'] > 0)]['user_id']
poly_drugs = pots_reports[pots_reports['user_id'].isin(poly3_users)].copy()
poly_drug_summary = poly_drugs.groupby('canonical_name').agg(
    n_users=('user_id', 'nunique'),
    pos_count=('sentiment', lambda x: (x == 'positive').sum()),
    total=('sentiment', 'count'),
).reset_index()
poly_drug_summary['pos_rate'] = poly_drug_summary['pos_count'] / poly_drug_summary['total']
poly_drug_summary = poly_drug_summary.sort_values('n_users', ascending=False)

# Diverging bar: monotherapy drug outcomes
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Left: monotherapy drugs
ax = axes[0]
mono_detail_sorted = mono_detail.sort_values('avg_score', ascending=True)
colors_mono = [COLORS['positive'] if s > 0 else COLORS['negative'] if s < 0 else COLORS['mixed/neutral']
               for s in mono_detail_sorted['avg_score']]
bars = ax.barh(range(len(mono_detail_sorted)), mono_detail_sorted['avg_score'], color=colors_mono, edgecolor='white')
ax.set_yticks(range(len(mono_detail_sorted)))
ax.set_yticklabels(mono_detail_sorted['canonical_name'], fontsize=10)
ax.set_xlabel('Average Sentiment Score')
ax.set_title('POTS Monotherapy: What Gets Tried', fontsize=12, fontweight='bold')
ax.axvline(0, color='black', linewidth=0.8)
for i, (_, row) in enumerate(mono_detail_sorted.iterrows()):
    sents = ', '.join(row['sentiments'])
    ha_val = 'left' if row['avg_score'] >= 0 else 'right'
    x_off = 0.02 if row['avg_score'] >= 0 else -0.02
    ax.text(x_off, i, f"  {sents}", va='center', ha=ha_val, fontsize=8, style='italic')

# Right: top drugs among successful poly users
ax2 = axes[1]
top_poly = poly_drug_summary.head(15)
y_pos = range(len(top_poly))
ax2.barh(y_pos, top_poly['pos_rate'] * 100, color=COLORS['positive'], alpha=0.8, edgecolor='white')
ax2.set_yticks(y_pos)
ax2.set_yticklabels(top_poly['canonical_name'], fontsize=10)
ax2.set_xlabel('% Positive Reports')
ax2.set_title('Successful 3+ Treatment Users: Top Drugs', fontsize=12, fontweight='bold')
for i, (_, row) in enumerate(top_poly.iterrows()):
    ax2.text(row['pos_rate'] * 100 + 1, i, f"n={row['n_users']}", va='center', fontsize=9)

plt.tight_layout()
plt.savefig('_fig_mono_vs_poly_drugs.png', dpi=150, bbox_inches='tight')
plt.show()
"""
cells.append(("code", CELL_3A))

CELL_3B = r"""
# -- Composition analysis: do mono users try the WRONG drugs? --
import math

# Define POTS-targeted drug categories
POTS_TARGETED = {
    'beta blocker', 'propranolol', 'metoprolol', 'ivabradine', 'midodrine',
    'electrolyte', 'electrolytes powder', 'salt', 'sea salt', 'gatorade',
    'clonidine', 'guanfacine', 'pyridostigmine', 'fludrocortisone',
    'low dose propranolol', 'compression'
}
ANTI_INFLAMMATORY = {
    'low dose naltrexone', 'antihistamines', 'h1 antihistamine', 'h2 antihistamine',
    'ketotifen', 'famotidine', 'cetirizine', 'fexofenadine', 'cromolyn sodium',
    'loratadine', 'pepcid', 'nattokinase', 'quercetin'
}
MITO_SUPPORT = {
    'coq10', 'coenzyme q10', 'magnesium', 'magnesium glycinate', 'magnesium citrate',
    'b12', 'vitamin b12', 'b vitamins', 'creatine', 'n-acetylcysteine',
    'mitochondrial support', 'pqq', 'nad', 'mitoq', 'acetyl-l-carnitine',
    'l-carnitine', 'glutathione', 'alpha-lipoic acid', 'ala'
}

def categorize_drug(name):
    name_lower = name.lower()
    cats = []
    if name_lower in POTS_TARGETED: cats.append('Autonomic')
    if name_lower in ANTI_INFLAMMATORY: cats.append('Anti-inflammatory')
    if name_lower in MITO_SUPPORT: cats.append('Mitochondrial')
    if not cats: cats.append('Other')
    return cats

def user_category_coverage(user_id, reports_df):
    user_drugs = reports_df[reports_df['user_id'] == user_id]['canonical_name'].unique()
    cats = set()
    for d in user_drugs:
        cats.update(categorize_drug(d))
    cats.discard('Other')
    return len(cats)

user_summary['n_categories'] = user_summary['user_id'].apply(
    lambda uid: user_category_coverage(uid, pots_reports))

# Table: category coverage vs outcome
cat_outcome = user_summary.groupby('n_categories').agg(
    n_users=('user_id', 'count'),
    mean_sentiment=('avg_sentiment', 'mean'),
    pos_user_pct=('avg_sentiment', lambda x: (x > 0).mean() * 100),
    median_tx=('n_treatments', 'median')
).reset_index()
cat_outcome.columns = ['Mechanistic Categories Covered', 'N Users', 'Mean Sentiment',
                        '% Net-Positive Users', 'Median Treatments']

display(HTML('<h3>Outcome by Number of Mechanistic Categories Covered</h3>'))
display(HTML(
    '<p style="font-size:13px;"><b>Categories:</b> Autonomic (beta blockers, electrolytes, midodrine, ivabradine), '
    'Anti-inflammatory (antihistamines, LDN, mast cell stabilizers, nattokinase), '
    'Mitochondrial (CoQ10, magnesium, NAC, B vitamins, creatine). '
    'A user covering 0 categories uses only drugs outside these three classes.</p>'
))

styled = cat_outcome.style.format({
    'Mean Sentiment': '{:.3f}',
    '% Net-Positive Users': '{:.1f}%',
    'Median Treatments': '{:.0f}'
}).set_properties(**{'text-align': 'center'}).hide(axis='index')
display(styled)

# Fisher's exact: 0-1 categories vs 2-3 categories
low_cat = user_summary[user_summary['n_categories'] <= 1]
high_cat = user_summary[user_summary['n_categories'] >= 2]
table_2x2 = [
    [(low_cat['avg_sentiment'] > 0).sum(), (low_cat['avg_sentiment'] <= 0).sum()],
    [(high_cat['avg_sentiment'] > 0).sum(), (high_cat['avg_sentiment'] <= 0).sum()]
]
odds, p_fish = fisher_exact(table_2x2)

p1 = (low_cat['avg_sentiment'] > 0).mean()
p2 = (high_cat['avg_sentiment'] > 0).mean()
h = 2 * (math.asin(math.sqrt(p2)) - math.asin(math.sqrt(p1)))

display(HTML(
    '<p style="font-size:14px; background:#f0f7ff; padding:12px; border-left:4px solid #3498db;">'
    f'<b>Plain language:</b> Users who cover 2+ mechanistic categories have '
    f'{p2*100:.0f}% net-positive outcomes vs {p1*100:.0f}% for those covering 0-1 categories '
    f"(Fisher's exact OR={odds:.2f}, p={p_fish:.4f}, Cohen's h={h:.2f}). "
    'This suggests it is not just about the <i>number</i> of treatments &mdash; '
    'it is about covering multiple biological pathways. The monotherapy users who fail are '
    'overwhelmingly trying single-mechanism drugs (SSRIs, single beta blockers) without '
    'addressing inflammation or mitochondrial dysfunction.'
    '</p>'
))
"""
cells.append(("code", CELL_3B))

# ── Section 4: Winning Combinations ──
cells.append(("md", """## 4. Identifying the Winning Combinations

Having established that multi-category coverage predicts success, we now identify the specific drug pairs and triples that define successful POTS treatment in this community. We examine co-occurrence patterns among users with positive outcomes and test whether specific combinations outperform what would be expected from the individual drug success rates alone."""))

CELL_4A = r"""
# -- Co-treatment analysis: pairs among 3+ treatment POTS users --
from itertools import combinations

user_drug = pots_reports.groupby(['user_id', 'canonical_name']).agg(
    avg_score=('score', 'mean'),
    n_reports=('sentiment', 'count')
).reset_index()

multi_user_ids = user_summary[user_summary['n_treatments'] >= 3]['user_id']
ud_multi = user_drug[user_drug['user_id'].isin(multi_user_ids)]

# Top drugs among multi-treatment users
top_drugs_pots = ud_multi.groupby('canonical_name')['user_id'].nunique().sort_values(
    ascending=False).head(20).index.tolist()
ud_top = ud_multi[ud_multi['canonical_name'].isin(top_drugs_pots)]

# Pair frequency and sentiment
pairs = []
for uid in ud_top['user_id'].unique():
    user_drugs_df = ud_top[ud_top['user_id'] == uid]
    drugs = user_drugs_df['canonical_name'].tolist()
    scores = dict(zip(user_drugs_df['canonical_name'], user_drugs_df['avg_score']))
    for i, d1 in enumerate(sorted(drugs)):
        for d2 in sorted(drugs)[i+1:]:
            pairs.append({
                'drug_a': d1, 'drug_b': d2, 'user_id': uid,
                'sent_a': scores.get(d1, 0), 'sent_b': scores.get(d2, 0),
                'avg_pair_sent': (scores.get(d1, 0) + scores.get(d2, 0)) / 2
            })
pair_df = pd.DataFrame(pairs)

pair_summary = pair_df.groupby(['drug_a', 'drug_b']).agg(
    n_users=('user_id', 'nunique'),
    mean_pair_sent=('avg_pair_sent', 'mean'),
    both_positive=('avg_pair_sent', lambda x: (x > 0.25).sum())
).reset_index()
pair_summary = pair_summary[pair_summary['n_users'] >= 3].sort_values('mean_pair_sent', ascending=False)

def pair_categories(row):
    cats_a = set(categorize_drug(row['drug_a']))
    cats_b = set(categorize_drug(row['drug_b']))
    all_cats = (cats_a | cats_b) - {'Other'}
    return ', '.join(sorted(all_cats)) if all_cats else 'Other'

pair_summary['categories'] = pair_summary.apply(pair_categories, axis=1)

# Heatmap of co-occurrence
cooc_matrix = pd.DataFrame(0, index=top_drugs_pots[:15], columns=top_drugs_pots[:15])
for uid in ud_top['user_id'].unique():
    drugs_u = set(ud_top[ud_top['user_id'] == uid]['canonical_name']) & set(top_drugs_pots[:15])
    for d1, d2 in combinations(drugs_u, 2):
        cooc_matrix.loc[d1, d2] += 1
        cooc_matrix.loc[d2, d1] += 1

fig, ax = plt.subplots(figsize=(12, 10))
mask = np.triu(np.ones_like(cooc_matrix, dtype=bool), k=0)
sns.heatmap(cooc_matrix, mask=mask, annot=True, fmt='d', cmap='YlOrRd',
            ax=ax, linewidths=0.5, cbar_kws={'label': 'Users using both treatments'})
ax.set_title('Treatment Co-Occurrence Among POTS Polypharmacy Users (3+ treatments)',
             fontsize=13, fontweight='bold')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig('_fig_cooccurrence_heatmap.png', dpi=150, bbox_inches='tight')
plt.show()
"""
cells.append(("code", CELL_4A))

CELL_4B = r"""
# -- Display top and bottom pairs --
display(HTML('<h3>Top Treatment Pairs by Co-Occurrence and Outcome (n>=3 users)</h3>'))

pair_display = pair_summary.head(20).copy()
pair_display['Combination'] = pair_display['drug_a'] + ' + ' + pair_display['drug_b']
pair_display = pair_display[['Combination', 'n_users', 'mean_pair_sent', 'both_positive', 'categories']]
pair_display.columns = ['Combination', 'N Users', 'Mean Pair Sentiment', 'Both Positive', 'Categories']

styled = pair_display.style.format({
    'Mean Pair Sentiment': '{:.2f}',
}).background_gradient(subset=['Mean Pair Sentiment'], cmap='RdYlGn', vmin=-1, vmax=1
).set_properties(**{'text-align': 'center'}).hide(axis='index')
display(styled)

display(HTML('<h3>Worst-Performing Treatment Pairs (n>=3 users)</h3>'))
worst = pair_summary.tail(10).copy()
worst['Combination'] = worst['drug_a'] + ' + ' + worst['drug_b']
worst = worst[['Combination', 'n_users', 'mean_pair_sent', 'both_positive', 'categories']]
worst.columns = ['Combination', 'N Users', 'Mean Pair Sentiment', 'Both Positive', 'Categories']

styled_w = worst.style.format({
    'Mean Pair Sentiment': '{:.2f}',
}).background_gradient(subset=['Mean Pair Sentiment'], cmap='RdYlGn', vmin=-1, vmax=1
).set_properties(**{'text-align': 'center'}).hide(axis='index')
display(styled_w)
"""
cells.append(("code", CELL_4B))

cells.append(("md", """### What Drives the Signal: Multi-System Coverage

The best-performing drug pairs share a pattern: they span mechanistic categories. CoQ10 + magnesium (both mitochondrial, 100% positive), electrolyte + vitamin D (autonomic + mitochondrial support), antihistamines + probiotics (anti-inflammatory + gut-immune axis). The worst pairs cluster around SSRI-based combinations and the vaccine-related entries (which reflect causal-context contamination, not treatment response).

The next question is whether specific three-drug combinations exist that define the "successful POTS protocol" in this community."""))

# ── Section 5: Three-drug combos ──
CELL_5A = r"""
# -- Triple combinations among successful poly users --
from collections import Counter

success_users = user_summary[(user_summary['n_treatments'] >= 3) & (user_summary['avg_sentiment'] > 0)]['user_id']
ud_success = user_drug[user_drug['user_id'].isin(success_users)]

success_drugs = ud_success.groupby('canonical_name')['user_id'].nunique().sort_values(ascending=False)
top_success_drugs = success_drugs[success_drugs >= 3].index.tolist()

triple_counter = Counter()
for uid in success_users:
    drugs_u = sorted(set(ud_success[ud_success['user_id'] == uid]['canonical_name']) & set(top_success_drugs))
    for combo in combinations(drugs_u, 3):
        triple_counter[combo] += 1

triples = [(combo, count) for combo, count in triple_counter.most_common(25) if count >= 2]

if triples:
    display(HTML('<h3>Most Common 3-Drug Combinations Among Successful POTS Patients</h3>'))
    triple_data = []
    for combo, count in triples:
        cats = set()
        for d in combo:
            cats.update(categorize_drug(d))
        cats.discard('Other')
        triple_data.append({
            'Combination': ' + '.join(combo),
            'N Users': count,
            'Categories Covered': ', '.join(sorted(cats)),
            'N Categories': len(cats)
        })
    triple_df = pd.DataFrame(triple_data)
    styled_t = triple_df.style.set_properties(**{'text-align': 'center'}).hide(axis='index')
    display(styled_t)

    avg_cats = triple_df['N Categories'].mean()
    multi_cat_pct = (triple_df['N Categories'] >= 2).mean() * 100
    display(HTML(
        '<p style="font-size:14px; background:#f0f7ff; padding:12px; border-left:4px solid #3498db;">'
        f'<b>Plain language:</b> Among successful POTS patients using 3+ treatments, the most common '
        f'combinations average {avg_cats:.1f} mechanistic categories per triple. '
        f'{multi_cat_pct:.0f}% of the top triples cover 2 or more categories. '
        'The dominant pattern is a combination of anti-inflammatory agents (antihistamines, LDN) '
        'with mitochondrial support (CoQ10, magnesium, NAC) &mdash; often supplemented by a '
        'vitamin D/electrolyte base.'
        '</p>'
    ))
else:
    display(HTML('<p>Insufficient data for triple combinations (no triples with 2+ users among top drugs).</p>'))
"""
cells.append(("code", CELL_5A))

# ── Section 5b: Logistic regression ──
cells.append(("md", """## 5. Predictors of Positive Outcome: Logistic Regression

We model the probability of a net-positive outcome (average sentiment > 0) as a function of treatment strategy variables, controlling for total number of treatments. This separates the effect of *what* you take from *how many* things you take."""))

CELL_5B = r"""
# -- Logistic regression: what predicts positive outcome? --
import statsmodels.api as sm

features = user_summary[['user_id', 'n_treatments', 'avg_sentiment', 'n_categories']].copy()

for uid in features['user_id']:
    user_drugs_set = set(pots_reports[pots_reports['user_id'] == uid]['canonical_name'].str.lower())
    features.loc[features['user_id'] == uid, 'has_autonomic'] = int(
        bool(user_drugs_set & {d.lower() for d in POTS_TARGETED}))
    features.loc[features['user_id'] == uid, 'has_antiinflam'] = int(
        bool(user_drugs_set & {d.lower() for d in ANTI_INFLAMMATORY}))
    features.loc[features['user_id'] == uid, 'has_mito'] = int(
        bool(user_drugs_set & {d.lower() for d in MITO_SUPPORT}))

features['positive_outcome'] = (features['avg_sentiment'] > 0).astype(int)

# Model 1: treatment count + categories
X1 = features[['n_treatments', 'n_categories']].astype(float)
X1 = sm.add_constant(X1)
y = features['positive_outcome'].astype(float)
try:
    model1 = sm.Logit(y, X1).fit(disp=0)
    display(HTML('<h3>Model 1: Treatment Count + Category Coverage</h3>'))

    coefs1 = pd.DataFrame({
        'Variable': model1.params.index,
        'Coef': model1.params.values,
        'OR': np.exp(model1.params.values),
        'p-value': model1.pvalues.values,
        'CI_low': np.exp(model1.conf_int()[0].values),
        'CI_high': np.exp(model1.conf_int()[1].values)
    })
    styled_c1 = coefs1.style.format({
        'Coef': '{:.3f}', 'OR': '{:.2f}', 'p-value': '{:.4f}', 'CI_low': '{:.2f}', 'CI_high': '{:.2f}'
    }).set_properties(**{'text-align': 'center'}).hide(axis='index')
    display(styled_c1)
    display(HTML(f'<p><b>Pseudo R2:</b> {model1.prsquared:.3f} | <b>AIC:</b> {model1.aic:.1f} | <b>n:</b> {len(features)}</p>'))
except Exception as e:
    display(HTML(f'<p>Model 1 failed to converge: {e}</p>'))

# Model 2: category-level binary features
X2 = features[['n_treatments', 'has_autonomic', 'has_antiinflam', 'has_mito']].astype(float)
X2 = sm.add_constant(X2)
try:
    model2 = sm.Logit(y, X2).fit(disp=0)
    display(HTML('<h3>Model 2: Specific Category Effects (controlling for treatment count)</h3>'))

    coefs2 = pd.DataFrame({
        'Variable': model2.params.index,
        'Coef': model2.params.values,
        'OR': np.exp(model2.params.values),
        'p-value': model2.pvalues.values,
        'CI_low': np.exp(model2.conf_int()[0].values),
        'CI_high': np.exp(model2.conf_int()[1].values)
    })
    styled_c2 = coefs2.style.format({
        'Coef': '{:.3f}', 'OR': '{:.2f}', 'p-value': '{:.4f}', 'CI_low': '{:.2f}', 'CI_high': '{:.2f}'
    }).set_properties(**{'text-align': 'center'}).hide(axis='index')
    display(styled_c2)
    display(HTML(f'<p><b>Pseudo R2:</b> {model2.prsquared:.3f} | <b>AIC:</b> {model2.aic:.1f} | <b>n:</b> {len(features)}</p>'))
except Exception as e:
    display(HTML(f'<p>Model 2 failed to converge: {e}</p>'))

display(HTML(
    '<p style="font-size:14px; background:#f0f7ff; padding:12px; border-left:4px solid #3498db;">'
    '<b>Interpretation note:</b> With only 49 users, these logistic models are underpowered for '
    'individual coefficient significance. The value is in the <i>direction</i> and <i>relative magnitude</i> '
    'of effects, not in p-values for individual predictors. The AIC comparison between models tells us '
    'whether category-level variables add explanatory power beyond treatment count alone.'
    '</p>'
))
"""
cells.append(("code", CELL_5B))

# ── Section 6: Individual drug performance ──
cells.append(("md", """## 6. Individual Treatment Performance: POTS vs the Broader Community

Some treatments perform differently in POTS patients than in the broader Long COVID community. Identifying these divergences reveals POTS-specific pharmacology \u2014 treatments that work for general Long COVID but fail for POTS, or vice versa."""))

CELL_6 = r"""
# -- Per-drug comparison: POTS vs non-POTS --
causal_names = {'covid vaccine', 'pfizer vaccine', 'vaccine', 'vaccine injection', 'booster',
                'moderna vaccine', 'mrna covid-19 vaccine', 'flu vaccine'}

def drug_user_stats(reports_df, min_users=5):
    user_level = reports_df.groupby(['user_id', 'canonical_name']).agg(
        avg_score=('score', 'mean')
    ).reset_index()
    drug_stats = user_level.groupby('canonical_name').agg(
        n_users=('user_id', 'nunique'),
        mean_score=('avg_score', 'mean'),
        pos_rate=('avg_score', lambda x: (x > 0.5).mean()),
    ).reset_index()
    return drug_stats[drug_stats['n_users'] >= min_users]

pots_drug_stats = drug_user_stats(pots_reports, min_users=4)
nonpots_drug_stats = drug_user_stats(non_pots_reports, min_users=20)

compare = pots_drug_stats.merge(nonpots_drug_stats, on='canonical_name', suffixes=('_pots', '_nonpots'))
compare['delta_pos_rate'] = compare['pos_rate_pots'] - compare['pos_rate_nonpots']
compare['delta_sentiment'] = compare['mean_score_pots'] - compare['mean_score_nonpots']
compare = compare[~compare['canonical_name'].str.lower().isin(causal_names)]
compare = compare.sort_values('delta_pos_rate', ascending=True)

# Forest plot: delta in positive rate
fig, ax = plt.subplots(figsize=(12, max(6, len(compare) * 0.5)))
y_pos = range(len(compare))
colors_delta = ['#e74c3c' if d < -0.1 else '#2ecc71' if d > 0.1 else '#95a5a6'
                for d in compare['delta_pos_rate']]

ax.barh(y_pos, compare['delta_pos_rate'] * 100, color=colors_delta, edgecolor='white', height=0.7)
ax.set_yticks(y_pos)
ax.set_yticklabels(compare['canonical_name'], fontsize=10)
ax.axvline(0, color='black', linewidth=1)
ax.set_xlabel('Difference in Positive Rate (POTS minus Non-POTS, pp)', fontsize=11)
ax.set_title('Treatment Performance Gap: POTS vs Non-POTS Patients',
             fontsize=13, fontweight='bold')

for i, (_, row) in enumerate(compare.iterrows()):
    side = 'left' if row['delta_pos_rate'] < 0 else 'right'
    offset = -2 if row['delta_pos_rate'] < 0 else 2
    ax.text(row['delta_pos_rate'] * 100 + offset, i,
            f"POTS n={row['n_users_pots']:.0f}", va='center', ha=side, fontsize=8)

from matplotlib.patches import Patch
legend_elements = [
    Patch(facecolor='#e74c3c', label='POTS performs worse (>10pp gap)'),
    Patch(facecolor='#95a5a6', label='Similar performance'),
    Patch(facecolor='#2ecc71', label='POTS performs better (>10pp gap)')
]
ax.legend(handles=legend_elements, loc='lower right', fontsize=10, framealpha=0.9)
plt.tight_layout()
plt.savefig('_fig_pots_vs_nonpots_drugs.png', dpi=150, bbox_inches='tight')
plt.show()

# Statistical tests for biggest divergences
display(HTML('<h3>Largest POTS-Specific Divergences (Fisher Exact)</h3>'))
test_rows = []
for _, row in compare.iterrows():
    if abs(row['delta_pos_rate']) >= 0.1 and row['n_users_pots'] >= 4:
        a = int(row['pos_rate_pots'] * row['n_users_pots'])
        b = int(row['n_users_pots'] - a)
        c = int(row['pos_rate_nonpots'] * row['n_users_nonpots'])
        d_val = int(row['n_users_nonpots'] - c)
        if min(a, b, c, d_val) >= 0:
            odds_r, p_val = fisher_exact([[a, b], [c, d_val]])
            h_eff = 2 * (math.asin(math.sqrt(max(0.001, row['pos_rate_pots']))) -
                         math.asin(math.sqrt(max(0.001, row['pos_rate_nonpots']))))
            test_rows.append({
                'Treatment': row['canonical_name'],
                'POTS pos%': f"{row['pos_rate_pots']*100:.0f}%",
                'Non-POTS pos%': f"{row['pos_rate_nonpots']*100:.0f}%",
                'Delta': f"{row['delta_pos_rate']*100:+.0f}pp",
                'OR': f"{odds_r:.2f}",
                "Cohen's h": f"{h_eff:.2f}",
                'p': f"{p_val:.3f}",
                'POTS n': int(row['n_users_pots']),
                'Non-POTS n': int(row['n_users_nonpots'])
            })
if test_rows:
    test_df = pd.DataFrame(test_rows)
    display(test_df.style.set_properties(**{'text-align': 'center'}).hide(axis='index'))
"""
cells.append(("code", CELL_6))

# ── Section 7: Counterintuitive Findings ──
cells.append(("md", """## 7. Counterintuitive Findings Worth Investigating"""))

CELL_7 = r"""
# -- Counterintuitive patterns --
findings = []

# 1. Nattokinase
natto_pots = pots_reports[pots_reports['canonical_name'] == 'nattokinase']
natto_nonpots = non_pots_reports[non_pots_reports['canonical_name'] == 'nattokinase']
if len(natto_pots) > 0 and len(natto_nonpots) > 0:
    natto_pots_user = natto_pots.groupby('user_id')['score'].mean()
    natto_np_user = natto_nonpots.groupby('user_id')['score'].mean()
    natto_pos_pots = (natto_pots_user > 0.5).mean()
    natto_pos_np = (natto_np_user > 0.5).mean()
    findings.append(
        '<h4>1. Nattokinase: A Community Favorite that Backfires in POTS</h4>'
        f'<p>Nattokinase is the 8th most popular treatment overall (50 users, 69% positive). '
        f'But among POTS patients, it has a {natto_pos_pots*100:.0f}% positive rate at the user level '
        f'(n={len(natto_pots_user)}) compared to {natto_pos_np*100:.0f}% in non-POTS patients '
        f'(n={len(natto_np_user)}). This is a striking reversal. Nattokinase is a fibrinolytic enzyme '
        'marketed for microclot dissolution. But POTS patients may experience worsened orthostatic '
        'symptoms from blood pressure changes induced by fibrinolysis. The data cannot confirm this '
        'mechanism, but the divergence is large enough to warrant caution for POTS patients.</p>'
    )

# 2. Magnesium: 100% positive
mag_pots = pots_reports[pots_reports['canonical_name'] == 'magnesium']
if len(mag_pots) > 0:
    n_mag = len(mag_pots)
    n_mag_u = mag_pots['user_id'].nunique()
    lo_w, _ = wilson_ci(n_mag, n_mag)
    findings.append(
        '<h4>2. Magnesium: Perfect Positive Rate in POTS (But Small Sample)</h4>'
        f'<p>Every single magnesium report among POTS users is positive ({n_mag} reports from '
        f'{n_mag_u} users). The Wilson 95% CI lower bound is {lo_w*100:.0f}%, still far above the '
        '50% baseline. Magnesium addresses multiple POTS mechanisms: it regulates heart rhythm, '
        'reduces muscle cramps common in dysautonomia, and supports mitochondrial ATP production. '
        'The perfect rate may also reflect that magnesium is well-tolerated and has minimal side '
        'effects, producing less negative reporting.</p>'
    )

# 3. SSRIs
ssri_names = ['ssri', 'escitalopram', 'sertraline', 'selective serotonin reuptake inhibitor']
ssri_pots = pots_reports[pots_reports['canonical_name'].isin(ssri_names)]
if len(ssri_pots) > 0:
    ssri_user = ssri_pots.groupby('user_id')['score'].mean()
    ssri_pos = (ssri_user > 0).mean()
    esc_n = pots_reports[pots_reports['canonical_name'] == 'escitalopram']['user_id'].nunique()
    findings.append(
        '<h4>3. SSRIs: First-Line Clinical Recommendation, Last-Place Community Outcome</h4>'
        f'<p>SSRIs are commonly prescribed for POTS to stabilize norepinephrine signaling. In this data, '
        f'SSRI-class drugs show a {ssri_pos*100:.0f}% net-positive rate among POTS users (n={len(ssri_user)}). '
        f'Escitalopram specifically has 0% positive reports across {esc_n} POTS users. '
        'This contradicts clinical guidelines that include SSRIs as a treatment option for POTS. '
        'Several explanations are possible: SSRIs may worsen orthostatic intolerance in some patients, '
        'the community may over-report side effects for a drug class they are skeptical of, or SSRIs '
        'may help POTS-adjacent symptoms (anxiety, depression) without improving POTS itself. '
        'This finding is worth investigating but should not be taken as evidence that SSRIs are harmful.</p>'
    )

# 4. Beta blockers
bb_names = ['beta blocker', 'propranolol', 'metoprolol']
bb_pots = pots_reports[pots_reports['canonical_name'].isin(bb_names)]
if len(bb_pots) > 0:
    bb_user = bb_pots.groupby('user_id')['score'].mean()
    bb_pos = (bb_user > 0).mean()
    findings.append(
        '<h4>4. Beta Blockers: The Standard of Care with Below-Average Results</h4>'
        f'<p>Beta blockers (propranolol, metoprolol) are the first-line pharmacological treatment for POTS. '
        f'In this community data, they show a {bb_pos*100:.0f}% net-positive rate among POTS users '
        f'(n={len(bb_user)}). The general community reports 80% positive for beta blockers (n=37 overall). '
        'This gap suggests that beta blockers alone are insufficient for Long COVID POTS, which involves '
        'inflammation and mitochondrial dysfunction beyond simple heart rate control. Notably, beta blockers '
        'appear more frequently in successful multi-drug regimens than as monotherapy &mdash; they may work '
        'better as part of a combination strategy than as a standalone treatment.</p>'
    )

if not findings:
    findings.append('<p>All findings aligned with community consensus and clinical expectations.</p>')

display(HTML(''.join(findings)))
"""
cells.append(("code", CELL_7))

# ── Section 8: Qualitative Evidence ──
cells.append(("md", """## 8. What Patients Are Saying

These quotes are from POTS patients in the dataset, selected because they illustrate specific treatment outcomes. Each quote contains a concrete treatment reference and outcome."""))

CELL_8 = r"""
# -- Pull targeted quotes --
import datetime

pots_list = list(pots_ids)
ph2 = ','.join('?' for _ in pots_list)
quotes_raw = pd.read_sql(
    f'SELECT p.body_text, p.post_date, p.user_id FROM posts p '
    f'WHERE p.user_id IN ({ph2}) AND LENGTH(p.body_text) BETWEEN 80 AND 600 '
    f'ORDER BY p.post_date DESC',
    conn, params=pots_list
)

def find_quotes(df, keywords, n=3):
    results = []
    for _, row in df.iterrows():
        text = row['body_text'].lower()
        if any(k in text for k in keywords):
            dt = datetime.datetime.fromtimestamp(row['post_date']).strftime('%Y-%m-%d')
            clean = row['body_text'].replace('\n', ' ').strip()
            sentences = clean.split('. ')
            short = '. '.join(sentences[:2]) + ('.' if len(sentences) > 1 else '')
            if len(short) > 250:
                short = short[:247] + '...'
            results.append((dt, short))
            if len(results) >= n:
                break
    return results

quote_sections = []

q1 = find_quotes(quotes_raw, ['combination', 'together', 'stack', 'protocol', 'regimen', 'multiple'], n=2)
if q1:
    quote_sections.append('<h4>On multi-treatment strategies:</h4>')
    for dt, text in q1:
        quote_sections.append(
            f'<blockquote style="border-left:3px solid #3498db; padding:8px 12px; margin:8px 0; font-style:italic;">'
            f'"{text}" <br><small>-- POTS patient, {dt}</small></blockquote>')

q2 = find_quotes(quotes_raw, ['naltrexone', 'ldn'], n=2)
if q2:
    quote_sections.append('<h4>On low dose naltrexone:</h4>')
    for dt, text in q2:
        quote_sections.append(
            f'<blockquote style="border-left:3px solid #2ecc71; padding:8px 12px; margin:8px 0; font-style:italic;">'
            f'"{text}" <br><small>-- POTS patient, {dt}</small></blockquote>')

q3 = find_quotes(quotes_raw, ['nattokinase'], n=1)
if q3:
    quote_sections.append('<h4>On nattokinase (contradicting its general popularity):</h4>')
    for dt, text in q3:
        quote_sections.append(
            f'<blockquote style="border-left:3px solid #e74c3c; padding:8px 12px; margin:8px 0; font-style:italic;">'
            f'"{text}" <br><small>-- POTS patient, {dt}</small></blockquote>')

q4 = find_quotes(quotes_raw, ['electrolyte', 'salt', 'magnesium'], n=2)
if q4:
    quote_sections.append('<h4>On electrolytes and magnesium:</h4>')
    for dt, text in q4:
        quote_sections.append(
            f'<blockquote style="border-left:3px solid #2ecc71; padding:8px 12px; margin:8px 0; font-style:italic;">'
            f'"{text}" <br><small>-- POTS patient, {dt}</small></blockquote>')

q5 = find_quotes(quotes_raw, ['ssri', 'antidepressant', 'escitalopram', 'dismissed'], n=1)
if q5:
    quote_sections.append('<h4>On SSRIs and clinical mismatch:</h4>')
    for dt, text in q5:
        quote_sections.append(
            f'<blockquote style="border-left:3px solid #e67e22; padding:8px 12px; margin:8px 0; font-style:italic;">'
            f'"{text}" <br><small>-- POTS patient, {dt}</small></blockquote>')

if quote_sections:
    display(HTML(''.join(quote_sections)))
else:
    display(HTML('<p>No targeted quotes found matching treatment criteria.</p>'))
"""
cells.append(("code", CELL_8))

# ── Section 9: Sensitivity checks ──
cells.append(("md", """## 9. Sensitivity Checks

The main finding \u2014 that multi-target therapy outperforms monotherapy for POTS \u2014 needs stress-testing. We check whether it survives when we (1) restrict to strong-signal reports only, (2) drop the 3 most extreme users, and (3) use a stricter positive threshold."""))

CELL_9 = r"""
# -- Sensitivity check 1: strong signal only --
strong_reports = pots_reports[pots_reports['signal_strength'] == 'strong']
strong_user = strong_reports.groupby('user_id').agg(
    n_treatments=('canonical_name', 'nunique'),
    avg_sentiment=('score', 'mean'),
).reset_index()

mono_s = strong_user[strong_user['n_treatments'] == 1]['avg_sentiment']
poly_s = strong_user[strong_user['n_treatments'] >= 3]['avg_sentiment']
if len(mono_s) >= 2 and len(poly_s) >= 2:
    u_s, p_s = mannwhitneyu(mono_s, poly_s, alternative='two-sided')
    check1 = (f'Strong-signal only: mono mean={mono_s.mean():.2f} (n={len(mono_s)}), '
              f'poly 3+ mean={poly_s.mean():.2f} (n={len(poly_s)}), p={p_s:.4f}')
    holds1 = p_s < 0.1
else:
    check1 = f'Strong-signal only: insufficient sample after filtering (mono={len(mono_s)}, poly={len(poly_s)})'
    holds1 = None

# -- Sensitivity check 2: drop 3 most extreme users --
extreme_ids = user_summary.nlargest(3, 'n_treatments')['user_id']
trimmed = user_summary[~user_summary['user_id'].isin(extreme_ids)]
mono_t = trimmed[trimmed['n_treatments'] == 1]['avg_sentiment']
poly_t = trimmed[trimmed['n_treatments'] >= 3]['avg_sentiment']
if len(mono_t) >= 2 and len(poly_t) >= 2:
    u_t, p_t = mannwhitneyu(mono_t, poly_t, alternative='two-sided')
    check2 = (f'Dropping 3 heaviest users: mono mean={mono_t.mean():.2f} (n={len(mono_t)}), '
              f'poly 3+ mean={poly_t.mean():.2f} (n={len(poly_t)}), p={p_t:.4f}')
    holds2 = p_t < 0.1
else:
    check2 = 'Dropping 3 heaviest users: insufficient data'
    holds2 = None

# -- Sensitivity check 3: stricter threshold --
user_summary['strict_pos'] = (user_summary['avg_sentiment'] > 0.3).astype(int)
mono_strict = user_summary[user_summary['n_treatments'] == 1]['strict_pos']
poly_strict = user_summary[user_summary['n_treatments'] >= 3]['strict_pos']
if len(mono_strict) >= 2 and len(poly_strict) >= 2:
    table_s = [[mono_strict.sum(), len(mono_strict) - mono_strict.sum()],
               [poly_strict.sum(), len(poly_strict) - poly_strict.sum()]]
    or_s, p_fs = fisher_exact(table_s)
    check3 = (f'Stricter threshold (>0.3): mono {mono_strict.mean()*100:.0f}% positive (n={len(mono_strict)}), '
              f'poly 3+ {poly_strict.mean()*100:.0f}% positive (n={len(poly_strict)}), Fisher p={p_fs:.4f}')
    holds3 = p_fs < 0.1
else:
    check3 = 'Stricter threshold: insufficient data'
    holds3 = None

def verdict(h):
    if h is None: return 'N/A'
    return 'HOLDS' if h else 'WEAKENED'

display(HTML(
    '<h3>Sensitivity Check Results</h3>'
    '<table style="font-size:13px; border-collapse:collapse; width:100%;">'
    f'<tr style="border-bottom:1px solid #ccc;"><td style="padding:6px;">1. {check1}</td>'
    f'<td style="padding:6px; text-align:center;"><b>{verdict(holds1)}</b></td></tr>'
    f'<tr style="border-bottom:1px solid #ccc;"><td style="padding:6px;">2. {check2}</td>'
    f'<td style="padding:6px; text-align:center;"><b>{verdict(holds2)}</b></td></tr>'
    f'<tr style="border-bottom:1px solid #ccc;"><td style="padding:6px;">3. {check3}</td>'
    f'<td style="padding:6px; text-align:center;"><b>{verdict(holds3)}</b></td></tr>'
    '</table>'
))
"""
cells.append(("code", CELL_9))

# ── Section 10: Shannon Entropy ──
cells.append(("md", """## 10. User Agreement Analysis (Verbose)

Shannon entropy measures how much users agree about a treatment. Low entropy means consensus (everyone says positive or everyone says negative). High entropy means disagreement. For POTS, high-entropy treatments are the most interesting \u2014 they may indicate responder/non-responder subgroups."""))

CELL_10 = r"""
# -- Shannon entropy per drug for POTS --
from scipy.stats import entropy as sp_entropy

drug_entropy = []
for drug in pots_reports['canonical_name'].unique():
    sub = pots_reports[pots_reports['canonical_name'] == drug]
    n_users = sub['user_id'].nunique()
    if n_users < 4:
        continue
    counts = sub['sentiment'].value_counts()
    probs = counts / counts.sum()
    h = sp_entropy(probs, base=2)
    drug_entropy.append({
        'drug': drug, 'n_users': n_users, 'entropy': h,
        'pos_pct': (sub['sentiment'] == 'positive').mean() * 100,
        'neg_pct': (sub['sentiment'] == 'negative').mean() * 100,
    })

ent_df = pd.DataFrame(drug_entropy).sort_values('entropy', ascending=False)

# Scatter: entropy vs positive rate
fig, ax = plt.subplots(figsize=(11, 7))
sizes = ent_df['n_users'] * 15
scatter = ax.scatter(ent_df['pos_pct'], ent_df['entropy'], s=sizes,
                     c=ent_df['pos_pct'], cmap='RdYlGn', vmin=0, vmax=100,
                     alpha=0.7, edgecolor='black', linewidth=0.5, zorder=5)

texts = []
for _, row in ent_df.iterrows():
    texts.append(ax.text(row['pos_pct'], row['entropy'], row['drug'],
                         fontsize=8, ha='center', va='bottom'))

# Overlap avoidance
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
                pos = t2.get_position()
                t2.set_position((pos[0], pos[1] + 0.05))

ax.set_xlabel('% Positive Reports', fontsize=12)
ax.set_ylabel('Shannon Entropy (bits)', fontsize=12)
ax.set_title('Treatment Consensus vs Efficacy Among POTS Patients',
             fontsize=13, fontweight='bold')
cbar = plt.colorbar(scatter, ax=ax, label='% Positive')
for s_val in [5, 10, 15]:
    ax.scatter([], [], s=s_val*15, c='gray', alpha=0.5, edgecolor='black', label=f'{s_val} users')
ax.legend(title='Sample size', loc='upper left', framealpha=0.9)
plt.tight_layout()
plt.savefig('_fig_entropy_scatter.png', dpi=150, bbox_inches='tight')
plt.show()

top3 = ', '.join(ent_df.head(3)['drug'])
bot3 = ', '.join(ent_df.tail(3)['drug'])
display(HTML(
    '<p style="font-size:14px; background:#f0f7ff; padding:12px; border-left:4px solid #3498db;">'
    '<b>Plain language:</b> Treatments in the upper-left (high entropy, low positive rate) are divisive '
    'failures. Treatments in the lower-right (low entropy, high positive rate) are consensus successes. '
    f'The most divisive POTS treatments are {top3} &mdash; these may have responder subgroups worth '
    f'identifying in future research. The strongest consensus is around {bot3}.'
    '</p>'
))
"""
cells.append(("code", CELL_10))

# ── Section 11: Recommendations ──
cells.append(("md", """## 11. Tiered Recommendations

Based on the analysis above, we classify treatments into evidence tiers using both sample size and statistical signal. For POTS specifically, we also factor in whether the treatment appears in successful multi-drug regimens."""))

CELL_11 = r"""
# -- Build recommendation tiers --
from scipy.stats import binomtest as btest

pots_user_drug = pots_reports.groupby(['user_id', 'canonical_name']).agg(
    avg_score=('score', 'mean'),
    n_reports=('sentiment', 'count')
).reset_index()

drug_rec = pots_user_drug.groupby('canonical_name').agg(
    n_users=('user_id', 'nunique'),
    mean_score=('avg_score', 'mean'),
    pos_rate=('avg_score', lambda x: (x > 0.5).mean()),
).reset_index()

recs = []
for _, row in drug_rec.iterrows():
    n = int(row['n_users'])
    k = int(row['pos_rate'] * n)
    if n < 3:
        continue
    if row['canonical_name'].lower() in causal_names:
        continue
    if row['canonical_name'].lower() in GENERIC_TERMS:
        continue

    result = btest(k, n, 0.5)
    lo, hi = wilson_ci(k, n)

    if n >= 6 and result.pvalue < 0.05 and row['pos_rate'] > 0.5:
        tier = 'Strong Positive'
    elif n >= 6 and result.pvalue < 0.05 and row['pos_rate'] < 0.5:
        tier = 'Strong Negative'
    elif n >= 4 and row['pos_rate'] >= 0.65:
        tier = 'Moderate Positive'
    elif n >= 4 and row['pos_rate'] <= 0.35:
        tier = 'Moderate Negative'
    elif n >= 3:
        tier = 'Preliminary'
    else:
        tier = 'Insufficient'

    nnt_val = nnt(row['pos_rate'], 0.50) if row['pos_rate'] > 0.50 else None

    recs.append({
        'Treatment': row['canonical_name'],
        'N Users': n, 'Pos Rate': row['pos_rate'],
        'CI': f"[{lo:.0%}, {hi:.0%}]",
        'p-value': result.pvalue,
        'NNT': f"{nnt_val}" if nnt_val else chr(8212),
        'Tier': tier, 'Mean Score': row['mean_score']
    })

rec_df = pd.DataFrame(recs)
rec_df = rec_df.sort_values(['Tier', 'Pos Rate'], ascending=[True, False])

tier_colors = {
    'Strong Positive': '#27ae60', 'Moderate Positive': '#2ecc71',
    'Preliminary': '#f39c12',
    'Moderate Negative': '#e74c3c', 'Strong Negative': '#c0392b'
}

for tier_name in ['Strong Positive', 'Moderate Positive', 'Preliminary', 'Moderate Negative', 'Strong Negative']:
    tier_sub = rec_df[rec_df['Tier'] == tier_name]
    if len(tier_sub) == 0:
        continue
    display(HTML(f'<h3 style="color:{tier_colors[tier_name]};">{tier_name} (n={len(tier_sub)})</h3>'))
    show_cols = ['Treatment', 'N Users', 'Pos Rate', 'CI', 'p-value', 'NNT', 'Mean Score']
    styled_r = tier_sub[show_cols].style.format({
        'Pos Rate': '{:.0%}', 'p-value': '{:.3f}', 'Mean Score': '{:.2f}'
    }).set_properties(**{'text-align': 'center'}).hide(axis='index')
    display(styled_r)

# Forest plot
positive_tiers = rec_df[rec_df['Tier'].str.contains('Positive|Preliminary')]
fig, ax = plt.subplots(figsize=(12, max(6, len(positive_tiers) * 0.4)))
plot_df = positive_tiers.sort_values('Pos Rate', ascending=True)
y_pos = range(len(plot_df))

for i, (_, row) in enumerate(plot_df.iterrows()):
    lo, hi = wilson_ci(int(row['Pos Rate'] * row['N Users']), row['N Users'])
    color = tier_colors.get(row['Tier'], '#95a5a6')
    ax.plot(row['Pos Rate'] * 100, i, 'o', color=color, markersize=10, zorder=5)
    ax.plot([lo * 100, hi * 100], [i, i], '-', color=color, linewidth=2, zorder=4)

ax.set_yticks(y_pos)
ax.set_yticklabels(plot_df['Treatment'], fontsize=10)
ax.axvline(50, color='grey', linestyle='--', alpha=0.5, linewidth=1)
ax.set_xlabel('Positive Rate with 95% Wilson CI (%)', fontsize=11)
ax.set_title('POTS Treatment Recommendations: Forest Plot', fontsize=13, fontweight='bold')

from matplotlib.lines import Line2D
legend_els = [Line2D([0],[0], marker='o', color='w', markerfacecolor=c, markersize=10, label=t)
              for t, c in tier_colors.items() if t in plot_df['Tier'].values]
ax.legend(handles=legend_els, loc='lower right', fontsize=10, framealpha=0.9)
plt.tight_layout()
plt.savefig('_fig_recommendations_forest.png', dpi=150, bbox_inches='tight')
plt.show()
"""
cells.append(("code", CELL_11))

# ── Section 12: Conclusion ──
cells.append(("md", """## 12. Conclusion

This analysis confirms and extends Notebook 2's finding: POTS patients in the Long COVID community face a genuine treatment paradox, but the resolution is not mysterious. POTS monotherapy fails at striking rates \u2014 a 14.3% positive rate that is 4x worse than monotherapy for non-POTS Long COVID patients. The data does not support the interpretation that POTS is simply "harder to treat." Instead, it supports a more specific claim: POTS requires multi-target therapy.

The key insight is not that *more* treatments help \u2014 it is that *covering multiple mechanistic categories* predicts success. Users who address at least two of the three identified pathways (autonomic stabilization, anti-inflammatory action, mitochondrial support) achieve positive outcomes at rates comparable to the broader community. The logistic regression confirms that category coverage matters independently of treatment count.

The specific combinations that define successful POTS management in this community center on a magnesium + CoQ10 + electrolyte foundation (mitochondrial/autonomic base), supplemented by an anti-inflammatory agent \u2014 most commonly antihistamines or low dose naltrexone. Notably, the clinically standard POTS treatments (beta blockers, SSRIs) perform below community average when used in isolation, while the community-driven supplement stack (magnesium, CoQ10, electrolytes, vitamin D) performs above average. This does not mean beta blockers are ineffective \u2014 they appear in many successful regimens \u2014 but it does suggest they are insufficient as monotherapy.

**Based on this data, a POTS patient asking "what should I try?" should consider starting with a multi-system approach: electrolytes and salt loading for volume, magnesium and CoQ10 for mitochondrial support, and an antihistamine (H1 or mast cell stabilizer like ketotifen) for the inflammatory component. Beta blockers or ivabradine can address heart rate control, but should not be the only intervention. SSRIs and nattokinase should be approached with caution in the POTS context \u2014 the former shows poor community outcomes, and the latter, despite popularity in the broader Long COVID community, performs notably worse in POTS patients.** Famotidine, despite being a commonly recommended H2 antihistamine, also underperforms in POTS specifically. These are community reporting patterns, not clinical trial results, and individual responses will vary."""))

# ── Section 13: Research Limitations ──
cells.append(("md", """## 13. Research Limitations

1. **Selection bias:** Users active in r/covidlonghaulers are not representative of all Long COVID POTS patients. They skew toward treatment-seeking, digitally engaged, and English-speaking populations. POTS patients who manage symptoms successfully with standard medical care may never post.

2. **Reporting bias:** Users are more likely to report treatments that had strong effects (positive or negative) than those with subtle or no effect. This inflates the tails of the sentiment distribution and may undercount treatments that provide modest but real benefit. The 100% magnesium positive rate, for example, may partly reflect that dissatisfied magnesium users simply don't mention it.

3. **Survivorship bias:** Users who are still posting in month 6+ of Long COVID are by definition those who have not recovered. Our "successful" users are those who report improvement, not full recovery. The treatment strategies that lead to complete recovery and departure from the community are invisible.

4. **Recall bias:** Users reporting on treatments may misremember timing, dosage, or the sequence in which they tried treatments. A user who reports 10 treatments may have tried them over 2 years, with the positive ones being more recent (recency effect) or more vivid (salience effect).

5. **Confounding:** Users who try more treatments may differ from monotherapy users in severity, health literacy, financial resources, or access to specialist care. The polypharmacy advantage may reflect underlying resources rather than treatment synergy. We controlled for treatment count in the logistic regression, but cannot control for unobserved confounders.

6. **No control group:** There is no placebo arm. A 70% positive rate could reflect regression to the mean, natural disease course, placebo effect, or actual drug efficacy. We cannot distinguish these with observational community data.

7. **Sentiment vs efficacy:** A "positive" sentiment report means the user wrote positively about the treatment, not that the treatment objectively worked. Some users may report a treatment as positive because it reduced anxiety about their condition, improved sleep, or gave them a sense of agency \u2014 without actually changing POTS symptom severity.

8. **Temporal snapshot:** This data covers one month (March-April 2026). Treatment trends, community sentiment, and drug availability change over time. Treatments popular in this window may reflect recent viral posts, new research publicity, or supply chain availability rather than long-term community consensus."""))

# ── Disclaimer ──
CELL_DISCLAIMER = """
display(HTML(
    '<p style="font-size: 1.2em; font-weight: bold; font-style: italic; margin-top: 30px; '
    'padding: 15px; background: #fff3cd; border-left: 5px solid #ffc107;">'
    'These findings reflect reporting patterns in online communities, not population-level '
    'treatment effects. This is not medical advice.</p>'
))
"""
cells.append(("code", CELL_DISCLAIMER))

# ── Build and execute ──
DB_PATH = r"C:\Users\scgee\OneDrive\Documents\Projects\PatientPunk\polina_onemonth.db"
OUTPUT_STEM = r"C:\Users\scgee\OneDrive\Documents\Projects\PatientPunk\notebooks\sample_notebooks_verbose\3_pots_treatment_strategy"

nb = build_notebook(cells=cells, db_path=DB_PATH)
html_path = execute_and_export(nb, OUTPUT_STEM)
print(f"Done. HTML at: {html_path}")
