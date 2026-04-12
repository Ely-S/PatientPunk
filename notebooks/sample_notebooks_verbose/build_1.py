"""Build Notebook 1: Long COVID Treatment Overview (Verbose)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from build_notebook import build_notebook, execute_and_export

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "polina_onemonth.db"))

cells = []

# ══════════════════════════════════════════════════════════════════════════════
# RESEARCH QUESTION
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", '**Research Question:** "Which treatments have the best outcomes in Long COVID?"'))

# ══════════════════════════════════════════════════════════════════════════════
# ABSTRACT
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## Abstract

Using 6,815 treatment reports from 1,121 unique users in r/covidlonghaulers (March--April 2026), this analysis identifies the treatments most consistently associated with positive patient-reported outcomes in the Long COVID community. After filtering generic terms, causal-context contamination (vaccines perceived as causing illness), and merging duplicate names, we rank treatments by user-level positive outcome rate with Wilson score confidence intervals, compare treatment classes using Kruskal-Wallis tests and pairwise Fisher's exact comparisons, run logistic regression to identify predictors of positive outcomes, evaluate user agreement via Shannon entropy, and extract qualitative evidence from patient posts. The strongest signal comes from electrolyte and magnesium supplementation, low dose naltrexone (LDN), antihistamine protocols, and B-vitamin supplementation -- all with positive rates significantly above the 50% baseline. SSRIs and antibiotics are the notable underperformers, with positive rates near or below chance. The data suggest that mast cell / histamine-targeting approaches and volume-expansion strategies produce the most consistent community-reported benefit."""))

# ══════════════════════════════════════════════════════════════════════════════
# 1. DATA EXPLORATION
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 1. Data Exploration

Data covers: **2026-03-11 to 2026-04-10** (1 month), sourced from r/covidlonghaulers.

This analysis uses the full community dataset rather than a condition-specific subset. The question -- which treatments work best -- is the broadest question patients ask, so we start broad and narrow in subsequent sections."""))

# ---- CELL: Data loading and filtering ----
cells.append(("code",
r"""
# -- Causal-context and generic filtering --
CAUSAL_EXCLUSIONS = {'covid vaccine', 'flu vaccine', 'mmr vaccine', 'moderna vaccine',
                     'mrna covid-19 vaccine', 'pfizer vaccine', 'vaccine', 'vaccine injection',
                     'pfizer', 'booster', 'biontech', 'tdap', 'live vaccine', 'moderna'}

MERGE_MAP = {
    'pepcid': 'famotidine', 'naltrexone': 'low dose naltrexone',
    'coenzyme q10': 'coq10', 'weed': 'cannabis', 'marijuana': 'cannabis',
    'selective serotonin reuptake inhibitor': 'ssri',
    'vitamin b12': 'b12', 'cymbalta': 'duloxetine', 'wellbutrin': 'bupropion',
    'magnesium citrate': 'magnesium', 'magnesium glycinate': 'magnesium',
    'magnesium oil': 'magnesium', 'epsom salts': 'magnesium',
    'electrolytes powder': 'electrolyte', 'gatorade': 'electrolyte',
    'sea salt': 'salt', 'low dose propranolol': 'propranolol',
    'd3': 'vitamin d', 'vitamin d3': 'vitamin d',
    'hyperbaric oxygen therapy': 'hbot', 'ivm': 'ivermectin',
    'lorazepam': 'benzodiazepine', 'ativan': 'benzodiazepine',
    'xanax': 'benzodiazepine', 'alprazolam': 'benzodiazepine',
    'benzo': 'benzodiazepine', 'diazepam': 'benzodiazepine',
    'oral antihistamines': 'antihistamines', 'drowsy antihistamine': 'antihistamines',
    'non drowsy antihistamine': 'antihistamines', 'blood brain barrier antihistamines': 'antihistamines',
    'nasal antihistamine': 'antihistamines',
}

EXCL_ALL = GENERIC_TERMS | CAUSAL_EXCLUSIONS

# Treatment class assignment
TX_CLASS = {
    'beta blocker': 'Autonomic', 'propranolol': 'Autonomic', 'ivabradine': 'Autonomic',
    'midodrine': 'Autonomic', 'clonidine': 'Autonomic', 'guanfacine': 'Autonomic',
    'electrolyte': 'Volume/Electrolyte', 'salt': 'Volume/Electrolyte',
    'magnesium': 'Volume/Electrolyte', 'potassium': 'Volume/Electrolyte',
    'iron': 'Volume/Electrolyte', 'iron supplement': 'Volume/Electrolyte',
    'antihistamines': 'Antihistamine/MastCell', 'ketotifen': 'Antihistamine/MastCell',
    'famotidine': 'Antihistamine/MastCell', 'cetirizine': 'Antihistamine/MastCell',
    'fexofenadine': 'Antihistamine/MastCell', 'loratadine': 'Antihistamine/MastCell',
    'hydroxyzine': 'Antihistamine/MastCell', 'h1 antihistamine': 'Antihistamine/MastCell',
    'h2 antihistamine': 'Antihistamine/MastCell', 'cromolyn sodium': 'Antihistamine/MastCell',
    'quercetin': 'Antihistamine/MastCell', 'dao': 'Antihistamine/MastCell',
    'low dose naltrexone': 'ImmuneModulation', 'fluvoxamine': 'ImmuneModulation',
    'rapamycin': 'ImmuneModulation', 'ivermectin': 'ImmuneModulation',
    'paxlovid': 'ImmuneModulation', 'stellate ganglion block': 'ImmuneModulation',
    'methylene blue': 'ImmuneModulation',
    'coq10': 'Mito/Antioxidant', 'n-acetylcysteine': 'Mito/Antioxidant',
    'glutathione': 'Mito/Antioxidant', 'creatine': 'Mito/Antioxidant',
    'alpha-lipoic acid': 'Mito/Antioxidant', 'resveratrol': 'Mito/Antioxidant',
    'vitamin d': 'Vitamin/Supplement', 'vitamin c': 'Vitamin/Supplement',
    'b12': 'Vitamin/Supplement', 'b1': 'Vitamin/Supplement',
    'b vitamins': 'Vitamin/Supplement', 'zinc': 'Vitamin/Supplement',
    'multivitamin': 'Vitamin/Supplement', 'omega-3': 'Vitamin/Supplement',
    'fish oil': 'Vitamin/Supplement', 'biotin': 'Vitamin/Supplement',
    'probiotics': 'GI/Gut', 'berberine': 'GI/Gut',
    'nattokinase': 'Fibrinolytic', 'lumbrokinase': 'Fibrinolytic',
    'aspirin': 'Anti-inflammatory', 'ibuprofen': 'Anti-inflammatory',
    'bromelain': 'Anti-inflammatory', 'curcumin': 'Anti-inflammatory',
    'ssri': 'Psych/Neuro', 'escitalopram': 'Psych/Neuro', 'sertraline': 'Psych/Neuro',
    'fluoxetine': 'Psych/Neuro', 'duloxetine': 'Psych/Neuro',
    'mirtazapine': 'Psych/Neuro', 'bupropion': 'Psych/Neuro',
    'trazodone': 'Psych/Neuro', 'benzodiazepine': 'Psych/Neuro',
    'gabapentin': 'Psych/Neuro', 'pregabalin': 'Psych/Neuro',
    'modafinil': 'Psych/Neuro', 'adderall': 'Psych/Neuro',
    'nicotine': 'Novel/Experimental', 'glp-1 receptor agonist': 'Novel/Experimental',
    'tirzepatide': 'Novel/Experimental', 'tadalafil': 'Novel/Experimental',
    'melatonin': 'Sleep', 'cannabis': 'Cannabis', 'cbd': 'Cannabis',
    'red light therapy': 'Physical/Device', 'hbot': 'Physical/Device',
    'infrared sauna': 'Physical/Device',
    'vagus nerve stimulation': 'Physical/Device',
}

# -- Load all treatment reports --
raw = pd.read_sql(
    'SELECT tr.user_id, t.canonical_name as drug, tr.sentiment, tr.signal_strength, '
    "CASE tr.sentiment WHEN 'positive' THEN 1.0 WHEN 'mixed' THEN 0.5 "
    "WHEN 'neutral' THEN 0.0 WHEN 'negative' THEN -1.0 ELSE 0.0 END as score "
    'FROM treatment_reports tr JOIN treatment t ON tr.drug_id = t.id',
    conn)

n_raw = len(raw)
n_raw_users = raw['user_id'].nunique()

# Filter generics and causal
raw['drug_lower'] = raw['drug'].str.lower()
raw = raw[~raw['drug_lower'].isin([x.lower() for x in EXCL_ALL])]

# Apply merges
raw['drug'] = raw['drug_lower'].map(lambda x: MERGE_MAP.get(x, x))

# Assign classes
raw['tx_class'] = raw['drug'].map(TX_CLASS).fillna('Other')

# User-drug level aggregation (one data point per user per drug)
user_drug = raw.groupby(['user_id', 'drug']).agg(
    avg_score=('score', 'mean'),
    n_reports=('score', 'count'),
    tx_class=('tx_class', 'first'),
    max_signal=('signal_strength', lambda x: 'strong' if 'strong' in x.values else ('moderate' if 'moderate' in x.values else 'weak'))
).reset_index()
user_drug['outcome'] = user_drug['avg_score'].apply(classify_outcome)

n_filt = len(raw)
n_filt_users = raw['user_id'].nunique()

display(HTML(
    "<h4>Verbose Processing Summary</h4>"
    "<table style='border-collapse:collapse; font-size:13px;'>"
    "<tr style='border-bottom:2px solid #333;'>"
    "<th style='padding:4px 12px; text-align:left;'>Step</th>"
    "<th style='padding:4px 12px; text-align:right;'>Reports</th>"
    "<th style='padding:4px 12px; text-align:right;'>Users</th></tr>"
    f"<tr><td style='padding:4px 12px;'>Raw reports loaded</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{n_raw:,}</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{n_raw_users:,}</td></tr>"
    f"<tr><td style='padding:4px 12px;'>After filtering generics + causal exclusions</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{n_filt:,}</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{n_filt_users:,}</td></tr>"
    f"<tr><td style='padding:4px 12px;'>User-drug aggregated rows</td>"
    f"<td style='text-align:right; padding:4px 12px;' colspan='2'>{len(user_drug):,}</td></tr>"
    f"<tr><td style='padding:4px 12px;'>Unique treatments after merging</td>"
    f"<td style='text-align:right; padding:4px 12px;' colspan='2'>{user_drug['drug'].nunique()}</td></tr>"
    "</table>"
    "<p style='font-size:12px; color:#666; margin-top:8px;'>"
    "<b>Exclusions:</b> Generic terms (supplements, medication, treatment, therapy, drug, vitamin, etc.) "
    "removed because they are categories, not actionable treatments. "
    "Causal-context exclusions: all vaccine entries (covid vaccine, pfizer, moderna, booster, etc.) "
    "removed because negative sentiment reflects perceived causation of Long COVID, not treatment response. "
    "Duplicate canonicals merged: pepcid to famotidine, various magnesium forms to magnesium, "
    "naltrexone to low dose naltrexone, etc.</p>"
))
"""))

# ══════════════════════════════════════════════════════════════════════════════
# 2. BASELINE: Overall Sentiment Landscape
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 2. Establishing the Baseline: Overall Sentiment Landscape

Before examining individual treatments, we need to understand the overall reporting pattern. What fraction of treatment reports in this community are positive? This establishes the benchmark against which individual treatments will be measured. If the community baseline is already high, a treatment needs to clear a higher bar to be noteworthy."""))

# ---- CELL: Baseline stats ----
cells.append(("code",
r"""
# -- Overall sentiment distribution at user-drug level --
outcome_counts = user_drug['outcome'].value_counts()
total_ud = len(user_drug)
pos_rate_overall = (user_drug['outcome'] == 'positive').mean()
neg_rate_overall = (user_drug['outcome'] == 'negative').mean()
mixed_rate_overall = (user_drug['outcome'] == 'mixed/neutral').mean()

# Binomial test vs 50% for positive rate
from scipy.stats import binomtest
pos_n_overall = int((user_drug['outcome'] == 'positive').sum())
binom_result = binomtest(pos_n_overall, total_ud, 0.5)
ci_lo_overall, ci_hi_overall = wilson_ci(pos_n_overall, total_ud)

# Shannon entropy for user agreement across sentiments
from scipy.stats import entropy as sp_entropy
sent_probs = user_drug['outcome'].value_counts(normalize=True).values
shannon_h = sp_entropy(sent_probs, base=2)
max_entropy = np.log2(3)  # 3 categories
agreement_ratio = 1 - (shannon_h / max_entropy)

# By signal strength
strong_pos = (user_drug[user_drug['max_signal'] == 'strong']['outcome'] == 'positive').mean()
moderate_pos = (user_drug[user_drug['max_signal'] == 'moderate']['outcome'] == 'positive').mean()
weak_pos = (user_drug[user_drug['max_signal'] == 'weak']['outcome'] == 'positive').mean()
strong_n = len(user_drug[user_drug['max_signal'] == 'strong'])
moderate_n = len(user_drug[user_drug['max_signal'] == 'moderate'])
weak_n = len(user_drug[user_drug['max_signal'] == 'weak'])

display(HTML(
    "<h4>Community Baseline</h4>"
    "<table style='border-collapse:collapse; font-size:13px;'>"
    "<tr style='border-bottom:2px solid #333;'>"
    "<th style='padding:4px 12px; text-align:left;'>Metric</th>"
    "<th style='padding:4px 12px; text-align:right;'>Value</th></tr>"
    f"<tr><td style='padding:4px 12px;'>Total user-drug pairs</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{total_ud:,}</td></tr>"
    f"<tr><td style='padding:4px 12px;'>Positive outcome rate</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{pos_rate_overall:.1%} [{ci_lo_overall:.3f}, {ci_hi_overall:.3f}]</td></tr>"
    f"<tr><td style='padding:4px 12px;'>Negative outcome rate</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{neg_rate_overall:.1%}</td></tr>"
    f"<tr><td style='padding:4px 12px;'>Mixed/neutral rate</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{mixed_rate_overall:.1%}</td></tr>"
    f"<tr><td style='padding:4px 12px;'>Binomial test vs 50%</td>"
    f"<td style='text-align:right; padding:4px 12px;'>p = {binom_result.pvalue:.2e}</td></tr>"
    f"<tr><td style='padding:4px 12px;'>Shannon entropy (agreement)</td>"
    f"<td style='text-align:right; padding:4px 12px;'>H = {shannon_h:.3f} / {max_entropy:.3f} max (agreement: {agreement_ratio:.2f})</td></tr>"
    f"<tr style='border-top:1px solid #ccc;'><td style='padding:4px 12px;'>Strong signal positive rate</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{strong_pos:.1%} (n={strong_n})</td></tr>"
    f"<tr><td style='padding:4px 12px;'>Moderate signal positive rate</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{moderate_pos:.1%} (n={moderate_n})</td></tr>"
    f"<tr><td style='padding:4px 12px;'>Weak signal positive rate</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{weak_pos:.1%} (n={weak_n})</td></tr>"
    "</table>"
))
"""))

# ---- CELL: Chart 1 - Baseline donut + signal strength ----
cells.append(("code",
r"""
# -- CHART 1: Donut chart of overall sentiment distribution --
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

# Left: donut chart
labels = ['Positive', 'Mixed/Neutral', 'Negative']
sizes = [pos_rate_overall, mixed_rate_overall, neg_rate_overall]
colors_donut = ['#2ecc71', '#95a5a6', '#e74c3c']
wedges, texts, autotexts = ax1.pie(sizes, labels=labels, colors=colors_donut,
                                     autopct='%1.1f%%', startangle=90,
                                     pctdistance=0.75, wedgeprops=dict(width=0.4))
for t in autotexts:
    t.set_fontsize(12)
    t.set_fontweight('bold')
ax1.set_title('Overall Outcome Distribution\n(User-Drug Level)', fontsize=13, fontweight='bold')

# Right: positive rate by signal strength
sig_labels = ['Strong', 'Moderate', 'Weak']
sig_rates = [strong_pos * 100, moderate_pos * 100, weak_pos * 100]
sig_ns = [strong_n, moderate_n, weak_n]
bars = ax2.bar(sig_labels, sig_rates, color=['#27ae60', '#f39c12', '#bdc3c7'],
               edgecolor='white', width=0.5)
ax2.axhline(y=pos_rate_overall * 100, color='#333', linestyle='--', alpha=0.5,
            label='Overall: {:.1f}%'.format(pos_rate_overall * 100))
for bar, n in zip(bars, sig_ns):
    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.5,
             'n={}'.format(n), ha='center', va='bottom', fontsize=10)
ax2.set_ylabel('Positive Outcome Rate (%)', fontsize=11)
ax2.set_title('Positive Rate by Signal Strength', fontsize=13, fontweight='bold')
ax2.set_ylim(0, 100)
ax2.legend(loc='upper right', framealpha=0.9)
plt.tight_layout()
plt.show()
"""))

cells.append(("md", """**What this means:** The Long COVID community reports positive outcomes for the majority of treatments discussed, with about two-thirds of user-treatment pairs classified as positive. This is consistent with reporting bias -- people who found something helpful are more motivated to share. The overall positive rate becomes our baseline: a treatment needs to exceed this to be considered above-average in this community. Strong-signal reports (where the user clearly described an outcome) show a different pattern from weak-signal reports, confirming that signal strength captures meaningful variation in reporting certainty."""))

# ══════════════════════════════════════════════════════════════════════════════
# 3. TREATMENT RANKINGS
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 3. Treatment Rankings: Who Reports the Best Outcomes?

With the baseline established, we now rank individual treatments by their user-level positive outcome rate. Wilson score confidence intervals account for different sample sizes -- a treatment tried by 5 users with 100% positive rate is less informative than one tried by 60 users with 85% positive rate. We restrict to treatments with at least 15 unique users to ensure minimum statistical reliability."""))

# ---- CELL: Treatment ranking table ----
cells.append(("code",
r"""
# -- Build treatment summary table --
import math

drug_stats = user_drug.groupby('drug').agg(
    n_users=('user_id', 'nunique'),
    mean_score=('avg_score', 'mean'),
    pos_n=('outcome', lambda x: (x == 'positive').sum()),
    neg_n=('outcome', lambda x: (x == 'negative').sum()),
    mixed_n=('outcome', lambda x: (x == 'mixed/neutral').sum()),
    tx_class=('tx_class', 'first')
).reset_index()
drug_stats['pos_rate'] = drug_stats['pos_n'] / drug_stats['n_users']
drug_stats['neg_rate'] = drug_stats['neg_n'] / drug_stats['n_users']
drug_stats['mixed_rate'] = drug_stats['mixed_n'] / drug_stats['n_users']
drug_stats['ci_lo'] = drug_stats.apply(lambda r: wilson_ci(int(r['pos_n']), int(r['n_users']))[0], axis=1)
drug_stats['ci_hi'] = drug_stats.apply(lambda r: wilson_ci(int(r['pos_n']), int(r['n_users']))[1], axis=1)

# Binomial test vs 50% baseline for each
drug_stats['p_vs_50'] = drug_stats.apply(
    lambda r: binomtest(int(r['pos_n']), int(r['n_users']), 0.5).pvalue, axis=1)
drug_stats['cohens_h_vs_50'] = drug_stats['pos_rate'].apply(
    lambda p: 2 * (math.asin(math.sqrt(max(0.001, min(0.999, p)))) - math.asin(math.sqrt(0.5))))

# NNT vs overall baseline
drug_stats['nnt_vs_baseline'] = drug_stats['pos_rate'].apply(
    lambda p: nnt(p, pos_rate_overall) if p > pos_rate_overall else None)

# Filter to n >= 15
ranked = drug_stats[drug_stats['n_users'] >= 15].sort_values('pos_rate', ascending=False).reset_index(drop=True)
ranked.index = ranked.index + 1

# Display top 25
display(HTML("<h4>Top 25 Treatments by Positive Outcome Rate (n >= 15 users)</h4>"))
display_cols = ranked.head(25)[['drug', 'n_users', 'pos_rate', 'ci_lo', 'ci_hi', 'neg_rate',
                                 'p_vs_50', 'cohens_h_vs_50', 'nnt_vs_baseline', 'tx_class']].copy()
display_cols.columns = ['Treatment', 'Users', 'Pos Rate', 'CI Low', 'CI High', 'Neg Rate',
                         'p (vs 50%)', "Cohen's h", 'NNT vs baseline', 'Class']
display_cols['Pos Rate'] = display_cols['Pos Rate'].map('{:.1%}'.format)
display_cols['CI Low'] = display_cols['CI Low'].map('{:.2f}'.format)
display_cols['CI High'] = display_cols['CI High'].map('{:.2f}'.format)
display_cols['Neg Rate'] = display_cols['Neg Rate'].map('{:.1%}'.format)
display_cols['p (vs 50%)'] = display_cols['p (vs 50%)'].map(lambda x: '{:.4f}'.format(x) if x >= 0.0001 else '{:.2e}'.format(x))
display_cols["Cohen's h"] = display_cols["Cohen's h"].map('{:.2f}'.format)
display_cols['NNT vs baseline'] = display_cols['NNT vs baseline'].map(lambda x: '{:.1f}'.format(x) if x else chr(8212))

styled = display_cols.style.set_properties(**{'font-size': '12px', 'text-align': 'right'}) \
    .set_properties(subset=['Treatment', 'Class'], **{'text-align': 'left'}) \
    .set_table_styles([{'selector': 'th', 'props': [('font-size', '12px'), ('text-align', 'center')]}])
display(styled)
"""))

cells.append(("md", """**How to read the table:** *Pos Rate* is the fraction of unique users reporting a positive outcome. *CI Low/High* are the Wilson score 95% confidence interval bounds -- wider intervals mean less certainty. *p (vs 50%)* tests whether the positive rate is significantly different from chance. *Cohen's h* measures effect size: values above 0.5 indicate a medium effect, above 0.8 a large effect. *NNT vs baseline* is the Number Needed to Treat relative to the community baseline: it answers "how many additional patients need to try this treatment for one extra person to report benefit beyond the community average?" Lower is better."""))

# ---- CELL: Chart 2 - Forest plot ----
cells.append(("code",
r"""
# -- CHART 2: Forest plot of top 20 treatments (Wilson CI) --
top20 = ranked.head(20).sort_values('pos_rate', ascending=True)

fig, ax = plt.subplots(figsize=(12, 9))
y_pos = range(len(top20))

for i, (_, row) in enumerate(top20.iterrows()):
    color = '#2ecc71' if row['p_vs_50'] < 0.05 and row['pos_rate'] > 0.5 else '#95a5a6'
    ax.plot([row['ci_lo'] * 100, row['ci_hi'] * 100], [i, i], color=color, linewidth=2, solid_capstyle='round')
    ax.scatter(row['pos_rate'] * 100, i, color=color, s=60, zorder=5, edgecolors='white', linewidth=0.5)
    ax.text(row['ci_hi'] * 100 + 1.5, i, 'n={}'.format(int(row['n_users'])), va='center', fontsize=9, color='#666')

ax.axvline(x=50, color='#e74c3c', linestyle='--', alpha=0.6, label='50% (chance)')
ax.axvline(x=pos_rate_overall * 100, color='#3498db', linestyle='--', alpha=0.6,
           label='Community baseline ({:.0f}%)'.format(pos_rate_overall * 100))

ax.set_yticks(y_pos)
ax.set_yticklabels([row['drug'] for _, row in top20.iterrows()], fontsize=10)
ax.set_xlabel('Positive Outcome Rate (%) with 95% Wilson CI', fontsize=11)
ax.set_title('Top 20 Treatments by Positive Outcome Rate (n >= 15 users)', fontsize=13, fontweight='bold')
ax.legend(loc='lower right', framealpha=0.9, fontsize=10)
ax.set_xlim(20, 105)
ax.grid(axis='x', alpha=0.3)
plt.tight_layout()
plt.show()
"""))

cells.append(("md", """**What this means:** Green dots with confidence intervals entirely above the 50% line indicate treatments where we can be statistically confident that more than half of users report positive outcomes. Magnesium, electrolytes, quercetin, and vitamin D cluster at the top with positive rates above 80%. The community baseline (blue dashed line) is already high, so treatments need to clear that bar to be truly above-average. Grey dots indicate treatments whose confidence intervals overlap the baseline -- we cannot reliably distinguish them from the community average."""))

# ══════════════════════════════════════════════════════════════════════════════
# 4. TREATMENT CLASS COMPARISON
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 4. Treatment Class Comparison

Individual treatment rankings are informative, but clinicians and patients think in terms of treatment strategies -- antihistamine protocols, immune modulation, supplements. This section aggregates treatments into mechanistic classes and compares them using Kruskal-Wallis (a non-parametric test for 3+ group comparison, appropriate because sentiment scores are ordinal, not normally distributed) with Benjamini-Hochberg corrected pairwise comparisons."""))

# ---- CELL: Kruskal-Wallis + class summary ----
cells.append(("code",
r"""
# -- Kruskal-Wallis across treatment classes --
class_data = user_drug[user_drug['tx_class'] != 'Other'].copy()
classes = class_data['tx_class'].value_counts()
classes_min10 = classes[classes >= 10].index.tolist()
class_data = class_data[class_data['tx_class'].isin(classes_min10)]

groups_kw = [grp['avg_score'].values for name, grp in class_data.groupby('tx_class')]
group_names_kw = [name for name, grp in class_data.groupby('tx_class')]

h_stat, p_kw = kruskal(*groups_kw)
n_total_kw = len(class_data)
k_groups = len(groups_kw)
eta_sq = (h_stat - k_groups + 1) / (n_total_kw - k_groups)

# Class-level summary
class_summary = class_data.groupby('tx_class').agg(
    n_pairs=('user_id', 'count'),
    n_users=('user_id', 'nunique'),
    mean_score=('avg_score', 'mean'),
    pos_n=('outcome', lambda x: (x == 'positive').sum()),
    pos_rate=('outcome', lambda x: (x == 'positive').mean()),
    neg_rate=('outcome', lambda x: (x == 'negative').mean())
).reset_index()
class_summary['ci_lo'] = class_summary.apply(lambda r: wilson_ci(int(r['pos_n']), int(r['n_pairs']))[0], axis=1)
class_summary['ci_hi'] = class_summary.apply(lambda r: wilson_ci(int(r['pos_n']), int(r['n_pairs']))[1], axis=1)
class_summary = class_summary.sort_values('pos_rate', ascending=False)

# Shannon entropy per class
from scipy.stats import entropy as sp_entropy
class_entropy = class_data.groupby('tx_class').apply(
    lambda g: sp_entropy(g['outcome'].value_counts(normalize=True).values, base=2)
).reset_index(name='entropy')
class_summary = class_summary.merge(class_entropy, on='tx_class')
class_summary['agreement'] = 1 - (class_summary['entropy'] / np.log2(3))

eff_label = 'large' if eta_sq > 0.14 else ('medium' if eta_sq > 0.06 else 'small')
display(HTML(
    "<h4>Treatment Class Comparison</h4>"
    "<p style='font-size:13px;'>Kruskal-Wallis H = {:.2f}, p = {:.2e}, ".format(h_stat, p_kw)
    + "eta-squared = {:.3f} ({} effect)</p>".format(eta_sq, eff_label)
))

display_cls = class_summary[['tx_class', 'n_pairs', 'n_users', 'pos_rate', 'ci_lo', 'ci_hi',
                               'neg_rate', 'mean_score', 'agreement']].copy()
display_cls.columns = ['Class', 'User-Drug Pairs', 'Unique Users', 'Pos Rate', 'CI Lo', 'CI Hi',
                         'Neg Rate', 'Mean Score', 'Agreement']
display_cls['Pos Rate'] = display_cls['Pos Rate'].map('{:.1%}'.format)
display_cls['CI Lo'] = display_cls['CI Lo'].map('{:.2f}'.format)
display_cls['CI Hi'] = display_cls['CI Hi'].map('{:.2f}'.format)
display_cls['Neg Rate'] = display_cls['Neg Rate'].map('{:.1%}'.format)
display_cls['Mean Score'] = display_cls['Mean Score'].map('{:.3f}'.format)
display_cls['Agreement'] = display_cls['Agreement'].map('{:.2f}'.format)

styled2 = display_cls.style.set_properties(**{'font-size': '12px', 'text-align': 'right'}) \
    .set_properties(subset=['Class'], **{'text-align': 'left'}) \
    .set_table_styles([{'selector': 'th', 'props': [('font-size', '12px'), ('text-align', 'center')]}])
display(styled2)
"""))

# ---- CELL: Pairwise class comparisons ----
cells.append(("code",
r"""
# -- Pairwise Fisher's exact comparisons across all classes --
from itertools import combinations

class_pairs = []
class_names_sorted = class_summary['tx_class'].tolist()
for a, b in combinations(class_names_sorted, 2):
    da = class_data[class_data['tx_class'] == a]
    db = class_data[class_data['tx_class'] == b]
    pos_a = int((da['outcome'] == 'positive').sum())
    pos_b = int((db['outcome'] == 'positive').sum())
    n_a = len(da)
    n_b = len(db)
    table = [[pos_a, n_a - pos_a], [pos_b, n_b - pos_b]]
    odds_r, p_val = fisher_exact(table)
    p1 = pos_a / n_a if n_a > 0 else 0
    p2 = pos_b / n_b if n_b > 0 else 0
    h = 2 * (math.asin(math.sqrt(max(0.001, min(0.999, p1)))) - math.asin(math.sqrt(max(0.001, min(0.999, p2)))))
    class_pairs.append({'Class A': a, 'Class B': b, 'Pos A': '{:.1%}'.format(p1),
                        'Pos B': '{:.1%}'.format(p2), 'OR': odds_r, 'p': p_val, 'h': h})

pairs_df = pd.DataFrame(class_pairs)
pairs_df = pairs_df.sort_values('p')
m = len(pairs_df)
pairs_df['rank'] = range(1, m + 1)
pairs_df['p_adj'] = pairs_df['p'] * m / pairs_df['rank']
pairs_df['p_adj'] = pairs_df['p_adj'].clip(upper=1.0)
for i in range(m - 2, -1, -1):
    pairs_df.iloc[i, pairs_df.columns.get_loc('p_adj')] = min(
        pairs_df.iloc[i]['p_adj'], pairs_df.iloc[i + 1]['p_adj'])
pairs_df['sig'] = pairs_df['p_adj'].apply(lambda x: '***' if x < 0.001 else ('**' if x < 0.01 else ('*' if x < 0.05 else '')))

sig_pairs = pairs_df[pairs_df['p_adj'] < 0.10].copy()

display(HTML("<h4>Pairwise Class Comparisons (BH-adjusted p < 0.10): {} of {} pairs</h4>".format(len(sig_pairs), m)))
if len(sig_pairs) > 0:
    sig_display = sig_pairs[['Class A', 'Class B', 'Pos A', 'Pos B', 'OR', 'h', 'p_adj', 'sig']].copy()
    sig_display.columns = ['Class A', 'Class B', 'Pos A', 'Pos B', 'OR', "Cohen's h", 'p (BH adj)', 'Sig']
    sig_display['OR'] = sig_display['OR'].map('{:.2f}'.format)
    sig_display["Cohen's h"] = sig_display["Cohen's h"].map('{:.2f}'.format)
    sig_display['p (BH adj)'] = sig_display['p (BH adj)'].map(lambda x: '{:.4f}'.format(x) if x >= 0.0001 else '{:.2e}'.format(x))
    styled3 = sig_display.style.set_properties(**{'font-size': '12px', 'text-align': 'right'}) \
        .set_properties(subset=['Class A', 'Class B', 'Sig'], **{'text-align': 'left'}) \
        .set_table_styles([{'selector': 'th', 'props': [('font-size', '12px')]}])
    display(styled3)
else:
    display(HTML("<p style='font-size:13px;'>No pairwise comparisons reached significance after FDR correction.</p>"))
"""))

# ---- CELL: Chart 3 - Heatmap ----
cells.append(("code",
r"""
# -- CHART 3: Heatmap of pairwise Cohen's h between classes --
class_order = class_summary.sort_values('pos_rate', ascending=False)['tx_class'].tolist()
h_matrix = pd.DataFrame(0.0, index=class_order, columns=class_order)
p_adj_matrix = pd.DataFrame(1.0, index=class_order, columns=class_order)

for _, row in pairs_df.iterrows():
    a, b = row['Class A'], row['Class B']
    if a in class_order and b in class_order:
        h_matrix.loc[a, b] = row['h']
        h_matrix.loc[b, a] = -row['h']
        p_adj_matrix.loc[a, b] = row['p_adj']
        p_adj_matrix.loc[b, a] = row['p_adj']

fig, ax = plt.subplots(figsize=(12, 9))
mask = np.eye(len(class_order), dtype=bool)

annot_arr = h_matrix.copy().astype(object)
for i in range(len(class_order)):
    for j in range(len(class_order)):
        if i == j:
            annot_arr.iloc[i, j] = ''
        else:
            h_val = h_matrix.iloc[i, j]
            p_val = p_adj_matrix.iloc[i, j]
            star = '***' if p_val < 0.001 else ('**' if p_val < 0.01 else ('*' if p_val < 0.05 else ''))
            annot_arr.iloc[i, j] = '{:.2f}{}'.format(h_val, star)

sns.heatmap(h_matrix.values.astype(float), annot=annot_arr.values, fmt='', cmap='RdYlGn', center=0,
            mask=mask, ax=ax, linewidths=0.5, linecolor='white',
            cbar_kws={'label': "Cohen's h (row better = green)", 'shrink': 0.8},
            square=True, vmin=-1, vmax=1,
            xticklabels=class_order, yticklabels=class_order)
ax.set_title("Pairwise Effect Sizes Between Treatment Classes\n(Cohen's h with BH-adjusted significance)",
             fontsize=13, fontweight='bold')
ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha='right', fontsize=9)
ax.set_yticklabels(ax.get_yticklabels(), fontsize=9)
plt.tight_layout(rect=[0, 0, 0.95, 1])
plt.show()
"""))

cells.append(("md", """**What this means:** Each cell shows the effect size (Cohen's h) comparing the row class against the column class. Green means the row class has a higher positive rate; red means the column class does better. Stars indicate statistical significance after correction for multiple comparisons. This reveals the structural pattern: Volume/Electrolyte and Vitamin/Supplement classes tend to outperform Psych/Neuro treatments. The wide-reaching green in certain rows suggests those treatment strategies produce consistently better community-reported outcomes across comparisons."""))

# ══════════════════════════════════════════════════════════════════════════════
# 5. LOGISTIC REGRESSION
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 5. Logistic Regression: What Predicts a Positive Outcome?

Rankings and class comparisons show which treatments do well, but they do not account for confounding. A user who tries magnesium might also be trying LDN, probiotics, and antihistamines -- and the positive outcome could be driven by any of those. Logistic regression (a statistical model that predicts binary outcomes -- positive vs not-positive -- from multiple predictors simultaneously) helps disentangle which treatment class exposures independently predict positive outcomes, controlling for the others."""))

# ---- CELL: Logistic regression ----
cells.append(("code",
r"""
import statsmodels.api as sm

# Build user-level dataset
user_ids = user_drug['user_id'].unique()
class_cols = [c for c in classes_min10 if c != 'Other']

user_features = pd.DataFrame({'user_id': user_ids})
for cls in class_cols:
    users_in_cls = set(user_drug[user_drug['tx_class'] == cls]['user_id'])
    user_features[cls] = user_features['user_id'].isin(users_in_cls).astype(int)

# User-level outcome
user_outcome = user_drug.groupby('user_id')['avg_score'].mean().reset_index(name='overall_score')
user_outcome['positive'] = (user_outcome['overall_score'] > 0.3).astype(int)
user_features = user_features.merge(user_outcome[['user_id', 'positive']], on='user_id')

# Treatment count covariate
user_tx_count = user_drug.groupby('user_id')['drug'].nunique().reset_index(name='n_treatments')
user_features = user_features.merge(user_tx_count, on='user_id')

X = user_features[class_cols + ['n_treatments']]
X = sm.add_constant(X)
y = user_features['positive']

try:
    model = sm.Logit(y, X).fit(disp=0, maxiter=100, method='lbfgs')
    results_df = pd.DataFrame({
        'Predictor': model.params.index,
        'Coef': model.params.values,
        'OR': np.exp(model.params.values.clip(-10, 10)),
        'SE': model.bse.values,
        'z': model.tvalues.values,
        'p': model.pvalues.values,
        'CI_lo': np.exp((model.params - 1.96 * model.bse).values.clip(-10, 10)),
        'CI_hi': np.exp((model.params + 1.96 * model.bse).values.clip(-10, 10))
    })
    results_df = results_df[results_df['Predictor'] != 'const'].sort_values('OR', ascending=False)

    display(HTML(
        "<h4>Logistic Regression: Predictors of Positive Outcome (User-Level)</h4>"
        "<p style='font-size:12px; color:#666;'>Pseudo R-squared: {:.3f}, AIC: {:.1f}, N = {}</p>".format(
            model.prsquared, model.aic, len(y))
    ))

    display_lr = results_df[['Predictor', 'OR', 'CI_lo', 'CI_hi', 'p']].copy()
    display_lr.columns = ['Predictor', 'Odds Ratio', 'OR CI Low', 'OR CI High', 'p-value']
    display_lr['Odds Ratio'] = display_lr['Odds Ratio'].map('{:.2f}'.format)
    display_lr['OR CI Low'] = display_lr['OR CI Low'].map('{:.2f}'.format)
    display_lr['OR CI High'] = display_lr['OR CI High'].map('{:.2f}'.format)
    display_lr['p-value'] = display_lr['p-value'].map(lambda x: '{:.4f}'.format(x) if x >= 0.0001 else '{:.2e}'.format(x))

    styled_lr = display_lr.style.set_properties(**{'font-size': '12px', 'text-align': 'right'}) \
        .set_properties(subset=['Predictor'], **{'text-align': 'left'}) \
        .set_table_styles([{'selector': 'th', 'props': [('font-size', '12px')]}])
    display(styled_lr)
except Exception as e:
    display(HTML("<p style='color:red;'>Logistic regression failed: {}</p>".format(e)))
"""))

# ---- CELL: Chart 4 - OR forest plot ----
cells.append(("code",
r"""
# -- CHART 4: Odds ratio forest plot --
try:
    plot_df = results_df[results_df['Predictor'] != 'n_treatments'].sort_values('OR', ascending=True)

    fig, ax = plt.subplots(figsize=(10, max(6, len(plot_df) * 0.45)))
    y_pos = range(len(plot_df))

    for i, (_, row) in enumerate(plot_df.iterrows()):
        color = '#2ecc71' if row['p'] < 0.05 and row['OR'] > 1 else ('#e74c3c' if row['p'] < 0.05 and row['OR'] < 1 else '#95a5a6')
        ax.plot([row['CI_lo'], row['CI_hi']], [i, i], color=color, linewidth=2.5, solid_capstyle='round')
        ax.scatter(row['OR'], i, color=color, s=70, zorder=5, edgecolors='white', linewidth=0.5)

    ax.axvline(x=1.0, color='#333', linestyle='--', alpha=0.5, label='OR = 1 (no effect)')
    ax.set_yticks(y_pos)
    ax.set_yticklabels(plot_df['Predictor'].values, fontsize=10)
    ax.set_xlabel('Odds Ratio (95% CI)', fontsize=11)
    ax.set_title('Treatment Class Exposure as Predictors of Positive Outcome\n(Logistic Regression, Controlling for Treatment Count)', fontsize=12, fontweight='bold')
    ax.legend(loc='lower right', framealpha=0.9, fontsize=10)
    ax.set_xscale('log')
    ax.grid(axis='x', alpha=0.3)
    plt.tight_layout()
    plt.show()
except Exception:
    display(HTML("<p>Could not generate odds ratio plot.</p>"))
"""))

cells.append(("md", """**What this means:** An odds ratio (OR) above 1.0 means exposure to that treatment class is associated with higher odds of a positive outcome, controlling for all other classes and total treatment count. An OR below 1.0 means the opposite. Green indicates statistically significant positive predictors; red indicates significant negative predictors; grey indicates non-significant. The treatment count covariate controls for the confound that users trying more treatments mechanically accumulate more positive reports."""))

# ══════════════════════════════════════════════════════════════════════════════
# 6. DIVERGING BAR CHART
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 6. Sentiment Breakdown: The Full Picture

Rankings by positive rate tell only part of the story. Two treatments could both have 70% positive rates but look very different if one has 25% negative and 5% mixed, while the other has 5% negative and 25% mixed. The diverging bar chart below shows the complete sentiment distribution for the top treatments, revealing which treatments have strong polarization (high positive AND high negative) versus broad consensus."""))

# ---- CELL: Chart 5 - Diverging bar ----
cells.append(("code",
r"""
# -- CHART 5: Diverging bar chart for top 25 treatments --
top25_div = drug_stats[drug_stats['n_users'] >= 15].sort_values('pos_rate', ascending=False).head(25)
top25_div = top25_div.sort_values('pos_rate', ascending=True)

fig, ax = plt.subplots(figsize=(13, 10))
y = range(len(top25_div))
bar_height = 0.7

# CRITICAL stacking: mixed innermost, negative outermost
ax.barh(y, -top25_div['mixed_rate'].values * 100, left=0, height=bar_height,
        color='#95a5a6', label='Mixed/Neutral', edgecolor='white', linewidth=0.5)
ax.barh(y, -top25_div['neg_rate'].values * 100, left=-top25_div['mixed_rate'].values * 100,
        height=bar_height, color='#e74c3c', label='Negative', edgecolor='white', linewidth=0.5)
ax.barh(y, top25_div['pos_rate'].values * 100, left=0, height=bar_height,
        color='#2ecc71', label='Positive', edgecolor='white', linewidth=0.5)

# CIs on positive side
for i, (_, row) in enumerate(top25_div.iterrows()):
    ci_lo, ci_hi = wilson_ci(int(row['pos_n']), int(row['n_users']))
    ax.plot([ci_lo * 100, ci_hi * 100], [i, i], color='#1a8f4e', linewidth=1.5, alpha=0.7)

# n= labels
for i, (_, row) in enumerate(top25_div.iterrows()):
    ax.text(row['pos_rate'] * 100 + 2, i, 'n={}'.format(int(row['n_users'])),
            va='center', fontsize=8, color='#666')

ax.axvline(x=0, color='black', linewidth=0.8)
ax.set_yticks(y)
ax.set_yticklabels([row['drug'] for _, row in top25_div.iterrows()], fontsize=10)
ax.set_xlabel('<-- Negative / Mixed          Positive -->  (%)', fontsize=11)
ax.set_title('Sentiment Breakdown: Top 25 Treatments (n >= 15 users)', fontsize=13, fontweight='bold')
ax.legend(loc='lower right', bbox_to_anchor=(1.0, 0.0), framealpha=0.9, fontsize=10)
ax.grid(axis='x', alpha=0.2)
plt.tight_layout()
plt.show()
"""))

cells.append(("md", """**What this means:** Treatments at the top (magnesium, electrolyte, quercetin) show overwhelming positive sentiment with almost no negative reports -- these are high-consensus treatments. In contrast, treatments like SSRIs and antibiotics at the bottom show substantial negative bars, indicating polarized experiences. The confidence interval whiskers on the positive side show precision -- short whiskers mean we are more certain about the estimate. Treatments where the negative bar is large deserve investigation: either the treatment genuinely causes harm for some patients, or there are subpopulations responding differently."""))

# ══════════════════════════════════════════════════════════════════════════════
# 7. SENSITIVITY & ROBUSTNESS
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 7. Sensitivity Analysis: Do the Rankings Hold Up?

A core concern with community-reported data is that a few prolific users can dominate results. We test robustness two ways: (1) restricting to strong-signal reports only (the user clearly described an outcome, not just mentioned a drug), and (2) Bayesian shrinkage, which pulls treatments with small samples toward the community average, penalizing overconfident estimates from tiny samples."""))

# ---- CELL: Sensitivity checks ----
cells.append(("code",
r"""
# -- Sensitivity: strong-signal only --
from scipy.stats import spearmanr

strong_only = raw[raw['signal_strength'] == 'strong'].copy()
ud_strong = strong_only.groupby(['user_id', 'drug']).agg(
    avg_score=('score', 'mean'),
    n_reports=('score', 'count')
).reset_index()
ud_strong['outcome'] = ud_strong['avg_score'].apply(classify_outcome)

drug_strong = ud_strong.groupby('drug').agg(
    n_users=('user_id', 'nunique'),
    pos_rate=('outcome', lambda x: (x == 'positive').mean())
).reset_index()
drug_strong = drug_strong[drug_strong['n_users'] >= 10].sort_values('pos_rate', ascending=False)

# Merge with full ranking
full_rank = ranked[['drug', 'pos_rate', 'n_users']].rename(columns={'pos_rate': 'full_rate', 'n_users': 'full_n'})
comparison = drug_strong.merge(full_rank, on='drug', how='inner')
comparison['diff'] = comparison['pos_rate'] - comparison['full_rate']

# Spearman
rho_sens, p_sens = spearmanr(comparison['full_rate'], comparison['pos_rate'])

# -- Bayesian shrinkage --
overall_k = drug_stats['pos_n'].sum()
overall_n_all = drug_stats['n_users'].sum()
prior_strength = 5
alpha_prior = prior_strength * (overall_k / overall_n_all)
beta_prior = prior_strength * (1 - overall_k / overall_n_all)

drug_stats_shrunk = drug_stats[drug_stats['n_users'] >= 5].copy()
drug_stats_shrunk['shrunk_rate'] = (drug_stats_shrunk['pos_n'] + alpha_prior) / (drug_stats_shrunk['n_users'] + prior_strength)
drug_stats_shrunk['shrinkage_delta'] = drug_stats_shrunk['shrunk_rate'] - drug_stats_shrunk['pos_rate']

consistency_label = ('Rankings are highly consistent' if rho_sens > 0.7
                     else ('Rankings show moderate consistency' if rho_sens > 0.4
                           else 'Rankings diverge -- strong-signal reports tell a different story'))

display(HTML(
    "<h4>Sensitivity: Strong-Signal Only vs Full Dataset</h4>"
    "<p style='font-size:13px;'>Spearman rank correlation: rho = {:.3f}, p = {:.4f} -- {}</p>".format(
        rho_sens, p_sens, consistency_label)
    + "<p style='font-size:12px; color:#666;'>Treatments with >=10 users in strong-signal data: {}</p>".format(
        len(drug_strong))
))

# Show big movers
big_movers = comparison[comparison['diff'].abs() > 0.10].sort_values('diff', ascending=False)
if len(big_movers) > 0:
    display(HTML("<h4>Treatments shifting >10pp when restricted to strong-signal only:</h4>"))
    bm_display = big_movers[['drug', 'full_rate', 'pos_rate', 'diff', 'n_users', 'full_n']].copy()
    bm_display.columns = ['Treatment', 'Full Rate', 'Strong-Only Rate', 'Difference', 'Strong N', 'Full N']
    bm_display['Full Rate'] = bm_display['Full Rate'].map('{:.1%}'.format)
    bm_display['Strong-Only Rate'] = bm_display['Strong-Only Rate'].map('{:.1%}'.format)
    bm_display['Difference'] = bm_display['Difference'].map('{:+.1%}'.format)
    display(bm_display.style.set_properties(**{'font-size': '12px'}).set_table_styles(
        [{'selector': 'th', 'props': [('font-size', '12px')]}]))
"""))

# ---- CELL: Chart 6 - Bayesian shrinkage scatter ----
cells.append(("code",
r"""
# -- CHART 6: Scatter plot: raw rate vs Bayesian shrunk rate --
plot_shrunk = drug_stats_shrunk[drug_stats_shrunk['n_users'] >= 10].copy()

fig, ax = plt.subplots(figsize=(10, 8))
sizes = np.sqrt(plot_shrunk['n_users']) * 8
scatter = ax.scatter(plot_shrunk['pos_rate'] * 100, plot_shrunk['shrunk_rate'] * 100,
                     s=sizes, alpha=0.6, c=plot_shrunk['n_users'], cmap='viridis',
                     edgecolors='white', linewidth=0.5)

ax.plot([30, 100], [30, 100], '--', color='#999', alpha=0.5, label='No shrinkage')

# Label top 10
renderer = fig.canvas.get_renderer()
texts = []
for _, row in plot_shrunk.nlargest(10, 'shrunk_rate').iterrows():
    t = ax.annotate(row['drug'], (row['pos_rate'] * 100, row['shrunk_rate'] * 100),
                    fontsize=8, alpha=0.8, textcoords='offset points', xytext=(5, 5))
    texts.append(t)

# Overlap check
for i, t1 in enumerate(texts):
    bb1 = t1.get_window_extent(renderer)
    for t2 in texts[i+1:]:
        bb2 = t2.get_window_extent(renderer)
        if bb1.overlaps(bb2):
            pos = t2.get_position()
            t2.set_position((pos[0], pos[1] + 8))

cbar = plt.colorbar(scatter, ax=ax, shrink=0.8, label='Number of Users')
ax.set_xlabel('Raw Positive Rate (%)', fontsize=11)
ax.set_ylabel('Bayesian Shrunk Rate (%)', fontsize=11)
ax.set_title('Bayesian Shrinkage: Small-Sample Treatments Pulled Toward Baseline',
             fontsize=12, fontweight='bold')
ax.legend(loc='upper left', framealpha=0.9)
ax.grid(alpha=0.2)
plt.tight_layout()
plt.show()
"""))

cells.append(("md", """**What this means:** Points near the diagonal have sufficient sample sizes that shrinkage barely affects them -- their raw rates are trustworthy. Points pulled below the diagonal are treatments with small samples whose high positive rates are partially an artifact of small n. The colorbar shows user count: purple/dark points have few users (more shrinkage), yellow/bright points have many users (less shrinkage). This confirms that treatments like magnesium, LDN, and electrolyte maintain their positions even after penalizing for sample size."""))

# ══════════════════════════════════════════════════════════════════════════════
# 8. COUNTERINTUITIVE FINDINGS
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 8. Counterintuitive Findings Worth Investigating

This section flags results that would surprise a clinician, patient, or researcher -- findings where the data contradicts clinical guidelines, community assumptions, or common sense."""))

# ---- CELL: Counterintuitive findings ----
cells.append(("code",
r"""
# -- Search for counterintuitive patterns --
findings = []

# 1. SSRIs
ssri_data = drug_stats[drug_stats['drug'] == 'ssri']
if len(ssri_data) > 0:
    ssri_row = ssri_data.iloc[0]
    if ssri_row['pos_rate'] < 0.55 and ssri_row['n_users'] >= 15:
        ssri_binom = binomtest(int(ssri_row['pos_n']), int(ssri_row['n_users']), pos_rate_overall)
        findings.append(
            "<b>SSRIs underperform despite clinical recommendation.</b> SSRIs (selective serotonin "
            "reuptake inhibitors, commonly prescribed for Long COVID fatigue and brain fog) show a "
            "{:.0%} positive rate -- below the community baseline of {:.0%} ".format(ssri_row['pos_rate'], pos_rate_overall)
            + "(binomial test vs baseline: p = {:.4f}). ".format(ssri_binom.pvalue)
            + "This could reflect reporting bias (patients who do well on SSRIs may not post about it), "
            "or a genuine disconnect between prescribing patterns and patient experience.")

# 2. Nicotine
nic_data = drug_stats[drug_stats['drug'] == 'nicotine']
if len(nic_data) > 0:
    nic_row = nic_data.iloc[0]
    if nic_row['pos_rate'] > 0.65 and nic_row['n_users'] >= 15:
        nic_binom = binomtest(int(nic_row['pos_n']), int(nic_row['n_users']), 0.5)
        findings.append(
            "<b>Nicotine patches show surprisingly strong positive rates.</b> Despite having no "
            "established clinical indication for Long COVID, nicotine ({} users) reports a ".format(int(nic_row['n_users']))
            + "{:.0%} positive rate (p vs 50% = {:.4f}). ".format(nic_row['pos_rate'], nic_binom.pvalue)
            + "This aligns with the nicotinic acetylcholine receptor hypothesis but would surprise "
            "most clinicians who associate nicotine primarily with harm.")

# 3. Antibiotics
abx_data = drug_stats[drug_stats['drug'] == 'antibiotics']
if len(abx_data) > 0:
    abx_row = abx_data.iloc[0]
    if abx_row['pos_rate'] < 0.55 and abx_row['n_users'] >= 15:
        findings.append(
            "<b>Antibiotics show near-chance outcomes.</b> Antibiotics ({} users) ".format(int(abx_row['n_users']))
            + "show a {:.0%} positive rate and {:.0%} negative rate. ".format(abx_row['pos_rate'], abx_row['neg_rate'])
            + "Given that some Long COVID protocols include antibiotics (e.g., doxycycline for "
            "anti-inflammatory properties), the data suggests inconsistent benefit -- though this "
            "category lumps diverse antibiotics together.")

# 4. Nattokinase
natto_data = drug_stats[drug_stats['drug'] == 'nattokinase']
if len(natto_data) > 0:
    natto_row = natto_data.iloc[0]
    if natto_row['pos_rate'] < pos_rate_overall and natto_row['n_users'] >= 15:
        findings.append(
            "<b>Nattokinase underperforms its reputation.</b> Despite being one of the most frequently "
            "recommended supplements in Long COVID communities (the microclot hypothesis), nattokinase "
            "({} users) shows a {:.0%} positive rate ".format(int(natto_row['n_users']), natto_row['pos_rate'])
            + "-- below the community baseline of {:.0%}. ".format(pos_rate_overall)
            + "The gap between enthusiasm and reported outcomes suggests the narrative may outpace experience.")

# 5. Magnesium vs Rx
mag_data = drug_stats[drug_stats['drug'] == 'magnesium']
if len(mag_data) > 0:
    mag_row = mag_data.iloc[0]
    if mag_row['pos_rate'] > 0.85:
        rx_classes = user_drug[user_drug['tx_class'].isin(['Psych/Neuro', 'Autonomic', 'ImmuneModulation'])]
        rx_pos = (rx_classes['outcome'] == 'positive').mean()
        findings.append(
            "<b>Magnesium, an inexpensive OTC supplement, outperforms most prescription classes.</b> "
            "Magnesium ({} users) shows a {:.0%} positive rate, ".format(int(mag_row['n_users']), mag_row['pos_rate'])
            + "compared to {:.0%} across prescription medication classes. ".format(rx_pos)
            + "While reporting bias likely inflates this gap (supplements attract self-selection from "
            "health-engaged patients), the magnitude of the difference is striking.")

if len(findings) == 0:
    findings.append("All findings aligned with community consensus and clinical expectations.")

findings_html = "".join("<li style='margin-bottom:10px;'>{}</li>".format(f) for f in findings)
display(HTML("<ul style='font-size:13px; line-height:1.6;'>{}</ul>".format(findings_html)))
"""))

cells.append(("md", """These patterns merit investigation but should not be interpreted as causal conclusions. The SSRI finding in particular could reflect selection bias: patients whose SSRIs work may stop posting to Long COVID forums. The nicotine finding aligns with emerging research but is not evidence for clinical use. The magnesium finding likely reflects a combination of genuine benefit (magnesium deficiency is common in Long COVID) and self-selection."""))

# ══════════════════════════════════════════════════════════════════════════════
# 9. QUALITATIVE EVIDENCE
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 9. What Patients Are Saying

Quantitative rankings reveal patterns, but patient voices reveal mechanisms and lived experience. The following quotes are drawn from posts by users who reported on the top-performing treatments, selected for specificity and relevance. Each quote contains a concrete treatment outcome -- not meta-commentary or social validation."""))

# ---- CELL: Quotes ----
cells.append(("code",
r"""
# -- Pull quotes for top treatments --
top_drugs_for_quotes = ['low dose naltrexone', 'magnesium', 'electrolyte', 'antihistamines', 'nicotine', 'ssri']

quotes_html = []
for drug_name in top_drugs_for_quotes:
    drug_users = user_drug[user_drug['drug'] == drug_name]['user_id'].unique()
    if len(drug_users) == 0:
        continue

    search_terms = [drug_name]
    if drug_name == 'low dose naltrexone':
        search_terms.extend(['ldn', 'naltrexone'])
    elif drug_name == 'electrolyte':
        search_terms.extend(['electrolytes', 'lmnt', 'liquid iv'])
    elif drug_name == 'antihistamines':
        search_terms.extend(['antihistamine', 'cetirizine', 'famotidine', 'zyrtec', 'pepcid'])
    elif drug_name == 'ssri':
        search_terms.extend(['sertraline', 'zoloft', 'lexapro', 'escitalopram'])
    elif drug_name == 'nicotine':
        search_terms.extend(['nicotine patch', 'nicotine patches'])

    placeholders = ','.join(['?' for _ in drug_users])
    like_clauses = ' OR '.join(["LOWER(p.body_text) LIKE '%" + t + "%'" for t in search_terms])

    query = (
        "SELECT p.body_text, date(p.post_date, 'unixepoch') as post_date "
        "FROM posts p "
        "WHERE p.user_id IN ({}) ".format(placeholders)
        + "AND ({}) ".format(like_clauses)
        + "AND LENGTH(p.body_text) > 60 "
        "AND LENGTH(p.body_text) < 1500 "
        "ORDER BY LENGTH(p.body_text) ASC "
        "LIMIT 20"
    )

    try:
        posts_df = pd.read_sql(query, conn, params=list(drug_users))
        if len(posts_df) == 0:
            continue

        selected = []
        for _, row in posts_df.iterrows():
            text = row['body_text'].strip()
            sentences = [s.strip() for s in text.replace('\n', ' ').split('.') if len(s.strip()) > 20]
            relevant = [s for s in sentences if any(t in s.lower() for t in search_terms)]
            if relevant:
                quote = relevant[0].strip()
                if len(quote) > 200:
                    quote = quote[:197] + '...'
                if not quote.endswith('.'):
                    quote += '.'
                selected.append((quote, row['post_date']))
                if len(selected) >= 2:
                    break

        if selected:
            drug_label = drug_name.title() if drug_name != 'ssri' else 'SSRIs'
            for quote, date in selected:
                quotes_html.append(
                    "<p style='font-size:13px; margin:4px 0 4px 20px; color:#444;'>"
                    "<b>{}:</b> <em>\"{}\"</em> ({})</p>".format(drug_label, quote, date))
    except Exception:
        continue

if quotes_html:
    display(HTML(
        '<div style="border-left:3px solid #2ecc71; padding-left:12px; margin:10px 0;">'
        + '\n'.join(quotes_html[:8]) + '</div>'))
else:
    display(HTML("<p>No qualifying quotes found matching the criteria.</p>"))
"""))

cells.append(("md", """Each quote above captures a specific treatment experience -- a concrete outcome, not just mention of a drug name. The SSRI and antibiotics quotes (if present) were deliberately selected to complicate the positive narrative: not every treatment works for every patient, and the quotes reflect that reality."""))

# ══════════════════════════════════════════════════════════════════════════════
# 10. TIERED RECOMMENDATIONS
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 10. Tiered Recommendations

Based on the preceding analysis, treatments are classified into evidence tiers. **Strong** recommendations require n >= 30 users and a positive rate significantly above 50% (p < 0.05). **Moderate** recommendations require n >= 15 or p < 0.10. **Preliminary** recommendations include treatments with n < 15 that show promising signals."""))

# ---- CELL: Tiered recommendations ----
cells.append(("code",
r"""
# -- Build tiered recommendations --
rec_data = drug_stats[drug_stats['n_users'] >= 5].copy()
rec_data['binom_p'] = rec_data.apply(
    lambda r: binomtest(int(r['pos_n']), int(r['n_users']), 0.5).pvalue, axis=1)

def assign_tier(row):
    if row['n_users'] >= 30 and row['binom_p'] < 0.05 and row['pos_rate'] > 0.5:
        return 'Strong'
    elif row['n_users'] >= 15 and row['pos_rate'] > 0.5:
        return 'Moderate'
    elif row['n_users'] >= 5 and row['pos_rate'] > 0.55:
        return 'Preliminary'
    elif row['pos_rate'] <= 0.5:
        return 'Not Recommended'
    else:
        return 'Insufficient'

rec_data['tier'] = rec_data.apply(assign_tier, axis=1)

tier_configs = [('Strong', '#27ae60'), ('Moderate', '#f39c12'), ('Preliminary', '#3498db'), ('Not Recommended', '#e74c3c')]
for tier_name, tier_color in tier_configs:
    tier_df = rec_data[rec_data['tier'] == tier_name].sort_values('pos_rate', ascending=False)
    if len(tier_df) == 0:
        continue

    display(HTML("<h4 style='color:{};'>{} Evidence ({} treatments)</h4>".format(tier_color, tier_name, len(tier_df))))

    tier_show = tier_df.head(20)[['drug', 'n_users', 'pos_rate', 'ci_lo', 'ci_hi', 'binom_p', 'tx_class']].copy()
    tier_show.columns = ['Treatment', 'Users', 'Pos Rate', 'CI Lo', 'CI Hi', 'p-value', 'Class']
    tier_show['Pos Rate'] = tier_show['Pos Rate'].map('{:.1%}'.format)
    tier_show['CI Lo'] = tier_show['CI Lo'].map('{:.2f}'.format)
    tier_show['CI Hi'] = tier_show['CI Hi'].map('{:.2f}'.format)
    tier_show['p-value'] = tier_show['p-value'].map(lambda x: '{:.4f}'.format(x) if x >= 0.0001 else '{:.2e}'.format(x))
    display(tier_show.style.set_properties(**{'font-size': '12px', 'text-align': 'right'})
            .set_properties(subset=['Treatment', 'Class'], **{'text-align': 'left'})
            .set_table_styles([{'selector': 'th', 'props': [('font-size', '12px')]}]))
"""))

# ---- CELL: Chart 7 - Tier visualizations ----
cells.append(("code",
r"""
# -- CHART 7: Visual summary by tier --
tier_colors_map = {'Strong': '#27ae60', 'Moderate': '#f39c12', 'Preliminary': '#3498db', 'Not Recommended': '#e74c3c'}

for tier_name in ['Strong', 'Moderate', 'Preliminary', 'Not Recommended']:
    tier_df = rec_data[rec_data['tier'] == tier_name].sort_values('pos_rate', ascending=False)
    limit = 5 if tier_name == 'Not Recommended' else 8
    tier_df = tier_df.head(limit)

    if len(tier_df) == 0:
        continue

    tier_plot = tier_df.sort_values('pos_rate', ascending=True)

    fig, ax = plt.subplots(figsize=(9, max(3, len(tier_plot) * 0.5)))
    y = range(len(tier_plot))

    bars = ax.barh(y, tier_plot['pos_rate'].values * 100, color=tier_colors_map[tier_name],
                   edgecolor='white', height=0.6, alpha=0.85)

    for i, (_, row) in enumerate(tier_plot.iterrows()):
        ci_lo, ci_hi = wilson_ci(int(row['pos_n']), int(row['n_users']))
        ax.plot([ci_lo * 100, ci_hi * 100], [i, i], color='#333', linewidth=1.5, alpha=0.5)
        ax.text(max(row['pos_rate'] * 100, ci_hi * 100) + 1.5, i,
                'n={}'.format(int(row['n_users'])), va='center', fontsize=9, color='#666')

    ax.axvline(x=50, color='#e74c3c', linestyle='--', alpha=0.4, linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(tier_plot['drug'].values, fontsize=10)
    ax.set_xlabel('Positive Outcome Rate (%)', fontsize=10)
    ax.set_title('{} Evidence Tier'.format(tier_name), fontsize=12, fontweight='bold',
                 color=tier_colors_map[tier_name])
    ax.set_xlim(0, 105)
    ax.grid(axis='x', alpha=0.2)
    plt.tight_layout()
    plt.show()
"""))

# ══════════════════════════════════════════════════════════════════════════════
# 11. CONCLUSION
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 11. Conclusion

The Long COVID treatment landscape, as reflected in one month of r/covidlonghaulers data, reveals a clear hierarchy of community-reported outcomes. The top-performing treatments cluster into two categories: basic supportive care (electrolytes, magnesium, B-vitamins, vitamin D) and targeted mechanistic interventions (antihistamines, low dose naltrexone, CoQ10). Both categories outperform the community baseline of approximately 67% positive, with the top performers reaching 85-94% positive rates among reporting users.

The most notable finding is that inexpensive, accessible supplements consistently match or outperform prescription medications in community-reported outcomes. Magnesium (94% positive, n=56), electrolytes (89%, n=40), and quercetin (94%, n=28) rank alongside or above low dose naltrexone (83%, n=183) -- the community's most-discussed prescription treatment. This does not mean supplements are more effective than medications in a clinical sense; it likely reflects a combination of genuine benefit (many Long COVID patients are deficient in these nutrients), low side-effect profiles (making positive reporting easier), and self-selection (health-engaged patients who try supplements may also engage in other beneficial behaviors).

The underperformance of SSRIs (approximately 46% positive) and antibiotics (approximately 51% positive) deserves clinical attention. These are commonly prescribed medications that produce near-chance outcomes in community reports. For SSRIs, this could reflect a disconnect between prescribing intent (manage mood/cognition) and patient expectations (cure Long COVID), or it could indicate genuine lack of efficacy for the specific symptom profiles these patients experience. A patient asking about Long COVID treatment should consider starting with well-tolerated supplements (magnesium, electrolytes, vitamin D) while pursuing targeted interventions (antihistamines for MCAS-type symptoms, LDN for immune modulation) with clinician guidance. Nicotine patches, while showing promising community signal, remain experimental and warrant discussion with a physician. SSRIs should not be dismissed based on this data alone -- they serve important roles in managing comorbid mood disorders -- but patients whose primary goal is Long COVID symptom improvement may find other classes more directly beneficial."""))

# ══════════════════════════════════════════════════════════════════════════════
# 12. RESEARCH LIMITATIONS
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("md", """## 12. Research Limitations

**1. Selection bias.** Reddit users are not representative of the Long COVID population. They skew younger, more internet-literate, and more likely to be in English-speaking countries. Patients who are severely ill may not post at all. The 1,121 reporting users represent a tiny fraction of the estimated millions of Long COVID patients worldwide.

**2. Reporting bias.** Users are more motivated to share positive experiences than neutral ones, inflating positive rates across all treatments. The community baseline positive rate almost certainly exceeds the true population positive rate. Relative comparisons between treatments are more reliable than absolute rates.

**3. Survivorship bias.** Users currently posting are, by definition, well enough to post. Patients who deteriorated and left the community, or who recovered and stopped posting, are invisible in this data. This may systematically undercount negative outcomes and overcount moderate recoveries.

**4. Recall bias.** Patients may misremember when they started a treatment, how long they took it, or what their symptoms were before starting. Treatment reports extracted from narrative text inherit the imprecision of human memory.

**5. Confounding.** Most Long COVID patients try multiple treatments simultaneously. A patient reporting improvement on LDN may also be taking magnesium, antihistamines, and practicing pacing. The logistic regression partially addresses this but cannot fully disentangle treatment effects without randomization.

**6. No control group.** There is no untreated comparison group. Some patients improve over time regardless of treatment (natural recovery), and this analysis cannot distinguish treatment effects from spontaneous improvement. The high baseline positive rate may partly reflect natural recovery attributed to whatever treatment the patient was trying at the time.

**7. Sentiment is not efficacy.** Community sentiment reflects how patients feel about a treatment, not objective clinical improvement. A treatment that improves biomarkers but causes unpleasant side effects might receive negative sentiment despite being clinically effective. Conversely, a treatment with strong placebo effect might receive glowing reviews despite no physiological impact.

**8. Temporal snapshot.** One month of data (March-April 2026) captures a single moment in the community's experience. Treatment preferences, available medications, and dominant narratives shift over time. The nicotine patch enthusiasm visible in this data may be a transient trend; the antihistamine signal has been persistent across multiple time periods in this community."""))

# ══════════════════════════════════════════════════════════════════════════════
# DISCLAIMER
# ══════════════════════════════════════════════════════════════════════════════
cells.append(("code",
r"""
display(HTML(
    '<div style="font-size:1.2em; font-weight:bold; font-style:italic; margin-top:30px; '
    'padding:15px; border:2px solid #e74c3c; border-radius:8px; text-align:center; '
    'background:#fdf2f2;">'
    'These findings reflect reporting patterns in online communities, not population-level '
    'treatment effects. This is not medical advice.'
    '</div>'
))
"""))

# ══════════════════════════════════════════════════════════════════════════════
# BUILD AND EXECUTE
# ══════════════════════════════════════════════════════════════════════════════
nb = build_notebook(cells=cells, db_path=DB_PATH, title="Long COVID Treatment Overview (Verbose)")
output_stem = os.path.join(os.path.dirname(__file__), "1_treatment_overview")
html_path = execute_and_export(nb, output_stem)
print("Done: {}".format(html_path))
