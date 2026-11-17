import json, glob, collections, statistics as st
L = lambda x: x if isinstance(x, list) else ([] if not x else [x])
meta = {}
for f in glob.glob("chunks/chunk_*_ids.json"):
    for r in json.load(open(f)): meta[r["id"]] = r["sample"]
regex_v = {r["id"]: r["regex_value"] for r in json.load(open("sample_pct.json"))}
C = {}
for f in sorted(glob.glob("coded/chunk_*.jsonl")):
    for line in open(f):
        line = line.strip()
        if line:
            r = json.loads(line); C[r["id"]] = r["code"]
print("coded:", len(C), "of", len(meta), " by sample:", collections.Counter(meta[i] for i in C))
A, S, K = "activity_capacity_change", "symptom_severity_change", "crash_change"
ch = {i: c for i, c in C.items() if meta[i] != "pct_statement" and c.get("first_person_patient") and c.get("describes_change")}
def show(label, sub):
    n = len(sub); p = lambda f: f"{100*sum(1 for c in sub if f(c))/n:.0f}%"
    print(f"\n### {label}: n={n}")
    print(" activity mentioned", p(lambda c: c[A] != "not_mentioned"), "| symptoms", p(lambda c: c[S] != "not_mentioned"), "| crashes", p(lambda c: c[K] != "not_mentioned"))
    print(" cost of activity", p(lambda c: c["cost_of_activity_mentioned"]), "| fluctuation", p(lambda c: c["fluctuation_mentioned"]), "| restriction explains symptoms", p(lambda c: c["activity_restriction_explains_symptoms"]), "| questionnaire gap", p(lambda c: c.get("questionnaire_gap")))
    both = [c for c in sub if c[A] in ("up","down","same") and c[S] in ("better","worse","same")]
    dis = [c for c in both if (c[A]=="up" and c[S]!="better") or (c[A]=="down" and c[S]!="worse") or (c[A]=="same" and c[S]!="same")]
    if both: print(f" both directions stated: n={len(both)}, disagree {100*len(dis)/len(both):.0f}%")
    print(" change ONLY as activity", p(lambda c: c[A] in ("up","down") and c[S] in ("not_mentioned",)), "| ONLY as symptoms", p(lambda c: c[S] in ("better","worse") and c[A] == "not_mentioned"))
    for key in ("domains_changed", "units"):
        cc = collections.Counter(x for c in sub for x in set(L(c[key]))); print(f" {key}:", ", ".join(f"{k} {100*v/n:.0f}%" for k, v in cc.most_common(14)))
show("ALL change narratives", list(ch.values()))
for s in ("improve_title", "worsen_title"): show(s, [c for i, c in ch.items() if meta[i] == s])
print("\nquestionnaire_gap phrases:"); 
for c in list(ch.values())[:200]:
    if c.get("questionnaire_gap"): print("  -", c["questionnaire_gap"])
# percent statements
P = {i: c for i, c in C.items() if meta[i] == "pct_statement"}
hit = {i: c["self_rated_percent"] for i, c in P.items() if isinstance(c.get("self_rated_percent"), (int, float))}
print(f"\n### PCT SAMPLE n={len(P)}: coder finds a current self-rating in {len(hit)} ({100*len(hit)/max(len(P),1):.0f}%) = regex precision")
print(f" regex value within 5 pts of coder value: {100*sum(abs(v-regex_v[i])<=5 for i,v in hit.items())/max(len(hit),1):.0f}%")
g = collections.defaultdict(list)
for i, v in hit.items(): g[P[i]["current_severity"]].append(v)
for t in ["very_severe","bedbound","housebound","severe","moderate","mild","recovered_or_remission","unstated"]:
    xs = sorted(g[t])
    if xs: print(f"  {t:24s} median {st.median(xs):5.0f}  IQR {xs[len(xs)//4]:.0f}-{xs[3*len(xs)//4]:.0f}  n={len(xs)}")
# agreement with DeepSeek on overlap
D = {}
for line in open("out_all.jsonl"):
    r = json.loads(line)
    if "code" in r: D[r["id"]] = r["code"]
ov = [i for i in D if i in C]
def kappa(key):
    pairs = [(str(D[i][key]), str(C[i][key])) for i in ov]
    po = sum(a == b for a, b in pairs) / len(pairs)
    ca, cb = collections.Counter(a for a, _ in pairs), collections.Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in ca) / len(pairs) ** 2
    return po, (po - pe) / (1 - pe) if pe < 1 else float("nan")
print(f"\n### Agreement Sonnet vs DeepSeek on {len(ov)} overlapping posts (raw agreement, Cohen's kappa)")
for key in ("describes_change", A, S, K, "activity_restriction_explains_symptoms", "cost_of_activity_mentioned", "fluctuation_mentioned", "current_severity"):
    po, k = kappa(key); print(f"  {key:40s} {100*po:4.0f}%  k={k:.2f}")
