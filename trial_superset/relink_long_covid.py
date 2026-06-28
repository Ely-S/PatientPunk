"""Push papers-as-labels for Long COVID — multi-paper retry on the trials we declined.

29 Long-COVID no-results trials linked to a paper the model rejected (usually the wrong paper:
review/protocol/secondary). extract_best() tries multiple candidate papers per trial until one
yields an extractable per-arm primary result. Recovered trials are appended to m3_extractions.jsonl
(last-line-wins, so build_augmented picks them up). Long-COVID only.

Run: PYTHONPATH=trial_superset trial_superset/.venv/Scripts/python.exe -m relink_long_covid
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor

from m3_pool import POOL
from run_study import build_cfg
from build_improved import terms_of, classify
from litlabels.extract_labels import extract_best, MODEL

JSONL = "trial_superset/data/m3_extractions.jsonl"
SLUG = "long_covid"


def main() -> None:
    from naturalv2.clinical_trial import ClinicalTrial
    from naturalv2.utils import check_trial
    from naturalv2.cli.create_study import resolve_trial_filters
    filters = resolve_trial_filters(build_cfg("x"))

    already = set()  # ncts already successfully extracted
    for line in open(JSONL, encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("slug") == SLUG and r.get("extractable"):
            already.add(r["nct"])

    tp = os.path.join(POOL, SLUG, "nct_reports_noresults")
    todo = []
    for fn in sorted(os.listdir(tp)):
        if not fn.endswith(".json"):
            continue
        nct, p = fn[:-5], os.path.join(tp, fn)
        if nct in already:
            continue
        try:
            t = ClinicalTrial.from_json_file(p)
        except Exception:
            continue
        if check_trial(t, filters)[1] and classify(terms_of(t), SLUG):
            todo.append((nct, p))
    print(f"retrying {len(todo)} not-yet-extracted Long-COVID candidates ({MODEL}), {len(already)} already have labels")

    def work(item):
        nct, p = item
        try:
            res = extract_best(nct, p)
        except Exception as e:
            return {"nct": nct, "slug": SLUG, "linked": True, "extractable": False, "error": str(e)[:100]}
        if res:
            schema, pmcid, via = res
            return {"nct": nct, "slug": SLUG, "linked": True, "pmcid": pmcid, "via": via,
                    "extractable": True, "schema": schema}
        return {"nct": nct, "slug": SLUG, "linked": True, "extractable": False}

    recovered = 0
    with open(JSONL, "a", encoding="utf-8") as out:
        for rec in ThreadPoolExecutor(max_workers=8).map(work, todo):
            if rec.get("extractable"):
                recovered += 1
                out.write(json.dumps(rec) + "\n")
                out.flush()
    print(f"recovered {recovered} additional Long-COVID paper labels -> appended to {JSONL}")


if __name__ == "__main__":
    main()
