import json, glob, re, collections, random, statistics as st
meta = {}
for f in glob.glob("chunks/chunk_*_ids.json"):
    for r in json.load(open(f)): meta[r["id"]] = r["sample"]
C = {}
for f in glob.glob("coded/chunk_*.jsonl"):
    for l in open(f):
        if l.strip(): r = json.loads(l); C[r["id"]] = r["code"]
ch = [c for i, c in C.items() if meta[i] != "pct_statement" and c["first_person_patient"] and c["describes_change"]]
ACT = re.compile(r"\b(walk|work|job|exercis|run|gym|hike|shower|cook|clean|house|out|travel|drive|function|able|activit|do |doing|errand|school|social|friends|outing|steps|upright|stand|bed|life|normal life|play|dance|lift)", re.I)
SYM = re.compile(r"\b(pain|fog|fatigue|tired|energy|sleep|symptom|nausea|headache|migraine|heart|palpitation|breath|dizz|anxiety|depress|mood|gut|tinnitus|smell|taste|hives|rash|pem|crash|flare|fever|vision|numb|tingl|hr\b|pots)", re.I)
wm = [c["what_matters_most"] or "" for c in ch]
cat = collections.Counter()
for w in wm:
    a, s = bool(ACT.search(w)), bool(SYM.search(w))
    cat["activity/function only" if a and not s else "symptom only" if s and not a else "both" if a and s else "neither (global e.g. 'feel normal', 'recovered')"] += 1
print(f"what_matters_most (n={len(wm)}):", {k: f"{100*v/len(wm):.0f}%" for k, v in cat.most_common()})
random.seed(5); print("  samples:", random.sample([w for w in wm if w], 15))
# ladder: bootstrap CIs for mean tier per rung
import csv, sys
csv.field_size_limit(sys.maxsize)
