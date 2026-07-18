"""
build_j11_rejudge_nb.py — Judgement 11 value re-score notebook (semantic judge vs Jaccard).

Answers: how much of the ⑪ "28% value agreement" was a measurement artifact (right value, different
phrasing) versus a genuine coding error? Uses the Opus semantic-equivalence verdicts
(data/validation/j11_rejudge.json) against the Jaccard baseline (j11_coding_runs.json), broken down
per field, so we know which fields just need normalization and which are actually mis-coded.
Prices at build time; code-free HTML.
"""
from __future__ import annotations
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "notebooks"))
from build_notebook import build_notebook, execute_and_export

REJ_JSON = (ROOT / "data" / "validation" / "j11_rejudge.json").as_posix()
COD_JSON = (ROOT / "data" / "validation" / "j11_coding_runs.json").as_posix()
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


RQ = ('**Research Question:** "Judgement ⑪ scored coded values at ~28% agreement by Jaccard set-overlap. How '
      'much of that was a *measurement artifact* (right value, different phrasing) versus a genuine coding '
      'error — and which fields are which?"\n\n*A re-score of ⑪ using an Opus semantic-equivalence judge on the '
      'same codings. This decides whether the fix is normalization (a formatting problem) or something deeper.*')

LOAD = r'''
import json
from collections import defaultdict

REJ = json.load(open(r"__REJ__", encoding="utf-8"))
COD = json.load(open(r"__COD__", encoding="utf-8"))
verd = {(v["model"], v["sample_id"], v["field"]): v["verdict"] for v in REJ["verdicts"]}
GOLD = {g["sample_id"]: g["fields"] for g in COD["gold"]}
FIELDS = COD["manifest"]["fields"]; CAND = COD["manifest"]["candidate_models"]
PRICES = __PRICES__
cod = {(c["model"], c["sample_id"]): c["fields"] for c in COD["codings"]}
def short(m): return m.split("/")[-1]
def jac(a, b):
    a, b = set(a or []), set(b or [])
    return len(a & b) / len(a | b) if (a | b) else 1.0

# per co-populated (model, sample, field): jaccard + semantic verdict
rows = []
for m in CAND:
    for s, gf in GOLD.items():
        mf = cod.get((m, s), {})
        for f in FIELDS:
            gv, mv = gf.get(f), mf.get(f)
            if gv and mv:
                v = verd.get((m, s, f), "different")
                rows.append(dict(model=short(m), field=f, jac=jac(mv, gv),
                                 equiv=(v == "equivalent"), ok=(v in ("equivalent", "model_subset")), verdict=v))
R = pd.DataFrame(rows)

JAC = R.jac.mean(); STRICT = R.equiv.mean(); LEN = R.ok.mean()
vc = R.verdict.value_counts(normalize=True)
# per-field
fg = R.groupby("field").agg(jac=("jac", "mean"), strict=("equiv", "mean"), lenient=("ok", "mean"), n=("ok", "size")).reset_index()
fg["jump"] = fg["lenient"] - fg["jac"]
fg["diff_rate"] = 1 - fg["lenient"]          # share genuinely wrong (not equivalent, not a correct subset)
_art = fg[(fg.n >= 10) & (fg["jump"] > 0.25)].sort_values("jump", ascending=False)   # normalization wins
_bad = fg[(fg.n >= 15) & (fg["diff_rate"] >= 0.25)].sort_values("diff_rate", ascending=False)  # real-error tail
_badtxt = ", ".join(f"{r.field} {r.diff_rate:.0%}" for _, r in _bad.head(5).iterrows()) or "none"
display(Markdown(f"""
**Abstract.** ⑪'s ~28% value agreement was measured by Jaccard set-overlap, which scores "2" vs "at least 2"
as a total miss. Re-scoring the exact same codings with an **Opus semantic-equivalence judge** — across
**{R.model.nunique()} models**, **{len(R):,} co-populated field-values** — splits that number into a good-news
story and a real caveat. **Good news:** by Jaccard the mean is **{JAC:.0%}**, but semantically **{STRICT:.0%}**
of values are *equivalent* to gold and **{LEN:.0%}** are equivalent-or-a-correct-subset — so the scalar-field
panic (age/dose/counts/dates that scored 0 on Jaccard for saying "2" instead of "at least 2") was a pure
**measurement artifact**. The fields that jump most ({', '.join(_art.field.head(4))}) are fixed by
normalization alone. **The caveat:** ~{vc.get('different',0):.0%} of values are *genuinely* wrong (Verdict mix:
{vc.get('equivalent',0):.0%} equivalent, {vc.get('model_subset',0):.0%} correct-but-less-complete,
{vc.get('different',0):.0%} different), and that error is **not uniform** — it concentrates in interpretive
free-text fields ({_badtxt} genuinely different). Normalization can't fix those; the models actually disagree
with Opus on content (and some "different" may be Opus over-interpreting — the ⑩ judge-panel question). **So the
⑪ fix is two-tier: normalize the scalar/categorical majority, and treat the interpretive fields as noisy
clustering covariates that need a stricter schema or a judge panel — not just "models can't code."**
"""))
'''.replace("__REJ__", REJ_JSON).replace("__COD__", COD_JSON)

S1 = ("## 1. Why re-score at all\n\n"
      "⑪ measured coded values by **Jaccard set-overlap**, which is right for *drug sets* but wrong for "
      "free-text values: `infection_count` gold `\"at least 2 (second infection)\"` vs model `\"2\"` scores "
      "**0** by Jaccard, even though it's the same answer. So the 28% headline conflates three things — "
      "genuine errors, incomplete lists, and pure phrasing differences. This re-score asks Opus a narrower, "
      "checkable question — *does the model's value mean the same as gold?* — to separate them.")

S2 = ("## 2. The headline — Jaccard vs semantic\n\n"
      "The same codings, scored three ways: Jaccard (what ⑪ reported), semantic **equivalent** (means the "
      "same), and semantic **equivalent-or-subset** (right, possibly less complete).")
S2_CODE = r'''
vals = [("Jaccard (⑪ original)", JAC, "#95a5a6"), ("semantic: equivalent", STRICT, "#0e6b74"),
        ("semantic: equivalent + subset", LEN, "#27ae60")]
fig, ax = plt.subplots(figsize=(8, 3.2))
ax.barh([v[0] for v in vals], [v[1] for v in vals], color=[v[2] for v in vals], height=0.6)
for i, (_, x, _c) in enumerate(vals): ax.text(x + 0.01, i, f"{x:.0%}", va="center", fontsize=11, fontweight="bold")
ax.set_xlim(0, 1.05); ax.set_xlabel("mean value accuracy over co-populated fields")
ax.set_title("Value accuracy: measurement artifact vs reality"); fig.tight_layout(); plt.show()
display(Markdown(
  f"**What this shows:** the value accuracy jumps from **{JAC:.0%}** (Jaccard) to **{STRICT:.0%}** equivalent "
  f"and **{LEN:.0%}** equivalent-or-subset. Most of the apparent failure was Jaccard penalising correct values "
  f"for wording — the models are coding the *right* values far more often than the set-overlap number implied."))
'''

S3 = ("## 3. Which fields were artifacts, which are real errors\n\n"
      "Per field, two things at once. **Position:** Jaccard (x) vs semantic accuracy (y) — points high above "
      "the diagonal are pure **normalization** wins (right value, Jaccard undercounted). **Colour:** the "
      "genuine-error rate (share ruled *different*) — a red point is a real coding disagreement that "
      "normalization will *not* fix, wherever it sits. A pale point high on the diagonal is the ideal (right, "
      "just needs canonicalising); a red point is a noisy clustering covariate.")
S3_CODE = r'''
d = fg[fg.n >= 10].copy()
fig, ax = plt.subplots(figsize=(8.5, 7))
sc = ax.scatter(d.jac, d.lenient, s=45 + d.n/3, c=d.diff_rate, cmap="Reds", vmin=0, vmax=0.5,
                edgecolor="#333", linewidth=0.4, zorder=3)
ax.plot([0,1],[0,1], ls=":", color="#999")
cb = fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04); cb.set_label("genuine-error rate (ruled 'different')")
# label the biggest normalization wins AND the reddest (real-error) fields
lab = pd.concat([d.sort_values("jump", ascending=False).head(5),
                 d.sort_values("diff_rate", ascending=False).head(6)]).drop_duplicates("field")
for _, r in lab.iterrows():
    ax.annotate(r.field, (r.jac, r.lenient), fontsize=7.5, xytext=(4,2), textcoords="offset points")
ax.set_xlabel("Jaccard value agreement (⑪ original)"); ax.set_ylabel("semantic accuracy (equivalent + subset)")
ax.set_xlim(0,1.02); ax.set_ylim(0,1.02); ax.set_title("Per field: normalization win (up-left→diagonal) vs genuine error (red)")
fig.tight_layout(); plt.show()
tbl = fg[fg.n>=10].sort_values("diff_rate", ascending=False)[["field","jac","strict","lenient","diff_rate","jump","n"]].copy()
for c in ["jac","strict","lenient","diff_rate","jump"]: tbl[c] = (tbl[c]*100).round(0).astype(int).astype(str)+"%"
tbl.columns = ["field","Jaccard","semantic (equiv)","semantic (+subset)","genuinely different","Jaccard→sem jump","n"]
display(HTML("<b>Per-field, sorted by genuine-error rate (worst first)</b>" + tbl.to_html(index=False)))
'''

S4 = ("## 4. What the errors actually are\n\n"
      "The three-way verdict split says how the co-populated values fail: equivalent (fine), a correct but "
      "less-complete subset (a recall/granularity gap, not a wrong value), or genuinely different (the real "
      "coding error).")
S4_CODE = r'''
order = ["equivalent","model_subset","different"]; cmap = {"equivalent":"#27ae60","model_subset":"#f1c40f","different":"#e74c3c"}
counts = R.verdict.value_counts(normalize=True).reindex(order).fillna(0)
fig, ax = plt.subplots(figsize=(8, 2.4))
left = 0
for k in order:
    ax.barh(["all co-populated values"], counts[k], left=left, color=cmap[k], label=k.replace("_"," "))
    if counts[k] > 0.03: ax.text(left + counts[k]/2, 0, f"{counts[k]:.0%}", ha="center", va="center", fontsize=10, color="white", fontweight="bold")
    left += counts[k]
ax.set_xlim(0,1); ax.set_xlabel("share of co-populated field-values")
ax.legend(bbox_to_anchor=(0.5,-0.35), loc="upper center", ncol=3, frameon=False)
ax.set_title("How coded values compare to gold"); fig.tight_layout(); plt.show()
display(Markdown(
  f"**What this shows:** only **{counts['different']:.0%}** of co-populated values are genuinely wrong. "
  f"**{counts['equivalent']:.0%}** mean exactly the same as gold, and **{counts['model_subset']:.0%}** are "
  f"correct but less complete than Opus (a granularity gap on list fields, not a wrong value). The real coding-"
  f"error rate is far below what Jaccard implied — the dominant issue is phrasing/normalization, not accuracy."))
'''

S5 = ("## 5. Conclusion — a two-tier fix, and a bad-covariate watchlist\n\n"
      "The re-score settles the earlier question, but splits it in two: a normalizable majority and a genuinely "
      "error-prone interpretive tail.")
S5_CODE = r'''
# per-model semantic value accuracy vs old jaccard
ms = R.groupby("model").agg(jaccard=("jac","mean"), equiv=("equiv","mean"), ok=("ok","mean"), n=("ok","size")).reset_index().sort_values("ok", ascending=False)
show = ms.copy()
for c in ["jaccard","equiv","ok"]: show[c]=(show[c]*100).round(0).astype(int).astype(str)+"%"
show.columns=["model","Jaccard","semantic equiv","semantic +subset","n values"]
display(HTML("<b>Per-model value accuracy: Jaccard vs semantic</b>" + show.to_html(index=False)))
n_art = int((fg[(fg.n>=10)].jump > 0.25).sum())
_hard = fg[(fg.n>=15) & (fg.diff_rate>=0.25)].sort_values("diff_rate", ascending=False)
_hardtxt = ", ".join(f"`{r.field}` ({r.diff_rate:.0%})" for _, r in _hard.head(6).iterrows()) or "none"
lines = [
  f"- **The scalar-field panic was a measurement artifact.** Semantically, values are **{STRICT:.0%}** equivalent "
  f"to gold and **{LEN:.0%}** equivalent-or-subset — vs {JAC:.0%} by Jaccard. Numeric/date/count fields that "
  f"scored ~0 on Jaccard for phrasing ('2' vs 'at least 2') are actually right; normalization alone fixes them.",
  f"- **But the ~{R.verdict.value_counts(normalize=True).get('different',0):.0%} genuine-error rate is real and "
  f"concentrated, not noise.** {len(_hard)} interpretive free-text fields are ruled *different* ≥25% of the time: "
  f"{_hardtxt}. These are the covariates where models genuinely disagree with Opus on **content** — normalization "
  f"will not help.",
  f"- **The fix is two-tier, not one.** (1) **Normalize** the {n_art}+ scalar/categorical fields that jump from "
  f"low Jaccard to high semantic — this is judgement ③ extended to Track-B values, plus a semantic (not "
  f"set-overlap) metric going forward. (2) **Harden the interpretive fields** — tighter schema/enums, or a judge "
  f"panel to decide whether the disagreement is model-error or Opus over-interpretation (the ⑩ single-Opus-truth "
  f"caveat bites hardest exactly here).",
  f"- **For the clustering study:** the interpretive tail above is a *bad-covariate watchlist*. Cluster on the "
  f"normalizable majority with confidence; stratify, down-weight, or exclude the red fields until a panel "
  f"resolves whether their disagreement is real.",
]
display(Markdown("### Verdict\n\n" + "\n".join(lines)))
'''

S6 = '''## 6. Research limitations

- **Opus judges its own gold.** Opus coded the reference values and now rules on equivalence to them — mild
  circularity (verification ≠ generation, and "is 2 the same as at least 2" is fairly objective, but a second
  independent judge or a panel would tighten it). This is the same Opus-as-truth caveat flagged for ⑩.
- **"model_subset" credits incomplete lists as not-wrong** — correct for value accuracy, but a list field that
  systematically under-lists is still lossy for clustering; presence/recall (⑪) still matters alongside this.
- **Equivalence is per-value**; it does not re-check presence (whether the right fields were populated) — that
  is ⑪'s presence-F1, unchanged here.
- **Judged only co-populated fields** (both gold and model non-null); fields one side left null are a presence
  question, not a value one.
- Measures the correctness of a measurement step, not any treatment effect.'''

PROV = r'''
import hashlib as _h
try: _sha = _h.sha256(open(r"__DB__","rb").read()).hexdigest()[:16]
except Exception: _sha = "n/a"
M = REJ["manifest"]
prov = pd.DataFrame({
  "item": ["re-score generated (UTC)","source codings","judge","candidate models","field-values judged","metric","skill version"],
  "value": [M["generated_utc"], M["source"], M["judge_model"], len(M["candidate_models"]), f"{len(R):,}",
            "semantic equivalence (equivalent | subset | different)", "research-assistant v2"],
})
display(HTML("<b>Provenance</b>" + prov.to_html(index=False)))
display(HTML('<div style="font-size:1.2em;font-weight:bold;font-style:italic;margin-top:1em">'
             'These findings reflect the correctness of a measurement pipeline and model knowledge, not '
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
    nb = build_notebook(cells, db_path=DB, title="Judgement 11 — value re-score (semantic judge)")
    html = execute_and_export(nb, "notebooks/validation/j11_value_rejudge", timeout=1200)
    print("Wrote", html, "| prices:", len(prices))


if __name__ == "__main__":
    main()
