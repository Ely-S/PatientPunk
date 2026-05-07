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

By default, reads the DB via the canonical resolver in
`docs/RCT_historical_validation/paths.py` (env var `RCT_DB_PATH` →
package-anchor walk-up) and writes outputs into a `merged/` subdirectory of
the package's `data/` folder. Both can be overridden via --db and --out.

This is the CLEAN replacement for the earlier merge_and_analyze_historical.py
script: there is no cross-DB merging — the single combined database is the
sole source of truth.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from scipy.stats import binomtest
from statsmodels.stats.proportion import proportion_confint

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# This script lives at <repo>/scripts/dump_per_drug_csvs.py. The RCT
# validation package — including paths.py, the canonical DB resolver — lives
# at <repo>/docs/RCT_historical_validation/. We bootstrap sys.path to import
# it so this script and the in-package entry points share one resolver.
_REPO_ROOT      = Path(__file__).resolve().parents[1]
_RCT_PKG        = _REPO_ROOT / "docs" / "RCT_historical_validation"
if str(_RCT_PKG) not in sys.path:
    sys.path.insert(0, str(_RCT_PKG))
from paths import (  # noqa: E402
    PathResolutionError,
    db_path as resolve_db_path,
    data_dir as resolve_data_dir,
)

# Each drug's "cutoff" here is the publication date of the comparator paper.
# The SQL predicate is "post_date < epoch_midnight(cutoff)", so any post on or
# after the publication date is excluded. The end-2022 cap (exclusive at
# 2023-01-01) binds for paxlovid and colchicine.
DRUGS = {
    "famotidine":  {"pub_date": "2021-06-07", "trial_dir": "+", "paper": "Glynne et al. 2021"},
    "loratadine":  {"pub_date": "2021-06-07", "trial_dir": "+", "paper": "Glynne et al. 2021"},
    "prednisone":  {"pub_date": "2021-10-26", "trial_dir": "0", "paper": "Utrero-Rico et al. 2021"},
    "naltrexone":  {"pub_date": "2022-07-03", "trial_dir": "+", "paper": "O'Kelly et al. 2022"},
    "paxlovid":    {"pub_date": "2024-06-07", "trial_dir": "0", "paper": "Geng et al. (STOP-PASC) 2024"},
    "colchicine":  {"pub_date": "2025-10-20", "trial_dir": "0", "paper": "Bassi et al. 2025"},
}
END_2022_EXCLUSIVE = "2023-01-01"
SIG_RANK = {"strong": 3, "moderate": 2, "weak": 1, "n/a": 0, None: 0, "": 0}


def epoch_midnight(date_str: str) -> int:
    """UTC-midnight epoch for the given YYYY-MM-DD."""
    return int(datetime.strptime(date_str, "%Y-%m-%d").replace(
        tzinfo=timezone.utc).timestamp())


def fetch_reports(db_path: Path, drug: str, window_end_exclusive_ts: int) -> pd.DataFrame:
    """Pulls reports with post_date strictly before the given midnight epoch
    (the publication date, or 2023-01-01 if the end-2022 cap binds).

    Posts where p.user_id = 'deleted' (the placeholder for `[deleted]`/
    `[removed]` Reddit authors) are excluded — those rows come from many
    distinct real users we cannot identify, and collapsing them under one
    pseudo-user would give the entire deleted population one vote per drug."""
    with sqlite3.connect(db_path.as_posix()) as conn:
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
              AND p.post_date < ?
              AND p.user_id != 'deleted'
        """, conn, params=(drug, window_end_exclusive_ts))


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
        "pub_date": info["pub_date"],
        "window_end_exclusive": min(info["pub_date"], END_2022_EXCLUSIVE),
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


def _try_relative(path: Path, anchor: Path) -> Path:
    """Display path relative to anchor when possible, else absolute."""
    try:
        return path.resolve().relative_to(anchor)
    except ValueError:
        return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db", type=Path, default=None,
        help=("Path to the analysis SQLite DB. If omitted, paths.py resolves it: "
              "RCT_DB_PATH env var → anchor walk-up to the package root."),
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help=("Directory to write per-drug CSVs and summary.csv. "
              "If omitted, defaults to <package_root>/data/merged/."),
    )
    args = parser.parse_args(argv)

    # ── Resolve DB ──
    if args.db is not None:
        db: Path = args.db.resolve()
        if not db.exists():
            sys.exit(
                f"ERROR: analysis DB not found at {db}\n"
                f"See docs/RCT_historical_validation/README.md for download instructions."
            )
    else:
        try:
            db = resolve_db_path()
        except PathResolutionError as e:
            sys.exit(f"ERROR: {e}")

    # ── Resolve output dir ──
    if args.out is not None:
        out: Path = args.out
    else:
        try:
            out = resolve_data_dir() / "merged"
        except PathResolutionError as e:
            sys.exit(f"ERROR: {e}")

    out.mkdir(parents=True, exist_ok=True)
    print(f"Source DB: {_try_relative(db, _REPO_ROOT)}")
    print()
    print(f"{'drug':<12} {'trial':<6} {'pub_date':<12} {'win_end_excl':<14} "
          f"{'n':>5} {'pos':>5} {'%pos':>6} {'95% CI':>20} {'p':>9}")
    print("-" * 99)

    rows = []
    for drug, info in DRUGS.items():
        window_end_exclusive = min(info["pub_date"], END_2022_EXCLUSIVE)
        cutoff_ts = epoch_midnight(window_end_exclusive)
        merged = fetch_reports(db, drug, cutoff_ts)
        deduped = dedup_recent_then_strength(merged)
        merged.to_csv(out / f"{drug}_reports_merged.csv", index=False)
        deduped.to_csv(out / f"{drug}_reports_dedup.csv", index=False)

        s = stats_row(deduped, drug, info)
        rows.append(s)
        ci = f"[{s['pos_lo_pct']:.1f}%, {s['pos_hi_pct']:.1f}%]"
        print(f"{drug:<12} {info['trial_dir']:<6} {info['pub_date']:<12} "
              f"{s['window_end_exclusive']:<14} {s['n']:>5} {s['pos']:>5} "
              f"{s['pos_pct']:>5.1f}% {ci:>20} {s['p_vs_50']:>9.4f}")

    pd.DataFrame(rows).to_csv(out / "summary.csv", index=False)
    print()
    print(f"Wrote per-drug CSVs and summary.csv to {_try_relative(out, _REPO_ROOT)}/")


if __name__ == "__main__":
    main()
