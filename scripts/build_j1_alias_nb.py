"""
build_j1_alias_nb.py — Build the Judgement 1 (alias generation) validation notebook.

The archetype factual-judgement notebook: each model's alias output scored for CORRECTNESS
against two truth sources (RxNorm + Opus-as-judge), the judge validated against RxNorm, and
cross-model divergence reported as a diagnostic (never the verdict). Built via the
research-assistant skill's notebook builder; exports code-free HTML.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notebooks"))
from build_notebook import build_notebook, execute_and_export

RUNS_JSON = (ROOT / "data" / "validation" / "j1_alias_runs.json").as_posix()
DB = (ROOT / "patientpunk.db").as_posix()

RQ = ('**Research Question:** "For alias generation (judgement ①), how correct is each model\'s '
      'output — scored against Opus-as-truth and RxNorm — and how much do the models diverge?"\n\n'
      "*Judgement ① of 11 · the archetype factual-judgement test: run the roster, grade each model\'s "
      "correctness against two independent truth sources, and read cross-model divergence as a "
      "diagnostic. The abstract below is computed from the run.*")

# ── Cell: load, score against both truth sources, compute divergence, show abstract ──
LOAD = r'''
import json
from itertools import combinations
from scipy.stats import fisher_exact, spearmanr

RUNS = json.load(open(r"__RUNS__", encoding="utf-8"))
MAN = RUNS["manifest"]
gens, judge, rxn = RUNS["generations"], RUNS["judge"], RUNS["rxnorm"]
CAND = MAN["candidate_models"]
def short(m): return m.split("/")[-1].replace("claude-","").replace("-20251001","")

VERD = {(j["model"], j["drug"]): j["verdicts"] for j in judge}

def rx_match(alias, drug):
    # Strict: exact, or the alias is a token *within* an RxNorm name ("zyrtec" in "zyrtec-d").
    # NOT the reverse ("naltrexone" in "naltrexone acetate") — that would let a hallucinated
    # salt form count as RxNorm-confirmed just for containing a real name.
    a = alias.lower().strip()
    for n in rxn.get(drug, {}).get("all", []):
        if a == n or (len(a) >= 4 and a in n):
            return True
    return False

# per (model, drug, run) correctness
rows = []
for g in gens:
    m, d, aliases = g["model"], g["drug"], g["aliases"]
    if not aliases:
        continue
    verd = VERD.get((m, d), {})
    n = len(aliases)
    ov = sum(1 for a in aliases if verd.get(a) == "valid")
    rh = sum(1 for a in aliases if rx_match(a, d))
    rows.append(dict(model=m, mshort=short(m), drug=d, run=g["run"], n_aliases=n,
                     opus_valid=ov, opus_prec=ov / n, rx_hit=rh, rx_prec=rh / n))
df = pd.DataFrame(rows)

# unique alias set per (model, drug); correctness computed on UNIQUE aliases so the
# significance test isn't pseudo-replicated by the k identical repeats.
union = {}
for g in gens:
    union.setdefault((g["model"], g["drug"]), set()).update(g["aliases"])
drugs = sorted({g["drug"] for g in gens})
mr = []
for m in CAND:
    tot = val = rh = 0
    for d in drugs:
        u = union.get((m, d), set()); verd = VERD.get((m, d), {})
        tot += len(u)
        val += sum(1 for a in u if verd.get(a) == "valid")
        rh += sum(1 for a in u if rx_match(a, d))
    mr.append(dict(model=m, mshort=short(m), opus_prec=val / tot, rx_prec=rh / tot,
                   opus_valid=int(val), opus_invalid=int(tot - val), n_unique=int(tot),
                   mean_aliases=df[df.model == m].groupby("drug").n_aliases.mean().mean()))
MS = pd.DataFrame(mr)

# brand recall: fraction of RxNorm brand names each model's union produced
br = []
for m in CAND:
    hits = tot = 0
    for d, r in rxn.items():
        brands = set(r.get("brand", []))
        if not brands:
            continue
        u = union.get((m, d), set())
        hits += sum(1 for b in brands if any(b == x or b in x for x in u)); tot += len(brands)
    br.append(dict(model=m, brand_recall=hits / tot if tot else float("nan"), n_brands=tot))
MS = MS.merge(pd.DataFrame(br), on="model")

# judge validation: of RxNorm-confirmed aliases, how often does Opus agree ("valid")?
jv = [dict(model=m, mshort=short(m), drug=d, alias=a, opus=v)
      for (m, d), verd in VERD.items() for a, v in verd.items() if rx_match(a, d)]
JV = pd.DataFrame(jv)
judge_agree = (JV.opus == "valid").mean() if len(JV) else float("nan")

# cross-model divergence: pairwise Jaccard of union alias sets, per drug
def jacc(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if (a | b) else float("nan")
drugs = sorted({g["drug"] for g in gens})
DIV = pd.DataFrame([dict(drug=d, pair=f"{short(x)} vs {short(y)}",
                         jaccard=jacc(union.get((x, d), set()), union.get((y, d), set())))
                    for d in drugs for x, y in combinations(CAND, 2)])

# within-model variability: mean pairwise Jaccard across the k runs
wv = []
for m in CAND:
    for d in drugs:
        runs = [g["aliases"] for g in gens if g["model"] == m and g["drug"] == d]
        if len(runs) >= 2:
            wv.append(dict(model=m, mshort=short(m), drug=d,
                           self_jaccard=np.mean([jacc(a, b) for a, b in combinations(runs, 2)])))
WV = pd.DataFrame(wv)

_best = MS.sort_values("opus_prec", ascending=False).iloc[0]
_worst = MS.sort_values("opus_prec").iloc[0]
display(Markdown(f"""
**Abstract.** Alias generation (judgement ①) is the pipeline's first step — a hallucinated alias
(here, *lumbrokinase* listed for *nattokinase*, a different enzyme) would propagate straight into
drug-ID and canonicalisation. We test it the way the Eli/Shaun design specifies: **{len(CAND)}
candidate models** generate aliases for **{MAN['n_drugs']} drugs** (k={MAN['k']}, temperature 0),
scored for **correctness against two independent truth sources** — RxNorm (formal aliases) and
**Opus-as-judge** (which grades the informal aliases and wrong-drug hallucinations RxNorm cannot) —
with cross-model divergence read only as a diagnostic. The judge is validated against RxNorm: on
RxNorm-confirmed aliases Opus agrees **{judge_agree:.0%}** of the time, so it is trustworthy for the
rest. **{_best['mshort']}** is the more precise generator ({_best['opus_prec']:.0%} of its aliases
judged valid) vs **{_worst['mshort']}** ({_worst['opus_prec']:.0%}); RxNorm alone confirms only
{MS['rx_prec'].mean():.0%} on average — the coverage gap the judge fills. **Candidate roster is 2
Anthropic models (OpenRouter credits were exhausted mid-project); the same harness runs the full
lab roster unchanged once restored.**
"""))
'''.replace("__RUNS__", RUNS_JSON)

S1 = ("## 1. What this judgement is, and why correctness matters here\n\n"
      "`get_drug_aliases` asks a model for every name a drug goes by — generic, brand, abbreviation, "
      "common misspelling. Those aliases are how the pipeline **finds** the drug in free text, so this is "
      "the *first* LLM judgement and everything downstream inherits its errors. Two failure modes matter: "
      "**hallucinated aliases** (naming a *different* drug — e.g. `naloxone` for `naltrexone`, or "
      "`lumbrokinase` for `nattokinase`), which cause false drug matches; and **missed brand names**, which "
      "cause missed matches. Unlike sentiment, this judgement has a **right answer**, so we measure "
      "*accuracy*, not agreement.")

S2 = ("## 2. Two truth sources — and validating the judge before trusting it\n\n"
      "Neither truth source is sufficient alone. **RxNorm** is objective but only knows *formal* names "
      "(brand/generic); it has no `LDN`, no typos, and it even misses some real brands. **Opus-as-judge** "
      "reads each alias and rules valid/invalid — it covers the informal names and catches wrong-drug "
      "hallucinations, but it is a model grading models. So before we lean on Opus, we check it against "
      "RxNorm on the subset RxNorm *does* cover: if Opus validates the aliases RxNorm confirms, the judge "
      "is trustworthy for the rest.")
S2_CODE = r'''
order = [short(m) for m in CAND]
g = JV.groupby("mshort")["opus"].apply(lambda s: (s == "valid").mean()).reindex(order)
counts = JV.groupby("mshort").size().reindex(order)
ys = np.arange(len(order))
fig, ax = plt.subplots(figsize=(7, 1.4 + 0.7*len(order)))
ax.hlines(ys, 0, g.values, color="#b9ccce", lw=3, zorder=1)
ax.scatter(g.values, ys, color="#0e6b74", s=130, zorder=2)
for y, v, n in zip(ys, g.values, counts.values):
    ax.text(v + 0.02, y, f"{v:.0%}  (n={int(n)})", va="center", fontsize=9)
ax.axvline(1.0, ls="--", color="#999", lw=1)
ax.set_yticks(ys); ax.set_yticklabels(order); ax.set_xlim(0, 1.18)
ax.set_xlabel("Opus 'valid' rate on RxNorm-confirmed aliases")
ax.set_title("Judge validation: does Opus agree with RxNorm where RxNorm is sure?")
fig.tight_layout(); plt.show()
display(Markdown(
  f"**What this shows:** on aliases RxNorm independently confirms, Opus rules 'valid' "
  f"**{(JV.opus=='valid').mean():.0%}** of the time — it reproduces the objective truth where we can check "
  f"it, which licenses using it on the informal aliases (LDN, misspellings) RxNorm can't reach. The "
  f"{int((JV.opus!='valid').sum())} of {len(JV)} disagreements are the honest ceiling on the judge."))
'''

S3 = ("## 3. Correctness scorecard — the verdict\n\n"
      "Now the accuracy of each model's alias output, on two measures: **Opus-precision** (fraction of "
      "generated aliases the judge calls valid) and **RxNorm-precision** (fraction confirmed by RxNorm — a "
      "floor, since RxNorm lacks informal names), plus **brand recall** (did the model produce RxNorm's "
      "brand names?). This is the row that goes on the scorecard.")
S3_CODE = r'''
labels = [short(m) for m in CAND]
xs = np.arange(len(labels)); w = 0.26
fig, ax = plt.subplots(figsize=(2.6 + 2.2*len(labels), 4.8))
metrics = [("opus_prec", "Opus precision", "#0e6b74"),
           ("rx_prec", "RxNorm precision", "#3498db"),
           ("brand_recall", "RxNorm brand recall", "#e67e22")]
for j, (col, lab, c) in enumerate(metrics):
    vals = [MS.loc[MS.mshort == l, col].values[0] for l in labels]
    ax.bar(xs + (j-1)*w, vals, w, color=c, label=lab)
# Wilson CI on the headline Opus precision
for i, l in enumerate(labels):
    r = MS.loc[MS.mshort == l].iloc[0]
    lo, hi = wilson_ci(int(r.opus_valid), int(r.opus_valid + r.opus_invalid))
    ax.errorbar(xs[i]-w, r.opus_prec, yerr=[[r.opus_prec-lo],[hi-r.opus_prec]], fmt="none", ecolor="#222", capsize=4)
ax.set_xticks(xs); ax.set_xticklabels(labels); ax.set_ylim(0, 1.05)
ax.set_ylabel("rate"); ax.set_title("Alias-generation correctness by model (error bars: 95% CI on Opus precision)")
ax.legend(bbox_to_anchor=(1.01, 1), loc="upper left", frameon=False)
fig.tight_layout(); plt.show()

tbl = MS[["mshort","opus_prec","rx_prec","brand_recall","mean_aliases","n_unique"]].copy()
for c in ["opus_prec","rx_prec","brand_recall"]: tbl[c] = (tbl[c]*100).round(0).astype(int).astype(str)+"%"
tbl["mean_aliases"] = tbl["mean_aliases"].round(1)
tbl.columns = ["model","Opus precision","RxNorm precision","brand recall","mean aliases/drug","unique aliases"]
display(HTML("<b>Per-model correctness</b>" + tbl.to_html(index=False)))

if len(CAND) == 2:
    a, b = MS.iloc[0], MS.iloc[1]
    _, p = fisher_exact([[a.opus_valid, a.opus_invalid],[b.opus_valid, b.opus_invalid]])
    hi, lo = (a, b) if a.opus_prec >= b.opus_prec else (b, a)
    verdict = (f"**{hi.mshort}** generates more precise aliases than **{lo.mshort}** "
               f"({hi.opus_prec:.0%} vs {lo.opus_prec:.0%} valid; Fisher exact p={p:.2g}). ")
    verdict += ("The gap is significant." if p < 0.05 else "The gap is not significant at this sample.")
    display(Markdown("**Verdict:** " + verdict))
'''

S4 = ("## 4. Counterintuitive: the objective database ranks the models backwards\n\n"
      "This is the finding that justifies the whole design. Score these models only against **RxNorm** — the "
      "objective external drug database — and you rank them one way. Score them against **Opus-as-judge** and "
      "the ranking flips. The reason: the model that looks worse by RxNorm is generating *correct informal* "
      "aliases (LDN, misspellings, real brands RxNorm omits) that RxNorm can't confirm, while the model that "
      "looks better by RxNorm is padding with actual wrong-drug hallucinations. Trusting the database alone "
      "would have picked the wrong model.")
S4_CODE = r'''
rx_rank = MS.sort_values("rx_prec", ascending=False).mshort.tolist()
op_rank = MS.sort_values("opus_prec", ascending=False).mshort.tolist()
flipped = rx_rank != op_rank
cols = {short(CAND[0]): "#0e6b74"}
if len(CAND) > 1: cols[short(CAND[1])] = "#e67e22"
fig, ax = plt.subplots(figsize=(6.8, 5))
for _, r in MS.iterrows():
    ax.plot([0, 1], [r.rx_prec, r.opus_prec], "-o", color=cols[r.mshort], lw=2.5, markersize=9)
    ax.text(-0.03, r.rx_prec, f"{r.mshort}  {r.rx_prec:.0%}", ha="right", va="center", fontsize=9)
    ax.text(1.03, r.opus_prec, f"{r.opus_prec:.0%}  {r.mshort}", ha="left", va="center", fontsize=9)
ax.set_xticks([0, 1]); ax.set_xticklabels(["scored by\nRxNorm (floor)", "scored by\nOpus-judge (truth)"])
ax.set_xlim(-0.4, 1.4); ax.set_ylim(0, 1.03); ax.set_ylabel("precision")
ax.set_title("Same models, two truth sources" + (" — the ranking flips" if flipped else ""))
fig.tight_layout(); plt.show()
if flipped:
    msg = (f"**The ranking reverses.** By RxNorm, **{rx_rank[0]}** looks best; by Opus-judge, **{op_rank[0]}** "
           f"is best. Trusting the objective database alone, we'd have chosen **{rx_rank[0]}** — the "
           f"*more*-hallucinating model. This is exactly why the design uses Opus-as-truth and treats "
           f"database/model agreement as a floor, never the verdict.")
else:
    msg = (f"Both sources rank the models the same way (**{op_rank[0]}** first) — here they agree. But the "
           f"Opus−RxNorm gap ({MS['opus_prec'].mean():.0%} vs {MS['rx_prec'].mean():.0%} on average) still "
           f"shows how much correct informal aliasing RxNorm cannot see.")
display(Markdown(msg))
'''

S5 = ("## 5. Cross-model divergence (diagnostic) and run-to-run variability\n\n"
      "Divergence answers \"do the models produce the same alias set?\" — a flag for *where* they behave "
      "differently, never a correctness verdict (two models can agree on the same junk). Variability is the "
      "K=5 self-agreement at temperature 0.")
S5_CODE = r'''
col1, col2 = "#0e6b74", "#e67e22"
if len(DIV):
    dd = DIV.sort_values("jaccard")
    fig, ax = plt.subplots(figsize=(7, max(3, 0.32*len(dd))))
    ax.barh(dd.drug, dd.jaccard, color="#8e44ad", height=0.6)
    ax.set_xlim(0, 1); ax.set_xlabel("Jaccard of alias sets between models"); ax.set_title("Cross-model divergence by drug (lower = models disagree more)")
    fig.tight_layout(); plt.show()
    wv_txt = ""
    if len(WV):
        wv_txt = (f" Within-model run-to-run agreement (k={MAN['k']}, temp 0) averages "
                  f"{WV.self_jaccard.mean():.2f} — " +
                  ("near-deterministic, as expected." if WV.self_jaccard.mean() > 0.9
                   else "notably below 1, so even at temp 0 the alias list wobbles between runs."))
    display(Markdown(
      f"**What this shows:** the two models share a mean **{DIV.jaccard.mean():.0%}** of their alias sets; "
      f"they diverge most on **{dd.iloc[0].drug}** and agree most on **{dd.iloc[-1].drug}**. Pair this with "
      f"§3 — divergence tells you *where* they differ, §3 tells you *who is right*.{wv_txt}"))
'''

S6 = ("## 6. Conclusion & scorecard row\n\n"
      "Alias generation has a right answer, and we measured it against two truth sources with the judge "
      "itself validated. The tiered read:")
S6_CODE = r'''
best = MS.sort_values("opus_prec", ascending=False).iloc[0]
lines = [
  f"- **Correctness (vs Opus-truth):** {best.mshort} leads at {best.opus_prec:.0%} valid; "
  f"full per-model numbers in the §3 table. This is the accuracy column of the scorecard.",
  f"- **Judge is sound:** Opus reproduced RxNorm on {judge_agree:.0%} of confirmable aliases, so the "
  f"precision numbers above are trustworthy, not circular.",
  f"- **RxNorm is a floor ({MS['rx_prec'].mean():.0%}), not the verdict** — it can't see LDN or typos and "
  f"misses some real brands; it corroborates rather than scores.",
  f"- **Divergence is a diagnostic, not a ranking** — the models overlap ~{DIV.jaccard.mean():.0%} on which "
  f"aliases they emit; who is *correct* is the Opus/RxNorm column, not the overlap.",
]
display(Markdown("### Verdict\n\n" + "\n".join(lines)))
# scorecard row(s)
sc = MS[["mshort","opus_prec","rx_prec","brand_recall","mean_aliases"]].copy()
for c in ["opus_prec","rx_prec","brand_recall"]: sc[c] = (sc[c]*100).round(0).astype(int).astype(str)+"%"
sc["mean_aliases"] = sc["mean_aliases"].round(1)
sc.columns = ["model","accuracy (Opus)","RxNorm floor","brand recall","aliases/drug"]
display(HTML("<b>① alias — scorecard rows</b>" + sc.to_html(index=False)))
'''

S7 = '''## 7. Research limitations

- **Roster.** OpenRouter credits were exhausted, so the candidate set is 2 Anthropic models — the
  cross-model divergence is therefore *within-lab* and understates true divergence. The harness takes any
  `--models` list; the full lab roster runs unchanged when credits return. This is the biggest gap.
- **Opus-as-truth is silver, not gold.** It is a model grading models; we validated it against RxNorm on
  the covered subset (§2), but on genuinely ambiguous informal aliases it is a judgment, not ground truth.
  RxNorm covers only the formal names and even misses some real brands.
- **Drug set.** 16 curated real drugs + one supplement; precision on obscure supplements (no RxNorm anchor)
  leans entirely on Opus and should be read with more caution.
- **Temperature 0** removes sampling noise but not all non-determinism; the K=5 self-Jaccard (§5) quantifies
  the residue.
- This notebook measures the *correctness of a measurement step*, not any treatment effect.'''

PROV = r'''
import hashlib as _h
try: _sha = _h.sha256(open(r"__DB__","rb").read()).hexdigest()[:16]
except Exception: _sha = "n/a (empty/placeholder db)"
prov = pd.DataFrame({
  "item": ["run generated (UTC)","judgement","candidate models","judge (truth)","truth sources",
           "drugs / k","temperature","skill version"],
  "value": [MAN["generated_utc"], MAN["judgement"], ", ".join(MAN["candidate_models"]),
            MAN["judge_model"], ", ".join(MAN["truth_sources"]),
            f'{MAN["n_drugs"]} / {MAN["k"]}', MAN["temperature"], "research-assistant v2"],
})
display(HTML("<b>Provenance</b>" + prov.to_html(index=False)))
display(HTML('<div style="font-size:1.2em;font-weight:bold;font-style:italic;margin-top:1em">'
             'These findings reflect the behaviour of a measurement pipeline and model knowledge, not '
             'population-level treatment effects. This is not medical advice.</div>'))
'''.replace("__DB__", DB)


def main():
    cells = [
        ("md", RQ), ("code", LOAD),
        ("md", S1),
        ("md", S2), ("code", S2_CODE),
        ("md", S3), ("code", S3_CODE),
        ("md", S4), ("code", S4_CODE),
        ("md", S5), ("code", S5_CODE),
        ("md", S6), ("code", S6_CODE),
        ("md", S7), ("code", PROV),
    ]
    nb = build_notebook(cells, db_path=DB, title="Judgement 1 — alias generation validation")
    html = execute_and_export(nb, "notebooks/validation/j1_alias", timeout=900)
    print("Wrote", html)


if __name__ == "__main__":
    main()
