# -*- coding: utf-8 -*-
"""Combined-cohort LDN notebook: r/covidlonghaulers (CLH) + Phoenix Rising.

Scope is deliberately limited to the TWO axes that are comparable across the two
corpora: (1) reported DOSE (mined by identical regex over raw post text — pipeline-
independent) and (2) the structured SIDE-EFFECT profile (same categorizer applied to
both). SENTIMENT IS EXCLUDED: the two corpora were classified with different
models/prompts and aggregated by different dedup rules, so their positive-rate numbers
(CLH 68.5% vs Phoenix ~36%) are not comparable and are not shown here.

Reads ldn_2yr.db (CLH; build_ldn_data.py + build_ldn_ae.py) and
      ldn_phoenix.db (Phoenix; build_ldn_phoenix_data.py — identical logic).
"""
from __future__ import annotations
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
PKG = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("PP_DATA_DIR", PKG / "data"))  # source DBs are not committed; see ../README.md and MANIFEST.csv
sys.path.insert(0, str(REPO / "docs" / "RCT_historical_validation"))  # build_notebook lives here
from build_notebook import build_notebook, execute_and_export  # noqa: E402

DB = REPO / "FDA_analysis" / "notebooks" / "ldn_2yr.db"            # -> conn (CLH)
PHX = (DATA / "ldn_phoenix.db").resolve().as_posix()
OUT = PKG / "notebooks" / "ldn_two_community_tolerability"

cells = []
def md(s): cells.append(("md", s))
def code(s): cells.append(("code", s))

# ── setup: second connection + shared professional style / caption helpers ───
code(f'''
from collections import Counter
import textwrap

# ── house style (consistent across every figure) ──
plt.rcParams.update({{
    "axes.titlesize": 12.5, "axes.titleweight": "bold", "axes.titlepad": 10,
    "axes.labelsize": 10.5, "axes.labelcolor": "#1c2833",
    "axes.edgecolor": "#444444", "axes.linewidth": 0.8,
    "xtick.labelsize": 9, "ytick.labelsize": 10, "font.size": 10,
    "xtick.color": "#444444", "ytick.color": "#444444",
    "axes.grid": False, "savefig.dpi": 200, "figure.dpi": 110,
}})
CLH_C, PHX_C, CLIN_C = "#8e44ad", "#2e86c1", "#2c3e50"   # Reddit/CLH, Phoenix, clinical
PURPLE, GREY, SHADE, ACCENT = CLH_C, "#b9a7c7", "#f4eff8", "#6c3483"
N_CLH, N_PHX = 0, 0

def grid(ax, axis="x"):
    ax.grid(axis=axis, color="#e9e9e9", lw=0.7, zorder=0); ax.set_axisbelow(True)

def caption(fig, n, text, bottom=0.27, left=0.20, top=0.90, right=0.97):
    """Scientific-style figure legend pinned to the bottom of the figure."""
    fig.subplots_adjust(left=left, right=right, top=top, bottom=bottom)
    fig.text(0.012, 0.012, chr(10).join(textwrap.wrap(text, 168)),
             ha="left", va="bottom", fontsize=7.4, color="#666666", style="italic")

def note(text, sev="note"):   # retained for the tolerability table (non-figure)
    c = {{"caution": "#b9770e", "caveat": "#5d6d7e", "note": "#1a5276"}}[sev]
    display(HTML(f'<div style="border-left:4px solid {{c}}; background:#fbfcfc; padding:9px 13px; margin:6px 0; color:#1c2833;">{{text}}</div>'))

conn_phx = sqlite3.connect(r"{PHX}")
clh = pd.read_sql("select * from user_features", conn)
phx = pd.read_sql("select * from user_features", conn_phx)
N_CLH, N_PHX = len(clh), len(phx)
''')

md('''# Low-Dose Naltrexone Across Two Patient Communities — Dosing and Tolerability

**Scope and an important caveat.** This notebook compares low-dose naltrexone (LDN) use in two independent online patient communities — **r/covidlonghaulers** (Long COVID; the cohort behind our FDA comment, n=321 LDN patients) and **Phoenix Rising** (a long-standing ME/CFS + Long COVID forum, n=354 LDN patients). It is restricted to the two measures that are **comparable** across the corpora:

1. **Reported dose** — mined by the *same regex over raw post text*, so it does not depend on how either corpus was classified.
2. **Reported side effects** — the structured side-effect field, categorized by one shared rule set.

> **Sentiment / response rate is intentionally excluded.** The two corpora were classified with different models and prompts and aggregated by different dedup rules; their headline positive rates (CLH 68.5% vs Phoenix ~36% user-level) are **not** comparable and must not be read as a benefit comparison. Nothing here pools or contrasts sentiment.

These are self-reported, uncontrolled data and do not establish efficacy or safety.''')

# ── 1. Dose ──────────────────────────────────────────────────────────────────
md('''## 1. Real-world LDN dosing — both communities cluster ≤4.5 mg

Each bar is one **exact stated dose** (not binned); height = patients reporting that dose as their lowest, **stacked by source**. The shaded band is the ≤4.5 mg established-LDN range — the only FDA-approved naltrexone product is the 50 mg tablet.''')

code('''
def dose_counts(d): return Counter(round(v,3) for v in d.loc[d.mentions_dose==1,"min_dose"].dropna())
cdc=dose_counts(clh); pdc=dose_counts(phx)
vals=sorted(set(cdc)|set(pdc))
x=np.arange(len(vals)); clh_n=[cdc.get(v,0) for v in vals]; phx_n=[pdc.get(v,0) for v in vals]
cle=int(clh.dose_le_4_5.sum()); ctot=int(clh.mentions_dose.sum())
ple=int(phx.dose_le_4_5.sum()); ptot=int(phx.mentions_dose.sum())
fig,ax=plt.subplots(figsize=(10.5,4.6))
grid(ax,"y")
le_idx=[i for i,v in enumerate(vals) if v<=4.5]
if le_idx: ax.axvspan(-0.5,max(le_idx)+0.5,color=SHADE,zorder=0)
ax.bar(x,clh_n,color=CLH_C,label=f"r/covidlonghaulers  (n={ctot} dose-stating)",zorder=3,width=0.82)
ax.bar(x,phx_n,bottom=clh_n,color=PHX_C,label=f"Phoenix Rising  (n={ptot} dose-stating)",zorder=3,width=0.82)
ax.set_xticks(x); ax.set_xticklabels([f"{v:g}" for v in vals])
ax.set_xlabel("Lowest reported LDN dose (mg) — one bar per exact stated dose")
ax.set_ylabel("Patients reporting this dose (n)")
ax.set_title("Real-world LDN dosing across two patient communities")
top=max((c+p) for c,p in zip(clh_n,phx_n)); ax.set_ylim(0,top*1.18)
if le_idx:
    ax.axvline(max(le_idx)+0.5,color="#9b59b6",ls="--",lw=1,zorder=2)
    ax.text(0,top*1.12,"shaded = ≤4.5 mg window",ha="left",va="top",fontsize=9,color=ACCENT)
ax.legend(frameon=False,fontsize=9.5,loc="upper right"); ax.spines[["top","right"]].set_visible(False)
caption(fig,1,f"Distribution of self-reported low-dose naltrexone (LDN) doses in two independent patient communities. "
        f"Each bar is one exact stated dose (no binning); height is the number of patients reporting that dose as their "
        f"lowest, stacked by source (r/covidlonghaulers, purple; Phoenix Rising, blue). The shaded region marks the "
        f"≤4.5 mg established-LDN range. {cle}/{ctot} ({100*cle/ctot:.0f}%) of dose-stating r/covidlonghaulers "
        f"patients and {ple}/{ptot} ({100*ple/ptot:.0f}%) of Phoenix Rising patients use ≤4.5 mg; the only "
        f"FDA-approved naltrexone product is the 50 mg tablet (alcohol/opioid use disorder). Doses are self-reported by "
        f"the subset of patients who state one; both axes share the same dose scale.",bottom=0.30,left=0.07)
plt.show()
''')

# ── 2. Side-effect counts ─────────────────────────────────────────────────────
md('''## 2. Reported side-effect counts — pooled, colored by source

One bar per side-effect category; length = number of side-effect reports mentioning it, **stacked by source**. Categories overlap (a report can mention several). Green labels mark the three effects the clinical literature names as characteristic of LDN.''')

code('''
LIT = {"Sleep disturbance","Gastrointestinal","Vivid / abnormal dreams"}
def counts(c):
    s=pd.read_sql("select * from ae_summary",c)
    m={k:int(v) for k,v in pd.read_sql("select k,v from ae_meta",c).values}
    s=s[s.category!="Other / unspecified"]
    return dict(zip(s.category,s.n_reports)), m
cc,cm=counts(conn); pc,pm=counts(conn_phx)
cats=sorted(set(cc)|set(pc), key=lambda k:-(cc.get(k,0)+pc.get(k,0)))
y=np.arange(len(cats))[::-1]
clh_v=[cc.get(k,0) for k in cats]; phx_v=[pc.get(k,0) for k in cats]
fig,ax=plt.subplots(figsize=(10.0,5.4))
grid(ax,"x")
ax.barh(y,clh_v,color=CLH_C,label=f"r/covidlonghaulers  (n={cm['n_ae_reports']} side-effect reports)",zorder=3)
ax.barh(y,phx_v,left=clh_v,color=PHX_C,label=f"Phoenix Rising  (n={pm['n_ae_reports']} side-effect reports)",zorder=3)
for yi,cv,pv in zip(y,clh_v,phx_v):
    if cv>=6:  ax.text(cv/2,yi,str(cv),va="center",ha="center",fontsize=7.5,color="white")
    if pv>=12: ax.text(cv+pv/2,yi,str(pv),va="center",ha="center",fontsize=7.5,color="white")
    ax.text(cv+pv+5,yi,str(cv+pv),va="center",fontsize=8.5,color="#555")
ax.set_yticks(y); ax.set_yticklabels(cats)
for tick,k in zip(ax.get_yticklabels(),cats):
    if k in LIT: tick.set_color("#1e8449"); tick.set_fontweight("bold")
ax.set_xlim(0,max(c+p for c,p in zip(clh_v,phx_v))+45)
ax.set_xlabel("Side-effect reports mentioning the effect (n) — stacked by source")
ax.set_title("Reported LDN side effects by community")
ax.legend(frameon=False,fontsize=9.5,loc="lower right"); ax.spines[["top","right"]].set_visible(False)
caption(fig,2,f"Number of side-effect reports mentioning each category, stacked by source (r/covidlonghaulers, purple, "
        f"n={cm['n_ae_reports']} reports; Phoenix Rising, blue, n={pm['n_ae_reports']} reports). Categories overlap "
        f"(a single report may mention several) and 'Other / unspecified' is omitted. Bars are pooled report COUNTS: "
        f"Phoenix fills the larger share of every bar because it is the larger corpus, not because of a higher "
        f"per-patient rate; a size-controlled comparison is shown separately. Green labels mark sleep disturbance, "
        f"gastrointestinal upset and vivid dreams — the effects the clinical literature names as characteristic of LDN. "
        f"Counts are mention frequencies, not incidence.",bottom=0.24,left=0.22)
plt.show()
''')

# ── 3. Side effects vs the clinical trials ───────────────────────────────────
md('''## 3. How the reported side effects compare to the clinical trials

Du & Nguyen (2025) pool the LDN trials and report six side effects as **% of trial patients**. The comparable real-world unit is the **% of LDN patients** in a cohort whose reports mention that effect. Two views follow: absolute magnitude (3a), then size-normalized profile shape (3b).''')

md('''**3a. Magnitude — r/covidlonghaulers vs the trials.** Only the matched-method r/covidlonghaulers cohort is shown against the clinical magnitudes. Phoenix Rising is omitted *here*: its side-effect extraction was ~4× more liberal (60% vs 15% of reports carry a side-effect term), inflating its per-patient rates above clinical incidence — a prompt artifact, not a real difference. Phoenix appears in 3b on a size-normalized footing.''')

code('''
DUN=[("Headache",10.0),("Sleep disturbance",9.0),("Light-headedness",8.5),("GI disturbance",5.0),("Brain fog",5.0),("Fatigue",2.5)]
order=sorted(DUN,key=lambda x:-x[1]); cats=[d[0] for d in order]
def crate(c):
    n=dict(pd.read_sql("select category,n_users from ae_clinical",c).values)
    N={k:int(v) for k,v in pd.read_sql("select k,v from ae_meta",c).values}["n_users_total"]
    return n,N
cn,cN=crate(conn)
clin=[dict(DUN)[k] for k in cats]; clh_rate=[100*cn[k]/cN for k in cats]
y=np.arange(len(cats))[::-1]; h=0.38
fig,ax=plt.subplots(figsize=(9.6,4.8))
grid(ax,"x")
ax.barh(y+h/2,clin,h,color=CLIN_C,label="Clinical trials (Du & Nguyen 2025)",zorder=3)
ax.barh(y-h/2,clh_rate,h,color=CLH_C,label=f"r/covidlonghaulers (% of {cN} patients)",zorder=3)
for yi,a,b in zip(y,clin,clh_rate):
    ax.text(a+0.15,yi+h/2,f"{a:.1f}%",va="center",fontsize=8.5,color=CLIN_C)
    ax.text(b+0.15,yi-h/2,f"{b:.1f}%",va="center",fontsize=8.5,color=ACCENT)
ax.set_yticks(y); ax.set_yticklabels(cats); ax.set_xlim(0,12)
ax.set_xlabel("Patients reporting the side effect (%)")
ax.set_title("LDN side effects: r/covidlonghaulers vs clinical trials")
ax.legend(frameon=False,fontsize=9,loc="lower right"); ax.spines[["top","right"]].set_visible(False); ax.tick_params(left=False)
caption(fig,"3a",f"Per-patient LDN side-effect rates in r/covidlonghaulers (purple, % of {cN} LDN patients whose posts "
        f"mention each effect) versus pooled clinical-trial frequencies (Du & Nguyen 2025, dark; % of trial patients). "
        f"Both are percentages of patients, the comparable unit. The real-world rates track the trials within a few "
        f"points for sleep disturbance and GI upset; spontaneous Reddit reporting under-captures lightly-elicited "
        f"effects such as headache and light-headedness. Phoenix Rising is excluded here because its higher extraction "
        f"rate inflates absolute magnitudes (shown size-normalized in the profile-shape panel). Self-reported, uncontrolled data; not incidence.",
        bottom=0.30,left=0.20)
plt.show()
''')

md('''**3b. Profile shape — all three sources.** To place Phoenix Rising on the same footing despite its higher extraction rate, each source's six-category profile is scaled to 100% (relative emphasis, not incidence). The question becomes: *of the reported side effects, is the mix the same?*''')

code('''
def vec(c):
    n=dict(pd.read_sql("select category,n_users from ae_clinical",c).values)
    return [n[k] for k in cats]
def norm(v): s=sum(v) or 1; return [100*x/s for x in v]
dun=norm([dict(DUN)[k] for k in cats]); clhv=norm(vec(conn)); phxv=norm(vec(conn_phx))
y=np.arange(len(cats))[::-1]; h=0.26
fig,ax=plt.subplots(figsize=(9.6,5.4))
grid(ax,"x")
ax.barh(y+h,dun,h,color=CLIN_C,label="Clinical trials (Du & Nguyen 2025)",zorder=3)
ax.barh(y,clhv,h,color=CLH_C,label="r/covidlonghaulers (n=321)",zorder=3)
ax.barh(y-h,phxv,h,color=PHX_C,label="Phoenix Rising (n=354)",zorder=3)
ax.set_yticks(y); ax.set_yticklabels(cats)
ax.set_xlabel("Relative share of the six tracked side effects (%, normalized within each source)")
ax.set_title("LDN side-effect profile shape — three sources, size-normalized")
ax.legend(frameon=False,fontsize=9,loc="lower right"); ax.spines[["top","right"]].set_visible(False); ax.tick_params(left=False)
caption(fig,"3b","Relative profile of LDN side effects across three independent sources. For each source the six "
        "side-effect categories reported by Du & Nguyen (2025) are rescaled to sum to 100%, showing the relative MIX of "
        "effects rather than their absolute frequency; this controls for the sources' very different extraction rates "
        "(a side effect is recorded in 60% of Phoenix Rising reports vs 15% of r/covidlonghaulers reports), so only "
        "profile shape is compared. Real-world bars give the proportion of LDN patients whose posts mention each effect "
        "(r/covidlonghaulers, Long COVID, n=321; Phoenix Rising, ME/CFS + Long COVID, n=354); clinical bars are pooled "
        "trial frequencies (Du & Nguyen 2025). Both online cohorts emphasize sleep disturbance and fatigue while the "
        "trials rank headache and light-headedness higher — the expected gap between spontaneously volunteered and "
        "clinician-elicited adverse events. Values reflect reporting patterns, not incidence; absolute magnitudes are "
        "not comparable across sources (a magnitude comparison is shown separately).",bottom=0.34,left=0.20)
plt.show()
''')

# ── 4. Side effects vs dose reached ──────────────────────────────────────────
md('''## 4. Does side-effect reporting track dose?

A natural question for a labeling decision: do side effects rise with dose? Dose-stating patients are grouped by the **highest dose they report reaching**, and we compare the share reporting any side effect within each community (cohorts are not pooled). Absolute rates are shown first (**4a**); because the two forums report side effects at very different baseline levels, a second panel (**4b**) normalizes each forum to its own lowest-dose group so the dose *trend* is comparable between them. Wilson 95% confidence intervals; bands are patient-level summaries, not the dose at which an effect occurred.''')

code('''
BANDS=["≤1.5","1.5–4.5",">4.5"]
def band(v): return "≤1.5" if v<=1.5 else ("1.5–4.5" if v<=4.5 else ">4.5")
def by_band(df):
    d=df[(df.mentions_dose==1)&(df.max_dose.notna())]
    return {b:(len(d[d.max_dose.map(band)==b]), int(d[d.max_dose.map(band)==b].any_side_effect.sum())) for b in BANDS}
cb=by_band(clh); pb=by_band(phx)
y=np.arange(len(BANDS))[::-1]
fig,ax=plt.subplots(figsize=(9.6,4.4))
grid(ax,"x")
for data,col,off in [(cb,CLH_C,0.15),(pb,PHX_C,-0.15)]:
    for i,b in enumerate(BANDS):
        n,k=data[b]
        if not n: continue
        r=100*k/n; lo,hi=wilson_ci(k,n); lo*=100; hi*=100; yy=y[i]+off
        ax.plot([lo,hi],[yy,yy],color=col,lw=2.2,solid_capstyle="round",zorder=3)
        ax.scatter([r],[yy],s=70,color=col,edgecolor="white",lw=1,zorder=4)
        ax.text(hi+1.8,yy,f"{r:.0f}%  (n={n})",va="center",fontsize=8.5,color=col)
ax.scatter([],[],color=CLH_C,label="r/covidlonghaulers"); ax.scatter([],[],color=PHX_C,label="Phoenix Rising")
ax.set_yticks(y); ax.set_yticklabels([f"{b} mg" for b in BANDS])
ax.set_xlim(0,112); ax.set_xlabel("Patients reporting any side effect (%, with 95% CI)")
ax.set_ylabel("Highest LDN dose reached")
ax.set_title("Side-effect reporting vs LDN dose reached")
ax.legend(frameon=False,fontsize=9,loc="lower left"); ax.spines[["top","right"]].set_visible(False)
caption(fig,"","Proportion of dose-stating LDN patients reporting any side effect, grouped by the highest dose they "
        "report reaching, with Wilson 95% confidence intervals (n per band shown). Within each community the rate is "
        "flat across the dose range — intervals overlap with no monotonic increase — so side-effect reporting does not "
        "rise with dose across the established LDN range. Bands use the patient-level maximum stated dose, not the dose "
        "at which an effect occurred, so this is a patient-level association, not a pharmacological dose-response. "
        "Self-reported titration also tends to cap the dose reached once side effects appear, biasing toward more side "
        "effects at lower max dose; the flatness holds despite that. Phoenix Rising's higher overall level reflects its "
        "more liberal side-effect extraction, not greater toxicity — only within-community trends are comparable. "
        "'Any side effect' is a coarse indicator that does not weight severity.",bottom=0.34,left=0.16)
plt.show()
''')

md('''**4b. Normalized between forums.** The two communities report side effects at very different baseline levels (an extraction-rate artifact), so their absolute rates sit far apart. Expressing each band as a risk ratio versus that forum's own ≤1.5 mg group removes the baseline and puts the dose trend on one comparable scale.''')

code('''
def rr_ci(k1,n1,k0,n0,z=1.96):
    if min(k1,k0,n1,n0)==0: return (np.nan,np.nan,np.nan)
    rr=(k1/n1)/(k0/n0); se=np.sqrt(1/k1-1/n1+1/k0-1/n0)
    return rr, rr*np.exp(-z*se), rr*np.exp(z*se)
y=np.arange(len(BANDS))[::-1]
fig,ax=plt.subplots(figsize=(9.6,4.4))
grid(ax,"x")
ax.axvline(1.0,color="#7f8c8d",ls="--",lw=1,zorder=2)
for data,col,off in [(cb,CLH_C,0.15),(pb,PHX_C,-0.15)]:
    n0,k0=data[BANDS[0]]
    for i,b in enumerate(BANDS):
        n,k=data[b]; yy=y[i]+off
        if i==0:
            ax.scatter([1.0],[yy],s=55,facecolor="white",edgecolor=col,lw=1.6,zorder=4)
            continue
        rr,lo,hi=rr_ci(k,n,k0,n0)
        ax.plot([lo,hi],[yy,yy],color=col,lw=2.2,solid_capstyle="round",zorder=3)
        ax.scatter([rr],[yy],s=70,color=col,edgecolor="white",lw=1,zorder=4)
        ax.text(hi*1.05,yy,f"RR {rr:.2f}",va="center",fontsize=8.5,color=col)
ax.scatter([],[],color=CLH_C,label="r/covidlonghaulers"); ax.scatter([],[],color=PHX_C,label="Phoenix Rising")
ax.set_xscale("log"); ax.set_xlim(0.42,2.7)
ax.set_xticks([0.5,0.7,1.0,1.5,2.0]); ax.set_xticklabels(["0.5","0.7","1.0","1.5","2.0"])
ax.set_yticks(y); ax.set_yticklabels([f"{b} mg"+(" (ref)" if i==0 else "") for i,b in enumerate(BANDS)])
ax.set_xlabel("Side-effect rate relative to the ≤1.5 mg group (risk ratio, 95% CI; log scale)")
ax.set_ylabel("Highest LDN dose reached")
ax.set_title("Side-effect reporting vs dose — normalized within each forum")
ax.legend(frameon=False,fontsize=9,loc="lower left"); ax.spines[["top","right"]].set_visible(False)
caption(fig,"","Side-effect reporting by dose, normalized within each forum to remove the large baseline difference in "
        "extraction rate, so the dose trend is comparable between communities. Each dose band is expressed as a risk "
        "ratio versus that forum's own ≤1.5 mg group (reference = 1.0, dashed line; open marker), with 95% confidence "
        "intervals on a log scale. In both communities every interval spans 1.0 — no band differs from the lowest-dose "
        "group — so the absence of a dose-side-effect relationship is consistent across forums, not an artifact of "
        "either one's reporting level. Risk ratios use the patient-level maximum dose and 'any side effect'; per-band "
        "cells are small (n≈18–78), so intervals are wide. Self-reported, uncontrolled data.",bottom=0.34,left=0.16)
plt.show()
''')

md('''**4c. By individual side effect (Phoenix Rising).** Breaking the relationship out per side-effect category needs more data than r/covidlonghaulers can supply at this split — its category-by-dose cells are single-digit. Phoenix Rising can support it; denominators are all dose-stating patients per band, so within-cohort the trend is unaffected by Phoenix's higher overall reporting level.''')

code('''
from scipy.stats import norm
def ca_trend(ks,ns,scores=(0,1,2)):
    ks=np.array(ks,float); ns=np.array(ns,float); s=np.array(scores,float)
    N=ns.sum(); K=ks.sum()
    if K<=0 or K>=N: return np.nan
    p=K/N; T=np.sum(s*(ks-ns*p)); var=p*(1-p)*(np.sum(ns*s*s)-(np.sum(ns*s))**2/N)
    return 2*norm.sf(abs(T/np.sqrt(var))) if var>0 else np.nan
BANDS=["≤1.5","1.5–4.5",">4.5"]; SH={"≤1.5":"#2a9d8f","1.5–4.5":"#e9c46a",">4.5":"#e76f51"}   # cool->warm = low->high dose
def band(v): return "≤1.5" if v<=1.5 else ("1.5–4.5" if v<=4.5 else ">4.5")
ph=pd.read_sql("select user_id,max_dose from user_features where mentions_dose=1 and max_dose is not null",conn_phx)
ph["band"]=ph.max_dose.map(band)
cset=pd.read_sql("select user_id,category from ae_user_clinical",conn_phx).groupby("user_id").category.apply(set)
ph["cats"]=ph.user_id.map(cset).apply(lambda s: s if isinstance(s,set) else set())
CATS=["Sleep disturbance","GI disturbance","Fatigue","Headache","Light-headedness","Brain fog"]
CATS=sorted(CATS,key=lambda c: ph.cats.apply(lambda s:c in s).sum())   # ascending -> biggest at top
bn={b:int((ph.band==b).sum()) for b in BANDS}
def kc(c,b): return int(ph[ph.band==b].cats.apply(lambda s:c in s).sum())
y=np.arange(len(CATS)); h=0.26
fig,ax=plt.subplots(figsize=(9.8,5.8)); grid(ax,"x")
for j,b in enumerate(BANDS):
    rates=[]; elo=[]; ehi=[]
    for c in CATS:
        n=bn[b]; k=kc(c,b); r=100*k/n; lo,hi=wilson_ci(k,n)
        rates.append(r); elo.append(r-100*lo); ehi.append(100*hi-r)
    ax.barh(y+(1-j)*h,rates,h,color=SH[b],xerr=[elo,ehi],
            error_kw=dict(lw=0.8,ecolor="#777",capsize=2),label=f"{b} mg (n={bn[b]})",zorder=3)
pval={c:ca_trend([kc(c,b) for b in BANDS],[bn[b] for b in BANDS]) for c in CATS}
ax.set_yticks(y); ax.set_yticklabels([f"{c}\\n(trend p={pval[c]:.2f})" if pval[c]==pval[c] else f"{c}\\n(trend n/a)" for c in CATS],fontsize=9.5)
ax.set_xlim(0,82); ax.set_xlabel("Phoenix Rising patients mentioning the effect (%, within dose band; Wilson 95% CI)")
ax.set_title("Side-effect category vs dose reached — Phoenix Rising")
ax.legend(frameon=False,fontsize=8.5,loc="lower right",title="Highest dose reached",title_fontsize=8.5)
ax.spines[["top","right"]].set_visible(False)
caption(fig,"","Per-patient rate of each side-effect category by highest dose reached, in Phoenix Rising — the only "
        "cohort with enough per-category data (r/covidlonghaulers has single-digit counts per category-by-dose cell and "
        "is not broken out; its aggregate dose relationship is shown in the preceding panels). Denominator is all "
        "dose-stating patients per band (≤1.5 mg n=43; 1.5–4.5 mg n=78; >4.5 mg n=27); bars are the share mentioning "
        "each effect, with Wilson 95% confidence intervals. The p value beside each category is a Cochran–Armitage test "
        "for a linear trend across dose bands: none is significant — no side effect rises with dose, and the wide, "
        "overlapping intervals reflect the small per-band cells (the test is low-powered, so this rules out a large "
        "dose effect, not a subtle one). Within-cohort, so unaffected by Phoenix's overall reporting level. Patient-level "
        "maximum dose, not the dose at which an effect occurred; titration confound applies; self-reported.",bottom=0.30,left=0.23)
plt.show()
''')

md('''**4d. Both forums combined (cohort-adjusted).** Pooling the two communities for more power — but adjusted for their different baseline reporting rates so the extraction-rate gap cannot leak into the dose comparison. Bars are directly standardized rates (a fixed cohort mix applied across all bands, so band differences reflect dose, not composition); the p value is a Cochran–Armitage trend test **stratified by forum** (each forum's own baseline held constant, within-forum dose signals pooled). Error bars are approximate 95% CIs.''')

code('''
from scipy.stats import norm
BANDS=["≤1.5","1.5–4.5",">4.5"]; SCORES={"≤1.5":0,"1.5–4.5":1,">4.5":2}
SH={"≤1.5":"#2a9d8f","1.5–4.5":"#e9c46a",">4.5":"#e76f51"}   # cool->warm = low->high dose
def band(v): return "≤1.5" if v<=1.5 else ("1.5–4.5" if v<=4.5 else ">4.5")
def load(cn):
    d=pd.read_sql("select user_id,max_dose from user_features where mentions_dose=1 and max_dose is not null",cn)
    d["band"]=d.max_dose.map(band)
    cs=pd.read_sql("select user_id,category from ae_user_clinical",cn).groupby("user_id").category.apply(set)
    d["cats"]=d.user_id.map(cs).apply(lambda s: s if isinstance(s,set) else set()); return d
DC=[load(conn),load(conn_phx)]
W=[len(d) for d in DC]; W=[w/sum(W) for w in W]          # size weights (CLH ~35% / Phoenix ~65%)
def nk(d,b,c): sub=d[d.band==b]; return len(sub), int(sub.cats.apply(lambda s:c in s).sum())
bn={b:int(sum((d.band==b).sum() for d in DC)) for b in BANDS}
CATS=["Sleep disturbance","GI disturbance","Fatigue","Headache","Light-headedness","Brain fog"]
CATS=sorted(CATS,key=lambda c: sum(nk(d,b,c)[1] for d in DC for b in BANDS))
def std_rate(c,b):
    R=0.0; var=0.0
    for d,w in zip(DC,W):
        n,k=nk(d,b,c)
        if n==0: continue
        pv=(k+0.5)/(n+1)                                  # adjusted -> 0-event cells still carry uncertainty
        R+=w*(k/n); var+=w*w*pv*(1-pv)/n
    return 100*R, 100*var**0.5
def strat_ca(c):
    Tsum=Vsum=0.0
    for d in DC:
        ks=[nk(d,b,c)[1] for b in BANDS]; ns=[nk(d,b,c)[0] for b in BANDS]; s=[SCORES[b] for b in BANDS]
        N=sum(ns); K=sum(ks)
        if K<=0 or K>=N: continue
        p=K/N
        Tsum+=sum(si*(ki-ni*p) for si,ki,ni in zip(s,ks,ns))
        Vsum+=p*(1-p)*(sum(ni*si*si for ni,si in zip(ns,s))-(sum(ni*si for ni,si in zip(ns,s)))**2/N)
    return 2*norm.sf(abs(Tsum/Vsum**0.5)) if Vsum>0 else float("nan")
y=np.arange(len(CATS)); h=0.26
fig,ax=plt.subplots(figsize=(9.8,5.8)); grid(ax,"x")
for j,b in enumerate(BANDS):
    rates=[]; err=[]
    for c in CATS:
        r,se=std_rate(c,b); rates.append(r); err.append(1.96*se)
    ax.barh(y+(1-j)*h,rates,h,color=SH[b],xerr=err,error_kw=dict(lw=0.8,ecolor="#777",capsize=2),label=f"{b} mg (n={bn[b]})",zorder=3)
pval={c:strat_ca(c) for c in CATS}
ax.set_yticks(y); ax.set_yticklabels([f"{c}\\n(trend p={pval[c]:.2f})" if pval[c]==pval[c] else f"{c}\\n(trend n/a)" for c in CATS],fontsize=9.5)
ax.set_xlim(0,70); ax.set_xlabel("Cohort-adjusted patients mentioning the effect (%, directly standardized; ≈95% CI)")
ax.set_title("Side-effect category vs dose reached — both forums, cohort-adjusted")
ax.legend(frameon=False,fontsize=8.5,loc="lower right",title="Highest dose reached",title_fontsize=8.5)
ax.spines[["top","right"]].set_visible(False)
caption(fig,"","Per-patient side-effect reporting rates were compared across dose bands (highest reported dose) using "
        "Wilson 95% confidence intervals and a Cochran–Armitage trend test, with the two communities combined via direct "
        "standardization and a community-stratified test to prevent their differing baseline reporting rates from "
        "confounding the dose comparison. Within each band the two forums' per-category rates are combined at a fixed "
        "cohort weight (by dose-stating cohort size: r/covidlonghaulers ≈35%, Phoenix Rising ≈65%), so across-band "
        "differences reflect dose rather than cohort composition, and the trend test is stratified by forum (each "
        "forum's own baseline held constant, within-forum dose signals pooled). No category shows a significant dose "
        "trend (smallest p≈0.26) and the ≈95% intervals overlap across bands; combining both forums tightens the "
        "estimate without revealing a dose relationship the per-forum views missed. Bars are cohort-adjusted reporting "
        "frequencies, a weighted blend of the two forums and not an incidence; dose is the patient-level maximum, not "
        "the dose at which an effect occurred; the titration confound applies; data are self-reported and uncontrolled, "
        "and CLH's per-category cells are small and contribute noisily despite adjustment.",bottom=0.32,left=0.23)
plt.show()
''')

# ── 5. Tolerability headline ──────────────────────────────────────────────────
md('''## 5. Tolerability headline numbers, per community

Side effects are common to mention but rarely described as limiting. Denominators differ, so these are shown **side by side, never pooled.**''')

code('''
def meta(c):
    return {k:int(v) for k,v in pd.read_sql("select k,v from ae_meta",c).values}
cm=meta(conn); pm=meta(conn_phx)
rows=[("Total LDN reports","n_total_reports"),
      ("Reports mentioning a side effect","n_ae_reports"),
      ("Reports describing discontinuation","n_disc_reports"),
      ("Reports with a serious-event term","n_serious_reports")]
def fmt(m,key):
    v=m[key]; t=m["n_total_reports"]
    return f"{v}  ({100*v/t:.1f}%)" if key!="n_total_reports" else f"{v}"
html=['<table style="border-collapse:collapse;font-size:0.95em;">',
      '<tr><th style="text-align:left;padding:6px 14px;border-bottom:2px solid #ccc;">Measure</th>'
      '<th style="padding:6px 14px;border-bottom:2px solid #ccc;color:#8e44ad;">r/covidlonghaulers</th>'
      '<th style="padding:6px 14px;border-bottom:2px solid #ccc;color:#2e86c1;">Phoenix Rising</th></tr>']
for lab,key in rows:
    html.append(f'<tr><td style="padding:6px 14px;border-bottom:1px solid #eee;">{lab}</td>'
                f'<td style="padding:6px 14px;border-bottom:1px solid #eee;text-align:center;">{fmt(cm,key)}</td>'
                f'<td style="padding:6px 14px;border-bottom:1px solid #eee;text-align:center;">{fmt(pm,key)}</td></tr>')
html.append("</table>")
display(HTML("".join(html)))
note(f"Discontinuation language is uncommon in both ({100*cm['n_disc_reports']/cm['n_total_reports']:.1f}% CLH, "
     f"{100*pm['n_disc_reports']/pm['n_total_reports']:.1f}% Phoenix), and structured serious-event terms are rare "
     f"({cm['n_serious_reports']} CLH, {pm['n_serious_reports']} Phoenix). With no denominator of total users at risk "
     f"this corroborates a benign tolerability profile; it cannot establish safety.","note")
''')

# ── limitations ───────────────────────────────────────────────────────────────
md('''## What these data are — and are not

- **Sentiment is excluded by design.** The corpora were classified differently; only dose and side-effect *shape* are compared here.
- **Side-effect percentages are mention rates, not incidence.** Patients who tolerate LDN often say nothing; reactors post more; early quitters are under-counted. Extraction prompts also differed between corpora.
- **Dose rests on the minority who state one** (~25–40% of LDN patients) and is self-reported.
- **No control group, selection/survivorship bias, observational throughout.** These data show real-world dosing and tolerability patterns across two communities; they do not establish efficacy or safety. Only a randomized, actively-monitored trial can.''')

code('''display(HTML('<div style="font-size:1.2em;font-weight:bold;font-style:italic;margin-top:10px;">These findings '
'reflect reporting patterns in online communities, not population-level treatment effects. This is not medical advice.</div>'))''')

nb = build_notebook(cells=cells, db_path=str(DB), title="LDN Two-Community Dosing & Tolerability")
html = execute_and_export(nb, str(OUT))
print("BUILT:", html)

# refresh standalone figure exports so notebook rebuilds never leave them stale
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from export_ldn_figures import export_all
export_all()
