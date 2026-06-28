"""M3c - inject paper-extracted labels and build the augmented training set.

Reads data/m3_extractions.jsonl (extractable results from extract_labels --all). For each
rescued trial, synthesizes a CT.gov-shaped resultsSection.outcomeMeasuresModule (PRIMARY
outcome, per-arm value + denom) + a resultsFirstPostDate (= paper date), then runs HER
Study over (improved retro WITH results) + (paper-labeled retro) per condition.

Faithful: her check_trial / Experiment / Study are unchanged; her code computes the label
(value/denom, or value/100 for percent) from our synthetic results exactly as it would from
a real CT.gov result.

Run (after extract_labels --all): trial_superset/.venv/Scripts/python.exe trial_superset/build_augmented.py
Outputs: data/m3_labeled/<slug>/studies/<...>_apo_study.yaml + augmented manifest
"""

from __future__ import annotations

import csv
import glob
import json
import os
import shutil

import yaml

from seed_terms import CLUSTER
from run_study import build_cfg
from build_improved import classified_trials, LABEL, M2
from m3_pool import POOL

JSONL = "trial_superset/data/m3_extractions.jsonl"
OUT = "trial_superset/data/m3_labeled"


def load_extractions() -> dict[str, dict[str, dict]]:
    by_slug: dict[str, dict[str, dict]] = {}
    if not os.path.exists(JSONL):
        return by_slug
    for line in open(JSONL, encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("extractable") and r.get("schema"):
            by_slug.setdefault(r["slug"], {})[r["nct"]] = r["schema"]
    return by_slug


def synth_outcome_measure(schema: dict) -> dict | None:
    """CT.gov-shaped PRIMARY OutcomeMeasure from the extraction schema. None if no usable arm."""
    groups, counts, measurements = [], [], []
    for i, a in enumerate(schema.get("arms", [])):
        n, val = a.get("n"), a.get("value")
        if n is None or val is None:
            continue
        try:
            int(n); float(val)
        except (TypeError, ValueError):
            continue
        gid = f"OG{i:03d}"
        groups.append({"id": gid, "title": a.get("title", gid)})
        counts.append({"groupId": gid, "value": str(int(n))})
        measurements.append({"groupId": gid, "value": str(val)})
    if not measurements:
        return None
    return {
        "type": "PRIMARY",
        "title": schema.get("primary_outcome_title", "Primary outcome"),
        "unitOfMeasure": schema.get("unit_of_measure", ""),
        "groups": groups,
        "denoms": [{"units": "Participants", "counts": counts}],
        "classes": [{"categories": [{"measurements": measurements}]}],
    }


def inject_one(slug: str, nct: str, schema: dict, dest_reports: str) -> str | None:
    """Write an augmented trial JSON (synthetic results + date) into dest_reports.
    Returns the date string (or None if written but no date), or False if nothing was written."""
    om = synth_outcome_measure(schema)
    if om is None:
        return False  # no usable numeric arm -> nothing written (distinct from "written, no date")
    src = os.path.join(POOL, slug, "nct_reports_noresults", f"{nct}.json")
    trial = json.load(open(src, encoding="utf-8"))
    # her ResultsSection requires all three modules; flow + baseline are stubbed (empty),
    # only outcomeMeasuresModule carries the paper-extracted label.
    trial["resultsSection"] = {
        "participantFlowModule": {},
        "baselineCharacteristicsModule": {"groups": [], "measures": []},
        "outcomeMeasuresModule": {"outcomeMeasures": [om]},
    }
    date = (schema.get("result_public_date") or "").strip() or None
    trial["protocolSection"]["statusModule"]["resultsFirstPostDateStruct"] = {"date": date or ""}
    with open(os.path.join(dest_reports, f"{nct}.json"), "w", encoding="utf-8") as f:
        json.dump(trial, f)
    return date


# Build all cluster conditions. NATURAL estimates each trial independently (no pooled cross-trial
# model — see docs/method_and_scope.md), so Long COVID is the PRIMARY benchmark and the other 4
# conditions are a SEPARATE adjacent-conditions benchmark. The split into two datasets
# (master_pulled_data.csv vs cluster_benchmark.csv) happens in build_master_csv.py.
CANONICAL_CONDITIONS = list(CLUSTER)
ADAPTED = "trial_superset/data/adapted_registries/nct_reports"


def adapted_registry_retro(slug: str, dest_reports: str) -> list[tuple[str, str | None]]:
    """Fold in non-CT.gov (ISRCTN) trials adapted to CT.gov shape (adapt_registries.py).
    Long COVID only; only trials carrying a synthetic outcome. Returns [(id, date)]."""
    if slug != "long_covid" or not os.path.isdir(ADAPTED):
        return []
    out = []
    for fn in sorted(os.listdir(ADAPTED)):
        if not fn.endswith(".json"):
            continue
        src = os.path.join(ADAPTED, fn)
        j = json.load(open(src, encoding="utf-8"))
        if not j.get("resultsSection", {}).get("outcomeMeasuresModule", {}).get("outcomeMeasures"):
            continue
        shutil.copy(src, os.path.join(dest_reports, fn))
        date = j["protocolSection"]["statusModule"].get("resultsFirstPostDateStruct", {}).get("date")
        out.append((fn[:-5], date or None))
    return out


def main() -> None:
    from naturalv2.cli.create_study import resolve_trial_filters
    from naturalv2.study import Study, get_study_filepaths
    filters = resolve_trial_filters(build_cfg("x"))
    extractions = load_extractions()

    rows = []
    manifest = []
    for slug in CANONICAL_CONDITIONS:
        dest = os.path.join(OUT, slug)
        dest_reports = os.path.join(dest, "nct_reports")
        # co-locate the WITH-results downloads + test so her Experiment can read every trial
        shutil.copytree(os.path.join(M2, slug, "nct_reports"), dest_reports, dirs_exist_ok=True)
        shutil.copytree(os.path.join(M2, slug, "nct_reports_test"),
                        os.path.join(dest, "nct_reports_test"), dirs_exist_ok=True)

        improved_retro = classified_trials(slug, filters, test=False)  # WITH-results (clean classifier)
        test = classified_trials(slug, filters, test=True)
        paper_retro = []
        for nct, schema in extractions.get(slug, {}).items():
            date = inject_one(slug, nct, schema, dest_reports)
            if date is not False:  # only trials whose synthetic results file was actually written
                paper_retro.append((nct, date))

        registry_retro = adapted_registry_retro(slug, dest_reports)  # non-CT.gov (ISRCTN), LC only
        cfg = build_cfg(dest, {"conditions": [LABEL[slug]]})
        cfg.save_path = dest
        study = Study(improved_retro + paper_retro + registry_retro, test, cfg)
        os.makedirs(os.path.join(dest, "studies"), exist_ok=True)
        out_fp = get_study_filepaths(dest, LABEL[slug], "noparallel_notbinary", ate=False)["study"]
        study.to_yaml(out_fp)

        # how many of the augmented train+val came from papers?
        aug = yaml.safe_load(open(out_fp, encoding="utf-8"))
        aug_ncts = {list(d.keys())[0] for d in (aug.get("train_trials") or []) + (aug.get("val_trials") or [])}
        paper_in = aug_ncts & set(extractions.get(slug, {}))
        rows.append((slug, study.num_train_trials + study.num_val_trials, len(paper_in)))
        for split in ("train_trials", "val_trials", "test_trials"):
            for d in (aug.get(split) or []):
                n, meta = next(iter(d.items()))
                source = ("registry_adapted" if n.startswith("ISRCTN")
                          else "paper_extracted" if n in extractions.get(slug, {})
                          else "ctgov_structured")
                manifest.append({"condition": slug, "split": split.replace("_trials", ""), "nct": n,
                                 "label_source": source,
                                 "date": meta[1] if len(meta) > 1 else "", "title": meta[0] if meta else ""})

    with open("trial_superset/data/training_set_manifest_augmented.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["condition", "split", "nct", "label_source", "date", "title"])
        w.writeheader(); w.writerows(manifest)

    print(f"{'condition':<14}{'aug train+val':>15}{'from papers':>13}")
    print("-" * 42)
    tot = tp = 0
    for slug, av, pin in rows:
        tot += av; tp += pin
        print(f"{slug:<14}{av:>15}{pin:>13}")
    print("-" * 42)
    print(f"{'TOTAL':<14}{tot:>15}{tp:>13}")
    print(f"\nImproved baseline train+val = {tot - tp}  ->  augmented = {tot}  (+{tp} paper-labeled)")
    print("Augmented manifest: data/training_set_manifest_augmented.csv")


if __name__ == "__main__":
    main()
