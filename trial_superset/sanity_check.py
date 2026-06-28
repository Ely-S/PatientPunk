"""Sanity-check the augmented training set (data QA, not just 'it ran').

Checks:
  1. manifest: counts, label_source split, duplicate NCTs, date population
  2. disjointness: paper-labeled (results:without) vs structured (results:with) NCT sets;
     train/val/test non-overlap
  3. structured baseline unchanged (= improved 161 train+val)
  4. labels: rebuild every train+val Experiment, flag empty/degenerate, compare the
     avg_potential_outcome distributions of structured vs paper (surfaces the mean/N scale)

Run: trial_superset/.venv/Scripts/python.exe trial_superset/sanity_check.py
"""

from __future__ import annotations

import csv
import glob
import logging
import statistics as st
from collections import Counter, defaultdict

import yaml

logging.disable(logging.INFO)

MANIFEST = "trial_superset/data/training_set_manifest_augmented.csv"
LABELED = "trial_superset/data/m3_labeled"
LABEL = {"long_covid": "Long COVID", "me_cfs": "ME-CFS", "fibromyalgia": "Fibromyalgia",
         "dysautonomia": "Dysautonomia", "chronic_lyme": "Chronic Lyme"}


def dist(vals):
    if not vals:
        return "n=0"
    inside = sum(1 for v in vals if 0 <= v <= 1)
    return (f"n={len(vals)} min={min(vals):.3f} med={st.median(vals):.3f} max={max(vals):.3f} "
            f"in[0,1]={inside}/{len(vals)} ({100*inside/len(vals):.0f}%)")


def main() -> None:
    rows = list(csv.DictReader(open(MANIFEST, encoding="utf-8-sig")))
    print(f"=== 1. MANIFEST ({len(rows)} rows) ===")
    print("by label_source:", dict(Counter(r["label_source"] for r in rows)))
    print("by split:", dict(Counter(r["split"] for r in rows)))
    print("by condition:", dict(Counter(r["condition"] for r in rows)))

    # duplicate NCTs (same trial appearing twice anywhere)
    nct_rows = defaultdict(list)
    for r in rows:
        nct_rows[r["nct"]].append((r["condition"], r["split"], r["label_source"]))
    dups = {n: v for n, v in nct_rows.items() if len(v) > 1}
    print(f"\n[{'PASS' if not dups else 'CHECK'}] duplicate NCTs across rows: {len(dups)}")
    for n, v in list(dups.items())[:8]:
        print(f"   {n}: {v}")

    # date population for paper-labeled (temporal split depends on it)
    paper = [r for r in rows if r["label_source"] == "paper_extracted"]
    nodate = [r["nct"] for r in paper if not r["date"].strip()]
    print(f"[{'PASS' if not nodate else 'CHECK'}] paper-labeled missing date: {len(nodate)}/{len(paper)} {nodate[:6]}")

    # === 2. disjointness ===
    print("\n=== 2. DISJOINTNESS ===")
    paper_ncts = {r["nct"] for r in rows if r["label_source"] == "paper_extracted"}
    struct_ncts = {r["nct"] for r in rows if r["label_source"] == "ctgov_structured"}
    print(f"[{'PASS' if not (paper_ncts & struct_ncts) else 'FAIL'}] paper vs structured overlap: {len(paper_ncts & struct_ncts)}")
    by_split = defaultdict(set)
    for r in rows:
        by_split[r["split"]].add(r["nct"])
    tv_test = (by_split["train"] | by_split["val"]) & by_split["test"]
    print(f"[{'PASS' if not tv_test else 'FAIL'}] train/val vs test overlap: {len(tv_test)}")

    # === 3. structured baseline ===
    struct_tv = sum(1 for r in rows if r["label_source"] == "ctgov_structured" and r["split"] in ("train", "val"))
    print(f"\n=== 3. BASELINE ===\n[{'PASS' if struct_tv == 161 else 'CHECK'}] structured train+val = {struct_tv} (expected 161 from improved baseline)")

    # === 4. labels: rebuild Experiments ===
    print("\n=== 4. LABELS (rebuild every train+val Experiment) ===")
    from naturalv2.experiment import Experiment
    struct_apo, paper_apo, empty, extreme = [], [], [], []
    src_by_nct = {r["nct"]: r["label_source"] for r in rows}
    for slug in LABEL:
        f = glob.glob(f"{LABELED}/{slug}/studies/*_apo_study.yaml")
        if not f:
            continue
        study = yaml.safe_load(open(f[0], encoding="utf-8"))
        for split in ("train_trials", "val_trials"):
            for d in (study.get(split) or []):
                nct = list(d.keys())[0]
                try:
                    e = Experiment(f"{LABELED}/{slug}", nct, "noparallel_notbinary",
                                   status="completed", require_binary_endpoint=False)
                except Exception as ex:
                    empty.append((nct, f"BUILD-FAIL {type(ex).__name__}"))
                    continue
                apos = list(e.avg_potential_outcomes)
                if not apos:
                    empty.append((nct, "no APO"))
                    continue
                (paper_apo if src_by_nct.get(nct) == "paper_extracted" else struct_apo).extend(apos)
                for v in apos:
                    if v < -10 or v > 10:
                        extreme.append((nct, src_by_nct.get(nct), round(v, 2)))
    print(f"[{'PASS' if not empty else 'CHECK'}] train+val trials with empty/failed labels: {len(empty)} {empty[:6]}")
    print(f"structured-results APO dist: {dist(struct_apo)}")
    print(f"paper-extracted  APO dist: {dist(paper_apo)}")
    print(f"[{'note' if extreme else 'PASS'}] |APO|>10 values: {len(extreme)} {extreme[:8]}")
    if struct_apo and paper_apo:
        print("\nNOTE: APO = value/denom (or value/100 for percent). Continuous-mean endpoints give")
        print("mean/N, so continuous trials (structured AND paper) sit at small magnitudes vs binary")
        print("rates - inherent to the notbinary preset, not introduced by papers. Flagged for Nikita.")


if __name__ == "__main__":
    main()
