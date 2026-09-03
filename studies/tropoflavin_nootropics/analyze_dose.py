"""Historical proximity-based dose analysis over pipeline A report text.

Pipeline B now extracts explicit treatment-dose pairs. This script retains the
older pipeline A sensitivity analysis, where doses are recovered from report
text within a bounded window of a 7,8-DHF alias.
"""
from __future__ import annotations
import collections, json, math, sqlite3, sys

from study_support import (
    PROXIMITY_ALIAS as ALIAS,
    StudyPaths,
    doses_near,
    proximity_dose_bin as bin_of,
    readonly_sqlite_uri,
)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SIG = {"strong": 3, "moderate": 2, "weak": 1, "n/a": 0, None: 0, "": 0}


ORDER = ["1-9 mg", "10-19 mg", "20-29 mg", "30-49 mg", "50-99 mg", "100-1000 mg"]

c = sqlite3.connect(readonly_sqlite_uri(StudyPaths.from_environment().database), uri=True)
c.row_factory = sqlite3.Row
rows = list(c.execute("""
    SELECT r.user_id, r.post_id, r.sentiment, r.signal_strength, r.side_effects,
           COALESCE(p.title,'') || ' ' || COALESCE(p.body_text,'') AS txt, p.post_date
    FROM treatment_reports r JOIN posts p ON p.post_id = r.post_id"""))

print(f"{len(rows):,} reports joined to text")
have_alias = [r for r in rows if ALIAS.search(r["txt"])]
print(f"{len(have_alias):,} contain a resolvable alias in their own text")

recs = []
for r in have_alias:
    ds = [d for d in (bin_of(x) for x in doses_near(r["txt"])) if d]
    if not ds:
        continue
    # a report quoting several doses votes once, at its lowest stated dose
    b = min(set(ds), key=ORDER.index)
    recs.append((r["user_id"], b, r["sentiment"], r["signal_strength"],
                 r["side_effects"], r["post_date"], len(set(ds)) > 1))
print(f"{len(recs):,} reports yielded a plausible 7,8-DHF dose "
      f"({100*len(recs)/len(rows):.1f}% of all reports)")
print(f"{sum(1 for x in recs if x[6]):,} of those quoted more than one dose bin\n")

# one vote per user: most recent, ties by signal strength
best = {}
for u, b, s, g, se, pd_, _ in sorted(recs, key=lambda x: (x[5] or 0, SIG.get(x[3], 0)), reverse=True):
    best.setdefault(u, (b, s, se))

by = collections.defaultdict(list)
for b, s, se in best.values():
    by[b].append((s, se))


def wilson(k, n, z=1.96):
    if not n: return (0.0, 0.0)
    p = k / n
    d = 1 + z*z/n
    ctr = (p + z*z/(2*n)) / d
    hw = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / d
    return (100*(ctr-hw), 100*(ctr+hw))


print(f"{'dose':<14}{'users':>6}{'positive':>10}{'  95% CI':>16}{'  neg':>6}{'  any SE':>9}")
print("-"*64)
for b in ORDER:
    v = by.get(b, [])
    n = len(v)
    if not n: continue
    pos = sum(1 for s, _ in v if s == "positive")
    neg = sum(1 for s, _ in v if s == "negative")
    se  = sum(1 for _, x in v if x and x not in ("[]", "none", ""))
    lo, hi = wilson(pos, n)
    print(f"{b:<14}{n:>6}{100*pos/n:>9.1f}%   [{lo:>4.1f}, {hi:>4.1f}]{100*neg/n:>5.1f}%{100*se/n:>8.1f}%")

tn = sum(len(v) for v in by.values())
tp = sum(1 for v in by.values() for s, _ in v if s == "positive")
ts = sum(1 for v in by.values() for _, x in v if x and x not in ("[]", "none", ""))
print("-"*64)
print(f"{'all dosed':<14}{tn:>6}{100*tp/tn:>9.1f}%{'':>16}{'':>5}{100*ts/tn:>8.1f}%")

print("\n\nSide effects named, by dose bin")
print("="*64)
for b in ORDER:
    v = by.get(b, [])
    if not v: continue
    cnt = collections.Counter()
    users_with = 0
    for _, x in v:
        if not x or x in ("[]", "none", ""): continue
        try: items = json.loads(x)
        except Exception: continue
        if not items: continue
        users_with += 1
        for i in items:
            cnt[str(i).strip().lower()] += 1
    top = ", ".join(f"{k} ({n})" for k, n in cnt.most_common(6)) or "—"
    print(f"\n{b}  ({users_with}/{len(v)} users named any, "
          f"{cnt.total()/users_with if users_with else 0:.1f} effects each)")
    print(f"   {top}")
