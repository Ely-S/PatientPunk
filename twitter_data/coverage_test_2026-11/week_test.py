#!/usr/bin/env python3
"""One-week coverage test of the keyword corpus against X, any drug.
Counts first (no posts read), then the week's posts if under --max-posts, then a lookup of corpus-only ids.
Requests are capped separately for counts, search and lookup. Full long-form text is requested (note_tweet).
  python week_test.py --drug '(LDN OR naltrexone)' --corpus set_week_2025-09-01_ldn.json --tag ldn [--dry-run] [--max-posts 300]
"""
import argparse, collections, datetime, json, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent)); import step1_search as s

CO = '("long covid" OR longcovid OR LC OR PASC)'
CO_NARROW = '("long covid" OR longcovid)'
FIELDS = s.FIELDS + ",note_tweet"
COTERMS = {"long covid": r"long.?covid", "LC": r"\bLC\b", "PASC": r"\bPASC\b", "long haul": r"long.?haul", "post covid": r"post.?covid"}
full = lambda p: (p.get("note_tweet") or {}).get("text") or p["text"]
terms = lambda t: [k for k, r in COTERMS.items() if re.search(r, t, re.I)]
isrep = lambda p: any(r.get("type") == "replied_to" for r in p.get("referenced_tweets") or [])

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--drug", required=True); ap.add_argument("--corpus", required=True); ap.add_argument("--tag", required=True)
    ap.add_argument("--start", default=s.START); ap.add_argument("--end", default=s.END); ap.add_argument("--max-posts", type=int, default=300); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    queries = {"drug_plus_co": f"{a.drug} {CO} -is:retweet", "drug_only": f"{a.drug} -is:retweet", "drug_plus_co_narrow": f"{a.drug} {CO_NARROW} -is:retweet"}
    win = {"start_time": a.start, "end_time": a.end}
    if a.dry_run:
        for k, q in queries.items(): print(f"counts/all  {k}: {q}")
        print(f"search/all  drug_plus_co if count <= {a.max_posts}, then GET /2/tweets?ids= for corpus-only; cost ${s.PRICE_PER_POST}/post"); return
    tok = s.token(); run = s.HERE / f"run_{a.tag}_{datetime.datetime.now(datetime.UTC):%Y%m%dT%H%M%SZ}"; run.mkdir()
    man = {"tag": a.tag, "queries": queries, "week": [a.start, a.end], "counts": {}}
    clog = []
    for k, q in queries.items():
        body = s.get("/tweets/counts/all", dict(query=q, granularity="day", **win), tok, clog)
        (run / f"counts_{k}.json").write_text(json.dumps(body, indent=1))
        man["counts"][k] = {"total": body["meta"]["total_tweet_count"], "by_day": {r["start"][:10]: r["tweet_count"] for r in sorted(body["data"], key=lambda r: r["start"])}}
        print(f"counts {k:<20} {man['counts'][k]['total']:>7}   {list(man['counts'][k]['by_day'].values())}")
    setw = {str(x["tweet_id"]): x for x in json.load(open(a.corpus))}; man["corpus_week"] = len(setw)
    n = man["counts"]["drug_plus_co"]["total"]
    if n > a.max_posts:
        print(f"count {n} exceeds --max-posts {a.max_posts}; not fetching. corpus has {len(setw)}."); (run / "manifest.json").write_text(json.dumps(man, indent=1)); return
    print(f"fetching about {n} posts, about ${n * s.PRICE_PER_POST:.2f}")
    slog = []; posts = []; nt = None; page = 0
    while True:
        p = dict(query=queries["drug_plus_co"], max_results=100, **{"tweet.fields": FIELDS, "expansions": "author_id", "user.fields": "username,verified"}, **win, **({"next_token": nt} if nt else {}))
        body = s.get("/tweets/search/all", p, tok, slog); page += 1; (run / f"search_page_{page:02d}.json").write_text(json.dumps(body, ensure_ascii=False, indent=1))
        posts += body.get("data", []); nt = body.get("meta", {}).get("next_token")
        if not nt or len(slog) >= 10: break
        import time; time.sleep(1.1)
    users = {}
    for f in run.glob("search_page_*.json"): users.update({u["id"]: u for u in json.load(open(f)).get("includes", {}).get("users", [])})
    api = {p["id"]: p for p in posts}; both = set(api) & set(setw); xonly = set(api) - set(setw); conly = set(setw) - set(api)
    llog = []; found, errs = {}, {}
    if conly:
        lk = s.get("/tweets", {"ids": ",".join(sorted(conly)), "tweet.fields": FIELDS, "expansions": "author_id", "user.fields": "username,verified"}, tok, llog)
        (run / "lookup_corpus_only.json").write_text(json.dumps(lk, ensure_ascii=False, indent=1))
        found = {t["id"]: t for t in lk.get("data", [])}; errs = {e.get("resource_id") or e.get("value"): e for e in lk.get("errors", [])}
    narrow = re.compile(COTERMS["long covid"] + "|longcovid", re.I)
    xo = [{"id": i, "user": users.get(api[i]["author_id"], {}).get("username"), "created": api[i]["created_at"], "len": len(full(api[i])), "note_tweet": bool(api[i].get("note_tweet")),
           "reply": isrep(api[i]), "coterms": terms(full(api[i])), "query_mismatch": not narrow.search(full(api[i])) and not re.search(COTERMS["LC"], full(api[i])) and not re.search(COTERMS["PASC"], full(api[i])),
           "text": full(api[i])} for i in sorted(xonly, key=lambda i: api[i]["created_at"])]
    co = [{"id": i, "user": setw[i]["author_username"], "len": len(setw[i]["text"]), "coterms": terms(setw[i]["text"]),
           "status": "still_on_x" if i in found else ("deleted" if "Not Found" in (errs.get(i, {}).get("title") or "") else "unauthorized"), "text": setw[i]["text"]} for i in conly]
    res = {"x_visible": len(api), "corpus": len(setw), "in_both": len(both), "x_only": len(xonly), "corpus_only": len(conly),
           "x_only_real_miss": sum(1 for x in xo if not x["query_mismatch"]), "x_only_longform": sum(1 for x in xo if x["len"] > 280),
           "in_both_longform": sum(1 for i in both if len(setw[i]["text"]) > 280), "in_both_maxlen": max([len(setw[i]["text"]) for i in both] or [0]),
           "corpus_only_status": dict(collections.Counter(c["status"] for c in co)), "x_reply_share": round(sum(isrep(p) for p in api.values()) / max(1, len(api)), 2),
           "x_lang": dict(collections.Counter(p.get("lang") for p in api.values())), "requests": {"counts": len(clog), "search": len(slog), "lookup": len(llog)},
           "cost_usd": round((len(posts) + len(found)) * s.PRICE_PER_POST, 2)}
    man.update(result=res, x_only=xo, corpus_only=co, finished=datetime.datetime.now(datetime.UTC).isoformat())
    (run / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1))
    print("\nresult:"); [print(f"  {k:<22} {v}") for k, v in res.items()]
    print("\nX-only:"); [print(f"  {'MISMATCH' if x['query_mismatch'] else 'MISS    '} @{x['user']:<16} len {x['len']:>5} {'reply' if x['reply'] else 'orig '} {x['coterms']}  {x['text'][:120]!r}") for x in xo]
    print("\ncorpus-only:"); [print(f"  {c['status']:<12} @{c['user']:<16} len {c['len']:>4} {c['coterms']}  {c['text'][:120]!r}") for c in co]
    print(f"\nsaved under {run}")

if __name__ == "__main__": main()
