"""#2 - validate extraction accuracy against CT.gov ground truth.

Takes trials that have BOTH structured CT.gov results AND an OA paper (the with-results
downloads in m2_outputs). Runs the SAME extractor on the paper (blind to the structured
results - extract() only reads protocolSection), then compares the extracted per-arm primary
value to the trial's actual CT.gov result. High agreement => the 77 paper-only labels are
trustworthy; low agreement => the extractor grabs wrong outcomes/arms/timepoints.

Run from the repo root:
  $env:PYTHONPATH = "trial_superset"
  trial_superset/.venv/Scripts/python.exe trial_superset/extract_validate.py --n 30
"""

from __future__ import annotations

import argparse
import logging
import os
from concurrent.futures import ThreadPoolExecutor

logging.disable(logging.INFO)

from seed_terms import CLUSTER
from run_study import build_cfg
from build_improved import terms_of, classify, M2
from build_labels_sidecar import rows_from_structured
from litlabels.extract_labels import extract, link_paper, MODEL


def close(a, b, rtol=0.10, atol=0.5):
    if a is None or b is None:
        return False
    return abs(a - b) <= max(atol, rtol * max(abs(a), abs(b)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    n = ap.parse_args().n

    from naturalv2.clinical_trial import ClinicalTrial
    from naturalv2.utils import check_trial, check_nonplacebo
    from naturalv2.cli.create_study import resolve_trial_filters
    filters = resolve_trial_filters(build_cfg("x"))

    per = max(1, n // len(CLUSTER))
    picked = []
    for slug in CLUSTER:
        tp = os.path.join(M2, slug, "nct_reports")
        if not os.path.isdir(tp):
            continue
        taken = 0
        for fn in sorted(os.listdir(tp)):
            if not fn.endswith(".json") or taken >= per:
                continue
            p = os.path.join(tp, fn)
            try:
                trial = ClinicalTrial.from_json_file(p)
            except Exception:
                continue
            if not (check_trial(trial, filters)[1] and classify(terms_of(trial), slug)):
                continue
            gt = rows_from_structured(p, check_nonplacebo)  # CT.gov truth (PRIMARY, non-placebo)
            if not gt:
                continue
            link = link_paper(fn[:-5], p)
            if link:
                picked.append((slug, fn[:-5], p, link["pmcid"], gt))
                taken += 1

    def work(item):
        slug, nct, p, pmcid, gt = item
        try:
            ex = extract(nct, p, pmcid)
        except Exception as e:
            return (slug, nct, "ERROR", str(e)[:60], None, None)
        if not (ex and ex.get("extractable")):
            return (slug, nct, "no-extract", (ex or {}).get("note", "")[:60], None, None)
        gt_vals = [g[3] for g in gt if g[3] is not None]            # structured raw values
        ex_vals = [a.get("value") for a in ex.get("arms", []) if a.get("value") is not None]
        ex_vals = [float(v) for v in ex_vals if isinstance(v, (int, float))]
        matched = sum(1 for g in gt_vals if any(close(g, e) for e in ex_vals))
        verdict = "MATCH" if gt_vals and matched == len(gt_vals) else (
            "PARTIAL" if matched else "MISMATCH")
        return (slug, nct, verdict, "", gt_vals, ex_vals)

    print(f"validating {len(picked)} trials (paper extraction vs CT.gov ground truth), {MODEL}\n")
    results = list(ThreadPoolExecutor(max_workers=8).map(work, picked))

    from collections import Counter
    tally = Counter()
    for slug, nct, verdict, note, gt, ex in results:
        tally[verdict] += 1
        line = f"[{slug}] {nct} {verdict}"
        if gt is not None:
            line += f"  truth={[round(x,2) for x in gt]} extracted={[round(x,2) for x in ex]}"
        elif note:
            line += f"  ({note})"
        print(line)
    n_cmp = tally["MATCH"] + tally["PARTIAL"] + tally["MISMATCH"]
    print(f"\nverdicts: {dict(tally)}")
    if n_cmp:
        print(f"full-match rate (of comparable): {tally['MATCH']}/{n_cmp} ({100*tally['MATCH']//n_cmp}%); "
              f"match+partial: {(tally['MATCH']+tally['PARTIAL'])}/{n_cmp}")


if __name__ == "__main__":
    main()
