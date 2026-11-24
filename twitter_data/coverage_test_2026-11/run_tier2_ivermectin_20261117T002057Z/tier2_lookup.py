#!/usr/bin/env python3
"""Tier 2: X API v2 user lookup (GET /2/users?ids=...) for the report authors of one drug plus its
matched control authors. Reuses token() and get() from step1_search.py so the bearer token only ever
appears in the Authorization header. Hard cap: REQUEST_CAP requests to this one endpoint, nothing else.

    python -I tier2_lookup.py --drug ldn --run-dir <folder>        # writes users_page_NN.json + request_log.json
    python -I tier2_lookup.py --drug ivermectin                    # creates run_tier2_ivermectin_<UTC>/ next to this file's parent
    python -I tier2_lookup.py --drug ldn --dry-run                 # count ids and requests, send nothing
"""
import argparse, datetime, json, pathlib, sys, time

PROJECT = pathlib.Path(__file__).resolve().parent.parent      # .../twitter_week_test
sys.path.insert(0, str(PROJECT))
from step1_search import token, get                           # noqa: E402

AUTHOR_LIST = PROJECT / "tier2_author_list.json"
USER_FIELDS = "created_at,description,name,profile_image_url,protected,public_metrics,username,verified,verified_type"
BATCH = 100
REQUEST_CAP = 16
PRICE_PER_ID = 0.01


def ids_for(drug: str) -> list[str]:
    d = json.loads(AUTHOR_LIST.read_text())
    rep = [a for a, v in d["report_authors"].items() if drug in v.get("drugs", [])]
    ctl = [str(a) for a in d["control_non_report_authors"][drug]]
    seen, out = set(), []
    for a in rep + ctl:
        if a not in seen:
            seen.add(a); out.append(a)
    print(f"{drug}: {len(rep)} report authors + {len(ctl)} control -> {len(out)} unique ids")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drug", required=True, choices=["ldn", "ivermectin"])
    ap.add_argument("--run-dir"); ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    ids = ids_for(args.drug)
    batches = [ids[i:i + BATCH] for i in range(0, len(ids), BATCH)]
    print(f"{len(batches)} requests of up to {BATCH} ids; cap {REQUEST_CAP}; max spend ${len(ids) * PRICE_PER_ID:.2f} at ${PRICE_PER_ID}/id")
    if len(batches) > REQUEST_CAP:
        sys.exit(f"abort: {len(batches)} requests would exceed the cap of {REQUEST_CAP}")
    if args.dry_run:
        print(f"would GET https://api.x.com/2/users?ids=<{BATCH} ids>&user.fields={USER_FIELDS}  x{len(batches)}"); return
    run_dir = pathlib.Path(args.run_dir) if args.run_dir else PROJECT / f"run_tier2_{args.drug}_{datetime.datetime.now(datetime.UTC):%Y%m%dT%H%M%SZ}"
    run_dir.mkdir(parents=True, exist_ok=True)
    tok = token(); http_log = []; req_log = []
    n_data = n_err = 0
    for n, batch in enumerate(batches, 1):
        if len(http_log) >= REQUEST_CAP:
            sys.exit(f"abort before page {n}: {len(http_log)} HTTP attempts already made, cap {REQUEST_CAP}")
        at = datetime.datetime.now(datetime.UTC).isoformat()
        body = get("/users", {"ids": ",".join(batch), "user.fields": USER_FIELDS}, tok, http_log)   # exits on 402/403 or after retries
        data, errs = body.get("data", []), body.get("errors", [])
        (run_dir / f"users_page_{n:02d}.json").write_text(json.dumps(body, ensure_ascii=False, indent=1))
        req_log.append({"page": n, "at_utc": at, "ids_sent": len(batch), "ids": batch, "http_status": http_log[-1]["status"],
                        "n_data": len(data), "n_errors": len(errs), "http_attempts_so_far": len(http_log)})
        (run_dir / "request_log.json").write_text(json.dumps(req_log, indent=1))
        n_data += len(data); n_err += len(errs)
        print(f"  page {n}: sent {len(batch)}, HTTP {http_log[-1]['status']}, data {len(data)}, errors {len(errs)}", flush=True)
        if n < len(batches): time.sleep(1.1)
    summary = {"drug": args.drug, "requests_made": len(req_log), "http_attempts": len(http_log), "ids_sent": len(ids),
               "ids_returned_data": n_data, "ids_returned_errors": n_err, "spend_usd_at_0.01_per_id": round(n_data * PRICE_PER_ID, 2),
               "spend_usd_if_errors_billed": round((n_data + n_err) * PRICE_PER_ID, 2), "http_log": http_log,
               "finished_utc": datetime.datetime.now(datetime.UTC).isoformat()}
    (run_dir / "lookup_manifest.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "http_log"}, indent=1)); print(f"saved under {run_dir}")


if __name__ == "__main__":
    main()
