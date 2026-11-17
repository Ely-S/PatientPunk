import json, sys, collections
def load(p): return {json.loads(l)["id"]: json.loads(l)["code"] for l in open(p) if l.strip()}
A, B = load(sys.argv[1]), load(sys.argv[2])
ids = [i for i in B if i in A]
FIELDS = ["first_person_patient","describes_change","activity_capacity_change","symptom_severity_change","crash_change",
 "activity_restriction_explains_symptoms","cost_of_activity_mentioned","fluctuation_mentioned","current_severity"]
def kappa(pairs):
    n = len(pairs); po = sum(a == b for a, b in pairs) / n
    ca, cb = collections.Counter(a for a, _ in pairs), collections.Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in ca) / n**2
    return po, ((po - pe) / (1 - pe) if pe < 1 else float("nan"))
print(f"n={len(ids)}")
for f in FIELDS:
    po, k = kappa([(str(A[i][f]), str(B[i][f])) for i in ids]); print(f"  {f:40s} {100*po:4.0f}%  kappa={k:.2f}")
pp = [(A[i]["self_rated_percent"], B[i]["self_rated_percent"]) for i in ids]
num = lambda x: isinstance(x, (int, float))
both = [(a, b) for a, b in pp if num(a) and num(b)]
pres = sum((num(a)) == (num(b)) for a, b in pp)
print(f"  self_rated_percent: presence agreement {100*pres/len(pp):.0f}%; both present n={len(both)}, within 5 pts {sum(abs(a-b)<=5 for a,b in both)}/{len(both)}")
