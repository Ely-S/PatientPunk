import sqlite3, sys, re, random, json, collections
random.seed(0)
db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
P = {
 "pct_self": re.compile(r"\b(?:i'?m|i am|im|at|about|maybe|around|back to|now)\s+(?:at\s+)?(?:about\s+|around\s+|maybe\s+)?(\d{1,3})\s?%\s*(?:of\s+(?:my\s+)?(?:normal|old self|former self|baseline|pre[- ]?covid|healthy|health|capacity|functioning|function)|recovered|better|back|functional|functioning|healthy|normal|improved)?", re.I),
 "pct_recovered": re.compile(r"\b(\d{1,3})\s?%\s+(?:recovered|better|back|functional|functioning|healthy|normal|improved|of (?:my )?(?:normal|old self|former self|baseline|pre[- ]?covid|healthy self|capacity))", re.I),
 "can_now": re.compile(r"\bi\s+(?:can|could)\s+(?:now|finally|actually)\s+(?:\w+\s+){0,1}?(\w+)", re.I),
 "can_no_longer": re.compile(r"\bi\s+(?:can(?:'?t| ?not)|couldn'?t)\s+(?:even\s+)?(\w+)\s+(?:\w+\s+){0,3}?(?:anymore|any more|without crashing|without a crash)", re.I),
 "without_crashing": re.compile(r"\b(\w+(?:\s+\w+){0,4})\s+without\s+(?:crashing|a crash|pem|triggering pem|getting pem)", re.I),
 "crash_freq": re.compile(r"\bcrash(?:es|ing)?\s+(?:once|twice|\d+\s+times|every|a few times|multiple times)\s+(?:a|per|every)?\s*(day|week|month|year)", re.I),
 "steps": re.compile(r"\b(\d{1,2},?\d{3}|\d{3,5})\s*(?:k\s*)?steps\b", re.I),
 "upright": re.compile(r"\bupright\s+(?:for\s+)?(?:about\s+)?(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)", re.I),
 "walk_dist": re.compile(r"\bwalk(?:ed|ing)?\s+(?:for\s+)?(?:about\s+)?(\d+(?:\.\d+)?)\s*(minutes?|mins?|miles?|km|blocks?|hours?)", re.I),
 "baseline_change": re.compile(r"\bbaseline\s+(?:has\s+|is\s+|was\s+)?(improved|dropped|lowered|raised|went down|went up|got worse|got better|worsened|shifted|declined|increased|decreased|tanked|plummeted)", re.I),
 "new_baseline": re.compile(r"\b(?:new|lower|higher|worse|better)\s+baseline\b", re.I),
 "good_days_ratio": re.compile(r"\b(\d+|more|fewer|less)\s+good days\b", re.I),
 "survey_critique": re.compile(r"\b(?:questionnaire|survey|sf-?36|promis|chalder|scale)s?\b[^.!?\n]{0,120}\b(?:doesn'?t|don'?t|didn'?t|can'?t|fail|not)\s+(?:\w+\s+){0,2}?(?:capture|reflect|measure|account|ask|show|represent)", re.I),
 "pem_delay": re.compile(r"\b(?:pem|crash)[^.!?\n]{0,60}\b(\d+|one|two|three|a)\s*(?:-|to)?\s*(?:\d+\s*)?(hours?|days?)\s+(?:later|after)", re.I),
 "trade_off": re.compile(r"\b(?:if i|when i|every time i)\s+(\w+(?:\s+\w+){0,4})[^.!?\n]{0,40}\b(?:i (?:crash|pay for it|get pem|am wiped|need (?:a|two|three|\d+) days?))", re.I),
}
counts = collections.Counter(); caps = {k: collections.Counter() for k in P}
samples = {k: [] for k in P}; seen = collections.Counter()
authors = {k: set() for k in P}
def scan(rows):
    for text, author in rows:
        if not text: continue
        for k, rx in P.items():
            for m in rx.finditer(text):
                counts[k] += 1; seen[k] += 1; authors[k].add(author)
                if m.groups(): caps[k][" ".join(g.lower() for g in m.groups() if g)] += 1
                s = text[max(0, m.start()-160): m.end()+160].replace("\n", " ")
                if len(samples[k]) < 40: samples[k].append(s)
                elif random.random() < 40/seen[k]: samples[k][random.randrange(40)] = s
scan(db.execute("select coalesce(title,'')||'. '||coalesce(selftext,''), author from posts"))
scan(db.execute("select body, author from comments"))
out = {k: {"matches": counts[k], "authors": len(authors[k]), "top": caps[k].most_common(60), "samples": samples[k]} for k in P}
json.dump(out, open("patterns.json", "w"), indent=1)
for k in P: print(k, counts[k], len(authors[k]), caps[k].most_common(25))
