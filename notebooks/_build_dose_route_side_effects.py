"""Build, execute, and export: dose, route and side-effect reporting for tropoflavin.

Nothing is pooled across compounds. Milligrams are not comparable between substances,
and neither are routes -- what sublingual delivery buys over swallowing depends on the
compound's own first-pass metabolism. An earlier version pooled both and produced a
meaningless dose axis.

Rebuilt after the 2026-09-01 recall repair (issue #143).
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

DB_BLOCK = f'''import sys
DB_PATH = r"{DATA / '2026-08-31-comparator-cohort/sentiment/comparators.db'}"
STUDY_DIR = r"{STUDY}"
if not os.path.exists(DB_PATH):
    raise FileNotFoundError(DB_PATH)
sys.path.insert(0, STUDY_DIR)
conn = sqlite3.connect(f"file:{{DB_PATH}}?mode=ro", uri=True)'''

CELLS = []
md = lambda s: CELLS.append(("md", s))
code = lambda s: CELLS.append(("code", s))

md('**Research question:** *Does the dose someone takes, or the route they take it by, '
   'predict whether they report a side effect?*')

md("""# Dose, Route and Side-Effect Reporting in Tropoflavin Users

## Abstract

Pipeline B records the dose and administration route a patient states; Pipeline A records
whether they named a side effect. The two share an author key, so they can be joined to
ask whether dose or route predicts reported harm.

**Nothing here is pooled across compounds.** Milligrams are not comparable between
substances, and neither are routes: how much sublingual delivery buys over swallowing
depends on the compound's own first-pass metabolism. An earlier version of this analysis
pooled both. Its dose axis was meaningless — one band turned out to be mostly gram-scale
lion's mane, which manufactured a spurious downward trend. Every estimate below sits
inside a single compound.

That leaves **7,8-DHF as the only compound that can be tested**: 49 people with a stated
dose across six bands, 45 with a stated route. 4′-DMA is reported for completeness and is
*not* tested — 15 dosed users and a 14-vs-3 route split cannot support an inference.

The answer is **no**. Every dose band's interval contains the compound's own baseline, the
trend across bands is flat, and sublingual does not separate from other routes.

The binding constraint is not extraction quality but what people write down. 747 of the
752 authors mention the compound; only about 60–75 ever attach a milligram number to it.
Section 5 checks that against the raw text rather than trusting the pipeline.
""")

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
about something else.

A person is analysable only if they have a sentiment report for that compound. Without one
there is no outcome to score, and counting their silence as "no side effect" would invent
data.""")

code("""import dose_route_se_data as D
import collections

# The setup cell opened comparators.db alone. The merge also reads the linked study
# database, so let the module open both -- it attaches the linked db as schema `L`.
conn = D.connect()

rows = D.build(conn)
obs  = [r for r in rows if r["observed"]]

print(f"(author, compound) exposures : {len(rows)}")
for k, v in collections.Counter(r["origin"] for r in rows).most_common():
    print(f"   {k:22} {v}")
print(f"\\nanalysable (have a sentiment report for that compound): {len(obs)}")
for compound in ("7,8-DHF", "4'-DMA"):
    g = [r for r in obs if r["compound"] == compound]
    k = sum(r["has_se"] for r in g)
    p, lo, hi = D.wilson(k, len(g))
    print(f"   {compound:9} n={len(g):>4}  dose {sum(1 for r in g if r['dose_band']):>3}"
          f"  route {sum(1 for r in g if r['route']):>3}"
          f"   baseline {100*p:.1f}% [{100*lo:.0f}, {100*hi:.0f}]")""")

md("""### The corroboration filter

The repair raised recall by telling the model to extract complete stack lists. That cost
attribution accuracy: it began pairing a compound with whatever dose sat nearby. A
recovered dose is kept only when the number appears within 400 characters of a mention of
the compound it was attached to.

Three doses fail that check. All three were verified by hand as belonging to a different
compound in the same passage — 100 mg of Phenyl Hydrazide, 10 mg of Kratom, and
"less than 5 mg" of a tryptamine.""")

code("""import csv

dropped = []
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

md("""## 2. Side-effect reporting by dose band, within compound

Each row is a dose band; the dot is the point estimate, the bar the 95% Wilson interval,
and the dashed line that compound's own baseline. Wilson rather than the normal
approximation because most cells hold fewer than fifteen people.

The two compounds are charted separately and never combined. They do not even occupy the
same range — 4′-DMA has nothing above 25 mg while 7,8-DHF concentrates between 25 and
100 — so a shared "<5 mg" bucket would stack doses an order of magnitude apart in
potency.""")

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
    ax.axvline(100 * baseline, ls="--", lw=1, color="#888", zorder=1)
    ax.text(100 * baseline + 1.5, 0.985, f"baseline {100*baseline:.1f}%",
            transform=ax.get_xaxis_transform(), va="top", ha="left",
            fontsize=8, color="#666")
    for yi, row in zip(y, table):
        ax.plot([100 * row["lo"], 100 * row["hi"]], [yi, yi], lw=6,
                color="#2a78d6", alpha=0.25, solid_capstyle="butt", zorder=2)
        ax.plot(100 * row["p"], yi, "o", ms=7, color="#2a78d6", zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{r['label']}  (n={r['n']})" for r in table])
    ax.set_xlim(0, 100); ax.set_xlabel("% reporting >=1 side effect")
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold")
    ax.grid(axis="x", lw=0.5, alpha=0.3); ax.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.margins(y=0.08)

def baseline_for(compound):
    g = [r for r in obs if r["compound"] == compound]
    return sum(r["has_se"] for r in g) / len(g), len(g)

for compound in ("7,8-DHF", "4'-DMA"):
    sub = [r for r in obs if r["compound"] == compound and r["dose_band"]]
    base_c, n_base = baseline_for(compound)
    tbl = rate_table(sub, "dose_band", D.BAND_ORDER)
    note = "" if compound == "7,8-DHF" else "   [descriptive only -- not tested]"
    print(f"\\n{compound}: {len(sub)} people with a dose, "
          f"baseline {100*base_c:.1f}% of {n_base}{note}")
    print(f"  {'band':16}{'n':>5}{'>=1 SE':>8}{'rate':>8}   95% CI")
    for r in tbl:
        print(f"  {r['label']:16}{r['n']:>5}{r['k']:>8}{100*r['p']:>7.1f}%   "
              f"[{100*r['lo']:>4.0f}%, {100*r['hi']:>4.0f}%]")
    fig, ax = plt.subplots(figsize=(9, 0.5 * len(tbl) + 2))
    forest(tbl, f"{compound} - reported >=1 side effect, by dose band", base_c, ax)
    plt.tight_layout(); plt.show()""")

md("""### Does the rate trend with dose?

Cochran–Armitage across the ordered milligram bands, run **within 7,8-DHF only**. 4′-DMA
spreads 12 people across three bands and is not tested.""")

code("""sub = [r for r in obs if r["compound"] == "7,8-DHF"
       and r["dose_band"] in D.BAND_ORDER[:6]]
cells = []
for i, band in enumerate(D.BAND_ORDER[:6], start=1):
    g = [r for r in sub if r["dose_band"] == band]
    if g:
        cells.append((i, sum(r["has_se"] for r in g), len(g)))
z, p = D.cochran_armitage(cells)
print(f"7,8-DHF trend across {len(cells)} bands (n={sum(c[2] for c in cells)}): "
      f"z = {z:+.2f}, p = {p:.3f}")

lower = [r for r in sub if (r["dose_order"] or 9) <= 3]     # <25 mg
upper = [r for r in sub if (r["dose_order"] or 0) >= 4]     # >=25 mg
a, b = sum(r["has_se"] for r in upper), len(upper) - sum(r["has_se"] for r in upper)
c_, d_ = sum(r["has_se"] for r in lower), len(lower) - sum(r["has_se"] for r in lower)
print(f"7,8-DHF <25 mg vs >=25 mg: {c_}/{len(lower)} vs {a}/{len(upper)}, "
      f"Fisher exact p = {D.fisher_exact(a, b, c_, d_):.3f}")

n_dma = len([r for r in obs if r["compound"] == "4'-DMA" and r["dose_band"]])
print(f"\\n4'-DMA: {n_dma} people with a dose -- not tested.")""")

md("""## 3. Side-effect reporting by route, within compound

Route is not pooled either. The *label* "sublingual" is compound-independent, but the
*exposure* it produces is not: bypassing first-pass metabolism is worth a different amount
for each compound, which is the whole reason people take 7,8-DHF under the tongue. Pooling
across compounds would average heterogeneous effects into a number that estimates nothing
in particular.

Sublingual dominates both compounds, so the contrast is sublingual against everything else
with a stated route.""")

code("""for compound in ("7,8-DHF", "4'-DMA"):
    sub = [r for r in obs if r["compound"] == compound and r["route"]]
    base_c, _ = baseline_for(compound)
    tbl = rate_table(sub, "route", D.ROUTE_ORDER)
    print(f"\\n{compound}: {len(sub)} people with a stated route")
    print(f"  {'route':26}{'n':>5}{'>=1 SE':>8}{'rate':>8}   95% CI")
    for r in tbl:
        print(f"  {r['label']:26}{r['n']:>5}{r['k']:>8}{100*r['p']:>7.1f}%   "
              f"[{100*r['lo']:>4.0f}%, {100*r['hi']:>4.0f}%]")

    subl  = [r for r in sub if r["route"] == "oral mucosal"]
    other = [r for r in sub if r["route"] != "oral mucosal"]
    if len(subl) >= 5 and len(other) >= 5:
        a, b = sum(r["has_se"] for r in subl), len(subl) - sum(r["has_se"] for r in subl)
        c_, d_ = sum(r["has_se"] for r in other), len(other) - sum(r["has_se"] for r in other)
        print(f"  sublingual {a}/{len(subl)} vs other routes {c_}/{len(other)}"
              f"  ->  Fisher exact p = {D.fisher_exact(a, b, c_, d_):.3f}")
    else:
        print(f"  sublingual {len(subl)} vs other {len(other)} -- too thin to test.")

    if len(sub) >= 20:
        fig, ax = plt.subplots(figsize=(9, 0.5 * len(tbl) + 2))
        forest(tbl, f"{compound} - reported >=1 side effect, by route", base_c, ax)
        plt.tight_layout(); plt.show()""")

md("""## 4. What the recall repair changed

The honest test of the repair is whether it moved a conclusion. It did not — it added
people to the only stratum that was ever valid.""")

code("""orig = [r for r in obs if r["origin"] == "original"]
print(f"{'':40}{'original':>10}{'repaired':>10}")
for compound in ("7,8-DHF", "4'-DMA"):
    for label, key in (("with a dose", "dose_band"), ("with a route", "route")):
        a = sum(1 for r in orig if r["compound"] == compound and r[key])
        b = sum(1 for r in obs  if r["compound"] == compound and r[key])
        print(f"  {compound + ' ' + label:38}{a:>10}{b:>10}   ({100*(b-a)/max(a,1):+.0f}%)")""")

md("""## 5. Is that really all there is?

These counts come out of the extraction, and the extraction is known to under-report
(issue #143). So they are worth checking against the raw text rather than trusting the
pipeline. Scanning the same 752 author histories for a mass quantity near a compound
mention gives:

| filter | authors |
|---|---:|
| any dose within 120 chars of a mention | 146 |
| after dropping `mg/kg` and study citations | 135 |
| after dropping doses nearer *another* drug name | 92 |
| after requiring first-person use language | 45 |
| **what Pipeline B extracted** | **59** |

The extracted figure sits inside that band. The loose 146 is inflated by rodent-study
`5 mg/kg` figures quoted from papers and by stack lists where the milligrams belong to a
neighbour. Comparing the sets directly: 59 authors in both, 33 found only by the text
scan, 26 only by extraction. Reading a sample of the 33, roughly a third are real misses
(`7,8-DHF: 20mg sublingual powder`) and the rest are artifacts of the scan — purchase
quantities like `Powder, 500mg × 1`, or the phrase "the dose is crucial" beside an
unrelated price.

**The true count is likely 60–75.** More extraction effort would add perhaps ten or
fifteen people. It would not change the shape of the problem: 747 of 752 authors mention
this compound and only about a twelfth of them ever write down a number. The doses were
never recorded, so they cannot be recovered.

Reproduce with `studies/tropoflavin_nootropics/raw_dose_count.py` and
`raw_dose_strict.py`.""")

md("""## 6. What constrains this

**1. It is a reporting rate.** "Named a side effect somewhere" is not incidence. Someone
who tolerated the compound perfectly and someone who never discussed side effects are
indistinguishable here.

**2. Underpowered by construction.** The largest single dose band holds 16 people. A true
difference of ten or fifteen percentage points between bands would not reliably surface. A
flat result here is *absence of evidence*, not evidence of absence.

**3. Dose and route are rarely co-reported**, so no interaction is estimable. The bands
are marginal, not joint.

**4. The recovered rows are ~85–90% precise.** The corroboration filter removes the three
dose misattributions it can detect. Routes are weaker: of 20 recovered route values, 4
were unsupported by any route language near the compound, including one `sublingual`
appearing nowhere in the source. Lean on the route panel less than the dose panel.

**5. Side-effect strings are uncanonicalised.** Presence/absence is safe; counts are not.
`comparators.db` stores raw strings, so `headache` and `headaches` both score.

**6. Self-selection.** Someone who gets a bad effect has more reason to post about it, and
more reason to say what they took. Nothing here corrects for that.""")

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
