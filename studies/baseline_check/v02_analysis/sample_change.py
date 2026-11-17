import sqlite3, sys, json, random
random.seed(42)
db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
base = """select id, subreddit, created_utc, title, selftext from posts
  where subreddit in ('covidlonghaulers','cfs','LongCovid','LongHaulersRecovery','cfsrecovery','mecfs','cfsme')
  and length(selftext) between 400 and 5000 and author not in ('[deleted]','AutoModerator') and ({})"""
imp = "lower(title) like '%improv%' or lower(title) like '%recover%' or lower(title) like '%better%' or lower(title) like '%remission%' or lower(title) like '%progress%' or lower(title) like '%success%'"
wor = "lower(title) like '%worse%' or lower(title) like '%relapse%' or lower(title) like '%setback%' or lower(title) like '%declin%' or lower(title) like '%deteriorat%' or lower(title) like '%getting worse%'"
out = []
for label, cond in (("improve_title", imp), ("worsen_title", wor)):
    rows = db.execute(base.format(cond)).fetchall()
    for r in random.sample(rows, 300):
        out.append({"id": r[0], "sample": label, "sub": r[1], "ts": r[2], "text": f"{r[3]}\n\n{r[4]}"})
    print(label, len(rows))
json.dump(out, open("sample_change.json", "w"))
