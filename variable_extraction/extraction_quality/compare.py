#!/usr/bin/env python3
"""Diff two runs: per-field score deltas, and which mismatches moved.

Macro f1 alone hides the failure mode that matters most during prompt
iteration -- a rule that fixes `conditions` while quietly breaking `medications`
shows up as a small gain. This prints the per-field delta and names the
individual cells that were fixed and newly broken, so a "win" has to survive
being looked at.

Usage:
    python compare.py results/<baseline>.json results/<candidate>.json
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from eval_prompt_fixtures import ROOT

METRICS = ("precision", "recall", "f1")


def macro(run: dict) -> dict[str, float]:
    scored = [m for m in run["field_scores"].values() if m["n_present"] > 0]
    if not scored:
        return {"macro_f1": 0.0, "macro_agreement": 0.0}
    return {
        "macro_f1": statistics.mean(m["f1"] for m in scored),
        "macro_agreement": statistics.mean(m["agreement_present"] for m in scored),
    }


def cells(run: dict) -> dict[tuple[str, str], dict]:
    return {(m["post_id"], m["field"]): m for m in run["mismatches"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()

    base = json.loads(args.baseline.read_text())
    cand = json.loads(args.candidate.read_text())

    print(f"baseline : {base['label']:<20} model={base['model']} prompt={base.get('prompt_sha', '?')} "
          f"variants={','.join(base.get('prompt_variants') or []) or '-'}")
    print(f"candidate: {cand['label']:<20} model={cand['model']} prompt={cand.get('prompt_sha', '?')} "
          f"variants={','.join(cand.get('prompt_variants') or []) or '-'}")
    if base.get("fixture") != cand.get("fixture"):
        print(f"\n!! different fixtures ({base.get('fixture')} vs {cand.get('fixture')}) -- not comparable")

    mb, mc = macro(base), macro(cand)
    print("\n=== Macro ===")
    for key in mb:
        print(f"  {key:<16} {mb[key]:.3f} -> {mc[key]:.3f}  ({mc[key] - mb[key]:+.3f})")

    print("\n=== Per-field f1 (only fields that moved) ===")
    print(f"{'field':<28}{'precision':>22}{'recall':>22}{'f1':>22}")
    for field in sorted(set(base["field_scores"]) | set(cand["field_scores"])):
        b = base["field_scores"].get(field)
        c = cand["field_scores"].get(field)
        if not b or not c or b["f1"] == c["f1"]:
            continue
        row = "".join(f"{b[m]:>8.3f} ->{c[m]:>6.3f}{c[m] - b[m]:>+8.3f}" for m in METRICS)
        print(f"{field:<28}{row}")

    cb, cc = cells(base), cells(cand)
    fixed = sorted(set(cb) - set(cc))
    broken = sorted(set(cc) - set(cb))
    changed = sorted(k for k in set(cb) & set(cc) if cb[k]["candidate"] != cc[k]["candidate"])

    print(f"\n=== Fixed ({len(fixed)}) ===")
    for key in fixed:
        print(f"  {key[0]} / {key[1]}   was [{cb[key]['kind']}] {cb[key]['candidate'] or '(empty)'}")
    print(f"\n=== Newly broken ({len(broken)}) ===")
    for key in broken:
        print(f"  {key[0]} / {key[1]}   now [{cc[key]['kind']}] {cc[key]['candidate'] or '(empty)'}")
        print(f"      gold: {cc[key]['gold'] or '(empty)'}")
    print(f"\n=== Still wrong, differently ({len(changed)}) ===")
    for key in changed:
        print(f"  {key[0]} / {key[1]}")
        print(f"      gold: {cc[key]['gold'] or '(empty)'}")
        print(f"      was:  {cb[key]['candidate'] or '(empty)'}")
        print(f"      now:  {cc[key]['candidate'] or '(empty)'}")

    net = len(fixed) - len(broken)
    print(f"\nNet mismatch change: {len(cb)} -> {len(cc)} ({-net:+d})")
    for run, path in ((base, args.baseline), (cand, args.candidate)):
        if run.get("parse_failures"):
            print(f"  {path.name}: {len(run['parse_failures'])} parse failures")


if __name__ == "__main__":
    main()
