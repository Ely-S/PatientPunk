# -*- coding: utf-8 -*-
"""Build the verbose 'What predicts Mestinon response?' notebook via the
research-assistant skill conventions (notebooks/build_notebook.py).

All feature mining is pre-baked into mestinon_predict.db (build_predict_data.py),
so the notebook cells contain NO regex — only stats, charts, and narrative.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PKG = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("PP_DATA_DIR", PKG / "data"))  # source DBs are not committed; see ../README.md and MANIFEST.csv
sys.path.insert(0, str(REPO / "docs" / "RCT_historical_validation"))  # build_notebook lives here
from build_notebook import build_notebook, execute_and_export  # noqa: E402

DB = DATA / "mestinon_predict.db"
OUT = PKG / "notebooks" / "mestinon_what_predicts_response"

cells = []
def md(s): cells.append(("md", s))
def code(s): cells.append(("code", s))

# ── helpers cell ───────────────────────────────────────────────────────────────
code('''
import datetime
import statsmodels.api as sm
from scipy.stats import fisher_exact, kruskal
from statsmodels.stats.outliers_influence import variance_inflation_factor

def cohen_h(p1, p2):
    return 2*np.arcsin(np.sqrt(p1)) - 2*np.arcsin(np.sqrt(p2))

def callout(text, sev="caution"):
    color = {"caution": "#b9770e", "unreliable": "#922b21", "caveat": "#5d6d7e"}[sev]
    icon = {"caution": "&#9888;", "unreliable": "&#9940;", "caveat": "&#9432;"}[sev]
    display(HTML(f'<div style="border-left:4px solid {color}; background:#fbfcfc; '
                 f'padding:8px 12px; margin:6px 0; color:#1c2833;">{icon} <b>{sev.upper()}</b> &mdash; {text}</div>'))

df = pd.read_sql("select * from user_features", conn)
reps = pd.read_sql("select * from reports", conn)
N = len(df); NR = int(df.responder.sum())
CORPUS_ORDER = ["covidlonghaulers", "dysautonomia", "r/cfs", "Phoenix Rising"]
POP = {"covidlonghaulers":"long COVID", "dysautonomia":"POTS/dysautonomia",
       "r/cfs":"ME/CFS (Reddit)", "Phoenix Rising":"ME/CFS (forum)"}
PALETTE = {"covidlonghaulers":"#2e86c1", "dysautonomia":"#17a589", "r/cfs":"#ca6f1e", "Phoenix Rising":"#884ea0"}
''')

# ── research question + abstract ───────────────────────────────────────────────
md('**Research Question:** *"What predicts a positive response to Mestinon (pyridostigmine) in patient-reported data — and what does that imply for whether the drug should be formally studied?"*')

md('''# What Predicts Mestinon Response?

**Abstract.** Mestinon (pyridostigmine — a cholinesterase inhibitor approved for myasthenia gravis) is used off-label for the exercise intolerance and dysautonomia of long COVID and ME/CFS (myalgic encephalomyelitis / chronic fatigue syndrome). Pooling **1,476 patients** who discussed it across four online communities, we ask what distinguishes the roughly half who report benefit from the half who do not. The short answer: **almost nothing about the patient predicts response.** A logistic model over patient and regimen features explains little (McFadden pseudo-R² = 0.12). Its single strongest term is circular — reporting a side effect, mined from the same text that sets the outcome — and every other signal is about **how the drug was used**, not who the patient is: titrating the dose upward (the strongest clean predictor, ~2.8× the odds), multi-daily dosing, and mentioning a specific dose. No baseline patient phenotype emerged. The largest single driver of the response rate is not a patient feature at all but **which community was sampled** (31% in a chronic-illness forum vs ~50–53% elsewhere). The practical implication is that the observational "~50% works" figure is shaped by tolerability, dosing, and selection rather than a non-responder phenotype — which is precisely the ambiguity a controlled trial exists to resolve.''')

# ── section 1: why this matters ────────────────────────────────────────────────
md('''## 1. Why this question matters

Mestinon is a generic, off-patent drug with no commercial sponsor positioned to fund a large trial for these new uses. The conditions it is used for — long COVID, ME/CFS, dysautonomia — have essentially no approved therapies. That combination (cheap, established safety, real demand, unmet need, no commercial path) is the textbook profile of a stranded drug-repurposing candidate.

In that setting the question "what predicts response?" is not academic. If the patients who *don't* respond simply never reached an adequate dose or quit before the drug could work, then the observational "about half respond" rate **understates** the drug — and that is a fixable trial-design problem, not a reason to dismiss it. If instead non-response reflects a fixed patient phenotype, the drug is genuinely a coin flip. Distinguishing these two possibilities is the entire decision. This notebook asks how far patient-reported data can take us toward an answer — and is honest about where it cannot.''')

# ── section 2: baseline ────────────────────────────────────────────────────────
md('''## 2. Baseline: response across four communities

Before asking *what* predicts response, we establish the overall picture. Each patient is reduced to one data point — their average sentiment across every Mestinon report they wrote — and counted a **responder** if that average is strongly positive (>0.7, i.e. their reports are predominantly positive). "Response" here means *self-reported benefit*, not a measured clinical outcome.''')

code('''
rows = []
for c in CORPUS_ORDER:
    s = df[df.corpus==c]; k = int(s.responder.sum()); n = len(s)
    lo, hi = wilson_ci(k, n)
    rows.append({"community": c, "population": POP[c], "n_users": n,
                 "responder_%": round(100*k/n,1), "ci_low": round(100*lo,1), "ci_high": round(100*hi,1)})
base = pd.DataFrame(rows)
k_all = NR; lo_all, hi_all = wilson_ci(k_all, N)

fig, ax = plt.subplots(figsize=(10, 4.6))
y = np.arange(len(base))[::-1]
for i, r in base.iterrows():
    yy = y[i]
    ax.plot([r.ci_low, r.ci_high], [yy, yy], color=PALETTE[r["community"]], lw=2.5, zorder=2)
    ax.scatter(r["responder_%"], yy, s=140, color=PALETTE[r["community"]], zorder=3,
               edgecolor="white", linewidth=1.5)
    ax.text(r.ci_high+1.2, yy, f'{r["responder_%"]:.0f}%  (n={r.n_users})', va="center", fontsize=10)
ax.axvline(50, color="#7f8c8d", ls="--", lw=1, zorder=1)
ax.text(50, len(base)-0.35, " chance (50%)", color="#7f8c8d", fontsize=9, ha="left")
ax.set_yticks(y); ax.set_yticklabels([f'{r["community"]}\\n{r["population"]}' for _, r in base.iterrows()], fontsize=10)
ax.set_xlabel("Responder rate (%) with 95% Wilson CI"); ax.set_xlim(0, 80)
ax.set_title("Mestinon responder rate by community", fontsize=13, fontweight="bold")
sns.despine(left=True); plt.tight_layout(); plt.show()

sty = base.rename(columns={"responder_%":"responder %"}).style.hide(axis="index").format({
    "ci_low":"{:.1f}", "ci_high":"{:.1f}"}).set_caption("Responder rate per community (user-level)")
display(sty)
''')

md('''**What this shows.** Three of the four communities land in a tight ~50–53% band; the chronic-illness forum (Phoenix Rising) sits markedly lower at 31%. Crucially, the three Reddit communities span very different conditions (long COVID, POTS, ME/CFS) yet agree on the rate — so the *condition* is not what moves the number. Pooled, 50.9% of patients are responders, statistically indistinguishable from a coin flip. That "half and half" is the thing we now try to predict.''')

# ── section 3: univariate ──────────────────────────────────────────────────────
md('''## 3. Which features track response, one at a time?

We start with simple two-group comparisons: for each patient feature, do patients *with* the feature respond at a different rate than those *without* it? Every comparison reports Fisher's exact test and Cohen's *h* (effect size for proportions). The features fall into two families — **tolerability** (whether a side effect was reported) and **regimen** (multi-daily dosing, titrating up, reaching ≥60 mg, trial length).''')

code('''
FEATS = [("side_effect","Reported a side effect"), ("multi_daily","Multi-daily dosing (TID/BID)"),
         ("titrate_up","Titrated dose upward"), ("reached_60","Reached ≥60 mg"),
         ("mentions_dose","Mentioned a dose"), ("short_trial","Quit within 2 weeks"),
         ("titrate_down","Forced dose reduction")]
rows = []
for f, lab in FEATS:
    a = df[df[f]==1]; b = df[df[f]==0]
    p1, p2 = a.responder.mean(), b.responder.mean()
    _, p = fisher_exact([[a.responder.sum(), len(a)-a.responder.sum()],
                         [b.responder.sum(), len(b)-b.responder.sum()]])
    rows.append({"feature":lab, "n_with":len(a), "resp_with":100*p1, "resp_without":100*p2,
                 "Fisher p":p, "Cohen h":cohen_h(p1,p2)})
uni = pd.DataFrame(rows)

fig, ax = plt.subplots(figsize=(11, 5))
yy = np.arange(len(uni))[::-1]; h = 0.36
for i, r in uni.iterrows():
    f = FEATS[i][0]
    a = df[df[f]==1]; b = df[df[f]==0]
    la, ha = wilson_ci(int(a.responder.sum()), len(a)); lb, hb = wilson_ci(int(b.responder.sum()), len(b))
    ax.barh(yy[i]+h/2, r.resp_with, height=h, color="#2e86c1",
            xerr=[[r.resp_with-100*la],[100*ha-r.resp_with]], error_kw=dict(lw=1, ecolor="#566573"),
            label="with feature" if i==0 else None)
    ax.barh(yy[i]-h/2, r.resp_without, height=h, color="#aeb6bf",
            xerr=[[r.resp_without-100*lb],[100*hb-r.resp_without]], error_kw=dict(lw=1, ecolor="#566573"),
            label="without feature" if i==0 else None)
ax.axvline(50, color="#7f8c8d", ls="--", lw=1)
ax.set_yticks(yy); ax.set_yticklabels(uni.feature, fontsize=10)
ax.set_xlabel("Responder rate (%) with 95% CI"); ax.set_xlim(0, 85)
ax.set_title("Responder rate with vs. without each feature", fontsize=13, fontweight="bold")
ax.legend(loc="lower right", frameon=True); sns.despine(left=True); plt.tight_layout(); plt.show()

disp = uni.copy()
disp["NNT"] = [nnt(r.resp_with/100, r.resp_without/100) if r["Cohen h"]>0 else None for _, r in uni.iterrows()]
display(disp.style.hide(axis="index").format({
    "resp_with":"{:.0f}%","resp_without":"{:.0f}%","Fisher p":"{:.3f}","Cohen h":"{:+.2f}","NNT":"{}"})
    .set_caption("Univariate association of each feature with response"))
''')

md('''**What this shows.** Two genuinely positive regimen signals stand out: **titrating the dose upward** (68% vs 49% respond, p<0.001, NNT ≈ 5) and **reaching ≥60 mg** (63% vs 50%, p=0.015). Quitting within two weeks goes the other way (21% vs 51%). The single largest association is **reporting a side effect** (33% vs 67%) — but read that one carefully.''')

callout_cell = '''
callout("The side-effect association is partly <b>circular</b>. The side-effect field is mined from the same "
        "post text that sets the sentiment label — a post that says \\"it gave me cramps so I stopped\\" "
        "generates both a side-effect flag and a negative sentiment. So this is not independent evidence that "
        "side effects <i>cause</i> non-response; it is partly the same statement counted twice. The regimen "
        "signals (titration, dose) do not share text with the outcome and are the more trustworthy ones.", "caution")
'''
code(callout_cell)

# ── section 4: logistic ────────────────────────────────────────────────────────
md('''## 4. What predicts response, controlling for everything at once?

Univariate signals can be confounded — maybe people who titrate up are just from a different community. A logistic regression estimates each feature's independent contribution, holding the others (and the community) constant. Odds ratios above 1 favor response; below 1 disfavor it.''')

code('''
d = df.copy()
preds = ["side_effect","multi_daily","titrate_up","mentions_dose","has_duration"]
X = d[preds].astype(float).copy()
for c in ["dysautonomia","r/cfs","Phoenix Rising"]:
    X["corpus_"+c.split()[0].replace("/","")] = (d.corpus==c).astype(float)
Xc = sm.add_constant(X)
res = sm.Logit(d.responder, Xc).fit(disp=0)
ortab = pd.DataFrame({"odds_ratio": np.exp(res.params), "ci_low": np.exp(res.conf_int()[0]),
                      "ci_high": np.exp(res.conf_int()[1]), "p": res.pvalues}).drop("const")
labmap = {"side_effect":"Reported a side effect","multi_daily":"Multi-daily dosing","titrate_up":"Titrated up",
          "mentions_dose":"Mentioned a dose","has_duration":"Mentioned trial length",
          "corpus_dysautonomia":"Community: dysautonomia","corpus_rcfs":"Community: r/cfs",
          "corpus_Phoenix":"Community: Phoenix Rising"}
ortab.index = [labmap.get(i,i) for i in ortab.index]

fig, ax = plt.subplots(figsize=(10, 5))
yy = np.arange(len(ortab))[::-1]
for i, (name, r) in enumerate(ortab.iterrows()):
    sig = r.p < 0.05
    col = "#1a5276" if (sig and r.odds_ratio>1) else ("#922b21" if (sig and r.odds_ratio<1) else "#aeb6bf")
    ax.plot([r.ci_low, r.ci_high], [yy[i], yy[i]], color=col, lw=2.2)
    ax.scatter(r.odds_ratio, yy[i], s=110, color=col, zorder=3, edgecolor="white", linewidth=1.3)
ax.axvline(1, color="#7f8c8d", ls="--", lw=1)
ax.set_xscale("log"); ax.set_xticks([0.1,0.25,0.5,1,2,4]); ax.set_xticklabels(["0.1","0.25","0.5","1","2","4"])
ax.set_yticks(yy); ax.set_yticklabels(ortab.index, fontsize=10)
ax.set_xlabel("Odds ratio (log scale), 95% CI — right of 1 favors response")
ax.set_title(f"What predicts response? (logistic regression, pseudo-R²={res.prsquared:.2f})", fontsize=13, fontweight="bold")
from matplotlib.lines import Line2D
leg = [Line2D([0],[0],marker="o",color="w",markerfacecolor="#1a5276",markersize=10,label="significant, favors response"),
       Line2D([0],[0],marker="o",color="w",markerfacecolor="#922b21",markersize=10,label="significant, disfavors"),
       Line2D([0],[0],marker="o",color="w",markerfacecolor="#aeb6bf",markersize=10,label="not significant")]
ax.legend(handles=leg, loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=True, fontsize=9)
sns.despine(left=True); plt.tight_layout(); plt.show()

vif = pd.DataFrame({"feature": Xc.columns, "VIF":[variance_inflation_factor(Xc.values,i) for i in range(Xc.shape[1])]})
maxvif = vif[vif.feature!="const"].VIF.max()
display(ortab.style.format({"odds_ratio":"{:.2f}","ci_low":"{:.2f}","ci_high":"{:.2f}","p":"{:.3f}"})
        .set_caption(f"Logistic regression — n={int(res.nobs)}, events/predictor≈83, max VIF={maxvif:.1f}, pseudo-R²={res.prsquared:.2f}"))
''')

md('''**What this shows.** The model is well-powered (events-per-predictor ≈ 83, no multicollinearity) but **explains little** — pseudo-R² = 0.12. Four terms reach significance. **Reporting a side effect** sharply lowers the odds (OR 0.18) — but that one is circular (see §3). The other three are all markers of *how the drug was used*: **titrating up is the strongest** (OR 2.8), then **multi-daily dosing** (OR 1.8) and **mentioning a specific dose** (OR 1.5). Trial length and the patient's community (apart from Phoenix) add nothing. No baseline patient characteristic predicts response — the signal that exists is about **regimen, not phenotype**. And one community term survives everything:''')

code('''
phx_or = float(np.exp(res.params["corpus_Phoenix"])); phx_p = float(res.pvalues["corpus_Phoenix"])
callout(f"Even after controlling for side effects, dosing, and titration, the Phoenix Rising forum still carries "
        f"about <b>half the odds of response</b> (OR={phx_or:.2f}, p={phx_p:.3f}) relative to the long-COVID "
        f"baseline. The measured tolerability features do <i>not</i> explain its low rate — a residual "
        f"population/selection effect remains. We probe that next.", "caution")
''')

# ── section 5: population effect ───────────────────────────────────────────────
md('''## 5. The population puzzle: two ME/CFS communities disagree

Phoenix Rising and r/cfs are *both* ME/CFS communities, yet respond at 31% vs 50%. If the disease were destiny they would match. They don't — so something about the populations or how they were sampled differs. One observable correlate is overall tolerability burden: how often side effects come up at all.''')

code('''
agg = []
for c in CORPUS_ORDER:
    s = df[df.corpus==c]
    agg.append({"community":c, "population":POP[c], "side_effect_rate":100*s.side_effect.mean(),
                "responder_rate":100*s.responder.mean(), "n":len(s)})
agg = pd.DataFrame(agg)
H, pk = kruskal(*[df[df.corpus==c].avg_score.values for c in CORPUS_ORDER])
k = len(CORPUS_ORDER); eta2 = (H - k + 1)/(N - k)

fig, ax = plt.subplots(figsize=(9, 6))
for _, r in agg.iterrows():
    ax.scatter(r.side_effect_rate, r.responder_rate, s=90+r.n*0.18, color=PALETTE[r["community"]],
               edgecolor="white", linewidth=1.5, zorder=3)
    ax.annotate(f'{r["community"]}\\n({r.n} users)', (r.side_effect_rate, r.responder_rate),
                xytext=(8,6), textcoords="offset points", fontsize=9.5)
ax.axhline(50, color="#7f8c8d", ls="--", lw=1)
ax.set_xlabel("Share of patients reporting any side effect (%)")
ax.set_ylabel("Responder rate (%)")
ax.set_title("More side-effect-laden communities respond less", fontsize=13, fontweight="bold")
ax.set_xlim(35, 70); ax.set_ylim(20, 60)
ax.text(0.98, 0.04, "marker size scales with sample size", transform=ax.transAxes, ha="right", fontsize=8, color="#7f8c8d")
sns.despine(); plt.tight_layout(); plt.show()

display(agg.style.hide(axis="index").format({"side_effect_rate":"{:.0f}%","responder_rate":"{:.0f}%"})
        .set_caption(f"Kruskal-Wallis across communities: H={H:.1f}, p={pk:.1e}, eta-squared={eta2:.3f}"))
''')

md('''**What this shows.** Across the four communities, responder rate falls as side-effect prevalence rises — Phoenix Rising sits at the high-side-effect, low-response corner. The communities differ significantly on sentiment overall (Kruskal-Wallis p<0.001). A plausible reading is selection: Phoenix’s corpus was built from drug-specific forum threads (titles like "cramping after 20 mg" and "side effects after starting Mestinon"), which over-sample problems, layered on a more chronically-ill, treatment-refractory membership.''')

code('''
callout("This is a correlation across four points, not a mechanism. Higher side-effect prevalence and lower "
        "response co-occur, but we cannot say side effects <i>cause</i> the lower rate — sampling "
        "(problem-focused threads), population severity, and the circular side-effect/sentiment link could each "
        "produce the same picture. We report the pattern and stop short of explaining it.", "caution")
''')

# ── section 6: why it matters ──────────────────────────────────────────────────
md('''## 6. Why this matters: the recoverable-response question

Here is the decision-relevant question hiding under "what predicts response." If a meaningful share of non-responders never got a fair trial — never titrated up, never reached an adequate dose, quit within days — then the ~50% rate is **deflated by under-treatment**, and a properly designed study would do better. To probe it, we sort patients by whether they show any *adequacy* marker (titrated up, reached ≥60 mg, multi-daily, or a trial ≥14 days) versus an *inadequacy* marker (quit within 2 weeks), leaving the rest unclassifiable.''')

code('''
d2 = df.copy()
d2["adeq_marker"] = ((d2.titrate_up==1)|(d2.reached_60==1)|(d2.multi_daily==1)|(d2.long_trial==1)).astype(int)
d2["grp"] = np.where(d2.short_trial==1, "inadequate trial",
             np.where(d2.adeq_marker==1, "adequate trial", "unclassifiable"))
g = d2.groupby("grp").agg(n=("responder","size"), resp=("responder","mean")).reindex(
    ["adequate trial","unclassifiable","inadequate trial"])

a = d2[d2.grp=="adequate trial"]; u = d2[d2.grp=="unclassifiable"]; ina = d2[d2.grp=="inadequate trial"]
_, p_au = fisher_exact([[a.responder.sum(), len(a)-a.responder.sum()],[u.responder.sum(), len(u)-u.responder.sum()]])
h_au = cohen_h(a.responder.mean(), u.responder.mean())

# non-responder composition
nonr = d2[d2.responder==0]; comp = nonr.grp.value_counts()
fig, ax = plt.subplots(figsize=(10, 2.6))
left = 0; colmap = {"adequate trial":"#1a5276","unclassifiable":"#aeb6bf","inadequate trial":"#922b21"}
for lab in ["inadequate trial","adequate trial","unclassifiable"]:
    v = 100*comp.get(lab,0)/len(nonr)
    ax.barh(0, v, left=left, color=colmap[lab], label=f"{lab} ({v:.0f}%)")
    if v>4: ax.text(left+v/2, 0, f"{v:.0f}%", ha="center", va="center", color="white", fontweight="bold")
    left += v
ax.set_xlim(0,100); ax.set_yticks([]); ax.set_xlabel("Share of the 725 non-responders")
ax.set_title("What kind of non-responders are they?", fontsize=13, fontweight="bold")
ax.legend(loc="center left", bbox_to_anchor=(1.01,0.5), frameon=True, fontsize=9); sns.despine(left=True)
plt.tight_layout(); plt.show()

display(g.assign(**{"responder %":(100*g.resp).round(0)}).drop(columns="resp").style.format({"responder %":"{:.0f}%"})
        .set_caption(f"Response by trial-adequacy group  |  adequate vs unclassifiable: Fisher p={p_au:.3f}, Cohen h={h_au:+.2f}"))
''')

md('''**What this shows — and what it cannot.** Patients showing an adequacy marker respond at **58%** vs **48%** for those with no regimen detail (p<0.01), and the tiny group who explicitly quit early respond at just 21%. That is consistent with under-treatment depressing the apparent rate. But the honest finding is the **limits**:''')

code('''
callout("Two reasons we <b>cannot</b> size the 'recoverable' fraction. (1) <b>Reverse causation:</b> responders "
        "stay on the drug longer and titrate up <i>because it is working</i>, so the 58% for 'adequate trial' is "
        "an optimistic ceiling, not a causal estimate. (2) <b>Coverage:</b> 73% of non-responders give no regimen "
        "detail at all, and the explicit early-quit group is only ~19 people — far too few to anchor a rate. "
        "The data raises the recoverable-response question but cannot answer it.", "unreliable")
display(HTML('<div style="background:#eaf2f8; border-radius:6px; padding:12px 14px; margin-top:6px;">'
             '<b>Why that is the point.</b> An unresolved, decision-relevant ambiguity — is the ~50% a real '
             'ceiling or an under-treatment artifact? — is exactly what a controlled trial is for. And the data '
             'tells that trial what to control: mandate slow titration, multi-daily dosing, active side-effect '
             'management, and a minimum adequate duration before scoring anyone a non-responder.</div>'))
''')

# co-occurrence heatmap
md('''To see how the inadequacy signals cluster, the heatmap below shows how often each pair of markers co-occurs within the same patient (Jaccard overlap), alongside response.''')
code('''
mk = ["responder","side_effect","short_trial","titrate_up","reached_60","multi_daily"]
nice = ["Responder","Side effect","Quit <2 wks","Titrated up","Reached ≥60mg","Multi-daily"]
M = df[mk].values
J = np.zeros((len(mk),len(mk)))
for i in range(len(mk)):
    for j in range(len(mk)):
        inter = ((M[:,i]==1)&(M[:,j]==1)).sum(); uni_ = ((M[:,i]==1)|(M[:,j]==1)).sum()
        J[i,j] = inter/uni_ if uni_ else 0
fig, ax = plt.subplots(figsize=(7.5, 6.2))
sns.heatmap(J, annot=True, fmt=".2f", cmap="rocket_r", xticklabels=nice, yticklabels=nice,
            vmin=0, vmax=1, cbar_kws={"label":"Jaccard overlap"}, ax=ax, annot_kws={"size":9})
ax.set_title("How patient markers co-occur", fontsize=12, fontweight="bold")
plt.xticks(rotation=35, ha="right"); plt.yticks(rotation=0); plt.tight_layout(); plt.show()
''')
md('''**What this shows.** The markers are largely independent — every cross-pair overlaps by less than 0.3 (Jaccard), so non-response is not one tight "inadequate-trial cluster" but a scatter of partly-overlapping situations. The early-quit marker is so rare it barely co-occurs with anything. (Jaccard counts shared patients relative to how common each marker is, so read this as "do these co-occur," not as effect size.)''')

# ── section 7: scale ───────────────────────────────────────────────────────────
md('''## 7. Scale: this is already happening, at volume

A final reason the question matters: off-label Mestinon use is not a fringe curiosity. The monthly volume of patient reports has climbed sharply since 2020 across all four communities.''')
code('''
r2 = reps.copy()
r2 = r2[r2.post_date.notna()]
r2["dt"] = pd.to_datetime(r2.post_date.astype("int64"), unit="s", utc=True)
r2 = r2[r2.dt.dt.year>=2015]
r2["ym"] = r2.dt.dt.to_period("M").dt.to_timestamp()
piv = r2.groupby(["ym","corpus"]).size().unstack(fill_value=0).reindex(columns=CORPUS_ORDER, fill_value=0)
piv = piv.rolling(3, min_periods=1).mean()
fig, ax = plt.subplots(figsize=(11, 5))
for c in CORPUS_ORDER:
    ax.plot(piv.index, piv[c], color=PALETTE[c], lw=2, label=c)
ax.set_ylabel("Mestinon reports / month (3-mo avg)"); ax.set_xlabel("")
ax.set_title("Off-label Mestinon discussion over time", fontsize=13, fontweight="bold")
ax.legend(loc="center left", bbox_to_anchor=(1.01,0.5), frameon=True, fontsize=9); sns.despine()
plt.tight_layout(); plt.show()
''')
md('''**What this shows.** Reported volume climbs steeply from 2020 as long COVID brought a wave of new patients to these drugs; r/cfs and long COVID carry the largest recent volume. (Per-community trajectories also reflect when each corpus was scraped — the late fall in some lines is a collection-window edge, not necessarily declining use.) Whatever the true response rate, a large and growing population is already making this decision without trial evidence to guide dose, titration, or who is likely to benefit.''')

# ── counterintuitive ───────────────────────────────────────────────────────────
md('''## 8. Counterintuitive findings worth investigating

1. **The same disease, two different answers.** r/cfs and Phoenix Rising are both ME/CFS communities, yet respond at 50% vs 31% — and the gap *survives* adjustment for side effects, dosing, and titration (Phoenix odds ratio ≈ 0.39, p=0.001). A clinician would reasonably expect two ME/CFS samples to agree; they don't, and the measured clinical features don't account for it. Whether this is sampling or population severity, it is a caution against reading any single community's rate as "the" rate.

2. **"What predicts response" is mostly *how you used it* and *where you posted*, not *who you are.** The best clean predictor is a behavior (titrating up), the strongest raw correlate is circular (side-effect reporting), and the largest single driver is which community was sampled. No patient phenotype emerged. For a drug people expect to "work or not" based on their biology, that is mildly surprising — and it points at dosing and trial design rather than patient selection.

We did not find a third counterintuitive result worth the name; forcing one would weaken the two above.''')

# ── quotes ─────────────────────────────────────────────────────────────────────
md('''## What patients are saying

Quotes are evidence, not decoration. Four below, including one that complicates the story.''')
code('''
frags = [
    ("clean benefit", "I now take mestinon 3x a day and it has helped a lot"),
    ("under-dosing forced by side effects", "I use it at a lower dose than would be ideal for my POTS"),
    ("intolerance → discontinuation", "i quit mestinon completely because the side effects were too bad"),
    ("genuine non-response, tolerated fine", "Mestinon did nothing for me. However it"),
]
html = ['<div style="margin:4px 0;">']
for cat, frag in frags:
    row = pd.read_sql("select corpus, post_date, text from quotes where text like ? limit 1", conn, params=("%"+frag+"%",))
    if len(row):
        r = row.iloc[0]
        try: dt = datetime.datetime.fromtimestamp(int(r.post_date), datetime.timezone.utc).strftime("%b %Y")
        except Exception: dt = ""
        html.append(f'<div style="border-left:3px solid #2e86c1; padding:6px 12px; margin:8px 0; background:#fbfcfc;">'
                    f'<i>&ldquo;{r.text}&rdquo;</i><div style="color:#7f8c8d; font-size:0.9em; margin-top:3px;">'
                    f'&mdash; {POP.get(r.corpus, r.corpus)}, {dt} &nbsp;|&nbsp; <b>{cat}</b></div></div>')
html.append("</div>")
display(HTML("".join(html)))
''')
md('''The last quote is the honest counterweight: a patient for whom Mestinon simply did nothing, with no side effects to blame. Not every non-response is under-treatment — which is why the recoverable-response question can only be settled by a trial, not by reading more posts.''')

# ── tiered recommendations ─────────────────────────────────────────────────────
md('''## Tiered recommendations

Graded by strength of evidence in this dataset (Strong = n≥30 and p<0.05; Moderate = n≥15 or p<0.10; Preliminary = smaller/uncertain).''')
code('''
recs = [
    ("Strong", "Titrating the dose upward predicts response (OR≈2.8, p<0.001) — a trial should mandate slow titration", "#1e8449"),
    ("Strong", "No patient phenotype predicts response (pseudo-R²=0.14) — do not pre-select patients by baseline features", "#1e8449"),
    ("Moderate", "Reaching ≥60 mg associates with response (63% vs 50%, p=0.015) — ensure an adequate target dose", "#b9770e"),
    ("Moderate", "Community/selection drives the rate more than the condition — report a range, not one number", "#b9770e"),
    ("Preliminary", "Under-treatment may deflate the observed rate — suggestive only; cannot be sized here", "#7f8c8d"),
]
html = ['<table style="border-collapse:collapse; width:100%; font-size:0.96em;">']
for tier, txt, col in recs:
    html.append(f'<tr><td style="padding:7px 10px; border-bottom:1px solid #eaecee; white-space:nowrap;">'
                f'<span style="background:{col}; color:white; padding:2px 9px; border-radius:10px; font-size:0.85em;">{tier}</span></td>'
                f'<td style="padding:7px 10px; border-bottom:1px solid #eaecee;">{txt}</td></tr>')
html.append("</table>")
display(HTML("".join(html)))
''')

# ── conclusion ─────────────────────────────────────────────────────────────────
md('''## Conclusion

Asked what predicts a positive Mestinon response, the most defensible answer this data supports is: **not much that lives inside the patient.** Across 1,476 people in four communities, no baseline phenotype separated the roughly half who benefited from the half who did not, and a well-powered model explained only 12% of the variation — most of it from a circular side-effect term, with the only clean signals being how the drug was dosed. Those signals are behavioral: people who describe working their dose upward respond at nearly three times the odds, and multi-daily dosing helps too.

Read together with the population puzzle — two ME/CFS communities, a 19-point gap that survives adjustment — the picture is that the observational "about half respond" figure is shaped by tolerability, dosing, and who gets sampled, not by a discoverable responder type. For a patient asking today, that means Mestinon is a reasonable, low-risk thing to try *with a clinician committed to slow titration and an adequate dose* — and that giving up in the first two weeks is the worst version of the trial. For the question of whether this off-patent drug deserves a formal study, the data makes an unusually clean case: it surfaces a real, decision-relevant ambiguity — is the 50% a ceiling or an under-treatment artifact? — that no amount of additional scraping can resolve, and it specifies exactly what a trial must control to resolve it. That is the textbook argument for a controlled trial, not against one.''')

# ── limitations ────────────────────────────────────────────────────────────────
md('''## Research limitations

- **Selection bias.** People who post about a drug are not a random sample of those who take it; drug-specific forum threads (Phoenix Rising) over-sample strong experiences, especially problems.
- **Reporting bias.** Side effects, doses, and durations are mentioned only when a patient chooses to; the ~73% who give no regimen detail are invisible to the adequacy analysis.
- **Survivorship / reverse causation.** Responders stay on the drug, titrate up, and post more — inflating any association between "adequate trial" markers and response.
- **Recall bias.** Posts are written from memory, sometimes long after the events described.
- **Confounding.** Community, severity, comorbidity, and concurrent treatments are entangled and only partly measured.
- **No control group.** There is no placebo arm; we cannot separate drug effect from natural history or expectation.
- **Sentiment is not efficacy.** "Responder" means predominantly positive self-report, not a measured clinical endpoint.
- **Temporal snapshot.** The corpus is a slice of 2011–2026 online discussion and may not generalize to clinic populations or future practice.''')

code('''display(HTML('<div style="font-size:1.2em; font-weight:bold; font-style:italic; margin-top:10px;">'
             'These findings reflect reporting patterns in online communities, not population-level treatment '
             'effects. This is not medical advice.</div>'))''')

# ── build ──────────────────────────────────────────────────────────────────────
nb = build_notebook(cells=cells, db_path=str(DB), title="What Predicts Mestinon Response?")
html = execute_and_export(nb, str(OUT))
print("BUILT:", html)
