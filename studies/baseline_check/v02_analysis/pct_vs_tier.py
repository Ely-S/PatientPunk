import sqlite3, sys, re, hashlib, csv, collections, statistics as st
csv.field_size_limit(sys.maxsize)
db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
LEVEL = re.compile(r"\b(?:i'?m|i am|im|i feel(?: like)?|i'?d say i'?m|currently|now)\s+(?:at\s+)?(?:about\s+|around\s+|maybe\s+|roughly\s+|only\s+|like\s+)?(\d{1,3})\s?%\s*(?:of\s+(?:my\s+)?(?:normal|old self|former self|usual self|pre[- ]?(?:covid|illness|sick)\w*|healthy self|capacity|functioning|function|old life|baseline)|functional|functioning|recovered|back to normal|normal|healthy|of normal|capacity)\b"
                   r"|\bi'?m\s+at\s+(?:about\s+|around\s+|maybe\s+|roughly\s+|only\s+|like\s+)?(\d{1,3})\s?%"
                   r"|\b(\d{1,3})\s?%\s+(?:of\s+(?:my\s+)?(?:normal|old self|former self|usual self|pre[- ]?(?:covid|illness|sick)\w*|healthy self|old life)|functional|functioning|recovered|back to normal|of normal)\b", re.I)
per = collections.defaultdict(list)
for q in ("select coalesce(title,'')||'. '||coalesce(selftext,''), author from posts", "select body, author from comments"):
    for text, a in db.execute(q):
        if not text or not a or '%' not in text: continue
        for m in LEVEL.finditer(text):
            ctx = text[max(0,m.start()-40):m.end()+40].lower()
            if re.search(r"\b(better|improv|worse|sure|chance|percent of (people|patients)|of people|of patients|battery|oxygen|o2|spo2|sat)", ctx): continue
            v = int(next(g for g in m.groups() if g))
            if 0 <= v <= 100: per[hashlib.sha256(a.encode()).hexdigest()].append(v)
print("authors with a level-% statement:", len(per))
rows = {r["author_hash"]: r for r in csv.DictReader(open(sys.argv[2]))}
def single(v):
    xs = [x.strip().lower() for x in (v or "").split("|") if x.strip()]
    return xs[0] if len(xs) == 1 else None
for field, order in [("functional_status_tier", ["bedbound","housebound","severe","moderate","mild","mostly_functional"]),
                     ("illness_trajectory", ["worsening","relapsing","stable","improving","recovered"])]:
    g = collections.defaultdict(list)
    for h, vals in per.items():
        r = rows.get(h); t = single(r[field]) if r else None
        if t: g[t].append(st.median(vals))
    print(f"\n{field}: median self-rated % (IQR), n authors")
    for t in order:
        xs = sorted(g[t]); n = len(xs)
        if n: print(f"  {t:18s} {st.median(xs):5.0f}  ({xs[n//4]:.0f}-{xs[3*n//4]:.0f})  n={n}")
