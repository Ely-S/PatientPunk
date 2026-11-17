import sqlite3, sys, re, random
db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
D = {
 "PEM / crashes / pacing": r"\b(crash\w*|pem|post[- ]exertional|pacing|push(ed|ing)? through|payback)\b",
 "Physical activity (walk, exercise, stairs)": r"\b(walk\w*|steps|exercis\w*|gym|run(ning)?|hik\w*|stairs|bike|cycling|swim\w*)\b",
 "Self-care / chores (shower, cook, clean)": r"\b(shower\w*|cook\w*|dishes|laundry|groceries|grocery|clean(ing)?|dress(ing)?|chores)\b",
 "Work / school": r"\b(work(ing)? (full|part)|back to work|my job|career|school|universit\w*|college|office)\b",
 "Social / family life": r"\b(friends?|family|kids?|children|social(ise|ize|izing|ising)?|partner|husband|wife|date|dating)\b",
 "Cognition (fog, reading, focus)": r"\b(brain fog|fog|read(ing)?|focus|concentrat\w*|memory|think(ing)? clearly)\b",
 "Upright / orthostatic (stand, HR)": r"\b(stand(ing)?|upright|sit(ting)? up|heart rate|pots|tachycardia|bpm)\b",
 "Sleep": r"\b(sleep\w*|insomnia)\b",
 "Pain": r"\b(pain|ache\w*|headache\w*|migraine\w*)\b",
 "Leisure / travel / hobbies": r"\b(hobb\w*|travel\w*|vacation|holiday|concert|music|garden\w*|play(ing)? (guitar|piano|games?))\b",
 "Self-rated % (strict)": "STRICT",
 "Baseline": r"\bbaseline\b",
 "Good days / bad days": r"\b(good|bad) days?\b",
 "Fatigue / energy": r"\b(fatigue\w*|energy|exhaust\w*|tired)\b",
}
exec(open("level_rx.py").read())
R = {k: (LEVEL if v == "STRICT" else re.compile(v, re.I)) for k, v in D.items()}
def tally(q):
    rows = [t for (t,) in db.execute(q) if t and len(t) > 300]
    random.seed(0); rows = random.sample(rows, min(len(rows), 20000))
    return len(rows), {k: sum(1 for t in rows if r.search(t)) / len(rows) for k, r in R.items()}
rec_q = """select title||'. '||selftext from posts where subreddit in ('LongHaulersRecovery','cfsrecovery')
  or (subreddit in ('covidlonghaulers','cfs','LongCovid') and (lower(title) like '%recover%' or lower(title) like '%improv%' or lower(title) like '%remission%' or lower(title) like '%success%' or lower(title) like '%better%')) and title not like '%?%'"""
oth_q = """select title||'. '||selftext from posts where subreddit in ('covidlonghaulers','cfs','LongCovid')
  and not (lower(title) like '%recover%' or lower(title) like '%improv%' or lower(title) like '%remission%' or lower(title) like '%success%' or lower(title) like '%better%')"""
n1, a = tally(rec_q); n2, b = tally(oth_q)
print(f"improvement/recovery posts n={n1}; other illness posts n={n2}")
print(f"{'domain':44s} {'improve%':>9s} {'other%':>7s} {'ratio':>6s}")
for k in sorted(D, key=lambda k: -a[k]):
    print(f"{k:44s} {100*a[k]:8.1f} {100*b[k]:7.1f} {a[k]/b[k]:6.2f}")
