#!/usr/bin/env python3
"""Build a unified analysis database from the current pipeline outputs.

Combines, keyed on author_hash:
  * the corpus + drug sentiment already in data/posts.db -- users, posts,
    treatment, treatment_reports, written by src/import_posts.py and
    src/run_sentiment_pipeline.py; and
  * the variable-extraction outputs output/records.csv (demographic/clinical
    fields + inductively-discovered variables) and
    output/demographics_deductive.csv,

into a single SQLite database (default: patientpunk.db) holding:
  * the full relational schema -- users/posts/treatment/treatment_reports plus
    user_profiles/conditions/variables; and
  * a wide, clustering-ready `unified` table: one row per record, with every
    variable column + demo_* demographics + per-author drug-sentiment rollups.

This replaces the old bridge that expected Polina's database_creation outputs
(sentiment_cache.json / canonical_map.json); drug sentiment now lives directly
in data/posts.db.

Usage:
    python load_db.py
    python load_db.py --posts-db data/posts.db --records output/records.csv \
        --demographics output/demographics_deductive.csv --db patientpunk.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE / "variable_extraction"))
sys.path.insert(0, str(HERE / "src"))

import pandas as pd

from patientpunk.db import (
    init_db,
    load_extractions,
    load_variables,
    query_treatment_outcomes,
    register_run,
)

try:
    from utilities import get_git_commit  # src/utilities
except Exception:  # utilities pulls optional deps; provenance is best-effort
    def get_git_commit() -> str:
        return "unknown"


def _backup_db(src_db: Path, dst_db: Path) -> None:
    """Copy *src_db* -> *dst_db* via the sqlite backup API (full overwrite)."""
    if dst_db.exists():
        dst_db.unlink()
    src = sqlite3.connect(src_db)
    dst = sqlite3.connect(dst_db)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()


def build_unified(conn: sqlite3.Connection, records_csv: Path,
                  demographics_csv: Path | None) -> int:
    """Build the wide, clustering-ready ``unified`` table (one row per record).

    records.csv  LEFT JOIN  demographics (``demo_*`` prefix)  LEFT JOIN
    per-author drug-sentiment rollup -- all on ``author_hash``.
    """
    uni = pd.read_csv(records_csv, dtype=str).fillna("")

    if demographics_csv and demographics_csv.exists():
        demo_df = pd.read_csv(demographics_csv, dtype=str).fillna("")
        demo_df = demo_df.rename(
            columns={c: f"demo_{c}" for c in demo_df.columns if c != "author_hash"}
        ).drop_duplicates("author_hash")
        uni = uni.merge(demo_df, on="author_hash", how="left")

    # Per-author drug-sentiment rollup from treatment_reports (already in the DB).
    drug_rows = conn.execute(
        """
        SELECT tr.user_id                              AS author_hash,
               GROUP_CONCAT(DISTINCT t.canonical_name) AS drugs_mentioned,
               COUNT(*)                                AS n_drug_reports,
               SUM(CASE WHEN tr.sentiment='positive' THEN 1 ELSE 0 END) AS drugs_positive,
               SUM(CASE WHEN tr.sentiment='negative' THEN 1 ELSE 0 END) AS drugs_negative
        FROM treatment_reports tr
        JOIN treatment t ON t.id = tr.drug_id
        GROUP BY tr.user_id
        """
    ).fetchall()
    drug_df = pd.DataFrame(
        drug_rows,
        columns=["author_hash", "drugs_mentioned", "n_drug_reports",
                 "drugs_positive", "drugs_negative"],
    )
    if not drug_df.empty:
        uni = uni.merge(drug_df, on="author_hash", how="left")

    uni = uni.fillna("")
    uni.to_sql("unified", conn, if_exists="replace", index=False)
    conn.commit()
    return len(uni)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--posts-db", type=Path, default=HERE / "data" / "posts.db",
                        help="SQLite DB with corpus + drug sentiment (default: data/posts.db).")
    parser.add_argument("--records", type=Path, default=HERE / "output" / "records.csv",
                        help="Variable-extraction records.csv (default: output/records.csv).")
    parser.add_argument("--demographics", type=Path,
                        default=HERE / "output" / "demographics_deductive.csv",
                        help="Deductive demographics CSV (optional).")
    parser.add_argument("--db", type=Path, default=HERE / "patientpunk.db",
                        help="Output unified database (default: patientpunk.db).")
    parser.add_argument("--schema-sql", type=Path, default=HERE / "schema.sql",
                        help="Schema DDL (default: schema.sql).")
    args = parser.parse_args(argv)

    if not args.posts_db.exists():
        sys.exit(f"Missing posts DB: {args.posts_db}\n"
                 f"  (run src/import_posts.py + src/run_sentiment_pipeline.py first)")
    if not args.records.exists():
        sys.exit(f"Missing records.csv: {args.records}\n"
                 f"  (run variable_extraction/main.py run first)")
    if not args.schema_sql.exists():
        sys.exit(f"Missing schema: {args.schema_sql}")
    demographics = args.demographics if args.demographics.exists() else None
    if demographics is None:
        print(f"  ! demographics CSV not found ({args.demographics}); skipping demographics layer")

    print(f"Posts DB:   {args.posts_db}")
    print(f"Output DB:  {args.db}")

    # 1. Copy corpus + drug sentiment forward into the output DB.
    _backup_db(args.posts_db, args.db)

    # 2. Ensure the full schema (adds user_profiles / conditions / variables).
    conn = init_db(args.db, schema_sql=args.schema_sql)

    # 3. Register this enrichment run for provenance.
    run_id = register_run(
        conn, "variable_extraction",
        {"records": str(args.records), "demographics": str(demographics or "")},
        commit_hash=get_git_commit(),
    )

    # 4. Demographics first (clean age/sex/loc), then records (conditions).
    #    load_extractions merges fill-NULL, so demographics values win.
    if demographics:
        load_extractions(conn, demographics, run_id=run_id)
    load_extractions(conn, args.records, run_id=run_id)

    # 5. Full variable matrix -> EAV table (includes discovered variables).
    n_vars = load_variables(conn, args.records, run_id)

    # 6. Wide, clustering-ready table.
    n_unified = build_unified(conn, args.records, demographics)

    # 7. Summary.
    def _count(table: str) -> int:
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.Error:
            return -1

    print("\n  Tables:")
    for table in ("users", "posts", "treatment", "treatment_reports",
                  "user_profiles", "conditions", "variables", "unified"):
        print(f"    {table:<18} {_count(table):>6}")
    print(f"\n  variables EAV rows: {n_vars}   unified rows: {n_unified}")

    outcomes = query_treatment_outcomes(conn)
    if outcomes:
        print("\n  Top drugs by report count:")
        for r in outcomes[:8]:
            print(f"    {r['drug']:<28} {r['n_reports']:>3} reports  "
                  f"(+{r['pct_positive'] or 0:.0f}% / -{r['pct_negative'] or 0:.0f}%)")

    conn.close()
    print(f"\nDone -> {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
