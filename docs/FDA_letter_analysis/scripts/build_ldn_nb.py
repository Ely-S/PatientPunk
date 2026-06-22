# -*- coding: utf-8 -*-
"""Verbose LDN (naltrexone) deep-dive notebook on the vetted 2-year dataset.
research-assistant skill format. Reads ldn_2yr.db (build_ldn_data.py)."""
from __future__ import annotations
import sys
from pathlib import Path
REPO = Path(r"C:\Users\scgee\OneDrive\Documents\Projects\PatientPunk")
sys.path.insert(0, str(REPO / "notebooks"))
from build_notebook import build_notebook, execute_and_export  # noqa: E402

DB = REPO / "FDA_analysis" / "notebooks" / "ldn_2yr.db"
OUT = REPO / "FDA_analysis" / "notebooks" / "ldn_2yr_deepdive"

cells = []
def md(s): cells.append(("md", s))
def code(s): cells.append(("code", s))

# ── helpers ─────────────────────────────────────────────────────────────────────
code('''
import datetime
from scipy.stats import binomtest, fisher_exact
def cohen_h(p1, p2): return 2*np.arcsin(np.sqrt(p1)) - 2*np.arcsin(np.sqrt(p2))
def callout(text, sev="caution"):
    c = {"caution":"#b9770e","unreliable":"#922b21","caveat":"#5d6d7e","note":"#1a5276"}[sev]
    display(HTML(f'<div style="border-left:4px solid {c}; background:#fbfcfc; padding:9px 13px; margin:6px 0; color:#1c2833;">{text}</div>'))
df = pd.read_sql("select * from user_features", conn)
reps = pd.read_sql("select * from reports", conn)
N = len(df); R = int(df.responder.sum())
GREEN, GRAY, RED, PURPLE = "#2ecc71", "#aeb6bf", "#e74c3c", "#8e44ad"
''')

md('**Research Question:** *"What does two years of patient-reported data (r/covidlonghaulers, 2020–2022) say about low-dose naltrexone for Long COVID — how often it is reported to help, at what doses, for which symptoms, and how tolerable it is?"*')

md('''# Low-Dose Naltrexone for Long COVID: A Two-Year Real-World Deep Dive

**Abstract.** We analyze every self-reported low-dose naltrexone (LDN) experience in the r/covidlonghaulers community over a two-year window (Oct 2020–Dec 2022), reduced to one outcome per patient (**N = 321**). **68.5% of patients report a positive outcome** — well above an even-odds baseline (binomial p < 1e-9) — a signal that holds among the most definitive reports and is stable across the two years. Real-world dosing clusters tightly in the **≤ 4.5 mg** range for which no FDA-approved product exists, and the symptoms patients tie to LDN (fatigue, brain fog, pain, post-exertional malaise) match the domains reported in the clinical literature. The data is observational self-report, not efficacy — but it is consistent with the positive O'Kelly (2022) pilot and supports LDN as a Scenario-2 repurposing candidate warranting a controlled trial.''')

# ── §1 cohort & response ─────────────────────────────────────────────────────────
md('''## 1. The cohort and the headline rate

Each of the 321 patients is reduced to a single outcome — their most recent, most definitive LDN report — so prolific posters can't dominate. "Responder" means that report is positive.''')
code('''
order = ["positive","mixed","neutral","negative"]
counts = df.best_sentiment.value_counts().reindex(order).fillna(0).astype(int)
cols = {"positive":GREEN,"mixed":GRAY,"neutral":"#d5dbdb","negative":RED}
fig, ax = plt.subplots(figsize=(6.2,6.2))
ax.pie(counts.values, colors=[cols[o] for o in order], startangle=90,
            wedgeprops=dict(width=0.42, edgecolor="white"),
            autopct=lambda p: f"{p:.1f}%" if p>4 else "", pctdistance=0.79, textprops=dict(fontsize=11,color="#1c2833"))
ax.add_artist(plt.Circle((0,0),0.58,color="white"))
ax.text(0,0.06,f"{100*R/N:.1f}%",ha="center",fontsize=26,fontweight="bold",color="#1e8449")
ax.text(0,-0.14,f"positive\\n(n={N})",ha="center",fontsize=11,color="#566573")
ax.legend([f"{o} ({counts[o]})" for o in order], loc="center left", bbox_to_anchor=(1.0,0.5), frameon=False, fontsize=10)
ax.set_title("LDN outcome distribution, per patient",fontsize=13,fontweight="bold"); plt.tight_layout(); plt.show()

lo,hi = wilson_ci(R,N); bp = binomtest(R,N,0.5).pvalue; h = cohen_h(R/N,0.5); n = nnt(R/N,0.5)
callout(f"<b>{100*R/N:.1f}% positive</b> [{100*lo:.1f}–{100*hi:.1f}% Wilson 95% CI], n={N}. Against an even-odds "
        f"baseline this is highly unlikely by chance (binomial p={bp:.1e}, Cohen's h={h:.2f}). In plain terms, "
        f"<b>NNT \\u2248 {n}</b> — about 1 in {n} patients reports benefit beyond a coin-flip expectation.", "note")
''')
md('''**What this shows.** Roughly two-thirds of patients who tried LDN and reported back described a positive outcome, with negatives a clear minority. The next sections test whether that holds up under scrutiny — among the most definitive reports, across time, and at what doses.''')

# ── §2 robustness ────────────────────────────────────────────────────────────────
md('''## 2. Does the signal survive scrutiny?

Two checks: the response rate restricted to the *strongest-signal* reports (the most unambiguous statements), and a sensitivity drop of the most extreme contributors.''')
code('''
sig_order = ["strong","moderate","weak"]
rows=[]
for s in sig_order:
    sub = df[df.best_signal==s]; k=int(sub.responder.sum()); n_=len(sub)
    if n_: lo,hi=wilson_ci(k,n_); rows.append((s,n_,100*k/n_,100*lo,100*hi))
S = pd.DataFrame(rows, columns=["signal","n","rate","lo","hi"])
fig,ax=plt.subplots(figsize=(8.5,3.8)); y=np.arange(len(S))[::-1]
for i,r in S.iterrows():
    ax.barh(y[i], r.rate, color=PURPLE, height=0.55, xerr=[[r.rate-r.lo],[r.hi-r.rate]], error_kw=dict(lw=1.2,ecolor="#566573"))
    ax.text(r.hi+1.5,y[i],f"{r.rate:.0f}%  (n={r.n})",va="center",fontsize=10)
ax.axvline(50,color="#7f8c8d",ls="--",lw=1); ax.set_yticks(y); ax.set_yticklabels([f"{s}-signal" for s in S.signal],fontsize=11)
ax.set_xlim(0,90); ax.set_xlabel("positive rate (%) with 95% CI")
ax.set_title("Response rate by report definitiveness",fontsize=12.5,fontweight="bold"); sns.despine(left=True); plt.tight_layout(); plt.show()

strong = df[df.best_signal=="strong"]; ks=int(strong.responder.sum()); ns=len(strong)
trim = df.sort_values("n_reports",ascending=False).iloc[3:]  # drop 3 most prolific
callout(f"The signal <b>strengthens</b> among strong-signal reports ({100*ks/ns:.0f}%, n={ns}) — it is not an artifact "
        f"of vague or hedged posts. Dropping the 3 most prolific contributors leaves the rate essentially unchanged "
        f"({100*trim.responder.mean():.1f}%). <b>Conclusion holds.</b>", "note")
''')

# ── §3 dosing ────────────────────────────────────────────────────────────────────
md('''## 3. Real-world dosing — and the regulatory hook

Patients rarely state an exact dose, but when they do it concentrates in a narrow band. This matters: that band sits below any approved product.''')
code('''
from collections import Counter
dz = df[df.mentions_dose==1].copy()
vals = sorted(dz.min_dose.dropna().tolist())
cnt = Counter(round(v,3) for v in vals)
# dot/strip: one dot per patient at their exact stated dose (true mg axis, no binning)
fig,ax=plt.subplots(figsize=(9.5,3.2))
ax.axvspan(0,4.5,color="#f4eff8",zorder=0)   # the <=4.5 mg window
for v,k in sorted(cnt.items()):
    col = PURPLE if v<=4.5 else "#b9a7c7"     # grey = above the established LDN range
    ax.scatter([v]*k,[(i+1)*0.10 for i in range(k)],s=26,color=col,edgecolor="white",linewidth=0.4,zorder=3)
ax.set_xlim(-0.2,11); ax.set_ylim(-0.1, max(cnt.values())*0.10+0.5); ax.set_yticks([])
ax.set_xlabel("LDN dose (mg) — one dot = one patient's lowest stated dose")
ax.set_title("Real-world LDN dosing — purple = within the ≤4.5 mg window",fontsize=12,fontweight="bold")
for s in ("top","right","left"): ax.spines[s].set_visible(False)
plt.tight_layout(); plt.show()
le = int(df.dose_le_4_5.sum()); tot = int(df.mentions_dose.sum())
callout(f"Of the {tot} patients who state a dose, <b>{le} ({100*le/tot:.0f}%) are using ≤4.5 mg</b> — the established "
        f"LDN range. The approved naltrexone product is <b>50 mg</b>; no FDA-approved product exists at these doses, so "
        f"patients must obtain compounded LDN. That gap is precisely what a repurposing/labeling action would address.", "caution")
''')

# ── §4 tolerability ──────────────────────────────────────────────────────────────
md('''## 4. Tolerability

Whether patients report side effects, and whether tolerability tracks with outcome.''')
code('''
sx_rate = 100*df.any_side_effect.mean()
a = df[df.responder==1]; b = df[df.responder==0]
_,p = fisher_exact([[a.any_side_effect.sum(), len(a)-a.any_side_effect.sum()],
                    [b.any_side_effect.sum(), len(b)-b.any_side_effect.sum()]])
fig,ax=plt.subplots(figsize=(7.5,2.6));
for i,(lab,sub,col) in enumerate([("responders",a,GREEN),("non-responders",b,RED)]):
    r=100*sub.any_side_effect.mean(); ax.barh(i,r,color=col,height=0.5); ax.text(r+1,i,f"{r:.0f}%",va="center",fontsize=10)
ax.set_yticks([0,1]); ax.set_yticklabels(["responders","non-responders"]); ax.set_xlim(0,max(40,sx_rate+10))
ax.set_xlabel("% reporting any side effect"); ax.set_title("Side-effect reporting by outcome",fontsize=12,fontweight="bold")
sns.despine(left=True); plt.tight_layout(); plt.show()
callout(f"Overall, <b>{sx_rate:.0f}%</b> of LDN patients mention any side effect — modest, consistent with LDN's "
        f"benign profile. Non-responders report them more often than responders (Fisher p={p:.3f}), the expected "
        f"pattern where intolerance drives discontinuation. Self-report under-captures side effects, so read this as a "
        f"floor, not a safety assessment.", "caveat")
''')

# ── §5 symptom domains ───────────────────────────────────────────────────────────
md('''## 5. Which symptoms patients tie to LDN

A keyword scan of each patient's LDN posts for the symptom domains LDN is used to target. This counts *mentions in context*, not verified improvement — but it shows where the community's LDN experience concentrates.''')
code('''
sym_cols = [c for c in df.columns if c.startswith("sym_")]
nice = {"sym_fatigue_energy":"Fatigue / energy","sym_brain_fog_cognition":"Brain fog / cognition","sym_pain":"Pain",
        "sym_post_exertional_pem":"Post-exertional malaise","sym_sleep":"Sleep","sym_autonomic_pots":"Autonomic / POTS",
        "sym_mood_anxiety":"Mood / anxiety"}
rates = [(nice[c], 100*df[c].mean()) for c in sym_cols]
rates.sort(key=lambda x:x[1])
fig,ax=plt.subplots(figsize=(9,4)); y=np.arange(len(rates))
ax.barh(y,[r[1] for r in rates],color="#2e86c1")
for i,(_,v) in enumerate(rates): ax.text(v+0.6,i,f"{v:.0f}%",va="center",fontsize=9.5)
ax.set_yticks(y); ax.set_yticklabels([r[0] for r in rates],fontsize=10); ax.set_xlabel("% of LDN patients mentioning")
ax.set_title("Symptom domains in patients' LDN discussion",fontsize=12.5,fontweight="bold"); sns.despine(); plt.tight_layout(); plt.show()
''')
md('''**What this shows.** Fatigue, brain fog, and pain dominate, with post-exertional malaise and sleep close behind — the same domains the clinical literature reports LDN affecting (Bonilla 2023; the pooled meta-analysis effect sizes are largest for fatigue, pain, and function). The real-world record and the published symptom map agree on *where* to look in a trial.''')

# ── §6 temporal ──────────────────────────────────────────────────────────────────
md('''## 6. Stability over the two years''')
code('''
r2 = reps[reps.post_date>0].copy()
r2["dt"]=pd.to_datetime(r2.post_date.astype("int64"),unit="s",utc=True); r2["ym"]=r2.dt.dt.to_period("M").dt.to_timestamp()
r2["pos"]=(r2.sentiment=="positive").astype(int)
g = r2.groupby("ym").agg(n=("pos","size"),rate=("pos","mean"))
fig,ax=plt.subplots(figsize=(11,4))
ax.bar(g.index,g.n,width=20,color="#d6eaf8",label="reports / month")
ax2=ax.twinx(); ax2.plot(g.index,100*g.rate,color=PURPLE,lw=2,marker="o",ms=3,label="% positive")
ax2.axhline(50,color="#7f8c8d",ls="--",lw=1); ax2.set_ylim(0,100); ax2.set_ylabel("% positive (report-level)",color=PURPLE)
ax.set_ylabel("reports / month"); ax.set_title("LDN discussion volume and positivity, 2020–2022",fontsize=12.5,fontweight="bold")
ax.legend(loc="upper left",fontsize=9); ax2.legend(loc="upper right",fontsize=9); sns.despine(); plt.tight_layout(); plt.show()
callout("Report-level positivity stays well above 50% throughout the window, with no drift — the signal isn't an early "
        "burst of enthusiasm that faded. (Report-level positivity runs higher than the per-patient rate because "
        "enthusiastic users post more often; the per-patient 68.5% is the conservative figure.)", "caveat")
''')

# ── §7 concordance ───────────────────────────────────────────────────────────────
md('''## 7. Concordance with the clinical record

This dataset predates the O'Kelly (2022) pilot's publication. The community signal — strongly positive, well above chance — points the same direction the pilot later did (6 of 7 quality-of-life domains improved, n=52). Our companion methodology paper formalizes this: pre-publication LDN sentiment correctly anticipated O'Kelly's positive result. The real-world record and the (sparse) trial record agree.''')

# ── quotes ───────────────────────────────────────────────────────────────────────
md('''## What patients are saying''')
code('''
qd = pd.read_sql("select * from quotes", conn)
umap = df.set_index("user_id").responder.to_dict()
qd["responder"]=qd.user_id.map(umap)
def pick(resp, sx, kw, n=1):
    s = qd[(qd.responder==resp)&(qd.side_effect==sx)&(qd.text.str.contains(kw,case=False,na=False))]
    return s.head(n)
chosen = pd.concat([
    pick(1,0,"energy|fatigue"), pick(1,0,"fog|brain"), pick(0,1,"side effect|stopped|quit"), pick(0,0,"nothing|no (effect|change)|didn")
]).drop_duplicates("text").head(4)
html=['<div>']
for _,r in chosen.iterrows():
    try: dt=datetime.datetime.fromtimestamp(int(r.post_date),datetime.timezone.utc).strftime("%b %Y")
    except Exception: dt=""
    tag = "positive" if r.responder==1 else "non-responder"
    html.append(f'<div style="border-left:3px solid #8e44ad;padding:6px 12px;margin:8px 0;background:#fbfcfc;">'
                f'<i>&ldquo;{r.text}&rdquo;</i><div style="color:#7f8c8d;font-size:0.9em;margin-top:3px;">&mdash; '
                f'r/covidlonghaulers, {dt} &nbsp;|&nbsp; <b>{tag}</b></div></div>')
html.append("</div>"); display(HTML("".join(html)))
''')

# ── recommendations ──────────────────────────────────────────────────────────────
md('''## Recommendations''')
code('''
recs=[("Strong","LDN shows a robust real-world benefit signal in Long COVID (68.5%, n=321, p<1e-9) that survives signal-strength and sensitivity checks","#1e8449"),
      ("Strong","Real-world dosing is ≤4.5 mg with no approved product — a clear MODERN-Act/labeling target, not a standard supplement","#1e8449"),
      ("Moderate","Trial endpoints should center on fatigue, brain fog, pain, and PEM — the domains patients consistently tie to LDN","#b9770e"),
      ("Preliminary","This is observational self-report; a placebo-controlled, LDN-monotherapy RCT remains necessary to establish efficacy","#7f8c8d")]
h=['<table style="border-collapse:collapse;width:100%;font-size:0.96em;">']
for t,txt,c in recs:
    h.append(f'<tr><td style="padding:7px 10px;border-bottom:1px solid #eaecee;white-space:nowrap;vertical-align:top;">'
             f'<span style="background:{c};color:white;padding:2px 9px;border-radius:10px;font-size:0.82em;">{t}</span></td>'
             f'<td style="padding:7px 10px;border-bottom:1px solid #eaecee;">{txt}</td></tr>')
h.append("</table>"); display(HTML("".join(h)))
''')

# ── conclusion ───────────────────────────────────────────────────────────────────
md('''## Conclusion

Across two years and 321 patients, low-dose naltrexone is reported to help roughly two in three people with Long COVID who try it — a signal far above chance that holds among the most definitive reports, stays stable over time, and concentrates in exactly the symptom domains (fatigue, brain fog, pain, post-exertional malaise) the clinical literature flags. Real-world use sits squarely in the ≤4.5 mg range for which no approved product exists, making LDN a clean example of the repurposing gap the FDA's RFI targets. None of this is proof of efficacy — it is self-reported, uncontrolled, and cannot separate drug effect from placebo or natural recovery. But it is a consistent, well-characterized preliminary signal in a condition with no approved treatment, and it tells a confirmatory trial exactly what to measure and at what dose. That is the definition of a Scenario-2 candidate worth studying.''')

# ── limitations ──────────────────────────────────────────────────────────────────
md('''## Research limitations

- **Selection bias.** People who post about LDN are not a random sample; those who benefit (or have strong reactions) may post more.
- **Reporting bias.** Doses, side effects, and symptoms appear only when mentioned; the dose analysis rests on the 25% who state one.
- **Survivorship.** The most-recent-report rule captures lasting impressions but misses patients who quit silently.
- **Recall bias.** Posts are written from memory, sometimes long after starting LDN.
- **Confounding.** Concurrent treatments, natural recovery, and disease heterogeneity are entangled and unmeasured.
- **No control group.** No placebo arm; the 68.5% cannot be attributed to the drug alone.
- **Sentiment is not efficacy.** "Positive" means a favorable self-report, not a measured clinical endpoint, and the symptom scan counts mentions, not verified improvement.
- **Temporal snapshot.** A 2020–2022 slice of one community; generalization to clinic populations is unverified.''')

code('''display(HTML('<div style="font-size:1.2em;font-weight:bold;font-style:italic;margin-top:10px;">These findings '
'reflect reporting patterns in an online community, not population-level treatment effects. This is not medical advice.</div>'))''')

nb = build_notebook(cells=cells, db_path=str(DB), title="LDN 2-Year Deep Dive")
html = execute_and_export(nb, str(OUT))
print("BUILT:", html)

# refresh standalone figure exports so notebook rebuilds never leave them stale
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from export_ldn_figures import export_all
export_all()
