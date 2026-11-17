"""Item 4: blind coverage regrade vs the original (designer-fork) ratings."""
import json, collections, sys
OLD = sys.argv[1]
fork = {r["id"]: r for r in map(json.loads, open(OLD))}
blind = {}
for p in ("blind_0.jsonl", "blind_1.jsonl"):
    for l in open(p):
        if l.strip(): r = json.loads(l); blind[r["id"]] = r
print("blind judged", len(blind))
U = [i for i, r in blind.items() if r["describes_change"]]
print("blind: describes change", len(U))
def dist(rs):
    c = collections.Counter(rs); n = len(rs)
    return ", ".join(f"{k} {100*c[k]/n:.0f}% ({c[k]})" for k in ("fully", "partly", "not"))
print("BLIND  :", dist([blind[i]["captured"] for i in U]))
for s in ("severe", "mild_moderate"):
    print(f"  {s}:", dist([blind[i]["captured"] for i in U if fork[i]["stratum"] == s]))
print("FORK same posts:", dist([fork[i]["captured"] for i in U]))
pairs = [(fork[i]["captured"], blind[i]["captured"]) for i in U]
po = sum(a == b for a, b in pairs) / len(pairs)
ca, cb = collections.Counter(a for a, _ in pairs), collections.Counter(b for _, b in pairs)
pe = sum(ca[k]*cb[k] for k in ca) / len(pairs)**2
print(f"fork vs blind on {len(pairs)}: agreement {100*po:.0f}%, kappa {(po-pe)/(1-pe):.2f}")
print("crosstab fork->blind:", collections.Counter(pairs).most_common())
qs = collections.Counter()
for i in U:
    for q in {x.split(":")[0] for x in blind[i]["captured_by"] or []}: qs[q] += 1
print("share each Q helps capture (blind):", {q: f"{100*v/len(U):.0f}%" for q, v in sorted(qs.items())})
print("\nblind 'missing' (for theming):")
for i in U:
    if blind[i]["missing"]: print(f"  {blind[i]['captured']:6s} {i:9s} {blind[i]['missing']}")
