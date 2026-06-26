"""Measure the cost of the binary preset vs notbinary, to decide if the label sidecar is needed.

binary preset (binary_endpoint=True): only binary/count primary endpoints pass check_trial AND
get labels -> every label is a clean rate in [0,1], NO sidecar needed. But continuous-endpoint
trials are dropped. This quantifies how many trials we'd lose per condition (structured + paper).

Reads m3_labeled/<slug>/nct_reports (structured WITH-results + injected paper trials, co-located).
Run: trial_superset/.venv/Scripts/python.exe trial_superset/binary_compare.py
"""

from __future__ import annotations

import glob
import json
import logging
import os

logging.disable(logging.INFO)

from seed_terms import CLUSTER
from run_study import build_cfg
from build_improved import terms_of, classify, LABEL

LABELED = "trial_superset/data/m3_labeled"
JSONL = "trial_superset/data/m3_extractions.jsonl"
BINARY_FILTERS = {"randomized": True, "parallel": False, "num_noncontrol": None,
                  "nonhealthy": True, "binary_endpoint": True}


def main() -> None:
    from naturalv2.clinical_trial import ClinicalTrial
    from naturalv2.utils import check_trial, get_nested_value
    from naturalv2.cli.create_study import resolve_trial_filters
    from naturalv2.study import Study

    paper = set()
    if os.path.exists(JSONL):
        for line in open(JSONL, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("extractable"):
                paper.add(r["nct"])

    print(f"{'condition':<14}{'binary t+v':>11}{'(struct':>9}{'paper)':>8}   {'notbin t+v':>11}")
    print("-" * 56)
    tot_bin = tot_bin_paper = 0
    for slug in CLUSTER:
        dest = os.path.join(LABELED, slug)
        tp = os.path.join(dest, "nct_reports")
        if not os.path.isdir(tp):
            continue
        cfg = build_cfg(dest, {"conditions": [LABEL[slug]], "trial_filters": dict(BINARY_FILTERS)})
        cfg.save_path = dest
        bfilters = resolve_trial_filters(cfg)
        retro = []
        for fn in os.listdir(tp):
            if not fn.endswith(".json"):
                continue
            try:
                trial = ClinicalTrial.from_json_file(os.path.join(tp, fn))
            except Exception:
                continue
            if check_trial(trial, bfilters)[1] and classify(terms_of(trial), slug):
                date = get_nested_value(trial, "protocolSection.statusModule.resultsFirstPostDateStruct.date")
                retro.append((fn[:-5], date))
        study = Study(retro, [], cfg)  # binary_endpoint=True -> require_binary_endpoint labels
        tv = study.num_train_trials + study.num_val_trials
        surv = {list(d.keys())[0] for d in (study.train_trials + study.val_trials)}
        p = len(surv & paper)
        tot_bin += tv; tot_bin_paper += p
        notbin = {"long_covid": 28, "me_cfs": 17, "fibromyalgia": 140, "dysautonomia": 41, "chronic_lyme": 4}.get(slug, 0)
        print(f"{slug:<14}{tv:>11}{tv-p:>9}{p:>8}   {notbin:>11}")
    print("-" * 56)
    print(f"{'TOTAL':<14}{tot_bin:>11}{tot_bin-tot_bin_paper:>9}{tot_bin_paper:>8}   {'234':>11}")
    print(f"\nbinary preset: {tot_bin} train+val ({tot_bin_paper} paper) — ALL clean rates, NO sidecar")
    print(f"notbinary:     234 train+val (77 paper) — needs the label sidecar for continuous")


if __name__ == "__main__":
    main()
