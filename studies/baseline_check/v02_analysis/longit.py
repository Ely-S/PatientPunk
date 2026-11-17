import json, collections, statistics as st, math
lev = [json.loads(l) for l in open("level.jsonl")]
# one rating per (author, post): the median of matches in that text
per_post = collections.defaultdict(list); meta = {}
for r in lev:
    per_post[(r["a"], r["id"])].append(r["v"]); meta[(r["a"], r["id"])] = (r["ts"], r["tiers"])
rows = [(a, pid, meta[(a,pid)][0], st.median(v), meta[(a,pid)][1]) for (a,pid), v in per_post.items()]
print("ratings (author x text):", len(rows), " authors:", len({r[0] for r in rows}))
vals = [r[3] for r in rows]
print("distribution: >=90: %.0f%%  >=80: %.0f%%  <=30: %.0f%%  median %d" % (100*sum(v>=90 for v in vals)/len(vals), 100*sum(v>=80 for v in vals)/len(vals), 100*sum(v<=30 for v in vals)/len(vals), st.median(vals)))
print("\nTime-aligned known groups (tier word in the same text, exactly one):")
g = collections.defaultdict(list)
for a, pid, ts, v, tiers in rows:
    if len(tiers) == 1: g[tiers[0]].append(v)
for t in ["verysevere","bedbound","bedridden","housebound","severe","moderate","mild"]:
    xs = sorted(g[t]); n = len(xs)
    if n: print(f"  {t:12s} median {st.median(xs):4.0f}  IQR {xs[n//4]:.0f}-{xs[3*n//4]:.0f}  n={n}")
by_a = collections.defaultdict(list)
for a, pid, ts, v, tiers in rows: by_a[a].append((ts, v))
pairs_short, pairs_long, deltas_long = [], [], []
spans = []
for a, xs in by_a.items():
    xs.sort()
    if len(xs) >= 2: spans.append(max(v for _, v in xs) - min(v for _, v in xs))
    for (t1, v1), (t2, v2) in zip(xs, xs[1:]):
        days = (t2 - t1) / 86400
        if 0.5 <= days <= 14: pairs_short.append((v1, v2))
        if days >= 90: pairs_long.append((v1, v2, days))
print(f"\nauthors with >=2 dated ratings: {len(spans)}; range across their ratings: median {st.median(spans)} pts, >=20 pts: {100*sum(s>=20 for s in spans)/len(spans):.0f}%")
def corr(p):
    x, y = zip(*[(a, b) for a, b, *_ in p]); return st.correlation(x, y)
d = [b - a for a, b in pairs_short]
print(f"pairs 0.5-14 days apart: n={len(d)}  r={corr(pairs_short):.2f}  SD of change={st.pstdev(d):.1f}  |change|<=10: {100*sum(abs(x)<=10 for x in d)/len(d):.0f}%")
print(f"  -> smallest detectable change (1.96*sqrt2*SEM, SEM=SDdiff/sqrt2) ~ {1.96*st.pstdev(d):.0f} points")
dl = [b - a for a, b, _ in pairs_long]
print(f"pairs >=90 days apart: n={len(dl)}  r={corr(pairs_long):.2f}  mean change {st.mean(dl):+.1f}  up>=10: {100*sum(x>=10 for x in dl)/len(dl):.0f}%  down>=10: {100*sum(x<=-10 for x in dl)/len(dl):.0f}%")
ad = sorted(abs(x) for x in d)
print(f"short pairs |change|: median {st.median(ad)}, 75th {ad[3*len(ad)//4]}, 90th {ad[9*len(ad)//10]}; exactly equal: {100*sum(x==0 for x in ad)/len(ad):.0f}%")
nz = [x for x in d if x != 0]
print(f"short pairs excluding identical repeats: n={len(nz)}, median |change| {st.median(abs(x) for x in nz)}")
