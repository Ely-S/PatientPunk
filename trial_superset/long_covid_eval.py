"""Persist the Long-COVID evaluation set (the prediction targets).

Recruiting-inclusive (so LIFT and other in-flight trials are included), criteria-filtered,
Long-COVID-classified. One row per (trial, non-placebo arm) = one prediction target. Factorial
arms are RELABELED so isolated main effects survive her placebo-filter:
  "Placebo/LDN" -> "Low-Dose Naltrexone",  "Pyridostigmine/Placebo" -> "Pyridostigmine".
Each target is annotated with the per-condition Reddit corpus signal for its drug.

NOTE (naturalv2 main 7a2e006): her pipeline now classifies arms by CT.gov ArmGroupType (check_arm),
not the title, so this relabel + check_nonplacebo path is legacy. It agrees with her on factorial
main-effect arms (the case we care about) but can diverge on control arms whose title omits "placebo";
switch to ArmGroupType if exact parity with her Experiment's arm set is needed.

Run: PYTHONPATH=trial_superset trial_superset/.venv/Scripts/python.exe -m long_covid_eval
Output: data/long_covid_eval_set.csv
Prereq: data/relaxed_test/nct_reports_test (run relaxed_test_universe.py first).
"""

from __future__ import annotations

import csv
import json
import os
import sys

from build_improved import terms_of, classify
from run_study import build_cfg

REL = "trial_superset/data/relaxed_test/nct_reports_test"
OUT = "trial_superset/data/long_covid_eval_set.csv"
sys.path.insert(0, r"C:\Users\scgee\OneDrive\Documents\Projects\TrialScout")
try:
    from count_distinct_authors import ALIAS2DRUG, PAT
except Exception:
    ALIAS2DRUG, PAT = {}, None
SIG = json.load(open(r"C:\Users\scgee\OneDrive\Documents\Projects\TrialScout\signal_distinct.json",
                     encoding="utf-8")).get("long_covid", {})


def relabel(label: str) -> str:
    """Factorial-safe arm name: drop the placebo halves of an 'A/Placebo' label."""
    parts = [p.strip() for p in (label or "").replace("\\", "/").split("/")]
    nonpla = [p for p in parts if p and "placebo" not in p.lower() and "sham" not in p.lower()]
    return " + ".join(nonpla) if nonpla else "Placebo"


def corpus(name: str) -> tuple[str, int]:
    if not PAT:
        return ("", 0)
    best = ("", 0)
    for m in PAT.findall(name or ""):
        d = ALIAS2DRUG.get(m.lower())
        da = SIG.get(d, {})
        da = da.get("distinct_authors", 0) if isinstance(da, dict) else 0
        if da > best[1]:
            best = (d, da)
    return best


def main() -> None:
    from naturalv2.clinical_trial import ClinicalTrial
    from naturalv2.utils import check_trial, check_nonplacebo
    from naturalv2.cli.create_study import resolve_trial_filters
    filters = resolve_trial_filters(build_cfg("x"))

    if not os.path.isdir(REL):
        raise SystemExit(f"{REL} missing — run relaxed_test_universe.py first")

    rows = []
    for fn in os.listdir(REL):
        if not fn.endswith(".json"):
            continue
        p = os.path.join(REL, fn)
        t = ClinicalTrial.from_json_file(p)
        if not (check_trial(t, filters)[1] and classify(terms_of(t), "long_covid")):
            continue
        j = json.load(open(p, encoding="utf-8"))["protocolSection"]
        nct = fn[:-5]
        title = j["identificationModule"].get("briefTitle", "")[:90]
        status = j["statusModule"]["overallStatus"]
        prim = "; ".join(o.get("measure", "") for o in
                         j.get("outcomesModule", {}).get("primaryOutcomes", []) or [])[:90]
        for a in j.get("armsInterventionsModule", {}).get("armGroups", []) or []:
            arm = relabel(a.get("label", ""))
            if not check_nonplacebo([arm]):   # drop pure-placebo arms after relabel
                continue
            drug, da = corpus(arm + " " + " ".join(a.get("interventionNames", []) or []))
            rows.append({"nct": nct, "status": status, "is_lift": nct == "NCT06366724",
                         "title": title, "prediction_target_arm": arm[:50],
                         "corpus_drug": drug, "corpus_signal_authors": da,
                         "primary_outcome": prim})

    rows.sort(key=lambda r: (not r["is_lift"], -r["corpus_signal_authors"]))
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["nct", "status", "is_lift", "title",
                                          "prediction_target_arm", "corpus_drug",
                                          "corpus_signal_authors", "primary_outcome"])
        w.writeheader(); w.writerows(rows)

    trials = {r["nct"] for r in rows}
    print(f"Long-COVID eval set: {len(trials)} trials, {len(rows)} prediction-target arms -> {OUT}")
    print("\nLIFT prediction targets (factorial main effects):")
    for r in rows:
        if r["is_lift"]:
            print(f"   {r['prediction_target_arm']:34s} corpus={r['corpus_drug']}={r['corpus_signal_authors']}")
    print("\nTop targets by corpus signal:")
    for r in rows[:10]:
        print(f"   {r['nct']} {r['prediction_target_arm']:28s} {r['corpus_drug']}={r['corpus_signal_authors']}  [{r['status']}]")


if __name__ == "__main__":
    main()
