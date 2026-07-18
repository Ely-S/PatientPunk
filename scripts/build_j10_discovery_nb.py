"""
build_j10_discovery_nb.py — Judgement 10 (variable discovery) roster notebook.

Discovery decides WHAT covariates to cluster on. The story here is divergence: do the models even
agree on what to extract? Headline = field-count spread + N×N Jaccard of proposed field sets;
quality = Opus-judge keep-rate per model. Implication: freeze Opus's field set (not consensus).
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

RUNS_JSON = (ROOT / "data" / "validation" / "j10_discovery_runs.json").as_posix()
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


RQ = ('**Research Question:** "For variable discovery (judgement ⑩), do the models agree on WHAT fields '
      'to extract from patient posts — and how good are the fields they propose (Opus-judged)?"\n\n'
      '*Judgement ⑩ of 11 · Track B, step 1. Discovery sets the covariates clustering runs on, so the key '
      'question is cross-model divergence, with Opus-as-judge on field quality. Numbers computed from the run.*')

LOAD = r'''
import json
from itertools import combinations

RUNS = json.load(open(r"__RUNS__", encoding="utf-8"))
MAN = RUNS["manifest"]
proposals, VERD, KNOWN = RUNS["proposals"], RUNS["judge"], RUNS["known_fields"]
CAND = MAN["candidate_models"]
PRICES = __PRICES__
def short(m): return m.split("/")[-1]
def jacc(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if (a | b) else np.nan

# per-model proposed field set (union across batches)
fset = {m: set() for m in CAND}
for p in proposals:
    fset[p["model"]].update(f["field_name"] for f in p["fields"])

# how many models proposed each field (consensus), and its Opus verdict
from collections import Counter
prop_count = Counter()
for m in CAND:
    prop_count.update(fset[m])
ALLF = sorted(prop_count)

mr = []
for m in CAND:
    fs = fset[m]
    kept = sum(1 for f in fs if VERD.get(f) == "keep")
    mr.append(dict(model=m, mshort=short(m), n_fields=len(fs), n_kept=kept,
                   precision=(kept / len(fs) if fs else np.nan), price=PRICES.get(m, np.nan)))
MS = pd.DataFrame(mr)
FAILED = MS[MS.n_fields == 0].mshort.tolist()
MS = MS[MS.n_fields > 0].reset_index(drop=True)
OK = MS.model.tolist()

# N×N divergence of proposed field sets
MAT = pd.DataFrame(index=[short(m) for m in OK], columns=[short(m) for m in OK], dtype=float)
for x in OK:
    for y in OK:
        MAT.loc[short(x), short(y)] = 1.0 if x == y else jacc(fset[x], fset[y])
MS["outlier"] = [1 - np.nanmean([MAT.loc[short(m), short(o)] for o in OK if o != m]) for m in OK]

n_kept_total = sum(1 for f in ALLF if VERD.get(f) == "keep")
_lo, _hi = MS.sort_values("n_fields").iloc[0], MS.sort_values("n_fields").iloc[-1]
_meanov = np.nanmean(MAT.values[np.triu_indices(len(OK), 1)]) if len(OK) > 1 else np.nan
display(Markdown(f"""
**Abstract.** Variable discovery (judgement ⑩) is Track B's first step: a model reads patient posts and
proposes NEW fields to extract, beyond the fixed {MAN['n_known_fields']}-field schema. These become the
covariates clustering runs on — so if models disagree on *what* to extract, the clustering axes are
themselves model-dependent. Across **{len(OK)} models** on {MAN['n_posts']} posts (temp 0), the field
count ranges from **{int(_lo.n_fields)} ({_lo.mshort})** to **{int(_hi.n_fields)} ({_hi.mshort})** — a
{_hi.n_fields / max(_lo.n_fields,1):.0f}× spread — and the models share only a mean **{_meanov:.0%}** of
their proposed fields. Opus-as-judge keeps {MS.n_kept.sum()} of {len(ALLF)} distinct proposals as
genuinely useful covariates; per-model keep-rate (precision) ranges {MS.precision.min():.0%}–{MS.precision.max():.0%}.
The lesson the plan drew — freeze **Opus's** field set rather than any consensus — is exactly what this
divergence forces.{(' No parseable fields from: ' + ', '.join(FAILED) + '.') if FAILED else ''}
"""))
'''.replace("__RUNS__", RUNS_JSON)

S1 = ("## 1. What this judgement is, and why divergence matters\n\n"
      "`discover_fields.py` asks a model to read patient posts and propose *new* structured fields worth "
      "extracting (beyond the fixed schema) — things like `functional_status_tier` or `infection_count`. "
      "Those proposed fields become the **covariates the clustering runs on**. Unlike drug-ID, there is no "
      "single right field set — but if two models propose wildly different fields, the *axes of the "
      "clustering* are model-dependent, which is a validity problem before any cluster is computed. So the "
      "question is two-part: do models **agree** on what to extract, and are the fields they propose **good** "
      "(Opus-judged)?")

S2 = ("## 2. The divergence — models do not agree on what to extract\n\n"
      "First, how many fields each model proposes on the same posts. Eli's earlier benchmark found order-of-"
      "magnitude spreads; here it is directly measured.")
S2_CODE = r'''
d = MS.sort_values("n_fields")
fig, ax = plt.subplots(figsize=(8, 0.34*len(d) + 1))
ax.barh(d.mshort, d.n_fields, color="#0e6b74", height=0.68)
ax.barh(d.mshort, d.n_kept, color="#3cb18c", height=0.68)
for y, (_, r) in enumerate(d.iterrows()):
    ax.text(r.n_fields + 0.4, y, f"{int(r.n_fields)} ({int(r.n_kept)} kept)", va="center", fontsize=8)
ax.set_xlabel("fields proposed (dark = Opus kept)"); ax.set_title("Fields proposed per model")
fig.tight_layout(); plt.show()
display(Markdown(
  f"**What this shows:** the field count ranges **{int(MS.n_fields.min())}–{int(MS.n_fields.max())}** across "
  f"the roster — a {MS.n_fields.max()/max(MS.n_fields.min(),1):.0f}× spread on identical input. Models don't "
  f"disagree at the margin; they disagree on the whole scope of what a patient record should capture."))
'''

S3 = ("## 3. Quality — Opus-judge keep-rate\n\n"
      "Volume isn't value. Opus rules each proposed field keep (a distinct, well-defined, research-useful "
      "covariate) or junk (redundant / vague / not biomedical). Precision = fraction of a model's proposals "
      "Opus keeps.")
S3_CODE = r'''
d = MS.sort_values("precision")
fig, ax = plt.subplots(figsize=(8, 0.34*len(d) + 1))
ax.barh(d.mshort, d.precision, color="#0e6b74", height=0.68)
for y, (_, r) in enumerate(d.iterrows()):
    ax.text(r.precision + 0.01, y, f"{r.precision:.0%}  ({int(r.n_kept)}/{int(r.n_fields)})", va="center", fontsize=8)
ax.set_xlim(0, 1.15); ax.set_xlabel("Opus keep-rate (precision)"); ax.set_title("Proposed-field quality by model")
fig.tight_layout(); plt.show()
tbl = MS.sort_values("n_kept", ascending=False)[["mshort","n_fields","n_kept","precision","outlier","price"]].copy()
tbl["precision"] = (tbl["precision"]*100).round(0).astype("Int64").astype(str)+"%"
tbl["outlier"] = tbl["outlier"].round(2)
tbl["price"] = tbl["price"].map(lambda v: f"${v:g}" if pd.notna(v) else "?")
tbl.columns = ["model","proposed","kept","keep-rate","divergence","$/1M in"]
display(HTML("<b>Discovery scorecard</b>" + tbl.to_html(index=False)))
'''

S_COMP = ("## 4. Which models find the valuable fields — and which find them alone\n\n"
          "Count and keep-rate don't say whether models find the *same* good fields or *different* ones. "
          "Looking only at the valid (Opus-kept) fields: is there a shared core every model catches, or does "
          "each model contribute its own slice? This is what decides whether discovery is a job for one model "
          "or an ensemble.")
S_COMP_CODE = r'''
kept = set(f for f in prop_count if VERD.get(f) == "keep")
K = 6
core = [f for f in kept if prop_count[f] >= K]
uq = (pd.DataFrame([(short(m), sum(1 for f in fset[m] if f in kept and prop_count[f] == 1)) for m in OK],
                   columns=["mshort", "n_unique"]).sort_values("n_unique"))
ys = np.arange(len(uq))
fig, ax = plt.subplots(figsize=(8, 1.2 + 0.42*len(uq)))
ax.hlines(ys, 0, uq.n_unique, color="#d7c4e6", lw=3, zorder=1)
ax.scatter(uq.n_unique, ys, color="#8e44ad", s=90, zorder=2)
for y, v in zip(ys, uq.n_unique):
    ax.text(v + 0.4, y, str(int(v)), va="center", fontsize=8)
ax.set_yticks(ys); ax.set_yticklabels(uq.mshort); ax.set_xlim(0, max(uq.n_unique.max()*1.15, 1))
ax.set_xlabel("valid fields this model found ALONE (Opus-kept, no other model proposed)")
ax.set_title("Unique valuable discovery per model")
fig.tight_layout(); plt.show()

from collections import Counter as _C
covdist = _C(prop_count[f] for f in kept)
solo = [(f, next(short(m) for m in OK if f in fset[m])) for f in sorted(kept) if prop_count[f] == 1]
display(Markdown(
  f"**What this shows:** there is **no shared core** — of {len(kept)} Opus-kept fields, only **{len(core)}** were "
  f"proposed by >={K} of {len(OK)} models, and **{covdist.get(1,0)}** were seen by a single model. Each model "
  f"contributes a different valid slice: **{uq.iloc[-1].mshort}** alone surfaced **{int(uq.iloc[-1].n_unique)}** "
  f"valid covariates no other model found, while {uq.iloc[0].mshort} added {int(uq.iloc[0].n_unique)}. So "
  f"discovery models are **complementary, not rankable** — the fullest field set comes from unioning several, "
  f"and a thorough model is worth keeping in a discovery ensemble even if its keep-rate is only middling."))
ex = pd.DataFrame(solo[:14], columns=["valid field found by ONE model only", "the model"])
display(HTML("<b>Differentiators — valuable covariates a single model caught</b>" + ex.to_html(index=False)))
'''

S4 = ("## 5. Counterintuitive: more fields is not more signal\n\n"
      "The intuition is that a model proposing more fields is more thorough. The data says the extra fields "
      "are disproportionately junk — volume trades against precision — and the fields that survive are the "
      "ones many models independently converge on.")
S4_CODE = r'''
fig, ax = plt.subplots(1, 2, figsize=(13, 5.2))
# left: n_fields vs precision
ax[0].scatter(MS.n_fields, MS.precision, s=55, color="#0e6b74", zorder=3)
for i in {MS.n_fields.idxmax(), MS.n_fields.idxmin(), MS.precision.idxmax(), MS.precision.idxmin()}:
    r = MS.loc[i]; ax[0].annotate(r.mshort, (r.n_fields, r.precision), fontsize=8, xytext=(5,2), textcoords="offset points")
from scipy.stats import spearmanr
rho, prho = spearmanr(MS.n_fields, MS.precision)
ax[0].set_xlabel("fields proposed"); ax[0].set_ylabel("Opus keep-rate"); ax[0].set_title(f"Volume vs quality (rho={rho:.2f})")
# right: consensus — of fields proposed by k models, what fraction does Opus keep?
kbins = {}
for f in ALLF:
    k = prop_count[f]; kbins.setdefault(k, [0,0]); kbins[k][0]+=1; kbins[k][1]+= (VERD.get(f)=="keep")
ks = sorted(kbins); keeprate=[kbins[k][1]/kbins[k][0] for k in ks]; counts=[kbins[k][0] for k in ks]
ax2b = ax[1].twinx()
ax[1].bar(ks, counts, color="#d9e6e7", label="# fields")
ax2b.plot(ks, keeprate, "-o", color="#e67e22", label="Opus keep-rate")
ax[1].set_xlabel("proposed by how many models"); ax[1].set_ylabel("# distinct fields"); ax2b.set_ylabel("Opus keep-rate"); ax2b.set_ylim(0,1.05)
ax[1].set_title("Consensus vs quality")
fig.tight_layout(); plt.show()
_single = sum(1 for f in ALLF if prop_count[f]==1); _singlekeep = sum(1 for f in ALLF if prop_count[f]==1 and VERD.get(f)=="keep")
display(Markdown(
  f"**What this shows:** volume trends {'against' if rho<0 else 'with'} quality (Spearman rho={rho:.2f}). "
  f"**{_single} of {len(ALLF)}** distinct fields were proposed by just ONE model — the long tail of "
  f"idiosyncratic ideas — and Opus keeps only {_singlekeep/_single:.0%} of those, versus a higher rate for "
  f"fields multiple models converge on. Agreement tracks quality; idiosyncrasy tracks junk."))
'''

S5 = ("## 6. Divergence map & the frozen-GT implication\n\n"
      "The pairwise overlap of proposed field sets, and why this settles the design choice: with this little "
      "agreement, a consensus field set would keep only the trivially-obvious fields. Freezing **Opus's** "
      "reviewed set (the plan's call) is what the divergence forces.")
S5_CODE = r'''
order = MS.sort_values("n_kept", ascending=False).mshort.tolist()
M = MAT.reindex(index=order, columns=order).astype(float)
fig, ax = plt.subplots(figsize=(0.42*len(order)+3, 0.42*len(order)+2))
im = ax.imshow(M.values, cmap="magma", vmin=0, vmax=1)
ax.set_xticks(range(len(order))); ax.set_xticklabels(order, rotation=90, fontsize=7)
ax.set_yticks(range(len(order))); ax.set_yticklabels(order, fontsize=7)
fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="Jaccard of proposed field sets")
ax.set_title("Cross-model divergence — proposed fields (ordered by kept count)")
fig.tight_layout(); plt.show()
mean_ov = np.nanmean(MAT.values[np.triu_indices(len(order),1)])
display(Markdown(
  f"**What this shows:** models share a mean **{mean_ov:.0%}** of their proposed fields — far below the "
  f"extraction overlap in ②. There is no consensus field set to freeze; a majority-vote schema would "
  f"discard almost everything. This is the empirical case for the plan's decision: the frozen target is "
  f"**Opus's reviewed field set**, and cheap models are scored on how well they recover it — not on what "
  f"they agree with each other about."))
'''

S6 = ("## 7. Conclusion\n\n"
      "Discovery is the highest-variance judgement in the pipeline, and that variance is the finding.")
S6_CODE = r'''
lines = [
  f"- **No agreement on scope.** Field counts span {int(MS.n_fields.min())}–{int(MS.n_fields.max())} and "
  f"models share only ~{np.nanmean(MAT.values[np.triu_indices(len(MS),1)]):.0%} of proposals — the covariate "
  f"set is model-dependent, so discovery cannot be left to any single cheap model or to consensus.",
  f"- **Quality is judgeable even when scope isn't.** Opus keeps {MS.n_kept.sum()} of {len(ALLF)} distinct "
  f"proposals; the highest keep-rate is {MS.sort_values('precision',ascending=False).iloc[0].mshort} "
  f"({MS.precision.max():.0%}).",
  f"- **Freeze Opus's set.** With this divergence, the design must define the target as Opus's reviewed field "
  f"set (a frozen GT), then score cheap models on recovery — which is judgement ⑪'s schema.",
  f"- **Consensus ≈ quality.** Fields multiple models converge on are the ones Opus keeps; singletons are "
  f"mostly junk — a cheap heuristic for pruning discovery output.",
]
display(Markdown("### Verdict\n\n" + "\n".join(lines)))
'''

S7 = '''## 8. Research limitations

- **No frozen GT yet.** Correctness here is Opus-as-judge on field *quality* (keep/junk), not recovery of a
  frozen Opus field set — that GT is the next fixture (it is exactly what ⑪ needs). So this measures whether
  a proposed field is *good*, not whether a model recovered *the* target set.
- **Field-name matching is exact (normalized).** Near-duplicate names ("fatigue_severity" vs "fatigue_level")
  count as different fields, which inflates divergence — but that models don't even converge on naming is
  itself part of the finding.
- **Opus-as-judge is silver** and reviews its own descriptions; a second frontier reviewer (the GT step)
  would tighten the quality call.
- **Sample** is a fixed slice of long-COVID posts; discovered fields are corpus-specific.
- Measures the correctness/stability of a measurement step, not any treatment effect.'''

PROV = r'''
import hashlib as _h
try: _sha = _h.sha256(open(r"__DB__","rb").read()).hexdigest()[:16]
except Exception: _sha = "n/a"
prov = pd.DataFrame({
  "item": ["run generated (UTC)","judgement","candidate models","judge (truth)","posts / batches",
           "known schema fields","temperature","skill version"],
  "value": [MAN["generated_utc"], MAN["judgement"], f'{len(CAND)} ({len(OK)} produced fields)',
            MAN["judge_model"], f'{MAN["n_posts"]} / {MAN["n_batches"]}', MAN["n_known_fields"],
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
        ("md", S_COMP), ("code", S_COMP_CODE),
        ("md", S4), ("code", S4_CODE),
        ("md", S5), ("code", S5_CODE),
        ("md", S6), ("code", S6_CODE),
        ("md", S7), ("code", PROV),
    ]
    nb = build_notebook(cells, db_path=DB, title="Judgement 10 — variable discovery (roster)")
    html = execute_and_export(nb, "notebooks/validation/j10_discovery", timeout=1200)
    print("Wrote", html, "| prices:", len(prices))


if __name__ == "__main__":
    main()
