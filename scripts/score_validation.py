#!/usr/bin/env python3
"""Score a human-reviewed validation sheet built by build_validation_sample.py.

Prints per-field precision with Wilson 95% intervals, overall and per stratum,
a pass/fail line against each protocol target (docs/validation_protocol.md),
and the three PEM / severity answers the report needs. Output is aggregates
only, so it can be pasted into docs/psychedelics_v2_validation_report.md.

Usage:
    uv run python scripts/score_validation.py data/validation/psychedelics_v2_sample.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from statsmodels.stats.proportion import proportion_confint

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_validation_sample import PEM_COLUMN, SCORE_COLUMNS  # noqa: E402

VERDICTS = {"correct", "incorrect", "unclear"}
PEM_VERDICTS = {"yes", "no", "unclear"}

# Protocol targets: minimum precision, applied to correct / (correct + incorrect).
TARGETS = {
    "quote_supports_field": 1.00,
    "drug_attribution": 0.95,
    "self_actual_use": 0.95,
    "dose": 0.90,
    "duration": 0.90,
    "ae_category": 0.90,
    "ae_severity": 0.90,
}


def load_sheet(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path, keep_default_na=False, dtype=str)
    for col in (*SCORE_COLUMNS, PEM_COLUMN):
        d[col] = d[col].str.strip().str.lower()
    bad = []
    for col in SCORE_COLUMNS:
        bad += [(col, v) for v in set(d[col]) - VERDICTS - {"n/a", ""}]
    bad += [(PEM_COLUMN, v) for v in set(d[PEM_COLUMN]) - PEM_VERDICTS - {"n/a", ""}]
    if bad:
        raise SystemExit(f"unrecognised verdicts: {sorted(bad)}")
    return d


def precision(verdicts: pd.Series) -> dict:
    k = int((verdicts == "correct").sum())
    wrong = int((verdicts == "incorrect").sum())
    n = k + wrong
    lo, hi = proportion_confint(k, n, method="wilson") if n else (float("nan"),) * 2
    return {"correct": k, "incorrect": wrong, "unclear": int((verdicts == "unclear").sum()),
            "n": n, "precision": k / n if n else float("nan"), "ci_low": lo, "ci_high": hi}


def field_table(d: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([{"field": c, **precision(d[c])} for c in SCORE_COLUMNS])


def _pct(x: float) -> str:
    return "—" if pd.isna(x) else f"{x:.1%}"


def _md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def _fmt(t: pd.DataFrame) -> pd.DataFrame:
    t = t.copy()
    t["precision"] = t["precision"].map(_pct)
    t["95% Wilson"] = [f"{_pct(lo)}–{_pct(hi)}" if not pd.isna(lo) else "—"
                       for lo, hi in zip(t.pop("ci_low"), t.pop("ci_high"))]
    return t


def pem_share(d: pd.DataFrame, stratum: str) -> str:
    v = d.loc[d["stratum"].eq(stratum), PEM_COLUMN]
    yes, no = int((v == "yes").sum()), int((v == "no").sum())
    n = yes + no
    if not n:
        return f"{stratum}: not scored"
    lo, hi = proportion_confint(yes, n, method="wilson")
    return (f"{stratum}: {yes} of {n} describe PEM ({yes / n:.1%}, Wilson {lo:.1%}–{hi:.1%}); "
            f"{int((v == 'unclear').sum())} unclear")


def report(d: pd.DataFrame) -> str:
    unscored = {c: int((d[c] == "").sum()) for c in (*SCORE_COLUMNS, PEM_COLUMN)}
    out = [f"Rows: {len(d)}  ·  seed {d['seed'].iloc[0]}  ·  run `{d['run_id'].iloc[0]}`"]
    if any(unscored.values()):
        out.append("**Unscored cells:** " + ", ".join(f"{k} {v}" for k, v in unscored.items() if v))

    overall = field_table(d)
    out += ["", "### Precision by field (all strata)", "",
            "Precision = correct / (correct + incorrect); `unclear` is excluded and counted.", "",
            _md(_fmt(overall))]

    lines = []
    for _, r in overall.iterrows():
        target = TARGETS.get(r["field"])
        if target is None:
            continue
        if not r["n"]:
            lines.append(f"- `{r['field']}` ≥{target:.0%}: NOT SCORED")
            continue
        verdict = "PASS" if r["precision"] >= target else "FAIL"
        bound = "lower bound clears it" if r["ci_low"] >= target else "lower bound does not"
        lines.append(f"- `{r['field']}` ≥{target:.0%}: **{verdict}** "
                     f"({_pct(r['precision'])}, n={r['n']}; {bound})")
    out += ["", "### Against the protocol targets", "", *lines]

    per = []
    for stratum, sub in d.groupby("stratum", sort=False):
        t = field_table(sub)
        per.append(t[t["n"] > 0].assign(stratum=stratum))
    per = pd.concat(per)[["stratum", "field", "correct", "incorrect", "unclear", "n",
                          "precision", "ci_low", "ci_high"]]
    out += ["", "### Precision by stratum", "", _md(_fmt(per))]

    out += ["", "### PEM", ""]
    out += [f"- {pem_share(d, s)}" for s in
            ("pem_explicit", "fatigue_ketamine", "fatigue_psilocybin_lsd", "random_helped")]
    severe = precision(d.loc[d["stratum"].eq("severe_adverse_event"), "ae_severity"])
    out += ["", "### Severe adverse events", "",
            f"- severity `severe` confirmed by the prompt's definition: {severe['correct']} of "
            f"{severe['n']} ({_pct(severe['precision'])}, Wilson {_pct(severe['ci_low'])}–"
            f"{_pct(severe['ci_high'])}); {severe['unclear']} unclear"]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("sheet", type=Path)
    print(report(load_sheet(ap.parse_args().sheet)))


if __name__ == "__main__":
    main()
