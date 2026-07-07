#!/usr/bin/env python3
"""Aggregate the in-session sentiment labels into per-drug stats with 95% CIs.

Reads outputs/manual/labels_{ldn,mestinon}_b*.json and prints a report.
"""
from __future__ import annotations
import json, math
from collections import Counter
from pathlib import Path

MAN = Path("outputs/manual")
DRUGS = {
    "low-dose naltrexone (LDN)": ["labels_ldn_b1.json", "labels_ldn_b2.json"],
    "pyridostigmine / Mestinon": ["labels_mestinon_b1.json", "labels_mestinon_b2.json"],
}
Z = 1.96


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + Z**2 / n
    center = (p + Z**2 / (2 * n)) / denom
    half = Z * math.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2)) / denom
    return (max(0, center - half), min(1, center + half))


summary = {}
for label, files in DRUGS.items():
    rows = []
    for f in files:
        rows += json.loads((MAN / f).read_text())
    n = len(rows)
    sent = Counter(r["sentiment"] for r in rows)
    pos, neg, mix, neu = sent["positive"], sent["negative"], sent["mixed"], sent["neutral"]
    exp = pos + neg + mix
    sig = Counter(r["signal"] for r in rows if r["sentiment"] != "neutral")
    se = Counter()
    for r in rows:
        for s in r.get("side_effects", []):
            if s and s not in ("minimal", "unspecified side effects", "side effects", "initial side effects"):
                se[s] += 1
    cond = Counter()
    for r in rows:
        for c in r.get("conditions", []):
            cond[c] += 1

    lo, hi = wilson(pos, exp)
    lo_all, hi_all = wilson(pos, n)
    summary[label] = {
        "classified": n, "experiential": exp, "neutral": neu,
        "positive": pos, "negative": neg, "mixed": mix,
        "pos_pct_of_experiential": round(100 * pos / exp, 1) if exp else None,
        "neg_pct_of_experiential": round(100 * neg / exp, 1) if exp else None,
        "mixed_pct_of_experiential": round(100 * mix / exp, 1) if exp else None,
        "pos_95ci_of_experiential": [round(100 * lo, 1), round(100 * hi, 1)],
    }

    print("=" * 66)
    print(label)
    print("=" * 66)
    print(f"  Classified (random sample) : {n}")
    print(f"  Expressed personal experience: {exp}  ({100*exp/n:.0f}% of sample; rest were questions/info/sourcing)")
    print(f"  --- Among the {exp} experiential reports ---")
    print(f"    Positive : {pos:>3}  ({100*pos/exp:.0f}%)   [95% CI {100*lo:.0f}–{100*hi:.0f}%]")
    print(f"    Mixed    : {mix:>3}  ({100*mix/exp:.0f}%)")
    print(f"    Negative : {neg:>3}  ({100*neg/exp:.0f}%)")
    print(f"    Positive-or-mixed (some benefit): {100*(pos+mix)/exp:.0f}%")
    print(f"  Signal strength (experiential): " + ", ".join(f"{k}={v}" for k, v in sig.most_common()))
    print(f"  Top reported side effects: " + ", ".join(f"{k} ({v})" for k, v in se.most_common(10)))
    if cond:
        print(f"  Conditions tagged: " + ", ".join(f"{k} ({v})" for k, v in cond.most_common()))
    print()

(MAN / "sentiment_summary.json").write_text(json.dumps(summary, indent=2))
print("Wrote", MAN / "sentiment_summary.json")
