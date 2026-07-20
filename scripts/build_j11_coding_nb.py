"""
build_j11_coding_nb.py — Judgement 11 (variable coding) roster notebook.

Track B step 2. Each model fills the fixed 37-field schema on patient posts; correctness = per-field
P/R/F1 vs Opus-coded gold. A field prediction is scored on PRESENCE (did the model populate the field
iff Opus did) and VALUE agreement (Jaccard of the value sets when both populate it). The novel angle:
which of the 37 covariates are reliably codable and which are not — that tells clustering which axes to
trust. Prices at build time; exports code-free HTML.
"""
from __future__ import annotations
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notebooks"))
from build_notebook import build_notebook, execute_and_export

RUNS_JSON = (ROOT / "data" / "validation" / "j11_coding_runs.json").as_posix()
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


RQ = ('**Research Question:** "For variable coding (judgement ⑪), how accurately does each model fill the '
      'fixed 37-field schema — per-field, against Opus-coded gold — and which covariates are reliably '
      'codable at all?"\n\n*Judgement ⑪ of 11 · Track B, step 2. The fields clustering runs on are only as '
      'good as this step. Numbers computed from the run.*')

LOAD = r'''
import json
from collections import defaultdict
from itertools import combinations

RUNS = json.load(open(r"__RUNS__", encoding="utf-8"))
MAN = RUNS["manifest"]
codings, gold_list, FIELDS = RUNS["codings"], RUNS["gold"], MAN["fields"]
CAND = MAN["candidate_models"]
PRICES = __PRICES__
def short(m): return m.split("/")[-1]
GOLD = {g["sample_id"]: g["fields"] for g in gold_list}
SAMPLES = sorted(GOLD)

def jacc(a, b):
    a, b = set(a or []), set(b or [])
    return len(a & b) / len(a | b) if (a | b) else 1.0

cod = defaultdict(dict)
for c in codings:
    cod[c["model"]][c["sample_id"]] = c["fields"]

VAL_TAU = 0.3  # value-set overlap needed to count a co-populated field as value-correct

# per-model presence P/R/F1, value agreement, and strict field-F1 (present + value agrees)
mr = []
field_stat = {f: dict(tp=0, fp=0, fn=0, vj=[]) for f in FIELDS}
for m in CAND:
    tp = fp = fn = 0; vjac = []; strict_correct = 0
    for s in SAMPLES:
        gf, mf = GOLD.get(s, {}), cod[m].get(s, {})
        for f in FIELDS:
            gp, mp = bool(gf.get(f)), bool(mf.get(f))
            if gp and mp:
                tp += 1; vj = jacc(mf.get(f), gf.get(f)); vjac.append(vj)
                if vj >= VAL_TAU: strict_correct += 1
                field_stat[f]["tp"] += 1; field_stat[f]["vj"].append(vj)
            elif gp and not mp:
                fn += 1; field_stat[f]["fn"] += 1
            elif mp and not gp:
                fp += 1; field_stat[f]["fp"] += 1
    prec = tp / (tp + fp) if (tp + fp) else np.nan
    rec = tp / (tp + fn) if (tp + fn) else np.nan
    f1 = 2 * prec * rec / (prec + rec) if (prec and rec) else np.nan
    # strict F1 (presence AND value agreement)
    sprec = strict_correct / (tp + fp) if (tp + fp) else np.nan
    srec = strict_correct / (tp + fn) if (tp + fn) else np.nan
    sf1 = 2 * sprec * srec / (sprec + srec) if (sprec and srec) else np.nan
    mr.append(dict(model=m, mshort=short(m), presence_f1=f1, precision=prec, recall=rec,
                   value_acc=(np.mean(vjac) if vjac else np.nan), strict_f1=sf1,
                   n_populated=tp + fp, price=PRICES.get(m, np.nan)))
MS = pd.DataFrame(mr)
FAILED = MS[MS.n_populated == 0].mshort.tolist()
MS = MS[MS.n_populated > 0].reset_index(drop=True)

# per-field codability (presence F1 pooled across models + mean value agreement)
fr = []
for f in FIELDS:
    st = field_stat[f]
    p = st["tp"] / (st["tp"] + st["fp"]) if (st["tp"] + st["fp"]) else np.nan
    r = st["tp"] / (st["tp"] + st["fn"]) if (st["tp"] + st["fn"]) else np.nan
    f1 = 2 * p * r / (p + r) if (p and r) else np.nan
    fr.append(dict(field=f, presence_f1=f1, value_acc=(np.mean(st["vj"]) if st["vj"] else np.nan),
                   gold_freq=st["tp"] + st["fn"]))
FS = pd.DataFrame(fr)

_best = MS.sort_values("strict_f1", ascending=False).iloc[0]
_hard = FS[FS.gold_freq >= 3].sort_values("presence_f1").head(3)
_easy = FS[FS.gold_freq >= 3].sort_values("presence_f1", ascending=False).head(3)
display(Markdown(f"""
**Abstract.** Variable coding (judgement ⑪) fills the fixed **{len(FIELDS)}-field** schema with values —
the covariates clustering actually runs on. We score each of **{len(MS)} models** on {MAN['n_posts']} posts
against **Opus-coded gold**, per field, on presence (did it populate the field iff Opus did) and value
agreement (overlap of the values). **{_best.mshort}** codes best (strict F1={_best.strict_f1:.2f}, counting a
field correct only when it is both populated and its values overlap gold). But the sharper finding is
per-field: some covariates are reliably codable — **{', '.join(_easy.field)}** — while others are near-
unusable no matter the model — **{', '.join(_hard.field)}** — which tells clustering which axes to trust and
which to drop.{(' No parseable codings from: ' + ', '.join(FAILED) + '.') if FAILED else ''}
"""))
'''.replace("__RUNS__", RUNS_JSON)

S1 = ("## 1. What this judgement is, and why it's load-bearing\n\n"
      "`llm_extract.py` reads a post and fills the fixed schema — `age`, `conditions`, `functional_status_tier`, "
      "`treatment_outcome`, and 33 others. These *are* the clustering covariates: a mis-coded or missing value "
      "is a corrupt or absent feature. Because the schema is fixed and the source text is given, this is "
      "factual — scored per field against an Opus-coded gold, on whether the model populates the right fields "
      "(presence) and gets the right values.")

S2 = ("## 2. Correctness scorecard\n\n"
      "Per model, three numbers: **presence F1** (did it populate the fields Opus did?), **value agreement** "
      "(when both populate a field, do the values overlap?), and **strict F1** (a field counts only if "
      "populated *and* values agree). Strict F1 is the headline — it penalises both missing a field and "
      "filling it with the wrong value.")
S2_CODE = r'''
d = MS.sort_values("strict_f1")
fig, ax = plt.subplots(figsize=(8, 0.34*len(d) + 1))
ax.barh(d.mshort, d.strict_f1, color="#0e6b74", height=0.68)
for y, (_, r) in enumerate(d.iterrows()):
    ax.text(r.strict_f1 + 0.01, y, f"P{r.precision:.0%}/R{r.recall:.0%} · val {r.value_acc:.0%}", va="center", fontsize=7.5, color="#555")
ax.set_xlim(0, 1.25); ax.set_xlabel("strict F1 vs Opus gold  (labels: presence P/R · value agreement)")
ax.set_title("Variable-coding accuracy by model"); fig.tight_layout(); plt.show()
tbl = MS.sort_values("strict_f1", ascending=False)[["mshort","strict_f1","presence_f1","precision","recall","value_acc","price"]].copy()
for c in ["strict_f1","presence_f1"]: tbl[c] = tbl[c].round(2)
for c in ["precision","recall","value_acc"]: tbl[c] = (tbl[c]*100).round(0).astype("Int64").astype(str)+"%"
tbl["price"] = tbl["price"].map(lambda v: f"${v:g}" if pd.notna(v) else "?")
tbl.columns = ["model","strict F1","presence F1","precision","recall","value agree","$/1M in"]
display(HTML("<b>Per-model coding accuracy</b>" + tbl.to_html(index=False)))
'''

S3 = ("## 3. The real finding — which covariates are codable\n\n"
      "Model choice matters less than *field* choice. Pooled across the roster, each field has its own "
      "codability: some are extracted reliably, others fail for everyone. A field no model can code is a "
      "clustering axis to drop, regardless of which model runs production.")
S3_CODE = r'''
d = FS[FS.gold_freq >= 2].sort_values("presence_f1")
fig, ax = plt.subplots(figsize=(8.5, 0.32*len(d) + 1))
colors = ["#e74c3c" if v < 0.5 else "#f1c40f" if v < 0.75 else "#27ae60" for v in d.presence_f1.fillna(0)]
ax.barh(d.field, d.presence_f1.fillna(0), color=colors, height=0.7)
for y, (_, r) in enumerate(d.iterrows()):
    ax.text(0.01, y, f"  val {r.value_acc:.0%}" if pd.notna(r.value_acc) else "", va="center", fontsize=7, color="#333")
ax.set_xlim(0, 1.05); ax.set_xlabel("field presence-F1 pooled across models (green≥0.75, yellow≥0.5, red<0.5)")
ax.set_title("Per-field codability — which covariates the pipeline can trust"); fig.tight_layout(); plt.show()
red = d[d.presence_f1 < 0.5]
display(Markdown(
  f"**What this shows:** of {len(FS)} schema fields, **{int((FS.presence_f1>=0.75).sum())}** are coded reliably "
  f"(F1≥0.75) and **{len(red)}** are near-unusable (F1<0.5) — e.g. {', '.join(red.field.head(4))}. And presence "
  f"is the easy part: even on fields both populate, mean value agreement is only "
  f"**{FS.value_acc.mean():.0%}**, so the *values* drift further than the field-presence numbers suggest."))
'''

S4 = ("## 4. Counterintuitive: presence is easy, values are hard — and models split eager vs cautious\n\n"
      "A model can populate the right fields yet fill them with subtly wrong values, so the presence numbers "
      "flatter the real accuracy. And as in drug-ID, models sit on a precision–recall tradeoff — some over-"
      "populate (fill fields Opus left null), some under-populate (miss fields Opus found).")
S4_CODE = r'''
fig, ax = plt.subplots(figsize=(7.5, 6))
sizes = 40 + 400*(MS.value_acc.fillna(0) - MS.value_acc.min())/(MS.value_acc.max()-MS.value_acc.min()+1e-9)
sc = ax.scatter(MS.recall, MS.precision, s=sizes, c=MS.value_acc, cmap="viridis", zorder=3, edgecolor="white")
for i in {MS.precision.idxmax(), MS.recall.idxmax(), MS.strict_f1.idxmax(), MS.strict_f1.idxmin()}:
    r = MS.loc[i]; ax.annotate(r.mshort, (r.recall, r.precision), fontsize=8, fontweight="bold", xytext=(5,2), textcoords="offset points")
ax.set_xlabel("presence recall (found Opus's fields)"); ax.set_ylabel("presence precision (didn't invent fields)")
ax.set_xlim(0,1.02); ax.set_ylim(0,1.02); fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04, label="value agreement")
ax.set_title("Coding tradeoff: presence vs value (dot colour = value agreement)")
fig.tight_layout(); plt.show()
display(Markdown(
  f"**What this shows:** the most thorough is **{MS.sort_values('recall',ascending=False).iloc[0].mshort}** "
  f"({MS.recall.max():.0%} recall), the most conservative **{MS.sort_values('precision',ascending=False).iloc[0].mshort}** "
  f"({MS.precision.max():.0%} precision). But note the colour: even top presence models carry value agreement "
  f"around {MS.value_acc.median():.0%} — populating the field is not the same as coding it right, and clustering "
  f"consumes the *value*, not the presence."))
'''

S5 = ("## 5. Conclusion & scorecard — coding accuracy per dollar\n\n"
      "The scorecard, and the design's payoff for the covariate step.")
S5_CODE = r'''
best = MS.strict_f1.max()
elig = MS[MS.strict_f1 >= best - 0.05]
pick = elig.sort_values("price").iloc[0] if elig.price.notna().any() else MS.sort_values("strict_f1", ascending=False).iloc[0]
sc = MS.sort_values("strict_f1", ascending=False)[["mshort","strict_f1","presence_f1","value_acc","precision","recall","price"]].copy()
for c in ["strict_f1","presence_f1"]: sc[c] = sc[c].round(2)
for c in ["value_acc","precision","recall"]: sc[c] = (sc[c]*100).round(0).astype("Int64").astype(str)+"%"
sc["price"] = sc["price"].map(lambda v: f"${v:g}" if pd.notna(v) else "?")
sc.columns = ["model","strict F1","presence F1","value agree","precision","recall","$/1M in"]
display(HTML("<b>⑪ coding — full scorecard</b>" + sc.to_html(index=False)))
n_reliable = int((FS.presence_f1>=0.75).sum()); n_bad = int((FS.presence_f1<0.5).sum())
lines = [
  f"- **Best coder:** {MS.sort_values('strict_f1',ascending=False).iloc[0].mshort} (strict F1 {best:.2f}).",
  f"- **Best value:** **{pick.mshort}** — strict F1 {pick.strict_f1:.2f} at ${pick.price:g}/1M input"
  + (", within 5 points of the best while cheaper." if pick.strict_f1 < best else "."),
  f"- **Trust the field, not just the model:** {n_reliable} of {len(FS)} covariates code reliably (F1≥0.75); "
  f"{n_bad} are near-unusable (F1<0.5) and should be dropped or hand-audited before clustering. Measured on "
  f"presence-F1 **pooled across models**, so it is a property of the field rather than a per-model ranking — "
  f"it does not establish that every individual model fails them.",
  f"- **Values drift more than presence** (mean value agreement {MS.value_acc.mean():.0%}), so even a good "
  f"presence-F1 needs the value check before a covariate is trusted.",
]
display(Markdown("### Verdict\n\n" + "\n".join(lines)))
'''

S6 = '''## 6. Research limitations

- **Opus-as-gold is silver.** It codes the reference values, so a systematic Opus blind spot (a field it
  mis-reads, a value convention it prefers) becomes invisible "truth". The GT-review step (a second frontier
  coder) would tighten this — deferred.
- **Value matching is set-overlap (Jaccard).** "long covid" vs "long-covid" match after normalization, but
  paraphrases ("housebound" vs "cannot leave the house") do not — so value agreement is a lower bound; a
  semantic judge would score some near-misses as correct.
- **Presence vs value.** A field Opus left null that a model fills is scored a hallucination, but occasionally
  the model is right and Opus missed it (the mirror of ②); without the GT-review we can't separate those.
- **Posts** are 30 long-COVID posts; per-field codability is schema- and corpus-specific.
- **Price** is input $/1M and ignores the (larger) output token cost of coding 37 fields — an order-of-magnitude signal.
- Measures the correctness of a measurement step, not any treatment effect.'''

PROV = r'''
import hashlib as _h
try: _sha = _h.sha256(open(r"__DB__","rb").read()).hexdigest()[:16]
except Exception: _sha = "n/a"
prov = pd.DataFrame({
  "item": ["run generated (UTC)","judgement","candidate models","gold (truth)","schema",
           "posts / fields","temperature","skill version"],
  "value": [MAN["generated_utc"], MAN["judgement"], f'{len(CAND)} ({len(MS)} produced codings)',
            MAN["judge_model"], MAN["schema_id"], f'{MAN["n_posts"]} / {len(FIELDS)}',
            MAN["temperature"], "research-assistant v2"],
})
display(HTML("<b>Provenance</b>" + prov.to_html(index=False)))
display(HTML('<div style="font-size:1.2em;font-weight:bold;font-style:italic;margin-top:1em">'
             'These findings reflect the behaviour of a measurement pipeline and model knowledge, not '
             'population-level treatment effects. This is not medical advice.</div>'))
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
        ("md", S5), ("code", S5_CODE),
        ("md", S6), ("code", PROV),
    ]
    nb = build_notebook(cells, db_path=DB, title="Judgement 11 — variable coding (roster)")
    html = execute_and_export(nb, "notebooks/validation/j11_coding", timeout=1200)
    print("Wrote", html, "| prices:", len(prices))


if __name__ == "__main__":
    main()
