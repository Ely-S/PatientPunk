"""Item 1: what change matters most, blind recode of the 242 change posts (3 Sonnet coders, 20-post overlap)."""
import json, collections
meta = json.load(open("meta.json")); ov = set(meta["overlap_ids"])
L = lambda p: [json.loads(l) for l in open(p) if l.strip()]
c0, c1, c2 = L("coded_0.jsonl"), L("coded_1.jsonl"), L("coded_2.jsonl")
first = {r["id"]: r for r in c0 + c2}
first.update({r["id"]: r for r in c1 if r["id"] not in ov})
assert set(first) == set(meta["all_ids"]), len(first)
n = len(first); cat = collections.Counter(r["category"] for r in first.values())
print(f"n={n}")
for k, v in cat.most_common(): print(f"  {k:12s} {v:4d}  {100*v/n:4.0f}%")
gw = sum(r["global_wording"] for r in first.values()); print(f"global wording anywhere in post: {gw} ({100*gw/n:.0f}%)")
for name, cs in (("batch 0", c0), ("batch 1 (excl overlap)", [r for r in c1 if r["id"] not in ov]), ("batch 2", c2)):
    c = collections.Counter(r["category"] for r in cs); print(f"  {name}: n={len(cs)} global {c['global']} symptom {c['symptom']} activity {c['activity']} trajectory {c['trajectory']}")
second = {r["id"]: r for r in c1 if r["id"] in ov}
pairs = [(first[i]["category"], second[i]["category"]) for i in ov]
po = sum(a == b for a, b in pairs) / len(pairs)
ca, cb = collections.Counter(a for a, _ in pairs), collections.Counter(b for _, b in pairs)
pe = sum(ca[k] * cb[k] for k in ca) / len(pairs) ** 2
print(f"overlap n={len(pairs)} agreement {100*po:.0f}% kappa {(po-pe)/(1-pe):.2f}")
for a, b in pairs:
    if a != b: print("   disagree:", a, "vs", b)
gp = [(first[i]["global_wording"], second[i]["global_wording"]) for i in ov]
print("global_wording overlap agreement:", sum(a == b for a, b in gp), "/", len(gp))
