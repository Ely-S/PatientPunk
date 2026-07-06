"""Build the CORE-5 Long-COVID study in NATURAL's exact study-YAML format.

The 5 highest-confidence completed benchmark trials (the ones that passed the original
corpus-learnable gate: self-obtainable/oral-Rx, single-agent, blinded, self-report endpoint),
temporally split train/val by her Study class. This is the clean set Nikita can drop straight
into her pipeline — same shape as create_study emits.

Run: PYTHONPATH=trial_superset trial_superset/.venv/Scripts/python.exe -m build_core5_study
Output: data/core5/long_covid_core5_noparallel_notbinary_apo_study.yaml (+ core5_studies.csv)
"""

from __future__ import annotations

import csv
import os

from run_study import build_cfg

# (nct, results date) — all CT.gov-structured; Study sorts by date and splits train_ratio=0.6
CORE5 = [
    ("NCT05472090", "2024-11-26"),  # cyclobenzaprine (TNX-102 SL)
    ("NCT05047952", "2025-01-16"),  # vortioxetine
    ("NCT05618587", "2025-03-05"),  # low-dose lithium
    ("NCT04809974", "2025-06-25"),  # nicotinamide riboside (Niagen)
    ("NCT05874037", "2026-06-25"),  # fluvoxamine
]
SRC = "trial_superset/data/m3_labeled/long_covid"       # holds nct_reports/{nct}.json
OUT = "trial_superset/data/core5"
DRUG = {"NCT05472090": "cyclobenzaprine", "NCT05047952": "vortioxetine", "NCT05618587": "lithium",
        "NCT04809974": "nicotinamide_riboside", "NCT05874037": "fluvoxamine"}


def main() -> None:
    from naturalv2.study import Study
    cfg = build_cfg(SRC, {"conditions": ["Long Covid"]})
    cfg.save_path = SRC
    study = Study(CORE5, [], cfg)

    os.makedirs(OUT, exist_ok=True)
    yaml_fp = os.path.join(OUT, "long_covid_core5_noparallel_notbinary_apo_study.yaml")
    study.to_yaml(yaml_fp)

    # readable companion CSV: which of the 5 landed in train vs val (temporal split)
    import yaml as _yaml
    doc = _yaml.safe_load(open(yaml_fp, encoding="utf-8"))
    rows = []
    for split in ("train_trials", "val_trials"):
        for d in (doc.get(split) or []):
            nct, meta = next(iter(d.items()))
            rows.append({"nct": nct, "drug": DRUG.get(nct, ""), "split": split.replace("_trials", ""),
                         "date": meta[1] if len(meta) > 1 else "", "title": (meta[0] if meta else "")[:70]})
    rows.sort(key=lambda r: r["date"])
    with open(os.path.join(OUT, "core5_studies.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["nct", "drug", "split", "date", "title"])
        w.writeheader(); w.writerows(rows)

    print(f"CORE-5 study (her format): {study.num_train_trials} train + {study.num_val_trials} val")
    for r in rows:
        print(f"   [{r['split']:<5}] {r['date'][:7]}  {r['nct']}  {r['drug']}")
    print(f"-> {yaml_fp}")
    print(f"-> {os.path.join(OUT, 'core5_studies.csv')}")


if __name__ == "__main__":
    main()
