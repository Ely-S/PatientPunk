"""Label the reverse-route LDN posts for personal use, to measure what the co-term route loses.

Reads the reverse-route pull, splits authors into those the corpus already holds as LDN
authors and those it does not, and asks the model whether each post reports the author's
own use of the drug. Writes personal_use_labels.json and prints the comparison.
"""
import json, os, re, sys, time, urllib.request, collections, zipfile, pathlib

# The reverse-route run folder: $REVERSE_ROUTE_RUN, else the one beside this script.
HERE = pathlib.Path(__file__).resolve().parent
RUN = pathlib.Path(os.environ.get("REVERSE_ROUTE_RUN", HERE / "run_reverse_route_20261118T030628Z"))
# The treatment_wise_tweets archive: $TWITTER_DATASET_ZIP, else twitter_dataset.zip in twitter_data/.
DATASET_ZIP = pathlib.Path(os.environ.get("TWITTER_DATASET_ZIP", HERE.parent / "twitter_dataset.zip"))
OUT = RUN/"personal_use_labels.json"
MODEL = "deepseek/deepseek-v4.1-flash"
BATCH = 25

def key():
    """$OPENROUTER_API_KEY, else the repository's .env."""
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    for line in (HERE.parents[1] / ".env").read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("no key")

SYSTEM = (
 "You label tweets about low-dose naltrexone (LDN / naltrexone). For each numbered tweet decide "
 "whether the author is reporting THEIR OWN use of the drug: they take it, have taken it, are "
 "starting or stopping it, describe their own dose, or describe an effect it had on them.\n"
 "own = the author's own use or their own experience of taking it.\n"
 "other = someone else's use (a relative, a patient, a study, a general recommendation), a question, "
 "news, a link, advocacy, or a mention with no personal experience.\n"
 "A first-person sentence about wanting or considering it, with no actual use, is other.\n"
 'Return ONLY a JSON array, one object per tweet, in order: [{"n": 1, "label": "own"}, ...]'
)

def ask(batch, k):
    body = json.dumps({
        "model": MODEL, "temperature": 0,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": "\n".join(
                         f'{i+1}. {(p.get("text") or "").replace(chr(10)," ")[:400]}' for i, p in enumerate(batch))}],
    }).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                txt = json.loads(r.read())["choices"][0]["message"]["content"]
            m = re.search(r"\[.*\]", txt, re.S)
            arr = json.loads(m.group(0))
            return {int(o["n"]): str(o["label"]).lower() for o in arr if "n" in o}
        except Exception as e:
            if attempt == 3: print("  batch failed:", e); return {}
            time.sleep(2 * (attempt + 1))

def main():
    posts = [p for p in json.load(open(RUN/"ldn_posts.json"))["posts"] if isinstance(p, dict)]
    # corpus LDN posts and authors
    ids, auths = set(), set()
    z = zipfile.ZipFile(DATASET_ZIP)
    DRUG = re.compile(r'\b(ldn|low[- ]dose naltrexone|naltrexone)\b', re.I)
    for n in z.namelist():
        if n.endswith(".json") and re.search(r"ldn|naltrex", n, re.I) and "__MACOSX" not in n:
            d = json.loads(z.read(n).decode("utf-8", "replace"))
            for r in (d if isinstance(d, list) else d.get("tweets", [])):
                if isinstance(r, dict) and DRUG.search(r.get("text") or ""):
                    ids.add(str(r.get("tweet_id"))); auths.add(str(r.get("author_id")))

    k = key(); labels = {}
    if OUT.exists(): labels = json.load(open(OUT))
    todo = [p for p in posts if str(p["id"]) not in labels]
    print(f"{len(posts)} posts, {len(labels)} already labelled, {len(todo)} to do "
          f"({(len(todo)+BATCH-1)//BATCH} calls)")
    for i in range(0, len(todo), BATCH):
        b = todo[i:i+BATCH]
        got = ask(b, k)
        for j, p in enumerate(b):
            labels[str(p["id"])] = got.get(j+1, "unknown")
        json.dump(labels, open(OUT, "w"))
        print(f"  {min(i+BATCH, len(todo))}/{len(todo)}", flush=True)

    # report
    grp = lambda p: "captured" if str(p["author_id"]) in auths else "missing"
    tot = collections.Counter(); own = collections.Counter(); unk = collections.Counter()
    authors = collections.defaultdict(set)
    for p in posts:
        g = grp(p); tot[g] += 1; authors[g].add(str(p["author_id"]))
        l = labels.get(str(p["id"]), "unknown")
        if l == "own": own[g] += 1
        elif l == "unknown": unk[g] += 1
    print("\n| group | patients | LDN posts | personal-use posts | share of posts |")
    print("|---|---:|---:|---:|---:|")
    for g in ("captured", "missing"):
        print(f"| {g} | {len(authors[g])} | {tot[g]} | {own[g]} | {100*own[g]/tot[g]:.0f}% |")
    T = own["captured"] + own["missing"]
    print(f"\nPersonal-use posts total {T}. The missing group holds {own['missing']} = "
          f"{100*own['missing']/T:.1f}% of them.")
    print(f"Unlabelled: {unk['captured']+unk['missing']}")
    print(f"In-corpus personal-use posts: "
          f"{sum(1 for p in posts if str(p['id']) in ids and labels.get(str(p['id']))=='own')} of {T}")

main()
