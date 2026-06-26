"""Consolidate the improved per-condition studies into one canonical training-set manifest.

The improved mode (clean keyword classifier, build_improved.py) is the canonical training
set (decision 2026-06-25: adopt clean classification including long_COVID). This flattens
the 5 per-condition studies into one CSV + prints the summary.

Run: trial_superset/.venv/Scripts/python.exe trial_superset/consolidate.py
Output: data/training_set_manifest.csv
"""

from __future__ import annotations

import csv
import glob

import yaml

from seed_terms import CLUSTER

OUT = "trial_superset/data/training_set_manifest.csv"


def main() -> None:
    rows = []
    summary = {}
    for slug in CLUSTER:
        files = glob.glob(f"trial_superset/data/improved_outputs/{slug}/studies/*_apo_study.yaml")
        if not files:
            continue
        study = yaml.safe_load(open(files[0], encoding="utf-8"))
        counts = {}
        for split in ("train_trials", "val_trials", "test_trials"):
            split_name = split.replace("_trials", "")
            for d in (study.get(split) or []):
                nct, meta = next(iter(d.items()))
                title = meta[0] if meta else ""
                date = meta[1] if len(meta) > 1 else ""
                rows.append({"condition": slug, "split": split_name, "nct": nct,
                             "date": date, "title": title})
            counts[split_name] = len(study.get(split) or [])
        summary[slug] = counts

    rows.sort(key=lambda r: (r["condition"], r["split"], r["date"] or "9999"))
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["condition", "split", "nct", "date", "title"])
        w.writeheader()
        w.writerows(rows)

    print(f"{'condition':<14}{'train':>7}{'val':>6}{'test':>6}{'total':>7}")
    print("-" * 40)
    tt = tv = te = 0
    for slug, c in summary.items():
        tr, va, ts = c.get("train", 0), c.get("val", 0), c.get("test", 0)
        tt += tr; tv += va; te += ts
        print(f"{slug:<14}{tr:>7}{va:>6}{ts:>6}{tr+va+ts:>7}")
    print("-" * 40)
    print(f"{'TOTAL':<14}{tt:>7}{tv:>6}{te:>6}{tt+tv+te:>7}")
    print(f"\nTraining (train+val) = {tt+tv}   Test = {te}   Rows written: {len(rows)} -> {OUT}")


if __name__ == "__main__":
    main()
