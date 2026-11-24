"""Build daily mention counts per drug for the Twitter corpus and r/covidlonghaulers.

Writes only aggregates (no text, no user ids) to ../data/:
  daily_counts.csv   platform, drug, date, posts, threads, authors
  reddit_totals.csv  date, posts, threads (all subreddit activity, the denominator)
  twitter_ldn_posts.csv / twitter_ivm_posts.csv  per-post date, likes, first-post flag, labels (no text)

    uv run python twitter_data_news_blog/analysis/extract.py
"""
import collections, csv, json, pathlib, re, sqlite3, datetime as dt

ROOT = pathlib.Path(__file__).resolve().parents[2]
TW = ROOT / "twitter_data/databases/tweets.db"
RD = ROOT / "twitter_data/databases/clh_ldn_twmatch.db"
OUT = pathlib.Path(__file__).resolve().parents[1] / "data"

# Same keywords the scrape used, grouped into one concept per drug. Generic words
# (antiviral, cytokine, epa, dha, immunotherapy, oxygen therapy) are left out.
DRUGS = {
    "LDN": r"\bldn\b|naltrex\w*|naltexone|naltraxone",
    "Ivermectin": r"ivermectin\w*|stromectol|ivomec|horse paste|horse dewormer",
    "Paxlovid": r"paxlovid|nirmatrelvir",
    "Metformin": r"metformin|glucophage",
    "Hydroxychloroquine": r"hydroxychloroquine|plaquenil|\bhcq\b",
    "Vitamin D": r"vitamin d\b|vitamin d3|vit d\b|cholecalciferol",
    "Vitamin C": r"vitamin c\b|ascorbic acid",
    "Zinc": r"\bzinc\b",
    "Nattokinase": r"nattokinase",
    "Lumbrokinase": r"lumbrokinase",
    "Serrapeptase": r"serrapeptase",
    "Quercetin": r"quercetin",
    "Melatonin": r"melatonin",
    "Fluvoxamine": r"fluvoxamine",
    "Remdesivir": r"remdesivir",
    "Maraviroc": r"maraviroc|selzentry",
    "Evusheld": r"evusheld|tixagevimab|cilgavimab",
    "IVIG": r"\bivig\b|intravenous immunoglobulin",
    "HBOT": r"\bhbot\b|hyperbaric",
    "Aspirin": r"aspirin",
    "Famotidine": r"famotidine|pepcid",
    "H1 antihistamines": r"antihistamine|cetirizine|zyrtec|fexofenadine|allegra|loratadine|claritin",
    "Statins": r"\bstatins?\b|atorvastatin|rosuvastatin",
    "CoQ10": r"coq10|coenzyme q10|ubiquinol|ubiquinone",
    "Omega-3": r"omega-?3|fish oil",
    "Interferon": r"interferon",
    "Azithromycin": r"azithromycin",
}
PATS = {k: re.compile(v) for k, v in DRUGS.items()}


def day(ts):
    return dt.datetime.fromtimestamp(ts, dt.UTC).strftime("%Y-%m-%d")


def twitter():
    con = sqlite3.connect(TW)
    counts = collections.defaultdict(lambda: [0, set()])
    for pid, uid, ts, text in con.execute("select post_id, user_id, post_date, body_text from posts"):
        t = (text or "").lower()
        d = day(ts)
        for k, p in PATS.items():
            if p.search(t):
                c = counts[(k, d)]; c[0] += 1; c[1].add(uid)
    rows = [("twitter", k, d, n, n, len(a)) for (k, d), (n, a) in counts.items()]
    # per-post tables for the composition analysis (no text, no ids written)
    labels = json.load(open(ROOT / "twitter_data/adhoc_results/ldn_results.json"))
    reps = {}
    for pid, s in con.execute("select post_id, sentiment from treatment_reports where run_id=4"):
        reps[pid] = s
    ivm_reps = dict(con.execute("select post_id, sentiment from treatment_reports where run_id in (6,7)"))
    for name, pat, rp, lab in [("ldn", PATS["LDN"], reps, labels), ("ivm", PATS["Ivermectin"], ivm_reps, {})]:
        seen = set(); out = []
        q = "select post_id, user_id, post_date, body_text, metadata from posts order by post_date"
        for pid, uid, ts, text, meta in con.execute(q):
            if not pat.search((text or "").lower()):
                continue
            m = json.loads(meta or "{}").get("metrics", {})
            L = lab.get(pid, {})
            out.append({"date": day(ts), "likes": m.get("like_count", 0), "retweets": m.get("retweet_count", 0),
                        "first_post": int(uid not in seen), "report": rp.get(pid, ""),
                        "labelled": int(bool(L)), "personal_use": L.get("personal_use", ""),
                        "lab_sentiment": L.get("sentiment", "")})
            seen.add(uid)
        with open(OUT / f"twitter_{name}_posts.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    return rows


def reddit():
    con = sqlite3.connect(RD)
    parent, info = {}, []
    for pid, par, ts, uid, title, body in con.execute(
            "select post_id, parent_id, post_date, user_id, title, body_text from posts"):
        if par:
            parent[pid] = par
        info.append((pid, ts, uid, ((title or "") + " " + (body or "")).lower()))

    def root(p):
        seen = 0
        while p in parent and seen < 500:
            p = parent[p]; seen += 1
        return p

    counts = collections.defaultdict(lambda: [0, set(), set()])
    totals = collections.defaultdict(lambda: [0, set()])
    for pid, ts, uid, t in info:
        d = day(ts); r = root(pid)
        tt = totals[d]; tt[0] += 1; tt[1].add(r)
        for k, p in PATS.items():
            if p.search(t):
                c = counts[(k, d)]; c[0] += 1; c[1].add(r); c[2].add(uid)
    rows = [("reddit", k, d, n, len(th), len(a)) for (k, d), (n, th, a) in counts.items()]
    with open(OUT / "reddit_totals.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["date", "posts", "threads"])
        for d in sorted(totals):
            w.writerow([d, totals[d][0], len(totals[d][1])])
    return rows


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    rows = twitter(); print("twitter rows", len(rows), flush=True)
    rows += reddit(); print("all rows", len(rows), flush=True)
    with open(OUT / "daily_counts.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["platform", "drug", "date", "posts", "threads", "authors"])
        w.writerows(sorted(rows))
