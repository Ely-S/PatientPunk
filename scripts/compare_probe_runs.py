#!/usr/bin/env python3
"""Pair-level agreement between two psychedelic probe runs (repeat-pass stability).

Claims do not align one-to-one across runs, so agreement is measured at the
level the analysis uses: one row per (account, drug) cohort pair, with
any helped / any worsened / any no-effect / pair AE status / any severe AE /
each symptom class present. Reports Cohen's kappa and raw agreement per field.

Both databases are opened read-only. Author hashes are used only in memory to
align pairs; output is aggregates only.

Usage:
    uv run python scripts/compare_probe_runs.py \
        data/probes/psychedelic_pharmacology.db data/probes/psychedelic_pharmacology_repeat.db
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "studies/psychedelics/v2"))
from psychedelics_v2 import SYMPTOM_ORDER, classify_symptom  # noqa: E402

AE_RANK = {"not_stated": 0, "explicit_none": 1, "reported": 2}


def load_pairs(db: Path, run_id: str | None = None) -> tuple[str, dict, set]:
    """Pair-level outcome summary for one run, plus the pairs whose units all completed."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        runs = [r[0] for r in con.execute("SELECT run_id FROM probe_run")]
        if run_id is None:
            if len(runs) != 1:
                raise SystemExit(f"{db} holds {len(runs)} runs; pass --run-ids")
            run_id = runs[0]
        elif run_id not in runs:
            raise SystemExit(f"run {run_id} is not in {db}")
        units = con.execute(
            "SELECT unit_key, author_hash, target, status FROM unit WHERE run_id = ?", (run_id,)
        ).fetchall()
        claims = con.execute(
            "SELECT unit_key, values_json FROM claim WHERE run_id = ? AND included = 1", (run_id,)
        ).fetchall()
    finally:
        con.close()

    unit_pair = {u: (a, t) for u, a, t, _ in units}
    complete: dict[tuple, bool] = {}
    for _, a, t, status in units:
        complete[(a, t)] = complete.get((a, t), True) and status == "complete"

    pairs: dict[tuple, dict] = {}
    for unit_key, values_json in claims:
        v = json.loads(values_json)
        p = pairs.setdefault(unit_pair[unit_key], {
            "directions": set(), "ae_status": "not_stated", "severe": False, "classes": set()})
        for e in v["effects"]:
            p["directions"].add(e["direction"])
            p["classes"].add(classify_symptom(e.get("target")))
        if AE_RANK[v["adverse_event_status"]] > AE_RANK[p["ae_status"]]:
            p["ae_status"] = v["adverse_event_status"]
        p["severe"] |= any(a.get("severity") == "severe" for a in v["adverse_events"])
    return run_id, pairs, {k for k, ok in complete.items() if ok}


def features(p: dict | None) -> dict:
    p = p or {"directions": set(), "ae_status": "not_stated", "severe": False, "classes": set()}
    return {
        "any helped": "helped" in p["directions"],
        "any worsened": "worsened" in p["directions"],
        "any no effect": "no_effect" in p["directions"],
        "AE status": p["ae_status"],
        "any severe AE": p["severe"],
        **{f"class: {c}": c in p["classes"] for c in SYMPTOM_ORDER},
        "_classes": frozenset(p["classes"]),
    }


def cohen_kappa(a: list, b: list) -> tuple[float, float]:
    """Return (kappa, raw agreement) for two equal-length label lists."""
    n = len(a)
    if not n:
        return float("nan"), float("nan")
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n**2
    kappa = float("nan") if expected == 1 else (observed - expected) / (1 - expected)
    return kappa, observed


def compare(left: dict, right: dict, universe: set) -> list[dict]:
    keys = sorted(universe)
    fa = [features(left.get(k)) for k in keys]
    fb = [features(right.get(k)) for k in keys]
    rows = []
    for field in [f for f in fa[0] if not f.startswith("_")]:
        a, b = [x[field] for x in fa], [x[field] for x in fb]
        kappa, raw = cohen_kappa(a, b)
        rows.append({"field": field, "kappa": kappa, "agreement": raw,
                     "positive (left)": sum(1 for x in a if x is True or x == "reported"),
                     "positive (right)": sum(1 for x in b if x is True or x == "reported")})
    effect = [i for i in range(len(keys)) if fa[i]["_classes"] or fb[i]["_classes"]]
    exact = sum(fa[i]["_classes"] == fb[i]["_classes"] for i in effect)
    jaccard = [len(fa[i]["_classes"] & fb[i]["_classes"]) / len(fa[i]["_classes"] | fb[i]["_classes"])
               for i in effect]
    rows.append({"field": "symptom-class set: exact match (effect-bearing in either run)",
                 "kappa": float("nan"), "agreement": exact / len(effect) if effect else float("nan"),
                 "positive (left)": len(effect), "positive (right)": len(effect)})
    rows.append({"field": "symptom-class set: mean Jaccard (effect-bearing in either run)",
                 "kappa": float("nan"),
                 "agreement": sum(jaccard) / len(jaccard) if jaccard else float("nan"),
                 "positive (left)": len(effect), "positive (right)": len(effect)})
    return rows


def _f(x: float) -> str:
    return "—" if x != x else f"{x:.3f}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("left", type=Path)
    ap.add_argument("right", type=Path)
    ap.add_argument("--run-ids", nargs=2, metavar=("LEFT", "RIGHT"))
    args = ap.parse_args()
    ids = args.run_ids or (None, None)
    lid, left, lok = load_pairs(args.left, ids[0])
    rid, right, rok = load_pairs(args.right, ids[1])
    universe = lok & rok
    print(f"left  {args.left.name}  run {lid[:12]}  pairs with an included claim {len(left):,}")
    print(f"right {args.right.name}  run {rid[:12]}  pairs with an included claim {len(right):,}")
    print(f"compared: {len(universe):,} cohort pairs whose units completed in both runs "
          f"(a pair with no included claim counts as all-negative / not_stated)")
    inc_a = [k in left for k in sorted(universe)]
    inc_b = [k in right for k in sorted(universe)]
    k, raw = cohen_kappa(inc_a, inc_b)
    print()
    print("| field | Cohen's κ | raw agreement | positive (left) | positive (right) |")
    print("|---|---|---|---|---|")
    print(f"| any included claim | {_f(k)} | {_f(raw)} | {sum(inc_a)} | {sum(inc_b)} |")
    for r in compare(left, right, universe):
        print(f"| {r['field']} | {_f(r['kappa'])} | {_f(r['agreement'])} | "
              f"{r['positive (left)']} | {r['positive (right)']} |")


if __name__ == "__main__":
    main()
