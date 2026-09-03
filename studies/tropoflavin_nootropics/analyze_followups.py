"""Fisher on the no_effect gap, sentiment by use-case, and side effects."""

import collections
import json
import math
import re
import sqlite3
import sys

from scipy.stats import binomtest, fisher_exact
from statsmodels.stats.multitest import multipletests
from study_support import (
    StudyPaths,
    compound_for_treatment,
    load_pipeline_b_records,
    readonly_sqlite_uri,
)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def wilson(k, n, z=1.96):
    if not n:
        return (float("nan"),) * 2
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / d
    return max(0, c - m), min(1, c + m)


# ── 1. no_effect gap, one vote per author per compound ─────────────────────
RANK = {
    "worsened": 4,
    "no_effect": 3,
    "mixed": 2,
    "helped": 1,
    "unknown": 0,
}  # keep the most informative
author_out = collections.defaultdict(dict)  # (author, compound) -> outcome

for record in load_pipeline_b_records(StudyPaths.from_environment().records):
    r = record.model_dump()
    for entry in (r.get("treatment_outcome") or "").split("|"):
        parts = [p.strip() for p in entry.strip().split(":")]
        if len(parts) < 2 or not parts[1]:
            continue
        drug, outcome = parts[0], parts[1].lower()
        which = compound_for_treatment(drug)
        if not which or outcome not in RANK:
            continue
        prev = author_out[which].get(r["author_hash"])
        if prev is None or RANK[outcome] > RANK[prev]:
            author_out[which][r["author_hash"]] = outcome

print("=" * 70)
print("1. NO_EFFECT GAP — one vote per author per compound")
print("=" * 70)
tab = {}
for k in ("7,8-DHF", "4'-DMA"):
    c = collections.Counter(author_out[k].values())
    n = sum(c.values())
    tab[k] = (c, n)
    ne = c["no_effect"]
    lo, hi = wilson(ne, n)
    print(f"\n  {k}: n={n} authors  {dict(c)}")
    print(
        f"    no_effect {ne}/{n} = {100 * ne / n:.1f}%  [{100 * lo:.1f}, {100 * hi:.1f}]"
    )

# Some authors report both compounds, so a full-sample Fisher test violates
# independence. Report the matched and mutually exclusive subsets separately.
parent = author_out["7,8-DHF"]
derivative = author_out["4'-DMA"]
overlap = set(parent).intersection(derivative)
parent_only = set(parent).difference(overlap)
derivative_only = set(derivative).difference(overlap)
parent_only_no_effect = sum(
    parent[author] == "no_effect" and derivative[author] != "no_effect"
    for author in overlap
)
derivative_only_no_effect = sum(
    parent[author] != "no_effect" and derivative[author] == "no_effect"
    for author in overlap
)
discordant = parent_only_no_effect + derivative_only_no_effect
matched_p = (
    binomtest(parent_only_no_effect, discordant, 0.5).pvalue if discordant else 1.0
)
parent_exclusive_no_effect = sum(
    parent[author] == "no_effect" for author in parent_only
)
derivative_exclusive_no_effect = sum(
    derivative[author] == "no_effect" for author in derivative_only
)
exclusive_odds, exclusive_p = fisher_exact(
    [
        [parent_exclusive_no_effect, len(parent_only) - parent_exclusive_no_effect],
        [
            derivative_exclusive_no_effect,
            len(derivative_only) - derivative_exclusive_no_effect,
        ],
    ]
)
print(f"\n  Overlapping authors: {len(overlap)}")
print(
    "    discordant no_effect: "
    f"parent only {parent_only_no_effect}, derivative only {derivative_only_no_effect}; "
    f"exact McNemar p={matched_p:.4f}"
)
print(
    f"  Exclusive authors: parent {parent_exclusive_no_effect}/{len(parent_only)}, "
    f"derivative {derivative_exclusive_no_effect}/{len(derivative_only)}; "
    f"OR={exclusive_odds:.2f}, Fisher p={exclusive_p:.4f}"
)

# ── 2. sentiment by use-case ───────────────────────────────────────────────
PURPOSE = {
    "neurogenesis / BDNF": r"\bbdnf\b|\btrkb\b|neurogenes|neuroplastic|\bsynaptogenes|\brewir",
    "depression / mood": r"\bdepress|\bantidepress|\bmood\b|anhedoni",
    "focus / cognition": r"\bfocus\b|\bconcentrat|\bcognit|\bbrain fog\b|\bclarity\b|\bproductiv",
    "memory / learning": r"\bmemory\b|\brecall\b|\blearning\b|\bmemoriz",
    "sleep": r"\bsleep\b|\binsomnia\b",
    "anxiety": r"\banxiet|\banxious\b|\bpanic\b",
    "ADHD": r"\badhd\b|attention deficit",
    "stimulant recovery": r"\bstimulant\b.{0,30}(recover|damage|crash)|\btolerance\b",
    "neuroprotect / repair": r"neuroprotect|\bregenerat|\bheal\w* (my |the )?brain",
}
db = sqlite3.connect(
    readonly_sqlite_uri(StudyPaths.from_environment().database), uri=True
)
db.row_factory = sqlite3.Row
rows = db.execute("""SELECT r.sentiment, r.signal_strength sig, r.user_id, r.side_effects,
                          p.body_text, p.title, p.post_date
                   FROM treatment_reports r JOIN posts p ON p.post_id=r.post_id""").fetchall()
SIG = {"strong": 3, "moderate": 2, "weak": 1, "n/a": 0, None: 0, "": 0}
print("\n" + "=" * 70)
print("2. SENTIMENT BY USE-CASE (pipeline A, one vote per user per category)")
print("=" * 70)
res = []
for cat, pat in PURPOSE.items():
    rx = re.compile(pat, re.I)
    best = {}
    for r in sorted(
        rows, key=lambda r: (r["post_date"] or 0, SIG.get(r["sig"], 0)), reverse=True
    ):
        t = (r["title"] or "") + " " + (r["body_text"] or "")
        if rx.search(t):
            best.setdefault(r["user_id"], r["sentiment"])
    n = len(best)
    if not n:
        continue
    pos = sum(1 for v in best.values() if v == "positive")
    neg = sum(1 for v in best.values() if v == "negative")
    lo, hi = wilson(pos, n)
    res.append((cat, n, pos, neg, 100 * pos / n, 100 * lo, 100 * hi))
base_n = len({r["user_id"] for r in rows})
base_pos = None
bb = {}
for r in sorted(
    rows, key=lambda r: (r["post_date"] or 0, SIG.get(r["sig"], 0)), reverse=True
):
    bb.setdefault(r["user_id"], r["sentiment"])
base_pos = sum(1 for v in bb.values() if v == "positive")
print(f"\n  {'use-case':24s}{'users':>7}{'pos':>6}{'neg':>6}{'pos %':>8}{'95% CI':>16}")
for cat, n, pos, neg, pct, lo, hi in sorted(res, key=lambda x: -x[1]):
    flag = " *small*" if n < 30 else ""
    print(
        f"  {cat:24s}{n:>7}{pos:>6}{neg:>6}{pct:>7.1f}%   [{lo:4.1f},{hi:5.1f}]{flag}"
    )
print(
    f"  {'ALL (baseline)':24s}{base_n:>7}{base_pos:>6}{base_n - base_pos:>6}"
    f"{100 * base_pos / base_n:>7.1f}%"
)
ps = []
for cat, n, pos, neg, pct, lo, hi in res:
    odds, p = fisher_exact(
        [[pos, n - pos], [base_pos - pos, (base_n - n) - (base_pos - pos)]]
    )
    ps.append((cat, n, pct, p))
adj = multipletests([p for _, _, _, p in ps], method="fdr_bh")[1]
print("\n  vs baseline (Fisher, BH-corrected across %d categories):" % len(ps))
for (cat, n, pct, p), q in sorted(zip(ps, adj), key=lambda x: x[1]):
    print(
        f"    {cat:24s} n={n:<4} {pct:5.1f}%   p={p:.3f}  q={q:.3f}"
        + ("  <-- survives" if q < 0.05 else "")
    )

# ── 3. side effects ────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("3. SIDE EFFECTS")
print("=" * 70)
se = collections.Counter()
n_with = 0
for r in rows:
    raw = r["side_effects"]
    if not raw or raw == "[]":
        continue
    try:
        lst = json.loads(raw)
    except Exception:
        continue
    if not lst:
        continue
    n_with += 1
    for s in lst:
        se[str(s).strip().lower()] += 1
print(
    f"\n  pipeline A: {n_with:,} of {len(rows):,} records carry side effects ({100 * n_with / len(rows):.1f}%)"
)
print(f"  {sum(se.values()):,} mentions, {len(se):,} distinct terms\n")
for s, n in se.most_common(20):
    print(f"    {s:32s} {n:3,}")
