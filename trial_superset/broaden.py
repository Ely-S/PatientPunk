"""M2 - broaden the training universe across the 5 cluster conditions.

Runs her pipeline (via run_study) once per condition in seed_terms.CLUSTER, each with
its own broad download scope, and reports how the TRAINING set grows beyond Long-COVID
alone (M1). Training = completed + results; status relaxation does not affect it.

Per condition we record train/val/test trial counts + label counts, sample new training
trials, and confirm the study YAML reloads in her Study class.

Run:
  trial_superset/.venv/Scripts/python.exe trial_superset/broaden.py
Outputs: data/m2_outputs/<condition>/studies/<...>_apo_study.yaml  (one per condition)
"""

from __future__ import annotations

import argparse
import os

import yaml

from seed_terms import CLUSTER
from run_study import build_cfg, scoped_download


def run_condition(slug: str, filters: list[str], scope: str) -> dict:
    save_path = f"trial_superset/data/m2_outputs/{slug}"
    cfg = build_cfg(save_path, {"conditions": list(filters)})
    print(f"\n### {slug}  (filter={filters!r}  scope={scope!r})")
    scoped_download(save_path, scope, test=False)
    scoped_download(save_path, scope, test=True)
    from naturalv2.cli.create_study import run_study_and_get_stats
    stats = run_study_and_get_stats(cfg)
    stats["slug"] = slug
    stats["save_path"] = save_path
    return stats


def sample_trials(save_path: str, filter0: str, n: int = 3) -> list[str]:
    """Pull a few train-trial titles from the produced study YAML for sanity."""
    from naturalv2.study import get_study_filepaths
    p = get_study_filepaths(save_path, filter0, "noparallel_notbinary", ate=False)["study"]
    if not os.path.exists(p):
        return []
    study = yaml.safe_load(open(p, encoding="utf-8"))
    out = []
    for d in (study.get("train_trials") or [])[:n]:
        nct, meta = next(iter(d.items()))
        out.append(f"{nct}: {meta[0][:80]}")
    return out


def main() -> None:
    results = []
    for slug, spec in CLUSTER.items():
        results.append(run_condition(slug, spec["filter"], spec["scope"]))

    print("\n" + "=" * 78)
    print(f"{'condition':<14}{'train':>7}{'val':>6}{'test':>6}{'tr_lbl':>8}{'val_lbl':>9}{'treat':>7}{'outc':>6}")
    print("-" * 78)
    tot_train = tot_val = tot_test = 0
    for r in results:
        print(f"{r['slug']:<14}{r['train_trials']:>7}{r['val_trials']:>6}{r['test_trials']:>6}"
              f"{r['train_labels']:>8}{r['val_labels']:>9}{r['num_treatments']:>7}{r['num_outcomes']:>6}")
        tot_train += r["train_trials"]; tot_val += r["val_trials"]; tot_test += r["test_trials"]
    print("-" * 78)
    print(f"{'TOTAL':<14}{tot_train:>7}{tot_val:>6}{tot_test:>6}")

    lc = next(r for r in results if r["slug"] == "long_covid")
    lc_retro = lc["train_trials"] + lc["val_trials"]
    tot_retro = tot_train + tot_val
    print(f"\nTraining superset (train+val): Long-COVID-only={lc_retro}  ->  cluster={tot_retro}  "
          f"(x{tot_retro/lc_retro:.1f})" if lc_retro else "")

    # GATE checks
    print("\n--- M2 GATE ---")
    grew = tot_retro > lc_retro
    print(f"[{'PASS' if grew else 'FAIL'}] training set grows vs M1 Long-COVID-only ({lc_retro} -> {tot_retro})")

    print("\nSample new training trials (non-Long-COVID conditions):")
    for r in results:
        if r["slug"] == "long_covid":
            continue
        for line in sample_trials(r["save_path"], CLUSTER[r["slug"]]["filter"][0]):
            print(f"  [{r['slug']}] {line}")

    # confirm every study YAML reloads in her Study class
    from naturalv2.study import Study, get_study_filepaths
    print("\nStudy.from_yaml reload check:")
    all_ok = True
    for r in results:
        p = get_study_filepaths(r["save_path"], CLUSTER[r["slug"]]["filter"][0], "noparallel_notbinary", ate=False)["study"]
        try:
            Study.from_yaml(p)
            print(f"  [OK] {r['slug']}")
        except Exception as e:
            all_ok = False
            print(f"  [FAIL] {r['slug']}: {type(e).__name__}: {e}")
    print(f"[{'PASS' if all_ok else 'FAIL'}] all per-condition studies reload in her Study class")


if __name__ == "__main__":
    main()
