"""Build the model-ready label sidecar (keeps every trial; fixes the notbinary scale issue).

Her notbinary pipeline computes avg_potential_outcome = value/N for EVERY endpoint, which is a
response rate for binary endpoints but garbage (mean/N) for continuous ones. This sidecar leaves
her native field untouched and adds, per (trial, outcome, arm):
  - endpoint_type : binary | percentage | continuous
  - raw_value, n
  - clean_outcome : rate in [0,1] (binary/percentage) OR raw mean (continuous) -- a MEANINGFUL value
  - scale_proportion : continuous on a bounded instrument -> oriented (mean-min)/(max-min) in [0,1];
                       null for unbounded continuous / changes-from-baseline / binary

Paper trials use the extraction schema (incl. scale_min/max/higher_is_better); structured trials are
parsed from their CT.gov OutcomeMeasure (paramType/unit). Non-placebo arms only (her convention).

Run: trial_superset/.venv/Scripts/python.exe trial_superset/build_labels_sidecar.py
Output: data/labels_sidecar.csv
"""

from __future__ import annotations

import csv
import json
import logging
import os

logging.disable(logging.INFO)

MANIFEST = "trial_superset/data/training_set_manifest_augmented.csv"
JSONL = "trial_superset/data/m3_extractions.jsonl"
LABELED = "trial_superset/data/m3_labeled"
OUT = "trial_superset/data/labels_sidecar.csv"

_MEAN_PARAMS = {"MEAN", "MEDIAN", "LEAST_SQUARES_MEAN", "GEOMETRIC_MEAN", "GEOMETRIC_LEAST_SQUARES_MEAN"}
_COUNT_PARAMS = {"COUNT_OF_PARTICIPANTS", "COUNT_OF_UNITS", "NUMBER"}


def _num(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def scale_prop(value, smin, smax, higher_better):
    if None in (value, smin, smax) or smax == smin or higher_better is None:
        return None
    p = (value - smin) / (smax - smin)
    if not higher_better:
        p = 1 - p
    return round(min(1.0, max(0.0, p)), 4)


def rows_from_paper(schema, check_nonplacebo):
    kind = schema.get("outcome_kind")
    etype = {"binary_count": "binary", "percentage": "percentage"}.get(kind, "continuous")
    title = schema.get("primary_outcome_title", "")
    smin, smax = _num(schema.get("scale_min")), _num(schema.get("scale_max"))
    hib = schema.get("higher_is_better")
    out = []
    for a in schema.get("arms", []):
        if a.get("is_placebo") or not check_nonplacebo([a.get("title", "")]):
            continue
        val, n = _num(a.get("value")), _num(a.get("n"))
        if val is None:
            continue
        if etype == "percentage":
            clean, sp = val / 100.0, None
        elif etype == "binary":
            clean, sp = (val / n if n else None), None
        else:
            clean, sp = val, scale_prop(val, smin, smax, hib)
        out.append((title, a.get("title", ""), etype, val, n, clean, sp))
    return out


def rows_from_structured(trial_path, check_nonplacebo):
    if not os.path.exists(trial_path):
        return []
    trial = json.load(open(trial_path, encoding="utf-8"))
    oms = trial.get("resultsSection", {}).get("outcomeMeasuresModule", {}).get("outcomeMeasures", []) or []
    out = []
    for om in oms:
        if om.get("type") != "PRIMARY":
            continue
        unit = (om.get("unitOfMeasure") or "").lower()
        ptype = (om.get("paramType") or "").upper()
        title = om.get("title", "")
        groups = {g["id"]: g.get("title", g["id"]) for g in om.get("groups", []) or []}
        denoms = (om.get("denoms") or [{}])[0].get("counts", []) or []
        denom = {c["groupId"]: _num(c.get("value")) for c in denoms}
        meas = {}
        for cls in om.get("classes", []) or []:
            for cat in (cls.get("categories") or []):
                for m in (cat.get("measurements") or []):
                    meas[m["groupId"]] = _num(m.get("value"))
        if "percent" in unit:
            etype = "percentage"
        elif ptype in _MEAN_PARAMS:
            etype = "continuous"
        elif ptype in _COUNT_PARAMS:
            etype = "binary"
        else:
            etype = "continuous"  # unknown: don't spuriously divide by N
        for gid, gtitle in groups.items():
            if not check_nonplacebo([gtitle]):
                continue
            val, n = meas.get(gid), denom.get(gid)
            if val is None:
                continue
            if etype == "percentage":
                clean = val / 100.0
            elif etype == "binary":
                clean = (val / n) if n else None
            else:
                clean = val
            out.append((title, gtitle, etype, val, n, clean, None))
    return out


def main() -> None:
    from naturalv2.utils import check_nonplacebo
    paper = {}
    if os.path.exists(JSONL):
        for line in open(JSONL, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("extractable") and r.get("schema"):
                paper[r["nct"]] = r["schema"]

    manifest = list(csv.DictReader(open(MANIFEST, encoding="utf-8-sig")))
    out_rows, et_counter = [], {}
    for r in manifest:
        nct, slug, src = r["nct"], r["condition"], r["label_source"]
        if src == "paper_extracted" and nct in paper:
            rows = rows_from_paper(paper[nct], check_nonplacebo)
        else:
            rows = rows_from_structured(os.path.join(LABELED, slug, "nct_reports", f"{nct}.json"), check_nonplacebo)
        for (otitle, arm, etype, val, n, clean, sp) in rows:
            et_counter[etype] = et_counter.get(etype, 0) + 1
            out_rows.append({"nct": nct, "condition": slug, "split": r["split"], "label_source": src,
                             "outcome": otitle[:120], "arm": arm[:80], "endpoint_type": etype,
                             "raw_value": val, "n": n,
                             "clean_outcome": round(clean, 4) if clean is not None else "",
                             "scale_proportion": sp if sp is not None else ""})

    cols = ["nct", "condition", "split", "label_source", "outcome", "arm", "endpoint_type",
            "raw_value", "n", "clean_outcome", "scale_proportion"]
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)

    cont = [r for r in out_rows if r["endpoint_type"] == "continuous"]
    with_prop = [r for r in cont if r["scale_proportion"] != ""]
    print(f"label rows: {len(out_rows)}  by endpoint_type: {et_counter}")
    print(f"continuous arms: {len(cont)}; with scale_proportion: {len(with_prop)} ({100*len(with_prop)//max(len(cont),1)}%)")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
