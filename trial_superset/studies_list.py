"""Consolidated Long-COVID study list: one row per benchmark/target trial with coverage + weight.

Joins master_pulled_data.csv (trial metadata + is_prediction_target/in_nikita_seed),
drug_coverage.csv (raw distinct-author coverage per trial), and coverage_validation.csv
(on-target fraction + effective coverage for the validated drugs). Sorted runnable-first by
effective (else raw) coverage. effective_authors = the reliability-weight input for the study.

Run: trial_superset/.venv/Scripts/python.exe trial_superset/studies_list.py
Output: data/studies_list.csv
"""

from __future__ import annotations

import csv
from collections import Counter

D = "trial_superset/data"
OUT = f"{D}/studies_list.csv"
COLS = ["nct", "intervention", "role", "credibility", "readout", "raw_authors", "on_target_frac",
        "effective_authors", "coverage_confidence", "runnable", "is_prediction_target",
        "in_nikita_seed", "primary_outcome"]


def load(p):
    try:
        return list(csv.DictReader(open(p, encoding="utf-8-sig")))
    except FileNotFoundError:
        return []


def _date(m):
    return ((m.get("results_public_date") or m.get("primary_completion_date") or "")[:7]) if m else ""


def main():
    cov = load(f"{D}/drug_coverage.csv")
    val = {r["intervention"]: r for r in load(f"{D}/coverage_validation.csv")}
    meta = {}
    for r in load(f"{D}/master_pulled_data.csv"):
        if r["condition"] == "long_covid":
            meta.setdefault(r["nct"], r)

    rows = []
    for c in cov:
        nct, drug = c["trial_nct"], c["intervention"]
        m, v = meta.get(nct, {}), val.get(drug, {})
        conf = ("validated" if drug in val
                else "over_count_risk" if c.get("alias_note")
                else "N/A" if c["runnable"] == "N/A_not_nameable"
                else "clean_alias_unvalidated")
        rows.append({"nct": nct, "intervention": drug, "role": c["role"], "credibility": c["credibility"],
                     "readout": _date(m), "raw_authors": c["distinct_authors"],
                     "on_target_frac": v.get("on_target_frac", ""), "effective_authors": v.get("effective_authors", ""),
                     "coverage_confidence": conf, "runnable": c["runnable"],
                     "is_prediction_target": m.get("is_prediction_target", ""),
                     "in_nikita_seed": m.get("in_nikita_seed", ""),
                     "primary_outcome": (m.get("outcome", "") or "")[:60]})

    rank = {"runnable": 0, "thin": 1, "no_signal": 2, "N/A_not_nameable": 3}

    def key(r):
        eff = int(r["effective_authors"]) if r["effective_authors"] else \
            (int(r["raw_authors"]) if str(r["raw_authors"]).isdigit() else 0)
        return (rank.get(r["runnable"], 4), -eff)

    rows.sort(key=key)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"studies_list.csv: {len(rows)} trials  by runnable:", dict(Counter(r["runnable"] for r in rows)))
    print(f"  runnable completed benchmark:", sum(1 for r in rows if r["runnable"] == "runnable" and "target" not in r["role"]))
    print(f"  runnable targets:", sum(1 for r in rows if r["runnable"] == "runnable" and "target" in r["role"]))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
