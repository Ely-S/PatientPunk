"""Build, execute, and export the 7,8-DHF dose / route / side-effect notebook.

Scope is 7,8-DHF alone. 4'-DMA is excluded rather than reported alongside: at 15 dosed
users and a 14-vs-3 route split it cannot support an inference, and milligrams do not
pool across compounds that differ tenfold in potency.

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

md('**Research question:** *Does dose or route predict whether a 7,8-DHF user reports a '
   'side effect — and if not, what does?*')

md("""# 7,8-DHF: Dose, Route and Side-Effect Reporting

## Abstract

Pipeline B records the dose and route a patient states; Pipeline A records whether they
named a side effect. They share an author key, so the two can be joined.

**Scope is 7,8-DHF alone.** 4′-DMA is excluded, not reported alongside: milligrams do not
pool across compounds differing about tenfold in potency, and at 15 dosed users it cannot
support an inference of its own.

Across **116 analysable users**, 49 state a dose and 45 a route. Neither predicts
side-effect reporting — every dose band's interval contains the 36.2% cohort baseline,
the trend across bands is flat (p = 0.49), and sublingual does not separate from other
routes (p = 0.53).

**The more useful result is what does predict it.** Two things, and both are artifacts of
how the data was made rather than facts about the drug:

1. Saying the compound *worsened* something — which is not a predictor at all.
   All 16 users who said so also have a side effect recorded, so the term is not even
   estimable. Pipeline B's `worsened: insomnia` and Pipeline A's
   `side_effects: ["insomnia"]` are the same sentence read twice.
2. How much the person wrote about the compound. And the increase is *smaller* than
   independent accumulation across reports would predict, so there is no evidence of
   anything beyond more-text-more-chances.

Nothing pharmacological survives. A side-effect rate computed this way measures reporting
intensity, not risk — which constrains how any drug in this panel can be compared.

Section 6 rebuilds the dose question on a sounder unit. At person level a dose and an
outcome are joined because the same author wrote both somewhere; where the post itself
can be checked, that pairing disagrees with the author 21% of the time. Counting only
posts that state a dose and an outcome together leaves 36 posts from 33 authors, and the
answer does not change — trend p = 0.35, unchanged by clustering. The post-level estimate
is smaller and less precise, and it is the one that means what it says.

The reported profile itself is dominated by sleep and activation, each affecting about
one user in ten.
""")

md("""## 1. Cohort and provenance

| quantity | source |
|---|---|
| dose, route | Pipeline B — `pipeline_b_compound_exposures`, plus the 2026-09-01 repair |
| side-effect presence | Pipeline A — `treatment_reports.side_effects` in `comparators.db` |
| join key | `author_hash` = `user_id` |

`comparators.db` keeps 7,8-DHF as its own `drug_id`, so side effects attribute to this
compound rather than the tropoflavin family.

**The outcome is a reporting rate, not incidence.** It means "this user named a side
effect somewhere in their posts". A user is analysable only if they filed a sentiment
report for the compound — without one there is no outcome to score, and treating their
silence as "no side effect" would invent data.""")

code("""import dose_route_se_data as D
import collections

conn = D.connect()          # comparators.db with the linked study db attached as `L`
rows = [r for r in D.build(conn)
        if r["observed"] and r["compound"] == "7,8-DHF"]

k = sum(r["has_se"] for r in rows)
p, lo, hi = D.wilson(k, len(rows))
print(f"7,8-DHF analysable users : {len(rows)}")
print(f"  with a stated dose     : {sum(1 for r in rows if r['dose_band'])}")
print(f"  with a stated route    : {sum(1 for r in rows if r['route'])}")
print(f"  recovered by the repair: {sum(1 for r in rows if r['origin'] != 'original')}")
print(f"\\nBASELINE: {k}/{len(rows)} = {100*p:.1f}%  [{100*lo:.1f}%, {100*hi:.1f}%]")""")

md("""## 2. Dose

The dot is the point estimate, the bar the 95% Wilson interval, the dashed line the
cohort baseline. Wilson rather than the normal approximation because most cells hold
fewer than fifteen people.""")

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
        kk, nn = sum(x["has_se"] for x in g), len(g)
        pp, ll, hh = D.wilson(kk, nn)
        out.append(dict(label=label, n=nn, k=kk, p=pp, lo=ll, hi=hh))
    return out

def forest(table, title, baseline, ax):
    # baseline=None omits the reference line -- it is only meaningful when every
    # row shares the same denominator and outcome.
    y = np.arange(len(table))[::-1]
    if baseline is not None:
        ax.axvline(100 * baseline, ls="--", lw=1, color="#888", zorder=1)
        ax.text(100 * baseline + 1.5, 0.985, f"baseline {100*baseline:.1f}%",
                transform=ax.get_xaxis_transform(), va="top", ha="left",
                fontsize=8, color="#666")
    for yi, row in zip(y, table):
        ax.plot([100 * row["lo"], 100 * row["hi"]], [yi, yi], lw=6,
                color="#2a78d6", alpha=0.25, solid_capstyle="butt", zorder=2)
        ax.plot(100 * row["p"], yi, "o", ms=7, color="#2a78d6", zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{r['label']}  (n={r.get('count', r['n'])})" for r in table])
    ax.set_xlim(0, 100); ax.set_xlabel("% reporting >=1 side effect")
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold")
    ax.grid(axis="x", lw=0.5, alpha=0.3); ax.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.margins(y=0.08)

base = sum(r["has_se"] for r in rows) / len(rows)
dosed = [r for r in rows if r["dose_band"]]
tbl = rate_table(dosed, "dose_band", D.BAND_ORDER)
print(f"{'band':16}{'n':>5}{'>=1 SE':>8}{'rate':>8}   95% CI")
for r in tbl:
    print(f"{r['label']:16}{r['n']:>5}{r['k']:>8}{100*r['p']:>7.1f}%   "
          f"[{100*r['lo']:>4.0f}%, {100*r['hi']:>4.0f}%]")

fig, ax = plt.subplots(figsize=(9, 0.5 * len(tbl) + 2))
forest(tbl, "7,8-DHF - reported >=1 side effect, by dose band", base, ax)
plt.tight_layout(); plt.show()

cells = []
for i, band in enumerate(D.BAND_ORDER[:6], start=1):
    g = [r for r in dosed if r["dose_band"] == band]
    if g:
        cells.append((i, sum(r["has_se"] for r in g), len(g)))
z, pv = D.cochran_armitage(cells)
print(f"trend across {len(cells)} bands (n={sum(c[2] for c in cells)}): "
      f"z = {z:+.2f}, p = {pv:.3f}")

low  = [r for r in dosed if (r["dose_order"] or 9) <= 3]
high = [r for r in dosed if (r["dose_order"] or 0) >= 4]
a, b = sum(r["has_se"] for r in high), len(high) - sum(r["has_se"] for r in high)
c_, d_ = sum(r["has_se"] for r in low), len(low) - sum(r["has_se"] for r in low)
print(f"<25 mg vs >=25 mg: {c_}/{len(low)} vs {a}/{len(high)}, "
      f"Fisher exact p = {D.fisher_exact(a, b, c_, d_):.3f}")""")

md("""## 3. Route

Sublingual (`oral mucosal`) dominates, so the contrast is sublingual against every other
stated route.

Read the small cells carefully. `swallowed oral` and `nasal mucosal` each contain a single
user who reported a side effect; one more would move `swallowed oral` from 14% to 29%. Any
apparent route effect here is a small-denominator illusion, not a signal.""")

code("""routed = [r for r in rows if r["route"]]
tbl = rate_table(routed, "route", D.ROUTE_ORDER)
print(f"{'route':26}{'n':>5}{'>=1 SE':>8}{'rate':>8}   95% CI")
for r in tbl:
    print(f"{r['label']:26}{r['n']:>5}{r['k']:>8}{100*r['p']:>7.1f}%   "
          f"[{100*r['lo']:>4.0f}%, {100*r['hi']:>4.0f}%]")
no_route = [r for r in rows if not r["route"]]
kk = sum(r["has_se"] for r in no_route)
print(f"{'(no route stated)':26}{len(no_route):>5}{kk:>8}"
      f"{100*kk/len(no_route):>7.1f}%")

subl  = [r for r in routed if r["route"] == "oral mucosal"]
other = [r for r in routed if r["route"] != "oral mucosal"]
a, b = sum(r["has_se"] for r in subl), len(subl) - sum(r["has_se"] for r in subl)
c_, d_ = sum(r["has_se"] for r in other), len(other) - sum(r["has_se"] for r in other)
print(f"\\nsublingual {a}/{len(subl)} vs other routes {c_}/{len(other)}"
      f"  ->  Fisher exact p = {D.fisher_exact(a, b, c_, d_):.3f}")

fig, ax = plt.subplots(figsize=(9, 0.5 * len(tbl) + 2))
forest(tbl, "7,8-DHF - reported >=1 side effect, by route", base, ax)
plt.tight_layout(); plt.show()""")

md("""### Is there a route-specific local effect?

If sublingual dosing caused harm attributable to the route, local irritation is where it
would appear. Searching every 7,8-DHF side-effect string for mucosal language — mouth,
tongue, throat, taste, burning, numbness, stinging, gums — finds none.""")

code("""import re
LOCAL = r"mouth|tongue|throat|taste|burn|gum|sting|numb|sublingual|mucos"
found = collections.Counter()
for r in rows:
    for t in D.side_effect_terms(conn, r["author"], 1):
        if re.search(LOCAL, t):
            found[t] += 1
print(f"terms matching mucosal language: {sum(found.values())}")
for t, v in found.most_common():
    print(f"   {v}x {t}")
print("\\n('irritability' matches the pattern on 'irrit' but is mood, not mucosa -"
      "\\n which is why this is inspected rather than counted automatically.)")""")

md("""## 4. What users actually report

Raw strings are uncanonicalised in `comparators.db` — `headache` and `headaches` are
separate entries — so presence/absence per person is safe but any profile needs grouping
first. `D.canon_side_effect` does that; terms it cannot place are reported rather than
swept into an "other" bucket.

The denominator is the whole cohort, so these read as "x% of 7,8-DHF users mentioned
this", not "x% of side effects were this".""")

code("""cat_people = collections.defaultdict(set)
unmapped = collections.Counter()
for r in rows:
    for t in D.side_effect_terms(conn, r["author"], 1):
        lab = D.canon_side_effect(t)
        if lab:
            cat_people[lab].add(r["author"])
        else:
            unmapped[t] += 1

n = len(rows)
print(f"{'category':26}{'users':>7}{'% of cohort':>13}   95% CI")
prof = []
for lab, ppl in sorted(cat_people.items(), key=lambda x: -len(x[1])):
    kk = len(ppl)
    pp, ll, hh = D.wilson(kk, n)
    prof.append(dict(label=lab, n=n, count=kk, k=kk, p=pp, lo=ll, hi=hh))
    print(f"{lab:26}{kk:>7}{100*pp:>12.1f}%   [{100*ll:>4.1f}%, {100*hh:>4.1f}%]")
print(f"\\nunmapped: {sum(unmapped.values())} mentions, {len(unmapped)} distinct terms")
print("  e.g.", [t for t, _ in unmapped.most_common(6)])

fig, ax = plt.subplots(figsize=(9, 0.42 * len(prof) + 2))
forest(prof, "7,8-DHF - side-effect categories, % of all 116 users", None, ax)
ax.set_xlim(0, 40); ax.set_xlabel("% of the 116-user cohort mentioning this")
plt.tight_layout(); plt.show()""")

md("""## 5. What predicts reporting a side effect

Since dose and route do not, the question is what does. The first candidate has to be
removed before any model is fit, and removing it is the more interesting result.""")

md("""### `worsened` is the same variable, not a predictor

Pipeline B writes `7,8-dhf: worsened: insomnia`. Pipeline A writes
`side_effects: ["insomnia"]`. These are two extractions of **the same sentence**.

The cross-tabulation makes it unarguable: every user who said the compound worsened
something also has a side effect recorded. Not a strong association — a perfect one.
Logistic regression cannot estimate a coefficient under complete separation, which is the
statistical way of saying the two columns carry the same information.""")

code("""worsened = collections.defaultdict(set)
for author, outcome in conn.execute(
        "select author_hash, outcome from L.pipeline_b_treatment_outcomes "
        "where target_compound='7,8-DHF'"):
    worsened[author].add(outcome)

tab = collections.Counter()
for r in rows:
    tab[(int("worsened" in worsened.get(r["author"], set())), int(r["has_se"]))] += 1

print(f"{'':22}{'no side effect':>16}{'side effect':>14}")
for said in (0, 1):
    lab = "said 'worsened'" if said else "did not"
    print(f"  {lab:20}{tab[(said, 0)]:>16}{tab[(said, 1)]:>14}")
n_w = tab[(1, 0)] + tab[(1, 1)]
print(f"\\n{tab[(1,1)]} of {n_w} who said it worsened something also named a side effect "
      f"({100*tab[(1,1)]/max(n_w,1):.0f}%)")
print("complete separation -- the term is not estimable and is excluded below."
      if tab[(1, 0)] == 0 else "not complete separation.")""")

code("""same = diff = 0
examples = []
for author, symptom in conn.execute(
        "select author_hash, symptom from L.pipeline_b_treatment_outcomes "
        "where target_compound='7,8-DHF' and outcome='worsened' and symptom<>''"):
    terms = set(D.side_effect_terms(conn, author, 1))
    s_ = symptom.strip().lower()
    hit = any(s_ == t or s_ in t or t in s_ for t in terms)
    same += hit
    diff += not hit
    if len(examples) < 6:
        examples.append((s_, sorted(terms)[:3], hit))
print(f"'worsened: X' rows carrying a symptom : {same + diff}")
print(f"   X is literally a side-effect string : {same}")
print(f"   no overlap                          : {diff}   <- Pipeline A found nothing")
for s_, t, hit in examples:
    print(f"   {'MATCH ' if hit else 'differ'} {s_!r:28} -> {t}")""")

md("""### The model, with that term excluded

What remains is volume, stack size, and whether a dose was stated.""")

code("""import math
import pandas as pd
import statsmodels.formula.api as smf

meta = {a: (t or 0, len([m for m in (md_ or "").split("|") if m.strip()]))
        for a, t, md_ in conn.execute(
            "select author_hash, text_count, medications from L.pipeline_b_records")}

for r in rows:
    r["n_reports"] = D.report_count(conn, r["author"], 1)

df = pd.DataFrame([dict(
    se=int(r["has_se"]),
    log_reports=math.log(r["n_reports"] + 1),
    log_texts=math.log(meta.get(r["author"], (0, 0))[0] + 1),
    stack=meta.get(r["author"], (0, 0))[1],
    has_dose=int(bool(r["dose_band"]))) for r in rows])

m = smf.logit("se ~ log_reports + log_texts + stack + has_dose", data=df).fit(disp=0)
ci = m.conf_int()
print(f"n = {int(m.nobs)}   pseudo R2 = {m.prsquared:.3f}")
print(f"  {'term':14}{'odds ratio':>12}{'95% CI':>20}{'p':>9}")
for term in m.params.index:
    if term == "Intercept":
        continue
    orr = math.exp(min(m.params[term], 700))
    l_, h_ = math.exp(min(ci.loc[term, 0], 700)), math.exp(min(ci.loc[term, 1], 700))
    star = " *" if m.pvalues[term] < 0.05 else ""
    print(f"  {term:14}{orr:>12.2f}{f'[{l_:.2f}, {h_:.2f}]':>20}"
          f"{m.pvalues[term]:>9.3f}{star}")
print("\\nA pseudo R2 near 0.05 means these four together explain very little.")""")

md("""### And the volume term is close to arithmetic

If naming a side effect is roughly an independent chance per report, someone with four
reports has four chances. Estimating that per-report chance from the single-report users
and projecting it forward shows the observed rise is *slower* than pure accumulation — so
there is no evidence of anything beyond more text, more opportunities.""")

code("""one = [r for r in rows if r["n_reports"] == 1]
q = sum(r["has_se"] for r in one) / len(one)
print(f"per-report chance, from the {len(one)} single-report users: q = {q:.3f}\\n")
print(f"  {'group':14}{'users':>7}{'mean reports':>14}{'observed':>10}{'if chance':>11}")
for lab, sub in (("1 report",  [r for r in rows if r["n_reports"] <= 1]),
                 ("2-3 reports", [r for r in rows if 2 <= r["n_reports"] <= 3]),
                 ("4+ reports",  [r for r in rows if r["n_reports"] >= 4])):
    if not sub:
        continue
    mean_n = sum(r["n_reports"] for r in sub) / len(sub)
    obs = sum(r["has_se"] for r in sub) / len(sub)
    print(f"  {lab:14}{len(sub):>7}{mean_n:>14.1f}{100*obs:>9.1f}%"
          f"{100*(1-(1-q)**mean_n):>10.1f}%")""")

md("""## 6. The same question with the post as the unit

Every estimate above joins a dose to an outcome because **the same person wrote both**,
somewhere in their history. That link is often not the author's:

- only 45 of the 173 side-effect reports sit in a post that also states a dose
- where both exist, the person-level band disagrees with what the post itself says
  **21% of the time** — usually because the person mentioned several doses over time and
  the author-level rollup collapsed them to `multiple bands`
- 33 of 59 dosed users have no dose in any post that recorded a side effect at all

So the exposure column is frequently the wrong dose. That is a measurement error, and no
amount of data fixes it.

The alternative is to count a row only when one post carries both — *"I dosed 30 mg
sublingually and..."*. The pairing is then the author's, not ours. The cost is that a
person can contribute more than one post, so the rows are not independent and anything
fitted on them must cluster by author.""")

code("""posts = D.build_posts(conn)          # one row per report whose own post states a dose
post_authors = {p["author"] for p in posts}

kk = sum(p["has_se"] for p in posts)
pp, ll, hh = D.wilson(kk, len(posts))
print(f"posts stating a 7,8-DHF dose : {len(posts)}")
print(f"distinct authors             : {len(post_authors)}")
print(f"posts per author             : {len(posts)/len(post_authors):.2f}")
print(f"reporting a side effect      : {kk}/{len(posts)} = {100*pp:.1f}%"
      f"  [{100*ll:.0f}%, {100*hh:.0f}%]")

print(f"\\n{'band':16}{'posts':>7}{'authors':>9}{'SE':>5}{'rate':>8}   95% CI")
groups = collections.defaultdict(list)
for p_ in posts:
    groups[p_["dose_band"]].append(p_)
for b in D.BAND_ORDER[:6]:
    v = groups.get(b)
    if not v:
        continue
    kx = sum(x["has_se"] for x in v)
    px, lx, hx = D.wilson(kx, len(v))
    print(f"{b:16}{len(v):>7}{len({x['author'] for x in v}):>9}{kx:>5}"
          f"{100*px:>7.1f}%   [{100*lx:>4.0f}%, {100*hx:>4.0f}%]")""")

md("""### Attribution is compound-specific

`4'-DMA-7,8-DHF` contains the string `7,8-DHF`, so a naive pattern hands the 4'-DMA dose
to 7,8-DHF on any post naming both. `D.compound_mentions` excludes an occurrence that is
the tail of the other compound's name.""")

code("""for t in ("I take 4'-DMA-7,8-DHF at 8mg",
          "I take 7,8-DHF at 50mg",
          "I use 4'-DMA-7,8-DHF 8mg and plain 7,8-DHF 50mg"):
    print(f"{t!r}")
    print(f"    7,8-DHF spans : {D.compound_mentions(t, '7,8-DHF')}")
    print(f"    4'-DMA spans  : {D.compound_mentions(t, chr(52)+chr(39)+'-DMA')}")""")

md("""### Does dose predict the outcome, at post level?

Fitted twice: once assuming posts are independent, once clustering by author. With 1.09
posts per author the correction is nearly a no-op here — which is the honest answer to
the pseudo-replication worry rather than a reason to ignore it.""")

code("""import math
import pandas as pd
import statsmodels.formula.api as smf

dfp = pd.DataFrame([dict(se=int(p_["has_se"]), log_mg=math.log(p_["mg"]),
                         author=p_["author"]) for p_ in posts])
for label, kw in (("naive (posts independent)", {}),
                  ("cluster-robust by author",
                   dict(cov_type="cluster", cov_kwds={"groups": dfp["author"]}))):
    m = smf.logit("se ~ log_mg", data=dfp).fit(disp=0, **kw)
    ci = m.conf_int().loc["log_mg"]
    print(f"  {label:28} OR per e-fold dose = {math.exp(m.params['log_mg']):.2f}"
          f"  [{math.exp(ci[0]):.2f}, {math.exp(ci[1]):.2f}]"
          f"  p = {m.pvalues['log_mg']:.3f}")

cells_p = []
for i, b in enumerate(D.BAND_ORDER[:6], start=1):
    v = groups.get(b)
    if v:
        cells_p.append((i, sum(x["has_se"] for x in v), len(v)))
zp, pvp = D.cochran_armitage(cells_p)
print(f"\\n  trend across bands: z = {zp:+.2f}, p = {pvp:.3f}")

m_ratio = len(posts) / len(post_authors)
print(f"  mean posts/author {m_ratio:.2f}; design effect at ICC 0.2 = "
      f"{1 + (m_ratio - 1) * 0.2:.2f}")""")

md("""### What changed, and what did not

| | person-level | post-level |
|---|---|---|
| rows | 49 users | 36 posts (33 authors) |
| dose–outcome pairing | assembled by us | stated by the author |
| independence | rows independent | clustered, correction ~1.02 |
| trend | z = +0.70, p = 0.49 | z = -0.94, p = 0.35 |

Both are null, and the post-level estimate is *less* precise because it discards every
person whose dose and side effect were never in the same post. That is the trade: the
person-level number is bigger and means less.

Note the direction flips to negative — higher dose, marginally fewer reports. Not
significant, and consistent with self-titration: someone who reacts badly at 25 mg does
not go on to try 100 mg, so the high-dose rows are selected for having tolerated the
compound. That selection biases *against* finding harm at dose, and no re-analysis of
this data removes it.""")

md("""## 7. Is 49 dosed users really all there is?

That count comes from the extraction, which is known to under-report (issue #143), so it
is worth checking against the raw text. Scanning the same 752 author histories for a mass
quantity near a compound mention:

| filter | authors |
|---|---:|
| any dose within 120 chars of a mention | 146 |
| after dropping `mg/kg` and study citations | 135 |
| after dropping doses nearer *another* drug name | 92 |
| after requiring first-person use language | 45 |
| **what Pipeline B extracted** (both compounds) | **59** |

The extracted figure sits inside that band. The loose 146 is inflated by rodent-study
`5 mg/kg` figures quoted from papers and by stack lists where the milligrams belong to a
neighbour. Comparing sets directly: 59 in both, 33 found only by the scan, 26 only by
extraction; roughly a third of the 33 are real misses.

**The true count is likely 60–75.** More extraction effort adds perhaps ten or fifteen
people. It does not change the shape: 747 of 752 authors mention this compound and about
a twelfth ever write down a number. The doses were never recorded, so they cannot be
recovered. Reproduce with `raw_dose_count.py` and `raw_dose_strict.py`.""")

md("""## 8. What constrains this

**1. The outcome measures reporting, not incidence.** Section 5 is the evidence: what
predicts it is how much someone wrote, plus a circular term. Someone who tolerated the
compound and someone who never discussed side effects are indistinguishable.

**2. Underpowered by construction.** The largest dose band holds 16 users. A true
difference of ten or fifteen points between bands would not reliably surface. A flat
result is *absence of evidence*, not evidence of absence.

**3. Dose and route are rarely co-reported**, so no interaction is estimable.

**4. Recovered rows are ~85–90% precise.** The corroboration filter removes the three
dose misattributions it can detect. Routes are weaker — of 20 recovered route values, 4
were unsupported by route language near the compound. Lean on route less than dose.

**5. Self-selection.** Someone harmed has more reason to post, and to say what they took.
Nothing here corrects for that, and it acts in the same direction as the volume artifact.

**6. Category boundaries are ours.** `D.SE_CATEGORIES` is a regex map, not a validated
ontology; `activation / anxiety` and `sleep / wakefulness` plausibly overlap in the
underlying complaint.""")

code("""from IPython.display import HTML, display
display(HTML(
    '<div style="font-size:1.05em;font-style:italic;text-align:center;padding:18px;'
    'margin-top:18px;border-top:2px solid #ccc;"><strong>These findings reflect reporting '
    'patterns in an online community, not population-level treatment effects. '
    'This is not medical advice.</strong></div>'))""")

nb = build_notebook(cells=CELLS, db_path_block=DB_BLOCK, title="7,8-DHF dose, route and side effects")
out = REPO / "notebooks" / "dose_route_side_effects"
execute_and_export(nb, str(out))
print(f"built -> {out}.html")
