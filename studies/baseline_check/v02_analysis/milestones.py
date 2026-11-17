import json, csv, sys, collections, re
csv.field_size_limit(sys.maxsize)
tier = {}
for r in csv.DictReader(open(sys.argv[1])):
    xs = [x.strip().lower() for x in r["functional_status_tier"].split("|") if x.strip()]
    if len(xs) == 1: tier[r["author_hash"]] = xs[0]
grp = {"bedbound": "severe+", "housebound": "severe+", "severe": "severe+", "moderate": "moderate", "mild": "mild+", "mostly_functional": "mild+"}
SKIP = {"be","feel","think","say","find","believe","tell","imagine","wait","understand","help","stop","get","see","seem","afford",
        "remember","explain","describe","figure","stand" if False else "", "really","even","just","still","do","have","go","make","take","handle","deal","live","put","keep","know","want","try","use","give","speak" if False else ""}
FILL = {"even","really","actually","just","barely","hardly","still","now","finally","also","only","not","properly","easily","fully","comfortably","longer","no"}
STOP = {"the","a","an","my","to","for","of","in","on","with","and","it","that","this","more","than","any","anymore","without","at","up","out","around","too","much","as","so","very","about","or"}
VERBS_KEEP = {"stand","sit","walk","shower","bathe","wash","brush","cook","clean","read","watch","work","drive","exercise","run","talk","speak",
              "leave","climb","lift","eat","sleep","concentrate","focus","think","type","text","use","look","tolerate","play","listen","go","get","do","hold","carry","dress","socialize","socialise","lie","roll","feed","chew","swallow","write","study","shop","garden","hike","swim","bike","cycle","travel","laugh","sing","hug","wash"}
def norm(ph):
    w = [x for x in re.findall(r"[a-z']+", ph) if x not in FILL]
    if not w or w[0] not in VERBS_KEEP: return None
    obj = [x for x in w[1:] if x not in STOP][:1]
    return " ".join([w[0]] + obj)
cnt = {s: collections.defaultdict(set) for s in (1, -1)}
by_grp = {s: collections.defaultdict(lambda: collections.defaultdict(set)) for s in (1, -1)}
n_auth = collections.defaultdict(set)
for line in open("milestones.jsonl"):
    r = json.loads(line); k = norm(r["ph"])
    if not k: continue
    cnt[r["s"]][k].add(r["a"])
    g = grp.get(tier.get(r["a"]))
    if g: by_grp[r["s"]][k][g].add(r["a"]); n_auth[g].add(r["a"])
print("authors per group with any milestone:", {g: len(v) for g, v in n_auth.items()})
for s, lab in ((1, "CAN NOW / WAS ABLE TO"), (-1, "CAN'T / CAN NO LONGER")):
    print(f"\n== {lab}: top phrases by distinct authors (share of authors in severe+ / moderate / mild+ groups, %)")
    for k, a in sorted(cnt[s].items(), key=lambda kv: -len(kv[1]))[:45]:
        sh = [100*len(by_grp[s][k][g])/len(n_auth[g]) for g in ("severe+","moderate","mild+")]
        print(f"  {k:22s} {len(a):6d}   {sh[0]:5.2f} {sh[1]:5.2f} {sh[2]:5.2f}   sev/mild={sh[0]/max(sh[2],1e-9):4.1f}")
