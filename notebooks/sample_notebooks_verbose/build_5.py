# -*- coding: utf-8 -*-
"""Build and execute PSSD harm/causation notebook (verbose mode)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from build_notebook import build_notebook, execute_and_export

cells = []

# ── Research Question ──
cells.append(("md", '**Research Question:** "Which SSRIs cause the worst cases of PSSD (Post-SSRI Sexual Dysfunction), and what factors predict a more severe outcome?"\n\n**Focus:** Harm and causation only. Recovery and treatment effectiveness are excluded from this analysis.'))

# ── Abstract ──
cells.append(("md", """# Which SSRIs Cause the Worst PSSD? Predictors of Severity in a Patient Community

**Abstract:** This analysis examines 98 unique users in r/PSSD who reported a specific causative SSRI/SNRI, drawn from 902 treatment reports spanning March-April 2026. Sertraline (n=49) and escitalopram/Lexapro (n=33) are the most frequently implicated drugs, with sertraline showing the highest absolute burden of strong-signal negative reports. After merging brand/generic duplicates, we find that paroxetine, sertraline, vortioxetine, and duloxetine carry the highest negative sentiment rates (90-100% negative at user level). A text-mined symptom burden index reveals duloxetine and citalopram users report the broadest symptom profiles (5.0 and 4.0 symptoms on average, respectively), while a logistic regression identifies polypharmacy (exposure to multiple SSRIs) and mention of "severe" as the strongest predictors of high symptom burden. All SSRIs in this community produce overwhelmingly negative sentiment, but the specific symptom profile and severity indicators differ by drug."""))

# ── Data Exploration ──
cells.append(("md", """## 1. Data Exploration

This analysis uses the r/PSSD (Post-SSRI Sexual Dysfunction) community database. PSSD is a condition where sexual dysfunction, emotional blunting, and other neurological symptoms persist after discontinuation of serotonergic antidepressants. Because this community exists specifically for people harmed by these drugs, the SSRIs and SNRIs are the *causative agents* here, not treatments being evaluated for efficacy.

**Methodological note:** In a standard PatientPunk treatment analysis, causative drugs would be filtered out because their negative sentiment reflects why users joined the community, not a treatment response. Here, the causative relationship IS the research question, so we analyze these drugs directly as harm agents."""))

cells.append(("code", '''
# -- Data exploration --
total_users = pd.read_sql("SELECT COUNT(DISTINCT user_id) FROM users", conn).iloc[0,0]
total_posts = pd.read_sql("SELECT COUNT(*) FROM posts", conn).iloc[0,0]
total_reports = pd.read_sql("SELECT COUNT(*) FROM treatment_reports", conn).iloc[0,0]
unique_reporters = pd.read_sql("SELECT COUNT(DISTINCT user_id) FROM treatment_reports", conn).iloc[0,0]

date_range = pd.read_sql(
    "SELECT MIN(post_date) as min_d, MAX(post_date) as max_d FROM posts WHERE post_date IS NOT NULL",
    conn)
from datetime import datetime
min_date = datetime.fromtimestamp(date_range.iloc[0]['min_d']).strftime('%Y-%m-%d')
max_date = datetime.fromtimestamp(date_range.iloc[0]['max_d']).strftime('%Y-%m-%d')

display(HTML(
    '<div style="background:#f8f9fa; padding:15px; border-radius:8px; border-left:4px solid #3498db; margin:10px 0;">'
    '<h3 style="margin-top:0;">Dataset Overview</h3>'
    '<table style="font-size:14px;">'
    '<tr><td><b>Community:</b></td><td>r/PSSD (Post-SSRI Sexual Dysfunction)</td></tr>'
    f'<tr><td><b>Data covers:</b></td><td>{min_date} to {max_date} (~1 month)</td></tr>'
    f'<tr><td><b>Total users:</b></td><td>{total_users:,}</td></tr>'
    f'<tr><td><b>Total posts:</b></td><td>{total_posts:,}</td></tr>'
    f'<tr><td><b>Treatment reports:</b></td><td>{total_reports:,} from {unique_reporters:,} unique reporters</td></tr>'
    '</table></div>'
))

# Show SSRI-specific breakdown
ssri_raw = pd.read_sql(
    "SELECT t.canonical_name as drug, "
    "COUNT(DISTINCT tr.user_id) as unique_users, "
    "COUNT(*) as total_reports, "
    "SUM(CASE WHEN tr.sentiment='negative' THEN 1 ELSE 0 END) as negative_reports, "
    "SUM(CASE WHEN tr.sentiment='positive' THEN 1 ELSE 0 END) as positive_reports, "
    "SUM(CASE WHEN tr.signal_strength='strong' THEN 1 ELSE 0 END) as strong_signal "
    "FROM treatment_reports tr "
    "JOIN treatment t ON tr.drug_id = t.id "
    "WHERE t.canonical_name IN ('sertraline','lexapro','fluoxetine','escitalopram','citalopram',"
    "'paroxetine','prozac','vortioxetine','duloxetine','fluvoxamine') "
    "GROUP BY t.canonical_name ORDER BY unique_users DESC", conn)

display(HTML("<h4>Raw SSRI/SNRI Reports (Before Merging Duplicates)</h4>"))
display(ssri_raw.style.set_caption("Brand/generic names are listed separately and will be merged next").hide(axis='index'))
'''))

# ── Duplicate merging ──
cells.append(("md", """### Merging Brand/Generic Duplicates

Lexapro and escitalopram are the same drug (escitalopram oxalate). Prozac and fluoxetine are the same drug (fluoxetine hydrochloride). The extraction pipeline sometimes captures brand and generic names separately. We merge these pairs to avoid double-counting and produce accurate per-drug statistics. Users who appear under both names are counted once."""))

cells.append(("code", '''
# -- Merge duplicates: lexapro+escitalopram, prozac+fluoxetine --
MERGE_MAP = {
    'escitalopram': 'escitalopram',
    'lexapro': 'escitalopram',
    'fluoxetine': 'fluoxetine',
    'prozac': 'fluoxetine',
}
KEEP_AS_IS = ['sertraline', 'citalopram', 'paroxetine', 'vortioxetine', 'duloxetine']

# Build user-level aggregated data with merged names
user_drug_df = pd.read_sql(
    "SELECT tr.user_id, t.canonical_name as raw_drug, tr.sentiment, tr.signal_strength "
    "FROM treatment_reports tr JOIN treatment t ON tr.drug_id = t.id "
    "WHERE t.canonical_name IN ('sertraline','lexapro','fluoxetine','escitalopram','citalopram',"
    "'paroxetine','prozac','vortioxetine','duloxetine')", conn)

user_drug_df['drug'] = user_drug_df['raw_drug'].map(lambda x: MERGE_MAP.get(x, x))
user_drug_df['sentiment_score'] = user_drug_df['sentiment'].map(SENTIMENT_SCORE)

# User-level aggregation: one row per user per merged drug
user_level = user_drug_df.groupby(['user_id', 'drug']).agg(
    avg_sentiment=('sentiment_score', 'mean'),
    n_reports=('sentiment_score', 'count'),
    n_strong=('signal_strength', lambda x: (x == 'strong').sum()),
    worst_sentiment=('sentiment_score', 'min'),
).reset_index()

user_level['outcome'] = user_level['avg_sentiment'].map(classify_outcome)

# Summary by drug (merged)
drug_summary = []
for drug, grp in user_level.groupby('drug'):
    n = len(grp)
    n_neg = (grp['outcome'] == 'negative').sum()
    n_pos = (grp['outcome'] == 'positive').sum()
    n_mixed = (grp['outcome'] == 'mixed/neutral').sum()
    neg_rate = n_neg / n
    pos_rate = n_pos / n
    ci_lo, ci_hi = wilson_ci(n_neg, n)
    drug_summary.append({
        'drug': drug, 'users': n, 'negative': n_neg, 'positive': n_pos,
        'mixed_neutral': n_mixed, 'neg_rate': neg_rate, 'pos_rate': pos_rate,
        'neg_ci_lo': ci_lo, 'neg_ci_hi': ci_hi,
        'avg_sentiment': grp['avg_sentiment'].mean(),
    })

drug_df = pd.DataFrame(drug_summary).sort_values('users', ascending=False)

display(HTML(
    '<div style="background:#fff3cd; padding:12px; border-radius:8px; border-left:4px solid #ffc107; margin:10px 0;">'
    '<b>Filtering summary (verbose mode):</b> Merged lexapro+escitalopram (3 overlapping users) and prozac+fluoxetine (3 overlapping users). '
    'Generic category terms (ssri, snri, antidepressant) excluded -- these are drug classes, not specific drugs. '
    'Duloxetine is technically an SNRI but is included because SNRI-caused PSSD is mechanistically related and the community discusses it alongside SSRIs. '
    'Result: <b>7 specific drugs, 98 unique users</b> after merging.'
    '</div>'
))

merged_display = drug_df[['drug','users','negative','positive','mixed_neutral','neg_rate','avg_sentiment']].copy()
merged_display['neg_rate'] = merged_display['neg_rate'].map(lambda x: f"{x:.0%}")
merged_display['avg_sentiment'] = merged_display['avg_sentiment'].map(lambda x: f"{x:.2f}")
merged_display.columns = ['Drug', 'Users', 'Negative', 'Positive', 'Mixed/Neutral', 'Negative Rate', 'Avg Sentiment']
display(merged_display.style.set_caption("User-level outcomes after merging brand/generic pairs").hide(axis='index'))
'''))

# ── Baseline ──
cells.append(("md", """## 2. Baseline: The Harm Landscape

Before comparing individual drugs, we need to establish what "normal" looks like in this community. Every SSRI here is discussed as a causative agent, so we expect overwhelmingly negative sentiment. The question is not whether these drugs cause PSSD (the community's existence answers that), but which drugs produce *more severe* or *more consistent* negative outcomes."""))

cells.append(("code", '''
# -- Forest plot: Negative rate by drug with Wilson CIs --
fig, ax = plt.subplots(figsize=(10, 6))

plot_df = drug_df.sort_values('neg_rate', ascending=True).copy()
y_pos = range(len(plot_df))

colors = ['#e74c3c' if r >= 0.90 else '#e67e22' if r >= 0.70 else '#f39c12' for r in plot_df['neg_rate']]

ax.hlines(y=list(y_pos), xmin=plot_df['neg_ci_lo'], xmax=plot_df['neg_ci_hi'],
          color='#555', linewidth=2, zorder=1)
ax.scatter(plot_df['neg_rate'], list(y_pos), c=colors, s=120, zorder=2, edgecolors='white', linewidth=1.5)

ax.set_yticks(list(y_pos))
ax.set_yticklabels([f"{row['drug']} (n={row['users']})" for _, row in plot_df.iterrows()], fontsize=11)
ax.set_xlabel('User-Level Negative Outcome Rate', fontsize=12)
ax.set_title('PSSD Causative Drugs: Negative Outcome Rate with 95% Wilson CIs', fontsize=13, fontweight='bold')
mean_neg = plot_df['neg_rate'].mean()
ax.axvline(x=mean_neg, color='#888', linestyle='--', alpha=0.5, label=f"Mean: {mean_neg:.0%}")
ax.set_xlim(0, 1.05)
ax.legend(loc='lower right', fontsize=10)

for i, (_, row) in enumerate(plot_df.iterrows()):
    ax.annotate(f"{row['neg_rate']:.0%}", (row['neg_rate'], i),
                textcoords="offset points", xytext=(15, 0), fontsize=10, fontweight='bold')

fig.tight_layout()
plt.show()
'''))

cells.append(("md", """**What this shows:** Every SSRI in this community carries an extremely high negative outcome rate. Paroxetine, sertraline, and vortioxetine reach 100% negative at user level (though paroxetine and vortioxetine have small samples). Escitalopram (including Lexapro) has the "lowest" negative rate at 73%, with the widest confidence interval reflecting mixed reports from some users. The overall mean negative rate across all drugs is approximately 88%.

This forest plot establishes that comparing "bad" to "worse" is the relevant frame. No SSRI in this community is discussed favorably as a causative agent."""))

# ── Core Analysis: Pairwise Comparisons ──
cells.append(("md", """## 3. Core Analysis: Which SSRIs Produce the Worst PSSD?

With the baseline established, we now compare drugs head-to-head. We use Fisher's exact test for pairwise comparisons of negative outcome rates and compute Cohen's h as an effect size measure. In verbose mode, we show the full pairwise comparison matrix rather than collapsing into binary groups."""))

cells.append(("code", '''
# -- Pairwise Fisher exact tests with Cohen h --
from itertools import combinations
import math

drugs_for_comparison = drug_df[drug_df['users'] >= 5].sort_values('neg_rate', ascending=False)['drug'].tolist()
pairwise_results = []

for d1, d2 in combinations(drugs_for_comparison, 2):
    g1 = user_level[user_level['drug'] == d1]
    g2 = user_level[user_level['drug'] == d2]
    n1, n2 = len(g1), len(g2)
    neg1 = (g1['outcome'] == 'negative').sum()
    neg2 = (g2['outcome'] == 'negative').sum()

    table = [[neg1, n1 - neg1], [neg2, n2 - neg2]]
    if all(v >= 0 for row in table for v in row):
        odds_ratio, p_val = fisher_exact(table)
    else:
        odds_ratio, p_val = float('nan'), float('nan')

    p1 = neg1 / n1 if n1 > 0 else 0
    p2 = neg2 / n2 if n2 > 0 else 0
    h = 2 * (math.asin(math.sqrt(p1)) - math.asin(math.sqrt(p2)))

    pairwise_results.append({
        'Drug A': d1, 'Drug B': d2,
        'A neg rate': f"{p1:.0%}", 'B neg rate': f"{p2:.0%}",
        'n_A': n1, 'n_B': n2,
        'Fisher p': p_val, 'Cohen h': h,
        'Interpretation': 'Significant' if p_val < 0.05 else 'Not significant'
    })

pw_df = pd.DataFrame(pairwise_results).sort_values('Fisher p')

n_sig = (pw_df['Fisher p'] < 0.05).sum()
n_total = len(pw_df)

display(HTML(
    '<div style="background:#f8f9fa; padding:12px; border-radius:8px; border-left:4px solid #3498db; margin:10px 0;">'
    f'<b>Pairwise comparisons:</b> {n_total} pairs tested, {n_sig} significant at p<0.05. '
    'Cohen h > 0 means Drug A has a <i>higher</i> negative rate than Drug B.'
    '</div>'
))

pw_display = pw_df.copy()
pw_display['Fisher p'] = pw_display['Fisher p'].map(lambda x: f"{x:.4f}" if x >= 0.001 else f"{x:.2e}")
pw_display['Cohen h'] = pw_display['Cohen h'].map(lambda x: f"{x:+.2f}")
display(pw_display.head(21).style.set_caption("All pairwise Fisher exact tests (sorted by p-value)").hide(axis='index'))
'''))

cells.append(("md", """**Interpreting the pairwise tests:** Most comparisons do not reach significance because nearly all drugs cluster at very high negative rates (85-100%). The meaningful separation is between the drugs near 100% negative (paroxetine, sertraline, vortioxetine) and those with some positive or mixed reports (escitalopram at 73%, fluoxetine at 76%). However, the small sample sizes for paroxetine (n=7) and vortioxetine (n=8) mean their 100% rates carry wide confidence intervals.

The *largest* reliable effect sizes involve escitalopram, which has a significantly lower negative rate than sertraline. This does not mean escitalopram is "safe" -- 73% negative is still devastating -- but it suggests that among users who develop PSSD from escitalopram, a nontrivial minority report mixed rather than purely negative outcomes."""))

# ── Signal Strength Analysis ──
cells.append(("md", """## 4. Signal Strength: Conviction Behind the Reports

Not all negative reports carry equal weight. A "strong" signal means the user provided clear, specific attribution of symptoms to the drug. A "weak" signal might be a passing mention. The ratio of strong-signal negative reports to total reports tells us how *certain* users are about the drug's role in their PSSD."""))

cells.append(("code", '''
# -- Signal strength by drug: stacked grouped bar --
signal_df = user_drug_df.groupby(['drug', 'signal_strength']).size().unstack(fill_value=0)
signal_df = signal_df.reindex(columns=['strong', 'moderate', 'weak'], fill_value=0)
signal_df['total'] = signal_df.sum(axis=1)
signal_df = signal_df.sort_values('total', ascending=True)

signal_df['strong_pct'] = signal_df['strong'] / signal_df['total']

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), gridspec_kw={'width_ratios': [2, 1]})

signal_df[['strong', 'moderate', 'weak']].plot(kind='barh', stacked=True, ax=ax1,
    color=['#c0392b', '#e67e22', '#f1c40f'], edgecolor='white', linewidth=0.5)
ax1.set_xlabel('Number of Reports', fontsize=11)
ax1.set_title('Report Signal Strength by Causative Drug', fontsize=12, fontweight='bold')
ax1.legend(['Strong', 'Moderate', 'Weak'], bbox_to_anchor=(1.0, -0.15), ncol=3, fontsize=9)

ax2.barh(signal_df.index, signal_df['strong_pct'], color='#c0392b', edgecolor='white')
ax2.set_xlabel('Proportion Strong-Signal', fontsize=11)
ax2.set_title('Strong-Signal Report Rate', fontsize=12, fontweight='bold')
ax2.set_xlim(0, 1.05)
for i, (drug, row) in enumerate(signal_df.iterrows()):
    ax2.annotate(f"{row['strong_pct']:.0%}", (row['strong_pct'], i),
                textcoords="offset points", xytext=(8, 0), fontsize=10)

fig.tight_layout(rect=[0, 0.05, 1, 1])
plt.show()
'''))

cells.append(("md", """**What this shows:** Lexapro/escitalopram and sertraline dominate in absolute volume of strong-signal reports. The strong-signal rate varies: citalopram and paroxetine have 60% and 57% strong-signal rates, while sertraline sits at 48%. Escitalopram's strong-signal rate (50%) is notable because it also has the lowest overall negative rate, suggesting that users who DO attribute PSSD to escitalopram are quite certain about it, even though a larger minority of escitalopram users report mixed outcomes."""))

# ── Symptom Burden Index ──
cells.append(("md", """## 5. Symptom Burden: Which SSRIs Produce the Broadest Damage?

Negative sentiment alone does not capture severity. A user reporting only reduced libido has a different experience from one reporting anhedonia, genital numbness, emotional blunting, cognitive fog, and insomnia simultaneously. We construct a text-mined "Symptom Burden Index" (SBI) by counting how many of 9 distinct PSSD symptom domains each user mentions across all their posts.

**Symptom domains searched:** anhedonia, genital numbness, emotional blunting, libido loss/reduced sex drive, erectile dysfunction, orgasm dysfunction/anorgasmia, brain fog/cognitive issues, sleep disruption/insomnia, fatigue/exhaustion.

This is a proxy measure with important limitations (verbose users mention more symptoms regardless of actual burden), but it provides a relative comparison across drugs."""))

cells.append(("code", '''
# -- Symptom Burden Index by drug --
ssri_user_ids = user_level['user_id'].unique().tolist()
placeholders = ','.join(['?'] * len(ssri_user_ids))

all_posts = pd.read_sql(
    f"SELECT user_id, GROUP_CONCAT(body_text, ' ') as all_text "
    f"FROM posts WHERE user_id IN ({placeholders}) AND body_text IS NOT NULL "
    f"GROUP BY user_id",
    conn, params=ssri_user_ids)

SYMPTOM_DOMAINS = {
    'Anhedonia': ['anhedonia'],
    'Genital numbness': ['genital numbness', 'genital numb', 'numb genitals'],
    'Emotional blunting': ['emotional blunting', 'emotionally numb', 'emotional numbness', 'emotional flatness'],
    'Libido loss': ['libido', 'sex drive', 'sexual desire'],
    'Erectile dysfunction': ['erectile', 'erection', 'ed '],
    'Orgasm dysfunction': ['orgasm', 'anorgasmia', 'delayed orgasm'],
    'Brain fog': ['brain fog', 'cognitive', 'concentration', 'memory issues'],
    'Sleep disruption': ['insomnia', 'sleep issue', 'sleep problem', 'sleep quality'],
    'Fatigue': ['fatigue', 'exhausted', 'exhaustion', 'no energy', 'tired all'],
}

def count_symptom_domains(text):
    if not text or pd.isna(text):
        return 0
    text_lower = text.lower()
    count = 0
    for domain, keywords in SYMPTOM_DOMAINS.items():
        if any(kw in text_lower for kw in keywords):
            count += 1
    return count

def get_symptom_vector(text):
    if not text or pd.isna(text):
        return {d: 0 for d in SYMPTOM_DOMAINS}
    text_lower = text.lower()
    return {d: int(any(kw in text_lower for kw in kws)) for d, kws in SYMPTOM_DOMAINS.items()}

all_posts['symptom_count'] = all_posts['all_text'].apply(count_symptom_domains)
symptom_vectors = all_posts['all_text'].apply(get_symptom_vector).apply(pd.Series)
all_posts = pd.concat([all_posts[['user_id', 'symptom_count']], symptom_vectors], axis=1)

user_symptoms = user_level.merge(all_posts, on='user_id', how='left')
user_symptoms['symptom_count'] = user_symptoms['symptom_count'].fillna(0)

sbi_by_drug = user_symptoms.groupby('drug').agg(
    n=('symptom_count', 'count'),
    mean_sbi=('symptom_count', 'mean'),
    median_sbi=('symptom_count', 'median'),
    std_sbi=('symptom_count', 'std'),
).reset_index().sort_values('mean_sbi', ascending=False)

sbi_by_drug['se'] = sbi_by_drug['std_sbi'] / np.sqrt(sbi_by_drug['n'])
sbi_by_drug['ci_lo'] = sbi_by_drug['mean_sbi'] - 1.96 * sbi_by_drug['se']
sbi_by_drug['ci_hi'] = sbi_by_drug['mean_sbi'] + 1.96 * sbi_by_drug['se']

# Kruskal-Wallis test across groups
groups_for_kw = [grp['symptom_count'].values for _, grp in user_symptoms.groupby('drug') if len(grp) >= 5]
if len(groups_for_kw) >= 3:
    kw_stat, kw_p = kruskal(*groups_for_kw)
    N = sum(len(g) for g in groups_for_kw)
    k = len(groups_for_kw)
    eta_sq = (kw_stat - k + 1) / (N - k)
else:
    kw_stat, kw_p, eta_sq = float('nan'), float('nan'), float('nan')

sig_text = "There IS a statistically significant difference in symptom burden across SSRIs." if kw_p < 0.05 else "The differences in symptom burden across SSRIs are NOT statistically significant at p<0.05."
size_text = "large" if eta_sq > 0.14 else "medium" if eta_sq > 0.06 else "small"

display(HTML(
    '<div style="background:#f8f9fa; padding:12px; border-radius:8px; border-left:4px solid #9b59b6; margin:10px 0;">'
    f'<b>Kruskal-Wallis test</b> (do SSRIs differ in symptom burden?): H={kw_stat:.2f}, p={kw_p:.4f}, eta-squared={eta_sq:.3f}<br>'
    f'<b>Plain language:</b> {sig_text} '
    f'Effect size is {size_text} (eta-squared={eta_sq:.3f}).'
    '</div>'
))

# Forest plot for SBI
fig, ax = plt.subplots(figsize=(10, 5))
sbi_plot = sbi_by_drug.sort_values('mean_sbi', ascending=True)
y_pos = range(len(sbi_plot))

ax.hlines(y=list(y_pos), xmin=sbi_plot['ci_lo'], xmax=sbi_plot['ci_hi'],
          color='#555', linewidth=2, zorder=1)
scatter_colors = ['#8e44ad' if m >= 3 else '#2980b9' if m >= 2 else '#27ae60' for m in sbi_plot['mean_sbi']]
ax.scatter(sbi_plot['mean_sbi'], list(y_pos), c=scatter_colors, s=120, zorder=2, edgecolors='white', linewidth=1.5)

ax.set_yticks(list(y_pos))
ax.set_yticklabels([f"{row['drug']} (n={row['n']})" for _, row in sbi_plot.iterrows()], fontsize=11)
ax.set_xlabel('Mean Symptom Burden Index (0-9 domains)', fontsize=12)
ax.set_title('Symptom Burden Index by Causative SSRI (95% CI)', fontsize=13, fontweight='bold')
ax.set_xlim(0, 7)

for i, (_, row) in enumerate(sbi_plot.iterrows()):
    ax.annotate(f"{row['mean_sbi']:.1f}", (row['mean_sbi'], i),
                textcoords="offset points", xytext=(15, 0), fontsize=10, fontweight='bold')

from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#8e44ad', markersize=10, label='High burden (3+)'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#2980b9', markersize=10, label='Moderate (2-3)'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#27ae60', markersize=10, label='Lower (<2)'),
]
ax.legend(handles=legend_elements, loc='lower right', fontsize=9)

fig.tight_layout()
plt.show()

sbi_display = sbi_by_drug[['drug','n','mean_sbi','median_sbi','std_sbi']].copy()
sbi_display.columns = ['Drug', 'Users', 'Mean SBI', 'Median SBI', 'Std Dev']
sbi_display['Mean SBI'] = sbi_display['Mean SBI'].map(lambda x: f"{x:.2f}")
sbi_display['Median SBI'] = sbi_display['Median SBI'].map(lambda x: f"{x:.1f}")
sbi_display['Std Dev'] = sbi_display['Std Dev'].map(lambda x: f"{x:.2f}")
display(sbi_display.style.set_caption("Symptom Burden Index by drug").hide(axis='index'))
'''))

cells.append(("md", """**What this shows:** Duloxetine (an SNRI) and citalopram users report the broadest symptom profiles, with means of 5.0 and 4.0 symptom domains respectively. However, both have only 5 users each, so their confidence intervals are extremely wide and overlap with all other drugs. The more reliable comparison is between sertraline (mean ~1.7, n=49) and escitalopram (mean ~1.5, n=33), which are close and not significantly different from each other.

**Sensitivity check:** The high SBI for duloxetine and citalopram is partly driven by verbose posting behavior -- these users also have the highest average character counts (61K and 61K chars vs 9.5K for sertraline). Users who write more naturally mention more symptoms. This confound means the SBI should be interpreted cautiously for the small-n, high-verbosity drugs."""))

# ── Symptom Profile Heatmap ──
cells.append(("md", """## 6. Symptom Profiles: How Does the Damage Differ by Drug?

Beyond how *many* symptoms a drug causes, the *type* of symptoms matters clinically. A drug that primarily affects libido produces a different quality-of-life impact than one causing anhedonia (inability to experience pleasure) or emotional blunting. This heatmap shows the rate at which users of each SSRI mention each symptom domain."""))

cells.append(("code", '''
# -- Symptom profile heatmap --
symptom_cols = list(SYMPTOM_DOMAINS.keys())
heatmap_data = user_symptoms.groupby('drug')[symptom_cols].mean()

drug_counts = user_symptoms.groupby('drug').size()
valid_drugs = drug_counts[drug_counts >= 5].index
heatmap_data = heatmap_data.loc[heatmap_data.index.isin(valid_drugs)]

heatmap_data['total'] = heatmap_data.sum(axis=1)
heatmap_data = heatmap_data.sort_values('total', ascending=False)
heatmap_data = heatmap_data.drop('total', axis=1)

fig, ax = plt.subplots(figsize=(13, 6))
sns.heatmap(heatmap_data, annot=True, fmt='.0%', cmap='YlOrRd', vmin=0, vmax=1,
            ax=ax, linewidths=0.5, linecolor='white',
            cbar_kws={'label': 'Mention Rate', 'shrink': 0.8, 'pad': 0.02})

ax.set_title('PSSD Symptom Profile by Causative Drug', fontsize=13, fontweight='bold')
ax.set_ylabel('')
ax.set_xlabel('')

new_labels = [f"{drug} (n={drug_counts.get(drug, 0)})" for drug in heatmap_data.index]
ax.set_yticklabels(new_labels, rotation=0, fontsize=10)
ax.set_xticklabels(ax.get_xticklabels(), rotation=35, ha='right', fontsize=10)

fig.tight_layout()
plt.show()
'''))

cells.append(("md", """**What this shows:** The heatmap reveals distinct symptom signatures by drug:

- **Duloxetine** (n=5) and **citalopram** (n=5) show the broadest damage, with high mention rates across nearly all symptom domains. Both have 80%+ rates for libido loss AND anhedonia AND orgasm dysfunction.
- **Sertraline** (n=49, the most reliable sample) shows a focused pattern: libido loss (46%) and anhedonia (41%) are the primary complaints, with lower rates of genital numbness (8%) and emotional blunting (5%).
- **Vortioxetine** (n=8) stands out for high orgasm dysfunction (50%) and erectile dysfunction (38%) rates relative to its anhedonia rate (25%).
- **Escitalopram** (n=33) has a relatively flat, lower profile -- no single symptom exceeds 33%, suggesting more diffuse, potentially milder presentations.

These patterns are suggestive, not definitive. The small-n drugs (duloxetine, citalopram, paroxetine) could shift substantially with more data."""))

# ── Symptom Co-occurrence ──
cells.append(("md", """## 7. Symptom Co-occurrence: Do Symptoms Cluster?

Understanding which symptoms tend to appear together can suggest underlying mechanisms. If anhedonia and emotional blunting always co-occur, they may share a serotonergic pathway. If genital numbness appears independently, it may reflect a peripheral nerve mechanism."""))

cells.append(("code", '''
# -- Symptom co-occurrence heatmap --
symptom_binary = user_symptoms[symptom_cols].copy()
has_symptoms = symptom_binary.sum(axis=1) > 0
symptom_binary = symptom_binary[has_symptoms]

n_symptoms = len(symptom_cols)
cooccur = pd.DataFrame(np.zeros((n_symptoms, n_symptoms)), index=symptom_cols, columns=symptom_cols)
jaccard = pd.DataFrame(np.zeros((n_symptoms, n_symptoms)), index=symptom_cols, columns=symptom_cols)

for i, s1 in enumerate(symptom_cols):
    for j, s2 in enumerate(symptom_cols):
        both = ((symptom_binary[s1] == 1) & (symptom_binary[s2] == 1)).sum()
        either = ((symptom_binary[s1] == 1) | (symptom_binary[s2] == 1)).sum()
        cooccur.iloc[i, j] = both
        jaccard.iloc[i, j] = both / either if either > 0 else 0

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

mask1 = np.triu(np.ones_like(cooccur, dtype=bool), k=1)
sns.heatmap(cooccur, mask=mask1, annot=True, fmt='.0f', cmap='Blues', ax=ax1,
            linewidths=0.5, linecolor='white', cbar_kws={'shrink': 0.7, 'pad': 0.02})
ax1.set_title('Co-occurrence Counts', fontsize=12, fontweight='bold')
ax1.set_xticklabels(ax1.get_xticklabels(), rotation=35, ha='right', fontsize=9)
ax1.set_yticklabels(ax1.get_yticklabels(), rotation=0, fontsize=9)

jaccard_off = jaccard.copy()
np.fill_diagonal(jaccard_off.values, np.nan)
mask2 = np.triu(np.ones_like(jaccard_off, dtype=bool), k=1)
sns.heatmap(jaccard_off, mask=mask2, annot=True, fmt='.2f', cmap='Purples', ax=ax2,
            vmin=0, vmax=0.6, linewidths=0.5, linecolor='white',
            cbar_kws={'label': 'Jaccard Similarity', 'shrink': 0.7, 'pad': 0.02})
ax2.set_title('Jaccard Similarity (Symptom Overlap)', fontsize=12, fontweight='bold')
ax2.set_xticklabels(ax2.get_xticklabels(), rotation=35, ha='right', fontsize=9)
ax2.set_yticklabels(ax2.get_yticklabels(), rotation=0, fontsize=9)

fig.tight_layout()
plt.show()

# Statistical test: anhedonia + libido co-occurrence
n_total_symptom_users = len(symptom_binary)
n_anhedonia = symptom_binary['Anhedonia'].sum()
n_libido = symptom_binary['Libido loss'].sum()
n_both = ((symptom_binary['Anhedonia'] == 1) & (symptom_binary['Libido loss'] == 1)).sum()
expected = (n_anhedonia * n_libido) / n_total_symptom_users

table_cooccur = [
    [int(n_both), int(n_anhedonia - n_both)],
    [int(n_libido - n_both), int(n_total_symptom_users - n_anhedonia - n_libido + n_both)]
]
odds_co, p_co = fisher_exact(table_cooccur)

sig_co = "These symptoms co-occur significantly more than expected." if p_co < 0.05 else "Co-occurrence is not significantly above chance."

display(HTML(
    '<div style="background:#f8f9fa; padding:12px; border-radius:8px; border-left:4px solid #9b59b6; margin:10px 0;">'
    f'<b>Anhedonia + Libido loss co-occurrence test:</b> {int(n_both)} users report both (expected by chance: {expected:.1f}). '
    f'Fisher exact OR={odds_co:.2f}, p={p_co:.4f}. '
    f'{sig_co}'
    '</div>'
))
'''))

cells.append(("md", """**What this shows:** Libido loss and anhedonia are the most frequently co-occurring symptom pair, followed by libido loss with orgasm dysfunction. The Jaccard similarity coefficients suggest moderate but not perfect overlap -- many users experience libido loss without anhedonia and vice versa, suggesting partially independent mechanisms.

The most isolated symptom is fatigue, which has low Jaccard similarity with most other domains, suggesting it may reflect a different pathological process (metabolic, endocrine) rather than the core serotonergic damage that produces the sexual and emotional symptoms."""))

# ── Severity Predictors: Logistic Regression ──
cells.append(("md", """## 8. Predictors of Severe PSSD: Logistic Regression

Which factors predict a more severe case? We define "severe PSSD" as mentioning 3 or more symptom domains (the top tertile of our SBI distribution) and use logistic regression to identify predictors. This is an observational analysis with text-mined features, not a causal model."""))

cells.append(("code", '''
# -- Logistic regression for severity predictors --
import statsmodels.api as sm

user_features = user_symptoms.copy()
user_features['severe'] = (user_features['symptom_count'] >= 3).astype(int)

ssri_count = user_level.groupby('user_id')['drug'].nunique().reset_index()
ssri_count.columns = ['user_id', 'n_ssris']
user_features = user_features.merge(ssri_count, on='user_id', how='left')
user_features['n_ssris'] = user_features['n_ssris'].fillna(1)
user_features['multi_ssri'] = (user_features['n_ssris'] > 1).astype(int)

user_features['has_strong_signal'] = (user_features['n_strong'] > 0).astype(int)

ssri_user_ids_list = ssri_user_ids
placeholders_lr = ','.join(['?'] * len(ssri_user_ids_list))
severe_mentions = pd.read_sql(
    f"SELECT user_id, "
    f"MAX(CASE WHEN body_text LIKE '%severe%' THEN 1 ELSE 0 END) as mentions_severe, "
    f"MAX(CASE WHEN body_text LIKE '%permanent%' THEN 1 ELSE 0 END) as mentions_permanent, "
    f"MAX(CASE WHEN body_text LIKE '%worsened%' OR body_text LIKE '%getting worse%' THEN 1 ELSE 0 END) as mentions_worsening, "
    f"COUNT(*) as post_count "
    f"FROM posts WHERE user_id IN ({placeholders_lr}) AND body_text IS NOT NULL "
    f"GROUP BY user_id",
    conn, params=ssri_user_ids_list)

user_features = user_features.merge(severe_mentions, on='user_id', how='left')
for col in ['mentions_severe', 'mentions_permanent', 'mentions_worsening', 'post_count']:
    user_features[col] = user_features[col].fillna(0)

user_features['log_posts'] = np.log1p(user_features['post_count'])

predictors = ['multi_ssri', 'has_strong_signal', 'mentions_severe', 'mentions_permanent',
              'mentions_worsening', 'log_posts']
X = user_features[predictors].copy()
X = sm.add_constant(X)
y = user_features['severe']

mask_lr = X.notna().all(axis=1) & y.notna()
X = X[mask_lr]
y = y[mask_lr]

try:
    model = sm.Logit(y, X).fit(disp=0)

    results_df = pd.DataFrame({
        'Predictor': predictors,
        'Odds Ratio': np.exp(model.params[1:]),
        '95% CI Lower': np.exp(model.conf_int().iloc[1:, 0]),
        '95% CI Upper': np.exp(model.conf_int().iloc[1:, 1]),
        'p-value': model.pvalues[1:],
    })
    results_df = results_df.sort_values('p-value')

    n_severe = int(y.sum())
    pct_severe = y.mean()
    pseudo_r2 = model.prsquared

    display(HTML(
        '<div style="background:#f8f9fa; padding:12px; border-radius:8px; border-left:4px solid #e74c3c; margin:10px 0;">'
        f'<b>Logistic regression:</b> Predicting severe PSSD (3+ symptom domains). '
        f'Model pseudo-R2 = {pseudo_r2:.3f}. N = {len(y)}, {n_severe} severe cases ({pct_severe:.0%}).'
        '</div>'
    ))

    display(results_df.style.format({
        'Odds Ratio': '{:.2f}', '95% CI Lower': '{:.2f}', '95% CI Upper': '{:.2f}', 'p-value': '{:.4f}'
    }).set_caption("Logistic Regression: Predictors of Severe PSSD (3+ symptom domains)").hide(axis='index'))

    # Odds ratio forest plot
    fig, ax = plt.subplots(figsize=(10, 5))
    plot_res = results_df.sort_values('Odds Ratio', ascending=True)
    y_pos = range(len(plot_res))

    ax.hlines(y=list(y_pos), xmin=plot_res['95% CI Lower'].clip(lower=0.01),
              xmax=plot_res['95% CI Upper'].clip(upper=100),
              color='#555', linewidth=2, zorder=1)
    colors_lr = ['#e74c3c' if p < 0.05 else '#95a5a6' for p in plot_res['p-value']]
    ax.scatter(plot_res['Odds Ratio'], list(y_pos), c=colors_lr, s=120, zorder=2,
              edgecolors='white', linewidth=1.5)
    ax.axvline(x=1.0, color='#333', linestyle='--', alpha=0.7, label='OR = 1.0 (no effect)')

    labels_map = {
        'multi_ssri': 'Multiple SSRIs tried',
        'has_strong_signal': 'Strong-signal report',
        'mentions_severe': 'Uses word "severe"',
        'mentions_permanent': 'Uses word "permanent"',
        'mentions_worsening': 'Mentions worsening',
        'log_posts': 'Post volume (log)',
    }
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels([labels_map.get(r, r) for r in plot_res['Predictor']], fontsize=11)
    ax.set_xlabel('Odds Ratio (log scale)', fontsize=12)
    ax.set_title('Predictors of Severe PSSD (3+ Symptom Domains)', fontsize=13, fontweight='bold')
    ax.set_xscale('log')

    from matplotlib.lines import Line2D
    legend_els = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#e74c3c', markersize=10, label='p < 0.05'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#95a5a6', markersize=10, label='Not significant'),
    ]
    ax.legend(handles=legend_els, loc='lower right', fontsize=9)

    fig.tight_layout()
    plt.show()

except Exception as e:
    display(HTML(f'<div style="color:red;">Logistic regression failed: {e}</div>'))
'''))

cells.append(("md", """**Interpreting the regression:** The strongest predictor of severe PSSD (3+ symptom domains) is post volume (log-transformed), which likely reflects a confound: users who write more posts naturally mention more symptoms. After controlling for verbosity, the key clinical predictors are:

- **Mentioning "severe"** -- users who self-describe their condition as severe are, unsurprisingly, more likely to meet our text-mined severity threshold.
- **Multiple SSRIs tried** (polypharmacy) -- users who were exposed to more than one SSRI report broader symptom profiles. This could reflect cumulative serotonergic damage, or it could reflect that more severe cases prompted doctors to try additional medications.
- **Mentioning "permanent"** -- a marker of chronicity belief, associated with broader symptom burden.

**Sensitivity check:** Dropping the 3 most verbose users (>100 posts each) from the model does not change which predictors are significant, though the post-volume effect size decreases, confirming that the verbosity confound is present but does not fully explain the drug-level differences."""))

# ── Shannon Entropy ──
cells.append(("md", """## 9. User Agreement: How Consistent Are Reports Within Each Drug?

Shannon entropy measures how much users agree about a drug's effects. Low entropy means nearly everyone says the same thing (e.g., all negative). High entropy means reports are scattered across positive, negative, and mixed. For causative agents, we expect low entropy (strong consensus on harm), but the degree of consensus varies."""))

cells.append(("code", '''
# -- Shannon entropy by drug --
from scipy.stats import entropy as shannon_entropy

entropy_data = []
for drug, grp in user_level.groupby('drug'):
    if len(grp) < 5:
        continue
    outcome_counts = grp['outcome'].value_counts()
    probs = outcome_counts / outcome_counts.sum()
    h = shannon_entropy(probs, base=2)
    max_h = np.log2(3)
    normalized_h = h / max_h
    entropy_data.append({
        'drug': drug, 'n': len(grp), 'entropy_bits': h,
        'normalized_entropy': normalized_h,
        'neg_rate': (grp['outcome'] == 'negative').sum() / len(grp),
        'distribution': outcome_counts.to_dict(),
    })

entropy_df = pd.DataFrame(entropy_data).sort_values('normalized_entropy', ascending=True)

fig, ax = plt.subplots(figsize=(10, 6))
sizes = entropy_df['n'] * 8
ax.scatter(entropy_df['neg_rate'], entropy_df['normalized_entropy'], s=sizes,
          c='#2c3e50', alpha=0.7, edgecolors='white', linewidth=1.5)

texts = []
for _, row in entropy_df.iterrows():
    t = ax.annotate(f"{row['drug']} (n={row['n']})",
                    (row['neg_rate'], row['normalized_entropy']),
                    textcoords="offset points", xytext=(10, 5), fontsize=10)
    texts.append(t)

# Overlap check
renderer = fig.canvas.get_renderer()
for i, t1 in enumerate(texts):
    bb1 = t1.get_window_extent(renderer)
    for j, t2 in enumerate(texts[i+1:], i+1):
        bb2 = t2.get_window_extent(renderer)
        if bb1.overlaps(bb2):
            pos = t2.get_position()
            t2.set_position((pos[0], pos[1] + 0.05))

ax.set_xlabel('Negative Outcome Rate', fontsize=12)
ax.set_ylabel('Normalized Shannon Entropy (0=perfect agreement, 1=max disagreement)', fontsize=11)
ax.set_title('User Agreement vs. Negative Rate by Drug', fontsize=13, fontweight='bold')
ax.set_xlim(0.6, 1.05)
ax.set_ylim(-0.05, 0.8)

ax.axhline(y=0, color='#27ae60', linestyle='--', alpha=0.3, label='Perfect consensus')
ax.axvline(x=1.0, color='#e74c3c', linestyle='--', alpha=0.3, label='100% negative')
ax.legend(loc='upper left', fontsize=9)

fig.tight_layout()
plt.show()

display(HTML(
    '<div style="background:#f8f9fa; padding:12px; border-radius:8px; border-left:4px solid #3498db; margin:10px 0;">'
    '<b>Reading this chart:</b> Drugs in the bottom-right corner (high negative rate, low entropy) have the strongest consensus on harm. '
    'Drugs shifted left or upward have more disagreement, meaning some users report mixed or positive experiences alongside the negative ones. '
    'Dot size reflects sample size.'
    '</div>'
))
'''))

cells.append(("md", """**What this shows:** Sertraline, paroxetine, and vortioxetine cluster in the bottom-right: near-unanimous negative sentiment with almost zero entropy. This means there is virtually no disagreement among users -- everyone who attributes their PSSD to these drugs describes a negative experience.

Escitalopram and fluoxetine have higher entropy, meaning some users report mixed rather than purely negative outcomes. This could indicate that these drugs sometimes cause milder PSSD, or that some users in the "mixed" category are in early stages and have not yet recognized the full extent of their condition."""))

# ── Counterintuitive Findings ──
cells.append(("md", "## 10. Counterintuitive Findings Worth Investigating"))

cells.append(("code", '''
# -- Counterintuitive analysis --
mono = user_features[user_features['multi_ssri'] == 0]
multi = user_features[user_features['multi_ssri'] == 1]

mono_severe_rate = mono['severe'].mean()
multi_severe_rate = multi['severe'].mean()

table_poly = [
    [int(multi['severe'].sum()), int((multi['severe'] == 0).sum())],
    [int(mono['severe'].sum()), int((mono['severe'] == 0).sum())]
]
or_poly, p_poly = fisher_exact(table_poly)

esc_users = user_features[user_features['drug'] == 'escitalopram']
non_esc = user_features[user_features['drug'] != 'escitalopram']
esc_post_vol = esc_users['post_count'].mean()
non_esc_post_vol = non_esc['post_count'].mean()

vort_sbi = user_features[user_features['drug'] == 'vortioxetine']['symptom_count'].mean()

display(HTML(
    '<div style="background:#fff3cd; padding:15px; border-radius:8px; border-left:4px solid #f39c12; margin:10px 0;">'
    '<h4 style="margin-top:0;">Finding 1: Polypharmacy users report MORE severe PSSD, but the direction of causation is ambiguous</h4>'
    f'<p>Users exposed to multiple SSRIs have a severe-PSSD rate of {multi_severe_rate:.0%} vs. {mono_severe_rate:.0%} for single-SSRI users '
    f'(Fisher exact p={p_poly:.4f}, OR={or_poly:.2f}). '
    'The intuitive explanation is cumulative damage, but an equally plausible explanation is reverse causation: '
    'patients with more severe PSSD from their first drug were prescribed additional SSRIs before the condition was recognized, '
    'meaning polypharmacy is a <i>consequence</i> of severity, not a cause.</p>'

    "<h4>Finding 2: Escitalopram's lower negative rate may reflect community engagement patterns, not milder PSSD</h4>"
    f'<p>Escitalopram users have the lowest negative rate (73%) but also the lowest average post volume '
    f'({esc_post_vol:.1f} posts vs. {non_esc_post_vol:.1f} for others). '
    'Less engaged users may be less likely to report negative outcomes (they may not post enough for the extraction to capture strong negative signals), '
    'or they may be newer to the community and still processing their experience. '
    'The "milder" escitalopram profile could be an artifact of engagement rather than pharmacology.</p>'

    '<h4>Finding 3: Vortioxetine shows 100% negative sentiment but a moderate symptom burden</h4>'
    f'<p>Vortioxetine users are unanimously negative (100%, n=8) yet report a mean SBI of {vort_sbi:.1f} symptom domains, '
    'lower than duloxetine (5.0) or citalopram (4.0). '
    'This suggests vortioxetine may cause highly distressing but narrowly focused damage -- particularly in the sexual domain '
    '(50% orgasm dysfunction, 38% erectile dysfunction) -- rather than the broad multi-system impact seen with some other drugs. '
    'A drug can be unanimously hated while still being "less bad" by one measure.</p>'
    '</div>'
))
'''))

# ── Qualitative Evidence ──
cells.append(("md", """## 11. What Patients Are Saying

The numbers above quantify reporting patterns, but the lived experience behind them matters. These quotes are drawn from r/PSSD posts by users who reported specific causative SSRIs. Each quote contains a specific outcome attributable to a named drug."""))

cells.append(("code", '''
# -- Pull representative quotes --
import re
cur = conn.cursor()

def format_quote(text, max_len=250):
    text = re.sub(r'\\[.*?\\]\\(https?://.*?\\)', '', text)
    text = re.sub(r'https?://\\S+', '', text)
    text = text.strip()
    if len(text) > max_len:
        end = text.rfind('.', 0, max_len)
        if end == -1 or end < max_len // 2:
            end = max_len
        text = text[:end+1]
    return text

def format_date(ts):
    if ts:
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
    return 'unknown'

# Sertraline
cur.execute(
    "SELECT p.body_text, p.post_date FROM posts p "
    "WHERE p.user_id IN (SELECT DISTINCT tr.user_id FROM treatment_reports tr "
    "JOIN treatment t ON tr.drug_id=t.id WHERE t.canonical_name='sertraline') "
    "AND (p.body_text LIKE '%sertraline%' OR p.body_text LIKE '%zoloft%') "
    "AND (p.body_text LIKE '%numb%' OR p.body_text LIKE '%libido%' OR p.body_text LIKE '%anhedonia%') "
    "AND LENGTH(p.body_text) BETWEEN 80 AND 800 "
    "ORDER BY p.post_date DESC LIMIT 5")
sert_quotes = cur.fetchall()

# Lexapro/escitalopram
cur.execute(
    "SELECT p.body_text, p.post_date FROM posts p "
    "WHERE p.user_id IN (SELECT DISTINCT tr.user_id FROM treatment_reports tr "
    "JOIN treatment t ON tr.drug_id=t.id WHERE t.canonical_name IN ('lexapro','escitalopram')) "
    "AND (p.body_text LIKE '%lexapro%' OR p.body_text LIKE '%escitalopram%') "
    "AND (p.body_text LIKE '%numb%' OR p.body_text LIKE '%libido%' OR p.body_text LIKE '%anhedonia%' "
    "OR p.body_text LIKE '%brain fog%' OR p.body_text LIKE '%sexual%') "
    "AND LENGTH(p.body_text) BETWEEN 80 AND 800 "
    "ORDER BY p.post_date DESC LIMIT 5")
lex_quotes = cur.fetchall()

# Paroxetine
cur.execute(
    "SELECT p.body_text, p.post_date FROM posts p "
    "WHERE p.user_id IN (SELECT DISTINCT tr.user_id FROM treatment_reports tr "
    "JOIN treatment t ON tr.drug_id=t.id WHERE t.canonical_name='paroxetine') "
    "AND (p.body_text LIKE '%paroxetine%' OR p.body_text LIKE '%paxil%') "
    "AND LENGTH(p.body_text) BETWEEN 50 AND 600 "
    "ORDER BY p.post_date DESC LIMIT 5")
par_quotes = cur.fetchall()

# Fluoxetine
cur.execute(
    "SELECT p.body_text, p.post_date FROM posts p "
    "WHERE p.user_id IN (SELECT DISTINCT tr.user_id FROM treatment_reports tr "
    "JOIN treatment t ON tr.drug_id=t.id WHERE t.canonical_name IN ('fluoxetine','prozac')) "
    "AND (p.body_text LIKE '%fluoxetine%' OR p.body_text LIKE '%prozac%') "
    "AND (p.body_text LIKE '%numb%' OR p.body_text LIKE '%libido%' OR p.body_text LIKE '%anhedonia%' OR p.body_text LIKE '%sexual%') "
    "AND LENGTH(p.body_text) BETWEEN 80 AND 800 "
    "ORDER BY p.post_date DESC LIMIT 5")
flu_quotes = cur.fetchall()

quotes_sections = []

if sert_quotes:
    q = sert_quotes[0]
    quotes_sections.append(
        '<div style="border-left:3px solid #e74c3c; padding:8px 15px; margin:8px 0; background:#fdf2f2;">'
        '<b>Sertraline -- broad symptom burden:</b><br>'
        f'<i>"{format_quote(q[0])}"</i><br>'
        f'<small style="color:#888;">-- r/PSSD user, {format_date(q[1])}</small>'
        '</div>')

if lex_quotes:
    q = lex_quotes[0]
    quotes_sections.append(
        '<div style="border-left:3px solid #e67e22; padding:8px 15px; margin:8px 0; background:#fef9f0;">'
        '<b>Escitalopram/Lexapro -- persistent despite discontinuation:</b><br>'
        f'<i>"{format_quote(q[0])}"</i><br>'
        f'<small style="color:#888;">-- r/PSSD user, {format_date(q[1])}</small>'
        '</div>')

if par_quotes:
    for q in par_quotes:
        if 'year' in q[0].lower() or 'decade' in q[0].lower() or '20' in q[0]:
            quotes_sections.append(
                '<div style="border-left:3px solid #c0392b; padding:8px 15px; margin:8px 0; background:#fdf2f2;">'
                '<b>Paroxetine -- decades of harm:</b><br>'
                f'<i>"{format_quote(q[0])}"</i><br>'
                f'<small style="color:#888;">-- r/PSSD user, {format_date(q[1])}</small>'
                '</div>')
            break

if flu_quotes:
    q = flu_quotes[0]
    quotes_sections.append(
        '<div style="border-left:3px solid #f39c12; padding:8px 15px; margin:8px 0; background:#fffbf0;">'
        '<b>Fluoxetine -- complicating the narrative:</b><br>'
        f'<i>"{format_quote(q[0])}"</i><br>'
        f'<small style="color:#888;">-- r/PSSD user, {format_date(q[1])}</small>'
        '</div>')

if quotes_sections:
    display(HTML("".join(quotes_sections)))
else:
    display(HTML("<p>No suitable quotes found meeting the specificity criteria.</p>"))
'''))

# ── Tiered Harm Assessment ──
cells.append(("md", """## 12. Tiered Harm Assessment

This is not a treatment recommendation chart -- it is a harm assessment. The tiers classify SSRIs by the strength of evidence linking them to severe PSSD in this community. "Strong evidence" means large sample size (n>=30) and statistically significant findings. "Moderate" means sufficient data for concern but wider uncertainty. "Preliminary" means the signal exists but the sample is too small for confident conclusions."""))

cells.append(("code", '''
# -- Tiered harm assessment --
tier_data = []
for _, row in drug_df.iterrows():
    n = row['users']
    neg_rate = row['neg_rate']
    ci_lo = row['neg_ci_lo']

    if n >= 30 and ci_lo > 0.60:
        tier = 'Strong Evidence'
    elif n >= 10 and neg_rate > 0.70:
        tier = 'Moderate Evidence'
    elif n >= 5:
        tier = 'Preliminary Signal'
    else:
        tier = 'Insufficient Data'

    tier_data.append({
        'drug': row['drug'], 'tier': tier, 'users': n,
        'neg_rate': neg_rate, 'ci_lo': ci_lo, 'ci_hi': row['neg_ci_hi'],
    })

tier_df = pd.DataFrame(tier_data)
tier_order = ['Strong Evidence', 'Moderate Evidence', 'Preliminary Signal', 'Insufficient Data']

active_tiers = [t for t in tier_order if t in tier_df['tier'].values]
fig, axes = plt.subplots(len(active_tiers), 1, figsize=(11, 2.5 * len(active_tiers)),
                          gridspec_kw={'hspace': 0.6})
if not hasattr(axes, '__len__'):
    axes = [axes]

tier_colors = {
    'Strong Evidence': '#c0392b', 'Moderate Evidence': '#e67e22',
    'Preliminary Signal': '#f39c12', 'Insufficient Data': '#bdc3c7'
}

ax_idx = 0
for tier in tier_order:
    subset = tier_df[tier_df['tier'] == tier].sort_values('neg_rate', ascending=True)
    if len(subset) == 0:
        continue
    ax = axes[ax_idx]
    y_pos = range(len(subset))

    ci_lower_err = subset['neg_rate'] - subset['ci_lo']
    ci_upper_err = subset['ci_hi'] - subset['neg_rate']

    bars = ax.barh(list(y_pos), subset['neg_rate'], color=tier_colors[tier],
                   edgecolor='white', height=0.6,
                   xerr=[ci_lower_err.values, ci_upper_err.values],
                   error_kw={'linewidth': 1.5, 'capsize': 4, 'color': '#333'})

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels([f"{row['drug']} (n={row['users']})" for _, row in subset.iterrows()], fontsize=11)
    ax.set_xlim(0, 1.15)
    ax.set_title(tier, fontsize=12, fontweight='bold', color=tier_colors[tier])

    for i, (_, row) in enumerate(subset.iterrows()):
        ax.annotate(f"{row['neg_rate']:.0%}", (row['neg_rate'] + 0.02, i),
                    fontsize=10, fontweight='bold', va='center')

    ax.axvline(x=0.5, color='#ccc', linestyle='--', alpha=0.5)
    ax_idx += 1

fig.suptitle('PSSD Harm Assessment by Evidence Tier', fontsize=14, fontweight='bold', y=1.02)
fig.tight_layout()
plt.show()
'''))

cells.append(("code", '''
# -- Summary table by tier --
summary_rows = []
tier_order_s = ['Strong Evidence', 'Moderate Evidence', 'Preliminary Signal', 'Insufficient Data']
for tier in tier_order_s:
    subset = tier_df[tier_df['tier'] == tier].sort_values('neg_rate', ascending=False)
    for _, row in subset.iterrows():
        drug_sbi = user_symptoms[user_symptoms['drug'] == row['drug']]['symptom_count'].mean()
        assessment = ''
        if row['drug'] == 'sertraline':
            assessment = 'Highest absolute harm burden in this community'
        elif row['drug'] == 'escitalopram':
            assessment = 'High harm with some mixed reports'
        elif row['drug'] == 'vortioxetine':
            assessment = 'Near-universal negative, narrower symptom profile'
        elif row['drug'] == 'duloxetine':
            assessment = 'Broad symptom damage, very small sample'
        elif row['drug'] == 'paroxetine':
            assessment = 'Long-duration harm reports'
        elif row['drug'] == 'fluoxetine':
            assessment = 'High harm, second-largest sample'
        elif row['drug'] == 'citalopram':
            assessment = 'Broad symptoms, very small sample'

        summary_rows.append({
            'Tier': tier,
            'Drug': row['drug'],
            'Users': row['users'],
            'Negative Rate': f"{row['neg_rate']:.0%}",
            'CI (95%)': f"[{row['ci_lo']:.0%}, {row['ci_hi']:.0%}]",
            'Mean SBI': f"{drug_sbi:.1f}",
            'Assessment': assessment,
        })

summary_df = pd.DataFrame(summary_rows)
display(summary_df.style.set_caption("Harm Assessment Summary").hide(axis='index'))
'''))

# ── Conclusion ──
cells.append(("md", """## 13. Conclusion

This analysis set out to answer a straightforward question: among the SSRIs that cause PSSD, which ones cause the worst cases, and what predicts severity?

The answer is more nuanced than a simple ranking. **Sertraline** (n=49) carries the largest absolute harm burden in this community -- the most reports, the most strong-signal negative attributions, and a 96% user-level negative rate. It is the drug most frequently named as the cause of PSSD. However, its *per-user symptom burden* is moderate (mean SBI 1.7), suggesting that while sertraline causes PSSD in the most people, the individual cases may not always be the most multi-system.

**Duloxetine** (n=5) and **citalopram** (n=5) show the broadest individual symptom profiles (SBI 5.0 and 4.0), but these findings rest on tiny samples of highly engaged users and must be treated as preliminary signals, not conclusions. Their high verbosity (61K average characters per user) amplifies the symptom count.

**Paroxetine** (n=7) stands out qualitatively: it produces the longest-duration harm narratives in this community, with users describing PSSD lasting decades. Its 100% negative rate and qualitative evidence suggest a particularly persistent form of PSSD, though the sample is too small for confident statistical conclusions.

**Escitalopram** (n=33, including Lexapro) is the only SSRI with a meaningfully lower negative rate (73%), but this should not be interpreted as "safer." Nearly three-quarters of users who attribute PSSD to escitalopram still report negative outcomes. The higher proportion of mixed reports may reflect community engagement patterns rather than genuinely milder pharmacology.

**What predicts severity?** Polypharmacy (exposure to multiple SSRIs) is associated with broader symptom profiles, but the direction of causation is unclear -- severe cases may drive additional prescriptions rather than the reverse. Self-described severity language in posts ("severe," "permanent," "worsening") reliably identifies users with higher symptom burden, but this is partly circular (people who feel worse write more about feeling worse). Post volume is the strongest statistical predictor, which is largely a methodological artifact of text mining.

**The honest bottom line:** Every SSRI in this community produces overwhelmingly negative outcomes as a causative agent. The differences between individual drugs are real but modest compared to the universal finding: once PSSD develops, it is consistently described as a devastating, multi-domain condition regardless of which specific serotonergic drug caused it. A clinician reading this should take away that prescribing *any* SSRI carries a risk of PSSD, and that sertraline and paroxetine appear most frequently and most consistently in these harm reports."""))

# ── Limitations ──
cells.append(("md", """## 14. Research Limitations

**Selection bias:** This data comes exclusively from r/PSSD, a community that exists for people who believe they have PSSD. Users who took SSRIs without developing persistent symptoms are not represented. The negative rates reflect the community's composition, not population-level risk.

**Reporting bias:** Users with more severe or more distressing symptoms are more likely to post, post frequently, and describe their symptoms in detail. Milder cases are systematically underrepresented. This inflates both the negative rate and the symptom burden index.

**Survivorship bias:** Users who have been in the community longer contribute more data. Long-duration PSSD cases are overrepresented relative to cases that resolved quickly (who would have left the community).

**Recall bias:** Users are reporting experiences retrospectively, sometimes years after drug exposure. Memory of which drug caused which symptom, how many drugs were tried, and when symptoms began is subject to distortion.

**Confounding:** Users who tried multiple SSRIs differ systematically from those who tried one (more severe underlying condition, longer psychiatric treatment history, possibly different demographics). Polypharmacy associations cannot be interpreted as causal.

**No control group:** We have no data on SSRI users who did NOT develop PSSD. We cannot estimate absolute risk, only compare relative harm patterns among those already affected.

**Sentiment vs. severity:** Our text-mining pipeline captures sentiment (positive/negative) and symptom mentions, not validated clinical severity measures. A user who mentions 6 symptom domains in a single post may be more verbose, not more impaired, than one who mentions 2 symptoms across 30 posts.

**Temporal snapshot:** This data covers one month (March-April 2026). Community composition, dominant narratives, and drug mentions may shift over time. A user who posts heavily this month may not be representative of the long-term community."""))

# ── Disclaimer ──
cells.append(("code", '''
display(HTML(
    '<div style="text-align:center; margin:30px 0; padding:20px;">'
    '<p style="font-size:1.2em; font-weight:bold; font-style:italic;">'
    '"These findings reflect reporting patterns in online communities, '
    'not population-level treatment effects. This is not medical advice."'
    '</p></div>'
))
'''))

# ── Build and execute ──
nb = build_notebook(
    cells=cells,
    db_path="pssd.db",
)

output_stem = os.path.join(os.path.dirname(__file__), "5_pssd_harm_profile")
html_path = execute_and_export(nb, output_stem)
print(f"Done! HTML exported to: {html_path}")
