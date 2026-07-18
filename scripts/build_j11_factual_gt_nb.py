"""
build_j11_factual_gt_nb.py — the frozen factual GT (cross-lab frontier consensus) notebook.

Replaces "closeness to a single Opus gold" with a defensible yardstick: where >=3 of 4 different-
lab frontier models agree, that's gold; where they split, the cell is contested and gets no
accuracy number. Reports GT coverage (how much of the schema even HAS a knowable answer), the
Opus-dissent rate (how often the incumbent single gold was itself the outlier), and each model's
TRUE accuracy against the consensus. Code-free HTML.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notebooks"))
from build_notebook import build_notebook, execute_and_export

DV = (ROOT / "data" / "validation").as_posix()
DB = (ROOT / "patientpunk.db").as_posix()

FRAME = (
"# Judgement ⑪ — a frozen factual gold from cross-lab consensus\n\n"
"Every accuracy number so far has been *closeness to a single Opus gold*. But the golds disagree "
"13–16% with a 5–10pt own-lab bias, and on the hardest cells the models agree with **each other** "
"while Opus is the outlier. So a single-model gold hands you a falsely authoritative accuracy number — "
"especially on the interpretive fields.\n\n"
"This builds the honest replacement. A **panel of four different-lab frontier models** — Opus "
"(Anthropic), Gemini-3.1-Pro (Google), GPT-5.1 (OpenAI), Grok-4.5 (xAI) — codes the 30 posts. Where "
"**≥3 of the 4 agree** (semantically) on a value, or ≥3 leave a field empty, that cell gets a **frozen "
"gold**. Where they split, the cell is **contested** — genuinely underdetermined, so it gets *no* gold "
"rather than a fake accuracy number. Non-panel models are then scored only on the gold cells.")

LOAD = r'''
import json
import numpy as np
DV = r"__DV__"
gt = json.load(open(DV + "/j11_factual_gt.json", encoding="utf-8"))
TIER = ["Tier-1","Tier-2","Tier-3"]
TCOL = {"Tier-1":"#27ae60","Tier-2":"#e67e22","Tier-3":"#c0392b"}
display(Markdown(f"*(loaded — panel = {', '.join(p.split('/')[-1] for p in gt['panel'])}; "
 f"{gt['n_posts']} posts; gold = ≥3 of 4 cross-lab agree)*"))
'''.replace("__DV__", DV)

S1 = ("## 1. How much of the schema even *has* a knowable answer?\n\n"
      "Before scoring anyone, the first question a real gold answers: on how many cells can a cross-lab "
      "panel actually establish a value? A **value-gold** is a populated field ≥3 models agree on; an "
      "**absent-gold** is a field ≥3 agree isn't present; **contested** is everything else — no gold.")
S1_CODE = r'''
cov = gt["coverage"]
kinds=["value","absent","contested"]; col={"value":"#2980b9","absent":"#27ae60","contested":"#c0392b"}
x=np.arange(3)
fig,ax=plt.subplots(figsize=(9.5,5))
bottom=np.zeros(3)
for k in kinds:
    vals=np.array([cov[t][k] for t in TIER])
    ax.bar(x,vals,bottom=bottom,color=col[k],label={"value":"value-gold (≥3 agree on a value)",
        "absent":"absent-gold (≥3 agree: not present)","contested":"contested (no gold)"}[k])
    for i,(v,b) in enumerate(zip(vals,bottom)):
        if v>8: ax.text(i,b+v/2,f"{int(v)}",ha="center",va="center",color="white",fontweight="bold",fontsize=9)
    bottom+=vals
ax.set_xticks(x); ax.set_xticklabels(TIER); ax.set_ylabel("cells (of 30 posts × fields)")
ax.legend(fontsize=8); ax.set_title("GT coverage — where a cross-lab answer exists vs where it's contested")
fig.tight_layout(); plt.show()
rows=[]
for t in TIER:
    c=cov[t]; tot=sum(c.values()); rows.append([t, c["value"], c["absent"], c["contested"],
        f"{(c['value']+c['absent'])/tot:.0%}"])
display(HTML("<b>GT coverage per tier</b>"+
 pd.DataFrame(rows,columns=["tier","value-gold","absent-gold","contested","gold coverage"]).to_html(index=False)))
display(Markdown(
 "**Tier-1 is a real yardstick — 95% of cells resolve** (a value or a confident absence). Tier-2 drops to "
 "83%. And note the shape of Tier-3: it looks '91% resolved', but that's almost all **absence** — only ~32 "
 "cells carry an agreed *value*, the rest is 'this field isn't present.' So where a Tier-3 field actually "
 "appears, a cross-lab panel usually **can't** agree on its value. The contested cells aren't noise to "
 "hide — they're the honest statement that some covariates have no knowable answer from a short post."))
'''

S2 = ("## 2. How quirky was the single Opus gold? — the Opus-dissent rate\n\n"
      "The payoff of a consensus gold: we can finally measure how often the incumbent single-model gold "
      "was itself the **outlier** — the other three labs agreed on a value and Opus disagreed. Every one "
      "of those cells is a place the old 'accuracy vs Opus' score mis-graded a model that was actually right.")
S2_CODE = r'''
od = gt["opus_dissent"]
rates=[od[t]["rate"]*100 for t in TIER]
fig,ax=plt.subplots(figsize=(8,4.6))
ax.bar(TIER,rates,color=[TCOL[t] for t in TIER])
for i,t in enumerate(TIER):
    ax.text(i,rates[i]+0.5,f"{od[t]['dissent']}/{od[t]['value_cells']} = {rates[i]:.0f}%",ha="center",fontweight="bold")
ax.set_ylabel("Opus is the cross-lab outlier (%)"); ax.set_ylim(0,25)
ax.set_title("On 12–18% of gold cells, the single Opus gold was itself the outlier")
fig.tight_layout(); plt.show()
display(Markdown(
 f"**On {od['Tier-1']['rate']:.0%} of Tier-1, {od['Tier-2']['rate']:.0%} of Tier-2 and {od['Tier-3']['rate']:.0%} "
 f"of Tier-3 value-gold cells, Opus dissented from the cross-lab consensus.** That is the quirk rate baked into "
 f"every 'accuracy vs Opus' number — roughly **1 in 6** cells where a model that agreed with three other "
 f"frontier labs was scored *wrong* for disagreeing with Opus. It's the concrete reason a single-model gold "
 f"can't anchor the study, and the reason the numbers below are higher (and fairer) than the vs-Opus ones."))
'''

S3 = ("## 3. True accuracy against the consensus gold\n\n"
      "Now the reusable yardstick: each non-panel model's value-accuracy on the gold cells (scored where "
      "Opus is in the consensus, so the candidate-vs-Opus semantic verdict is a valid proxy for candidate-"
      "vs-gold). This is precision on populated values — *when the model gives a value, does it match the "
      "cross-lab answer* — not recall.")
S3_CODE = r'''
sc = gt["candidate_accuracy"]
# sort by Tier-1
order=sorted(sc, key=lambda m:-(sc[m]["Tier-1"][0] or 0))
x=np.arange(len(order)); w=0.26
fig,ax=plt.subplots(figsize=(12,6))
for i,t in enumerate(TIER):
    vals=[(sc[m][t][0] or 0)*100 for m in order]
    ax.bar(x+(i-1)*w,vals,w,color=TCOL[t],label=t)
ax.set_xticks(x); ax.set_xticklabels(order,rotation=55,ha="right",fontsize=8)
ax.set_ylabel("value accuracy vs consensus gold (%)"); ax.set_ylim(0,100); ax.legend()
ax.set_title("True accuracy vs cross-lab consensus gold (value cells) — Tier-1 is 90–99%")
fig.tight_layout(); plt.show()
rows=[]
for m in order:
    def f(t): a,n=sc[m][t]; return f"{a:.0%} (n={n})" if a is not None else "—"
    rows.append([m, f("Tier-1"), f("Tier-2"), f("Tier-3")])
display(HTML("<b>Value accuracy vs consensus gold, per tier</b>"+
 pd.DataFrame(rows,columns=["model","Tier-1","Tier-2","Tier-3"]).to_html(index=False)))
t1=[sc[m]["Tier-1"][0] for m in sc if sc[m]["Tier-1"][0] is not None]
display(Markdown(
 f"**Against cross-lab truth, Tier-1 accuracy is 90–99% — much higher than the vs-Opus numbers implied.** "
 f"A big slice of the old 'error' was Opus-quirk (§2), not model error. Tier-2 spreads wider (64–93%) and "
 f"Tier-3 rides on ~20–28 cells per model, so read it as directional, not precise. **Note deepseek-v4-flash "
 f"(the production candidate) sits at the low end of Tier-1** — another reason to run coding as cross-lab "
 f"consensus, not that model solo."))
'''

S4 = "## 4. Verdict — a real yardstick, honestly scoped"
S4_CODE = r'''
lines=[
 "- **This is the accuracy yardstick the study lacked.** Cross-lab frontier consensus, frozen — reusable to "
 "score any future model or batch size cheaply, with no single lab's house-style as 'truth'.",
 f"- **The single-Opus gold mis-graded ~1 in 6 cells** (12–18% Opus-dissent). Every vs-Opus accuracy number in "
 "the earlier notebooks is understated by roughly that much on the fields where it dissented.",
 "- **Tier-1 is genuinely gradeable (95% coverage, 90–99% accuracy). Tier-3 values are not** — only ~32 agreed "
 "value cells across 30 posts; the panel itself can't fix a covariate that a short post underdetermines. Score "
 "Tier-1, screen Tier-2, and treat Tier-3 as characterize-don't-grade.",
 "- **Freeze this and extend it.** v1 is 30 posts; a 150-post panel run (same four models) turns it into the "
 "durable GT the plan called for, and would cover ②/⑨ the same way. The construction here is the reusable part.",
]
display(Markdown("\n".join(lines)))
'''

LIM = '''## Limitations

- **30 posts.** Tier-3 value-gold is ~32 cells; per-model Tier-3 accuracy rides on 20–28 cells — wide bars.
  The construction is the deliverable; scale to ~150 posts for a stable yardstick.
- **"Silver-plus," not human truth.** The gold is cross-lab model *consensus*. Where all four frontier labs
  share a blind spot, the consensus inherits it — better than one lab, not independent ground truth.
- **Scoring proxy.** Candidate accuracy is measured via the candidate-vs-Opus semantic verdict, valid only on
  gold cells where Opus is in the consensus (the majority). Cells where Opus dissented are excluded from
  scoring (and reported separately in §2), so they don't distort the numbers.
- **Precision, not recall.** These are value-agreement rates on populated cells; whether a model *populates*
  the gold cells (recall) is the separate presence question from the ⑪ coding notebook.
- Measures coding accuracy against a model consensus, not any treatment effect. Not medical advice.'''

PROV = r'''
prov=pd.DataFrame({"item":["gold","panel","posts","gold rule","scoring","skill"],
 "value":["cross-lab frontier consensus", ", ".join(p.split("/")[-1] for p in gt["panel"]), str(gt["n_posts"]),
          "≥3 of 4 agree (value) or ≥3 absent; else contested",
          "value accuracy vs consensus where Opus ∈ consensus", "research-assistant v2"]})
display(HTML("<b>Provenance</b>"+prov.to_html(index=False)))
display(HTML('<div style="font-size:1.15em;font-weight:bold;font-style:italic;margin-top:1em">'
             'A model-consensus gold, not human truth. Measures coding accuracy, not treatment effects. Not medical advice.</div>'))
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
    nb = build_notebook(cells, db_path=DB, title="J11 — factual GT (cross-lab consensus)")
    html = execute_and_export(nb, "notebooks/validation/j11_factual_gt", timeout=1200)
    print("Wrote", html)


if __name__ == "__main__":
    main()
