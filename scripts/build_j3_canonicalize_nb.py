"""
build_j3_canonicalize_nb.py — Judgement ③ (canonicalisation) accuracy + agreement.

Each model was asked to merge a list of drug alias surface-forms (from the ① alias data) into synonym
groups. We KNOW the correct grouping — every alias's real drug — so this is one of the few judgements with a
real gold. Score: how well each model's merge groups match the drug groups (Adjusted Rand Index + merge
precision/recall on alias pairs), plus cross-model agreement. Code-free HTML.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notebooks"))
from build_notebook import build_notebook, execute_and_export

RUNS = (ROOT / "data" / "validation" / "j3_canonicalize_runs.json").as_posix()
DB = (ROOT / "patientpunk.db").as_posix()

FRAME = (
"# Judgement ③ — canonicalisation: do models merge synonyms correctly?\n\n"
"Canonicalisation is the merge/split decision — should `\"LDN\"` and `\"low dose naltrexone\"` collapse to one "
"drug? Unusually for these judgements, we have a **real gold**: the alias surface-forms come from the ① "
"alias-generation run, so we know each one's true drug. Every model was given the deduped alias list and "
"asked to group synonyms; we score its grouping against the true drug grouping (Adjusted Rand Index + "
"pairwise merge precision/recall) and check how much the models agree with each other.")

LOAD = r'''
import json
import numpy as np
from itertools import combinations
from collections import defaultdict, Counter
def adjusted_rand_score(t, p):
    n=len(t); c2=lambda x:x*(x-1)//2
    cont=Counter(zip(t,p)); a=Counter(t); b=Counter(p)
    sc=sum(c2(v) for v in cont.values()); sa=sum(c2(v) for v in a.values()); sb=sum(c2(v) for v in b.values())
    tot=c2(n); exp=sa*sb/tot if tot else 0; mx=(sa+sb)/2
    return 1.0 if mx-exp==0 else (sc-exp)/(mx-exp)
d=json.load(open(r"__RUNS__")); gold=d["gold"]; canon=d["canon"]; M=d["manifest"]
names=list(gold); short=lambda m:m.split("/")[-1]
gold_lab=[gold[n] for n in names]
MODELS=[m for m in canon if canon[m]]
def model_labels(m):
    c=canon[m]; return [c.get(n,n) for n in names]   # canonical representative per alias
def merge_pr(m):
    lab=model_labels(m); tp=fp=fn=0
    for i,j in combinations(range(len(names)),2):
        g=(gold_lab[i]==gold_lab[j]); p=(lab[i]==lab[j])
        if g and p: tp+=1
        elif p and not g: fp+=1
        elif g and not p: fn+=1
    prec=tp/(tp+fp) if tp+fp else 1.0; rec=tp/(tp+fn) if tp+fn else 1.0
    f1=2*prec*rec/(prec+rec) if prec+rec else 0
    return prec,rec,f1
stats={m:(adjusted_rand_score(gold_lab, model_labels(m)),)+merge_pr(m) for m in MODELS}
display(Markdown(f"*(loaded — {len(names)} aliases over {M['n_drugs']} drugs, {len(MODELS)} models)*"))
'''.replace("__RUNS__", RUNS)

S1 = ("## 1. Canonicalisation accuracy per model\n\n"
      "Adjusted Rand Index (grouping vs the true drug grouping; 1.0 = perfect, 0 = chance) and the underlying "
      "merge precision/recall on alias pairs.")
S1_CODE = r'''
rows=sorted(MODELS, key=lambda m:-stats[m][0])
fig,ax=plt.subplots(figsize=(8.5,6))
ax.barh([short(m) for m in rows],[stats[m][0] for m in rows],color=["#27ae60" if stats[m][0]>0.8 else "#e67e22" if stats[m][0]>0.6 else "#c0392b" for m in rows])
for i,m in enumerate(rows): ax.text(stats[m][0]+0.01,i,f"{stats[m][0]:.2f}",va="center",fontsize=8)
ax.invert_yaxis(); ax.set_xlabel("Adjusted Rand Index vs true drug grouping"); ax.set_xlim(0,1.05)
ax.set_title("Canonicalisation accuracy (ARI) per model"); fig.tight_layout(); plt.show()
tb=[[short(m), f"{stats[m][0]:.2f}", f"{stats[m][1]:.0%}", f"{stats[m][2]:.0%}", f"{stats[m][3]:.0%}"] for m in rows]
display(HTML("<b>Per-model: ARI + pairwise merge precision / recall / F1</b>"+
             pd.DataFrame(tb, columns=["model","ARI","merge precision","merge recall","merge F1"]).to_html(index=False)))
aris=[stats[m][0] for m in MODELS]; recs=[stats[m][2] for m in MODELS]
display(Markdown(f"**Median ARI {np.median(aris):.2f}, median merge-recall {np.median(recs):.0%}.** "
 f"The dominant error mode is under-merging — a model leaves `\"famo\"`, `\"pepcid\"`, `\"famotidine hcl\"` in "
 f"separate groups (recall < precision). Splitting distinct drugs apart (precision) is rarely the problem; "
 f"**collapsing all the surface variants of one drug is the hard part**, and it's where models differ most."))
'''

S2 = "## 2. Do the models agree with each other on the merges?"
S2_CODE = r'''
pairs=[adjusted_rand_score(model_labels(a),model_labels(b)) for a,b in combinations(MODELS,2)]
gold_ari=[stats[m][0] for m in MODELS]
display(Markdown(
 f"**Mean pairwise ARI between models: {np.mean(pairs):.2f}** (vs mean {np.mean(gold_ari):.2f} against the "
 f"gold). Models agree with *each other* about as much as with the truth — canonicalisation is fairly "
 f"determined (there's a right answer and capable models mostly find it), so cross-model divergence here is a "
 f"reliable outlier signal, not underdetermination. A model far below the pack is genuinely worse at merging, "
 f"not just idiosyncratic."))
'''

S3 = "## 3. What gets mis-merged"
S3_CODE = r'''
# aliases most often left un-merged from their drug's main group, across models
from collections import Counter
miss=Counter()
for m in MODELS:
    lab=dict(zip(names, model_labels(m)))
    # main canonical for each drug = the most common label among that drug's aliases
    bydrug=defaultdict(list)
    for n in names: bydrug[gold[n]].append(n)
    for drug,al in bydrug.items():
        labs=[lab[n] for n in al]; main=Counter(labs).most_common(1)[0][0]
        for n in al:
            if lab[n]!=main: miss[n]+=1
top=miss.most_common(12)
if top:
    tb=[[n, gold[n], f"{c}/{len(MODELS)}"] for n,c in top]
    display(HTML("<b>Aliases most often left un-merged from their drug (across models)</b>"+
                 pd.DataFrame(tb,columns=["alias","true drug","models that split it off"]).to_html(index=False)))
display(Markdown("These are the surface forms canonicalisation most often drops — typos/abbreviations/dose-"
 "bearing forms (`\"famotidine 20mg\"`, `\"famotadine\"`). A deterministic normalisation (lowercase, strip dose, "
 "edit-distance to the ingredient) or an RxNorm lookup would catch most before the LLM merge even runs."))
'''

S4 = "## 4. Verdict"
S4_CODE = r'''
aris=[stats[m][0] for m in MODELS]
lines=[
 f"- **Canonicalisation is one of the more accurate judgements** — median ARI {np.median(aris):.2f} vs the true "
 f"drug grouping; the merge decision has a right answer and capable models mostly get it.",
 f"- **Under-merging is the failure mode** — models leave synonym/typo/dose variants in separate groups "
 f"(recall < precision). Splitting distinct drugs apart is rare.",
 f"- **Cross-model agreement ≈ agreement-with-gold**, so this judgement is *determined* — a model well below "
 f"the pack is a real outlier to drop, not just a different-but-valid style (unlike the subjective judgements).",
 f"- **Cheap win:** front the LLM merge with deterministic normalisation + RxNorm lookup (covers the "
 f"~38% RxNorm-scoreable names for free); reserve the model for the genuinely ambiguous merges.",
]
display(Markdown("\n".join(lines)))
'''

LIM = '''## Limitations

- **Gold is the 6-target-drug alias space** (plus incidental drugs from the ① run) — real corpus
  canonicalisation faces peptides, supplements, and drug *classes* that RxNorm can't score; this measures the
  cleaner drug-synonym case.
- **Merge quality measured on alias pairs / ARI** — a single mis-grouped high-frequency alias moves the number;
  read the tier, not the 2nd decimal.
- **One canonicalisation call per model** (no repeats) — no within-model variability here.
- Measures a normalisation step's correctness, not any treatment effect. Not medical advice.'''

PROV = r'''
prov=pd.DataFrame({"item":["gold","aliases","drugs","models","metric","skill"],
 "value":[M["gold_source"], str(M["n_names"]), str(M["n_drugs"]), str(len(MODELS)),
          "Adjusted Rand Index + pairwise merge P/R/F1", "research-assistant v2"]})
display(HTML("<b>Provenance</b>"+prov.to_html(index=False)))
display(HTML('<div style="font-size:1.15em;font-weight:bold;font-style:italic;margin-top:1em">'
             'Measures the correctness of a normalisation step, not treatment effects. Not medical advice.</div>'))
'''


def main():
    cells = [
        ("md", FRAME), ("code", LOAD),
        ("md", S1), ("code", S1_CODE),
        ("md", S2), ("code", S2_CODE),
        ("md", S3), ("code", S3_CODE),
        ("md", S4), ("code", S4_CODE),
        ("md", LIM), ("code", PROV),
    ]
    nb = build_notebook(cells, db_path=DB, title="Judgement 3 — canonicalisation accuracy")
    html = execute_and_export(nb, "notebooks/validation/j3_canonicalize", timeout=900)
    print("Wrote", html)


if __name__ == "__main__":
    main()
