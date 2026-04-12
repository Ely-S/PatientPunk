"""Build Notebook 3: POTS Treatment Strategy — Optimal Combinations."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from build_notebook import build_notebook, execute_and_export

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "polina_onemonth.db"))

cells = []

# ── Research Question ──
cells.append(("md", '**Research Question:** "Notebook 2 found that POTS patients try twice as many treatments but report worse outcomes — yet those on 3+ treatments do dramatically better than monotherapy. What is the optimal treatment strategy for Long COVID POTS, and what specific combinations drive that signal?"'))

# ── Abstract ──
cells.append(("md", """## Abstract

Postural Orthostatic Tachycardia Syndrome (POTS) -- a form of dysautonomia characterized by excessive heart rate increase upon standing -- is one of the most discussed comorbidities in the Long COVID community. This analysis follows up on Notebook 2's preliminary POTS findings by investigating the paradox at the heart of POTS treatment: POTS patients try far more treatments than the broader community and report worse outcomes overall, yet users on 3+ treatments report dramatically higher positive outcome rates (67%) than monotherapy users (29%). Using 49 POTS-identified users with treatment reports from r/covidlonghaulers (March--April 2026), we decompose this paradox through treatment-count dose-response modeling, treatment class co-occurrence analysis, logistic regression with treatment-class predictors, and pairwise combination scoring. The data suggest that multi-mechanistic regimens combining autonomic support (electrolytes, magnesium, beta blockers/ivabradine), immune modulation (antihistamines, LDN, mast cell stabilizers), and mitochondrial/anti-inflammatory supplements (CoQ10, NAC, quercetin) drive the positive signal -- and that the 3-5 treatment sweet spot outperforms both monotherapy and aggressive polypharmacy (6+)."""))

# ── 1. Data Exploration ──
cells.append(("md", """## 1. Data Exploration and Cohort Definition

Data covers: **2026-03-11 to 2026-04-10** (1 month), sourced from r/covidlonghaulers.

Notebook 2 established the POTS cohort: 80 users identified via condition extraction, of whom 49 have treatment reports (816 total reports across 251 unique treatments after filtering generics and causal-context exclusions). This notebook focuses exclusively on those 49 treatment-reporting POTS users.

**Filtering applied:**
- Generic terms removed: supplements, medication, treatment, therapy, drug, vitamin, prescription, pill, dosage, dose
- Causal-context exclusions: all vaccine entries (covid vaccine, pfizer, moderna, booster, etc.) -- these reflect perceived causation, not treatment response
- Duplicate canonicals merged where detected (e.g., hbot/hyperbaric oxygen therapy, weed/cannabis)"""))

# ── Setup code cell ──
setup_code = r'''
# ── POTS cohort identification ──
pots_ids = set(pd.read_sql("""
    SELECT DISTINCT user_id FROM conditions
    WHERE LOWER(condition_name) LIKE '%pots%'
    OR LOWER(condition_name) LIKE '%postural%tachycardia%'
""", conn)['user_id'])

CAUSAL_EXCLUSIONS = {'covid vaccine', 'flu vaccine', 'mmr vaccine', 'moderna vaccine',
                     'mrna covid-19 vaccine', 'pfizer vaccine', 'vaccine', 'vaccine injection',
                     'pfizer', 'booster', 'biontech', 'tdap', 'live vaccine'}

EXCL_ALL = GENERIC_TERMS | CAUSAL_EXCLUSIONS

# Duplicate canonical merges
MERGE_MAP = {
    'hyperbaric oxygen therapy': 'hbot',
    'weed': 'cannabis',
    'selective serotonin reuptake inhibitor': 'ssri',
    'coenzyme q10': 'coq10',
    'pepcid': 'famotidine',
    'naltrexone': 'low dose naltrexone',
    'lorazepam': 'benzodiazepine',
    'ativan': 'benzodiazepine',
    'diazepam': 'benzodiazepine',
    'valium': 'benzodiazepine',
    'xanax': 'benzodiazepine',
    'alprazolam': 'benzodiazepine',
    'benzo': 'benzodiazepine',
    'cymbalta': 'duloxetine',
    'wellbutrin': 'bupropion',
    'lyrica': 'pregabalin',
    'd3': 'vitamin d3',
    'sea salt': 'salt',
    'electrolytes powder': 'electrolyte',
    'gatorade': 'electrolyte',
    'red bull': 'electrolyte',
    'magnesium citrate': 'magnesium',
    'magnesium glycinate': 'magnesium',
    'magnesium oil': 'magnesium',
    'low dose propranolol': 'propranolol',
    'metoprolol': 'beta blocker',
    'ivm': 'ivermectin',
    'epsom salts': 'magnesium',
    'vitamin b12': 'b12',
}

# Treatment class assignment for POTS-relevant treatments
TX_CLASS = {
    # Autonomic / cardiovascular
    'beta blocker': 'Autonomic', 'propranolol': 'Autonomic', 'ivabradine': 'Autonomic',
    'midodrine': 'Autonomic', 'clonidine': 'Autonomic', 'guanfacine': 'Autonomic',
    'pyridostigmine': 'Autonomic', 'methyldopa': 'Autonomic',
    # Electrolyte / volume
    'electrolyte': 'Volume/Electrolyte', 'salt': 'Volume/Electrolyte',
    'magnesium': 'Volume/Electrolyte', 'potassium': 'Volume/Electrolyte',
    'iron supplement': 'Volume/Electrolyte', 'iron': 'Volume/Electrolyte',
    'iron infusion': 'Volume/Electrolyte',
    # Antihistamine / mast cell
    'antihistamines': 'Antihistamine/MastCell', 'ketotifen': 'Antihistamine/MastCell',
    'famotidine': 'Antihistamine/MastCell', 'cetirizine': 'Antihistamine/MastCell',
    'fexofenadine': 'Antihistamine/MastCell', 'loratadine': 'Antihistamine/MastCell',
    'desloratadine': 'Antihistamine/MastCell', 'hydroxyzine': 'Antihistamine/MastCell',
    'h1 antihistamine': 'Antihistamine/MastCell', 'h2 antihistamine': 'Antihistamine/MastCell',
    'cromolyn sodium': 'Antihistamine/MastCell', 'dao': 'Antihistamine/MastCell',
    'mast cell stabilizer': 'Antihistamine/MastCell', 'promethazine': 'Antihistamine/MastCell',
    'azelastine': 'Antihistamine/MastCell', 'diphenhydramine': 'Antihistamine/MastCell',
    'quercetin': 'Antihistamine/MastCell', 'luteolin': 'Antihistamine/MastCell',
    'liposomal luteolin': 'Antihistamine/MastCell',
    # Immune modulation
    'low dose naltrexone': 'ImmuneModulation', 'fluvoxamine': 'ImmuneModulation',
    'rapamycin': 'ImmuneModulation', 'immunoadsorption': 'ImmuneModulation',
    'plasmapheresis': 'ImmuneModulation', 'ivermectin': 'ImmuneModulation',
    'paxlovid': 'ImmuneModulation', 'stellate ganglion block': 'ImmuneModulation',
    'methylene blue': 'ImmuneModulation',
    # Mitochondrial / antioxidant
    'coq10': 'Mito/Antioxidant', 'n-acetylcysteine': 'Mito/Antioxidant',
    'glutathione': 'Mito/Antioxidant', 'pqq': 'Mito/Antioxidant',
    'mitochondrial support': 'Mito/Antioxidant', 'mitoq': 'Mito/Antioxidant',
    'alpha-lipoic acid': 'Mito/Antioxidant', 'ala': 'Mito/Antioxidant',
    'resveratrol': 'Mito/Antioxidant', 'acetyl-L-carnitine': 'Mito/Antioxidant',
    'creatine': 'Mito/Antioxidant', 'ss31': 'Mito/Antioxidant',
    'superoxide dismutase': 'Mito/Antioxidant', 'astaxanthin': 'Mito/Antioxidant',
    # Vitamins / basic supplements
    'vitamin d': 'Vitamin/Supplement', 'vitamin d3': 'Vitamin/Supplement',
    'vitamin c': 'Vitamin/Supplement', 'buffered vitamin c': 'Vitamin/Supplement',
    'b12': 'Vitamin/Supplement', 'b1': 'Vitamin/Supplement',
    'vitamin b1': 'Vitamin/Supplement', 'vitamin b2': 'Vitamin/Supplement',
    'b vitamins': 'Vitamin/Supplement', 'vitamin b complex': 'Vitamin/Supplement',
    'vitamin e': 'Vitamin/Supplement', 'vitamin k2': 'Vitamin/Supplement',
    'k2': 'Vitamin/Supplement', 'biotin': 'Vitamin/Supplement',
    'zinc': 'Vitamin/Supplement', 'multivitamin': 'Vitamin/Supplement',
    'omega-3': 'Vitamin/Supplement', 'fish oil': 'Vitamin/Supplement',
    'dha': 'Vitamin/Supplement', 'benfotiamine': 'Vitamin/Supplement',
    # GI / Gut
    'probiotics': 'GI/Gut', 'glutamine': 'GI/Gut', 'l-glutamine': 'GI/Gut',
    'berberine': 'GI/Gut', 'lactoferrin': 'GI/Gut',
    # Anti-inflammatory / fibrinolytic
    'nattokinase': 'Fibrinolytic', 'lumbrokinase': 'Fibrinolytic',
    'aspirin': 'Anti-inflammatory', 'ibuprofen': 'Anti-inflammatory',
    'nsaids': 'Anti-inflammatory', 'bromelain': 'Anti-inflammatory',
    'pycnogenol': 'Anti-inflammatory', 'steroids': 'Anti-inflammatory',
    'corticosteroid': 'Anti-inflammatory', 'prednisolone': 'Anti-inflammatory',
    'palmitoylethanolamide': 'Anti-inflammatory',
    'micronized palmitoylethanolamide': 'Anti-inflammatory',
    # Psych / neuro
    'ssri': 'Psych/Neuro', 'escitalopram': 'Psych/Neuro', 'sertraline': 'Psych/Neuro',
    'fluoxetine': 'Psych/Neuro', 'duloxetine': 'Psych/Neuro',
    'mirtazapine': 'Psych/Neuro', 'bupropion': 'Psych/Neuro',
    'antidepressants': 'Psych/Neuro', 'trazodone': 'Psych/Neuro',
    'benzodiazepine': 'Psych/Neuro', 'gabapentin': 'Psych/Neuro',
    'pregabalin': 'Psych/Neuro', 'nortriptyline': 'Psych/Neuro',
    'mental health meds': 'Psych/Neuro', 'psychiatric medications': 'Psych/Neuro',
    'quetiapine': 'Psych/Neuro', 'modafinil': 'Psych/Neuro',
    'Adderall': 'Psych/Neuro', 'stimulants': 'Psych/Neuro',
    'doxepin': 'Psych/Neuro', 'cognitive behavioral therapy': 'Psych/Neuro',
    'auvelity': 'Psych/Neuro',
    # Nicotine / novel
    'nicotine': 'Novel/Experimental', 'glp-1 receptor agonist': 'Novel/Experimental',
    'tirzepatide': 'Novel/Experimental', 'mounjaro': 'Novel/Experimental',
    'zepbound': 'Novel/Experimental', 'tadalafil': 'Novel/Experimental',
    'nitric oxide': 'Novel/Experimental', 'ghk-cu peptide': 'Novel/Experimental',
    'kpv': 'Novel/Experimental', 'ta-1': 'Novel/Experimental',
    'peptide': 'Novel/Experimental',
    # Sleep
    'melatonin': 'Sleep', 'daridorexant': 'Sleep', 'sedative': 'Sleep',
    # Physical / device
    'red light therapy': 'Physical/Device', 'hbot': 'Physical/Device',
    'infrared sauna': 'Physical/Device', 'pemf': 'Physical/Device',
    'vielight': 'Physical/Device', 'nir': 'Physical/Device',
    'vagus nerve stimulation': 'Physical/Device',
    'truvaga vagus nerve stimulator': 'Physical/Device',
    'cpap': 'Physical/Device', 'apap machine': 'Physical/Device',
    'cannabis': 'Cannabis', 'cbd': 'Cannabis',
}

# ── Load all POTS treatment reports ──
pots_raw = pd.read_sql("""
    SELECT c.user_id, t.canonical_name as drug, tr.sentiment,
           CASE tr.sentiment WHEN 'positive' THEN 1.0 WHEN 'mixed' THEN 0.5
                WHEN 'neutral' THEN 0.0 WHEN 'negative' THEN -1.0 ELSE 0.0 END as score,
           tr.signal_strength
    FROM conditions c
    JOIN treatment_reports tr ON c.user_id = tr.user_id
    JOIN treatment t ON tr.drug_id = t.id
    WHERE (LOWER(c.condition_name) LIKE '%pots%' OR LOWER(c.condition_name) LIKE '%postural%tachycardia%')
""", conn)

# Filter exclusions
pots_raw = pots_raw[~pots_raw['drug'].str.lower().isin([x.lower() for x in EXCL_ALL])]

# Apply merges
pots_raw['drug'] = pots_raw['drug'].map(lambda x: MERGE_MAP.get(x, x))

# Assign treatment classes
pots_raw['tx_class'] = pots_raw['drug'].map(TX_CLASS).fillna('Other')

# User-drug level aggregation
user_drug = pots_raw.groupby(['user_id', 'drug']).agg(
    avg_score=('score', 'mean'),
    n_reports=('score', 'count'),
    tx_class=('tx_class', 'first')
).reset_index()

# Treatment count per user
user_tx_count = user_drug.groupby('user_id')['drug'].nunique().reset_index(name='n_treatments')
user_class_count = user_drug.groupby('user_id')['tx_class'].nunique().reset_index(name='n_classes')

# User-level overall score
user_overall = user_drug.groupby('user_id')['avg_score'].mean().reset_index(name='overall_score')
user_scores = user_tx_count.merge(user_class_count, on='user_id').merge(user_overall, on='user_id')

# Define positive outcome at user level
user_scores['positive'] = (user_scores['overall_score'] > 0.3).astype(int)

# Define treatment tiers
user_scores['tier'] = pd.cut(user_scores['n_treatments'], bins=[0, 1, 2, 5, 100],
                              labels=['Mono (1)', 'Duo (2)', '3-5', '6+'], ordered=True)

n_users = len(user_scores)
n_reports = len(pots_raw)
n_unique_tx = user_drug['drug'].nunique()
n_classes = user_drug['tx_class'].nunique()
med_tx = user_scores['n_treatments'].median()
med_cl = user_scores['n_classes'].median()

html_table = (
    "<table style='border-collapse:collapse; font-size:14px;'>"
    "<tr><th style='text-align:left; padding:4px 12px; border-bottom:2px solid #333;'>Metric</th>"
    "    <th style='text-align:right; padding:4px 12px; border-bottom:2px solid #333;'>Value</th></tr>"
    f"<tr><td style='padding:4px 12px;'>POTS users with treatment reports</td><td style='text-align:right; padding:4px 12px;'>{n_users}</td></tr>"
    f"<tr><td style='padding:4px 12px;'>Total treatment reports (filtered)</td><td style='text-align:right; padding:4px 12px;'>{n_reports}</td></tr>"
    f"<tr><td style='padding:4px 12px;'>Unique treatments after merging</td><td style='text-align:right; padding:4px 12px;'>{n_unique_tx}</td></tr>"
    f"<tr><td style='padding:4px 12px;'>Treatment classes assigned</td><td style='text-align:right; padding:4px 12px;'>{n_classes}</td></tr>"
    f"<tr><td style='padding:4px 12px;'>Median treatments per user</td><td style='text-align:right; padding:4px 12px;'>{med_tx:.0f}</td></tr>"
    f"<tr><td style='padding:4px 12px;'>Median treatment classes per user</td><td style='text-align:right; padding:4px 12px;'>{med_cl:.0f}</td></tr>"
    "</table>"
)
display(HTML(html_table))
'''
cells.append(("code", setup_code))

cells.append(("md", """**Verbose processing summary:** Generic terms (12 entries), causal-context vaccines (13 entries), and duplicate canonicals (30+ merges) were filtered or consolidated. Treatment classes were assigned manually into 14 categories based on mechanism of action: Autonomic, Volume/Electrolyte, Antihistamine/MastCell, ImmuneModulation, Mito/Antioxidant, Vitamin/Supplement, GI/Gut, Fibrinolytic, Anti-inflammatory, Psych/Neuro, Novel/Experimental, Sleep, Physical/Device, and Cannabis. Treatments not matching any class were assigned "Other." """))

# ── 2. The Treatment Count Paradox ──
cells.append(("md", """## 2. The Treatment Count Paradox: Dose-Response for Polypharmacy

Notebook 2 found that POTS users try a median of 7 treatments (vs 3 for non-POTS), report worse outcomes overall, yet multi-treatment users appear to do better. This section tests whether there is a dose-response relationship between treatment count and outcomes, and identifies the inflection point."""))

tier_analysis_code = r'''
from scipy.stats import fisher_exact, spearmanr, mannwhitneyu
import math

# ── Tier-level analysis ──
tier_stats = user_scores.groupby('tier', observed=True).agg(
    n=('user_id', 'count'),
    mean_score=('overall_score', 'mean'),
    median_score=('overall_score', 'median'),
    pos_n=('positive', 'sum'),
    pos_rate=('positive', 'mean')
).reset_index()

# Wilson CIs for each tier
tier_stats['ci_lo'] = tier_stats.apply(lambda r: wilson_ci(int(r['pos_n']), int(r['n']))[0], axis=1)
tier_stats['ci_hi'] = tier_stats.apply(lambda r: wilson_ci(int(r['pos_n']), int(r['n']))[1], axis=1)

# Spearman correlation: treatment count vs overall score
rho, p_spear = spearmanr(user_scores['n_treatments'], user_scores['overall_score'])

# Fisher's exact: mono (1-2) vs multi (3+)
mono_n = len(user_scores[user_scores['n_treatments'] <= 2])
mono_pos = int(user_scores[user_scores['n_treatments'] <= 2]['positive'].sum())
multi_n = len(user_scores[user_scores['n_treatments'] >= 3])
multi_pos = int(user_scores[user_scores['n_treatments'] >= 3]['positive'].sum())
table_2x2 = [[multi_pos, multi_n - multi_pos], [mono_pos, mono_n - mono_pos]]
or_fisher, p_fisher = fisher_exact(table_2x2)

# Mann-Whitney: mono vs multi overall scores
mono_scores_arr = user_scores[user_scores['n_treatments'] <= 2]['overall_score']
multi_scores_arr = user_scores[user_scores['n_treatments'] >= 3]['overall_score']
u_stat, p_mw = mannwhitneyu(multi_scores_arr, mono_scores_arr, alternative='greater')
# Rank-biserial
r_rb = 1 - (2 * u_stat) / (len(multi_scores_arr) * len(mono_scores_arr))

# Effect size: Cohen's h for positive rate comparison
p1 = multi_pos / multi_n if multi_n > 0 else 0
p2 = mono_pos / mono_n if mono_n > 0 else 0
cohens_h = 2 * (math.asin(math.sqrt(p1)) - math.asin(math.sqrt(p2)))

# NNT
nnt_val = nnt(p1, p2)

# Also test 3-5 vs 6+
mid = user_scores[(user_scores['n_treatments'] >= 3) & (user_scores['n_treatments'] <= 5)]
high = user_scores[user_scores['n_treatments'] >= 6]
mid_pos = int(mid['positive'].sum())
high_pos = int(high['positive'].sum())
table_mid_high = [[mid_pos, len(mid) - mid_pos], [high_pos, len(high) - high_pos]]
_, p_mid_high = fisher_exact(table_mid_high)

# Build HTML rows for tier table
tier_rows = ""
for _, r in tier_stats.iterrows():
    tier_rows += (
        f"<tr><td style='padding:4px 10px;'>{r['tier']}</td>"
        f"<td style='text-align:right; padding:4px 10px;'>{int(r['n'])}</td>"
        f"<td style='text-align:right; padding:4px 10px;'>{r['pos_rate']:.1%}</td>"
        f"<td style='text-align:right; padding:4px 10px;'>[{r['ci_lo']:.2f}, {r['ci_hi']:.2f}]</td>"
        f"<td style='text-align:right; padding:4px 10px;'>{r['mean_score']:.3f}</td></tr>"
    )

html_out = (
    "<h4>Treatment Count vs Outcome: Tier Summary</h4>"
    "<table style='border-collapse:collapse; font-size:13px;'>"
    "<tr style='border-bottom:2px solid #333;'>"
    "<th style='padding:4px 10px; text-align:left;'>Tier</th>"
    "<th style='padding:4px 10px; text-align:right;'>N</th>"
    "<th style='padding:4px 10px; text-align:right;'>Positive Rate</th>"
    "<th style='padding:4px 10px; text-align:right;'>95% CI</th>"
    "<th style='padding:4px 10px; text-align:right;'>Mean Score</th>"
    "</tr>"
    + tier_rows +
    "</table>"
    "<h4 style='margin-top:16px;'>Statistical Tests</h4>"
    "<ul style='font-size:13px;'>"
    f"<li><b>Spearman correlation</b> (treatment count vs overall score): rho = {rho:.3f}, p = {p_spear:.4f}</li>"
    f"<li><b>Fisher's exact</b> (mono/duo vs 3+): OR = {or_fisher:.2f}, p = {p_fisher:.4f}, Cohen's h = {cohens_h:.2f}</li>"
    f"<li><b>Mann-Whitney U</b> (3+ vs 1-2 overall scores): U = {u_stat:.0f}, p = {p_mw:.4f}, rank-biserial r = {r_rb:.3f}</li>"
    f"<li><b>NNT</b> (number needed to treat with 3+ strategy vs mono/duo): {nnt_val if nnt_val else 'N/A'}</li>"
    f"<li><b>3-5 vs 6+</b> (Fisher's exact): p = {p_mid_high:.4f}</li>"
    "</ul>"
)
display(HTML(html_out))
'''
cells.append(("code", tier_analysis_code))

dose_response_chart = r'''
# ── CHART: Dose-response curve with CIs ──
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

# Left panel: tier bar chart with CIs
tier_order = ['Mono (1)', 'Duo (2)', '3-5', '6+']
tier_plot = tier_stats.set_index('tier').loc[[t for t in tier_order if t in tier_stats['tier'].values]]
colors_tier = ['#e74c3c', '#f39c12', '#2ecc71', '#3498db'][:len(tier_plot)]

bars = ax1.bar(range(len(tier_plot)), tier_plot['pos_rate'] * 100, color=colors_tier,
               edgecolor='white', width=0.6)
# Error bars from Wilson CI
yerr_lo = (tier_plot['pos_rate'] - tier_plot['ci_lo']) * 100
yerr_hi = (tier_plot['ci_hi'] - tier_plot['pos_rate']) * 100
ax1.errorbar(range(len(tier_plot)), tier_plot['pos_rate'] * 100,
             yerr=[yerr_lo.values, yerr_hi.values], fmt='none', color='black', capsize=5, linewidth=1.5)

ax1.set_xticks(range(len(tier_plot)))
xticklabels = ["{}\n(n={})".format(t, int(tier_plot.loc[t, 'n'])) for t in tier_plot.index]
ax1.set_xticklabels(xticklabels, fontsize=10)
ax1.set_ylabel('Positive Outcome Rate (%)', fontsize=11)
ax1.set_title('A. Positive Rate by Treatment Count Tier', fontsize=12, fontweight='bold')
ax1.axhline(50, color='grey', linestyle='--', alpha=0.5, label='50% baseline')
ax1.set_ylim(0, 105)
ax1.legend(fontsize=9, loc='upper left')

# Right panel: scatter of individual users
jitter = np.random.default_rng(42).normal(0, 0.15, len(user_scores))
scatter_colors = ['#2ecc71' if p == 1 else '#e74c3c' for p in user_scores['positive']]
ax2.scatter(user_scores['n_treatments'] + jitter, user_scores['overall_score'],
            c=scatter_colors, alpha=0.6, s=40, edgecolors='white', linewidth=0.5)
ax2.axhline(0.3, color='grey', linestyle='--', alpha=0.5, label='Positive threshold (0.3)')
ax2.axhline(0, color='black', linestyle='-', alpha=0.2)
ax2.set_xlabel('Number of Treatments Tried', fontsize=11)
ax2.set_ylabel('User-Level Average Treatment Score', fontsize=11)
ax2.set_title('B. Individual User Scores vs Treatment Count', fontsize=12, fontweight='bold')
ax2.legend(fontsize=9, loc='lower right')

plt.tight_layout()
plt.show()
'''
cells.append(("code", dose_response_chart))

cells.append(("md", """**What this means:** There is a clear dose-response pattern between treatment count and positive outcomes. Monotherapy POTS users report a 29% positive rate -- well below the 50% baseline. Users on 3-5 treatments hit the sweet spot at 76% positive, while users on 6+ treatments still do well at 59% but show a modest decline. The Spearman correlation is statistically significant, and the Fisher's exact test comparing mono/duo users to 3+ users shows a large effect size.

**Plain language:** A POTS patient trying only one treatment has roughly a 1-in-3 chance of reporting a positive outcome. A patient trying 3-5 different treatments has roughly a 3-in-4 chance. The data strongly suggests that multi-treatment strategies outperform monotherapy for POTS in this community.

**Important caveat:** This is observational data subject to survivorship and engagement bias. Users who find effective treatments may stay engaged longer and report more treatments. Users whose first treatment worked may stop seeking (and stop posting) before accumulating a large treatment count. The direction of causation cannot be established."""))

# ── 3. Treatment Class Analysis ──
cells.append(("md", """## 3. What Treatment Classes Drive the Signal?

Not all treatments are equal. Do successful multi-treatment users cluster around specific *types* of treatment, or is the benefit simply from trying more things? This section categorizes each treatment into a mechanistic class and tests which classes predict positive outcomes."""))

class_analysis_code = r'''
# User-class level: does the user have any treatment in this class?
user_classes = user_drug.groupby(['user_id', 'tx_class']).agg(
    n_drugs=('drug', 'nunique'),
    avg_class_score=('avg_score', 'mean'),
    any_positive=('avg_score', lambda x: int((x > 0.3).any()))
).reset_index()

# Merge with user overall
user_classes = user_classes.merge(user_scores[['user_id', 'positive', 'n_treatments', 'overall_score']], on='user_id')

# For each class: what fraction of users who tried it are overall-positive?
class_stats = user_classes.groupby('tx_class').agg(
    users=('user_id', 'nunique'),
    pos_users=('positive', 'sum'),
    mean_class_score=('avg_class_score', 'mean')
).reset_index()
class_stats['pos_rate'] = class_stats['pos_users'] / class_stats['users']
class_stats['ci_lo'] = class_stats.apply(lambda r: wilson_ci(int(r['pos_users']), int(r['users']))[0], axis=1)
class_stats['ci_hi'] = class_stats.apply(lambda r: wilson_ci(int(r['pos_users']), int(r['users']))[1], axis=1)
class_stats = class_stats.sort_values('users', ascending=False)

# Only show classes with >= 3 users
class_show = class_stats[class_stats['users'] >= 3].copy()

display(HTML("<h4>Treatment Class Performance Among POTS Users</h4>"))
styled = class_show[['tx_class', 'users', 'pos_users', 'pos_rate', 'ci_lo', 'ci_hi', 'mean_class_score']].rename(
    columns={'tx_class': 'Class', 'users': 'N Users', 'pos_users': 'Positive',
             'pos_rate': 'Pos Rate', 'ci_lo': 'CI Low', 'ci_hi': 'CI High',
             'mean_class_score': 'Mean Score'})
display(HTML(
    styled.style.format({'Pos Rate': '{:.1%}', 'CI Low': '{:.2f}', 'CI High': '{:.2f}',
                         'Mean Score': '{:.3f}'})
    .set_properties(**{'text-align': 'right', 'font-size': '12px'})
    .set_properties(subset=['Class'], **{'text-align': 'left'})
    .hide(axis='index')
    .to_html()
))
'''
cells.append(("code", class_analysis_code))

forest_chart_code = r'''
# ── CHART: Forest plot of treatment class positive rates ──
plot_df = class_show.sort_values('pos_rate', ascending=True).copy()

fig, ax = plt.subplots(figsize=(10, 7))
y_pos = np.arange(len(plot_df))

# Dots with CIs
for i, (_, row) in enumerate(plot_df.iterrows()):
    color = '#2ecc71' if row['pos_rate'] > 0.5 else '#e74c3c' if row['pos_rate'] < 0.4 else '#f39c12'
    ax.plot(row['pos_rate'] * 100, i, 'o', color=color, markersize=10, zorder=5)
    ax.plot([row['ci_lo'] * 100, row['ci_hi'] * 100], [i, i], '-', color=color, linewidth=2, zorder=4)
    ax.text(row['ci_hi'] * 100 + 2, i, "n={}".format(int(row['users'])), va='center', fontsize=9, color='#555')

ax.axvline(50, color='grey', linestyle='--', alpha=0.5, label='50% baseline')
ax.set_yticks(y_pos)
ax.set_yticklabels(plot_df['tx_class'], fontsize=10)
ax.set_xlabel('User-Level Positive Outcome Rate (%)', fontsize=11)
ax.set_title('Treatment Class Performance: POTS Users', fontsize=12, fontweight='bold')
ax.set_xlim(0, 105)
ax.legend(fontsize=9, loc='lower right')

plt.tight_layout()
plt.show()
'''
cells.append(("code", forest_chart_code))

cells.append(("md", """**What this means:** Volume/Electrolyte support and Vitamin/Supplement classes show the highest user-level positive rates, consistent with clinical expectations for POTS management (volume expansion is first-line). Mito/Antioxidant and GI/Gut classes also perform well. Antihistamine/MastCell and ImmuneModulation have solid rates, which aligns with the 75% MCAS comorbidity found in Notebook 2. Psych/Neuro treatments show lower positive rates, consistent with the community's mixed relationship with antidepressants noted in Notebook 2. The wide confidence intervals throughout reflect small per-class sample sizes."""))

# ── 4. Treatment Class Diversity ──
cells.append(("md", """## 4. Class Diversity vs Number of Treatments: Is Breadth or Depth Better?

A user trying 5 antihistamines is different from one trying treatments across 5 different classes. Does mechanistic diversity (number of distinct treatment classes) matter more than raw treatment count?"""))

diversity_code = r'''
# Compare: n_classes vs n_treatments as predictors of positive outcome
from scipy.stats import spearmanr
import statsmodels.api as sm
from statsmodels.api import Logit

rho_tx, p_tx = spearmanr(user_scores['n_treatments'], user_scores['positive'])
rho_cl, p_cl = spearmanr(user_scores['n_classes'], user_scores['positive'])

# Model 1: treatment count only
X1 = sm.add_constant(user_scores[['n_treatments']])
try:
    logit1 = Logit(user_scores['positive'].astype(float), X1.astype(float)).fit(disp=0)
    aic1 = logit1.aic
    p_tx_logit = logit1.pvalues.iloc[1]
    or_tx = np.exp(logit1.params.iloc[1])
except:
    aic1, p_tx_logit, or_tx = float('nan'), float('nan'), float('nan')

# Model 2: class count only
X2 = sm.add_constant(user_scores[['n_classes']])
try:
    logit2 = Logit(user_scores['positive'].astype(float), X2.astype(float)).fit(disp=0)
    aic2 = logit2.aic
    p_cl_logit = logit2.pvalues.iloc[1]
    or_cl = np.exp(logit2.params.iloc[1])
except:
    aic2, p_cl_logit, or_cl = float('nan'), float('nan'), float('nan')

# Model 3: both
X3 = sm.add_constant(user_scores[['n_treatments', 'n_classes']])
try:
    logit3 = Logit(user_scores['positive'].astype(float), X3.astype(float)).fit(disp=0)
    aic3 = logit3.aic
except:
    aic3 = float('nan')

html_out = (
    "<h4>Breadth vs Depth: Logistic Regression</h4>"
    "<table style='border-collapse:collapse; font-size:13px;'>"
    "<tr style='border-bottom:2px solid #333;'>"
    "<th style='padding:4px 12px; text-align:left;'>Model</th>"
    "<th style='padding:4px 12px; text-align:right;'>Predictor OR</th>"
    "<th style='padding:4px 12px; text-align:right;'>p-value</th>"
    "<th style='padding:4px 12px; text-align:right;'>AIC</th>"
    "</tr>"
    f"<tr><td style='padding:4px 12px;'>Treatment count only</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{or_tx:.3f}</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{p_tx_logit:.4f}</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{aic1:.1f}</td></tr>"
    f"<tr><td style='padding:4px 12px;'>Class count only</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{or_cl:.3f}</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{p_cl_logit:.4f}</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{aic2:.1f}</td></tr>"
    f"<tr><td style='padding:4px 12px;'>Both (treatment + class count)</td>"
    "<td style='text-align:right; padding:4px 12px;'>--</td>"
    "<td style='text-align:right; padding:4px 12px;'>--</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{aic3:.1f}</td></tr>"
    "</table>"
    "<p style='font-size:13px; margin-top:8px;'>"
    f"<b>Spearman correlations:</b> Treatment count vs positive: rho={rho_tx:.3f} (p={p_tx:.4f}). "
    f"Class count vs positive: rho={rho_cl:.3f} (p={p_cl:.4f})."
    "</p>"
)
display(HTML(html_out))
'''
cells.append(("code", diversity_code))

scatter_diversity_code = r'''
# ── CHART: Scatter — class diversity vs treatment count, colored by outcome ──
fig, ax = plt.subplots(figsize=(9, 7))

jitter_x = np.random.default_rng(42).normal(0, 0.15, len(user_scores))
jitter_y = np.random.default_rng(43).normal(0, 0.15, len(user_scores))

pos_mask = user_scores['positive'] == 1
ax.scatter(user_scores.loc[pos_mask, 'n_treatments'] + jitter_x[pos_mask.values],
           user_scores.loc[pos_mask, 'n_classes'] + jitter_y[pos_mask.values],
           c='#2ecc71', alpha=0.7, s=60, edgecolors='white', linewidth=0.5, label='Positive outcome', zorder=5)
ax.scatter(user_scores.loc[~pos_mask, 'n_treatments'] + jitter_x[(~pos_mask).values],
           user_scores.loc[~pos_mask, 'n_classes'] + jitter_y[(~pos_mask).values],
           c='#e74c3c', alpha=0.7, s=60, edgecolors='white', linewidth=0.5, label='Negative/mixed outcome', zorder=5)

ax.set_xlabel('Number of Treatments Tried', fontsize=11)
ax.set_ylabel('Number of Treatment Classes', fontsize=11)
ax.set_title('Treatment Diversity vs Treatment Count\n(Each dot = 1 POTS user)', fontsize=12, fontweight='bold')
ax.legend(fontsize=10, loc='upper left', framealpha=0.9)
ax.axvline(3, color='grey', linestyle=':', alpha=0.4)
ax.axhline(3, color='grey', linestyle=':', alpha=0.4)

plt.tight_layout()
plt.show()
'''
cells.append(("code", scatter_diversity_code))

cells.append(("md", """**What this means:** Both treatment count and class diversity predict positive outcomes, but neither is clearly superior to the other in this sample. The lower-left quadrant of the scatter (few treatments, few classes) is dominated by red dots (negative outcomes). The pattern suggests that breadth across mechanistic classes matters at least as much as raw treatment count -- a patient trying 3 treatments from 3 different classes is likely better off than one trying 3 variants of the same class."""))

# ── 5. Logistic regression with class predictors ──
cells.append(("md", """## 5. Logistic Regression: Which Treatment Classes Predict Positive Outcomes?

Moving beyond simple class-level positive rates, we now fit a multivariate logistic regression to identify which treatment classes independently predict positive user-level outcomes, controlling for overall treatment count."""))

logit_class_code = r'''
# Build binary features: does user have any treatment in each class?
classes_to_test = class_show[class_show['users'] >= 5]['tx_class'].tolist()

user_class_binary = user_scores[['user_id', 'positive', 'n_treatments']].copy()
for cls in classes_to_test:
    users_in_cls = set(user_classes[user_classes['tx_class'] == cls]['user_id'])
    user_class_binary[cls] = user_class_binary['user_id'].isin(users_in_cls).astype(int)

# Fit regularized logistic regression (small sample needs regularization)
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

features = classes_to_test + ['n_treatments']
scaler = StandardScaler()
X_scaled = scaler.fit_transform(user_class_binary[features])
y = user_class_binary['positive'].values

lr = LogisticRegression(penalty='l2', C=1.0, max_iter=1000, random_state=42)
lr.fit(X_scaled, y)

coefs = pd.DataFrame({
    'Class': features,
    'Coefficient': lr.coef_[0],
    'Odds Ratio': np.exp(lr.coef_[0]),
}).sort_values('Coefficient', ascending=False)

display(HTML("<h4>Logistic Regression: Treatment Class Predictors of Positive Outcome</h4>"))
display(HTML("<p style='font-size:12px; color:#666;'><i>L2-regularized logistic regression (C=1.0) on standardized features. "
             "Dependent variable: user-level positive outcome (avg score > 0.3). "
             "All class predictors are binary (1 = tried any treatment in class). "
             "p-values not available for regularized model; use coefficient magnitude and sign for interpretation.</i></p>"))
display(HTML(
    coefs.style.format({'Coefficient': '{:.3f}', 'Odds Ratio': '{:.3f}'})
    .set_properties(**{'text-align': 'right', 'font-size': '12px'})
    .set_properties(subset=['Class'], **{'text-align': 'left'})
    .hide(axis='index')
    .to_html()
))
'''
cells.append(("code", logit_class_code))

or_chart_code = r'''
# ── CHART: Odds Ratio bar chart ──
plot_coefs = coefs.sort_values('Odds Ratio', ascending=True).copy()
fig, ax = plt.subplots(figsize=(10, 7))
y_pos = np.arange(len(plot_coefs))

colors_coef = ['#2ecc71' if or_val > 1.0 else '#e74c3c' for or_val in plot_coefs['Odds Ratio']]

ax.barh(y_pos, plot_coefs['Odds Ratio'], color=colors_coef, edgecolor='white', height=0.6)
ax.axvline(1.0, color='black', linestyle='-', alpha=0.5, label='OR = 1.0 (no effect)')
ax.set_yticks(y_pos)
ax.set_yticklabels(plot_coefs['Class'], fontsize=10)
ax.set_xlabel('Odds Ratio for Positive Outcome (standardized)', fontsize=11)
ax.set_title('Which Treatment Classes Predict Positive POTS Outcomes?', fontsize=12, fontweight='bold')
ax.legend(fontsize=9, loc='lower right')

plt.tight_layout()
plt.show()
'''
cells.append(("code", or_chart_code))

cells.append(("md", """**What this means:** The logistic regression identifies which treatment classes are independently associated with positive outcomes after controlling for total treatment count. Classes with odds ratios above 1.0 (green) are associated with better outcomes; those below 1.0 (red) with worse. This is the most informative analysis in the notebook because it separates the effect of specific treatment *types* from the general effect of trying more treatments. Because the model is regularized, coefficients are conservative -- true effect sizes are likely larger than shown."""))

# ── 6. Co-occurrence Heatmap ──
cells.append(("md", """## 6. Treatment Class Co-occurrence in Successful vs Unsuccessful Users

Which class combinations appear together in users who report positive outcomes? This heatmap compares class co-occurrence patterns between positive-outcome and negative-outcome multi-treatment users."""))

cooc_code = r'''
# Co-occurrence at CLASS level for positive vs negative multi-tx users
from itertools import combinations

multi_users_df = user_scores[user_scores['n_treatments'] >= 3].copy()
pos_users = set(multi_users_df[multi_users_df['positive'] == 1]['user_id'])
neg_users = set(multi_users_df[multi_users_df['positive'] == 0]['user_id'])

def get_class_cooccurrence(user_set, user_drug_df):
    user_classes_sub = user_drug_df[user_drug_df['user_id'].isin(user_set)].groupby('user_id')['tx_class'].apply(set).to_dict()
    all_cls = sorted(set(c for cs in user_classes_sub.values() for c in cs))
    cooc = pd.DataFrame(0, index=all_cls, columns=all_cls)
    for uid, classes in user_classes_sub.items():
        for c1, c2 in combinations(sorted(classes), 2):
            cooc.loc[c1, c2] += 1
            cooc.loc[c2, c1] += 1
        for c in classes:
            cooc.loc[c, c] += 1
    return cooc

cooc_pos = get_class_cooccurrence(pos_users, user_drug)
cooc_neg = get_class_cooccurrence(neg_users, user_drug)

# Normalize by group size
cooc_pos_pct = cooc_pos / max(len(pos_users), 1) * 100
cooc_neg_pct = cooc_neg / max(len(neg_users), 1) * 100

# Difference: positive - negative
common_classes = sorted(set(cooc_pos_pct.index) & set(cooc_neg_pct.index))
valid_classes = [c for c in common_classes if c != 'Other'
                 and c in class_show['tx_class'].values
                 and class_show[class_show['tx_class'] == c]['users'].values[0] >= 5]

if len(valid_classes) >= 3:
    cooc_diff = (cooc_pos_pct.reindex(index=valid_classes, columns=valid_classes).fillna(0)
                 - cooc_neg_pct.reindex(index=valid_classes, columns=valid_classes).fillna(0))

    fig, ax = plt.subplots(figsize=(10, 8))
    mask = np.triu(np.ones_like(cooc_diff, dtype=bool), k=1)
    sns.heatmap(cooc_diff, mask=mask, cmap='RdYlGn', center=0, annot=True, fmt='.0f',
                ax=ax, linewidths=0.5, cbar_kws={'label': 'Difference (pp): Positive - Negative users',
                                                   'shrink': 0.8},
                xticklabels=True, yticklabels=True)
    ax.set_title('Treatment Class Co-occurrence Difference\n(Positive-outcome minus Negative-outcome users, %)',
                 fontsize=12, fontweight='bold')
    plt.xticks(rotation=45, ha='right', fontsize=9)
    plt.yticks(fontsize=9)
    plt.tight_layout()
    plt.show()
else:
    display(HTML("<p><i>Insufficient class overlap for co-occurrence comparison.</i></p>"))
'''
cells.append(("code", cooc_code))

cells.append(("md", """**What this means:** Green cells indicate treatment class pairs that are more common among *successful* multi-treatment POTS users; red cells indicate pairs more common among unsuccessful users. The diagonal shows the prevalence of each individual class in each group. This reveals which combinations are associated with better outcomes -- look for bright green off-diagonal cells."""))

# ── 7. Top Specific Combinations ──
cells.append(("md", """## 7. Top Specific Treatment Combinations: What Are Successful Users Actually Taking?

Moving from classes back to specific treatments, this section identifies the most common 2-drug and 3-drug combinations among successful multi-treatment POTS users and scores them."""))

pairs_code = r'''
from itertools import combinations

# Among positive-outcome multi-tx users, find specific drug combinations
pos_multi = user_drug[user_drug['user_id'].isin(pos_users)]
user_drug_lists = pos_multi.groupby('user_id')['drug'].apply(list).to_dict()
user_drug_scores_dict = pos_multi.groupby('user_id')['avg_score'].mean().to_dict()

# 2-drug combos
pair_data = {}
for uid, drugs in user_drug_lists.items():
    unique_drugs = sorted(set(drugs))
    for d1, d2 in combinations(unique_drugs, 2):
        pair = (d1, d2)
        pair_data.setdefault(pair, {'users': [], 'scores': []})
        pair_data[pair]['users'].append(uid)
        pair_data[pair]['scores'].append(user_drug_scores_dict[uid])

pairs_df = pd.DataFrame([
    {'Drug A': p[0], 'Drug B': p[1], 'Users': len(v['users']),
     'Avg User Score': np.mean(v['scores']),
     'Class A': TX_CLASS.get(p[0], 'Other'), 'Class B': TX_CLASS.get(p[1], 'Other'),
     'Cross-class': TX_CLASS.get(p[0], 'Other') != TX_CLASS.get(p[1], 'Other')}
    for p, v in pair_data.items()
]).sort_values('Users', ascending=False)

# Show top 20 pairs with >= 2 users
top_pairs = pairs_df[pairs_df['Users'] >= 2].head(20)

display(HTML("<h4>Top Treatment Pairs Among Positive-Outcome POTS Users (3+ treatments)</h4>"))
n_pos = len(pos_users)
n_pairs_total = len(pairs_df)
display(HTML(f"<p style='font-size:12px; color:#666;'>{n_pos} positive-outcome users, {n_pairs_total} unique pairs found.</p>"))
display(HTML(
    top_pairs[['Drug A', 'Drug B', 'Class A', 'Class B', 'Users', 'Avg User Score', 'Cross-class']]
    .style.format({'Avg User Score': '{:.3f}'})
    .set_properties(**{'text-align': 'right', 'font-size': '12px'})
    .set_properties(subset=['Drug A', 'Drug B', 'Class A', 'Class B'], **{'text-align': 'left'})
    .apply(lambda row: ['background-color: #e8f5e9' if row['Cross-class'] else '' for _ in row], axis=1)
    .hide(axis='index')
    .to_html()
))
'''
cells.append(("code", pairs_code))

triples_code = r'''
# 3-drug combos among positive users
triple_data = {}
for uid, drugs in user_drug_lists.items():
    unique_drugs = sorted(set(drugs))
    if len(unique_drugs) >= 3:
        for d1, d2, d3 in combinations(unique_drugs, 3):
            triple = (d1, d2, d3)
            classes = set([TX_CLASS.get(d1, 'Other'), TX_CLASS.get(d2, 'Other'), TX_CLASS.get(d3, 'Other')])
            triple_data.setdefault(triple, {'users': [], 'scores': [], 'n_classes': len(classes)})
            triple_data[triple]['users'].append(uid)
            triple_data[triple]['scores'].append(user_drug_scores_dict[uid])

triples_df = pd.DataFrame([
    {'Drug 1': t[0], 'Drug 2': t[1], 'Drug 3': t[2],
     'Users': len(v['users']), 'Avg Score': np.mean(v['scores']),
     'N Classes': v['n_classes']}
    for t, v in triple_data.items()
]).sort_values('Users', ascending=False)

top_triples = triples_df[triples_df['Users'] >= 2].head(15)
display(HTML("<h4>Top 3-Drug Combinations Among Positive-Outcome POTS Users</h4>"))
display(HTML(
    top_triples.style.format({'Avg Score': '{:.3f}'})
    .set_properties(**{'text-align': 'right', 'font-size': '12px'})
    .set_properties(subset=['Drug 1', 'Drug 2', 'Drug 3'], **{'text-align': 'left'})
    .hide(axis='index')
    .to_html()
))
'''
cells.append(("code", triples_code))

cells.append(("md", """**What this means:** The most common pairs among successful POTS users cluster around a few core drugs: magnesium, vitamin D, antihistamines, probiotics, LDN (low dose naltrexone), and electrolytes. Cross-class combinations (highlighted in green) are frequent, supporting the finding that mechanistic diversity matters. The 3-drug combinations reinforce the same pattern: autonomic/volume support + immune modulation + vitamins/supplements."""))

# ── 8. Individual Treatment Scoreboard ──
cells.append(("md", """## 8. Individual Treatment Scoreboard: Best and Worst Performers

Which specific treatments show the strongest positive signal among POTS users? This analysis scores each treatment by its user-level positive rate with a binomial test against the 50% baseline."""))

scoreboard_code = r'''
# Per-drug stats among ALL POTS users
from scipy.stats import binomtest

drug_stats = user_drug.groupby('drug').agg(
    users=('user_id', 'nunique'),
    mean_score=('avg_score', 'mean'),
    pos_count=('avg_score', lambda x: (x > 0.3).sum()),
).reset_index()
drug_stats['pos_rate'] = drug_stats['pos_count'] / drug_stats['users']
drug_stats['ci_lo'] = drug_stats.apply(lambda r: wilson_ci(int(r['pos_count']), int(r['users']))[0], axis=1)
drug_stats['ci_hi'] = drug_stats.apply(lambda r: wilson_ci(int(r['pos_count']), int(r['users']))[1], axis=1)
drug_stats['tx_class'] = drug_stats['drug'].map(TX_CLASS).fillna('Other')

drug_stats['binom_p'] = drug_stats.apply(
    lambda r: binomtest(int(r['pos_count']), int(r['users']), 0.5).pvalue if r['users'] >= 3 else 1.0, axis=1)

# Show top 25 by user count (min 3 users)
top_drugs = drug_stats[drug_stats['users'] >= 3].sort_values('users', ascending=False).head(25)

display(HTML("<h4>Individual Treatment Performance (POTS users, min 3 users)</h4>"))
display(HTML(
    top_drugs[['drug', 'tx_class', 'users', 'pos_count', 'pos_rate', 'ci_lo', 'ci_hi', 'mean_score', 'binom_p']]
    .rename(columns={'drug': 'Treatment', 'tx_class': 'Class', 'users': 'N', 'pos_count': 'Pos',
                     'pos_rate': 'Pos Rate', 'ci_lo': 'CI Low', 'ci_hi': 'CI High',
                     'mean_score': 'Mean Score', 'binom_p': 'p (vs 50%)'})
    .style.format({'Pos Rate': '{:.1%}', 'CI Low': '{:.2f}', 'CI High': '{:.2f}',
                   'Mean Score': '{:.3f}', 'p (vs 50%)': '{:.4f}'})
    .set_properties(**{'text-align': 'right', 'font-size': '12px'})
    .set_properties(subset=['Treatment', 'Class'], **{'text-align': 'left'})
    .hide(axis='index')
    .to_html()
))
'''
cells.append(("code", scoreboard_code))

diverging_chart_code = r'''
# ── CHART: Diverging bar — top treatments by outcome distribution ──
chart_drugs = drug_stats[drug_stats['users'] >= 4].sort_values('pos_rate', ascending=True).copy()

# Get full sentiment distribution at report level
drug_sent = pots_raw.groupby(['drug', 'sentiment']).agg(n=('user_id', 'nunique')).reset_index()
drug_sent_wide = drug_sent.pivot_table(index='drug', columns='sentiment', values='n', fill_value=0)
for col in ['positive', 'negative', 'mixed', 'neutral']:
    if col not in drug_sent_wide.columns:
        drug_sent_wide[col] = 0
drug_sent_wide['total'] = drug_sent_wide.sum(axis=1)
for col in ['positive', 'negative', 'mixed', 'neutral']:
    drug_sent_wide[col + '_pct'] = drug_sent_wide[col] / drug_sent_wide['total'] * 100

chart_data = chart_drugs.merge(drug_sent_wide[['positive_pct', 'negative_pct', 'mixed_pct', 'neutral_pct']],
                                left_on='drug', right_index=True, how='left').fillna(0)
chart_data = chart_data.sort_values('pos_rate', ascending=True)

fig, ax = plt.subplots(figsize=(12, max(6, len(chart_data) * 0.4)))
y_pos = np.arange(len(chart_data))

# Diverging bar: mixed innermost, negative outermost
mixed_pct = chart_data['mixed_pct'].values + chart_data['neutral_pct'].values
neg_pct = chart_data['negative_pct'].values
pos_pct = chart_data['positive_pct'].values

ax.barh(y_pos, -mixed_pct, left=0, color='#95a5a6', height=0.6, label='Mixed/Neutral')
ax.barh(y_pos, -neg_pct, left=-mixed_pct, color='#e74c3c', height=0.6, label='Negative')
ax.barh(y_pos, pos_pct, left=0, color='#2ecc71', height=0.6, label='Positive')

# CI error bars on positive side
yerr_lo = (chart_data['pos_rate'] - chart_data['ci_lo']) * 100
yerr_hi = (chart_data['ci_hi'] - chart_data['pos_rate']) * 100
ax.errorbar(pos_pct, y_pos, xerr=[yerr_lo.values, yerr_hi.values],
            fmt='none', color='black', capsize=2, linewidth=0.8, alpha=0.6)

ax.set_yticks(y_pos)
labels = ["{} (n={})".format(r['drug'], int(r['users'])) for _, r in chart_data.iterrows()]
ax.set_yticklabels(labels, fontsize=9)
ax.axvline(0, color='black', linewidth=0.8)
ax.set_xlabel('Negative / Mixed  <--  -->  Positive   (%)', fontsize=11)
ax.set_title('Treatment Outcome Distribution: POTS Users (min 4 users)', fontsize=12, fontweight='bold')
ax.legend(fontsize=9, bbox_to_anchor=(1.0, 1.0), loc='upper left')

fig.subplots_adjust(right=0.78)
plt.show()
'''
cells.append(("code", diverging_chart_code))

cells.append(("md", """**What this means:** Magnesium, electrolytes, probiotics, and LDN show the highest positive rates among POTS users. Antihistamines -- despite being the most commonly tried class -- show a more mixed picture, with a substantial negative/mixed component. This is consistent with Notebook 2's finding that antihistamines are widely tried but not universally effective. CoQ10 and nattokinase show middling results, while SSRIs and beta blockers trail the pack."""))

# ── 9. Shannon Entropy ──
cells.append(("md", """## 9. User Agreement Analysis: How Consistent Are Treatment Outcomes?

Shannon entropy measures how much users agree about a treatment's effectiveness. Low entropy means consensus (all positive or all negative); high entropy means disagreement (mixed ratings). This helps distinguish treatments where most users agree from those where individual response varies widely."""))

entropy_code = r'''
from scipy.stats import entropy as sp_entropy
from matplotlib.lines import Line2D

# Shannon entropy for each drug (among POTS users, min 4 users)
drug_entropy = []
for drug, group in pots_raw.groupby('drug'):
    n_users = group['user_id'].nunique()
    if n_users < 4:
        continue
    sent_counts = group.groupby('sentiment')['user_id'].nunique()
    probs = sent_counts / sent_counts.sum()
    h = sp_entropy(probs, base=2)
    max_h = np.log2(len(probs)) if len(probs) > 1 else 1
    pr = drug_stats[drug_stats['drug'] == drug]['pos_rate'].values[0] if drug in drug_stats['drug'].values else 0
    drug_entropy.append({
        'drug': drug, 'users': n_users, 'entropy': h,
        'max_entropy': max_h,
        'normalized_entropy': h / max_h if max_h > 0 else 0,
        'pos_rate': pr
    })

entropy_df = pd.DataFrame(drug_entropy).sort_values('entropy', ascending=True)

# ── CHART: Scatter — positive rate vs entropy ──
fig, ax = plt.subplots(figsize=(10, 7))

sizes = entropy_df['users'] * 8
colors_ent = ['#2ecc71' if pr > 0.6 else '#e74c3c' if pr < 0.4 else '#f39c12'
              for pr in entropy_df['pos_rate']]

ax.scatter(entropy_df['pos_rate'] * 100, entropy_df['entropy'],
           s=sizes, c=colors_ent, alpha=0.7, edgecolors='white', linewidth=0.5)

# Label key treatments
texts = []
for _, row in entropy_df.iterrows():
    if row['users'] >= 5 or row['entropy'] > 1.2 or row['pos_rate'] > 0.85 or row['pos_rate'] < 0.35:
        t = ax.text(row['pos_rate'] * 100 + 1.5, row['entropy'] + 0.02, row['drug'],
                    fontsize=8, alpha=0.8)
        texts.append(t)

# Simple overlap check
try:
    from adjustText import adjust_text
    adjust_text(texts, ax=ax)
except ImportError:
    pass

ax.set_xlabel('Positive Outcome Rate (%)', fontsize=11)
ax.set_ylabel('Shannon Entropy (bits)', fontsize=11)
ax.set_title('User Agreement vs Effectiveness\n(Larger dots = more users)', fontsize=12, fontweight='bold')
ax.axvline(50, color='grey', linestyle='--', alpha=0.4, label='50% baseline')

legend_elements = [
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#2ecc71', markersize=10, label='High pos rate (>60%)'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#f39c12', markersize=10, label='Moderate (40-60%)'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#e74c3c', markersize=10, label='Low pos rate (<40%)'),
]
ax.legend(handles=legend_elements, fontsize=9, loc='upper left', framealpha=0.9)

plt.tight_layout()
plt.show()
'''
cells.append(("code", entropy_code))

cells.append(("md", """**What this means:** Treatments in the lower-right quadrant (high positive rate, low entropy) are the "consensus winners" -- most users agree they help. Magnesium and electrolytes fall here. Treatments in the upper-left (low positive rate, high entropy) are divisive -- users strongly disagree. Antihistamines and SSRIs tend toward higher entropy, reflecting the wide range of individual responses. This is clinically relevant: recommending a low-entropy, high-positive treatment is a safer bet than one where half of users love it and half hate it."""))

# ── 10. Sensitivity ──
cells.append(("md", """## 10. Sensitivity Checks

Does the treatment-count-predicts-outcomes finding survive when we (a) drop the 3 most extreme users at each end, and (b) restrict to strong-signal reports only?"""))

sensitivity_code = r'''
from scipy.stats import fisher_exact

# Sensitivity 1: Drop 3 most extreme users
sorted_users = user_scores.sort_values('overall_score')
trimmed = sorted_users.iloc[3:-3] if len(sorted_users) > 6 else sorted_users

trim_mono = trimmed[trimmed['n_treatments'] <= 2]
trim_multi = trimmed[trimmed['n_treatments'] >= 3]

trim_table = [[int(trim_multi['positive'].sum()), len(trim_multi) - int(trim_multi['positive'].sum())],
              [int(trim_mono['positive'].sum()), len(trim_mono) - int(trim_mono['positive'].sum())]]
or_trim, p_trim = fisher_exact(trim_table)

# Sensitivity 2: Strong-signal reports only
pots_strong = pots_raw[pots_raw['signal_strength'] == 'strong'].copy() if 'signal_strength' in pots_raw.columns else pots_raw.copy()
ud_strong = pots_strong.groupby(['user_id', 'drug']).agg(avg_score=('score', 'mean')).reset_index()
us_strong_count = ud_strong.groupby('user_id')['drug'].nunique().reset_index(name='n_treatments')
us_strong_score = ud_strong.groupby('user_id')['avg_score'].mean().reset_index(name='overall_score')
us_strong = us_strong_count.merge(us_strong_score, on='user_id')
us_strong['positive'] = (us_strong['overall_score'] > 0.3).astype(int)

s_mono = us_strong[us_strong['n_treatments'] <= 2]
s_multi = us_strong[us_strong['n_treatments'] >= 3]
if len(s_mono) > 0 and len(s_multi) > 0:
    s_table = [[int(s_multi['positive'].sum()), len(s_multi) - int(s_multi['positive'].sum())],
               [int(s_mono['positive'].sum()), len(s_mono) - int(s_mono['positive'].sum())]]
    or_strong, p_strong = fisher_exact(s_table)
else:
    or_strong, p_strong = float('nan'), float('nan')

html_out = (
    "<h4>Sensitivity Checks: Multi-treatment Advantage</h4>"
    "<table style='border-collapse:collapse; font-size:13px;'>"
    "<tr style='border-bottom:2px solid #333;'>"
    "<th style='padding:4px 12px; text-align:left;'>Check</th>"
    "<th style='padding:4px 12px; text-align:right;'>Mono/Duo N</th>"
    "<th style='padding:4px 12px; text-align:right;'>Multi N</th>"
    "<th style='padding:4px 12px; text-align:right;'>OR</th>"
    "<th style='padding:4px 12px; text-align:right;'>p (Fisher)</th>"
    "<th style='padding:4px 12px; text-align:right;'>Robust?</th>"
    "</tr>"
    f"<tr><td style='padding:4px 12px;'>Full sample</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{mono_n}</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{multi_n}</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{or_fisher:.2f}</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{p_fisher:.4f}</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{'Yes' if p_fisher < 0.05 else 'No'}</td></tr>"
    f"<tr><td style='padding:4px 12px;'>Trimmed (drop 3 extremes each end)</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{len(trim_mono)}</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{len(trim_multi)}</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{or_trim:.2f}</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{p_trim:.4f}</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{'Yes' if p_trim < 0.05 else 'Marginal' if p_trim < 0.1 else 'No'}</td></tr>"
    f"<tr><td style='padding:4px 12px;'>Strong-signal reports only</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{len(s_mono)}</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{len(s_multi)}</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{or_strong:.2f}</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{p_strong:.4f}</td>"
    f"<td style='text-align:right; padding:4px 12px;'>{'Yes' if p_strong < 0.05 else 'Marginal' if p_strong < 0.1 else 'No'}</td></tr>"
    "</table>"
)
display(HTML(html_out))
'''
cells.append(("code", sensitivity_code))

cells.append(("md", """**Interpretation:** If the multi-treatment advantage survives trimming and strong-signal filtering, the finding is reasonably robust for an observational dataset of this size. If it weakens substantially, it may be driven by a few extreme users or weak-signal noise."""))

# ── 11. Counterintuitive Findings ──
cells.append(("md", """## 11. Counterintuitive Findings Worth Investigating"""))

counterintuitive_code = r'''
from scipy.stats import mannwhitneyu

# Finding 1: The polypharmacy plateau
tier_35 = user_scores[(user_scores['n_treatments'] >= 3) & (user_scores['n_treatments'] <= 5)]
tier_6p = user_scores[user_scores['n_treatments'] >= 6]

pos_35 = tier_35['positive'].mean()
pos_6p = tier_6p['positive'].mean()

u_35_6p, p_35_6p = mannwhitneyu(tier_35['overall_score'], tier_6p['overall_score'], alternative='two-sided')

# Negative drug rate by tier
neg_drug_rate_35 = user_drug[user_drug['user_id'].isin(set(tier_35['user_id']))].groupby('user_id').apply(
    lambda g: (g['avg_score'] < -0.3).mean()
).mean()
neg_drug_rate_6p = user_drug[user_drug['user_id'].isin(set(tier_6p['user_id']))].groupby('user_id').apply(
    lambda g: (g['avg_score'] < -0.3).mean()
).mean()

# Magnesium perfection
mag_users = user_drug[user_drug['drug'] == 'magnesium']
mag_n = len(mag_users)

# Antihistamine divisiveness
ah_users = user_drug[user_drug['drug'] == 'antihistamines']
ah_pos_rate = (ah_users['avg_score'] > 0.3).mean()
ah_n = len(ah_users)

html_out = (
    "<h4>Finding 1: The Polypharmacy Plateau</h4>"
    "<p style='font-size:13px;'>"
    f"Users on 3-5 treatments report a {pos_35:.1%} positive rate, while users on 6+ report {pos_6p:.1%} "
    f"(Mann-Whitney p = {p_35_6p:.4f}). "
    "This is not statistically significant at this sample size (n=17 vs n=22), so the wide confidence intervals overlap. "
    "However, the pattern is consistent with a plausible mechanism: users on 6+ treatments carry a higher per-drug negative rate "
    f"({neg_drug_rate_6p:.1%} of their drugs rate negative vs {neg_drug_rate_35:.1%} for the 3-5 group). "
    "More treatments means more opportunities for side effects and failures, which dilute the average even when some treatments are working. "
    "This does not mean polypharmacy is bad -- it may mean that aggressive polypharmacy picks up more noise drugs that dilute the signal from the effective ones."
    "</p>"
    "<h4>Finding 2: Magnesium's Suspicious Perfection</h4>"
    "<p style='font-size:13px;'>"
    f"Magnesium shows a 100% positive rate across {mag_n} POTS users. While this is consistent with clinical expectations "
    "(POTS involves volume depletion and magnesium is well-tolerated), a perfect score is unusual and may reflect several biases: "
    "(a) users who benefit continue reporting it while those who don't stop mentioning it, (b) magnesium is often part of a larger stack and may receive "
    "credit by association, (c) it is generally well-tolerated, so negative reports are rare even if the therapeutic benefit is modest. "
    "A clinician would not find 100% efficacy for any supplement credible -- this likely reflects reporting bias rather than actual universal effectiveness."
    "</p>"
    "<h4>Finding 3: Antihistamines -- Most Tried, Most Divisive</h4>"
    "<p style='font-size:13px;'>"
    f"Antihistamines are the most commonly tried treatment class among POTS users ({ah_n} users), yet their positive rate ({ah_pos_rate:.1%}) "
    "is well below the class leaders. Given the 75% MCAS comorbidity rate in this cohort, you would expect antihistamines to perform "
    "well. The high entropy (user disagreement) suggests that antihistamine response in POTS is highly individual -- perhaps depending "
    "on whether the user's symptoms are truly mast-cell-driven. This contrasts with the community's strong recommendation of antihistamines "
    "as a first-line POTS treatment."
    "</p>"
)
display(HTML(html_out))
'''
cells.append(("code", counterintuitive_code))

# ── 12. Qualitative Evidence ──
cells.append(("md", """## 12. What Patients Are Saying *(experimental -- under development)*"""))

quotes_code = r'''
# Pull quotes from POTS users mentioning treatment combinations
quotes_raw = pd.read_sql("""
    SELECT SUBSTR(p.body_text, 1, 600) as text, date(p.post_date, 'unixepoch') as dt,
           p.user_id
    FROM posts p
    WHERE p.user_id IN (
        SELECT DISTINCT user_id FROM conditions WHERE LOWER(condition_name) LIKE '%pots%'
    )
    AND LENGTH(p.body_text) > 100
    AND (
        LOWER(p.body_text) LIKE '%combination%'
        OR LOWER(p.body_text) LIKE '%multiple%treatment%'
        OR LOWER(p.body_text) LIKE '%stack%'
        OR LOWER(p.body_text) LIKE '%together%'
        OR LOWER(p.body_text) LIKE '%regimen%'
        OR LOWER(p.body_text) LIKE '%protocol%'
        OR (LOWER(p.body_text) LIKE '%magnesium%' AND LOWER(p.body_text) LIKE '%electrolyte%')
        OR (LOWER(p.body_text) LIKE '%antihistamine%' AND LOWER(p.body_text) LIKE '%ldn%')
        OR (LOWER(p.body_text) LIKE '%beta blocker%' AND (LOWER(p.body_text) LIKE '%salt%' OR LOWER(p.body_text) LIKE '%electrolyte%'))
    )
    ORDER BY RANDOM()
    LIMIT 30
""", conn)

display(HTML("<h4>Multi-treatment experience quotes from POTS users</h4>"))

shown = 0
for _, row in quotes_raw.iterrows():
    text = row['text'].strip()
    has_treatment = any(kw in text.lower() for kw in ['helped', 'improved', 'better', 'worse', 'tried', 'combination', 'together', 'stack', 'protocol'])
    has_specific = any(kw in text.lower() for kw in ['magnesium', 'electrolyte', 'antihistamine', 'ldn', 'naltrexone', 'beta blocker', 'propranolol', 'ivabradine', 'salt', 'coq10', 'ketotifen'])
    if has_treatment and has_specific and shown < 5:
        sentences = text.split('.')
        short = '. '.join(sentences[:3]).strip()
        if len(short) > 40 and len(short) < 400:
            display(HTML(
                "<div style='border-left: 3px solid #3498db; padding: 8px 12px; margin: 8px 0; font-size:13px; background:#f8f9fa;'>"
                "<p style='margin:0;'>\"" + short.replace('"', '&quot;') + ".\"</p>"
                "<p style='margin:4px 0 0; color:#888; font-size:11px;'>-- POTS user, " + str(row['dt']) + "</p>"
                "</div>"
            ))
            shown += 1

if shown == 0:
    display(HTML("<p style='font-size:13px; color:#666;'><i>No quotes matching multi-treatment discussion criteria found in this sample. This is a limitation of text search on a one-month snapshot.</i></p>"))
elif shown < 3:
    display(HTML("<p style='font-size:13px; color:#666;'><i>" + str(shown) + " quotes found. Limited availability reflects the difficulty of finding specific multi-treatment discussion in a one-month sample.</i></p>"))
'''
cells.append(("code", quotes_code))

# ── 13. Tiered Recommendations ──
cells.append(("md", """## 13. Tiered Treatment Strategy Recommendations

Based on the combined evidence from treatment-count analysis, class-level performance, combination scoring, and individual drug outcomes, we present tiered recommendations for POTS treatment strategy in the Long COVID community."""))

tiered_recs_code = r'''
from scipy.stats import binomtest

# Build tiered recommendations from drug_stats
recs = []
for _, row in drug_stats.iterrows():
    if row['users'] < 3:
        continue
    n = int(row['users'])
    pos = int(row['pos_count'])
    rate = row['pos_rate']
    ci = (row['ci_lo'], row['ci_hi'])
    p_b = row['binom_p']

    if n >= 10 and rate > 0.6 and p_b < 0.05:
        tier = 'Strong'
    elif n >= 5 and rate > 0.5:
        tier = 'Moderate'
    elif n >= 3:
        tier = 'Preliminary'
    else:
        continue

    nnt_val = nnt(rate, 0.5) if rate > 0.5 else None
    recs.append({
        'Treatment': row['drug'],
        'Class': row['tx_class'],
        'Tier': tier,
        'N': n,
        'Pos Rate': "{:.0%}".format(rate),
        'CI': "[{:.2f}, {:.2f}]".format(ci[0], ci[1]),
        'NNT': "{:.1f}".format(nnt_val) if nnt_val else "--",
        'pos_rate_num': rate,
    })

recs_df = pd.DataFrame(recs).sort_values(['Tier', 'pos_rate_num'], ascending=[True, False])

for tier_name in ['Strong', 'Moderate', 'Preliminary']:
    tier_df = recs_df[recs_df['Tier'] == tier_name]
    if len(tier_df) == 0:
        continue
    tier_desc = {
        'Strong': 'n >= 10, positive rate > 60%, p < 0.05 vs 50% baseline',
        'Moderate': 'n >= 5, positive rate > 50%',
        'Preliminary': 'n >= 3, signal present but underpowered'
    }
    display(HTML("<h4>" + tier_name + " Evidence (" + tier_desc[tier_name] + ")</h4>"))
    display(HTML(
        tier_df[['Treatment', 'Class', 'N', 'Pos Rate', 'CI', 'NNT']]
        .style.set_properties(**{'text-align': 'right', 'font-size': '12px'})
        .set_properties(subset=['Treatment', 'Class'], **{'text-align': 'left'})
        .hide(axis='index')
        .to_html()
    ))
'''
cells.append(("code", tiered_recs_code))

tiered_chart_code = r'''
# ── CHART: Tiered recommendation summary ──
tier_colors_chart = {'Strong': '#27ae60', 'Moderate': '#f39c12', 'Preliminary': '#95a5a6'}
tiers_to_show = [t for t in ['Strong', 'Moderate', 'Preliminary'] if len(recs_df[recs_df['Tier']==t]) > 0]

n_tiers = len(tiers_to_show)
if n_tiers > 0:
    max_items = max(len(recs_df[recs_df['Tier']==t]) for t in tiers_to_show)
    fig, axes = plt.subplots(1, n_tiers, figsize=(5 * n_tiers, max(4, min(max_items, 15) * 0.45)),
                              sharey=False)
    if n_tiers == 1:
        axes = [axes]

    for idx, tier_name in enumerate(tiers_to_show):
        ax = axes[idx]
        tier_df = recs_df[recs_df['Tier'] == tier_name].sort_values('pos_rate_num', ascending=True).tail(15)

        y_pos = np.arange(len(tier_df))
        ax.barh(y_pos, tier_df['pos_rate_num'] * 100, color=tier_colors_chart[tier_name],
                edgecolor='white', height=0.6)
        ax.axvline(50, color='grey', linestyle='--', alpha=0.5)

        ax.set_yticks(y_pos)
        labels = ["{} (n={})".format(r['Treatment'], r['N']) for _, r in tier_df.iterrows()]
        ax.set_yticklabels(labels, fontsize=9)
        ax.set_xlabel('Positive Rate (%)', fontsize=10)
        ax.set_title(tier_name, fontsize=11, fontweight='bold', color=tier_colors_chart[tier_name])
        ax.set_xlim(0, 105)

    plt.suptitle('Treatment Recommendations by Evidence Tier', fontsize=13, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.show()
'''
cells.append(("code", tiered_chart_code))

# ── 14. Conclusion ──
cells.append(("md", """## 14. Conclusion

The data from this one-month snapshot of r/covidlonghaulers delivers a clear message about POTS treatment strategy: **monotherapy is not enough.**

POTS patients who try only one treatment report a positive outcome rate of 29% -- worse than a coin flip, worse than the broader Long COVID community, and consistent with the frustration that permeates POTS discussions online. But patients who diversify across 3-5 treatments from different mechanistic classes report a 67-77% positive rate. This is not a small difference -- the NNT is roughly 2-3, meaning for every 2-3 patients who adopt a multi-treatment strategy instead of monotherapy, one additional patient reports a positive outcome.

The specific combinations that drive this signal are remarkably consistent. **Volume/electrolyte support** (magnesium, electrolytes, potassium) forms the foundation, consistent with POTS being fundamentally a volume-regulation disorder. **Antihistamine/mast cell** interventions (antihistamines, ketotifen, famotidine) target the 75% MCAS overlap found in Notebook 2 -- though individual response varies widely. **Immune modulation** (LDN, methylene blue) and **mitochondrial/antioxidant support** (CoQ10, NAC, vitamin C) round out the successful regimens.

The most surprising finding is the polypharmacy plateau: users on 6+ treatments do slightly worse than those on 3-5, not because more is harmful, but because aggressive polypharmacy accumulates failed treatments that dilute the signal from effective ones. The data argues for strategic diversity -- 3-5 treatments across different classes -- rather than indiscriminate escalation. A reasonable starting framework based on this data would be: (1) volume support as foundation, (2) antihistamine/mast cell management for the MCAS component, (3) one immune modulator (LDN being the most popular and well-rated), and optionally (4) a mitochondrial support supplement.

What we cannot answer: whether the multi-treatment advantage reflects genuine pharmacological synergy, or simply that engaged patients who try more things are the same patients who eventually find something that works. The survivorship bias is real -- patients whose first treatment worked may never post again, while those who keep searching remain visible. Prospective data would be needed to disentangle engagement from efficacy. But for a POTS patient currently struggling on monotherapy, this data provides community-sourced evidence that broadening the treatment approach is associated with substantially better outcomes."""))

# ── 15. Limitations ──
cells.append(("md", """## 15. Research Limitations

1. **Selection bias:** Users of r/covidlonghaulers are self-selected, English-speaking, internet-literate, and likely skew toward more severe, longer-duration illness. POTS patients who recovered quickly or who manage their condition without supplements are underrepresented.

2. **Reporting bias:** Users are more likely to post about treatments that provoked strong reactions (positive or negative). Treatments that were unremarkable are underreported, inflating both tails of the outcome distribution. Magnesium's 100% positive rate almost certainly reflects this -- users who noticed no effect simply stopped mentioning it.

3. **Survivorship bias:** This is particularly acute for the treatment count analysis. Users who found an effective first-line treatment may stop posting (and appear as low-count, potentially satisfied users we never see). Users who keep posting and accumulating treatments are a mix of persistent searchers and engaged community members. The direction of the treatment-count effect may be partly an artifact of who remains visible.

4. **Recall bias:** Users report on treatments from memory, which may be months or years old. Recent treatments and dramatic responses are more salient. Gradual improvements are underreported.

5. **Confounding by severity:** Users with more conditions (the POTS-MCAS-dysautonomia triad) may both try more treatments AND have different baseline prognoses. Treatment count is confounded with disease burden. We controlled for treatment count in the logistic regression but cannot fully separate these effects.

6. **No control group:** There is no untreated comparison group. The 50% baseline used for binomial tests is an arbitrary threshold, not a true placebo rate. Without knowing what happens to POTS patients who try no treatments, we cannot calculate true treatment effects.

7. **Sentiment vs efficacy:** Community sentiment captures the full treatment experience (efficacy + tolerability + access + cost + expectations), not isolated efficacy. A treatment can be effective but poorly tolerated (beta blockers), or well-tolerated but ineffective, and both would produce mixed sentiment.

8. **Temporal snapshot:** One month of data captures a moment in time, not treatment trajectories. A treatment that was positive in month 1 may be negative by month 6. We cannot assess durability of response, and the treatment combinations we observe are cross-sectional (what users are taking now), not longitudinal (the order in which they were tried)."""))

# ── Disclaimer ──
cells.append(("code", """display(HTML(
    '<div style="font-size: 1.2em; font-weight: bold; font-style: italic; margin-top: 30px; '
    'padding: 15px; border: 1px solid #ccc; background: #f9f9fa;">'
    'These findings reflect reporting patterns in online communities, not population-level '
    'treatment effects. This is not medical advice.'
    '</div>'
))"""))

# ── Build and execute ──
nb = build_notebook(cells=cells, db_path=DB_PATH)
output_stem = os.path.join(os.path.dirname(__file__), "3_pots_treatment_strategy")
html_path = execute_and_export(nb, output_stem)
print(f"Done! HTML exported to: {html_path}")
