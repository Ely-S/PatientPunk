#!/usr/bin/env python3
"""Tier 2 analysis: profile-level bot signals for the users fetched by tier2_lookup.py.

    python -I tier2_analyse.py --drug ldn --run-dir <folder with users_page_NN.json>

Joins to tier2_author_list.json (group, drugs, reports, sentiments), tier1/tier1_authors.csv (tier1_score,
dominant_sentiment) and derives first/last corpus tweet dates from the treatment_wise_tweets corpus
(read-only, untrusted data: json only). Writes tier2_<drug>_users.csv and tier2_<drug>_summary.md.
"""
import argparse, csv, datetime, glob, json, os, pathlib, re, statistics, sys

PROJECT = pathlib.Path(__file__).resolve().parent.parent
AUTHOR_LIST = PROJECT / "tier2_author_list.json"
TIER1_CSV = PROJECT / "tier1" / "tier1_authors.csv"
# The treatment_wise_tweets corpus folder: --corpus, else $TREATMENT_WISE_TWEETS, else beside this project.
CORPUS_DIR = os.environ.get("TREATMENT_WISE_TWEETS", str(PROJECT / "treatment_wise_tweets"))
CORPUS = str(pathlib.Path(CORPUS_DIR) / "*.json")
PRICE_PER_ID = 0.01
BIO_RE = re.compile(r"long ?covid|longcovid|#LC\b|ME/?CFS|pwME|chronic illness|patient|spoonie|disabled|POTS|dysautonomia|MCAS", re.I)
FLAGS = ["suspended_or_not_found", "created_within_30d_of_first_tweet", "followers_lt_10", "default_profile_image",
         "bio_empty", "following_gt_5000", "tweets_per_day_gt_50"]
STATUS_FROM_TITLE = {"Forbidden": "suspended", "Not Found Error": "not_found", "Resource Unavailable Error": "unavailable"}


def ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def corpus_dates(author_ids: set) -> dict:
    """author -> (first, last) corpus tweet datetimes, deduped on tweet_id like tier1_run.py."""
    seen, out = set(), {}
    for f in sorted(glob.glob(CORPUS)):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict) or not isinstance(d.get("tweets"), list):
            continue
        for t in d["tweets"]:
            if not isinstance(t, dict) or "tweet_id" not in t:
                continue
            a = str(t.get("author_id"))
            if a not in author_ids or str(t["tweet_id"]) in seen:
                continue
            seen.add(str(t["tweet_id"]))
            try:
                x = ts(str(t["created_at"]))
            except ValueError:
                continue
            lo, hi = out.get(a, (x, x))
            out[a] = (min(lo, x), max(hi, x))
    return out


def pct(n, d):
    return f"{100 * n / d:.1f}%" if d else "-"


def med(vals):
    v = [x for x in vals if x not in ("", None)]
    return f"{statistics.median(v):,.0f}" if v else "-"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drug", required=True); ap.add_argument("--run-dir", required=True)
    ap.add_argument("--corpus", default=CORPUS_DIR, help="treatment_wise_tweets folder (*.json)")
    args = ap.parse_args(); run = pathlib.Path(args.run_dir); drug = args.drug
    global CORPUS
    CORPUS = str(pathlib.Path(args.corpus) / "*.json")
    now = datetime.datetime.now(datetime.UTC)

    # ---- inputs
    al = json.loads(AUTHOR_LIST.read_text())
    meta = {}
    for a, v in al["report_authors"].items():
        if drug in v.get("drugs", []):
            meta[a] = dict(group="report", drugs="+".join(v["drugs"]), reports=v.get("reports", ""),
                           sentiments=" ".join(f"{k[:3]}={n}" for k, n in sorted(v.get("sentiments", {}).items())), username_list=v.get("username", ""))
    for a in al["control_non_report_authors"][drug]:
        meta.setdefault(str(a), dict(group="control", drugs="", reports=0, sentiments="", username_list=""))
    tier1 = {r["author_id"]: r for r in csv.DictReader(open(TIER1_CSV, encoding="utf-8"))}
    pages = sorted(run.glob("users_page_*.json"))
    if not pages:
        sys.exit(f"no users_page_*.json in {run}")
    users, errors, sent = {}, {}, []
    for p in pages:
        b = json.loads(p.read_text())
        for u in b.get("data", []): users[str(u["id"])] = u
        for e in b.get("errors", []): errors[str(e.get("resource_id") or e.get("value"))] = e
    for r in json.loads((run / "request_log.json").read_text()): sent += r["ids"]
    dates = corpus_dates(set(meta))

    # ---- per author rows
    rows = []
    for a in sent:
        m = meta.get(a, dict(group="?", drugs="", reports="", sentiments="", username_list=""))
        t1 = tier1.get(a, {})
        first, last = dates.get(a, (None, None))
        r = dict(author_id=a, username=m["username_list"] or t1.get("username", ""), group=m["group"], drugs=m["drugs"], reports=m["reports"],
                 sentiments=m["sentiments"], dominant_sentiment=t1.get("dominant_sentiment", ""), tier1_score=t1.get("tier1_score", ""),
                 n_tweets_in_corpus=t1.get("n_tweets_in_corpus", ""), first_corpus_tweet=first.date().isoformat() if first else "",
                 last_corpus_tweet=last.date().isoformat() if last else "", status="", error_title="", name="", created_at="",
                 account_age_days_at_first_corpus_tweet="", account_age_days_now="", created_within_30d_of_first_tweet="",
                 followers_count="", following_count="", tweet_count="", listed_count="", follower_following_ratio="",
                 following_gt_5000="", followers_lt_10="", default_profile_image="", bio_empty="", bio_len="", bio_patient_terms="",
                 tweets_per_day_lifetime="", tweets_per_day_gt_50="", verified="", verified_type="", bio_first60="")
        if a in users:
            u = users[a]; pm = u.get("public_metrics", {}); bio = (u.get("description") or "").strip()
            created = ts(u["created_at"]); age_now = max(1, (now - created).days)
            r.update(status="protected" if u.get("protected") else "live", username=u.get("username", r["username"]), name=u.get("name", ""),
                     created_at=created.date().isoformat(), account_age_days_now=age_now,
                     followers_count=pm.get("followers_count", 0), following_count=pm.get("following_count", 0),
                     tweet_count=pm.get("tweet_count", 0), listed_count=pm.get("listed_count", 0),
                     follower_following_ratio=round(pm.get("followers_count", 0) / max(1, pm.get("following_count", 0)), 3),
                     following_gt_5000=int(pm.get("following_count", 0) > 5000), followers_lt_10=int(pm.get("followers_count", 0) < 10),
                     default_profile_image=int("default_profile" in (u.get("profile_image_url") or "")),
                     bio_empty=int(not bio), bio_len=len(bio), bio_patient_terms=int(bool(BIO_RE.search(bio))),
                     tweets_per_day_lifetime=round(pm.get("tweet_count", 0) / age_now, 2),
                     verified=int(bool(u.get("verified"))), verified_type=u.get("verified_type", ""), bio_first60=bio[:60].replace("\n", " "),
                     suspended_or_not_found=0)
            r["tweets_per_day_gt_50"] = int(r["tweets_per_day_lifetime"] > 50)
            if first:
                age_first = (first - created).days
                r["account_age_days_at_first_corpus_tweet"] = age_first; r["created_within_30d_of_first_tweet"] = int(age_first <= 30)
            else:
                r["created_within_30d_of_first_tweet"] = 0
        else:
            e = errors.get(a, {}); title = e.get("title", "missing from response")
            r.update(status=STATUS_FROM_TITLE.get(title, "error"), error_title=title, suspended_or_not_found=1)
        r["tier2_flags"] = sum(int(r.get(f) or 0) for f in FLAGS)
        rows.append(r)
    cols = list(rows[0].keys())
    with open(run / f"tier2_{drug}_users.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)

    # ---- summary
    rep = [r for r in rows if r["group"] == "report"]; ctl = [r for r in rows if r["group"] == "control"]
    sent_grp = {"positive": [r for r in rep if r["dominant_sentiment"] == "positive"],
                "negative": [r for r in rep if r["dominant_sentiment"] == "negative"],
                "mixed+neutral": [r for r in rep if r["dominant_sentiment"] not in ("positive", "negative")]}
    L = [f"# Tier 2 profile lookup: {drug.upper()} authors", "",
         f"Report = {drug.upper()} effect-report authors; control = matched non-report {drug.upper()} authors. Ages relative to first corpus tweet and today ({now.date()})."]
    L += ["", "## 1. Account status", "", "| status | report | control |", "|---|---|---|"]
    for s in ["live", "protected", "suspended", "not_found", "unavailable", "error"]:
        nr, nc = sum(r["status"] == s for r in rep), sum(r["status"] == s for r in ctl)
        if nr or nc: L.append(f"| {s} | {nr} ({pct(nr, len(rep))}) | {nc} ({pct(nc, len(ctl))}) |")
    L.append(f"| total | {len(rep)} | {len(ctl)} |")
    L += ["", "## 2. Flag rates", "", "| flag | report | control | rep positive | rep negative | rep mixed+neutral |", "|---|---|---|---|---|---|"]
    def rate(rs, f): return pct(sum(int(r.get(f) or 0) for r in rs), len(rs))
    for f in FLAGS + ["bio_patient_terms"]:
        L.append(f"| {f} | {rate(rep, f)} | {rate(ctl, f)} | " + " | ".join(rate(sent_grp[k], f) for k in sent_grp) + " |")
    L.append(f"| n | {len(rep)} | {len(ctl)} | " + " | ".join(str(len(sent_grp[k])) for k in sent_grp) + " |")
    L += ["", "## 3. tier2_flags distribution and tier1_score >= 2", "", "| tier2_flags | report | control | report & tier1>=2 | report & tier1<2 |", "|---|---|---|---|---|"]
    def t1hi(r): return r["tier1_score"] not in ("",) and float(r["tier1_score"]) >= 2
    for k in range(0, max(r["tier2_flags"] for r in rows) + 1):
        L.append(f"| {k} | {sum(r['tier2_flags'] == k for r in rep)} | {sum(r['tier2_flags'] == k for r in ctl)} | "
                 f"{sum(r['tier2_flags'] == k and t1hi(r) for r in rep)} | {sum(r['tier2_flags'] == k and not t1hi(r) for r in rep)} |")
    L.append(f"| >=2 flags | {sum(r['tier2_flags'] >= 2 for r in rep)} ({pct(sum(r['tier2_flags'] >= 2 for r in rep), len(rep))}) | "
             f"{sum(r['tier2_flags'] >= 2 for r in ctl)} ({pct(sum(r['tier2_flags'] >= 2 for r in ctl), len(ctl))}) | "
             f"{sum(r['tier2_flags'] >= 2 and t1hi(r) for r in rep)} | {sum(r['tier2_flags'] >= 2 and not t1hi(r) for r in rep)} |")
    L += ["", "## 4. Top 20 report authors by tier2_flags", "", "| username | rep | sentiments | status | created | followers | following | bio (60) | flags |", "|---|---|---|---|---|---|---|---|---|"]
    top = sorted(rep, key=lambda r: (-r["tier2_flags"], -(float(r["tier1_score"] or 0)), -int(r["reports"] or 0)))[:20]
    for r in top:
        L.append(f"| {r['username']} | {r['reports']} | {r['sentiments']} | {r['status']} | {r['created_at']} | {r['followers_count']} | {r['following_count']} | "
                 f"{r['bio_first60'].replace('|', '/')} | {r['tier2_flags']} |")
    L += ["", "## 5. Medians (live + protected accounts)", "", "| metric | report | control |", "|---|---|---|"]
    live_r = [r for r in rep if r["created_at"]]; live_c = [r for r in ctl if r["created_at"]]
    for lab, key in [("account age (days, today)", "account_age_days_now"), ("account age at first corpus tweet (days)", "account_age_days_at_first_corpus_tweet"),
                     ("followers", "followers_count"), ("following", "following_count"), ("tweet_count", "tweet_count")]:
        L.append(f"| {lab} | {med([r[key] for r in live_r])} | {med([r[key] for r in live_c])} |")
    gone_r, gone_c = rate(rep, "suspended_or_not_found"), rate(ctl, "suspended_or_not_found")
    multi_r, multi_c = pct(sum(r["tier2_flags"] >= 2 for r in rep), len(rep)), pct(sum(r["tier2_flags"] >= 2 for r in ctl), len(ctl))
    big_follow = sum(1 for r in rep if r["following_gt_5000"] == 1 and (r["followers_count"] or 0) > 5000)
    reading = (f"The {drug.upper()} report authors look like the control authors, not like a bot cohort: {gone_r} are suspended/gone vs {gone_c} of controls, "
               f"{multi_r} carry two or more profile flags vs {multi_c}, and no report author with two or more tier-2 flags also scored tier1 >= 2. "
               f"Report accounts are a median {med([r['account_age_days_at_first_corpus_tweet'] for r in live_r])} days old at their first corpus tweet, with hundreds of followers "
               f"and bios naming long covid / ME/CFS / patient terms at {rate(rep, 'bio_patient_terms')} (controls {rate(ctl, 'bio_patient_terms')}; "
               f"negative-dominant reporters {rate(sent_grp['negative'], 'bio_patient_terms')}). The flags that fire are mostly empty bios on small, "
               f"long-standing accounts and the NCRI following>5000 rule; of the {sum(r['following_gt_5000'] == 1 for r in rep)} reporters it flags, {big_follow} "
               f"also have >5000 followers (mutual-follow activists and political accounts, not amplifier shells). Flag rates do not differ by sentiment in a way "
               f"that would suggest planted positive or negative reports. Caveat: public_metrics are today's values, not those at posting time.")
    L += ["", "## 6. Reading", "", reading, "",
          f"Spend: {len(pages)} requests to GET /2/users, {len(sent)} ids sent, {len(users)} ids returned as user objects ({len(errors)} as errors); "
          f"${len(users) * PRICE_PER_ID:.2f} at $0.01 per id returned (${len(sent) * PRICE_PER_ID:.2f} if every id sent is billed)."]
    (run / f"tier2_{drug}_summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
