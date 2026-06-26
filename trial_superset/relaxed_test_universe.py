"""Build the RELAXED test universe: NATURAL-v2 test trials including still-recruiting
trials, not just `status:act` (Active, not recruiting).

Her pipeline's test universe is `studyType:int,results:without,status:act` — active,
*recruitment complete*. That excludes every still-recruiting trial, including LIFT
(NCT06366724, our top pick), which is RECRUITING. Recruiting trials can NEVER be in
training (no results = no labels); this only affects the *test/prediction* set.

This script reproduces her test selection with status relaxed to
{ACTIVE_NOT_RECRUITING, RECRUITING, ENROLLING_BY_INVITATION}, applying her exact
`check_trial` (noparallel_notbinary_apo) + condition filter, and emits:
  - data/relaxed_test_universe.csv  (the universe to select off later)
  - prints the strict-vs-relaxed delta (named additions incl. LIFT)

Provenance: calls naturalv2 @ 16ca178 — find_valid_ncts / find_condition_ncts /
check_trial (unchanged). Only the download status filter is relaxed.

Run:
  trial_superset/.venv/Scripts/python.exe trial_superset/relaxed_test_universe.py
"""

from __future__ import annotations

import csv
import json
import os

import requests

from run_study import build_cfg, CTGOV_API

RELAXED_STATUSES = "RECRUITING,ACTIVE_NOT_RECRUITING,ENROLLING_BY_INVITATION"
SAVE_PATH = "trial_superset/data/relaxed_test"
SCOPE_QUERY = "COVID"


def download_relaxed_test(save_path: str, scope_query: str) -> int:
    """Stage results:without interventional trials for the 3 statuses into nct_reports_test."""
    trial_path = os.path.join(save_path, "nct_reports_test")
    if os.path.isdir(trial_path) and any(f.endswith(".json") for f in os.listdir(trial_path)):
        n = sum(1 for f in os.listdir(trial_path) if f.endswith(".json"))
        print(f"  [skip] {trial_path} already has {n} JSONs")
        return n
    os.makedirs(trial_path, exist_ok=True)
    base = {
        "format": "json",
        "aggFilters": "studyType:int,results:without",
        "filter.overallStatus": RELAXED_STATUSES,
        "query.cond": scope_query,
        "countTotal": "true",
        "pageSize": "1000",
    }
    staged, token = 0, None
    while True:
        params = dict(base)
        if token:
            params["pageToken"] = token
        r = requests.get(CTGOV_API, params=params, headers={"accept": "application/json"}, timeout=120)
        r.raise_for_status()
        data = r.json()
        for study in data.get("studies", []):
            nct = study["protocolSection"]["identificationModule"]["nctId"]
            with open(os.path.join(trial_path, f"{nct}.json"), "w", encoding="utf-8") as f:
                json.dump(study, f)
            staged += 1
        token = data.get("nextPageToken")
        if not token:
            break
    print(f"  [staged] {staged} relaxed test trials -> {trial_path}")
    return staged


def _meta(trial_path: str, nct: str) -> dict:
    j = json.load(open(os.path.join(trial_path, f"{nct}.json"), encoding="utf-8"))
    ps = j["protocolSection"]
    ivs = ps.get("armsInterventionsModule", {}).get("interventions", []) or []
    return {
        "nct": nct,
        "overall_status": ps["statusModule"]["overallStatus"],
        "phase": "/".join(ps.get("designModule", {}).get("phases", []) or []),
        "primary_completion": (ps.get("statusModule", {}).get("primaryCompletionDateStruct") or {}).get("date", ""),
        "title": ps["identificationModule"].get("briefTitle", "")[:120],
        "conditions": "; ".join(ps.get("conditionsModule", {}).get("conditions", []) or []),
        "interventions": "; ".join(f"{i.get('type','')}:{i.get('name','')}" for i in ivs)[:200],
    }


def main() -> None:
    cfg = build_cfg(SAVE_PATH)
    from naturalv2.cli.create_study import resolve_trial_filters, find_valid_ncts, find_condition_ncts

    filters = resolve_trial_filters(cfg)
    print(f"Filters (noparallel_notbinary_apo): {filters}")
    print("Downloading relaxed test universe:")
    download_relaxed_test(SAVE_PATH, SCOPE_QUERY)

    print("Applying her check_trial + condition filter...")
    valid = find_valid_ncts(cfg.save_path, filters, test=True)
    cond = find_condition_ncts(valid, cfg.save_path, list(cfg.conditions), filters, test=True)
    trial_path = os.path.join(SAVE_PATH, "nct_reports_test")
    rows = [_meta(trial_path, nct) for (nct, _) in cond]
    rows.sort(key=lambda r: (r["overall_status"] != "ACTIVE_NOT_RECRUITING", r["primary_completion"]))

    strict = [r for r in rows if r["overall_status"] == "ACTIVE_NOT_RECRUITING"]
    added = [r for r in rows if r["overall_status"] != "ACTIVE_NOT_RECRUITING"]

    out_csv = "trial_superset/data/relaxed_test_universe.csv"
    cols = ["nct", "overall_status", "phase", "primary_completion", "title", "conditions", "interventions"]
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    print("\n=== RELAXED TEST UNIVERSE (Long COVID, noparallel_notbinary_apo) ===")
    print(f"strict (ACTIVE_NOT_RECRUITING): {len(strict)}")
    print(f"added by relaxation           : {len(added)}  (RECRUITING / ENROLLING_BY_INVITATION)")
    print(f"relaxed total                 : {len(rows)}")
    print(f"LIFT NCT06366724 in relaxed?  : {'NCT06366724' in {r['nct'] for r in rows}}")
    print(f"\nNamed additions (would be NEW test/prediction targets):")
    for r in added:
        print(f"  {r['nct']}  [{r['overall_status']}]  {r['title']}")
    print(f"\nUniverse written: {out_csv}")


if __name__ == "__main__":
    main()
