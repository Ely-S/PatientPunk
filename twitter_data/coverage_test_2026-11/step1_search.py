#!/usr/bin/env python3
"""Step 1 of the Twitter coverage test: every post naming ivermectin (nine spellings) in one week,
from X's full-archive search, compared with what the November 2025 scrape holds for that week.

Token: read from the file ~/.config/x_api/bearer_token (chmod 600) or the X_BEARER_TOKEN variable.
It is never printed. Every page of the API reply is saved raw under pages/ before anything is computed.

    python step1_search.py --dry-run          # show the requests, send nothing
    python step1_search.py --counts           # also fetch weekly match counts 2020-2025 (no posts read)
    python step1_search.py                    # the week: 2025-09-01 to 2025-09-07
"""
import ssl, certifi, argparse, json, os, re, sys, time, urllib.parse, urllib.request, urllib.error, datetime, pathlib

HERE = pathlib.Path(__file__).parent
QUERY = ('(ivermectin OR ivermectine OR ivermectina OR stromectol OR ivomec OR ivm OR ivermec '
         'OR "horse paste" OR "horse dewormer") -is:retweet')
START, END = "2025-09-01T00:00:00Z", "2025-09-08T00:00:00Z"
FIELDS = "created_at,author_id,conversation_id,referenced_tweets,in_reply_to_user_id,public_metrics,lang"
API = "https://api.x.com/2"
PRICE_PER_POST = 0.005
REQUEST_CAP = 20          # cost guard: 20 pages of 100 posts is at most about $10 in one run
WORD = re.compile(r"\bivermectin\b", re.I)


def token() -> str:
    p = pathlib.Path.home() / ".config" / "x_api" / "bearer_token"
    t = p.read_text().strip() if p.exists() else os.environ.get("X_BEARER_TOKEN", "").strip()
    if not t:
        sys.exit("no token: put it in ~/.config/x_api/bearer_token (chmod 600) or X_BEARER_TOKEN")
    return t


def get(path: str, params: dict, tok: str, log: list) -> dict:
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(6):
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}", "User-Agent": "patientpunk-coverage-test"})
        try:
            with urllib.request.urlopen(req, timeout=60, context=ssl.create_default_context(cafile=certifi.where())) as r:
                body = json.loads(r.read().decode()); log.append({"path": path, "status": r.status, "at": datetime.datetime.now(datetime.UTC).isoformat()})
                return body
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            log.append({"path": path, "status": e.code, "at": datetime.datetime.now(datetime.UTC).isoformat(), "detail": detail})
            if e.code == 429:
                reset = int(e.headers.get("x-rate-limit-reset", "0") or 0); wait = max(5, min(900, reset - int(time.time()) + 1))
                print(f"  rate limited, waiting {wait}s", flush=True); time.sleep(wait); continue
            if e.code in (402, 403):
                sys.exit(f"{path} refused with HTTP {e.code}: {detail}\nThis endpoint is not open to this account; stop here and decide.")
            if e.code >= 500 and attempt < 5:
                time.sleep(2 ** attempt); continue
            raise
    sys.exit("gave up after retries")


def paginate(path: str, params: dict, tok: str, outdir: pathlib.Path, log: list):
    outdir.mkdir(parents=True, exist_ok=True)
    data, next_token, page = [], None, 0
    while True:
        if len(log) >= REQUEST_CAP:
            print(f"  request cap {REQUEST_CAP} reached; stopping with {len(data)} items", flush=True); break
        p = dict(params, **({"next_token": next_token} if next_token else {}))
        body = get(path, p, tok, log); page += 1
        (outdir / f"page_{page:03d}.json").write_text(json.dumps(body, ensure_ascii=False, indent=1))
        data.extend(body.get("data", []))
        next_token = body.get("meta", {}).get("next_token")
        print(f"  page {page}: {len(body.get('data', []))} items, total {len(data)}", flush=True)
        if not next_token: break
        time.sleep(1.1)   # search/all allows about one request per second
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--counts", action="store_true")
    args = ap.parse_args()
    search = {"query": QUERY, "start_time": START, "end_time": END, "max_results": 100, "tweet.fields": FIELDS,
              "expansions": "author_id", "user.fields": "username,verified"}
    counts = {"query": QUERY, "start_time": "2020-01-01T00:00:00Z", "end_time": "2025-11-13T00:00:00Z", "granularity": "day"}
    if args.dry_run:
        print("would request:")
        if args.counts: print(f"  GET {API}/tweets/counts/all?{urllib.parse.urlencode(counts)}")
        print(f"  GET {API}/tweets/search/all?{urllib.parse.urlencode(search)}  (then follow next_token)")
        print(f"cost: ${PRICE_PER_POST} per post returned; the set holds 25 for this week, so expect well under $1 unless the gap is large; hard cap {REQUEST_CAP} requests"); return
    tok = token(); log = []; run_dir = HERE / f"run_{datetime.datetime.now(datetime.UTC):%Y%m%dT%H%M%SZ}"; run_dir.mkdir()
    manifest = {"query": QUERY, "week": [START, END], "fields": FIELDS, "started_utc": datetime.datetime.now(datetime.UTC).isoformat()}
    if args.counts:
        print("counts 2020-2025 by day:")
        try:
            rows = paginate("/tweets/counts/all", counts, tok, run_dir / "counts_pages", log)
            (run_dir / "counts_by_day.json").write_text(json.dumps(rows, indent=1))
            manifest["counts_total"] = sum(r.get("tweet_count", 0) for r in rows); print(f"  total matching posts 2020-2025: {manifest['counts_total']:,}")
        except SystemExit as e:
            print(f"  counts not available: {e}"); manifest["counts_error"] = str(e)
    print("search/all for the week:")
    posts = paginate("/tweets/search/all", search, tok, run_dir / "search_pages", log)
    (run_dir / "week_posts.json").write_text(json.dumps(posts, ensure_ascii=False, indent=1))
    # ---- compare with the set
    setw = {str(x["tweet_id"]): x for x in json.load(open(HERE / "set_week_2025-09-01_ivermectin.json"))}
    api = {str(p["id"]): p for p in posts}
    both = set(api) & set(setw); api_only = set(api) - set(setw); set_only = set(setw) - set(api)
    api_only_word = [i for i in api_only if WORD.search(api[i]["text"])]; api_only_alias = [i for i in api_only if not WORD.search(api[i]["text"])]
    is_reply = lambda p: any(r.get("type") == "replied_to" for r in p.get("referenced_tweets", []) or [])
    res = {
        "population_api": len(api), "in_set": len(setw), "in_both": len(both),
        "scrape_recall_on_word": round(len(both) / max(1, len(both) + len(api_only_word)), 3),
        "api_only_naming_ivermectin": len(api_only_word), "api_only_alias_only": len(api_only_alias),
        "set_only_deleted_since": len(set_only),
        "api_reply_share": round(sum(1 for p in api.values() if is_reply(p)) / max(1, len(api)), 3),
        "api_lang": dict(sorted(((l, sum(1 for p in api.values() if p.get("lang") == l)) for l in {p.get("lang") for p in api.values()}), key=lambda kv: -kv[1])),
        "requests": len(log), "estimated_cost_usd": round(len(posts) * PRICE_PER_POST, 2),
    }
    manifest.update(res, finished_utc=datetime.datetime.now(datetime.UTC).isoformat(), request_log=log)
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print("\nresult:"); [print(f"  {k:<30} {v}") for k, v in res.items()]
    print(f"\nsaved under {run_dir}")

if __name__ == "__main__":
    main()
