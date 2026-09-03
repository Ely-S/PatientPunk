"""Sample first-person intent statements. See NOTES.md."""
import json, re, sys, random
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PAT = re.compile(r"(?i)(tropoflavin|hydroxyflavone|\b7[ .,'-]{0,2}8[ .,'-]{0,2}dhf\b|\bdhf\b)")
corpus = json.load(open("studies/tropoflavin_nootropics/source/subreddit_posts.json", encoding="utf-8"))
items = []
for p in corpus:
    t = ((p.get("title") or "") + " " + (p.get("body") or "")).strip()
    if PAT.search(t): items.append(t)
    for c in p["comments"]:
        b = (c.get("body") or "").strip()
        if PAT.search(b): items.append(b)

# first-person intent statements near a mention
INTENT = re.compile(r"(?i)\b(i take|i'?m taking|i use|i started|i tried|taking it for|for my|to help (with|my)|i bought|i've been (taking|using)|helps? (my|with))\b")
picked, seen = [], set()
random.seed(7)
random.shuffle(items)
for t in items:
    m = PAT.search(t)
    if not m or not INTENT.search(t): continue
    s = " ".join(t.split())
    if len(s) < 80 or len(s) > 400: continue
    key = s[:60]
    if key in seen: continue
    seen.add(key); picked.append(s)
    if len(picked) >= 14: break
for i, s in enumerate(picked, 1):
    print(f"{i:2d}. {s}\n")
