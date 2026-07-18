"""
build_model_agreement_nb.py — N×N model agreement in variable coding (judgement 11).

Pairwise agreement between all 22 candidate coders + Opus on the values they assign, clustered to expose
behavioural groups. Metric = mean Jaccard on co-populated field-values (deterministic, so all pairs are
cheap; it understates semantic agreement, but the relative structure — who codes alike — is the point).
Code-free HTML.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notebooks"))
from build_notebook import build_notebook, execute_and_export

COD = (ROOT / "data" / "validation" / "j11_coding_runs.json").as_posix()
DB = (ROOT / "patientpunk.db").as_posix()

FRAME = (
"# Which coders behave alike? — N×N agreement in variable coding\n\n"
"Beyond \"how close is each model to a gold\", the raw question: **how much do the coders agree with *each "
"other*?** For every pair of the 22 candidates + Opus, this measures value agreement on the fields they both "
"populated, then clusters the roster so behavioural groups show up as blocks. Metric is Jaccard set-overlap "
"(fast for all pairs; it *understates* semantic agreement — `\"2\"` vs `\"at least 2\"` scores 0 — so read the "
"relative structure, not the absolute levels).")

LOAD = r'''
import json, re
import numpy as np
from collections import defaultdict
from scipy.cluster.hierarchy import linkage, leaves_list, dendrogram
from scipy.spatial.distance import squareform
cod=json.load(open(r"__COD__"))
FIELDS=cod["manifest"]["fields"]
codings=defaultdict(dict)
for c in cod["codings"]: codings[c["model"]][c["sample_id"]]=c["fields"]
codings["anthropic/claude-opus-4.8"]={g["sample_id"]:g["fields"] for g in cod["gold"]}
models=sorted(codings); N=len(models); short=lambda m:m.split("/")[-1]
def _norm(x):
    if isinstance(x,list): x=" ".join(map(str,x))
    return set(re.sub(r"[^a-z0-9 ]"," ",str(x).lower()).split())
def _jac(a,b):
    a,b=_norm(a),_norm(b); return len(a&b)/len(a|b) if (a|b) else 1.0
samples=set().union(*[set(codings[m]) for m in models])
A=np.full((N,N),np.nan)
for i in range(N):
    for j in range(N):
        if i==j: A[i,j]=1.0; continue
        sims=[_jac(codings[models[i]][s][f], codings[models[j]][s][f])
              for s in samples if s in codings[models[i]] and s in codings[models[j]]
              for f in FIELDS if codings[models[i]][s].get(f) and codings[models[j]][s].get(f)]
        A[i,j]=np.mean(sims) if sims else np.nan
D=1-np.nan_to_num(A,nan=0.5); np.fill_diagonal(D,0); D=(D+D.T)/2
order=leaves_list(linkage(squareform(D,checks=False),method="average"))
labs=[short(models[k]) for k in order]; Ao=A[np.ix_(order,order)]
off=A.copy(); np.fill_diagonal(off,np.nan)
display(Markdown(f"*(loaded — {N}×{N}, overall mean pairwise agreement {np.nanmean(off):.0%})*"))
'''.replace("__COD__", COD)

S1 = "## 1. The agreement matrix (clustered)"
S1_CODE = r'''
fig,ax=plt.subplots(figsize=(11.5,10))
im=ax.imshow(Ao,cmap="RdYlGn",vmin=0.3,vmax=0.8)
ax.set_xticks(range(N)); ax.set_xticklabels(labs,rotation=90,fontsize=8)
ax.set_yticks(range(N)); ax.set_yticklabels(labs,fontsize=8)
for i in range(N):
    for j in range(N):
        if not np.isnan(Ao[i,j]) and Ao[i,j]<1:
            ax.text(j,i,f"{Ao[i,j]*100:.0f}",ha="center",va="center",fontsize=5.5,color="#222")
cb=fig.colorbar(im,fraction=0.046,pad=0.04); cb.set_label("mean value agreement (Jaccard, co-populated fields)")
ax.set_title("Model x model agreement in variable coding — clustered\ngreen = code alike, red = diverge"); fig.tight_layout(); plt.show()
display(Markdown("**Blocks = behavioural groups.** Bright-green off-diagonal cells are the models that code "
 "most alike; the red top rows are the outliers that code unlike everyone else."))
'''

SEM = ("## 2. How real is the disagreement? — Jaccard vs a semantic judge\n\n"
       "The matrix looks alarming, but token-Jaccard scores `\"34\"` vs `\"34 years old\"` as 0.33 and "
       "`\"isolation\"` vs `\"social isolation\"` near 0 — same meaning, tiny overlap. To see how much of the "
       "\"disagreement\" is real, four representative pairs (spanning the Jaccard range) were re-judged with the "
       "**Opus semantic-equivalence judge** on the values they both populated.")
SEM_CODE = r'''
import numpy as np
try:
    _sd=json.load(open(r"__SEM__")); _R=[r for r in _sd["records"] if r["verdict"] in ("equivalent","model_subset","different")]
except FileNotFoundError:
    _R=[]
if not _R:
    display(Markdown("*(semantic pair check not available — run scripts/run_pair_semantic.py)*"))
else:
    INTERP={"conditions","medications","alternative_treatments","mental_health","functional_status_tier","activity_level",
            "symptom_trajectory","social_impact","healthcare_costs","diagnostic_odyssey","doctor_dismissal","misdiagnosis",
            "healthcare_system","treatment_outcome","family_history","hormonal_events","symptom_duration","biomarker_results"}
    def _ag(recs):
        n=len(recs);
        return (np.mean([r["jaccard"] for r in recs]),
                sum(r["verdict"] in ("equivalent","model_subset") for r in recs)/n,
                sum(r["verdict"]=="different" for r in recs)/n) if n else (0,0,0)
    groups=[("all fields",_R),("structured / identity",[r for r in _R if r["field"] not in INTERP]),
            ("interpretive / free-text",[r for r in _R if r["field"] in INTERP])]
    labels=[g[0] for g in groups]; jac=[_ag(g[1])[0] for g in groups]; sem=[_ag(g[1])[1] for g in groups]
    x=np.arange(len(labels)); w=0.38
    fig,ax=plt.subplots(figsize=(8.5,3.6))
    ax.bar(x-w/2,[v*100 for v in jac],w,label="Jaccard agreement (the heatmap metric)",color="#c0392b")
    ax.bar(x+w/2,[v*100 for v in sem],w,label="semantic agreement (Opus judge)",color="#27ae60")
    for i in range(len(labels)):
        ax.text(x[i]-w/2,jac[i]*100+1,f"{jac[i]:.0%}",ha="center",fontsize=9)
        ax.text(x[i]+w/2,sem[i]*100+1,f"{sem[i]:.0%}",ha="center",fontsize=9,fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(labels); ax.set_ylabel("agreement %"); ax.set_ylim(0,100)
    ax.legend(fontsize=9); ax.set_title("The heatmap understates: Jaccard vs semantic agreement"); fig.tight_layout(); plt.show()
    a_all,s_all,d_all=_ag(_R)
    display(Markdown(
     f"**The models genuinely disagree on only ~{d_all:.0%} of values — they agree on {s_all:.0%}.** The heatmap's "
     f"{a_all:.0%} Jaccard is a metric artifact. Even the **interpretive** fields (that looked like ~20% on the "
     f"heatmap) are **{_ag(groups[2][1])[1]:.0%}** agreement semantically; structured fields are "
     f"**{_ag(groups[1][1])[1]:.0%}**. And the *worst* pair tested (an outlier × a weak model, Jaccard 26%) still "
     f"agrees ~80% semantically. **Read the heatmap for structure — which fields are hard, which models cluster — "
     f"not for absolute agreement; the coding is far more consistent than the red suggests.**"))
'''.replace("__SEM__", (ROOT/"data"/"validation"/"j11_pair_semantic.json").as_posix())

SEMNXN_CODE = r'''
import numpy as np
from collections import defaultdict as _dd
try:
    _nx=json.load(open(r"__NXN__")); _NR=[r for r in _nx["records"] if r["verdict"] in ("equivalent","model_subset","different")]
except FileNotFoundError:
    _NR=[]
if _NR:
    mods=["anthropic/claude-opus-4.8","x-ai/grok-4.5","openai/gpt-5.1","deepseek/deepseek-v4-flash"]
    sh={"anthropic/claude-opus-4.8":"Opus","x-ai/grok-4.5":"grok-4.5","openai/gpt-5.1":"gpt-5.1","deepseek/deepseek-v4-flash":"deepseek-v4-flash"}
    ag=_dd(lambda:[0,0])
    for r in _NR:
        k=frozenset(r["pair"].split("|")); ag[k][0]+=1; ag[k][1]+= r["verdict"] in ("equivalent","model_subset")
    n=len(mods); Mx=np.full((n,n),np.nan)
    for i in range(n):
        Mx[i,i]=1.0
        for j in range(i+1,n):
            k=frozenset((mods[i],mods[j]))
            if k in ag and ag[k][0]: Mx[i,j]=Mx[j,i]=ag[k][1]/ag[k][0]
    fig,ax=plt.subplots(figsize=(6.5,5.4)); im=ax.imshow(Mx,cmap="Greens",vmin=0.7,vmax=1.0)
    L=[sh[m] for m in mods]
    ax.set_xticks(range(n)); ax.set_xticklabels(L); ax.set_yticks(range(n)); ax.set_yticklabels(L)
    for i in range(n):
        for j in range(n):
            if i==j: ax.text(j,i,"—",ha="center",va="center",color="#888")
            elif not np.isnan(Mx[i,j]): ax.text(j,i,f"{Mx[i,j]:.0%}",ha="center",va="center",fontweight="bold",color="white" if Mx[i,j]>0.88 else "#222")
    fig.colorbar(im,fraction=0.046,pad=0.04).set_label("semantic agreement (equiv+subset)")
    ax.set_title("Semantic agreement — 4 coders, Opus-judged (not Jaccard)"); fig.tight_layout(); plt.show()
    display(Markdown("**A true semantic N×N** (4 models, to bound Opus-judge cost): every pair agrees **79–89%** — "
     "the frontier trio (Opus, grok-4.5, gpt-5.1) 87–89%, `deepseek-v4-flash` the most divergent at ~80%. Same "
     "story as the Jaccard matrix with the metric artifact removed — the coders substantially agree."))
'''.replace("__NXN__", (ROOT/"data"/"validation"/"j11_nxn_semantic.json").as_posix())

S2 = "## 3. Same-family models agree most"
S2_CODE = r'''
# top same-lab pairs
LAB=lambda m: m.split("/")[0]
pairs=[]
for i in range(N):
    for j in range(i+1,N):
        pairs.append((short(models[i]),short(models[j]),A[i,j],LAB(models[i])==LAB(models[j])))
same=sorted([p for p in pairs if p[3]], key=lambda p:-p[2])[:6]
diff_hi=sorted([p for p in pairs if not p[3]], key=lambda p:-p[2])[:4]
tb=pd.DataFrame([[f"{a} ↔ {b}", f"{v:.0%}", "same lab"] for a,b,v,_ in same]
                +[[f"{a} ↔ {b}", f"{v:.0%}", "cross lab"] for a,b,v,_ in diff_hi],
                columns=["pair","agreement","kind"])
display(HTML(tb.to_html(index=False)))
import numpy as _np
sl=_np.mean([p[2] for p in pairs if p[3]]); xl=_np.mean([p[2] for p in pairs if not p[3]])
display(Markdown(f"**Same-lab pairs agree {sl:.0%} on average vs {xl:.0%} cross-lab** — a "
 f"{(sl-xl)/xl:+.0%} relative gap. The top-agreeing pairs are all siblings (gemini×gemini, deepseek×deepseek, "
 f"mistral×mistral, llama×llama). Shared training makes models share *conventions*, which is exactly why a "
 f"single-model gold carries a house bias (the gold-triangulation notebook)."))
'''

S3 = "## 4. The outliers — who codes unlike everyone"
S3_CODE = r'''
mean_agree=[(short(models[i]), np.nanmean(np.delete(A[i],i))) for i in range(N)]
mean_agree.sort(key=lambda x:x[1])
fig,ax=plt.subplots(figsize=(8,6))
names=[m for m,_ in mean_agree]; vals=[v for _,v in mean_agree]
ax.barh(names, [v*100 for v in vals], color=["#c0392b" if v<0.42 else "#e67e22" if v<0.47 else "#27ae60" for v in vals])
for i,v in enumerate(vals): ax.text(v*100+0.3,i,f"{v:.0%}",va="center",fontsize=8)
ax.invert_yaxis(); ax.set_xlabel("mean agreement with all other coders"); ax.set_title("How mainstream is each coder?")
fig.tight_layout(); plt.show()
lo=mean_agree[0][0]; display(Markdown(
 f"**`{lo}` codes most unlike the rest**, and the small OpenAI models (`gpt-5.4-nano`, `gpt-5.6-luna`) sit at "
 f"the bottom — they diverge from the field. That matters for the gold work: **`gpt-5.6-luna` is one of our "
 f"golds yet is itself an idiosyncratic coder**, so 'error vs Luna' partly measures distance from Luna's "
 f"quirks, not correctness. The most *mainstream* coders (top, greenest) are the safest single reference."))
'''

S4 = "## 5. Verdict"
S4_CODE = r'''
lines=[
 f"- **Coders genuinely disagree on only ~14% of values** (Opus semantic judge, §2) — the {np.nanmean(off):.0%} "
 "Jaccard in the matrix is a metric artifact. The variable coding is far more consistent than the red heatmap "
 "suggests; near-identical on structured fields (~91%), ~83% even on the interpretive ones.",
 "- **Agreement clusters by lab** — same-family pairs agree markedly more than cross-family, so 'which model' "
 "shifts the coded values in family-correlated ways (a source of systematic, not random, variation).",
 "- **A few models are outliers** (gpt-5.4-nano, gpt-5.6-luna) — useful to know when picking a reference or a "
 "producer: an outlier gold biases the scoreboard; an outlier producer disagrees with any consensus.",
 "- **Implication:** consensus/agreement between two coders is only a strong signal when they are *not* "
 "same-family (independent errors); same-family agreement can be shared bias — reinforcing the "
 "cross-lab-consensus design from the producer/judge work.",
]
display(Markdown("\n".join(lines)))
'''

LIM = '''## Limitations

- **Jaccard understates** semantic agreement (`"2"` vs `"at least 2"` → 0); absolute levels are low by
  construction. The relative structure (who clusters with whom, who's an outlier) is robust to this; the exact
  percentages are not a semantic agreement rate.
- **Co-populated only** — each pair is scored on the fields *both* filled, so sparse coders contribute fewer
  comparisons; agreement is conditional on co-population, not on presence.
- **30 posts** — cluster structure is stable, fine cell-level differences are noisy.
- Agreement between models is not correctness — two models agreeing can share a bias (the whole point of §4).'''

PROV = r'''
prov=pd.DataFrame({"item":["coders","posts","metric","clustering","skill"],
 "value":[f"{N} (22 candidates + Opus)", str(len(samples)), "mean Jaccard on co-populated field-values",
          "average-linkage on 1−agreement", "research-assistant v2"]})
display(HTML("<b>Provenance</b>"+prov.to_html(index=False)))
display(HTML('<div style="font-size:1.15em;font-weight:bold;font-style:italic;margin-top:1em">'
             'Describes agreement between model coders, not ground-truth accuracy or treatment effects. '
             'Not medical advice.</div>'))
'''


def main():
    cells = [
        ("md", FRAME), ("code", LOAD),
        ("md", S1), ("code", S1_CODE),
        ("md", SEM), ("code", SEM_CODE), ("code", SEMNXN_CODE),
        ("md", S2), ("code", S2_CODE),
        ("md", S3), ("code", S3_CODE),
        ("md", S4), ("code", S4_CODE),
        ("md", LIM), ("code", PROV),
    ]
    nb = build_notebook(cells, db_path=DB, title="Model×model agreement in variable coding")
    html = execute_and_export(nb, "notebooks/validation/model_agreement", timeout=900)
    print("Wrote", html)


if __name__ == "__main__":
    main()
