"""
build_j7_sentiment_nb.py — Judgement 7 (sentiment) roster notebook.

Subjective family — no accuracy vs a gold. Reuses scripts/compute_alphas.py for nominal
Krippendorff's alpha on three axes: within-model (K repeats), cross-model (panel + pairwise
divergence), and vs-Polina (human reference). Data comes from the shared ⑦/⑧ classify run;
⑧ signal is analysed in its own notebook. Caveat threaded throughout: agreement is diagnostic,
never validation. Prices at build time; code-free HTML.
"""
from __future__ import annotations
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notebooks"))
from build_notebook import build_notebook, execute_and_export

RUNS_JSON = (ROOT / "data" / "validation" / "j78_classify_runs.json").as_posix()
SCRIPTS = (ROOT / "scripts").as_posix()
DB = (ROOT / "patientpunk.db").as_posix()


def fetch_prices() -> dict:
    try:
        cat = json.load(urllib.request.urlopen(
            urllib.request.Request("https://openrouter.ai/api/v1/models", headers={"User-Agent": "pp"}), timeout=30))
        out = {}
        for m in cat["data"]:
            p = m.get("pricing", {}).get("prompt")
            if p is not None:
                try: out[m["id"]] = round(float(p) * 1_000_000, 3)
                except (TypeError, ValueError): pass
        return out
    except Exception:
        return {}


RQ = ('**Research Question:** "For sentiment (judgement ⑦) — a subjective 4-class call — how self-consistent '
      'is each model, how much do the models agree with each other, and do they track the human coder '
      '(Polina)?"\n\n*Judgement ⑦ of 11 · subjective family: no right answer, so the axis is consistency '
      '(Krippendorff\'s nominal alpha), not accuracy. Signal strength (⑧) is analysed separately.*')

LOAD = r'''
import json, sys
sys.path.insert(0, r"__SCRIPTS__")
import compute_alphas as ca

RUNS = json.load(open(r"__RUNS__", encoding="utf-8"))
MAN = RUNS["manifest"]; results = RUNS["results"]; polina = RUNS["polina"]
CAND = MAN["candidate_models"]; K = MAN["k"]; PRICES = __PRICES__
MODELS = [m.split("/")[-1] for m in CAND]
def short(m): return m.split("/")[-1]
def nsent(v):
    v = str(v).lower().strip() if v else ""
    return ca.SENT_FIX.get(v, v)

def pivot_alpha(df):
    df = df[df.v.astype(str).str.len() > 0]
    if not len(df):
        return None
    m, _ = ca.pivot_field(df, "v")
    return ca.krippendorff_alpha_nominal(m) if m.size else None

# cross-model long frame (run 0) + Polina
rows = []
for r in results:
    if r["run"] == 0 and not r["parse_failed"]:
        rows.append(dict(coder_id=short(r["model"]), sample_id=r["sample_id"], canonical_drug=r["drug"], v=nsent(r["sentiment"])))
for p in polina:
    rows.append(dict(coder_id="Polina", sample_id=p["sample_id"], canonical_drug=p["drug"], v=nsent(p["sentiment"])))
df = pd.DataFrame(rows); df = df[df.v.astype(str).str.len() > 0]
mo = df[df.coder_id != "Polina"]
mmat, _ = ca.pivot_field(mo, "v"); PANEL = ca.krippendorff_alpha_nominal(mmat) if mmat.size else None
PAIR = ca.pairwise_alphas(mo, "v")
VSP = {md: pivot_alpha(df[df.coder_id.isin([md, "Polina"])]) for md in MODELS}
WITHIN = {}
for m0 in CAND:
    rr = [r for r in results if r["model"] == m0 and not r["parse_failed"]]
    w = pd.DataFrame([dict(coder_id="r%d" % r["run"], sample_id=r["sample_id"], canonical_drug=r["drug"], v=nsent(r["sentiment"])) for r in rr])
    WITHIN[short(m0)] = pivot_alpha(w) if (len(w) and w.coder_id.nunique() >= 2) else None

# per-model sentiment mix (run 0) for the composition view
comp = (pd.DataFrame([dict(m=short(r["model"]), s=nsent(r["sentiment"])) for r in results
                      if r["run"] == 0 and not r["parse_failed"] and nsent(r["sentiment"])]))

def _f(x): return f"{x:.2f}" if (x is not None and x == x) else "n/a"
_vp = pd.Series({k: v for k, v in VSP.items() if v is not None})
display(Markdown(f"""
**Abstract.** Sentiment (⑦) has no clean right answer, so we measure consistency, not accuracy, across
**{len(MODELS)} models** on the **{MAN['n_pairs']}** Polina-labelled (post, drug) pairs (k={K}, temp 0).
**Within-model** self-agreement is very high (median nominal α **{_f(pd.Series(WITHIN).median())}**) — at
temperature 0 the call is near-deterministic, so run-to-run noise is not the issue. The real story is
**cross-model**: the roster's panel α is **{_f(PANEL)}** — moderate agreement, well short of 1, so models
genuinely diverge on the 4-class call. Against **Polina** the median α is **{_f(_vp.median())}**
(best {_vp.idxmax()} {_f(_vp.max())}). Read all of it with the caveat that **agreement is diagnostic, never
validation**: where the roster agrees it may simply share our prompt's bias — and the confirmed ~10–20%
positive over-call is exactly such a shared error, invisible as disagreement.
"""))
'''.replace("__RUNS__", RUNS_JSON).replace("__SCRIPTS__", SCRIPTS)

S1 = ("## 1. Why sentiment is measured by consistency, not accuracy\n\n"
      "Sentiment (positive / negative / mixed / neutral) is interpretive — there is no external truth to check "
      "it against, and an Opus judge would only reproduce the same interpretive bias. So instead of accuracy we "
      "ask three consistency questions with Krippendorff's α: does a model agree with **itself** across "
      "repeats, with the **other models**, and with the **human coder**? The caveat that governs all three: "
      "high agreement can mean the call is easy *or* that everyone inherited our prompt's bias — it is a "
      "diagnostic, never a verdict of correctness.")

S2 = ("## 2. Within-model consistency — is the call stable at temperature 0?\n\n"
      "First, each model against itself across the K repeats. At temperature 0 this should be near-perfect; "
      "where it isn't, sentiment is intrinsically unstable for that model.")
S2_CODE = r'''
w = pd.DataFrame({"mshort": MODELS, "a": [WITHIN.get(m) for m in MODELS]}).dropna().sort_values("a")
ys = np.arange(len(w))
fig, ax = plt.subplots(figsize=(8, 1.2 + 0.42*len(w)))
ax.hlines(ys, 0, w.a, color="#cfe0e1", lw=3, zorder=1)
ax.scatter(w.a, ys, color="#0e6b74", s=80, zorder=2)
for y, v in zip(ys, w.a):
    ax.text(v + 0.01, y, f"{v:.2f}", va="center", fontsize=8)
ax.axvline(1.0, ls="--", color="#999", lw=1)
ax.set_yticks(ys); ax.set_yticklabels(w.mshort); ax.set_xlim(min(0, w.a.min()-0.05), 1.08)
ax.set_xlabel("within-model nominal α over K repeats (1 = perfectly self-consistent)")
ax.set_title("Sentiment: within-model consistency at temperature 0"); fig.tight_layout(); plt.show()
display(Markdown(
  f"**What this shows:** within-model agreement is high (median **{w.a.median():.2f}**) — at temperature 0 the "
  f"sentiment call is close to deterministic, so run-to-run noise is small. The variability that matters lives "
  f"*between* models (§3), not within them."))
'''

S3 = ("## 3. Cross-model agreement — do the models agree on sentiment?\n\n"
      "Now the models against each other (one run each). The heatmap is pairwise α between every pair; the "
      "panel α (all at once) is the headline. This says who behaves alike — not who is right.")
S3_CODE = r'''
order = MODELS
M = PAIR.reindex(index=order, columns=order).astype(float)
fig, ax = plt.subplots(figsize=(0.42*len(order)+3, 0.42*len(order)+2))
im = ax.imshow(M.values, cmap="coolwarm_r", vmin=-0.2, vmax=1)
ax.set_xticks(range(len(order))); ax.set_xticklabels(order, rotation=90, fontsize=7)
ax.set_yticks(range(len(order))); ax.set_yticklabels(order, fontsize=7)
fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="pairwise nominal α")
ax.set_title(f"Sentiment: cross-model agreement (panel α = {PANEL:.2f})")
fig.tight_layout(); plt.show()
# outlier = 1 - mean pairwise
out = {m: 1 - np.nanmean([PAIR.loc[m,o] for o in order if o != m]) for m in order}
od = pd.Series(out).sort_values(ascending=False)
display(Markdown(
  f"**What this shows:** panel α **{PANEL:.2f}** — moderate, well below 1: models diverge on the 4-class call, "
  f"not just at the margin. The biggest outlier is **{od.index[0]}** (1 − mean pairwise = {od.iloc[0]:.2f}); the "
  f"most typical is **{od.index[-1]}**. But an outlier is only 'wrong' if it *also* diverges from the human "
  f"(§4) — divergence alone doesn't say who's right."))
'''

S4 = ("## 4. Agreement with the human coder (Polina)\n\n"
      "Each model against Polina's 116 labels. Higher α = tracks the human better — but read it as a **screen**, "
      "not a ranking: Polina's codebook was lifted from the same prompt, so this measures spec-compliance, not "
      "correctness.")
S4_CODE = r'''
vp = pd.DataFrame({"mshort": MODELS, "a": [VSP.get(m) for m in MODELS]}).dropna().sort_values("a")
fig, ax = plt.subplots(figsize=(8, 0.32*len(vp)+1))
colors = ["#e74c3c" if v < vp.a.median()-0.1 else "#0e6b74" for v in vp.a]
ax.barh(vp.mshort, vp.a, color=colors, height=0.68)
for y,(_,r) in enumerate(vp.iterrows()): ax.text(r.a + 0.005, y, f"{r.a:.2f}", va="center", fontsize=7.5)
ax.axvline(vp.a.median(), ls="--", color="#999", lw=1, label=f"median {vp.a.median():.2f}")
ax.set_xlim(min(0, vp.a.min()-0.05), 1.0); ax.set_xlabel("sentiment α vs Polina (human)")
ax.set_title("Sentiment: agreement with the human coder (red = a low outlier)")
ax.legend(frameon=False, loc="lower right"); fig.tight_layout(); plt.show()
display(Markdown(
  f"**What this shows:** models cluster around α **{vp.a.median():.2f}** with Polina — the best is "
  f"**{vp.iloc[-1].mshort}** ({vp.iloc[-1].a:.2f}), the low outlier **{vp.iloc[0].mshort}** ({vp.iloc[0].a:.2f}). "
  f"This screens out a model that codes sentiment wildly differently from a human; it does **not** rank who is "
  f"'correct', because Polina and the models were both handed the same rubric."))
'''

S5 = ("## 5. The one probe that could push past agreement — the permutation null\n\n"
      "Consistency can't tell whether sentiment is actually **drug-conditional** or just reads generic "
      "positivity in the post. The test that can (no gold needed): re-run sentiment asking about drug *X* on "
      "posts that are really about drug *Y*. If the 'helped' rate doesn't collapse toward the base rate under "
      "that permutation, the model isn't reading the drug — it's reading the vibe. **This permuted pass is not "
      "in this run — it is the recommended next step for ⑦**, and the single most informative check we can add "
      "without labels.")

S6 = ("## 6. Conclusion & scorecard\n\n"
      "The consistency scorecard for sentiment — within-model, vs-Polina, divergence. No accuracy column, by design.")
S6_CODE = r'''
order = MODELS
rows = []
for m in order:
    div = 1 - np.nanmean([PAIR.loc[m,o] for o in order if o != m])
    rows.append(dict(model=m, within=WITHIN.get(m), vs_polina=VSP.get(m), divergence=div,
                     price=PRICES.get(next(c for c in CAND if c.split('/')[-1]==m), np.nan)))
SC = pd.DataFrame(rows).sort_values("vs_polina", ascending=False)
show = SC.copy()
for c in ["within","vs_polina","divergence"]: show[c] = show[c].round(2)
show["price"] = show["price"].map(lambda v: f"${v:g}" if pd.notna(v) else "?")
show.columns = ["model","within-model α","vs Polina α","divergence","$/1M in"]
display(HTML("<b>⑦ sentiment — consistency scorecard</b>" + show.to_html(index=False)))
lines = [
  f"- **Within-model is a non-issue at temp 0** (median α {pd.Series(WITHIN).median():.2f}).",
  f"- **Cross-model agreement caps at panel α {PANEL:.2f}** — sentiment is moderately, not strongly, agreed; "
  f"the roster genuinely splits on the 4-class call.",
  f"- **vs-Polina is a screen** (median {SC.vs_polina.median():.2f}) — it flags outliers, not who is right.",
  f"- **No model is 'correct' on sentiment.** It is validated only to consistency, and the shared positive "
  f"over-call sits underneath every number here. The permutation null (§5) is the next step to probe whether "
  f"sentiment is drug-conditional at all.",
]
display(Markdown("### Verdict\n\n" + "\n".join(lines)))
'''

S7 = '''## 7. Research limitations

- **Agreement ≠ validity** — the defining limit of a subjective judgement. Shared prompt bias inflates
  agreement; the confirmed ~10–20% positive over-call is a shared error that does not show up as disagreement.
- **Polina is one contaminated-codebook coder** (116 labels, codebook lifted from the prompt), so vs-Polina is
  a screen for outliers, not a human-agreement ceiling. Per-class cells (neutral 5, mixed 16) are too small for
  per-class scoring.
- **The permutation null is not in this run** (§5) — it is the recommended next probe for ⑦.
- **K=3 repeats** — enough to show within-model stability at temp 0, not to estimate it tightly.
- Measures consistency of a measurement step, not any treatment effect.'''

PROV = r'''
import hashlib as _h
try: _sha = _h.sha256(open(r"__DB__","rb").read()).hexdigest()[:16]
except Exception: _sha = "n/a"
prov = pd.DataFrame({
  "item": ["run generated (UTC)","judgement","candidate models","reference","pairs / k","temperature","alpha impl","skill version"],
  "value": [MAN["generated_utc"], "7_sentiment", len(CAND), MAN["reference"], f'{MAN["n_pairs"]} / {MAN["k"]}',
            MAN["temperature"], "compute_alphas.py (nominal)", "research-assistant v2"],
})
display(HTML("<b>Provenance</b>" + prov.to_html(index=False)))
display(HTML('<div style="font-size:1.2em;font-weight:bold;font-style:italic;margin-top:1em">'
             'These findings reflect the consistency of a measurement pipeline, not population-level treatment '
             'effects. This is not medical advice.</div>'))
'''.replace("__DB__", DB)


def main():
    prices = fetch_prices()
    load_cell = LOAD.replace("__PRICES__", repr(prices))
    cells = [
        ("md", RQ), ("code", load_cell),
        ("md", S1),
        ("md", S2), ("code", S2_CODE),
        ("md", S3), ("code", S3_CODE),
        ("md", S4), ("code", S4_CODE),
        ("md", S5),
        ("md", S6), ("code", S6_CODE),
        ("md", S7), ("code", PROV),
    ]
    nb = build_notebook(cells, db_path=DB, title="Judgement 7 — sentiment (roster)")
    html = execute_and_export(nb, "notebooks/validation/j7_sentiment", timeout=1200)
    print("Wrote", html, "| prices:", len(prices))


if __name__ == "__main__":
    main()
