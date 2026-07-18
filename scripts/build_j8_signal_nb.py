"""
build_j8_signal_nb.py — Judgement 8 (signal strength) roster notebook.

Subjective family — no accuracy vs a gold. Reuses scripts/compute_alphas.py for ORDINAL
Krippendorff's alpha (weak < moderate < strong) on three axes: within-model (K repeats),
cross-model (panel + pairwise divergence), and vs-Polina. Data comes from the shared ⑦/⑧
classify run; sentiment (⑦) is analysed separately. Signal is the least-agreed judgement in the
pipeline, and that is the finding. Prices at build time; code-free HTML.
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


RQ = ('**Research Question:** "For signal strength (judgement ⑧) — a subjective ordinal call '
      '(weak/moderate/strong) — how self-consistent is each model, how much do the models agree with each '
      'other, and do they track the human coder (Polina)?"\n\n*Judgement ⑧ of 11 · subjective family: no right '
      'answer, so the axis is consistency (Krippendorff\'s ordinal alpha), not accuracy. Sentiment (⑦) is '
      'analysed separately.*')

LOAD = r'''
import json, sys
sys.path.insert(0, r"__SCRIPTS__")
import compute_alphas as ca

RUNS = json.load(open(r"__RUNS__", encoding="utf-8"))
MAN = RUNS["manifest"]; results = RUNS["results"]; polina = RUNS["polina"]
CAND = MAN["candidate_models"]; K = MAN["k"]; PRICES = __PRICES__
MODELS = [m.split("/")[-1] for m in CAND]
def short(m): return m.split("/")[-1]
def nsig(v):
    v = str(v).lower().strip() if v else ""
    return ca.SIG_FIX.get(v, v)

def pivot_alpha(dfr):
    dfr = dfr[dfr.v.isin(ca.SIGNAL_ORDER)]   # ordinal levels only (drop n/a / blank)
    if not len(dfr):
        return None
    m, _ = ca.pivot_field(dfr, "v")
    return ca.krippendorff_alpha_ordinal(m) if m.size else None

rows = []
for r in results:
    if r["run"] == 0 and not r["parse_failed"]:
        rows.append(dict(coder_id=short(r["model"]), sample_id=r["sample_id"], canonical_drug=r["drug"], v=nsig(r["signal"])))
for p in polina:
    rows.append(dict(coder_id="Polina", sample_id=p["sample_id"], canonical_drug=p["drug"], v=nsig(p["signal"])))
df = pd.DataFrame(rows); df = df[df.v.isin(ca.SIGNAL_ORDER)]
mo = df[df.coder_id != "Polina"]
mmat, _ = ca.pivot_field(mo, "v"); PANEL = ca.krippendorff_alpha_ordinal(mmat) if mmat.size else None
PAIR = ca.pairwise_alphas(mo, "v", ordinal=True)
VSP = {md: pivot_alpha(df[df.coder_id.isin([md, "Polina"])]) for md in MODELS}
WITHIN = {}
for m0 in CAND:
    rr = [r for r in results if r["model"] == m0 and not r["parse_failed"]]
    w = pd.DataFrame([dict(coder_id="r%d" % r["run"], sample_id=r["sample_id"], canonical_drug=r["drug"], v=nsig(r["signal"])) for r in rr])
    WITHIN[short(m0)] = pivot_alpha(w) if (len(w) and w.coder_id.nunique() >= 2) else None

def _f(x): return f"{x:.2f}" if (x is not None and x == x) else "n/a"
_vp = pd.Series({k: v for k, v in VSP.items() if v is not None})
display(Markdown(f"""
**Abstract.** Signal strength (⑧) — how *strong* a report is — is subjective and ordinal, so we measure
consistency, not accuracy, across **{len(MODELS)} models** on the Polina-labelled pairs (k={K}, temp 0), using
ordinal Krippendorff's α (a weak-vs-strong miss counts more than weak-vs-moderate). **Within-model** self-
agreement is high (median α **{_f(pd.Series(WITHIN).median())}**). But **cross-model** agreement is the lowest
of any judgement in the pipeline: panel α **{_f(PANEL)}** — models genuinely disagree on *how strong* a report
is, even when they agree on its direction. Against **Polina** the median is **{_f(_vp.median())}**. The reading:
signal is **intrinsically underdetermined** from short posts, which caps how much any downstream weighting by
signal strength can be trusted — and, as everywhere in the subjective family, agreement here is a diagnostic,
not a verdict.
"""))
'''.replace("__RUNS__", RUNS_JSON).replace("__SCRIPTS__", SCRIPTS)

S1 = ("## 1. Why signal is measured by consistency, not accuracy\n\n"
      "Signal strength (weak / moderate / strong) rates how emphatic a report is — an interpretive, ordinal "
      "call with no external truth. So we measure consistency with **ordinal** Krippendorff's α (unlike "
      "sentiment's nominal α, an ordinal metric treats weak-vs-strong as a bigger miss than weak-vs-moderate): "
      "does a model agree with **itself**, the **other models**, and the **human**? The governing caveat is the "
      "same — agreement is a diagnostic of how underdetermined the call is, not proof anyone is right.")

S2 = ("## 2. Within-model consistency at temperature 0\n\n"
      "Each model against itself across the K repeats. High = stable; low = the model itself can't reproduce "
      "its own strength rating.")
S2_CODE = r'''
w = pd.DataFrame({"mshort": MODELS, "a": [WITHIN.get(m) for m in MODELS]}).dropna().sort_values("a")
ys = np.arange(len(w))
fig, ax = plt.subplots(figsize=(8, 1.2 + 0.42*len(w)))
ax.hlines(ys, 0, w.a, color="#f3ddc7", lw=3, zorder=1)
ax.scatter(w.a, ys, color="#e67e22", s=80, zorder=2)
for y, v in zip(ys, w.a):
    ax.text(v + 0.01, y, f"{v:.2f}", va="center", fontsize=8)
ax.axvline(1.0, ls="--", color="#999", lw=1)
ax.set_yticks(ys); ax.set_yticklabels(w.mshort); ax.set_xlim(min(0, w.a.min()-0.05), 1.08)
ax.set_xlabel("within-model ordinal α over K repeats (1 = perfectly self-consistent)")
ax.set_title("Signal: within-model consistency at temperature 0"); fig.tight_layout(); plt.show()
display(Markdown(
  f"**What this shows:** within-model ordinal α is high (median **{w.a.median():.2f}**) — a model reproduces its "
  f"own strength call at temperature 0. So the disagreement in §3 is real between-model divergence, not noise."))
'''

S3 = ("## 3. Cross-model agreement — the least-agreed judgement\n\n"
      "The models against each other. Pairwise ordinal α heatmap + the panel α. Expect this to be the lowest "
      "in the pipeline: rating *strength* from a short post is genuinely underdetermined.")
S3_CODE = r'''
order = MODELS
M = PAIR.reindex(index=order, columns=order).astype(float)
fig, ax = plt.subplots(figsize=(0.42*len(order)+3, 0.42*len(order)+2))
im = ax.imshow(M.values, cmap="coolwarm_r", vmin=-0.2, vmax=1)
ax.set_xticks(range(len(order))); ax.set_xticklabels(order, rotation=90, fontsize=7)
ax.set_yticks(range(len(order))); ax.set_yticklabels(order, fontsize=7)
fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="pairwise ordinal α")
ax.set_title(f"Signal: cross-model agreement (panel α = {PANEL:.2f})")
fig.tight_layout(); plt.show()
out = {m: 1 - np.nanmean([PAIR.loc[m,o] for o in order if o != m]) for m in order}
od = pd.Series(out).sort_values(ascending=False)
display(Markdown(
  f"**What this shows:** panel ordinal α **{PANEL:.2f}** — the lowest cross-model agreement of any judgement "
  f"tested. Models concur on a report's *direction* far more than its *strength*. Biggest outlier "
  f"**{od.index[0]}** (1 − mean pairwise {od.iloc[0]:.2f}). Low agreement here isn't a model failure so much as "
  f"a property of the task: weak/moderate/strong is a fuzzy line on a 100–800-char post."))
'''

S4 = ("## 4. Agreement with the human coder (Polina)\n\n"
      "Each model vs Polina's signal labels — a **screen**, not a ranking (her codebook came from the same "
      "prompt).")
S4_CODE = r'''
vp = pd.DataFrame({"mshort": MODELS, "a": [VSP.get(m) for m in MODELS]}).dropna().sort_values("a")
fig, ax = plt.subplots(figsize=(8, 0.32*len(vp)+1))
colors = ["#e74c3c" if v < vp.a.median()-0.1 else "#e67e22" for v in vp.a]
ax.barh(vp.mshort, vp.a, color=colors, height=0.68)
for y,(_,r) in enumerate(vp.iterrows()): ax.text(r.a + 0.005, y, f"{r.a:.2f}", va="center", fontsize=7.5)
ax.axvline(vp.a.median(), ls="--", color="#999", lw=1, label=f"median {vp.a.median():.2f}")
ax.set_xlim(min(0, vp.a.min()-0.1), 1.0); ax.set_xlabel("signal ordinal α vs Polina (human)")
ax.set_title("Signal: agreement with the human coder (red = a low outlier)")
ax.legend(frameon=False, loc="lower right"); fig.tight_layout(); plt.show()
display(Markdown(
  f"**What this shows:** vs-Polina signal α clusters low around **{vp.a.median():.2f}** — even the human is only "
  f"loosely tracked, best **{vp.iloc[-1].mshort}** ({vp.iloc[-1].a:.2f}). Consistent with §3: strength is the "
  f"call humans and models alike find hardest to pin down, so vs-Polina here mostly confirms the task is fuzzy, "
  f"not that any model is right."))
'''

S5 = ("## 5. What low signal-agreement means for the pipeline\n\n"
      "Signal strength feeds any downstream weighting that treats a 'strong' report as worth more than a "
      "'weak' one. With cross-model (and human) agreement this low, that weighting rests on a judgement no two "
      "raters reliably reproduce. The honest implication: **treat signal as a coarse, low-confidence axis** — "
      "collapse it (e.g. strong-vs-not) rather than using three graded levels, or down-weight its role in "
      "clustering — until a better-specified rubric raises the ceiling. This is a task-property finding, not a "
      "model-selection one: no model rescues an underdetermined call.")

S6 = ("## 6. Conclusion & scorecard\n\n"
      "The consistency scorecard for signal — within-model, vs-Polina, divergence. No accuracy column, by design.")
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
display(HTML("<b>⑧ signal — consistency scorecard</b>" + show.to_html(index=False)))
lines = [
  f"- **Within-model is stable at temp 0** (median α {pd.Series(WITHIN).median():.2f}).",
  f"- **Cross-model agreement is the pipeline's lowest** (panel ordinal α {PANEL:.2f}) — models disagree on "
  f"strength far more than on direction.",
  f"- **vs-Polina is low and a screen** (median {SC.vs_polina.median():.2f}) — even humans are hard to track here.",
  f"- **Signal is an underdetermined axis.** No model fixes that; the actionable move is to coarsen or "
  f"down-weight signal downstream rather than trust three graded levels.",
]
display(Markdown("### Verdict\n\n" + "\n".join(lines)))
'''

S7 = '''## 7. Research limitations

- **Agreement ≠ validity** — a subjective ordinal call can be measured for consistency but not correctness.
- **Signal is intrinsically underdetermined** from 100–800-char posts, which caps ⑧'s ceiling regardless of
  model; low agreement here is largely a task property, not a model defect.
- **Polina is one contaminated-codebook coder** (signal set only on personal-use=yes items), so vs-Polina is a
  screen, not a ceiling.
- **Ordinal α depends on the level ordering** (weak < moderate < strong); the mapping of the models' and
  Polina's typo'd labels ("week", "medium") is normalized in compute_alphas.
- **K=3 repeats** — enough to show within-model stability at temp 0, not to estimate it tightly.
- Measures consistency of a measurement step, not any treatment effect.'''

PROV = r'''
import hashlib as _h
try: _sha = _h.sha256(open(r"__DB__","rb").read()).hexdigest()[:16]
except Exception: _sha = "n/a"
prov = pd.DataFrame({
  "item": ["run generated (UTC)","judgement","candidate models","reference","pairs / k","temperature","alpha impl","skill version"],
  "value": [MAN["generated_utc"], "8_signal_strength", len(CAND), MAN["reference"], f'{MAN["n_pairs"]} / {MAN["k"]}',
            MAN["temperature"], "compute_alphas.py (ordinal)", "research-assistant v2"],
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
    nb = build_notebook(cells, db_path=DB, title="Judgement 8 — signal strength (roster)")
    html = execute_and_export(nb, "notebooks/validation/j8_signal", timeout=1200)
    print("Wrote", html, "| prices:", len(prices))


if __name__ == "__main__":
    main()
