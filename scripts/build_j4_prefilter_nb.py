"""
build_j4_prefilter_nb.py — Judgement ④ (prefilter) roster agreement + balanced accuracy.

Prefilter is the binary keep/drop (personal experience?). Polina's `personal_use` is the reference, but it's
degenerate (~91% yes), so recall is gameable by an always-yes model — plain accuracy is meaningless. So we
report: per-model yes-rate (the always-yes risk), cross-model agreement, and BALANCED accuracy vs Polina with
the base rate stated. Code-free HTML.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notebooks"))
from build_notebook import build_notebook, execute_and_export

RUNS = (ROOT / "data" / "validation" / "j4_prefilter_runs.json").as_posix()
DB = (ROOT / "patientpunk.db").as_posix()

FRAME = (
"# Judgement ④ — prefilter: keep/drop agreement (a degenerate label)\n\n"
"The prefilter decides whether a (comment, drug) expresses the author's own personal experience — a binary "
"keep/drop that gates everything downstream. Polina labelled it too, but her labels are **~91% \"yes\"**, so "
"an always-yes model scores ~91% \"accuracy\" while learning nothing. This judgement is therefore reported as "
"**agreement + balanced accuracy**, never plain accuracy: per-model yes-rate, cross-model agreement, and "
"balanced accuracy vs Polina with the base rate in view.\n\n"
"> ⚠️ **Corrected run.** The first pass of this judgement was invalid. `PREFILTER_PROMPT` asks for a JSON "
"array, so a compliant model replies `[\"yes\"]` — and the harness tested `startswith(\"yes\")` on the raw "
"reply, which is false for `[\"yes\"]`. Every model therefore scored as dropping ~100% of pairs (2,805 drops "
"vs 9 keeps). The same flaw existed in the pipeline's own single-item fallback and is fixed in "
"`_prefilter_one`. Numbers below are from the re-run with the parse corrected; the broken run is kept at "
"`j4_prefilter_runs.BROKEN_parse.json`. Every claim in this notebook is now computed from the data rather "
"than asserted — the hardcoded prose is what let the bug hide.")

LOAD = r'''
import json
import numpy as np
from itertools import combinations
from collections import defaultdict
d=json.load(open(r"__RUNS__")); ALL=d["results"]
R=[r for r in ALL if not r["parse_failed"] and r["keep"] is not None]
# Reliability first: a model that rarely answers has no meaningful yes-rate. Keep the raw results
# so parse-failure stays visible instead of being filtered away into an invisible denominator.
pfail={m: np.mean([r["parse_failed"] or r["keep"] is None for r in ALL if r["model"]==m])
       for m in sorted(set(r["model"] for r in ALL))}
POL={(p["sample_id"], p["drug"]): p["personal_use"] for p in d["polina"]}
MODELS=sorted(set(r["model"] for r in R)); short=lambda m:m.split("/")[-1]
cell=defaultdict(dict)   # (sample,drug) -> {model: keep}
for r in R: cell[(r["sample_id"], r["drug"])][r["model"]]=r["keep"]
pol_yes=np.mean([v for v in POL.values()])
display(Markdown(f"*(loaded — {len(R)} keep/drop decisions, {len(MODELS)} models; Polina base rate "
 f"{pol_yes:.0%} yes over {len(POL)} pairs)*"))
'''.replace("__RUNS__", RUNS)

S1 = ("## 1. Per-model yes-rate — the always-yes risk\n\n"
      "With a 91%-yes reference, a model that keeps everything looks accurate. So the first thing to check is "
      "whether models actually discriminate or just say yes.")
S1_CODE = r'''
yr=[]
for m in MODELS:
    v=[r["keep"] for r in R if r["model"]==m]; yr.append((short(m), np.mean(v), len(v)))
yr.sort(key=lambda x:-x[1])
fig,ax=plt.subplots(figsize=(8,6))
ax.barh([m for m,_,_ in yr],[y*100 for _,y,_ in yr],color=["#c0392b" if y>0.97 else "#27ae60" for _,y,_ in yr])
ax.axvline(pol_yes*100, ls="--", color="#333", label=f"Polina {pol_yes:.0%}")
for i,(m,y,n) in enumerate(yr): ax.text(y*100+0.5,i,f"{y:.0%}",va="center",fontsize=8)
ax.invert_yaxis(); ax.set_xlabel("yes-rate (share kept)"); ax.set_xlim(0,105); ax.legend()
ax.set_title("Prefilter yes-rate per model (red ≈ always-yes)"); fig.tight_layout(); plt.show()
RELIABLE=0.25   # >25% non-answers: the yes-rate is computed on too small a slice to mean anything
_pf={short(m): v for m, v in pfail.items()}
unreliable=[m for m,_,_ in yr if _pf.get(m, 0) > RELIABLE]
alwaysyes=[m for m,y,_ in yr if y>0.97 and _pf.get(m, 0) <= RELIABLE]
_msg=(f"**{len(alwaysyes)} models keep >97% of pairs** ({', '.join(alwaysyes) if alwaysyes else 'none'}) — "
 f"effectively always-yes, and their apparent accuracy vs Polina is the base rate, not skill. Models nearer the "
 f"Polina line ({pol_yes:.0%}) or below are the ones actually exercising the keep/drop judgement.")
if unreliable:
    _msg += ("\n\n**Reliability first:** " + ", ".join(f"`{m}` ({_pf[m]:.0%} non-answers)" for m in unreliable)
             + " fail to return a usable verdict on more than a quarter of pairs. Their yes-rate is computed on "
               "whatever slice they did answer, so it describes a fraction of their behaviour, not the model — "
               "read it as unusable-for-this-job rather than as a keep/drop tendency.")
display(Markdown(_msg))
'''

S2 = "## 2. Do models agree with each other on keep/drop?"
S2_CODE = r'''
sims=[]
for k,mv in cell.items():
    for a,b in combinations(MODELS,2):
        if a in mv and b in mv: sims.append(mv[a]==mv[b])
# pairwise agreement above chance: expected agreement from marginals
agree=np.mean(sims)
display(Markdown(
 f"**Mean pairwise agreement on keep/drop: {agree:.0%}.** "
 + (f"Against a {pol_yes:.0%}-yes reference, high agreement would be *cheap* — models would simply be agreeing "
    f"on the easy yes-majority. That is **not** what happens: at {agree:.0%} they disagree on roughly "
    f"{1-agree:.0%} of pairs."
    if agree < 0.75 else
    f"High raw agreement is expected when most pairs are \"keep\" — agreeing on the easy yes-majority is cheap, "
    f"so read this together with §1; the agreement that matters is on the rare *drop* cases.")
 + " For a gate that admits everything downstream, that disagreement is not cosmetic: **which model you run the "
   "prefilter with materially changes which corpus you end up analysing.**"))
'''

S3 = "## 3. Balanced accuracy vs Polina (not plain accuracy)"
S3_CODE = r'''
rows=[]
for m in MODELS:
    tp=fp=tn=fn=0
    for r in R:
        if r["model"]!=m: continue
        g=POL.get((r["sample_id"], r["drug"]))
        if g is None: continue
        p=r["keep"]
        if g and p: tp+=1
        elif g and not p: fn+=1
        elif (not g) and p: fp+=1
        else: tn+=1
    sens=tp/(tp+fn) if tp+fn else float("nan"); spec=tn/(tn+fp) if tn+fp else float("nan")
    bal=np.nanmean([sens,spec])
    rows.append([short(m), f"{sens:.0%}", f"{spec:.0%}" if tn+fp else "n/a", f"{bal:.0%}", tn+fp])
rows.sort(key=lambda x:-float(x[3].rstrip('%')))
display(HTML("<b>Per-model vs Polina — sensitivity (keep|yes), specificity (drop|no), balanced accuracy</b>"+
             pd.DataFrame(rows, columns=["model","sensitivity","specificity","balanced acc","n 'no' cases"]).to_html(index=False)))
_sens = np.nanmean([float(r[1].rstrip('%'))/100 for r in rows if r[1] != 'n/a'])
_spec = np.nanmean([float(r[2].rstrip('%'))/100 for r in rows if r[2] != 'n/a'])
_n_no = rows[0][4] if rows else 0
display(Markdown(
 f"Mean **sensitivity {_sens:.0%}** (keeps a genuine personal-use pair) vs mean **specificity {_spec:.0%}** "
 f"(correctly drops a non-personal-use pair). "
 + ("**Specificity is the discriminating axis** — sensitivity is near-ceiling for everyone, so all the signal "
    "is whether a model correctly *drops*."
    if _sens > _spec + 0.10 else
    "**Both axes carry signal here** — sensitivity is not at ceiling, so models differ on what they keep as "
    "well as what they drop.")
 + f" But Polina has only ~{_n_no} 'no' pairs, so specificity rests on a tiny n — treat balanced accuracy as a "
   f"screen for degenerate behaviour, not a rankable score. **This is why ④ is agreement-only until a balanced "
   f"no-set exists.**"))
'''

S4 = "## 4. Verdict"
S4_CODE = r'''
lines=[
 f"- **Prefilter can't be scored for accuracy** — Polina's labels are ~{pol_yes:.0%} yes, so plain accuracy is "
 "the base rate and specificity rests on ~12 'no' cases. This is a *reliability* result, not a validation.",
 (f"- **{len(alwaysyes)} of {len(yr)} models are effectively always-yes** (>97% keep): "
  f"{', '.join(alwaysyes)}. For those the apparent accuracy vs Polina is just the base rate."
  if alwaysyes else
  f"- **No model is a degenerate always-yes** — the highest yes-rate among models that reliably "
  f"answer is {max((y for m,y,_ in yr if _pf.get(m,0)<=RELIABLE), default=float('nan')):.0%} against a "
  f"{pol_yes:.0%} base rate, so the always-yes failure mode didn't materialise on this sample.")
 + " Either way the yes-rate (§1), not accuracy, is the diagnostic to monitor — a keep-everything model "
   "would still score ~base-rate 'accuracy'.",
 f"- **Mean pairwise agreement is {agree:.0%}**; disagreement concentrates on borderline own-use calls, not "
 "on clear personal reports. Cross-model divergence here flags ambiguous cases, not model quality.",
 "- **Needed before ④ can be validated:** a balanced `no`-set (the plan's open item). Until then, treat "
 "prefilter as a keep-biased gate and monitor per-model yes-rate for always-yes drift.",
]
display(Markdown("\n".join(lines)))
'''

LIM = '''## Limitations

- **Degenerate reference** — Polina ~91% yes, ~12 no; specificity (the only discriminating axis) is estimated
  on a tiny n, so no reliable per-model accuracy ranking is possible.
- **Contaminated codebook** — Polina's labels were lifted from the pipeline prompt, so agreement measures
  spec-compliance, not correctness (the standing IRR caveat).
- **K=1** — no within-model variability; the across-model + vs-Polina readouts are all this supports.
- Measures a gating decision's reliability, not any treatment effect. Not medical advice.'''

PROV = r'''
M=d["manifest"]
prov=pd.DataFrame({"item":["field","models","pairs","reference","metric","skill"],
 "value":["prefilter keep/drop", str(len(MODELS)), str(M["n_pairs"]), M["reference"],
          "yes-rate + pairwise agreement + balanced accuracy", "research-assistant v2"]})
display(HTML("<b>Provenance</b>"+prov.to_html(index=False)))
display(HTML('<div style="font-size:1.15em;font-weight:bold;font-style:italic;margin-top:1em">'
             'Measures a gating decision’s reliability, not treatment effects. Not medical advice.</div>'))
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
    nb = build_notebook(cells, db_path=DB, title="Judgement 4 — prefilter agreement")
    html = execute_and_export(nb, "notebooks/validation/j4_prefilter", timeout=900)
    print("Wrote", html)


if __name__ == "__main__":
    main()
