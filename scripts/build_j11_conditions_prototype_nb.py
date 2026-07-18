"""
build_j11_conditions_prototype_nb.py — did the Tier-2 `conditions` fix work?

Honest before->after on the highest-volume Tier-2 field, with the measurement confound removed. The
BEFORE and AFTER are BOTH judged by the same Opus judge in the SAME single-field context (the original
re-score judged conditions alongside other fields, which is stricter/looser and would confound the
delta). Reports the two numbers the taxonomy predicted: model-vs-gold genuine-error and producer
co-failure. Includes the negative-result lesson (hand-canonicalization mangles messy values, so surface
synonymy is left to the judge / the production ontology). Code-free HTML.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notebooks"))
from build_notebook import build_notebook, execute_and_export

DV = ROOT / "data" / "validation"
FIX = (DV / "j11_conditions_fix.json").as_posix()
DB = (ROOT / "patientpunk.db").as_posix()

FRAME = (
"# Tier-2 prototype — does the `conditions` fix work?\n\n"
"The [taxonomy notebook](j11_value_error_taxonomy.html) predicted that the Tier-2 fix would cut both the "
"genuine-error and the producer co-failure on `conditions`, because both come from the same shared mistake: "
"treating symptoms (PEM, fatigue, brain fog) as diagnosed conditions. This notebook tests that — and the "
"honest answer is **a qualified yes, with a lesson attached.**\n\n"
"**What the prototype actually applies.** Only the **boundary rule**: drop symptom-type terms, keep "
"condition/diagnosis terms **verbatim**. It does *not* hand-canonicalize surface forms — a first attempt to "
"do so mangled messy real values (`\"fever (now resolved)\"` → a fake condition `\"now resolved\"`), so surface "
"synonymy is left to the Opus judge, which stands in for the production ontology (UMLS/RxNorm). That is the "
"honest scope: this tests the *rule*, with the *tool* approximated by the judge.\n\n"
"**The method, and the confound we removed.** BEFORE and AFTER are **both** judged by Opus in the **same "
"single-field context**. The original re-score judged `conditions` *alongside* every other field, which turns "
"out to be materially more lenient — so comparing the fixed value (judged alone) against that original number "
"would credit the fix with a context effect it did not earn. Matching the context isolates the fix.")

LOAD = r'''
import json, re, difflib
from collections import defaultdict, Counter
D = json.load(open(r"__FIX__", encoding="utf-8")); R = D["records"]; N = len(R)
def short(m): return m.split("/")[-1]
def norm(x):
    if isinstance(x,list): x=" ".join(map(str,x))
    return re.sub(r"[^a-z0-9 ]"," ",str(x).lower()).strip()
def sim(a,b):
    ta,tb=set(norm(a).split()),set(norm(b).split())
    j=len(ta&tb)/len(ta|tb) if (ta|tb) else 1.0
    return max(j, difflib.SequenceMatcher(None,norm(a),norm(b)).ratio())

# three different-rates: original multi-field, raw-isolated (matched baseline), fixed-isolated
D_MULTI = sum(r["before_multi"]=="different" for r in R)/N
D_BEF   = sum(r["before"]=="different" for r in R)/N
D_AFT   = sum(r["after"]=="different" for r in R)/N
E_BEF   = sum(r["before"]=="equivalent" for r in R)/N
E_AFT   = sum(r["after"]=="equivalent" for r in R)/N
REDUC   = (D_BEF-D_AFT)/D_BEF if D_BEF else float("nan")
trans   = Counter((r["before"], r["after"]) for r in R)
toward  = sum(v for (b,a),v in trans.items() if (b=="different" and a!="different") or (b=="model_subset" and a=="equivalent"))
against = sum(v for (b,a),v in trans.items() if (b=="equivalent" and a=="different") or (b=="model_subset" and a=="different"))
residual= trans[("different","different")]

# producer co-failure (DeepSeek-v4-pro vs every other producer, pooled) before -> after
bym=defaultdict(dict)
for r in R: bym[r["model"]][r["sample_id"]]=r
A="deepseek/deepseek-v4-pro"; ba=bc=aa=ac=0
for B in bym:
    if B==A: continue
    for s in set(bym[A])&set(bym[B]):
        ra,rb=bym[A][s],bym[B][s]
        if sim(ra["raw_model"],rb["raw_model"])>=0.5:
            ba+=1
            if ra["before"]=="different": bc+=1
        if sim(ra["fixed_model"],rb["fixed_model"])>=0.5:
            aa+=1
            if ra["after"]=="different": ac+=1
COF_B=bc/ba if ba else float("nan"); COF_A=ac/aa if aa else float("nan")
COF_RED=(COF_B-COF_A)/COF_B if COF_B else float("nan")
display(Markdown("*(loaded — matched-context before/after on "+str(N)+" conditions values)*"))
'''.replace("__FIX__", FIX)

ABS = r'''
verd = "a qualified yes" if (REDUC>0.02 or COF_RED>0.05) else "no — the rule alone does not help"
display(Markdown(f"""
**Result — {verd}.** With the judging context matched, the boundary rule cuts `conditions` genuine-error
(Opus "different") from **{D_BEF:.0%} → {D_AFT:.0%}** (a **{REDUC:.0%} relative reduction**) and cuts producer
co-failure — the number the "agree → accept" gate actually depends on — from **{COF_B:.0%} → {COF_A:.0%}** (a
**{COF_RED:.0%} reduction**). The transition is net-positive: **{toward} values moved toward correct vs
{against} against.** *But it is modest, not a silver bullet:* **{residual} of the errors are
`different → different`** — genuine disagreement about *content* (a different diagnosis, a real completeness
gap) that stripping symptoms cannot touch. **Two things this pins down:** (1) most `conditions` error is
*genuine content*, not symptom-inclusion — so `conditions` leans more Tier-3 than the taxonomy assumed, and
the rule handles only its slice; (2) a measurement lesson — judging `conditions` in isolation is stricter
({D_MULTI:.0%} original multi-field → **{D_BEF:.0%}** isolated), and hand-canonicalization *hurt* (it mangled
annotation-laden values), so the real surface-normalization must come from the ontology tool, not a lexicon.
"""))
'''

S1 = ("## 1. What the fix does — and the negative result baked into it\n\n"
      "The boundary rule keeps diagnosis/syndrome terms and drops symptom terms, **verbatim** — no hand "
      "canonicalization, because that failed. A few real cases the rule catches:")
S1_CODE = r'''
ex=[r for r in R if r["before"]=="different" and r["after"]!="different"][:5]
rows=[[short(r["model"]), " | ".join(r["raw_model"])[:60], " | ".join(r["fixed_model"])[:38], " | ".join(r["fixed_gold"])[:38]] for r in ex]
display(HTML(pd.DataFrame(rows, columns=["producer","raw conditions","-> fixed (verbatim)","fixed gold"]).to_html(index=False)))
display(Markdown(
 "**The lesson embedded here:** a first attempt *also* canonicalized surface forms with a hand-lexicon — and "
 "it made things **worse**, because real values carry annotations (`\"fever (now resolved)\"`, `\"(suggested by "
 "commenter)\"`) that a split-and-map rule promotes to spurious conditions. So the prototype strips symptoms "
 "and leaves synonymy to the judge. **In production the surface normalization is the job of the ontology tool "
 "(UMLS concept IDs), not a rule** — the 'tool' half of 'tool + rule' is not optional, and this is the evidence."))
'''

S2 = ("## 2. The headline — with the context confound removed\n\n"
      "Same Opus judge, same 462 values. The key is that the **before** here is the *raw* value judged in the "
      "**same single-field context** as the fixed value — not the original multi-field number, which is more "
      "lenient and would have flattered the fix.")
S2_CODE = r'''
fig, ax = plt.subplots(1,2, figsize=(11,3.3))
bars=[("original\n(multi-field)",D_MULTI,"#95a5a6"),("raw\n(isolated = baseline)",D_BEF,"#c0392b"),("fixed\n(isolated)",D_AFT,"#27ae60")]
ax[0].bar([b[0] for b in bars],[b[1] for b in bars],color=[b[2] for b in bars])
for i,b in enumerate(bars): ax[0].text(i,b[1]+0.006,f"{b[1]:.0%}",ha="center",fontweight="bold")
ax[0].set_ylim(0,max(D_MULTI,D_BEF,D_AFT)*1.3); ax[0].set_title("genuine-error (Opus 'different')"); ax[0].tick_params(axis="x",labelsize=8)
cats=["equivalent","model_subset","different"]; mat=np.zeros((3,3))
for (b,a),n in trans.items():
    if b in cats and a in cats: mat[cats.index(b)][cats.index(a)]=n
ax[1].imshow(mat,cmap="Blues")
for i in range(3):
    for j in range(3):
        if mat[i,j]: ax[1].text(j,i,int(mat[i,j]),ha="center",va="center",color="white" if mat[i,j]>mat.max()/2 else "#333")
ax[1].set_xticks(range(3));ax[1].set_xticklabels([c[:5] for c in cats]);ax[1].set_yticks(range(3));ax[1].set_yticklabels(cats)
ax[1].set_xlabel("after fix");ax[1].set_ylabel("before (isolated)");ax[1].set_title("verdict transition (count)")
fig.tight_layout(); plt.show()
display(Markdown(
 f"**What this shows:** the honest baseline is **{D_BEF:.0%}** (isolated), not the {D_MULTI:.0%} we had been "
 f"quoting — judging `conditions` alone is stricter. Against that matched baseline the fix lands at **{D_AFT:.0%}** "
 f"(**{REDUC:.0%}** relative). In the grid, mass below the diagonal is the fix working ({toward} toward correct); "
 f"the {against} above it (mostly `equivalent → different`) is surface-variant exposure — real conditions the "
 f"verbatim rule left un-unified, which the ontology tool would catch."))
'''

S3 = ("## 3. The residual is the real story — conditions error is mostly *content*\n\n"
      "A good fix isolates the judge-worthy cases. Split the originally-different values:")
S3_CODE = r'''
resid=[r for r in R if r["before"]=="different" and r["after"]=="different"][:5]
rows=[[short(r["model"]), " | ".join(r["fixed_model"])[:46], " | ".join(r["fixed_gold"])[:46]] for r in resid]
display(HTML("<b>Still different after the fix — genuine content disagreement (a judge/panel problem)</b>"+
             pd.DataFrame(rows, columns=["producer","fixed model conditions","fixed gold conditions"]).to_html(index=False)))
n_diff_before = sum(1 for r in R if r["before"]=="different")
display(Markdown(
 f"**What this shows:** of the {n_diff_before} originally-different values, only **{n_diff_before-residual} "
 f"were the symptom-inclusion / subset noise the rule targets** — the other **{residual} are genuine content "
 f"disagreement** (a different diagnosis, an extra condition truly in dispute, a real completeness gap). That "
 f"is the load-bearing finding: **`conditions` error is dominated by content, not boundary** — so the Tier-2 "
 f"rule helps a slice, and the bulk still needs the ontology tool (for surface variants) plus a judge (for the "
 f"genuine residual). `conditions` sits closer to Tier 3 than the taxonomy first assumed."))
'''

S4 = ("## 4. Producer co-failure — the architecture-relevant win\n\n"
      "The number that actually matters for the two-producer 'agree → accept' gate is **co-failure**: when two "
      "producers agree, how often are they both wrong? On raw `conditions` they shared the symptom-inclusion "
      "blind spot; after the rule, agreement is on symptom-free lists.")
S4_CODE = r'''
fig, ax = plt.subplots(figsize=(6.3,2.7))
ax.bar(["before fix","after fix"],[COF_B,COF_A],color=["#c0392b","#27ae60"])
for i,v in enumerate([COF_B,COF_A]): ax.text(i,v+0.004,f"{v:.0%}",ha="center",fontweight="bold",fontsize=12)
ax.set_ylabel("co-failure (wrong | producers agree)"); ax.set_ylim(0,max(COF_B,COF_A)*1.35)
ax.set_title("DeepSeek-v4-pro vs all producers — conditions co-failure"); fig.tight_layout(); plt.show()
display(Markdown(
 f"**What this shows:** co-failure drops **{COF_B:.0%} → {COF_A:.0%}** (**{COF_RED:.0%}** relative) — a bigger "
 f"effect than on raw accuracy, and the one that counts for the architecture: two cheap producers agreeing on a "
 f"symptom-free `conditions` list is now a more trustworthy signal, so more of Tier-2 can exit at the "
 f"producer-consensus gate instead of going to judges. Note the fix helps *agreement quality* more than *absolute "
 f"accuracy* — exactly what you want for a consensus gate. *(Pooled DeepSeek-vs-all, conditions-only overlap; "
 f"directional.)*"))
'''

S5 = "## 5. Verdict — does the Tier-2 approach hold on `conditions`?"
S5_CODE = r'''
lines=[
 f"- **Qualified yes.** With the context confound removed, the boundary rule cuts genuine-error "
 f"**{D_BEF:.0%} → {D_AFT:.0%}** ({REDUC:.0%} relative) and producer co-failure **{COF_B:.0%} → {COF_A:.0%}** "
 f"({COF_RED:.0%} relative), net-positive ({toward} toward correct vs {against} against) — from a deterministic "
 f"rule, no per-post LLM.",
 f"- **But `conditions` is mostly a *content* problem, not a boundary one.** {residual} of the errors are genuine "
 f"disagreement the rule can't touch — so `conditions` behaves closer to Tier 3 than assumed. The rule is worth "
 f"applying (it helps the consensus gate), but it is not the whole fix for this field.",
 f"- **The 'tool' half is not optional.** Hand-canonicalization *hurt* (annotation mangling); the surface-variant "
 f"residual (`equivalent → different` cases) is exactly what a real ontology (UMLS concept IDs) would unify and a "
 f"lexicon can't. Building that is the next step for `conditions`.",
 f"- **A measurement lesson worth keeping:** judging a field in isolation is stricter than in-context "
 f"({D_MULTI:.0%} → {D_BEF:.0%} here) — before/after comparisons must match the judging context or the delta is "
 f"partly an artifact. This bit the first run and is why the honest number is {REDUC:.0%}, not the {(D_MULTI-D_AFT)/D_MULTI:.0%} the naive comparison implied.",
 f"- **Generalization:** the rule + ontology-tool pattern should transfer to `medications`/`alternative_treatments` "
 f"(drug-vs-supplement boundary, RxNorm the tool); the ordinal fields get the designed-enum fix instead. Each needs "
 f"its own tool built and tested — this field shows the rule alone is necessary but not sufficient.",
]
display(Markdown("\n".join(lines)))
'''

LIM = '''## Limitations

- **Boundary rule only; a domain lexicon, not UMLS.** The symptoms-vs-conditions test is a transparent
  long-COVID lexicon (`conditions_fix.py`), defaulting to *keep* (under-strips rather than over-strips). Surface
  synonymy is deliberately left to the Opus judge — the production ontology tool would do better and is exactly
  what the un-unified residual needs.
- **Hand-canonicalization was tried and dropped** because it injected spurious conditions from parenthetical
  annotations — a real negative result, reported (§1), not hidden.
- **The fix is applied to the gold too** (a field-level transform applied uniformly) — correct, but it means the
  metric measures making model and gold *comparable*, the right question for a clustering covariate.
- **Co-failure n is modest** (conditions-only producer overlap) and agreement is a string proxy — direction solid,
  exact rate directional.
- **"Correct" is vs Opus-gold, not ground truth** — the genuine-content residual is where a judge panel, not
  this rule, earns its keep. Describes a measurement step, not a treatment effect.'''

PROV = r'''
M=D["manifest"]
prov=pd.DataFrame({"item":["field","judge","fix","values","error (matched iso)","co-failure","skill"],
 "value":[M["field"], M["judge_model"], "boundary rule only (symptoms stripped; synonymy left to judge)",
          f"{N}", f"{D_BEF:.0%} -> {D_AFT:.0%}", f"{COF_B:.0%} -> {COF_A:.0%}", "research-assistant v2"]})
display(HTML("<b>Provenance</b>"+prov.to_html(index=False)))
display(HTML('<div style="font-size:1.15em;font-weight:bold;font-style:italic;margin-top:1em">'
             'Describes the correctness of a measurement step, not population-level treatment effects. '
             'Not medical advice.</div>'))
'''


def main():
    cells = [
        ("md", FRAME), ("code", LOAD), ("code", ABS),
        ("md", S1), ("code", S1_CODE),
        ("md", S2), ("code", S2_CODE),
        ("md", S3), ("code", S3_CODE),
        ("md", S4), ("code", S4_CODE),
        ("md", S5), ("code", S5_CODE),
        ("md", LIM), ("code", PROV),
    ]
    nb = build_notebook(cells, db_path=DB, title="Tier-2 prototype — conditions fix")
    html = execute_and_export(nb, "notebooks/validation/j11_conditions_fix_prototype", timeout=900)
    print("Wrote", html)


if __name__ == "__main__":
    main()
