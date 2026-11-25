#!/usr/bin/env python3
"""Tier 2 analysis: profile-level bot signals for the users fetched by tier2_lookup.py.

    python -I tier2_analyse.py --drug ldn --run-dir <folder with users_page_NN.json>

Joins to tier2_author_list.json (group, drugs, reports, sentiments), tier1/tier1_authors.csv (tier1_score,
dominant_sentiment) and derives first/last corpus tweet dates from treatment_wise_tweets/*.json, read
straight from twitter_data/source_corpus/twitter_dataset.zip (no unzip step; restore it with
twitter_data_news_blog/download_data.py, or give --corpus-zip / $TWITTER_DATASET_ZIP; read-only,
untrusted data: json only). Needs Python 3.11+. Writes tier2_<drug>_users.csv and tier2_<drug>_summary.md.
"""
import argparse, csv, datetime, json, os, pathlib, re, statistics, sys, zipfile

PROJECT = pathlib.Path(__file__).resolve().parent.parent
AUTHOR_LIST = PROJECT / "tier2_author_list.json"
TIER1_CSV = PROJECT / "tier1" / "tier1_authors.csv"
VENDOR_HITS = PROJECT / "tier1" / "vendor_regex_hits.json"
# The corpus archive, where twitter_data_news_blog/download_data.py restores it; --corpus-zip or
# $TWITTER_DATASET_ZIP overrides. Its tweets are treatment_wise_tweets/*.json inside the zip.
DATASET_ZIP = pathlib.Path(os.environ.get("TWITTER_DATASET_ZIP", PROJECT.parent / "source_corpus" / "twitter_dataset.zip"))
PRICE_PER_ID = 0.01
BIO_RE = re.compile(r"long ?covid|longcovid|#LC\b|ME/?CFS|pwME|chronic illness|patient|spoonie|disabled|POTS|dysautonomia|MCAS", re.I)
FLAGS = ["suspended_or_not_found", "created_within_30d_of_first_tweet", "followers_lt_10", "default_profile_image",
         "bio_empty", "following_gt_5000", "tweets_per_day_gt_50"]
STATUS_FROM_TITLE = {"Forbidden": "suspended", "Not Found Error": "not_found", "Resource Unavailable Error": "unavailable"}


def ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def corpus_files(zip_path: pathlib.Path):
    """Each treatment_wise_tweets/*.json in the archive, parsed, in name order; unreadable ones skipped."""
    with zipfile.ZipFile(zip_path) as z:
        for name in sorted(z.namelist()):
            folder, _, file = name.partition("/")
            if folder == "treatment_wise_tweets" and file.endswith(".json") and "/" not in file:
                try:
                    yield json.loads(z.read(name).decode("utf-8"))
                except ValueError:
                    continue


def corpus_dates(author_ids: set, zip_path: pathlib.Path) -> dict:
    """author -> (first, last) corpus tweet datetimes, deduped on tweet_id like tier1_run.py."""
    seen, out = set(), {}
    for d in corpus_files(zip_path):
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
    ap.add_argument("--corpus-zip", type=pathlib.Path, default=DATASET_ZIP,
                    help="twitter_dataset.zip (default: where download_data.py restores it)")
    args = ap.parse_args(); run = pathlib.Path(args.run_dir); drug = args.drug; corpus = args.corpus_zip
    for need in (corpus, AUTHOR_LIST, TIER1_CSV, VENDOR_HITS, run / "request_log.json"):
        if not need.exists():
            sys.exit(f"Missing input: {need}. Run twitter_data_news_blog/download_data.py to restore it"
                     + (", or pass --corpus-zip / set TWITTER_DATASET_ZIP." if need == corpus else "."))
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
    dates = corpus_dates(set(meta), corpus)

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
        r["username_list_raw"] = m["username_list"] or t1.get("username", "")
        rows.append(r)
    cols = [c for c in rows[0].keys() if c != "username_list_raw"]
    with open(run / f"tier2_{drug}_users.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)

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
    hi_both = [r for r in rep if r["tier2_flags"] >= 2 and t1hi(r)]
    both_txt = ("no report author with two or more tier-2 flags also scored tier1 >= 2" if not hi_both else
                f"{len(hi_both)} report author{'s' if len(hi_both) > 1 else ''} ({', '.join(r['username'] for r in hi_both)}) carr{'y' if len(hi_both) > 1 else 'ies'} two or more tier-2 flags and tier1 >= 2")
    def pf(rs, f): return 100 * sum(int(r.get(f) or 0) for r in rs) / len(rs) if rs else 0
    gone_lower = pf(rep, "suspended_or_not_found") <= pf(ctl, "suspended_or_not_found")
    multi_gap = 100 * sum(r["tier2_flags"] >= 2 for r in rep) / len(rep) - 100 * sum(r["tier2_flags"] >= 2 for r in ctl) / len(ctl)
    verdict = ("look like the control authors, not like a bot cohort" if gone_lower and multi_gap < 5 else
               "sit close to the control authors on profile signals, with a modest excess of multi-flag accounts" if multi_gap < 10 else
               "carry noticeably more profile flags than the control authors")
    reading = (f"The {drug.upper()} report authors {verdict}: {gone_r} are suspended/gone vs {gone_c} of controls, "
               f"{multi_r} carry two or more profile flags vs {multi_c}, and {both_txt}. "
               f"Report accounts are a median {med([r['account_age_days_at_first_corpus_tweet'] for r in live_r])} days old at their first corpus tweet "
               f"(controls {med([r['account_age_days_at_first_corpus_tweet'] for r in live_c])}), with a median {med([r['followers_count'] for r in live_r])} followers "
               f"(controls {med([r['followers_count'] for r in live_c])}) and bios naming long covid / ME/CFS / patient terms at {rate(rep, 'bio_patient_terms')} "
               f"(controls {rate(ctl, 'bio_patient_terms')}; negative-dominant reporters {rate(sent_grp['negative'], 'bio_patient_terms')}; "
               f"positive-dominant {rate(sent_grp['positive'], 'bio_patient_terms')}). The flags that fire are mostly empty bios "
               f"({rate(rep, 'bio_empty')} vs {rate(ctl, 'bio_empty')}), default profile images ({rate(rep, 'default_profile_image')} vs {rate(ctl, 'default_profile_image')}), "
               f"accounts with fewer than 10 followers ({rate(rep, 'followers_lt_10')} vs {rate(ctl, 'followers_lt_10')}) and the NCRI following>5000 rule; "
               f"of the {sum(r['following_gt_5000'] == 1 for r in rep)} reporters it flags, {big_follow} also have >5000 followers "
               f"(mutual-follow activists and political accounts, not amplifier shells). Caveat: public_metrics are today's values, not those at posting time.")
    L += ["", "## 6. Reading", "", reading, "",
          f"Spend: {len(pages)} requests to GET /2/users, {len(sent)} ids sent, {len(users)} ids returned as user objects ({len(errors)} as errors); "
          f"${len(users) * PRICE_PER_ID:.2f} at $0.01 per id returned (${len(sent) * PRICE_PER_ID:.2f} if every id sent is billed)."]

    # ---- 7. known vendor accounts (tier1/vendor_regex_hits.json: username, campaign, label; one row per post)
    vend_path = VENDOR_HITS
    vend = {}
    for h in json.loads(vend_path.read_text()):
        u = str(h.get("username") or "").lower()
        if not u: continue
        v = vend.setdefault(u, {"campaigns": set(), "posts": 0, "labels": set()})
        v["campaigns"].add(h.get("campaign") or "?"); v["posts"] += 1
        if h.get("label"): v["labels"].add(h["label"])
    def unames(r): return {x.lower() for x in (r["username"], r.get("username_list_raw", "")) if x}
    by_uname = {}
    for r in rows:
        for x in unames(r): by_uname.setdefault(x, r)
    vend_rows = {u: by_uname[u] for u in vend if u in by_uname}
    vend_ids = {id(r) for r in vend_rows.values()}
    L += ["", "## 7. Known vendor accounts (tier1 vendor_regex_hits.json)", "",
          f"{len(vend)} distinct vendor usernames in the regex-hit file ({sum(v['posts'] for v in vend.values())} posts); "
          f"{len(vend_rows)} of them are in this lookup ({sum(1 for r in vend_rows.values() if r['group'] == 'report')} report, "
          f"{sum(1 for r in vend_rows.values() if r['group'] == 'control')} control); {len(vend) - len(vend_rows)} are not (not {drug} report/control authors in tier2_author_list.json)."]
    camp_order = sorted({c for u in vend_rows for c in vend[u]["campaigns"]})
    for c in camp_order:
        us = sorted((u for u in vend_rows if c in vend[u]["campaigns"]), key=lambda u: (-vend_rows[u]["tier2_flags"], u))
        n_in = sum(1 for u in vend if c in vend[u]["campaigns"])
        L += ["", f"### {c} ({len(us)} of {n_in} usernames in lookup)", "",
              "| username | group | posts | status | created | followers | following | tweets | bio (60) | tier1 | flags |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for u in us:
            r = vend_rows[u]
            L.append(f"| {r['username']} | {r['group']} | {vend[u]['posts']} | {r['status']} | {r['created_at']} | {r['followers_count']} | {r['following_count']} | "
                     f"{r['tweet_count']} | {r['bio_first60'].replace('|', '/')} | {r['tier1_score']} | {r['tier2_flags']} |")
    vr = list(vend_rows.values())
    gone = [r for r in vr if r["suspended_or_not_found"] == 1]; live = [r for r in vr if r["suspended_or_not_found"] != 1]
    v_ge2 = [r for r in vr if r["tier2_flags"] >= 2]; v_ge2_live = [r for r in live if r["tier2_flags"] >= 2]
    v_ge1_live = [r for r in live if r["tier2_flags"] >= 1]
    L += ["", f"**Vendor headline:** of the {len(vr)} vendor accounts in the lookup, {len(gone)} ({pct(len(gone), len(vr))}) are suspended/not found/unavailable and "
          f"{len(live)} ({pct(len(live), len(vr))}) are still live or protected. Profile flags alone (tier2_flags >= 2) would have caught {len(v_ge2)} of {len(vr)} "
          f"({pct(len(v_ge2), len(vr))}); among the still-live ones, {len(v_ge2_live)} of {len(live)} ({pct(len(v_ge2_live), len(live))}) reach >= 2 flags and "
          f"{len(v_ge1_live)} ({pct(len(v_ge1_live), len(live))}) have at least one. "
          f"Flags that fire on live vendors: " + ", ".join(f"{f}={sum(int(r.get(f) or 0) for r in live)}" for f in FLAGS if f != "suspended_or_not_found") +
          f". Tier1 >= 2 (text/behaviour signals) catches {sum(1 for r in vr if t1hi(r))} of {len(vr)}; by group, the vendor accounts are "
          f"{sum(1 for r in vr if r['group'] == 'report')} report authors and {sum(1 for r in vr if r['group'] == 'control')} controls, so "
          f"{pct(sum(1 for r in vr if r['group'] == 'report'), len(rep))} of all {drug} report authors are known vendors by text match."]

    # ---- 8. non-vendor report authors with tier2_flags >= 2 and tier1_score >= 2, with sample report text from the corpus
    nv = [r for r in rep if r["tier2_flags"] >= 2 and t1hi(r) and id(r) not in vend_ids]
    L += ["", "## 8. Non-vendor report authors with tier2_flags >= 2 and tier1_score >= 2", "",
          f"{len(nv)} of {len(rep)} report authors (excluding the {sum(1 for r in rep if id(r) in vend_ids)} known vendor report authors)."]
    if nv:
        want = {r["author_id"] for r in nv}; samples = {}
        pat = re.compile(drug, re.I)
        for d in corpus_files(corpus):
            if not isinstance(d, dict) or not isinstance(d.get("tweets"), list): continue
            for t in d["tweets"]:
                if not isinstance(t, dict): continue
                a = str(t.get("author_id"))
                if a in want and pat.search(str(t.get("text", ""))):
                    sm = samples.setdefault(a, {})
                    if len(sm) < 3: sm.setdefault(str(t.get("tweet_id")), re.sub(r"\s+", " ", str(t.get("text", "")))[:200])
        L += ["", "| username | rep | sentiments | status | created | followers | following | bio (60) | tier1 | flags | sample report text (<=200 chars) |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in sorted(nv, key=lambda r: (-r["tier2_flags"], -float(r["tier1_score"] or 0))):
            sm = " // ".join(samples.get(r["author_id"], {}).values()).replace("|", "/") or "(no corpus tweet mentioning the drug found)"
            L.append(f"| {r['username']} | {r['reports']} | {r['sentiments']} | {r['status']} | {r['created_at']} | {r['followers_count']} | {r['following_count']} | "
                     f"{r['bio_first60'].replace('|', '/')} | {r['tier1_score']} | {r['tier2_flags']} | {sm} |")
    (run / f"tier2_{drug}_summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
