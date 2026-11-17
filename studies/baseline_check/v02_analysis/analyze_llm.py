import json, collections, statistics as st
R = [json.loads(l) for l in open("out_all.jsonl")]
err = [r for r in R if "error" in r]; R = [r for r in R if "code" in r]
print("coded", len(R), "errors", len(err))
tin = sum(r["tok"][0] for r in R); tout = sum(r["tok"][1] for r in R); print("tokens in/out", tin, tout)
ch = [r["code"] for r in R if r["sample"] in ("improve_title", "worsen_title") and r["code"]["first_person_patient"] and r["code"]["describes_change"]]
print(f"\nCHANGE NARRATIVES (first-person, describes change): n={len(ch)}")
def pct(f): return f"{100*sum(1 for c in ch if f(c))/len(ch):.0f}%"
A, S, C = "activity_capacity_change", "symptom_severity_change", "crash_change"
print("activity mentioned:", pct(lambda c: c[A] != "not_mentioned"), " symptoms mentioned:", pct(lambda c: c[S] != "not_mentioned"), " crashes mentioned:", pct(lambda c: c[C] != "not_mentioned"))
print("cost of activity:", pct(lambda c: c["cost_of_activity_mentioned"]), " fluctuation:", pct(lambda c: c["fluctuation_mentioned"]), " restriction explains symptoms:", pct(lambda c: c["activity_restriction_explains_symptoms"]))
print("\nactivity x symptoms crosstab:")
ct = collections.Counter((c[A], c[S]) for c in ch)
acts = ["up","down","same","fluctuating","not_mentioned"]; syms = ["better","worse","same","mixed","fluctuating","not_mentioned"]
print(f"{'':14s}" + "".join(f"{s:>14s}" for s in syms))
for a in acts: print(f"{a:14s}" + "".join(f"{ct[(a,s)]:14d}" for s in syms))
both = [c for c in ch if c[A] in ("up","down","same") and c[S] in ("better","worse","same")]
dis = [c for c in both if (c[A]=="up" and c[S] in ("worse","same")) or (c[A]=="down" and c[S] in ("better","same")) or (c[A]=="same" and c[S]!="same")]
print(f"\nwhere both directions are stated (n={len(both)}): activity and symptoms DISAGREE in {100*len(dis)/len(both):.0f}%")
only_act = sum(1 for c in ch if c[A] in ("up","down") and c[S] == "not_mentioned")
only_sym = sum(1 for c in ch if c[S] in ("better","worse") and c[A] == "not_mentioned")
print(f"change described ONLY as activity: {100*only_act/len(ch):.0f}%   ONLY as symptoms: {100*only_sym/len(ch):.0f}%")
for lab, key in (("domains", "domains_changed"), ("units", "units")):
    c = collections.Counter(x for r in ch for x in r[key]); print(f"\n{lab}:", ", ".join(f"{k} {100*v/len(ch):.0f}%" for k, v in c.most_common(18)))
for s in ("improve_title", "worsen_title"):
    sub = [r["code"] for r in R if r["sample"] == s and r["code"]["describes_change"]]
    c = collections.Counter(x for r in sub for x in r["domains_changed"])
    print(f"\n{s} (n={len(sub)}) top domains:", ", ".join(f"{k} {100*v/len(sub):.0f}%" for k, v in c.most_common(8)))
print("\nwhat_matters_most (sample):"); import random; random.seed(1)
for c in random.sample(ch, 40): print("  -", c["what_matters_most"])
# percent sample
P = [r for r in R if r["sample"] == "pct_statement"]
src = {x["id"]: x for x in json.load(open("sample_pct.json"))}
cur = [(r, r["code"]["self_rated_percent"]) for r in P]
hit = [(r, v) for r, v in cur if isinstance(v, (int, float))]
print(f"\nPCT SAMPLE: n={len(P)}; LLM finds a current self-rating in {len(hit)} ({100*len(hit)/len(P):.0f}% regex precision proxy)")
agree = sum(1 for r, v in hit if abs(v - src[r["id"]]["regex_value"]) <= 5); print(f"  regex value within 5 pts of LLM value: {100*agree/len(hit):.0f}%")
g = collections.defaultdict(list)
for r, v in hit: g[r["code"]["current_severity"]].append(v)
for t in ["very_severe","bedbound","housebound","severe","moderate","mild","recovered_or_remission","unstated"]:
    xs = sorted(g[t])
    if xs: print(f"  {t:24s} median {st.median(xs):5.0f}  IQR {xs[len(xs)//4]:.0f}-{xs[3*len(xs)//4]:.0f}  n={len(xs)}")
