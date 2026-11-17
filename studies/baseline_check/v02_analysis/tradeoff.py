import sqlite3, sys, re, random, collections
random.seed(3)
db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
P = {
 "fine as long as I rest/pace/do nothing": re.compile(r"\b(?:i'?m|i am|i feel|i'?m mostly|symptoms are|it'?s)\s+(?:\w+\s+){0,2}?(?:ok|okay|fine|good|stable|manageable|alright|better)\s+(?:\w+\s+){0,2}?(?:as long as|if|provided)\s+i\s+(?:don'?t\s+(?:do|push|overdo|exert)|rest|pace|stay\s+(?:in bed|home|in|still)|do\s+(?:nothing|very little|little)|avoid|keep\s+(?:still|resting)|lie)", re.I),
 "better because I do less": re.compile(r"\b(?:better|improved|stable|fewer crashes|less pem|less fatigue)\b[^.!?\n]{0,30}\b(?:because|since|now that)\s+i\s+(?:\w+\s+){0,2}?(?:quit|stopped working|stopped exercis\w*|do less|am doing less|rest more|pace|cut back|reduced my|gave up|left my job|stay in bed|don'?t do)", re.I),
 "doing more, symptoms same": re.compile(r"\b(?:doing|do|can do|able to do)\s+(?:a lot |much |a bit |slightly )?more\b[^.!?\n]{0,50}\b(?:but|yet|while|and)\b[^.!?\n]{0,30}\b(?:same|no worse|not worse|still feel|symptoms (?:haven'?t|are still|remain))", re.I),
 "pacing hides change (generic)": re.compile(r"\b(?:symptoms|fatigue)\b[^.!?\n]{0,40}\b(?:because i'?m pacing|because i pace|due to pacing|thanks to pacing|from pacing|since i started pacing)", re.I),
}
c = collections.Counter(); auth = collections.defaultdict(set); ex = collections.defaultdict(list)
for q in ("select coalesce(title,'')||'. '||coalesce(selftext,''), author from posts", "select body, author from comments"):
    for t, a in db.execute(q):
        if not t: continue
        for k, rx in P.items():
            m = rx.search(t)
            if m:
                c[k] += 1; auth[k].add(a)
                s = t[max(0, m.start()-120): m.end()+120].replace("\n", " ")
                if len(ex[k]) < 8: ex[k].append(s)
                elif random.random() < 0.02: ex[k][random.randrange(8)] = s
for k in P:
    print(f"\n## {k}: {c[k]} texts, {len(auth[k])} authors")
    for s in ex[k][:5]: print("  -", s[:300])
