"""Audit each cluster condition's filter for classification wins/losses.

For every scope-downloaded trial that passes her check_trial (noparallel_notbinary_apo),
compare HER condition match (substring, both directions, vs mesh+conditions) against a
condition-specific keyword test:
  - UNDER-MATCH (missed win): looks like the condition (keyword) but her filter DROPPED it
    -> filter too narrow (the ME/CFS pattern).
  - OVER-MATCH (noise): her filter KEPT it but it doesn't look like the condition
    -> substring quirk pulling in unrelated trials.

Read-only over data/m2_outputs/<slug>/nct_reports/. Uses naturalv2 check_trial unchanged.
Run: trial_superset/.venv/Scripts/python.exe trial_superset/audit_conditions.py
"""

from __future__ import annotations

import os

from seed_terms import CLUSTER
from run_study import build_cfg

# condition-specific "genuine" tokens (lowercased substring test against mesh+conditions)
GENUINE = {
    # post-acute ONLY (bare "covid"/"covid-19" would mislabel acute-COVID trials as long-COVID)
    "long_covid": ("long covid", "post-covid", "post covid", "postcovid", "pasc",
                   "post-acute sequelae", "post-acute covid", "long-covid"),
    "me_cfs": ("chronic fatigue", "fatigue syndrome", "myalgic", "me/cfs", "post-viral", "post exertional"),
    "fibromyalgia": ("fibromyalgia", "fibro"),
    "dysautonomia": ("dysautonomia", "orthostatic", "postural tachycardia", "pots", "autonomic"),
    "chronic_lyme": ("lyme", "borrelia"),
}


def condition_terms(trial) -> set[str]:
    from naturalv2.utils import get_nested_value
    meshes = get_nested_value(trial, "derivedSection.conditionBrowseModule.meshes")
    mesh_terms = [m.term for m in meshes] if meshes else []
    conds = get_nested_value(trial, "protocolSection.conditionsModule.conditions") or []
    return {t.lower() for t in mesh_terms + conds}


def her_match(terms: set[str], filters: list[str]) -> bool:
    cset = {c.replace("_", " ").lower() for c in filters}
    return any(c in t for t in terms for c in cset) or any(t in c for t in terms for c in cset)


def looks_genuine(terms: set[str], slug: str) -> bool:
    kws = GENUINE[slug]
    return any(k in t for t in terms for k in kws)


def main() -> None:
    from naturalv2.clinical_trial import ClinicalTrial
    from naturalv2.utils import check_trial
    from naturalv2.cli.create_study import resolve_trial_filters

    filters = resolve_trial_filters(build_cfg("x"))
    print(f"filters: {filters}\n")
    print(f"{'condition':<14}{'valid':>7}{'matched':>9}{'genuine_in':>12}{'UNDERmatch':>12}{'OVERmatch':>11}")
    print("-" * 70)

    for slug, spec in CLUSTER.items():
        tp = f"trial_superset/data/m2_outputs/{slug}/nct_reports"
        if not os.path.isdir(tp):
            continue
        under, over = [], []
        n_valid = n_match = n_genuine_match = 0
        for fn in os.listdir(tp):
            if not fn.endswith(".json"):
                continue
            trial = ClinicalTrial.from_json_file(os.path.join(tp, fn))
            _, valid = check_trial(trial, filters)
            if not valid:
                continue
            n_valid += 1
            terms = condition_terms(trial)
            matched = her_match(terms, spec["filter"])
            genuine = looks_genuine(terms, slug)
            if matched:
                n_match += 1
                if genuine:
                    n_genuine_match += 1
                else:
                    over.append((fn[:-5], sorted(terms)[:4]))
            elif genuine:
                under.append((fn[:-5], sorted(terms)[:4]))
        print(f"{slug:<14}{n_valid:>7}{n_match:>9}{n_genuine_match:>12}{len(under):>12}{len(over):>11}")
        for nct, terms in under[:6]:
            print(f"     UNDER {nct}  {terms}")
        for nct, terms in over[:6]:
            print(f"     OVER  {nct}  {terms}")
    print("\nUNDER = condition-looking trial her filter dropped (widen filter to win)")
    print("OVER  = her filter kept it but it doesn't look like the condition (substring noise)")


if __name__ == "__main__":
    main()
