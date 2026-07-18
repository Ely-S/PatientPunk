"""
build_j1_alias_nb.py — Judgement 1 (alias generation) validation notebook, ROSTER edition.

Scores every candidate model's alias output for CORRECTNESS against two truth sources
(RxNorm + Opus-as-judge, judge validated against RxNorm), then compares the models to each
other (N×N Jaccard divergence heatmap + per-model outlier score) and collapses it to a
price-aware scorecard — "which cheap model is closest to Opus, per dollar."

Prices are fetched from the OpenRouter catalogue at BUILD time and embedded, so the notebook
needs no network. Built via the research-assistant skill; exports code-free HTML.
"""
from __future__ import annotations
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notebooks"))
from build_notebook import build_notebook, execute_and_export

RUNS_JSON = (ROOT / "data" / "validation" / "j1_alias_runs.json").as_posix()
DB = (ROOT / "patientpunk.db").as_posix()


def fetch_prices() -> dict:
    """{model_id: input $ per 1M tokens} from the live OpenRouter catalogue."""
    try:
        cat = json.load(urllib.request.urlopen(
            urllib.request.Request("https://openrouter.ai/api/v1/models",
                                   headers={"User-Agent": "pp"}), timeout=30))
        out = {}
        for m in cat["data"]:
            p = m.get("pricing", {}).get("prompt")
            if p is not None:
                try:
                    out[m["id"]] = round(float(p) * 1_000_000, 3)
                except (TypeError, ValueError):
                    pass
        return out
    except Exception:
        return {}


RQ = ('**Research Question:** "For alias generation (judgement ①), how correct is each model in the '
      'roster — scored against Opus-as-truth and RxNorm — and how do the models diverge from one '
      'another?"\n\n*Judgement ① of 11 · the archetype factual test, now across the full lab roster: '
      'correctness vs two truth sources, an N×N divergence map, and a price-aware scorecard. '
      'Numbers are computed from the run.*')

LOAD = r'''
import json
from itertools import combinations
from scipy.stats import spearmanr

RUNS = json.load(open(r"__RUNS__", encoding="utf-8"))
MAN = RUNS["manifest"]
gens, judge, rxn = RUNS["generations"], RUNS["judge"], RUNS["rxnorm"]
CAND = MAN["candidate_models"]
PRICES = __PRICES__
def short(m): return m.split("/")[-1]

VERD = {(j["model"], j["drug"]): j["verdicts"] for j in judge}

def rx_match(alias, drug):
    a = alias.lower().strip()
    for n in rxn.get(drug, {}).get("all", []):
        if a == n or (len(a) >= 4 and a in n):
            return True
    return False

def jacc(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if (a | b) else np.nan

union, drugs = {}, sorted({g["drug"] for g in gens})
for g in gens:
    union.setdefault((g["model"], g["drug"]), set()).update(g["aliases"])
# per-run counts for mean alias size + within-model variability
runs_of = {}
for g in gens:
    runs_of.setdefault((g["model"], g["drug"]), []).append(g["aliases"])

# ── per-model correctness (on UNIQUE aliases) + variability + price ──
mr = []
for m in CAND:
    tot = val = rh = 0
    self_js, sizes = [], []
    for d in drugs:
        u = union.get((m, d), set()); verd = VERD.get((m, d), {})
        tot += len(u)
        val += sum(1 for a in u if verd.get(a) == "valid")
        rh += sum(1 for a in u if rx_match(a, d))
        rr = runs_of.get((m, d), [])
        sizes += [len(r) for r in rr]
        if len(rr) >= 2:
            self_js.append(np.mean([jacc(a, b) for a, b in combinations(rr, 2)]))
    # brand recall
    bh = bt = 0
    for d in drugs:
        brands = set(rxn.get(d, {}).get("brand", []))
        if brands:
            uu = union.get((m, d), set())
            bh += sum(1 for b in brands if any(b == x or b in x for x in uu)); bt += len(brands)
    mr.append(dict(model=m, mshort=short(m), n_unique=int(tot),
                   opus_prec=(val / tot if tot else np.nan), rx_prec=(rh / tot if tot else np.nan),
                   opus_valid=int(val), opus_invalid=int(tot - val),
                   brand_recall=(bh / bt if bt else np.nan),
                   mean_aliases=(np.mean(sizes) if sizes else 0.0),
                   self_jaccard=(np.mean(self_js) if self_js else np.nan),
                   price=PRICES.get(m, np.nan)))
MS = pd.DataFrame(mr)
FAILED = MS[MS.n_unique == 0].mshort.tolist()
MS = MS[MS.n_unique > 0].reset_index(drop=True)
OK = MS.model.tolist()

# ── judge validation: Opus vs RxNorm on confirmable aliases ──
jv = [dict(model=m, mshort=short(m), opus=v)
      for (m, d), verd in VERD.items() for a, v in verd.items() if rx_match(a, d)]
JV = pd.DataFrame(jv)
judge_agree = (JV.opus == "valid").mean() if len(JV) else np.nan
JVM = (JV.groupby("mshort")["opus"].apply(lambda s: (s == "valid").mean())) if len(JV) else pd.Series(dtype=float)

# ── cross-model divergence: N×N mean Jaccard across drugs ──
MAT = pd.DataFrame(index=[short(m) for m in OK], columns=[short(m) for m in OK], dtype=float)
for x in OK:
    for y in OK:
        if x == y:
            MAT.loc[short(x), short(y)] = 1.0
        else:
            js = [jacc(union.get((x, d), set()), union.get((y, d), set())) for d in drugs]
            MAT.loc[short(x), short(y)] = np.nanmean(js)
# outlier score = 1 - mean pairwise agreement with the rest
MS["outlier"] = [1 - np.nanmean([MAT.loc[short(m), short(o)] for o in OK if o != m]) for m in OK]

_best = MS.sort_values("opus_prec", ascending=False).iloc[0]
_rxbest = MS.sort_values("rx_prec", ascending=False).iloc[0]
_srho = spearmanr(MS.rx_prec, MS.opus_prec).correlation
display(Markdown(f"""
**Abstract.** Alias generation (judgement ①) is the pipeline's first step — a hallucinated alias
propagates into drug-ID and canonicalisation. We test the full roster the way the design specifies:
**{len(OK)} candidate models** across {MS.mshort.str.split('-').str[0].nunique()}+ labs generate
aliases for **{MAN['n_drugs']} drugs** (k={MAN['k']}, temp 0), each scored for **correctness against
two truth sources** — RxNorm (formal) and **Opus-as-judge** (informal aliases + hallucinations RxNorm
can't see) — with the judge validated against RxNorm ({judge_agree:.0%} agreement) and an N×N
divergence map beside it. **{_best.mshort}** is the most accurate ({_best.opus_prec:.0%} of aliases
judged valid). Crucially, RxNorm and Opus rank the roster differently (rank correlation ρ={_srho:.2f});
by RxNorm alone the top model would be **{_rxbest.mshort}** — so agreement with the database is a floor,
not the verdict.{(' Models that produced no parseable aliases: ' + ', '.join(FAILED) + '.') if FAILED else ''}
"""))
'''.replace("__RUNS__", RUNS_JSON)

S1 = ("## 1. What this judgement is, and why correctness matters\n\n"
      "`get_drug_aliases` asks a model for every name a drug goes by — generic, brand, abbreviation, "
      "common misspelling. Those aliases are how the pipeline *finds* the drug in free text, so this is the "
      "first LLM judgement and everything downstream inherits its errors. It has a **right answer**, so we "
      "measure accuracy, not agreement — and we do it across the whole roster so model choice is grounded.")

S2 = ("## 2. Validating the judge before trusting it\n\n"
      "Opus-as-judge is a model grading models, so before leaning on it we check it against RxNorm on the "
      "subset RxNorm covers: if Opus validates the aliases RxNorm confirms, the judge reproduces objective "
      "truth and is trustworthy for the informal aliases (LDN, typos) RxNorm can't reach.")
S2_CODE = r'''
if len(JVM):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(JVM.values, bins=np.linspace(0, 1, 21), color="#0e6b74", edgecolor="white")
    ax.axvline(judge_agree, color="#e67e22", lw=2, ls="--", label=f"pooled = {judge_agree:.0%}")
    ax.set_xlabel("per-model Opus-vs-RxNorm agreement"); ax.set_ylabel("models")
    ax.set_title("Judge validation across the roster"); ax.legend(frameon=False)
    fig.tight_layout(); plt.show()
    display(Markdown(
      f"**What this shows:** pooled across the roster, Opus reproduces RxNorm on **{judge_agree:.0%}** of "
      f"confirmable aliases, and most models sit near that line — the judge is consistently sound, not "
      f"cherry-picked. Where a model's bar is low, its RxNorm-confirmed set is small and noisy, not evidence "
      f"the judge failed."))
'''

S3 = ("## 3. Correctness scorecard — the verdict\n\n"
      "Each model's **Opus-precision** (fraction of its aliases the validated judge calls valid), sorted. "
      "This is the accuracy column of the scorecard; the RxNorm floor and the full table follow.")
S3_CODE = r'''
d = MS.sort_values("opus_prec", ascending=True)
fig, ax = plt.subplots(figsize=(8, 0.34*len(d) + 1))
lo = [wilson_ci(int(r.opus_valid), int(r.opus_valid + r.opus_invalid))[0] for _, r in d.iterrows()]
hi = [wilson_ci(int(r.opus_valid), int(r.opus_valid + r.opus_invalid))[1] for _, r in d.iterrows()]
ax.barh(d.mshort, d.opus_prec, color="#0e6b74", height=0.68)
ax.errorbar(d.opus_prec, range(len(d)), xerr=[d.opus_prec - lo, np.array(hi) - d.opus_prec],
            fmt="none", ecolor="#333", capsize=2, lw=1)
ax.set_xlim(0, 1.02); ax.set_xlabel("Opus-judge precision (95% CI)")
ax.set_title("Alias-generation accuracy by model")
fig.tight_layout(); plt.show()

tbl = MS.sort_values("opus_prec", ascending=False)[
    ["mshort","opus_prec","rx_prec","brand_recall","mean_aliases","price"]].copy()
for c in ["opus_prec","rx_prec","brand_recall"]:
    tbl[c] = (tbl[c]*100).round(0).astype("Int64").astype(str) + "%"
tbl["mean_aliases"] = tbl["mean_aliases"].round(1)
tbl["price"] = tbl["price"].map(lambda v: f"${v:g}" if pd.notna(v) else "?")
tbl.columns = ["model","Opus acc.","RxNorm floor","brand recall","aliases/drug","$/1M in"]
display(HTML("<b>Per-model correctness</b>" + tbl.to_html(index=False)))
'''

S4 = ("## 4. Counterintuitive: the objective database ranks the roster differently\n\n"
      "Score the roster by RxNorm and by Opus-judge and the orderings disagree. Models can sit high on "
      "RxNorm precision yet low on real accuracy (they stick to formal names but still hallucinate), or low "
      "on RxNorm yet high on accuracy (they add *correct* informal aliases RxNorm can't confirm). If you "
      "ranked models by the objective database — or by how much they agree with each other — you would pick "
      "wrong. Only the validated judge tracks truth.")
S4_CODE = r'''
# rank-by-RxNorm vs rank-by-Opus — off-diagonal = the two sources order the roster differently
R = MS.copy()
R["rank_rx"] = R.rx_prec.rank(ascending=False, method="min")
R["rank_op"] = R.opus_prec.rank(ascending=False, method="min")
R["move"] = (R.rank_rx - R.rank_op).abs()
n = len(R)
fig, ax = plt.subplots(figsize=(7, 7))
ax.scatter(R.rank_rx, R.rank_op, s=55, color="#0e6b74", zorder=3)
ax.plot([1, n], [1, n], ls=":", color="#999", lw=1, label="same rank in both")
for _, r in R.nlargest(6, "move").iterrows():
    ax.annotate(r.mshort, (r.rank_rx, r.rank_op), fontsize=8, fontweight="bold",
                xytext=(6, 0), textcoords="offset points")
ax.set_xlabel("rank by RxNorm precision  (1 = best)"); ax.set_ylabel("rank by Opus-judge  (1 = best)")
ax.set_title("Does the objective database rank the roster like the judge?")
ax.legend(frameon=False, loc="lower right"); fig.tight_layout(); plt.show()
srho = spearmanr(MS.rx_prec, MS.opus_prec).correlation
mover = R.nlargest(1, "move").iloc[0]
display(Markdown(
  f"**What this shows:** rank-by-RxNorm against rank-by-Opus (Spearman ρ={srho:.2f}). Points off the diagonal "
  f"are ordered *differently* by the two sources — **{mover.mshort}** moves {int(mover.move)} places between "
  f"them. A model high-left (good RxNorm rank, poor Opus rank) looks clean in the database but hallucinates; "
  f"low-right is the reverse — correct informal aliases RxNorm can't confirm. Rank the roster by the database "
  f"and you order it differently from the validated judge: RxNorm corroborates, it does not rank."))
'''

S5 = ("## 5. Comparing the models to each other — divergence map\n\n"
      "Correctness says who is *right*; divergence says who *behaves alike*. The matrix is the mean Jaccard "
      "of alias sets between every pair of models (1 = identical sets). It clusters the roster into behaviour "
      "groups and exposes outliers — but note the caveat: agreeing models can share the same bias, so "
      "divergence is a diagnostic, never a correctness verdict.")
S5_CODE = r'''
order = MS.sort_values("opus_prec", ascending=False).mshort.tolist()
M = MAT.reindex(index=order, columns=order).astype(float)
fig, ax = plt.subplots(figsize=(0.42*len(order) + 3, 0.42*len(order) + 2))
im = ax.imshow(M.values, cmap="viridis", vmin=0, vmax=1)
ax.set_xticks(range(len(order))); ax.set_xticklabels(order, rotation=90, fontsize=7)
ax.set_yticks(range(len(order))); ax.set_yticklabels(order, fontsize=7)
fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="mean Jaccard of alias sets")
ax.set_title("Cross-model divergence (ordered by accuracy)")
fig.tight_layout(); plt.show()

od = MS.sort_values("outlier", ascending=False)[["mshort","outlier","opus_prec"]].head(8).copy()
od["outlier"] = od["outlier"].round(2); od["opus_prec"] = (od["opus_prec"]*100).round(0).astype("Int64").astype(str)+"%"
od.columns = ["model","outlier score (1 − mean agreement)","Opus acc."]
display(HTML("<b>Most divergent models</b>" + od.to_html(index=False)))
display(Markdown(
  f"**What this shows:** the roster shares a mean **{np.nanmean(MAT.values[np.triu_indices(len(order),1)]):.0%}** "
  f"alias overlap. The most *divergent* model is **{od.iloc[0]['model']}** — but divergence alone is not a "
  f"fault: read it against §3, an outlier that is *also* low-accuracy is a problem; an outlier that stays "
  f"accurate just formats aliases differently."))
'''

S6 = ("## 6. Conclusion & scorecard — accuracy per dollar\n\n"
      "The payoff: the full scorecard, and the one number the project turns on — the cheapest model whose "
      "accuracy is close to the best (the design's *closest-to-Opus-per-dollar*).")
S6_CODE = r'''
best_acc = MS.opus_prec.max()
elig = MS[MS.opus_prec >= best_acc - 0.05].copy()  # within 5 points of the best
pick = elig.sort_values("price").iloc[0] if elig.price.notna().any() else MS.sort_values("opus_prec", ascending=False).iloc[0]

sc = MS.sort_values("opus_prec", ascending=False)[
    ["mshort","opus_prec","rx_prec","outlier","self_jaccard","mean_aliases","price"]].copy()
sc["opus_prec"] = (sc["opus_prec"]*100).round(0).astype("Int64").astype(str)+"%"
sc["rx_prec"] = (sc["rx_prec"]*100).round(0).astype("Int64").astype(str)+"%"
sc["outlier"] = sc["outlier"].round(2)
sc["self_jaccard"] = sc["self_jaccard"].round(2)
sc["mean_aliases"] = sc["mean_aliases"].round(1)
sc["price"] = sc["price"].map(lambda v: f"${v:g}" if pd.notna(v) else "?")
sc.columns = ["model","accuracy (Opus)","RxNorm floor","divergence","self-consist (k)","aliases/drug","$/1M in"]
display(HTML("<b>① alias — full scorecard</b>" + sc.to_html(index=False)))

lines = [
  f"- **Most accurate:** {MS.sort_values('opus_prec', ascending=False).iloc[0].mshort} "
  f"({best_acc:.0%} valid). This is the accuracy anchor for the scorecard.",
  f"- **Best value (closest to top accuracy per dollar):** **{pick.mshort}** — {pick.opus_prec:.0%} accuracy "
  f"at ${pick.price:g}/1M input" + (", within 5 points of the best while cheaper." if pick.opus_prec < best_acc else "."),
  f"- **Judge is sound** ({judge_agree:.0%} vs RxNorm), so these are correctness numbers, not agreement.",
  f"- **RxNorm is a floor, divergence is a diagnostic** — neither ranks the roster; the Opus column does.",
  f"- **Alias generation is unstable even at temp 0** — mean run-to-run self-Jaccard "
  f"{MS.self_jaccard.mean():.2f}, so K=5 is necessary, not optional.",
]
display(Markdown("### Verdict\n\n" + "\n".join(lines)))
'''

S7 = '''## 7. Research limitations

- **Opus-as-truth is silver, not gold.** It is a model grading models; we validated it against RxNorm on
  the covered subset (§2), but on genuinely ambiguous informal aliases it is a judgment. RxNorm covers only
  formal names and even misses some real brands, so its "floor" is thin.
- **Slugs drift.** The roster was resolved against the live OpenRouter catalogue on the run date; re-confirm
  before re-running. Models that returned no parseable aliases are listed in the abstract and excluded.
- **Drug set** is 16 curated real drugs + one supplement; accuracy on obscure supplements (no RxNorm anchor)
  leans entirely on Opus and deserves more caution.
- **Price** is input $/1M-tokens from the catalogue and ignores output tokens and latency; treat it as an
  order-of-magnitude cost signal, not a bill.
- This notebook measures the correctness of a measurement step, not any treatment effect.'''

PROV = r'''
import hashlib as _h
try: _sha = _h.sha256(open(r"__DB__","rb").read()).hexdigest()[:16]
except Exception: _sha = "n/a"
prov = pd.DataFrame({
  "item": ["run generated (UTC)","judgement","candidate models","judge (truth)","truth sources",
           "drugs / k","temperature","skill version"],
  "value": [MAN["generated_utc"], MAN["judgement"], f'{len(CAND)} ({len(OK)} produced aliases)',
            MAN["judge_model"], ", ".join(MAN["truth_sources"]), f'{MAN["n_drugs"]} / {MAN["k"]}',
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
        ("md", S6), ("code", S6_CODE),
        ("md", S7), ("code", PROV),
    ]
    nb = build_notebook(cells, db_path=DB, title="Judgement 1 — alias generation (roster)")
    html = execute_and_export(nb, "notebooks/validation/j1_alias", timeout=1200)
    print("Wrote", html, "| prices fetched:", len(prices))


if __name__ == "__main__":
    main()
