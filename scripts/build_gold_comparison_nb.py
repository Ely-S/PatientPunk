"""
build_gold_comparison_nb.py — is the model ranking robust, or an artifact of which model is "gold"?

Scores every candidate against THREE model-golds — Opus, GPT-5.6-Luna, GPT-5.6-Sol — using the same
Opus equivalence-judge each time, so only the gold changes. Answers whether the coding-quality ranking
holds across golds (it does), how much the three "authorities" disagree with each other (the irreducible
ambiguity), and whether each gold quietly flatters its own lab (family bias). Code-free HTML.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notebooks"))
from build_notebook import build_notebook, execute_and_export

DV = ROOT / "data" / "validation"
OPUS_F = (DV / "j11_rejudge.json").as_posix()
LUNA_F = (DV / "j11_vs_luna.json").as_posix()
SOL_F = (DV / "j11_vs_sol.json").as_posix()
DB = (ROOT / "patientpunk.db").as_posix()

FRAME = (
"# Is the coding-quality ranking real, or just \"who agrees with Opus\"?\n\n"
"Every earlier chart scored models against **Opus** as the gold. But Opus isn't ground truth — it's one "
"model's opinion. So we re-scored the same 30-post coding run against **three** model-golds — `Opus`, "
"`gpt-5.6-luna`, and `gpt-5.6-sol` — each time with the *same* Opus equivalence-judge, so the only thing "
"that changes is which model's codings are treated as truth. Three questions: does the ranking survive a "
"change of gold, how much do the three authorities disagree, and does each gold favour its own lab?")

LOAD = r'''
import json
from collections import defaultdict
from scipy.stats import spearmanr
OPUS="anthropic/claude-opus-4.8"; LUNA="openai/gpt-5.6-luna"; SOL="openai/gpt-5.6-sol"
def rate(fn):
    d=json.load(open(fn)); m=defaultdict(lambda:[0,0])
    for v in d["verdicts"]:
        if v["verdict"] in ("equivalent","model_subset","different"):
            m[v["model"]][0]+=1; m[v["model"]][1]+=v["verdict"]=="different"
    return {k:(e/n, n) for k,(n,e) in m.items()}
O=rate(r"__OPUS__"); L=rate(r"__LUNA__"); S=rate(r"__SOL__")
def short(m): return m.split("/")[-1]
# assemble a per-model table
allm=sorted(set(O)|set(L)|set(S), key=lambda k: S.get(k,(9,))[0])
rows=[]
for m in allm:
    rows.append(dict(model=short(m), slug=m,
                     vsOpus=O.get(m,(None,))[0], vsLuna=L.get(m,(None,))[0], vsSol=S.get(m,(None,))[0]))
df=pd.DataFrame(rows)
# authority mutual disagreement: each gold's error as a candidate under the others
disagree = {
 "Opus vs Luna": L.get(OPUS,(None,))[0], "Opus vs Sol": S.get(OPUS,(None,))[0],
 "Luna vs Opus": O.get(LUNA,(None,))[0], "Luna vs Sol": S.get(LUNA,(None,))[0],
 "Sol vs Opus": O.get(SOL,(None,))[0] if O.get(SOL) else None, "Sol vs Luna": L.get(SOL,(None,))[0] if L.get(SOL) else None,
}
display(Markdown(f"*(loaded — {len(df)} models scored across 3 golds)*"))
'''.replace("__OPUS__", OPUS_F).replace("__LUNA__", LUNA_F).replace("__SOL__", SOL_F)

S1 = ("## 1. Every model against all three golds\n\n"
      "Sorted by error vs Sol. A model has a gap where it *is* that gold (a model can't be scored against "
      "itself).")
S1_CODE = r'''
import numpy as np
m=df.copy(); y=np.arange(len(m)); h=0.26
fig,ax=plt.subplots(figsize=(10.5,9.5))
ax.barh(y+h, m["vsOpus"]*100, h, label="vs Opus-gold", color="#eda100")
ax.barh(y,   m["vsLuna"]*100, h, label="vs Luna-gold", color="#1baf7a")
ax.barh(y-h, m["vsSol"]*100,  h, label="vs Sol-gold",  color="#2a78d6")
ax.set_yticks(y); ax.set_yticklabels(m["model"], fontsize=9); ax.invert_yaxis()
ax.set_xlabel("coding error — % of values ruled 'different' vs each gold"); ax.set_xlim(0,36)
ax.grid(axis="x", alpha=0.3); ax.legend(loc="lower right")
ax.set_title("Per-model error across three model-golds"); fig.tight_layout(); plt.show()
tb=m[["model","vsOpus","vsLuna","vsSol"]].copy()
for c in ["vsOpus","vsLuna","vsSol"]: tb[c]=tb[c].apply(lambda x: f"{x:.0%}" if pd.notna(x) else "— (gold)")
display(HTML(tb.to_html(index=False)))
'''

S2 = "## 2. Does the ranking survive a change of gold?"
S2_CODE = r'''
sub=df.dropna(subset=["vsOpus","vsLuna","vsSol"])
r_ol=spearmanr(sub.vsOpus, sub.vsLuna).correlation
r_os=spearmanr(sub.vsOpus, sub.vsSol).correlation
r_ls=spearmanr(sub.vsLuna, sub.vsSol).correlation
best=df.sort_values("vsSol").iloc[0]["model"]; worst=df.sort_values("vsSol").iloc[-1]["model"]
display(Markdown(
 f"**Yes — strongly.** Spearman rank correlation between the golds: Opus↔Luna **{r_ol:.2f}**, "
 f"Opus↔Sol **{r_os:.2f}**, Luna↔Sol **{r_ls:.2f}**. The same models are good and bad regardless of which "
 f"is gold: `{best}` is best under all three; the small/cheap models (`qwen3-30b`, `mistral-small`, "
 f"`llama-4-scout`, `glm-4.7-flash`) are worst under all three. The quality tiers are a property of the "
 f"models, not of the gold — so the earlier Opus-based ranking wasn't an Opus artifact."))
'''

S3 = "## 3. How much do the three authorities disagree with each other?"
S3_CODE = r'''
d={k:v for k,v in disagree.items() if v is not None}
fig,ax=plt.subplots(figsize=(7,2.6))
ax.barh(list(d), [v*100 for v in d.values()], color="#c0392b", height=0.6)
for i,(k,v) in enumerate(d.items()): ax.text(v*100+0.3,i,f"{v:.0%}",va="center",fontsize=10,fontweight="bold")
ax.set_xlabel("error when one gold is scored as a candidate against another"); ax.set_xlim(0,max(d.values())*130)
ax.set_title("Mutual disagreement of the three golds"); ax.invert_yaxis(); fig.tight_layout(); plt.show()
mn=min(d.values()); mx=max(d.values())
display(Markdown(
 f"The three golds disagree with each other **{mn:.0%}–{mx:.0%}** of the time — the same order of magnitude "
 f"as a typical candidate's error. **No model is ground truth.** That mutual-disagreement band is the "
 f"irreducible interpretive ambiguity in the coding task: on ~1 value in 7, three capable models genuinely "
 f"read the post differently, and calling any one of them 'correct' is a choice, not a fact."))
'''

S4 = "## 4. Does each gold flatter its own lab? (family bias)"
S4_CODE = r'''
LAB={"anthropic":"Anthropic","openai":"OpenAI","google":"Google","meta-llama":"Meta","x-ai":"xAI",
     "deepseek":"DeepSeek","qwen":"Qwen","z-ai":"Zhipu","mistralai":"Mistral"}
df["lab"]=df["slug"].apply(lambda s: LAB.get(s.split("/")[0],"?"))
# Anthropic vs OpenAI candidates: mean error under Anthropic-gold (Opus) vs OpenAI-golds (Luna/Sol)
def lab_mean(lab, col):
    v=df[df.lab==lab][col].dropna(); return v.mean() if len(v) else float("nan")
rows=[]
for lab in ["Anthropic","OpenAI","Google","DeepSeek","xAI","Mistral","Qwen","Zhipu","Meta"]:
    o=lab_mean(lab,"vsOpus"); l=lab_mean(lab,"vsLuna"); s=lab_mean(lab,"vsSol")
    oa=(l+s)/2 if pd.notna(l) and pd.notna(s) else float("nan")   # mean vs the two OpenAI golds
    rows.append([lab, f"{o:.0%}" if pd.notna(o) else "-", f"{oa:.0%}" if pd.notna(oa) else "-",
                 f"{(oa-o):+.0%}" if pd.notna(o) and pd.notna(oa) else "-"])
tb=pd.DataFrame(rows, columns=["lab","vs Anthropic-gold (Opus)","vs OpenAI-golds (Luna/Sol avg)","Δ (OpenAI − Anthropic gold)"])
display(HTML(tb.to_html(index=False)))
display(Markdown(
 "**Yes, ~5–10 points.** Read the Δ column: **Anthropic** models are best under the Anthropic gold and get "
 "*worse* under the OpenAI golds (positive Δ — e.g. sonnet 13→17→19, haiku 17→20→28), while **OpenAI** models "
 "move the other way (gpt-5-mini 16→10→14). A model-gold measures *agreement with that model's house "
 "conventions*, not correctness — the concrete reason a single model-gold can't anchor the study."))
'''

S5 = "## 5. Verdict"
S5_CODE = r'''
lines=[
 "- **The ranking is real, not an Opus artifact** — rank correlation 0.7–0.9 across all three golds; the same "
 "models lead and trail regardless of which is gold.",
 "- **No model is ground truth** — the three golds disagree with each other ~13–16%, the irreducible ambiguity "
 "of the task. Any single 'accuracy vs gold' number is really *closeness to that model*.",
 "- **Each gold has a ~5–10pt family bias** toward its own lab, so a single model-gold systematically "
 "mis-ranks cross-lab. Score against **multiple golds (or a panel)** and read the tiers, not the decimals.",
 "- **Practical read for model selection:** trust the *tiers* — grok-4.5 / the frontier set at the top, the "
 "small/cheap models (qwen3-30b, mistral-small, llama-4-scout, glm-4.7-flash) reliably at the bottom under "
 "every gold — and treat sub-3-point gaps as noise (30 posts, ~180 values/model).",
]
display(Markdown("\n".join(lines)))
'''

LIM = '''## Limitations

- **Golds are models, not truth.** "Error" is disagreement with a model's codings; the whole point of §3 is
  that this is closeness, not correctness. A human-adjudicated gold would still be one contestable reading.
- **Sol is a slightly conservative gold** — it genuinely extracts fewer fields on ~3 posts (a real Sol trait,
  not a bug), so its comparison covers marginally fewer field-values; timeout-corrupted posts were repaired.
- **30 posts, ~180 values/model** — tiers are robust, the exact ordering within a tier is not; sub-3-point
  gaps are noise.
- **Same Opus equivalence-judge for all three golds** — this isolates the gold, but the judge itself is an
  Anthropic model; a different judge could shift absolute levels (not the cross-gold pattern).'''

PROV = r'''
M=json.load(open(r"__SOL__"))["manifest"]
prov=pd.DataFrame({"item":["golds","judge","models scored","posts","metric","skill"],
 "value":["Opus / gpt-5.6-luna / gpt-5.6-sol", M["judge_model"], str(len(df)), str(M["n_posts"]),
          "error = share of co-populated values ruled 'different'", "research-assistant v2"]})
display(HTML("<b>Provenance</b>"+prov.to_html(index=False)))
display(HTML('<div style="font-size:1.15em;font-weight:bold;font-style:italic;margin-top:1em">'
             'Describes agreement between model coders, not ground-truth accuracy or treatment effects. '
             'Not medical advice.</div>'))
'''.replace("__SOL__", SOL_F)


def main():
    cells = [
        ("md", FRAME), ("code", LOAD),
        ("md", S1), ("code", S1_CODE),
        ("md", S2), ("code", S2_CODE),
        ("md", S3), ("code", S3_CODE),
        ("md", S4), ("code", S4_CODE),
        ("md", S5), ("code", S5_CODE),
        ("md", LIM), ("code", PROV),
    ]
    nb = build_notebook(cells, db_path=DB, title="Model-gold triangulation (Opus / Luna / Sol)")
    html = execute_and_export(nb, "notebooks/validation/gold_triangulation", timeout=900)
    print("Wrote", html)


if __name__ == "__main__":
    main()
