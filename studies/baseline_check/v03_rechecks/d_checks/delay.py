"""Item 2: crash/PEM delay statements, including 'next day' phrasing. Counts texts (posts+comments) per delay bin."""
import sqlite3, sys, re, json, random, collections
db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
CRASH = r"(?:crash(?:es|ed|ing)?|pem|post[- ]exertional|flare(?:s|d)?(?: up)?|pay for it|paid for it)"
NUM = r"(?:\d+|a|an|one|two|three|four|five|a couple of|a few|couple)"
DELAY = (r"(?:(?:the\s+)?next\s+(?:day|morning)|the\s+(?:day|morning)\s+after|the\s+following\s+(?:day|morning)|tomorrow|"
         r"(?:" + NUM + r")\s*(?:(?:-|to)\s*\d+\s*)?(?:hours?|hrs?|days?)\s+(?:later|after(?:wards?)?)|"
         r"(?:" + NUM + r")\s*(?:(?:-|to)\s*\d+\s*)?(?:hours?|hrs?|days?)\s+delay(?:ed)?|"
         r"delayed\s+(?:by\s+)?(?:" + NUM + r")\s*(?:(?:-|to)\s*\d+\s*)?(?:hours?|hrs?|days?))")
RX = re.compile(rf"\b{CRASH}\b[^.!?\n]{{0,80}}?\b(?P<d1>{DELAY})|\b(?P<d2>{DELAY})\b[^.!?\n]{{0,80}}?\b{CRASH}\b", re.I)
W = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "a couple of": 2, "couple": 2}
def bin_of(d):
    d = d.lower()
    if re.search(r"next|day after|morning after|following|tomorrow", d): return "next day / day after"
    m = re.match(r"(\d+|a couple of|couple|a few|a|an|one|two|three|four|five)\s*(?:(?:-|to)\s*(\d+)\s*)?(hours?|hrs?|days?)", re.sub(r"^delayed\s+(?:by\s+)?", "", d))
    if not m: return "other"
    if m.group(2): return "a range (e.g. 24-72 hours, 1-3 days)"
    if m.group(1) == "a few": return "a few hours/days"
    n = int(m.group(1)) if m.group(1).isdigit() else W[m.group(1)]
    days = n / 24 if m.group(3).startswith("h") else n
    if days < 1: return "same day (under 24 hours)"
    if days <= 1: return "1 day / 24 hours"
    if days <= 2: return "2 days / 48 hours"
    if days <= 3: return "3 days / 72 hours"
    return "4+ days"
bins = collections.Counter(); samples = collections.defaultdict(list); n_texts = 0
q = '"crash" OR "crashes" OR "crashed" OR "crashing" OR "pem" OR "exertional" OR "flare" OR "flared" OR "flares" OR "pay for it" OR "paid for it"'
for sql in (f"select coalesce(p.title,'')||'. '||coalesce(p.selftext,'') from posts p join posts_fts f on p.rowid=f.rowid where posts_fts match ?",
            f"select c.body from comments c join comments_fts f on c.rowid=f.rowid where comments_fts match ?"):
    for (t,) in db.execute(sql, (q,)):
        hit = set()
        for m in RX.finditer(t or ""):
            b = bin_of(m.group("d1") or m.group("d2")); hit.add(b)
            if len(samples[b]) < 400: samples[b].append(t[max(0, m.start()-60): m.end()+60].replace("\n", " "))
        if hit: n_texts += 1
        for b in hit: bins[b] += 1
print("texts with any delay statement:", n_texts)
for b, n in bins.most_common(): print(f"{n:7d}  {b}")
random.seed(7)
check = [(b, s) for b in bins for s in random.sample(samples[b], min(len(samples[b]), max(2, round(50 * bins[b] / sum(bins.values())))))]
json.dump(check, open("delay_precision_sample.json", "w"), indent=1)
print("precision sample:", len(check))
