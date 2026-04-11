#!/usr/bin/env python3
"""Expand first N classified and unclassified treatment reports with full thread context.

Usage:
    # First 10 classified + 10 unclassified
    python analysis_scripts/expand_reports.py --db data/posts.db -n 10

    # Save to file
    python analysis_scripts/expand_reports.py --db data/posts.db -n 20 -o sample.json
"""
import argparse
import json
import sqlite3
from pathlib import Path


def get_ancestors(conn: sqlite3.Connection, post_id: str) -> list[str]:
    """Walk up the parent chain, return ancestor texts oldest-first (excluding the post itself)."""
    ancestors = []
    row = conn.execute("SELECT parent_id FROM posts WHERE post_id = ?", (post_id,)).fetchone()
    current = row[0] if row else None
    while current:
        row = conn.execute("SELECT parent_id, title, body_text FROM posts WHERE post_id = ?", (current,)).fetchone()
        if not row:
            break
        text = f"{row[1]}\n{row[2]}" if row[1] else row[2]
        ancestors.append(text)
        current = row[0]
    ancestors.reverse()
    return ancestors


def expand_reports(db_path: Path, n: int) -> dict:
    conn = sqlite3.connect(db_path)

    # --- Classified (in treatment_reports) ---
    rows = conn.execute(
        "SELECT tr.post_id, tr.sentiment, tr.signal_strength, "
        "t.canonical_name, p.body_text "
        "FROM treatment_reports tr "
        "JOIN treatment t ON t.id = tr.drug_id "
        "JOIN posts p ON p.post_id = tr.post_id "
        "LIMIT ?",
        (n,),
    ).fetchall()
    classified = []
    for post_id, sentiment, signal, drug, comment_text in rows:
        classified.append({
            "drug": drug,
            "sentiment": sentiment,
            "signal": signal,
            "ancestors": get_ancestors(conn, post_id),
            "comment": comment_text,
        })

    # --- Unclassified (posts with no treatment_reports entry) ---
    unclassified_rows = conn.execute(
        "SELECT post_id, body_text FROM posts "
        "WHERE body_text != '' AND post_id NOT IN (SELECT DISTINCT post_id FROM treatment_reports) "
        "LIMIT ?",
        (n,),
    ).fetchall()

    unclassified = []
    for post_id, comment_text in unclassified_rows:
        unclassified.append({
            "ancestors": get_ancestors(conn, post_id),
            "comment": comment_text,
        })

    conn.close()
    return {"classified": classified, "unclassified": unclassified}


def main():
    parser = argparse.ArgumentParser(description="Sample classified and unclassified treatment reports")
    parser.add_argument("--db", required=True, help="Path to SQLite database")
    parser.add_argument("-n", type=int, default=10, help="Number of each to sample (default: 10)")
    parser.add_argument("-o", "--output", help="Output JSON file (default: stdout)")
    args = parser.parse_args()

    results = expand_reports(Path(args.db), args.n)

    output = json.dumps(results, indent=2)
    if args.output:
        Path(args.output).write_text(output)
        print(f"Wrote {len(results['classified'])} classified + {len(results['unclassified'])} unclassified to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
