import json, collections, re
R = [json.loads(l) for l in open("coded.jsonl")]
U = [r for r in R if r["describes_change"]]
print("coded", len(R), "usable", len(U), collections.Counter(r["stratum"] for r in U))
def dist(rs):
    c = collections.Counter(r["captured"] for r in rs); n = len(rs)
    return ", ".join(f"{k} {100*c[k]/n:.0f}% ({c[k]})" for k in ("fully", "partly", "not"))
print("ALL:", dist(U))
for s in ("severe", "mild_moderate"): print(s, dist([r for r in U if r["stratum"] == s]))
sevs = collections.Counter(r["severity"] for r in U); print("severity stated:", sevs.most_common())
for grp, keys in (("bed/house/very severe", {"bedbound","housebound","very_severe","severe"}), ("mild/moderate/recovered", {"mild","moderate","recovered"})):
    print(grp, dist([r for r in U if r["severity"] in keys]))
qs = collections.Counter(); items = collections.Counter()
for r in U:
    seen = set()
    for x in r["captured_by"]:
        q = x.split(":")[0]; seen.add(q)
        if ":" in x: items[x.split(":")[1]] += 1
    for q in seen: qs[q] += 1
print("share of usable changes each Q helps capture:", {q: f"{100*qs[q]/len(U):.0f}%" for q in sorted(qs)})
print("Q2 items used:", items.most_common())
cap = [r for r in U if r["captured"] in ("fully","partly")]
only = collections.Counter()
for r in cap:
    s = {x.split(":")[0] for x in r["captured_by"]}
    if len(s) == 1: only[next(iter(s))] += 1
print("captured by one question only:", dict(only))
print("\nMISSING phrases:")
for r in U:
    if r["missing"]: print(f"{r['captured']:6s} {r['id']:9s} {r['missing']}")
