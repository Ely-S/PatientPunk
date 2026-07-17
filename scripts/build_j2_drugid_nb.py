"""
build_j2_drugid_nb.py — Judgement 2 (drug identification) roster notebook.

Same template as ①, but drug identification needs precision AND recall, so the headline is
F1 vs Opus-as-judge, with string-in-post as the objective floor (which — unlike RxNorm for ①
— is too LOOSE: a drug name in the post isn't necessarily a treatment the author used). Cross-
model divergence (N×N Jaccard heatmap + outlier score) and a price-aware scorecard follow.
Prices fetched at build time; exports code-free HTML.
"""
from __future__ import annotations
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notebooks"))
from build_notebook import build_notebook, execute_and_export

RUNS_JSON = (ROOT / "data" / "validation" / "j2_drugid_runs.json").as_posix()
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


RQ = ('**Research Question:** "For drug identification (judgement ②), how accurately does each model in '
      'the roster extract the drugs mentioned in a post — precision AND recall, against Opus-as-truth — and '
      'how do the models diverge?"\n\n*Judgement ② of 11 · the factual template with a recall dimension: '
      'F1 vs the validated judge, a precision–recall map, an N×N divergence heatmap, and a price-aware '
      'scorecard. Numbers computed from the run.*')

LOAD = r'''
import json
from itertools import combinations

RUNS = json.load(open(r"__RUNS__", encoding="utf-8"))
MAN = RUNS["manifest"]
exts, judge, posts = RUNS["extractions"], RUNS["judge"], RUNS["posts"]
CAND = MAN["candidate_models"]
PRICES = __PRICES__
def short(m): return m.split("/")[-1]

JUDGE = {j["sample_id"]: j for j in judge}
# gold present-set per post = extractions Opus ruled correct + drugs Opus said everyone missed
gold = {s: ({d for d, v in j["verdicts"].items() if v == "correct"} | set(j.get("missed", [])))
        for s, j in JUDGE.items()}
def str_in_post(d, s): return len(d) >= 3 and d in posts[s].lower()
def jacc(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if (a | b) else np.nan

# per (model, post)
rows = []
for e in exts:
    m, s, ext = e["model"], e["sample_id"], e["drugs"]
    verd = JUDGE.get(s, {}).get("verdicts", {})
    correct = [d for d in ext if verd.get(d) == "correct"]
    strhit = [d for d in ext if str_in_post(d, s)]
    rows.append(dict(model=m, mshort=short(m), sample_id=s, n_ext=len(ext),
                     n_correct=len(correct), n_strhit=len(strhit), n_gold=len(gold.get(s, set()))))
df = pd.DataFrame(rows)

# per-model micro-pooled precision / recall / F1 / string-precision + price
ext_sets = {(e["model"], e["sample_id"]): set(e["drugs"]) for e in exts}
sample_ids = sorted(posts)
mr = []
for m in CAND:
    sub = df[df.model == m]
    ext_tot, corr_tot = int(sub.n_ext.sum()), int(sub.n_correct.sum())
    gold_tot, str_tot = int(sub.n_gold.sum()), int(sub.n_strhit.sum())
    prec = corr_tot / ext_tot if ext_tot else np.nan
    rec = corr_tot / gold_tot if gold_tot else np.nan
    f1 = 2 * prec * rec / (prec + rec) if (prec and rec and prec + rec) else np.nan
    mr.append(dict(model=m, mshort=short(m), precision=prec, recall=rec, f1=f1,
                   str_prec=(str_tot / ext_tot if ext_tot else np.nan),
                   n_ext_total=ext_tot, n_correct=corr_tot,
                   mean_ext=sub.n_ext.mean(), price=PRICES.get(m, np.nan)))
MS = pd.DataFrame(mr)
FAILED = MS[MS.n_ext_total == 0].mshort.tolist()
MS = MS[MS.n_ext_total > 0].reset_index(drop=True)
OK = MS.model.tolist()

# N×N divergence (mean Jaccard of extraction sets across posts)
MAT = pd.DataFrame(index=[short(m) for m in OK], columns=[short(m) for m in OK], dtype=float)
for x in OK:
    for y in OK:
        MAT.loc[short(x), short(y)] = 1.0 if x == y else np.nanmean(
            [jacc(ext_sets.get((x, s), set()), ext_sets.get((y, s), set())) for s in sample_ids])
MS["outlier"] = [1 - np.nanmean([MAT.loc[short(m), short(o)] for o in OK if o != m]) for m in OK]

_best = MS.sort_values("f1", ascending=False).iloc[0]
_bestP = MS.sort_values("precision", ascending=False).iloc[0]
_bestR = MS.sort_values("recall", ascending=False).iloc[0]
display(Markdown(f"""
**Abstract.** Drug identification (judgement ②) reads a post and returns the *set* of drugs mentioned —
`extract_batch`, the pipeline's second step. A missed drug is a lost treatment report; a hallucinated one
is a phantom report. We test the roster the way the design specifies: **{len(OK)} models** extract drugs
from **{MAN['n_posts']} posts** (temp 0), scored for **precision and recall against Opus-as-judge** (which
reads the post, rules each extraction correct/hallucinated, and lists drugs everyone missed), with a
string-in-post floor and an N×N divergence map beside it. **{_best.mshort}** has the best balance
(F1={_best.f1:.2f}); the roster splits into precise-but-cautious ({_bestP.mshort}, {_bestP.precision:.0%}
precision) and thorough-but-eager ({_bestR.mshort}, {_bestR.recall:.0%} recall) extractors. Note the string
floor is too *loose* — a drug name in a post (e.g. "histamine" in "histamine issues") isn't a treatment the
author used — so unlike RxNorm for ①, here the objective source over-credits, and the judge is stricter.
{(' No parseable extractions from: ' + ', '.join(FAILED) + '.') if FAILED else ''}
"""))
'''.replace("__RUNS__", RUNS_JSON)

S1 = ("## 1. What this judgement is, and why correctness matters\n\n"
      "`extract_batch` reads a post and returns the set of drugs, supplements, and treatments it mentions. "
      "Every downstream sentiment report is keyed to a drug this step found, so its errors bound the whole "
      "pipeline: a **missed** drug silently drops a treatment report; a **hallucinated** drug injects a "
      "phantom one. Because a post has a definite set of drugs, this is factual — measured by **precision** "
      "(are the extracted drugs really there?) and **recall** (did it find them all?), not agreement.")

S2 = ("## 2. Two truth sources — and why the objective floor is not enough here\n\n"
      "For ① alias, the objective source (RxNorm) was too *strict*. For ② the objective source — does the "
      "extracted drug literally appear in the post? — is too *loose*: a drug name can appear as the author's "
      "**condition**, not a treatment they took ('histamine issues'), so string-presence over-credits. "
      "That's why Opus-as-judge, which reads the post and rules on *treatment* mention, is the standard, and "
      "the string floor only corroborates.")
S2_CODE = r'''
fig, ax = plt.subplots(figsize=(7.5, 6))
ax.scatter(MS.str_prec, MS.precision, s=55, color="#0e6b74", zorder=3)
lim = [0, 1.02]
ax.plot(lim, lim, ls=":", color="#999", lw=1, label="floor = judge")
for _, r in MS.iterrows():
    if abs(r.str_prec - r.precision) > 0.12:
        ax.annotate(r.mshort, (r.str_prec, r.precision), fontsize=7.5, xytext=(4, 2), textcoords="offset points")
ax.set_xlabel("string-in-post precision (objective floor)"); ax.set_ylabel("Opus-judge precision (truth)")
ax.set_xlim(0, 1.02); ax.set_ylim(0, 1.02); ax.legend(frameon=False, loc="lower right")
ax.set_title("The objective floor over-credits: string-present ≠ treatment")
fig.tight_layout(); plt.show()
gap = (MS.str_prec - MS.precision).mean()
display(Markdown(
  f"**What this shows:** points below the diagonal are models whose string-precision **exceeds** their true "
  f"precision by {gap:+.0%} on average — the extra 'hits' are drug names that appear in the post but aren't "
  f"treatments the author used (conditions, drugs mentioned in passing). The naive objective check would "
  f"score these as correct; the judge (reading for *treatment* mention) does not. RxNorm was too strict; the "
  f"string floor is too generous — either alone misleads, which is why the validated judge is the standard."))
'''

S3 = ("## 3. Correctness scorecard — the verdict\n\n"
      "F1 against Opus-as-truth per model (precision × recall), sorted. F1 is the headline because both "
      "failure modes hurt the pipeline; precision and recall separately are in the table.")
S3_CODE = r'''
d = MS.sort_values("f1", ascending=True)
fig, ax = plt.subplots(figsize=(8, 0.34*len(d) + 1))
ax.barh(d.mshort, d.f1, color="#0e6b74", height=0.68)
for y, (_, r) in enumerate(d.iterrows()):
    ax.text(r.f1 + 0.01, y, f"P{r.precision:.0%}/R{r.recall:.0%}", va="center", fontsize=7.5, color="#555")
ax.set_xlim(0, 1.12); ax.set_xlabel("F1 vs Opus-judge  (labels: precision / recall)")
ax.set_title("Drug-identification accuracy by model"); fig.tight_layout(); plt.show()

tbl = MS.sort_values("f1", ascending=False)[["mshort","f1","precision","recall","str_prec","mean_ext","price"]].copy()
tbl["f1"] = tbl["f1"].round(2)
for c in ["precision","recall","str_prec"]: tbl[c] = (tbl[c]*100).round(0).astype("Int64").astype(str)+"%"
tbl["mean_ext"] = tbl["mean_ext"].round(1)
tbl["price"] = tbl["price"].map(lambda v: f"${v:g}" if pd.notna(v) else "?")
tbl.columns = ["model","F1","precision","recall","string floor","drugs/post","$/1M in"]
display(HTML("<b>Per-model correctness</b>" + tbl.to_html(index=False)))
'''

S4 = ("## 4. Counterintuitive: the precision–recall split\n\n"
      "There is no single 'best extractor' — models sit on a tradeoff. Cautious models extract only the "
      "obvious drugs (high precision, low recall — they drop the ones needing inference); eager models grab "
      "everything drug-shaped (high recall, low precision — they hallucinate). Which end you want depends on "
      "whether a phantom report or a missed report costs the pipeline more.")
S4_CODE = r'''
fig, ax = plt.subplots(figsize=(7.5, 6.4))
sizes = 40 + 500 * (MS.f1 - MS.f1.min()) / (MS.f1.max() - MS.f1.min() + 1e-9)
sc = ax.scatter(MS.recall, MS.precision, s=sizes, c=MS.f1, cmap="viridis", zorder=3, edgecolor="white")
for _, r in MS.iterrows():
    ax.annotate(r.mshort, (r.recall, r.precision), fontsize=7, xytext=(4, 2), textcoords="offset points")
for f in [0.5, 0.7, 0.85]:  # F1 iso-contours
    rr = np.linspace(0.01, 1, 100); pp = f * rr / (2 * rr - f)
    ok = (pp > 0) & (pp <= 1); ax.plot(rr[ok], pp[ok], ls=":", color="#ccc", lw=1)
ax.set_xlabel("recall (found all the drugs?)"); ax.set_ylabel("precision (were they real?)")
ax.set_xlim(0, 1.02); ax.set_ylim(0, 1.02)
fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04, label="F1")
ax.set_title("Precision–recall tradeoff across the roster (dotted = equal-F1)")
fig.tight_layout(); plt.show()
display(Markdown(
  f"**What this shows:** models spread along the tradeoff, not a single quality axis. The most **precise** is "
  f"**{MS.sort_values('precision', ascending=False).iloc[0].mshort}** ({MS.precision.max():.0%}); the most "
  f"**thorough** is **{MS.sort_values('recall', ascending=False).iloc[0].mshort}** ({MS.recall.max():.0%}). "
  f"For clustering, recall usually matters more — a missed drug is a missing data point — so a model in the "
  f"high-recall corner with acceptable precision is the safer default."))
'''

S5 = ("## 5. Comparing the models to each other — divergence map\n\n"
      "Mean Jaccard of extraction sets between every pair of models (1 = identical). It clusters the roster "
      "into behaviour groups and flags outliers — a diagnostic, never a correctness verdict (models can agree "
      "on the same misses).")
S5_CODE = r'''
order = MS.sort_values("f1", ascending=False).mshort.tolist()
M = MAT.reindex(index=order, columns=order).astype(float)
fig, ax = plt.subplots(figsize=(0.42*len(order) + 3, 0.42*len(order) + 2))
im = ax.imshow(M.values, cmap="viridis", vmin=0, vmax=1)
ax.set_xticks(range(len(order))); ax.set_xticklabels(order, rotation=90, fontsize=7)
ax.set_yticks(range(len(order))); ax.set_yticklabels(order, fontsize=7)
fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="mean Jaccard of extraction sets")
ax.set_title("Cross-model divergence (ordered by F1)"); fig.tight_layout(); plt.show()
od = MS.sort_values("outlier", ascending=False)[["mshort","outlier","f1"]].head(8).copy()
od["outlier"] = od["outlier"].round(2); od["f1"] = od["f1"].round(2)
od.columns = ["model","outlier (1 − mean agreement)","F1"]
display(HTML("<b>Most divergent models</b>" + od.to_html(index=False)))
display(Markdown(
  f"**What this shows:** the roster shares a mean "
  f"**{np.nanmean(MAT.values[np.triu_indices(len(order),1)]):.0%}** extraction overlap — lower than alias "
  f"generation, because *which* borderline mentions count as drugs is genuinely underdetermined. Read outliers "
  f"against §3: a divergent low-F1 model is a problem; a divergent high-F1 one just draws the drug boundary "
  f"differently."))
'''

S6 = ("## 6. Conclusion & scorecard — F1 per dollar\n\n"
      "The full scorecard and the design's payoff: the cheapest model whose accuracy is close to the best.")
S6_CODE = r'''
best_f1 = MS.f1.max()
elig = MS[MS.f1 >= best_f1 - 0.05]
pick = elig.sort_values("price").iloc[0] if elig.price.notna().any() else MS.sort_values("f1", ascending=False).iloc[0]
sc = MS.sort_values("f1", ascending=False)[["mshort","f1","precision","recall","outlier","mean_ext","price"]].copy()
sc["f1"] = sc["f1"].round(2)
for c in ["precision","recall"]: sc[c] = (sc[c]*100).round(0).astype("Int64").astype(str)+"%"
sc["outlier"] = sc["outlier"].round(2); sc["mean_ext"] = sc["mean_ext"].round(1)
sc["price"] = sc["price"].map(lambda v: f"${v:g}" if pd.notna(v) else "?")
sc.columns = ["model","F1","precision","recall","divergence","drugs/post","$/1M in"]
display(HTML("<b>② drug-ID — full scorecard</b>" + sc.to_html(index=False)))
lines = [
  f"- **Best F1:** {MS.sort_values('f1', ascending=False).iloc[0].mshort} ({best_f1:.2f}) — the accuracy anchor.",
  f"- **Best value (F1 per dollar):** **{pick.mshort}** — F1 {pick.f1:.2f} at ${pick.price:g}/1M input"
  + (", within 5 points of the best while cheaper." if pick.f1 < best_f1 else "."),
  f"- **Precision and recall trade off** — pick the end that matches the cost of a phantom vs a missed report; "
  f"for clustering, lean recall.",
  f"- **The objective floor over-credits** (string-present ≠ treatment), so Opus-as-judge is the standard "
  f"here, not the floor.",
]
display(Markdown("### Verdict\n\n" + "\n".join(lines)))
'''

S7 = '''## 7. Research limitations

- **The judge validation is weaker than ①.** RxNorm gave a clean external check on the alias judge; for ②
  the only objective anchor (string-in-post) is too loose, so we cannot cross-check Opus as tightly. A proper
  ② judge validation needs a second frontier model to review Opus's verdicts (the GT-review step, deferred).
- **Opus-as-truth is silver** — on genuinely ambiguous mentions ("an oral antibiotic", a drug named as a
  condition) it is a judgment, and it defines both the precision standard and the recall gold, so a
  systematic Opus blind spot would not show up here.
- **Posts** are 40 IRR-frame posts (100–800 chars); recall on longer, drug-denser posts may differ, and the
  frame excludes the corpus's long tail.
- **Price** is input $/1M and ignores output/latency — an order-of-magnitude signal.
- Measures the correctness of a measurement step, not any treatment effect.'''

PROV = r'''
import hashlib as _h
try: _sha = _h.sha256(open(r"__DB__","rb").read()).hexdigest()[:16]
except Exception: _sha = "n/a"
prov = pd.DataFrame({
  "item": ["run generated (UTC)","judgement","candidate models","judge (truth)","truth sources",
           "posts","temperature","skill version"],
  "value": [MAN["generated_utc"], MAN["judgement"], f'{len(CAND)} ({len(OK)} produced extractions)',
            MAN["judge_model"], ", ".join(MAN["truth_sources"]), MAN["n_posts"], MAN["temperature"],
            "research-assistant v2"],
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
        ("md", S6), ("code", S6_CODE),
        ("md", S7), ("code", PROV),
    ]
    nb = build_notebook(cells, db_path=DB, title="Judgement 2 — drug identification (roster)")
    html = execute_and_export(nb, "notebooks/validation/j2_drugid", timeout=1200)
    print("Wrote", html, "| prices:", len(prices))


if __name__ == "__main__":
    main()
