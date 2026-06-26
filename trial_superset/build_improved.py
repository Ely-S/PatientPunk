"""Build the IMPROVED training set - cleaner per-condition classification.

Reuses the already-downloaded m2_outputs JSONs. For each condition, over trials that pass
HER check_trial, replace her substring condition-matcher with seed_terms.CLASSIFY (clean
keyword gate), then build HER Study from the classified retro/test lists. This recovers the
audit's under-matched wins and drops the over-matched noise (docs/condition_filter_audit.md).

We do NOT edit naturalv2: check_trial and Study are called unchanged; only the trial->condition
assignment between them is ours. Faithful mode (broaden.py) stays available for the Nikita diff.

Run: trial_superset/.venv/Scripts/python.exe trial_superset/build_improved.py
Outputs: data/improved_outputs/<slug>/studies/<...>_apo_study.yaml
"""

from __future__ import annotations

import os

import yaml

from seed_terms import CLUSTER, CLASSIFY
from run_study import build_cfg

# canonical condition label used in the improved study (conditions[0] drives the filename)
LABEL = {
    "long_covid": "Long COVID", "me_cfs": "ME-CFS", "fibromyalgia": "Fibromyalgia",
    "dysautonomia": "Dysautonomia", "chronic_lyme": "Chronic Lyme",
}
M2 = "trial_superset/data/m2_outputs"
OUT = "trial_superset/data/improved_outputs"


def terms_of(trial) -> set[str]:
    from naturalv2.utils import get_nested_value
    meshes = get_nested_value(trial, "derivedSection.conditionBrowseModule.meshes")
    mesh_terms = [m.term for m in meshes] if meshes else []
    conds = get_nested_value(trial, "protocolSection.conditionsModule.conditions") or []
    return {t.lower() for t in mesh_terms + conds}


def classify(terms: set[str], slug: str) -> bool:
    return any(tok in t for t in terms for tok in CLASSIFY[slug])


def date_of(trial, test: bool) -> str | None:
    from naturalv2.utils import get_nested_value
    path = ("protocolSection.statusModule.completionDateStruct.date" if test
            else "protocolSection.statusModule.resultsFirstPostDateStruct.date")
    return get_nested_value(trial, path)


def classified_trials(slug: str, filters: dict, test: bool):
    """(nct, date) list: passes her check_trial AND our keyword classifier."""
    from naturalv2.clinical_trial import ClinicalTrial
    from naturalv2.utils import check_trial
    tp = os.path.join(M2, slug, "nct_reports_test" if test else "nct_reports")
    out = []
    if not os.path.isdir(tp):
        return out
    for fn in os.listdir(tp):
        if not fn.endswith(".json"):
            continue
        trial = ClinicalTrial.from_json_file(os.path.join(tp, fn))
        if not check_trial(trial, filters)[1]:
            continue
        if classify(terms_of(trial), slug):
            out.append((fn[:-5], date_of(trial, test)))
    return out


def faithful_counts(slug: str) -> tuple[int, int]:
    """train+val and test counts from the M2 (faithful) study, for comparison."""
    from naturalv2.study import get_study_filepaths
    p = get_study_filepaths(os.path.join(M2, slug), CLUSTER[slug]["filter"][0],
                            "noparallel_notbinary", ate=False)["study"]
    if not os.path.exists(p):
        return (0, 0)
    s = yaml.safe_load(open(p, encoding="utf-8"))
    return (len(s.get("train_trials") or []) + len(s.get("val_trials") or []),
            len(s.get("test_trials") or []))


def main() -> None:
    from naturalv2.cli.create_study import resolve_trial_filters
    from naturalv2.study import Study
    filters = resolve_trial_filters(build_cfg("x"))

    rows = []
    for slug in CLUSTER:
        save_path = os.path.join(OUT, slug)
        cfg = build_cfg(save_path, {"conditions": [LABEL[slug]]})
        # Study reads per-trial JSONs from save_path/experiments via build_exp -> point it at
        # the m2 downloads by symlink/copy of nct_reports. build_exp uses save_path; the trial
        # JSONs live under m2. Simplest: reuse the m2 save_path for experiment IO.
        cfg.save_path = os.path.join(M2, slug)
        retro = classified_trials(slug, filters, test=False)
        test = classified_trials(slug, filters, test=True)
        study = Study(retro, test, cfg)
        # write under improved_outputs with the improved label
        from naturalv2.study import get_study_filepaths
        os.makedirs(save_path, exist_ok=True)
        out_fp = get_study_filepaths(save_path, LABEL[slug], "noparallel_notbinary", ate=False)["study"]
        study.to_yaml(out_fp)
        f_retro, f_test = faithful_counts(slug)
        rows.append((slug, f_retro, study.num_train_trials + study.num_val_trials,
                     f_test, study.num_test_trials))

    print(f"\n{'condition':<14}{'faith_retro':>12}{'impr_retro':>12}{'delta':>7}   {'faith_test':>11}{'impr_test':>11}")
    print("-" * 72)
    tf = ti = 0
    for slug, fr, ir, ft, it in rows:
        tf += fr; ti += ir
        print(f"{slug:<14}{fr:>12}{ir:>12}{ir-fr:>+7}   {ft:>11}{it:>11}")
    print("-" * 72)
    print(f"{'TOTAL':<14}{tf:>12}{ti:>12}{ti-tf:>+7}")
    print(f"\nFaithful training (train+val) = {tf}   Improved = {ti}   (delta {ti-tf:+d})")
    print("Improved studies -> data/improved_outputs/<slug>/studies/")


if __name__ == "__main__":
    main()
