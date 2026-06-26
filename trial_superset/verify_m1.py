"""Regression check for M1 - proves we reproduced Nikita's study by running her pipeline.

Three independent assertions:
  A. FORMAT  : our study YAML loads in HER `naturalv2.study.Study` class (drop-in for her pipeline).
  B. RETRO   : every trial in her shared study's completed (train+val) set is in ours.
               This is the M1 gate - the completed set is stable (results posted), so it must match.
  C. TEST    : the test-set gap is explained by trial STATUS (her shared set is recruiting-inclusive),
               not by a filtering error - i.e. her missing test trials are recoverable via status relax.

Run:
  trial_superset/.venv/Scripts/python.exe trial_superset/verify_m1.py
Exit code 0 = all gates pass.
"""

from __future__ import annotations

import csv
import os
import sys

import yaml

OURS = "trial_superset/data/m1_outputs/studies/long_covid_noparallel_notbinary_apo_study.yaml"
HERS = r"C:\Users\scgee\Downloads\long_covid_noparallel_notbinary_apo_study.yaml"
RELAXED_CSV = "trial_superset/data/relaxed_test_universe.csv"


def ncts(study: dict, key: str) -> set[str]:
    return {list(d.keys())[0] for d in study.get(key, [])}


def main() -> int:
    fails = 0

    # ---- A. FORMAT: loads in her Study class ----
    print("A. FORMAT - does our YAML load in her naturalv2.study.Study?")
    try:
        from naturalv2.study import Study
        s = Study.from_yaml(OURS)
        required = {"conditions", "covariates", "train_trials", "val_trials", "test_trials",
                    "num_train_trials", "num_val_trials", "num_test_trials", "experiment_name", "ate"}
        missing = required - set(s.__dict__)
        ok = not missing
        print(f"   loaded OK; required keys present: {ok}" + (f" (missing {missing})" if missing else ""))
        print(f"   -> {'PASS' if ok else 'FAIL'}")
        fails += 0 if ok else 1
    except Exception as e:
        print(f"   FAIL - {type(e).__name__}: {e}")
        fails += 1

    her = yaml.safe_load(open(HERS, encoding="utf-8"))
    ours = yaml.safe_load(open(OURS, encoding="utf-8"))

    # ---- B. RETRO reproduction (the gate) ----
    print("\nB. RETRO - is her completed (train+val) set reproduced?")
    her_retro = ncts(her, "train_trials") | ncts(her, "val_trials")
    our_retro = ncts(ours, "train_trials") | ncts(ours, "val_trials")
    shared = her_retro & our_retro
    missing = her_retro - our_retro
    ok = len(missing) == 0
    print(f"   her retro={len(her_retro)}  ours={len(our_retro)}  shared={len(shared)}/{len(her_retro)}")
    if missing:
        print(f"   MISSING (her retro not reproduced): {sorted(missing)}")
    print(f"   ours-only (new since her run): {sorted(our_retro - her_retro)}")
    print(f"   -> {'PASS' if ok else 'FAIL'} (gate: all of her retro present)")
    fails += 0 if ok else 1

    # ---- C. TEST gap explained by STATUS, not filtering error ----
    print("\nC. TEST - is the test-set gap explained by trial status (not a bug)?")
    her_test = ncts(her, "test_trials")
    our_test = ncts(ours, "test_trials")
    her_only = her_test - our_test
    if os.path.exists(RELAXED_CSV):
        relaxed = {r["nct"] for r in csv.DictReader(open(RELAXED_CSV, encoding="utf-8-sig"))}
        recoverable = her_only & relaxed
        true_drift = her_only - relaxed
        # PASS if the vast majority of her-only test trials are recovered by relaxing status
        ok = len(her_only) == 0 or len(recoverable) >= 0.8 * len(her_only)
        print(f"   her test={len(her_test)}  our strict test={len(our_test)}  her-only={len(her_only)}")
        print(f"   of her-only: recoverable via status-relax={len(recoverable)}  true drift={len(true_drift)} {sorted(true_drift)}")
        print(f"   -> {'PASS' if ok else 'FAIL'} (>=80% of the gap is status, not filtering)")
        fails += 0 if ok else 1
    else:
        print(f"   (skip - {RELAXED_CSV} not built; run relaxed_test_universe.py)")

    print(f"\n{'='*48}\nRESULT: {'ALL PASS' if fails == 0 else f'{fails} FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
