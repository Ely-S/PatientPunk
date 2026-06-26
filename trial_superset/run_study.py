"""M1 driver — reproduce Nikita's NATURAL-v2 study by RUNNING her pipeline.

We do NOT port her logic. We:
  1. Pre-stage `<save_path>/nct_reports[_test]/` with a *condition-scoped superset*
     of CT.gov trials (her `download_clinical_trials` pulls the ENTIRE interventional
     corpus with no condition filter — tens of thousands of JSONs. We instead query
     the same `aggFilters` PLUS `query.cond=<condition>`, which is a superset of her
     literal-substring condition filter, so her own filter still yields the faithful
     set — far cheaper).
  2. Call her `run_study_and_get_stats(cfg)` unchanged. It skips the full download
     (the dir already exists), scans only our scoped JSONs, applies `check_trial`,
     builds the `Study`, and writes the study YAML.

Provenance: calls naturalv2 @ pinned 16ca178 —
  naturalv2.cli.create_study.run_study_and_get_stats / .clinical_trial._save_trial
  (we match `_save_trial`'s on-disk format: raw API study dict -> `<nct>.json`).
No LLM/API key needed: create_study's Experiment extraction is deterministic parsing
of CT.gov structured results.

Run (M1 baseline):
  trial_superset/.venv/Scripts/python.exe trial_superset/run_study.py \
      --save-path trial_superset/data/m1_outputs

Outputs: <save_path>/studies/long_covid_noparallel_notbinary_apo_study.yaml
"""

from __future__ import annotations

import argparse
import json
import os

import requests
from omegaconf import OmegaConf

CTGOV_API = "https://clinicaltrials.gov/api/v2/studies"

# M1 reproduces her `noparallel_notbinary_apo` Long-COVID study.
DEFAULTS = {
    "experiment_name": "noparallel_notbinary",
    "ate": False,
    "train_ratio": 0.6,          # her conf/common.yaml default
    "conditions": ["Long Covid"],
    "trial_filters": {
        "randomized": True,
        "parallel": False,        # noparallel
        "num_noncontrol": None,   # -> 1 for apo (ate=False)
        "nonhealthy": True,
        "binary_endpoint": False, # notbinary
    },
}


def scoped_download(save_path: str, scope_query: str, test: bool) -> int:
    """Populate `<save_path>/nct_reports[_test]/` with a SUPERSET of trials for the
    download scope, then let her own condition filter narrow it.

    IMPORTANT: `scope_query` must be a *superset* of her `find_condition_ncts` filter,
    NOT equal to it. Her filter matches `trial_term in "<condition>"` as a substring,
    so for "long covid" a bare "covid" term qualifies — it sweeps in general-COVID
    trials. Scoping the download to `query.cond=Long COVID` therefore UNDER-pulls
    (misses those, incl. LIFT/NCT06366724). Use a broad family term (e.g. "COVID").

    Same aggFilters as her `download_clinical_trials`. Saves each study as `<nct>.json`
    in her exact on-disk format. Idempotent: skips if already populated. Returns count
    staged (0 if it skipped an existing dir).
    """
    trial_path = os.path.join(save_path, "nct_reports" + ("_test" if test else ""))
    if os.path.isdir(trial_path) and any(f.endswith(".json") for f in os.listdir(trial_path)):
        existing = sum(1 for f in os.listdir(trial_path) if f.endswith(".json"))
        print(f"  [skip] {trial_path} already has {existing} trial JSONs")
        return 0
    os.makedirs(trial_path, exist_ok=True)

    agg = "studyType:int,results:with,status:com" if not test else "studyType:int,results:without,status:act"
    base = {
        "format": "json",
        "aggFilters": agg,
        "query.cond": scope_query,  # broad superset; her filter narrows to the condition
        "countTotal": "true",
        "pageSize": "1000",
    }

    staged, page_token = 0, None
    while True:
        params = dict(base)
        if page_token:
            params["pageToken"] = page_token
        resp = requests.get(CTGOV_API, params=params, headers={"accept": "application/json"}, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        for study in data.get("studies", []):
            nct = study["protocolSection"]["identificationModule"]["nctId"]
            with open(os.path.join(trial_path, f"{nct}.json"), "w", encoding="utf-8") as f:
                json.dump(study, f)  # matches naturalv2._save_trial format
            staged += 1
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    stratum = "results:without/active (test)" if test else "results:with/completed (retro)"
    print(f"  [staged] {staged} trials -> {trial_path}  [{stratum}]")
    return staged


def build_cfg(save_path: str, overrides: dict | None = None) -> OmegaConf:
    """Build the OmegaConf her pipeline expects (bypasses Hydra; no conf/ needed)."""
    cfg_dict = dict(DEFAULTS)
    cfg_dict["save_path"] = save_path
    if overrides:
        cfg_dict.update(overrides)
    return OmegaConf.create(cfg_dict)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run Nikita's create_study with a scoped download.")
    ap.add_argument("--save-path", default="trial_superset/data/m1_outputs")
    ap.add_argument("--condition", action="append", help="Override her filter condition(s); repeatable.")
    ap.add_argument("--scope-query", default=None,
                    help="Broad CT.gov query.cond superset for the download (e.g. 'COVID'). "
                         "Must be broader than the filter condition. Defaults to the conditions.")
    ap.add_argument("--experiment-name", default=None)
    args = ap.parse_args()

    overrides: dict = {}
    if args.condition:
        overrides["conditions"] = args.condition
    if args.experiment_name:
        overrides["experiment_name"] = args.experiment_name

    cfg = build_cfg(args.save_path, overrides)
    conditions = list(cfg.conditions)
    scope_query = args.scope_query or " OR ".join(conditions)
    print(f"Conditions(filter): {conditions} | scope(download): {scope_query!r} | "
          f"experiment: {cfg.experiment_name} | ate: {cfg.ate}")
    print(f"Filters: {OmegaConf.to_container(cfg.trial_filters)}")

    print("Scoped download (completed/retro):")
    scoped_download(args.save_path, scope_query, test=False)
    print("Scoped download (active/test):")
    scoped_download(args.save_path, scope_query, test=True)

    # Import here so the scoped dirs exist before her find_valid_ncts checks them.
    from naturalv2.cli.create_study import run_study_and_get_stats

    print("\nRunning her pipeline (filter -> Study -> YAML)...")
    stats = run_study_and_get_stats(cfg)
    print("\n=== STUDY STATS ===")
    print(OmegaConf.to_yaml(OmegaConf.create(stats)))
    out = os.path.join(args.save_path, "studies")
    print(f"Study YAML written under: {out}")


if __name__ == "__main__":
    main()
