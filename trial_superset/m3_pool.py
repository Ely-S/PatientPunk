"""M3a - quantify the papers-as-labels addressable pool (the gate before building extraction).

Pulls completed trials that NEVER posted structured results (results:without, status:com)
for the cluster, applies her check_trial + our clean classifier, then checks Europe PMC for
a linked publication and whether OA full text (PMC) is available to extract an outcome from.

Reports per condition: candidates / with-any-paper / with-OA-fulltext. If the OA-fulltext
pool is non-trivial, extraction (M3b) is worth building.

Run: trial_superset/.venv/Scripts/python.exe trial_superset/m3_pool.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from seed_terms import CLUSTER
from run_study import build_cfg, CTGOV_API
from build_improved import terms_of, classify
from litlabels import cache, europe_pmc

# keep the EPMC cache inside the gitignored data/ dir
cache.CACHE_DIR = Path("trial_superset/data/.cache")

POOL = "trial_superset/data/m3_pool"


def download_noresults(save_path: str, scope: str) -> int:
    """Stage completed + results:without interventional trials for `scope`."""
    tp = os.path.join(save_path, "nct_reports_noresults")
    if os.path.isdir(tp) and any(f.endswith(".json") for f in os.listdir(tp)):
        return sum(1 for f in os.listdir(tp) if f.endswith(".json"))
    os.makedirs(tp, exist_ok=True)
    base = {"format": "json", "aggFilters": "studyType:int,results:without,status:com",
            "query.cond": scope, "countTotal": "true", "pageSize": "1000"}
    n, tok = 0, None
    while True:
        p = dict(base)
        if tok:
            p["pageToken"] = tok
        d = requests.get(CTGOV_API, params=p, headers={"accept": "application/json"}, timeout=120).json()
        for s in d.get("studies", []):
            nct = s["protocolSection"]["identificationModule"]["nctId"]
            with open(os.path.join(tp, f"{nct}.json"), "w", encoding="utf-8") as fh:
                json.dump(s, fh)
            n += 1
        tok = d.get("nextPageToken")
        if not tok:
            break
    return n


def epmc_link(nct: str) -> dict | None:
    """Best EPMC publication for a trial id; prefer an OA PMC hit."""
    res = europe_pmc.search(nct, page_size=10).get("resultList", {}).get("result", [])
    if not res:
        return None
    for x in res:  # prefer open-access full text
        if x.get("pmcid") and x.get("isOpenAccess") == "Y":
            return {"pmcid": x["pmcid"], "pmid": x.get("pmid"), "oa": True}
    x = res[0]
    return {"pmcid": x.get("pmcid"), "pmid": x.get("pmid"), "oa": x.get("isOpenAccess") == "Y"}


def main() -> None:
    from naturalv2.clinical_trial import ClinicalTrial
    from naturalv2.utils import check_trial
    from naturalv2.cli.create_study import resolve_trial_filters
    filters = resolve_trial_filters(build_cfg("x"))

    print(f"{'condition':<14}{'staged':>8}{'candidates':>12}{'any_paper':>11}{'OA_fulltext':>13}")
    print("-" * 58)
    tot = {"cand": 0, "paper": 0, "oa": 0}
    detail = {}
    for slug, spec in CLUSTER.items():
        sp = os.path.join(POOL, slug)
        staged = download_noresults(sp, spec["scope"])
        tp = os.path.join(sp, "nct_reports_noresults")
        cands = []
        skipped = 0
        for fn in os.listdir(tp):
            if not fn.endswith(".json"):
                continue
            try:
                trial = ClinicalTrial.from_json_file(os.path.join(tp, fn))
            except Exception:
                skipped += 1  # malformed record her pydantic model rejects -> unusable anyway
                continue
            if check_trial(trial, filters)[1] and classify(terms_of(trial), slug):
                cands.append(fn[:-5])
        n_paper = n_oa = 0
        oa_ncts = []
        for nct in cands:
            link = epmc_link(nct)
            if link:
                n_paper += 1
                if link["oa"] and link["pmcid"]:
                    n_oa += 1
                    oa_ncts.append(nct)
        detail[slug] = oa_ncts
        tot["cand"] += len(cands); tot["paper"] += n_paper; tot["oa"] += n_oa
        print(f"{slug:<14}{staged:>8}{len(cands):>12}{n_paper:>11}{n_oa:>13}")
    print("-" * 58)
    print(f"{'TOTAL':<14}{'':>8}{tot['cand']:>12}{tot['paper']:>11}{tot['oa']:>13}")
    print(f"\nAddressable pool: {tot['cand']} completed-no-results candidates; "
          f"{tot['paper']} have a paper; {tot['oa']} have OA full text to extract from.")
    print("OA-fulltext NCTs by condition (extraction targets):")
    for slug, ncts in detail.items():
        if ncts:
            print(f"  {slug}: {ncts}")


if __name__ == "__main__":
    main()
