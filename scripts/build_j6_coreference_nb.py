"""
build_j6_coreference_nb.py — Judgement ⑥ (coreference) via context ablation.

Each (comment, drug) was classified WITH its parent context and WITHOUT it. If a model uses coreference,
removing the context should change its judgement much more on CONTEXT-NECESSARY items (drug only in the
parent) than on CONTROL items (drug already in the comment — the noise floor). This notebook measures that
gap per model. Code-free HTML.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notebooks"))
from build_notebook import RELIABILITY_CODE, build_notebook, execute_and_export

RUNS = (ROOT / "data" / "validation" / "j6_coreference_runs.json").as_posix()
DB = (ROOT / "patientpunk.db").as_posix()

FRAME = (
"# Judgement ⑥ — coreference: does the model use upstream context?\n\n"
"The weakest judgement to validate — the frozen run had zero coreference items (a parent-id defect), so we "
"probe it directly by **context ablation**: classify each (comment, drug) with its parent context and "
"without. A model that resolves coreference should change its answer when the context is removed on "
"**context-necessary** items (the drug is *only* in the parent), and *not* on **control** items (the drug is "
"already in the comment, so the context is redundant — the noise floor). The gap between the two is the "
"coreference signal.")

LOAD = r'''
import json
import numpy as np
from collections import defaultdict
d=json.load(open(r"__RUNS__")); short=lambda m:m.split("/")[-1]
FAIL=fail_rates(d["records"], lambda r: short(r["model"]), lambda r: r["parse_failed"])
R=[r for r in d["records"] if not r["parse_failed"] and short(r["model"]) in scored(FAIL)]
# pair up with/without per (model, sample, drug)
byk=defaultdict(dict)
for r in R: byk[(r["model"], r["sample_id"], r["drug"], r["drug_in_comment"])][r["variant"]]=(r["sentiment"], r["signal"])
def changed(v): return v.get("with") is not None and v.get("without") is not None and v["with"]!=v["without"]
MODELS=sorted(set(r["model"] for r in R))
display(Markdown(reliability_md(FAIL)))
display(Markdown(f"*(loaded — {len(R)} usable classifications, {len(MODELS)} scored models; "
 f"{d['manifest']['n_context_necessary']} context-necessary pairs)*"))
'''.replace("__RUNS__", RUNS)

S1 = ("## 1. Does removing context change the answer — necessary vs control?\n\n"
      "Per model: how often the sentiment/signal flips when the parent context is ablated, on "
      "context-necessary items vs control items.")
S1_CODE = r'''
rows=[]
for m in MODELS:
    nec=[changed(v) for (mm,s,dr,dic),v in byk.items() if mm==m and dic==False and "with" in v and "without" in v]
    ctl=[changed(v) for (mm,s,dr,dic),v in byk.items() if mm==m and dic==True  and "with" in v and "without" in v]
    if nec: rows.append((short(m), np.mean(nec), (np.mean(ctl) if ctl else 0), len(nec), len(ctl)))
rows.sort(key=lambda x:-(x[1]-x[2]))
lo, hi = min(r[3] for r in rows), max(r[3] for r in rows)
N_NEC = f"{lo}–{hi} context-necessary pairs per model" if lo != hi else f"{hi} context-necessary pairs"
import numpy as np
y=np.arange(len(rows)); h=0.38
fig,ax=plt.subplots(figsize=(9,7))
ax.barh(y+h/2,[r[1]*100 for r in rows],h,label="context-necessary (drug only in parent)",color="#2a78d6")
ax.barh(y-h/2,[r[2]*100 for r in rows],h,label="control (drug in comment — noise floor)",color="#c0392b")
ax.set_yticks(y); ax.set_yticklabels([f"{r[0]} (n={r[3]}/{r[4]})" for r in rows],fontsize=8); ax.invert_yaxis()
ax.set_xlabel("change-rate when parent context is removed (%) · n = necessary/control pairs"); ax.legend(fontsize=8)
ax.set_title("Coreference probe — answer changes on context-necessary vs control items"); fig.tight_layout(); plt.show()
nec_all=np.mean([r[1] for r in rows]); ctl_all=np.mean([r[2] for r in rows])
display(Markdown(f"**Context-necessary items change {nec_all:.0%} of the time when the parent is removed, vs "
 f"{ctl_all:.0%} for control items** — a **{nec_all-ctl_all:+.0%}** gap in the expected direction, but a *weak* "
 f"one. Two reasons to read it cautiously: the control change-rate is **{ctl_all:.0%}** — removing *redundant* "
 f"context shouldn't move the answer at all, so the models are noticeably unstable to prompt edits, and the "
 f"coreference signal sits only ~{(nec_all-ctl_all)*100:.0f} points above that noise floor. And the "
 f"context-necessary group is tiny (**{N_NEC}**), so the gap is suggestive, not conclusive. **Best read: a hint that models use the reply "
 f"chain, not proof — ⑥ stays the least-validated judgement.**"))
'''

S2 = "## 2. Which models depend on context most"
S2_CODE = r'''
display(Markdown(
 "Models with a **large necessary-minus-control gap** resolve coreference strongly (they lean on the parent "
 "when the drug isn't local). A **small gap** means either the model ignores upstream context (a coreference "
 "weakness) or it guesses locally regardless. A model whose *control* change-rate is high is unstable — its "
 "answer wobbles even when context is redundant, which is noise, not coreference. Read the two bars together: "
 "the healthy pattern is a tall blue bar and a short red one."))
tb=[[r[0], r[3], f"{r[1]:.0%}", r[4], f"{r[2]:.0%}", f"{(r[1]-r[2]):+.0%}"] for r in rows]
display(HTML(pd.DataFrame(tb, columns=["model","n necessary","necessary Δ-rate","n control","control Δ-rate",
                                       "gap (coreference signal)"]).to_html(index=False)))
'''

S3 = "## 3. Verdict"
S3_CODE = r'''
nec_all=np.mean([r[1] for r in rows]); ctl_all=np.mean([r[2] for r in rows])
lines=[
 f"- **Weak-positive, not a clean pass.** The gap is in the right direction (**{nec_all:.0%}** necessary vs "
 f"**{ctl_all:.0%}** control, **{nec_all-ctl_all:+.0%}**), so models *lean* on the reply chain — but the effect "
 f"is small and rides on only {N_NEC}. ⑥ remains the least-validated of the eleven.",
 f"- **The {ctl_all:.0%} control change-rate is a red flag of its own** — removing redundant context shouldn't "
 "change the answer, so the classifier is fairly unstable to prompt edits (temperature is pinned to 0, so this "
 "is prompt-sensitivity, not sampling). That instability, not coreference, may be the bigger reliability story.",
 "- **We could only ever show *use*, not *correctness*** — ablation shows the model depends on context, never "
 "that it resolves it right. With no coreference gold and a defect-zeroed frozen run, this probe on real items "
 "is the honest ceiling for ⑥.",
 "- **Recommendation:** widen the context-necessary set (construct thread-structure items) and drive down the "
 "control change-rate (prompt-stability check) before treating coreference as validated.",
]
display(Markdown("\n".join(lines)))
'''

LIM = '''## Limitations

- **Change ≠ correctness** — ablation shows the model *depends on* context, not that its resolution is right.
  With no coreference gold, "uses context" is the strongest claim available (the plan's stated ceiling for ⑥).
- **Context-necessary is inferred** from whether the drug string appears in the comment text — a surface
  heuristic; a drug referred to only by pronoun/synonym in the comment could be mislabelled.
- **Depends on the parent_context field** in the IRR frame (280/300 pairs) at depth 2; deeper chains untested.
- Measures whether a resolution step fires, not any treatment effect. Not medical advice.'''

PROV = r'''
M=d["manifest"]
prov=pd.DataFrame({"item":["method","models","pairs","context-necessary","metric","skill"],
 "value":[M["method"], str(len(MODELS)), str(M["n_pairs"]), str(M["n_context_necessary"]),
          "change-rate under context ablation (necessary vs control)", "research-assistant v2"]})
display(HTML("<b>Provenance</b>"+prov.to_html(index=False)))
display(HTML('<div style="font-size:1.15em;font-weight:bold;font-style:italic;margin-top:1em">'
             'Measures whether a resolution step fires, not treatment effects. Not medical advice.</div>'))
'''


def main():
    cells = [
        ("md", FRAME), ("code", RELIABILITY_CODE), ("code", LOAD),
        ("md", S1), ("code", S1_CODE),
        ("md", S2), ("code", S2_CODE),
        ("md", S3), ("code", S3_CODE),
        ("md", LIM), ("code", PROV),
    ]
    nb = build_notebook(cells, db_path=DB, title="Judgement 6 — coreference (context ablation)")
    html = execute_and_export(nb, "notebooks/validation/j6_coreference", timeout=900)
    print("Wrote", html)


if __name__ == "__main__":
    main()
