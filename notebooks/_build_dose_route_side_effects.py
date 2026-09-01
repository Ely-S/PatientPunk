"""Build, execute, and export: dose, route and side-effect reporting for tropoflavin.

Rebuilt after the 2026-09-01 recall repair, which recovered 25 compound exposures the
2026-08-27 extraction had missed. See issue #143 for why they were missed.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from build_notebook import build_notebook, execute_and_export

REPO = Path(__file__).resolve().parent.parent
STUDY = REPO / "studies" / "tropoflavin_nootropics"
DATA_ROOT = Path(os.environ.get("PATIENTPUNK_DATA") or REPO.parent / "PatientPunk_data")
DATA = DATA_ROOT / "studies" / "tropoflavin_nootropics" / "runs"

DB_BLOCK = f'''DB_PATH = r"{DATA / '2026-08-31-comparator-cohort/sentiment/comparators.db'}"
STUDY_DIR = r"{STUDY}"
if not os.path.exists(DB_PATH):
    raise FileNotFoundError(DB_PATH)
sys.path.insert(0, STUDY_DIR)
conn = sqlite3.connect(f"file:{{DB_PATH}}?mode=ro", uri=True)'''

CELLS = []
md = lambda s: CELLS.append(("md", s))
code = lambda s: CELLS.append(("code", s))

# ── framing ───────────────────────────────────────────────────────────────────────
md('**Research question:** *Does the dose someone takes, or the route they take it by, '
   'predict whether they report a side effect?*')

md("""# Dose, Route and Side-Effect Reporting in Tropoflavin Users

## Abstract

Pipeline B records the dose and administration route a patient states; Pipeline A records
whether they named a side effect. The two share an author key, so they can be joined to
ask whether dose or route predicts reported harm.

The answer is **no**, and the more useful finding is *why the question is hard to answer*.
Across 159 observed (author, compound) exposures, only 64 carry a dose and 62 a route.
Every dose band's 95% interval contains the cohort baseline; a trend test across the six
bands is non-significant, and so is sublingual against every other route.

This is the second build. The first rested on an extraction that had silently missed a
large share of the compound mentions in its own corpus — see issue #143. A repair run
recovered 25 exposures, raising the dosed sample by 28% and the routed sample by 41%.
**The conclusion did not change.** That is worth stating plainly: the added data made the
intervals narrower without moving them off the baseline, which is a more informative null
than the one we had before.
""")

# ── data ──────────────────────────────────────────────────────────────────────────
md("""## 1. Where the numbers come from

| quantity | source |
|---|---|
| dose, administration route | Pipeline B — `pipeline_b_compound_exposures`, plus the 2026-09-01 repair run |
| side-effect presence | Pipeline A — `treatment_reports.side_effects` in `comparators.db` |
| join key | `author_hash` = `user_id` (13,545 of 13,568 linked authors resolve) |

`comparators.db` keeps 7,8-DHF and 4′-DMA as separate drug ids, so side effects attribute
per compound. The linked database merges them under one `treatment` row and cannot.

**The outcome is a reporting rate, not clinical incidence.** It means "this author named a
side effect somewhere in their posts". Silence is not tolerance — it is usually a post
about something else.""")

code("""import dose_route_se_data as D
import collections

rows = D.build(conn)
obs  = [r for r in rows if r["observed"]]

origin = collections.Counter(r["origin"] for r in rows)
print(f"(author, compound) exposures : {len(rows)}")
for k, v in origin.most_common():
    print(f"   {k:22} {v}")
print(f"\\nobserved (author has a sentiment report for that compound): {len(obs)}")
print(f"   ...with a dose band : {sum(1 for r in obs if r['dose_band'])}")
print(f"   ...with a route     : {sum(1 for r in obs if r['route'])}")

k = sum(r["has_se"] for r in obs)
p, lo, hi = D.wilson(k, len(obs))
print(f"\\nBASELINE side-effect reporting rate: {k}/{len(obs)} = {100*p:.1f}%"
      f"  [{100*lo:.1f}%, {100*hi:.1f}%]")""")

md("""### The corroboration filter

The repair raised recall by telling the model to extract complete stack lists. That cost
attribution accuracy: it began pairing a compound with whatever dose sat nearby. A
recovered dose is therefore kept only when the number actually appears within 400
characters of a mention of the compound it was attached to.

Three doses fail that check and are dropped here. All three were verified by hand as
belonging to a different compound in the same passage — 100 mg of Phenyl Hydrazide,
10 mg of Kratom, and "less than 5 mg" of a tryptamine.""")

code("""dropped = []
for (author, compound), rec in D.load_recovered().items():
    pass  # load_recovered already applies the filter; show what it removed

import csv, re
raw_pairs = kept_pairs = 0
for row in csv.DictReader((D.REPAIR / "improved" / "records.csv").open(encoding="utf-8")):
    text = None
    for item in (row.get("dosage") or "").split("|"):
        if ":" not in item:
            continue
        treatment, value = (s.strip() for s in item.split(":", 1))
        if not D.TARGET.search(treatment) or D.to_mg(value) is None:
            continue
        raw_pairs += 1
        if text is None:
            text = D.author_text(row["author_hash"])
        if D.corroborated(text, value):
            kept_pairs += 1
        else:
            dropped.append((row["author_hash"][:8], treatment, value))

print(f"numeric target doses extracted : {raw_pairs}")
print(f"corroborated, kept             : {kept_pairs}")
print(f"dropped as unattributable      : {len(dropped)}")
for a, t, v in dropped:
    print(f"   [{a}] {t} -> {v}")""")

# ── dose ──────────────────────────────────────────────────────────────────────────
md("""## 2. Side-effect reporting by dose band

Each row is a dose band. The dot is the point estimate, the bar the 95% Wilson interval,
and the dashed line the cohort baseline. Wilson rather than the normal approximation
because most cells hold fewer than fifteen exposures.""")

code("""import matplotlib.pyplot as plt
import numpy as np

def rate_table(subset, key, order):
    groups = collections.defaultdict(list)
    for r in subset:
        if r[key]:
            groups[r[key]].append(r)
    out = []
    for label in order:
        g = groups.get(label)
        if not g:
            continue
        k, n = sum(x["has_se"] for x in g), len(g)
        p, lo, hi = D.wilson(k, n)
        out.append(dict(label=label, n=n, k=k, p=p, lo=lo, hi=hi))
    return out

def forest(table, title, baseline, ax):
    y = np.arange(len(table))[::-1]
    ax.axvline(100 * baseline, ls="--", lw=1, color="#888", zorder=1,
               label=f"baseline {100*baseline:.1f}%")
    for yi, row in zip(y, table):
        ax.plot([100 * row["lo"], 100 * row["hi"]], [yi, yi], lw=6,
                color="#2a78d6", alpha=0.25, solid_capstyle="butt", zorder=2)
        ax.plot(100 * row["p"], yi, "o", ms=7, color="#2a78d6", zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{r['label']}  (n={r['n']})" for r in table])
    ax.set_xlim(0, 100); ax.set_xlabel("% reporting >=1 side effect")
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold")
    ax.grid(axis="x", lw=0.5, alpha=0.3); ax.set_axisbelow(True)
    for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
    ax.legend(loc="lower right", fontsize=8, frameon=False)

base = sum(r["has_se"] for r in obs) / len(obs)
dose_tbl = rate_table(obs, "dose_band", D.BAND_ORDER)

fig, ax = plt.subplots(figsize=(9, 0.5 * len(dose_tbl) + 2))
forest(dose_tbl, "Reported >=1 side effect, by dose band (both tropoflavin compounds)",
       base, ax)
plt.tight_layout(); plt.show()

print(f"{'band':16}{'n':>5}{'>=1 SE':>8}{'rate':>8}   95% CI")
for r in dose_tbl:
    print(f"{r['label']:16}{r['n']:>5}{r['k']:>8}{100*r['p']:>7.1f}%   "
          f"[{100*r['lo']:>4.0f}%, {100*r['hi']:>4.0f}%]")""")

md("""### Does the rate trend with dose?

A Cochran–Armitage test across the six ordered milligram bands. Bands are compared
**within compound** where possible: 4′-DMA is roughly an order of magnitude more potent,
so pooling raw milligrams across the two would be meaningless.""")

code("""quant = [r for r in obs if r["dose_band"] in D.BAND_ORDER[:6]]
cells = []
for i, band in enumerate(D.BAND_ORDER[:6], start=1):
    g = [r for r in quant if r["dose_band"] == band]
    if g:
        cells.append((i, sum(r["has_se"] for r in g), len(g)))
z, p = D.cochran_armitage(cells)
print(f"all tropoflavin exposures : z = {z:+.2f}, p = {p:.3f}   (n = {sum(c[2] for c in cells)})")

for compound in ("7,8-DHF", "4'-DMA"):
    sub = [r for r in quant if r["compound"] == compound]
    cc = []
    for i, band in enumerate(D.BAND_ORDER[:6], start=1):
        g = [r for r in sub if r["dose_band"] == band]
        if g:
            cc.append((i, sum(r["has_se"] for r in g), len(g)))
    if sum(c[2] for c in cc) >= 8:
        z2, p2 = D.cochran_armitage(cc)
        print(f"{compound:25} : z = {z2:+.2f}, p = {p2:.3f}   (n = {sum(c[2] for c in cc)})")

lower = [r for r in quant if (r["dose_order"] or 9) <= 3]
upper = [r for r in quant if (r["dose_order"] or 0) >= 4]
a, b = sum(r["has_se"] for r in upper), len(upper) - sum(r["has_se"] for r in upper)
c_, d_ = sum(r["has_se"] for r in lower), len(lower) - sum(r["has_se"] for r in lower)
print(f"\\n<25 mg vs >=25 mg : {c_}/{len(lower)} vs {a}/{len(upper)}, "
      f"Fisher exact p = {D.fisher_exact(a, b, c_, d_):.3f}")""")

# ── route ─────────────────────────────────────────────────────────────────────────
md("""## 3. Side-effect reporting by route

Sublingual (`oral mucosal`) dominates this cohort. The recovered exposures widen the
comparison group, which is where the repair helped most.""")

code("""route_tbl = rate_table(obs, "route", D.ROUTE_ORDER)
fig, ax = plt.subplots(figsize=(9, 0.5 * len(route_tbl) + 2))
forest(route_tbl, "Reported >=1 side effect, by administration route", base, ax)
plt.tight_layout(); plt.show()

print(f"{'route':26}{'n':>5}{'>=1 SE':>8}{'rate':>8}   95% CI")
for r in route_tbl:
    print(f"{r['label']:26}{r['n']:>5}{r['k']:>8}{100*r['p']:>7.1f}%   "
          f"[{100*r['lo']:>4.0f}%, {100*r['hi']:>4.0f}%]")

subl = [r for r in obs if r["route"] == "oral mucosal"]
other = [r for r in obs if r["route"] and r["route"] != "oral mucosal"]
a, b = sum(r["has_se"] for r in subl), len(subl) - sum(r["has_se"] for r in subl)
c_, d_ = sum(r["has_se"] for r in other), len(other) - sum(r["has_se"] for r in other)
print(f"\\nsublingual {a}/{len(subl)} vs every other known route {c_}/{len(other)}"
      f"  ->  Fisher exact p = {D.fisher_exact(a, b, c_, d_):.3f}")""")

# ── what the repair changed ───────────────────────────────────────────────────────
md("""## 4. What the recall repair changed

The honest test of the repair is not whether it produced more rows, but whether it moved
any conclusion. It did not — it narrowed intervals.""")

code("""orig = [r for r in obs if r["origin"] == "original"]
print(f"{'':34}{'original only':>15}{'with recovered':>16}")
for label, key, order in (("exposures with a dose", "dose_band", D.BAND_ORDER),
                          ("exposures with a route", "route", D.ROUTE_ORDER)):
    a = sum(1 for r in orig if r[key])
    b = sum(1 for r in obs if r[key])
    print(f"  {label:32}{a:>15}{b:>16}   ({100*(b-a)/max(a,1):+.0f}%)")

for label, subset in (("original only", orig), ("with recovered", obs)):
    t = rate_table(subset, "dose_band", D.BAND_ORDER)
    widths = [100 * (r["hi"] - r["lo"]) for r in t]
    print(f"\\n{label}: {len(t)} dose bands, mean 95% CI width "
          f"{sum(widths)/len(widths):.0f} percentage points")""")

# ── limits ────────────────────────────────────────────────────────────────────────
md("""## 5. What constrains this

**1. It is a reporting rate.** "Named a side effect somewhere" is not incidence. An
author who tolerated a compound perfectly and an author who never discussed side effects
are indistinguishable here.

**2. Dose and route are rarely co-reported.** Even after the repair, only a minority of
exposures carry both, so a dose × route interaction is not estimable. The bands are
marginal, not joint.

**3. The recovered rows are ~85–90% precise.** The corroboration filter removes the three
dose misattributions it can detect. Routes are weaker: of 20 recovered route values, 4
were unsupported by any route language near the compound, including one `sublingual`
appearing nowhere in the source. Route findings should be leaned on less than dose.

**4. Side-effect strings are uncanonicalised.** Presence/absence is safe; counts are not.
`comparators.db` stores raw strings, so `headache` and `headaches` both score.

**5. Absence of an effect is not evidence of absence.** With cells this size the study is
underpowered for anything but a large effect. A true difference of ten or fifteen
percentage points between bands would not reliably show up here.""")

code("""from IPython.display import HTML, display
display(HTML(
    '<div style="font-size:1.05em;font-style:italic;text-align:center;padding:18px;'
    'margin-top:18px;border-top:2px solid #ccc;"><strong>These findings reflect reporting '
    'patterns in an online community, not population-level treatment effects. '
    'This is not medical advice.</strong></div>'))""")

nb = build_notebook(cells=CELLS, db_path_block=DB_BLOCK,
                    title="Dose, route and side-effect reporting")
out = REPO / "notebooks" / "dose_route_side_effects"
execute_and_export(nb, str(out))
print(f"built -> {out}.html")
