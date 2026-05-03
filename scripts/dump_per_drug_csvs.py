"""
Dump per-drug CSVs from the single self-sufficient analysis database
(historical_validation_2020-07_to_2022-12.db).

For each of the six target drugs:
  - {drug}_reports_merged.csv  - all classified reports for the drug in
                                 the pre-publication window (one row per post)
  - {drug}_reports_dedup.csv   - same, after the per-(user, drug) dedup rule
                                 (most recent + signal-strength tiebreaker)

Plus a one-row-per-drug summary:
  - summary.csv                - n, %positive, Wilson 95% CI, p-value vs 50%

Outputs land in data/historical_validation/merged/.

This is the CLEAN replacement for the earlier merge_and_analyze_historical.py
script: there is no cross-DB merging — the single combined database is the
sole source of truth.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from scipy.stats import binomtest
from statsmodels.stats.proportion import proportion_confint

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path("C:/Users/scgee/OneDrive/Documents/Projects/PatientPunk")
DB   = ROOT / "data/historical_validation/historical_validation_2020-07_to_2022-12.db"
OUT  = ROOT / "data/historical_validation/merged"

DRUGS = {
    "famotidine":  {"cutoff": "2021-06-06", "trial_dir": "+", "paper": "Glynne et al. 2021"},
    "loratadine":  {"cutoff": "2021-06-06", "trial_dir": "+", "paper": "Glynne et al. 2021"},
    "prednisone":  {"cutoff": "2021-10-25", "trial_dir": "0", "paper": "Utrero-Rico et al. 2021"},
    "naltrexone":  {"cutoff": "2022-07-02", "trial_dir": "+", "paper": "O'Kelly et al. 2022"},
    "paxlovid":    {"cutoff": "2024-06-06", "trial_dir": "0", "paper": "Geng et al. (STOP-PASC) 2024"},
    "colchicine":  {"cutoff": "2025-10-19", "trial_dir": "0", "paper": "Bassi et al. 2025"},
}
END_2022 = "2022-12-31"
SIG_RANK = {"strong": 3, "moderate": 2, "weak": 1, "n/a": 0, None: 0, "": 0}


def epoch_eod(date_str: str) -> int:
    return int(datetime.strptime(date_str, "%Y-%m-%d").replace(
        tzinfo=timezone.utc, hour=23, minute=59, second=59).timestamp())


def fetch_reports(drug: str, cutoff_ts: int) -> pd.DataFrame:
    """Posts where p.user_id = 'deleted' (the placeholder for `[deleted]`/
    `[removed]` Reddit authors) are excluded — those rows come from many
    distinct real users we cannot identify, and collapsing them under one
    pseudo-user would give the entire deleted population one vote per drug."""
    with sqlite3.connect(DB.as_posix()) as conn:
        return pd.read_sql_query("""
            SELECT tr.user_id,
                   lower(t.canonical_name) AS drug,
                   tr.sentiment,
                   tr.signal_strength      AS sig,
                   p.post_date,
                   tr.post_id
            FROM treatment_reports tr
            JOIN treatment t ON tr.drug_id = t.id
            JOIN posts     p ON tr.post_id = p.post_id
            WHERE lower(t.canonical_name) = ?
              AND p.post_date IS NOT NULL
              AND p.post_date <= ?
              AND p.user_id != 'deleted'
        """, conn, params=(drug, cutoff_ts))


def dedup_recent_then_strength(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["sig_rank"] = df["sig"].map(lambda s: SIG_RANK.get(s, 0))
    df = df.sort_values(["user_id", "drug", "post_date", "sig_rank"],
                        ascending=[True, True, False, False])
    return (df.drop_duplicates(subset=["user_id", "drug"], keep="first")
              .drop(columns="sig_rank"))


def stats_row(df: pd.DataFrame, drug: str, info: dict) -> dict:
    n = len(df)
    pos  = int((df["sentiment"] == "positive").sum())
    neg  = int((df["sentiment"] == "negative").sum())
    neu  = int((df["sentiment"] == "neutral").sum())
    mix  = int((df["sentiment"] == "mixed").sum())
    nonr = neg + neu + mix
    if n == 0:
        pos_lo = pos_hi = nonr_lo = nonr_hi = 0.0
        p = 1.0
    else:
        pos_lo, pos_hi   = proportion_confint(pos,  n, alpha=0.05, method="wilson")
        nonr_lo, nonr_hi = proportion_confint(nonr, n, alpha=0.05, method="wilson")
        p = binomtest(pos, n, 0.5, alternative="two-sided").pvalue
    return {
        "drug": drug,
        "trial_dir": info["trial_dir"],
        "paper": info["paper"],
        "cutoff": info["cutoff"],
        "effective_cutoff": min(info["cutoff"], END_2022),
        "n": n,
        "pos": pos,
        "nonr": nonr,
        "pos_pct": pos / n * 100 if n else 0,
        "pos_lo_pct": pos_lo * 100,
        "pos_hi_pct": pos_hi * 100,
        "nonr_pct": nonr / n * 100 if n else 0,
        "nonr_lo_pct": nonr_lo * 100,
        "nonr_hi_pct": nonr_hi * 100,
        "p_vs_50": p,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Source DB: {DB.relative_to(ROOT)}")
    print()
    print(f"{'drug':<12} {'trial':<6} {'cutoff':<12} {'eff':<12} "
          f"{'n':>5} {'pos':>5} {'%pos':>6} {'95% CI':>20} {'p':>9}")
    print("-" * 95)

    rows = []
    for drug, info in DRUGS.items():
        cutoff_ts = epoch_eod(min(info["cutoff"], END_2022))
        merged = fetch_reports(drug, cutoff_ts)
        deduped = dedup_recent_then_strength(merged)
        merged.to_csv(OUT / f"{drug}_reports_merged.csv", index=False)
        deduped.to_csv(OUT / f"{drug}_reports_dedup.csv",  index=False)

        s = stats_row(deduped, drug, info)
        rows.append(s)
        ci = f"[{s['pos_lo_pct']:.1f}%, {s['pos_hi_pct']:.1f}%]"
        print(f"{drug:<12} {info['trial_dir']:<6} {info['cutoff']:<12} "
              f"{s['effective_cutoff']:<12} {s['n']:>5} {s['pos']:>5} "
              f"{s['pos_pct']:>5.1f}% {ci:>20} {s['p_vs_50']:>9.4f}")

    pd.DataFrame(rows).to_csv(OUT / "summary.csv", index=False)
    print()
    print(f"Wrote per-drug CSVs and summary.csv to {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
