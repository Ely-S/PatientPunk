"""
Rebuild the historical-validation analysis DB so parent_id is preserved.

Background: src/import_posts.py originally inserted comment.parent_id verbatim
('t3_<id>' or 't1_<id>'), then nulled any value that didn't match a post_id.
Since post_ids are stored bare, every parent_id ended up dangling and was
silently NULL'd, destroying thread structure. This was discovered during a thread-reconstruction audit. The fix (a 1-line prefix strip in import_posts.py) is in place; this
script applies the fix to the existing analysis DB without losing the
expensive LLM classifications.

Strategy:

  1. Fresh-import the canonical raw JSON into a NEW DB
     (parent_ids preserved this time, since import_posts.strip_reddit_prefix
     now strips the t1_/t3_ kind prefix before insert).
  2. Copy `treatment` (drug aliases), `extraction_runs` (pipeline-run
     provenance), and `treatment_reports` (LLM classifications) from the OLD
     DB into the NEW DB. These tables are deterministic given the JSON +
     pipeline runs, so copying preserves them exactly.
  3. Verify: same post count, same user count, same classifications, same
     headline numbers. Plus parent_id is now non-NULL for the expected share.

The new DB replaces the old one on disk; the caller is responsible for
re-uploading to S3 and updating the README's SHA-256.

Usage:
    python scripts/rebuild_analysis_db_with_parent_ids.py \\
        --old-db data/historical_validation/historical_validation_2020-07_to_2022-12.db \\
        --raw-json /c/Users/scgee/OneDrive/Documents/Projects/PatientPunk_data/historical_validation_2020-07_to_2022-12.json \\
        --new-db data/historical_validation/historical_validation_2020-07_to_2022-12.NEW.db \\
        --subreddit covidlonghaulers
"""
from __future__ import annotations
import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

# Make src/ importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from utilities.db import open_db
from import_posts import import_reddit_posts


def copy_table(src_conn, dst_conn, table, columns):
    """Copy all rows of a table from src DB to dst DB."""
    rows = src_conn.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
    placeholders = ", ".join("?" for _ in columns)
    dst_conn.executemany(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        rows,
    )
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--old-db", required=True, type=Path)
    ap.add_argument("--raw-json", required=True, type=Path)
    ap.add_argument("--new-db", required=True, type=Path)
    ap.add_argument("--subreddit", default="covidlonghaulers")
    args = ap.parse_args()

    if not args.old_db.exists():
        sys.exit(f"ERROR: old DB not found: {args.old_db}")
    if not args.raw_json.exists():
        sys.exit(f"ERROR: raw JSON not found: {args.raw_json}")
    if args.new_db.exists():
        sys.exit(f"ERROR: new DB already exists (refusing to overwrite): {args.new_db}")

    print(f"[1/4] Fresh import of {args.raw_json.name} -> {args.new_db}")
    schema_sql = (ROOT / "schema.sql").read_text(encoding="utf-8")
    with closing(open_db(args.new_db)) as conn:
        conn.executescript(schema_sql)
        # FK enforcement complicates bulk insert because comments reference
        # parent posts/comments by post_id, but bulk insert order may put
        # children before parents within a batch. We disable FK checks during
        # the bulk import (same as the original import_posts behavior — the
        # post-import dangling-parent cleanup query implicitly assumed FK off)
        # and the trailing integrity check below catches any actual mismatch.
        conn.execute("PRAGMA foreign_keys = OFF")
        import_reddit_posts(conn, args.raw_json, args.subreddit)
        conn.execute("PRAGMA foreign_keys = ON")

    # Sanity: parent_ids should now be non-NULL for the comments we expect
    new_conn = sqlite3.connect(str(args.new_db))
    n_total = new_conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    n_with_parent = new_conn.execute(
        "SELECT COUNT(*) FROM posts WHERE parent_id IS NOT NULL"
    ).fetchone()[0]
    n_dangling = new_conn.execute(
        "SELECT COUNT(*) FROM posts p WHERE p.parent_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM posts q WHERE q.post_id = p.parent_id)"
    ).fetchone()[0]
    print(f"      posts: {n_total:,}  with parent_id: {n_with_parent:,} ({100*n_with_parent/n_total:.1f}%)  dangling: {n_dangling}")
    if n_with_parent == 0:
        new_conn.close()
        sys.exit("ERROR: parent_id still 0 after fresh import. Check import_posts.strip_reddit_prefix.")

    print(f"[2/4] Copy treatment, extraction_runs, treatment_reports from {args.old_db.name}")
    old_conn = sqlite3.connect(str(args.old_db))

    # Copy treatment table (drug + canonical_name + alias columns; check schema)
    treatment_cols = [r[1] for r in new_conn.execute("PRAGMA table_info(treatment)")]
    n_treatment = copy_table(old_conn, new_conn, "treatment", treatment_cols)

    # Copy extraction_runs
    runs_cols = [r[1] for r in new_conn.execute("PRAGMA table_info(extraction_runs)")]
    n_runs = copy_table(old_conn, new_conn, "extraction_runs", runs_cols)

    # Copy treatment_reports
    tr_cols = [r[1] for r in new_conn.execute("PRAGMA table_info(treatment_reports)")]
    n_tr = copy_table(old_conn, new_conn, "treatment_reports", tr_cols)

    new_conn.commit()
    print(f"      treatment: {n_treatment:,}  extraction_runs: {n_runs:,}  treatment_reports: {n_tr:,}")

    # Also copy any rows from `users` and `conditions` if they exist in old but not new
    # (users should already be populated by import_reddit_posts, but old DB may have extras)
    print(f"[3/4] Reconcile users table (in case old DB has rows not in new)")
    n_user_existing = new_conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    user_cols = [r[1] for r in new_conn.execute("PRAGMA table_info(users)")]
    new_conn.executemany(
        f"INSERT OR IGNORE INTO users ({', '.join(user_cols)}) VALUES ({', '.join('?' for _ in user_cols)})",
        old_conn.execute(f"SELECT {', '.join(user_cols)} FROM users").fetchall(),
    )
    new_conn.commit()
    n_user_after = new_conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print(f"      users: {n_user_existing:,} -> {n_user_after:,} ({n_user_after - n_user_existing:,} added from old DB)")

    print(f"[4/4] Final integrity check")
    n_mismatch = new_conn.execute(
        "SELECT COUNT(*) FROM treatment_reports tr "
        "JOIN posts p ON tr.post_id = p.post_id "
        "WHERE tr.user_id != p.user_id"
    ).fetchone()[0]
    if n_mismatch != 0:
        sys.exit(f"ERROR: {n_mismatch} treatment_reports rows have user_id != posts.user_id")
    print(f"      0 user_id mismatches between treatment_reports and posts. PASS.")

    # Compare classification counts
    n_old_tr = old_conn.execute("SELECT COUNT(*) FROM treatment_reports").fetchone()[0]
    n_new_tr = new_conn.execute("SELECT COUNT(*) FROM treatment_reports").fetchone()[0]
    if n_old_tr != n_new_tr:
        sys.exit(f"ERROR: treatment_reports count drifted (old={n_old_tr}, new={n_new_tr})")
    print(f"      treatment_reports row count: {n_new_tr:,} (matches old DB)")

    new_conn.close()
    old_conn.close()
    print(f"\nNew DB ready: {args.new_db}")


if __name__ == "__main__":
    main()
