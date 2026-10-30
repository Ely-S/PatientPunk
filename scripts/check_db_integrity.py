"""Report thread links and foreign-key violations for pipeline databases.

    python scripts/check_db_integrity.py data/*.db

A database where every comment lost its parent_id still passes PRAGMA foreign_key_check,
so "has parent" is the column to watch: 0% with posts present means the threads are gone.
Exits 1 if a file cannot be read or a foreign key is violated.
"""
import sqlite3
import sys
from pathlib import Path


def check(path: Path) -> tuple[int, int, int, int]:
    """Posts, posts with a parent, parents pointing at no row, and foreign-key violations."""
    # Read-only. as_uri() percent-encodes characters such as '#', which would otherwise end
    # the URI early, drop mode=ro and make SQLite create a new file.
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        def count(sql: str) -> int:
            return conn.execute(sql).fetchone()[0]
        return (count("SELECT COUNT(*) FROM posts"),
                count("SELECT COUNT(*) FROM posts WHERE parent_id IS NOT NULL"),
                count("SELECT COUNT(*) FROM posts p WHERE parent_id IS NOT NULL"
                      " AND NOT EXISTS (SELECT 1 FROM posts q WHERE q.post_id = p.parent_id)"),
                len(conn.execute("PRAGMA foreign_key_check").fetchall()))
    finally:
        conn.close()


def main(paths: list[str]) -> int:
    if not paths:
        sys.exit(__doc__)
    failed = False
    print(f"{'database':44} {'posts':>10} {'has parent':>11} {'dangling':>9} {'FK viol':>8}")
    for name in paths:
        path = Path(name)
        try:
            posts, linked, dangling, violations = check(path)
        except sqlite3.Error as exc:  # a missing file or a folder lands here too
            if "no such table: posts" in str(exc):
                print(f"{path.name:44} skipped: no posts table")
            else:
                print(f"{path.name:44} could not be read: {exc}")
                failed = True
            continue
        share = f"{linked / posts:.1%}" if posts else "-"
        flag = "  <- no thread links" if posts and not linked else ""
        print(f"{path.name:44} {posts:>10,} {share:>11} {dangling:>9,} {violations:>8,}{flag}")
        failed = failed or violations > 0
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
