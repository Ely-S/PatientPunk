"""
build_j9_sideeffects_nb.py — Judgement ⑨ (side-effects) roster agreement.

Side-effects are a SET per (post, drug), extracted in the classify call. There's no external gold, so
validity is agreement-only: how much do models agree on the AE set for the same (post, drug)? This is
load-bearing because ⑨ feeds the FDA tolerability work — and it carries two named threats: the LIST-FANOUT
rule (a symptom is pinned to every drug in a stack) and DR4 (cross-community AE comparison inherits post
verbosity). Metric = mean pairwise Jaccard on the AE sets. Code-free HTML.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notebooks"))
from build_notebook import build_notebook, execute_and_export

RUNS = (ROOT / "data" / "validation" / "j9_sideeffects_runs.json").as_posix()
DB = (ROOT / "patientpunk.db").as_posix()

FRAME = (
"# Judgement ⑨ — side-effect extraction: do models agree on the AE set?\n\n"
"For each (post, drug) the classifier extracts a **set of side-effects**. This is a fully-wired field that "
"already feeds the FDA tolerability analysis, so its reliability matters — but it has no external gold, so "
"the only honest question is *agreement*: given the same post and drug, do models extract the same adverse "
"events? Measured across the roster on the IRR labelled pairs, metric = mean pairwise Jaccard on the AE sets.")

LOAD = r'''
import json, re
import numpy as np
from collections import defaultdict, Counter
from itertools import combinations
d=json.load(open(r"__RUNS__")); R=[r for r in d["results"] if not r["parse_failed"]]
MODELS=sorted(set(r["model"] for r in R)); short=lambda m:m.split("/")[-1]
# per (sample, drug): {model: set(side_effects)}
cell=defaultdict(dict)
for r in R:
    se=set(str(x).lower().strip() for x in (r.get("side_effects") or []) if str(x).strip())
    cell[(r["sample_id"], r["drug"])][r["model"]]=se
def jac(a,b): return len(a&b)/len(a|b) if (a|b) else 1.0
# pairwise model agreement on AE sets (only where BOTH models have a value for that post,drug)
pair=defaultdict(list)
for k,mv in cell.items():
    for a,b in combinations(MODELS,2):
        if a in mv and b in mv: pair[(a,b)].append(jac(mv[a],mv[b]))
allsims=[s for v in pair.values() for s in v]
# how often is the AE set EMPTY? (models often report no AEs)
n_cells=sum(len(mv) for mv in cell.values()); n_empty=sum(1 for mv in cell.values() for s in mv.values() if not s)
display(Markdown(f"*(loaded — {len(R)} classifications, {len(MODELS)} models; overall mean pairwise AE-set "
 f"agreement {np.mean(allsims):.0%}; {n_empty/n_cells:.0%} of extractions report no side-effects)*"))
'''.replace("__RUNS__", RUNS)

S1 = ("## 1. How much do models agree on the side-effect set?\n\n"
      "Mean pairwise Jaccard on the AE sets, per model against the rest.")
S1_CODE = r'''
per=[]
for m in MODELS:
    sims=[s for (a,b),v in pair.items() if m in (a,b) for s in v]
    per.append((short(m), np.mean(sims) if sims else np.nan))
per.sort(key=lambda x:-x[1])
fig,ax=plt.subplots(figsize=(8,6))
ax.barh([p[0] for p in per],[p[1]*100 for p in per],color="#2a78d6")
for i,p in enumerate(per): ax.text(p[1]*100+0.5,i,f"{p[1]:.0%}",va="center",fontsize=8)
ax.invert_yaxis(); ax.set_xlabel("mean AE-set agreement with other models (Jaccard)"); ax.set_xlim(0,max(p[1] for p in per)*115)
ax.set_title("Side-effect set agreement per model"); fig.tight_layout(); plt.show()
display(Markdown(f"**Agreement is low ({np.mean(allsims):.0%} overall)** — but AE sets are small and sparse, "
 f"so Jaccard is punishing (one model lists `insomnia`, another `sleep problems`, a third nothing → near-zero "
 f"overlap). Two structural reasons agreement is genuinely hard here: (a) side-effects are only mentioned in "
 f"passing in most posts, so presence is noisy; (b) free-text AE strings aren't normalized. **The takeaway "
 f"isn't a clean number — it's that raw side-effect *sets* are the least reliable field, and any AE analysis "
 f"needs string normalization + a presence threshold before trusting cross-model or cross-community counts.**"))
'''

S2 = "## 2. What gets reported — and the sparsity problem"
S2_CODE = r'''
allse=Counter(x for mv in cell.values() for s in mv.values() for x in s)
top=allse.most_common(15)
tb=pd.DataFrame(top, columns=["side-effect (verbatim)","times extracted"])
display(HTML("<b>Most-extracted side-effects (raw strings, unnormalised)</b>"+tb.to_html(index=False)))
display(Markdown(f"**{n_empty/n_cells:.0%} of extractions report NO side-effect at all** — most posts don't "
 f"discuss AEs for the drug in question, so the field is mostly empty and the non-empty entries are a thin, "
 f"noisy signal. The raw strings above also show the normalisation gap (synonyms/spellings uncollapsed), which "
 f"is exactly what drags the Jaccard agreement down and what an ontology pass (MedDRA/UMLS) would fix."))
'''

S3 = '''## 3. The two threats that matter for the FDA use

Side-effects feed the FDA tolerability work (`FDA_analysis/build_ldn_ae.py`,
`ldn_two_community_tolerability.ipynb`), so two known threats are load-bearing:

- **LIST-FANOUT** (`intervention_config.py:164`) — the prompt pins a reported symptom to *every* drug named in
  a stacked post. So on multi-treatment posts, each drug inherits the whole post's AE list, inflating per-drug
  side-effect counts exactly as the group-attribution rule inflates per-drug *positives* (judgement ⑤). Any
  per-drug AE profile from stacked posts is suspect.
- **DR4 (verbosity confound)** — the FDA work compares AE profiles *across communities* (CLH vs Phoenix). If
  one community writes longer posts, its AE lists look richer and the comparison measures verbosity, not
  tolerability. **Run DR4's flatness check (AE-set size vs post length, per community) before trusting any
  cross-community AE comparison.**

Both mean: the side-effect field is usable for *within-post presence* signals, but per-drug and
cross-community AE *counts* need the fan-out correction and the verbosity check first.'''

S4 = "## 4. Verdict"
S4_CODE = r'''
lines=[
 f"- **Side-effect sets are the least-reliable field** — ~{np.mean(allsims):.0%} mean pairwise agreement, and "
 f"~{n_empty/n_cells:.0%} of extractions are empty. Partly Jaccard punishing sparse sets, partly genuine "
 "presence noise + unnormalised strings.",
 "- **Not a clean pass/fail** — with no gold, this is agreement-only, and the low number is as much a metric "
 "and sparsity artifact as a model failure (same lesson as the variable-coding N×N). A MedDRA/UMLS "
 "normalization pass + a presence threshold would lift the usable signal substantially.",
 "- **Two corrections are mandatory before the FDA AE use:** the LIST-FANOUT fan-out (per-drug counts on "
 "stacked posts) and the DR4 verbosity check (cross-community counts). Neither is optional given how AE "
 "profiles are compared downstream.",
 "- **Recommendation:** treat raw AE sets as a *presence* signal only; normalize to an ontology and apply the "
 "two corrections before any per-drug or cross-community tolerability claim.",
]
display(Markdown("\n".join(lines)))
'''

LIM = '''## Limitations

- **No gold** — agreement-only; models agreeing on an AE could share a prompt bias, and a low number is partly
  the sparse-set Jaccard artifact, not proven unreliability.
- **Jaccard on tiny sets is high-variance** — one differing term swings a pair from 1.0 to 0.0; absolute levels
  understate semantic agreement (`insomnia` vs `sleep problems`).
- **IRR labelled pairs only** (116 post×drug), K=1 — no within-model variability here; the across-model number
  is the primary readout.
- Describes agreement of a measurement step, not real adverse-event rates. Not medical advice.'''

PROV = r'''
M=d["manifest"]
prov=pd.DataFrame({"item":["field","models","pairs","metric","threats","skill"],
 "value":["side_effects (classify_batch)", str(len(MODELS)), str(M.get("n_pairs","?")),
          "mean pairwise Jaccard on AE sets", "LIST-FANOUT + DR4 verbosity", "research-assistant v2"]})
display(HTML("<b>Provenance</b>"+prov.to_html(index=False)))
display(HTML('<div style="font-size:1.15em;font-weight:bold;font-style:italic;margin-top:1em">'
             'Describes agreement of a measurement step, not real adverse-event rates. Not medical advice.</div>'))
'''


def main():
    cells = [
        ("md", FRAME), ("code", LOAD),
        ("md", S1), ("code", S1_CODE),
        ("md", S2), ("code", S2_CODE),
        ("md", S3),
        ("md", S4), ("code", S4_CODE),
        ("md", LIM), ("code", PROV),
    ]
    nb = build_notebook(cells, db_path=DB, title="Judgement 9 — side-effect set agreement")
    html = execute_and_export(nb, "notebooks/validation/j9_sideeffects", timeout=900)
    print("Wrote", html)


if __name__ == "__main__":
    main()
