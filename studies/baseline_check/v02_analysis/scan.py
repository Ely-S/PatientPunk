import sqlite3, sys, re, hashlib, json
exec(open("level_rx.py").read())  # defines LEVEL, EXCL
db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
POS = re.compile(r"\bi (?:can now|can finally|could finally|was finally able to|was able to|managed to|am (?:now )?able to)\s+((?:[a-z']+\s+){1,3}[a-z']+)", re.I)
NEG = re.compile(r"\bi (?:can'?t|cannot|couldn'?t|am unable to|am not able to|can no longer)\s+(?:even\s+)?((?:[a-z']+\s+){1,3}[a-z']+)", re.I)
TIER = re.compile(r"\b(bed ?bound|bedridden|house ?bound|very severe|severe|moderate|mild)\b", re.I)
lev = open("level.jsonl", "w"); mil = open("milestones.jsonl", "w")
for kind, q in (("p", "select id, coalesce(title,'')||'. '||coalesce(selftext,''), author, created_utc from posts"),
                ("c", "select id, body, author, created_utc from comments")):
    for pid, text, a, ts in db.execute(q):
        if not text or not a or a in ("[deleted]", "AutoModerator"): continue
        h = hashlib.sha256(a.encode()).hexdigest()
        if "%" in text:
            for m in LEVEL.finditer(text):
                ctx = text[max(0, m.start()-40): m.end()+40].lower()
                if EXCL.search(ctx): continue
                v = int(next(g for g in m.groups() if g))
                if v <= 100:
                    tiers = sorted({t.lower().replace(" ", "") for t in TIER.findall(text)})
                    lev.write(json.dumps({"id": kind+pid, "a": h, "ts": ts, "v": v, "tiers": tiers,
                                          "snip": text[max(0, m.start()-200): m.end()+200]}) + "\n")
        low = text.lower()
        if " i " in f" {low} ":
            for rx, sign in ((POS, 1), (NEG, -1)):
                for m in rx.finditer(text):
                    mil.write(json.dumps({"a": h, "ts": ts, "s": sign, "ph": m.group(1).lower()}) + "\n")
print("done")
