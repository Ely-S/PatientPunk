"""
Reproducibility build script for RCT historical validation paper.

Generates Figure 1 (paired horizontal bar chart), Table 2 (data sources),
and Table 3 (per-drug response composition) from:

    "A Methodology for Gathering Real-World Evidence at Scale"

Usage:
    cd data_RCT_historical_validation/
    python _build_paper_figures.py

Output:
    output/paper_figures.ipynb            - source notebook
    output/paper_figures_executed.ipynb   - executed notebook
    output/paper_figures.html             - HTML export (code hidden)
    output/figure1.png                    - Figure 1 standalone image
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__) or ".")
from build_notebook import build_notebook, execute_and_export

cells = []

# ────────────────────────────────────────────────────────────────────
# INTRODUCTION
# ────────────────────────────────────────────────────────────────────
cells.append(("md", """# RCT Historical Validation — Reproducibility Figures

This notebook reproduces **Figure 1**, **Table 2**, and **Table 3** from the paper.

- **Figure 1**: Pre-publication community sentiment — responders vs non-responders for 6 drugs
- **Table 2**: Data sources by drug (database, window, post/user/report counts)
- **Table 3**: Per-drug response composition with Wilson 95% CIs and binomial test p-values

**Method**: For each drug, we extract all treatment-sentiment reports from r/covidlonghaulers
posts dated *before* the relevant clinical trial published. Each user contributes one data
point per drug (best-report dedup: positive > mixed > neutral > negative; strong > moderate > weak
tiebreak). We then test whether the proportion of responders (positive sentiment) differs from 50%.
"""))

# ────────────────────────────────────────────────────────────────────
# SETUP CODE (produces zero visible output)
# ────────────────────────────────────────────────────────────────────
cells.append(("code", r"""
from pathlib import Path
import math
from scipy.stats import binomtest
from statsmodels.stats.proportion import proportion_confint as wilson

# ── Connect to all 5 analysis databases ──
DB_DIR = Path(DB_PATH).parent

db_paths = {
    "may_sept_2021":     DB_DIR / "famotidine_loratadine_prednisone_may_sept_2021.db",
    "4mo_pre_stop_pasc": DB_DIR / "paxlovid_pre_stop_pasc_4mo.db",
    "year_2021":         DB_DIR / "colchicine_naltrexone_year_2021.db",
    "jan_2022":          DB_DIR / "naltrexone_jan_2022.db",
    "polina_onemonth":   DB_DIR / "corpus_baseline_onemonth.db",
}
slices = {k: sqlite3.connect(v.as_posix()) for k, v in db_paths.items()}

# ── Ranking for best-report-per-user dedup ──
SENT_RANK = {"positive": 3, "mixed": 2, "neutral": 1, "negative": 0}
SIG_RANK  = {"strong": 2, "moderate": 1, "weak": 0, "n/a": 0, None: 0, "": 0}

def best_per_user_drug(c, where_extra="", params=()):
    # Return one (rank_tuple, sentiment, drug) per (user, drug), keeping the best report.
    rows = c.execute(f'''
        SELECT tr.user_id, lower(t.canonical_name), tr.sentiment, tr.signal_strength, p.post_date
        FROM treatment_reports tr
        JOIN treatment t ON tr.drug_id = t.id
        JOIN posts p ON tr.post_id = p.post_id
        WHERE 1=1 {where_extra}
    ''', params).fetchall()
    best = {}
    for uid, drug, sent, sig, _d in rows:
        k = (SENT_RANK.get(sent, -1), SIG_RANK.get(sig, 0))
        key = (uid, drug)
        if key not in best or k > best[key][0]:
            best[key] = (k, sent, drug)
    return list(best.values())

def cohens_h(p1, p2):
    # Cohen's h effect size for two proportions.
    return 2 * (math.asin(math.sqrt(p1)) - math.asin(math.sqrt(p2)))

cutoff_2021_10 = 1633046400  # 2021-10-01 UTC (Glynne publication)

# ── Corpus baseline (multi-drug one-month sample, excluding the test drugs) ──
TEST_DRUGS = {"famotidine", "loratadine", "cetirizine", "prednisone",
              "paxlovid", "colchicine", "naltrexone"}
_om_all = best_per_user_drug(slices["polina_onemonth"])
_om_baseline_recs = [r for r in _om_all if r[2] not in TEST_DRUGS]
SHARED_BASELINE_N   = len(_om_baseline_recs)
SHARED_BASELINE_POS = sum(1 for r in _om_baseline_recs if r[1] == "positive")
SHARED_BASELINE     = SHARED_BASELINE_POS / SHARED_BASELINE_N
SHARED_BASELINE_LO, SHARED_BASELINE_HI = wilson(
    SHARED_BASELINE_POS, SHARED_BASELINE_N, alpha=0.05, method="wilson")
"""))

# ────────────────────────────────────────────────────────────────────
# FIGURE 1: Data extraction + paired horizontal bar chart
# ────────────────────────────────────────────────────────────────────
cells.append(("code", r"""
# ── Per-drug data extraction (6 drugs, cetirizine excluded — no direct trial) ──
drug_specs = [
    ("famotidine",  "may_sept_2021",     "AND p.post_date < ?", (cutoff_2021_10,), "+",
     "Glynne 2021"),
    ("loratadine",  "may_sept_2021",     "AND p.post_date < ?", (cutoff_2021_10,), "+",
     "Glynne 2021"),
    ("prednisone",  "may_sept_2021",     "AND p.post_date < ?", (cutoff_2021_10,), "0",
     "2024 meta-analysis"),
    ("paxlovid",    "4mo_pre_stop_pasc", "", (), "0",
     "STOP-PASC 2024"),
    ("colchicine",  "year_2021",         "", (), "0",
     "Bassi 2025"),
]

def _sentiment_breakdown(drug_label, sentiments, trial_dir, paper_ref):
    # Compute response stats for one drug.
    n = len(sentiments)
    pos  = sum(1 for s in sentiments if s == "positive")
    neg  = sum(1 for s in sentiments if s == "negative")
    neu  = sum(1 for s in sentiments if s == "neutral")
    mix  = sum(1 for s in sentiments if s == "mixed")
    nonr = neg + neu + mix
    pos_lo, pos_hi   = wilson(pos,  n, alpha=0.05, method="wilson") if n else (0, 0)
    nonr_lo, nonr_hi = wilson(nonr, n, alpha=0.05, method="wilson") if n else (0, 0)
    pval = binomtest(pos, n, 0.5, alternative="two-sided").pvalue if n else 1.0
    h = cohens_h(pos/n, 0.5) if n else 0.0
    return {
        "drug": drug_label, "n": n, "trial_dir": trial_dir, "paper": paper_ref,
        "pos": pos, "neg": neg, "neu": neu, "mix": mix, "nonr": nonr,
        "pos_pct": pos/n*100 if n else 0,
        "pos_lo": pos_lo*100, "pos_hi": pos_hi*100,
        "nonr_pct": nonr/n*100 if n else 0,
        "nonr_lo": nonr_lo*100, "nonr_hi": nonr_hi*100,
        "pval": pval, "h": h,
    }

resp_rows = []
for drug, sl, wx, p, td, ref in drug_specs:
    recs = best_per_user_drug(slices[sl], wx, p)
    recs = [r for r in recs if r[2] == drug]
    resp_rows.append(_sentiment_breakdown(drug, [r[1] for r in recs], td, ref))

# Naltrexone: combined across year_2021 + jan_2022
def _nalt_recs(slice_key):
    return slices[slice_key].execute('''
        SELECT tr.user_id, tr.sentiment, tr.signal_strength
        FROM treatment_reports tr JOIN treatment t ON tr.drug_id = t.id
        WHERE lower(t.canonical_name) IN ('naltrexone', 'low dose naltrexone', 'ldn')
    ''').fetchall()
nalt_best = {}
for uid, sent, sig in _nalt_recs("year_2021") + _nalt_recs("jan_2022"):
    k = (SENT_RANK.get(sent, -1), SIG_RANK.get(sig, 0))
    if uid not in nalt_best or k > nalt_best[uid][0]:
        nalt_best[uid] = (k, sent)
resp_rows.append(_sentiment_breakdown(
    "naltrexone", [v[1] for v in nalt_best.values()], "+", "O'Kelly 2022"))

resp_df = (pd.DataFrame(resp_rows)
           .sort_values("pos_pct", ascending=False)
           .reset_index(drop=True))

# ── Figure 1: Paired horizontal bars with trial-direction tags ──
from matplotlib.patches import Patch

fig, ax = plt.subplots(figsize=(12, 5.5))
y = np.arange(len(resp_df))[::-1]
bar_h = 0.36

# Responder bars (green)
ax.barh(y - bar_h/2, resp_df["pos_pct"], height=bar_h,
        color="#2ecc71", edgecolor="black", linewidth=0.5,
        label="% responders (positive)")
ax.errorbar(resp_df["pos_pct"], y - bar_h/2,
            xerr=[resp_df["pos_pct"] - resp_df["pos_lo"],
                  resp_df["pos_hi"] - resp_df["pos_pct"]],
            fmt="none", ecolor="#1e1e1e", elinewidth=1.2, capsize=3.5, capthick=1.2)

# Non-responder bars (red)
ax.barh(y + bar_h/2, resp_df["nonr_pct"], height=bar_h,
        color="#e74c3c", edgecolor="black", linewidth=0.5,
        label="% non-responders (neg + neu + mix)")
ax.errorbar(resp_df["nonr_pct"], y + bar_h/2,
            xerr=[resp_df["nonr_pct"] - resp_df["nonr_lo"],
                  resp_df["nonr_hi"] - resp_df["nonr_pct"]],
            fmt="none", ecolor="#1e1e1e", elinewidth=1.2, capsize=3.5, capthick=1.2)

# Value labels
for i, r in resp_df.iterrows():
    ax.text(r["pos_pct"] + 1.5, y[i] - bar_h/2, f"{r['pos_pct']:.0f}%",
            va="center", ha="left", fontsize=9)
    ax.text(r["nonr_pct"] + 1.5, y[i] + bar_h/2, f"{r['nonr_pct']:.0f}%",
            va="center", ha="left", fontsize=9)

ax.set_yticks(y)
ax.set_yticklabels([f"{r['drug']}\n(n={r['n']})" for _, r in resp_df.iterrows()], fontsize=10)
ax.set_xlim(0, max(resp_df["pos_hi"].max(), resp_df["nonr_hi"].max()) + 22)
ax.set_xlabel("% of users (95% Wilson CI)")
ax.set_title("Pre-publication community sentiment: responders vs non-responders by drug",
             fontsize=12, fontweight="bold")
ax.grid(axis="x", alpha=0.3)

# Trial-direction tags in right margin
TAG_STYLE = {
    "+": ("trial: positive", "#27ae60"),
    "0": ("trial: null",     "#c0392b"),
}
for i, r in resp_df.iterrows():
    label, color = TAG_STYLE.get(r["trial_dir"], (f"trial: {r['trial_dir']}", "#7f8c8d"))
    ax.text(1.01, y[i], label, transform=ax.get_yaxis_transform(),
            va="center", ha="left", fontsize=9.5, family="monospace",
            color=color, fontweight="bold")

legend_elems = [
    Patch(facecolor="#2ecc71", edgecolor="black", linewidth=0.5,
          label="% responders (positive)"),
    Patch(facecolor="#e74c3c", edgecolor="black", linewidth=0.5,
          label="% non-responders (neg + neu + mix)"),
    Patch(facecolor="#27ae60", label="trial: positive"),
    Patch(facecolor="#c0392b", label="trial: null"),
]
ax.legend(handles=legend_elems, loc="lower center", bbox_to_anchor=(0.5, -0.32),
          ncol=3, fontsize=9, frameon=True)
plt.tight_layout()
plt.savefig("figure1.png", dpi=150, bbox_inches="tight")
plt.show()
"""))

# ────────────────────────────────────────────────────────────────────
# TABLE 2: Data sources
# ────────────────────────────────────────────────────────────────────
cells.append(("md", """## Data sources and methodology

**Definitions:**
- **Responder**: user's best-report sentiment is `positive`.
- **Non-responder**: user's best-report sentiment is anything else (negative, neutral, or mixed).
- **Corpus baseline (65.8%)**: the typical drug-mention positive share on r/covidlonghaulers, computed from a cost-bounded multi-drug one-month sample excluding the seven test drugs.

Each user contributes one data point per drug (best-report dedup). All sentiment data is restricted to posts dated *before* the relevant trial's publication date."""))

cells.append(("code", r"""
# ── Table 2: Data sources by drug ──
_src_rows = [
    ("famotidine",  "famotidine_loratadine_prednisone_may_sept_2021",
     "2021-05-01", "2021-09-30", 88077, 207, 493, "Glynne et al. Oct 2021"),
    ("loratadine",  "famotidine_loratadine_prednisone_may_sept_2021",
     "2021-05-01", "2021-09-30", 88077, 107, 222, "Glynne et al. Oct 2021"),
    ("prednisone",  "famotidine_loratadine_prednisone_may_sept_2021",
     "2021-05-01", "2021-09-30", 88077, 176, 374, "Utrero-Rico et al. 2021"),
    ("paxlovid",    "paxlovid_pre_stop_pasc_4mo",
     "2024-03-01", "2024-06-06", 106889, 153, 341, "STOP-PASC Jun 2024"),
    ("colchicine",  "colchicine_naltrexone_year_2021",
     "2021-01-01", "2021-12-31", 217866, 40, 103, "Bassi et al. 2025"),
    ("naltrexone",  "colchicine_naltrexone_year_2021 + naltrexone_jan_2022",
     "2021-01-01", "2022-01-30", 244036, 76, 270, "O'Kelly et al. Jul 2022"),
]
src_df = pd.DataFrame(_src_rows, columns=["drug", "database", "window_start", "window_end",
                                           "total_posts", "unique_users", "treatment_reports",
                                           "trial_cutoff"])

src_html = "<table style='border-collapse:collapse; width:100%; font-size:0.9em; margin:12px 0;'>"
src_html += ("<tr style='background:#34495e; color:white;'>"
             "<th style='padding:6px 10px;'>Drug</th>"
             "<th style='padding:6px 10px;'>Database</th>"
             "<th style='padding:6px 10px;'>Window</th>"
             "<th style='padding:6px 10px;'>Total posts</th>"
             "<th style='padding:6px 10px;'>Unique users</th>"
             "<th style='padding:6px 10px;'>Treatment reports</th>"
             "<th style='padding:6px 10px;'>Pre-publication cutoff</th></tr>")
for i, (_, r) in enumerate(src_df.iterrows()):
    bg = "#fff" if i % 2 == 0 else "#f8f9fa"
    src_html += (f"<tr style='background:{bg};'>"
                 f"<td style='padding:6px 10px; font-weight:bold;'>{r['drug']}</td>"
                 f"<td style='padding:6px 10px; font-size:0.85em;'>{r['database']}</td>"
                 f"<td style='padding:6px 10px;'>{r['window_start']} to {r['window_end']}</td>"
                 f"<td style='padding:6px 10px; text-align:center;'>{r['total_posts']:,}</td>"
                 f"<td style='padding:6px 10px; text-align:center;'>{r['unique_users']}</td>"
                 f"<td style='padding:6px 10px; text-align:center;'>{r['treatment_reports']}</td>"
                 f"<td style='padding:6px 10px; font-size:0.85em;'>{r['trial_cutoff']}</td></tr>")
src_html += "</table>"
src_html += ("<p style='font-size:0.85em; color:#777; margin-top:4px;'>"
             "Total posts = all r/covidlonghaulers posts in the database window. "
             "Unique users = distinct users with at least one treatment report for this drug. "
             "Treatment reports = total sentiment-tagged mentions (before dedup). "
             "Naltrexone spans two databases to maximise pre-publication coverage.</p>")

display(HTML("<h3>Table 2 &mdash; Data sources by drug</h3>" + src_html))
"""))

# ────────────────────────────────────────────────────────────────────
# TABLE 3: Per-drug response composition
# ────────────────────────────────────────────────────────────────────
cells.append(("code", r"""
# ── Table 3: Response composition ──
table_df = resp_df[["drug", "trial_dir", "paper", "n", "pos", "pos_pct", "pos_lo", "pos_hi",
                    "nonr", "nonr_pct", "nonr_lo", "nonr_hi",
                    "mix", "pval", "h"]].copy()
def _fmt_pct(v): return f"{v:.1f}%"
def _fmt_ci(lo, hi): return f"[{lo:.1f}%, {hi:.1f}%]"
table_df["% responders"]      = table_df["pos_pct"].apply(_fmt_pct)
table_df["responders 95% CI"] = [_fmt_ci(lo, hi) for lo, hi in zip(table_df["pos_lo"], table_df["pos_hi"])]
table_df["% non-resp"]        = table_df["nonr_pct"].apply(_fmt_pct)
table_df["non-resp 95% CI"]   = [_fmt_ci(lo, hi) for lo, hi in zip(table_df["nonr_lo"], table_df["nonr_hi"])]
table_df["p (vs 50%)"]        = table_df["pval"].apply(lambda v: f"{v:.4f}" if v >= 0.001 else f"{v:.2e}")

display_table = table_df[["drug", "paper", "n",
                          "% responders", "responders 95% CI",
                          "nonr", "% non-resp", "non-resp 95% CI",
                          "p (vs 50%)"]].rename(columns={
    "nonr": "-/0/~",
})
display(HTML("<h3>Table 3 &mdash; Per-drug response composition (pre-publication data only)</h3>"
             "<p style='font-size:0.9em; color:#555;'>Each row: user-level best-report dedup. "
             "Responders = positive; non-responders = negative + neutral + mixed. "
             "p-values from two-sided binomial test against 50% null "
             "(H&#8320;: responders = non-responders).</p>"
             + display_table.to_html(index=False)))
"""))

# ────────────────────────────────────────────────────────────────────
# BUILD + EXECUTE
# ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    nb = build_notebook(cells=cells, db_path="data/corpus_baseline_onemonth.db")
    html_path = execute_and_export(nb, "output/paper_figures")
    print(f"\nDone. Open {html_path} to view the results.")
