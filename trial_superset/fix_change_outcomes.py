"""Align the sampled quantity with the label for change-from-baseline endpoints.

NATURAL's sample_ty prompt asks for a value "on the same scale as the outcome description above".
When a trial reports a CHANGE but describes an ABSOLUTE scale (NCT05618587: "Score range 1-49",
reported value -11.3), the model correctly returns an absolute severity and is then scored against a
change -- a guaranteed large error that says nothing about estimate quality (see docs/bugs.md A6).

This rewrites `_outcome_desc` in the experiment YAML for those endpoints so the description states the
change quantity and its sign convention. Detection reuses build_labels_sidecar.is_change, which reads
timeFrame and the description's stated range rather than title wording alone.

Run: PYTHONPATH=trial_superset python -m fix_change_outcomes <save_path> <nct> [experiment_name]
"""

from __future__ import annotations

import json
import os
import re
import sys

import yaml

from build_labels_sidecar import _RANGE_RE, is_change

# Deliberately direction-NEUTRAL. Scales disagree on which way is better -- FSS/BFS are severity
# (higher = worse) while LIFT's FUNCAP55 is capacity (higher = better) -- so stating "negative means
# improvement" would be correct for one and backwards for the other. Define the arithmetic only and
# let the scale description above it carry the meaning.
TEMPLATE = (
    "CHANGE in the {name} ({timeframe}), i.e. follow-up value minus baseline value. {orig} "
    "Report that CHANGE, not the absolute score: a POSITIVE number means the score went up and a "
    "NEGATIVE number means it went down, per the scale described above; 0 means no change{range_hint}."
)


def _trial_path(save_path: str, nct: str) -> str:
    """Completed trials live in nct_reports/, prospective targets in nct_reports_test/."""
    for sub in ("nct_reports", "nct_reports_test"):
        fp = os.path.join(save_path, sub, f"{nct}.json")
        if os.path.exists(fp):
            return fp
    raise FileNotFoundError(f"no trial JSON for {nct} under {save_path}")


def _primary_outcomes(trial_path: str) -> dict[str, dict]:
    """Primary outcomes keyed by name, from results if posted, else from the protocol.

    An active trial has no resultsSection, so its outcomes come from the protocol, where the fields
    are named `measure`/`description`/`timeFrame` rather than `title`/... Only wording detection
    applies there -- with no reported value there is nothing to range-check.
    """
    trial = json.load(open(trial_path, encoding="utf-8"))
    oms = trial.get("resultsSection", {}).get("outcomeMeasuresModule", {}).get("outcomeMeasures", []) or []
    if oms:
        return {om.get("title", ""): om for om in oms if om.get("type") == "PRIMARY"}
    protocol = trial.get("protocolSection", {}).get("outcomesModule", {}).get("primaryOutcomes", []) or []
    return {o.get("measure", ""): {"title": o.get("measure", ""), "timeFrame": o.get("timeFrame", ""),
                                   "description": o.get("description", "")} for o in protocol}


def _first_value(om: dict) -> float | None:
    for cls in om.get("classes", []) or []:
        cats = cls.get("categories") or []
        for m in ((cats[0].get("measurements") or []) if cats else []):
            try:
                return float(str(m.get("value")).replace(",", ""))
            except (TypeError, ValueError):
                return None
    return None


def main() -> None:
    save_path, nct = sys.argv[1], sys.argv[2]
    exp_name = sys.argv[3] if len(sys.argv) > 3 else "noparallel_notbinary"

    exp_fp = os.path.join(save_path, "experiments", exp_name, f"{nct}.yaml")
    doc = yaml.safe_load(open(exp_fp, encoding="utf-8"))
    oms = _primary_outcomes(_trial_path(save_path, nct))

    changed = []
    for name, orig in list((doc.get("_outcome_desc") or {}).items()):
        om = oms.get(name)
        if not om:
            continue
        tf = om.get("timeFrame", "") or ""
        if not is_change(name, tf, orig or "", _first_value(om)):
            continue
        # A 1-49 questionnaire yields changes in roughly -48..+48; state it so the model has a scale.
        m = _RANGE_RE.search(orig or "")
        hint = ""
        if m:
            lo, hi = sorted((float(m.group(1)), float(m.group(2))))
            span = hi - lo
            hint = f" (plausible range about {-span:g} to {span:g})"
        doc["_outcome_desc"][name] = TEMPLATE.format(
            name=name, timeframe=tf.strip().rstrip(".") or "change from baseline",
            orig=(orig or "").strip().rstrip(".") + ".", range_hint=hint,
        )
        changed.append(name)

    if not changed:
        print("no change-from-baseline outcomes found; nothing rewritten")
        return

    yaml.safe_dump(doc, open(exp_fp, "w", encoding="utf-8"), sort_keys=False, width=100)
    print(f"rewrote {len(changed)} outcome description(s) in {exp_fp}:")
    for name in changed:
        print(f"\n  [{name}]\n    {doc['_outcome_desc'][name]}")


if __name__ == "__main__":
    main()
