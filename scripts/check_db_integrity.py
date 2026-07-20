"""Report foreign-key violations and thread-link health for pipeline databases.

Enforcement only governs NEW writes, so it can say nothing about rows already on disk.
Thread-link health is reported alongside because the failure this pipeline suffered is not a
constraint violation at all: nulling every parent_id leaves a database that is perfectly valid
and useless, and foreign_key_check returns clean on it.

    python scripts/check_db_integrity.py data/*.db

Exits non-zero on any violation so it can gate a run.
"""
import argparse
import sqlite3
import sys
from pathlib import Path


def inspect(path: Path) -> dict:
    """Read-only integrity summary for one database.

    Always returns a dict; an unreadable file comes back with an "error" key rather than being
    dropped, so "no problems found" can never be confused with "never looked". The URI comes
    from Path.as_uri(), which percent-encodes and needs an absolute path.
    """
    if not path.is_file():
        return {"db": str(path), "error": "not a file"}
    try:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    except (sqlite3.Error, ValueError, OSError) as exc:
        return {"db": str(path), "error": str(exc)}
    try:
        # sqlite_master preserves the declared case, so a database created with "Posts" would
        # otherwise be reported as having no posts table and skipped.
        tables = {row[0].lower() for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "posts" not in tables:
            return {"db": str(path), "skipped": "no posts table"}

        report = {"db": path.name, "violations": conn.execute(
            "PRAGMA foreign_key_check").fetchall()}
        report["posts"] = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        if not report["posts"]:
            return report

        report["linked"] = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE parent_id IS NOT NULL").fetchone()[0]
        # A parent_id pointing at no row: what enforcement would now reject.
        report["dangling"] = conn.execute(
            "SELECT COUNT(*) FROM posts p WHERE p.parent_id IS NOT NULL AND NOT EXISTS "
            "(SELECT 1 FROM posts q WHERE q.post_id = p.parent_id)").fetchone()[0]
        return report
    except sqlite3.Error as exc:
        return {"db": str(path), "error": str(exc)}
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("databases", nargs="+", type=Path)
    args = parser.parse_args()

    results = [inspect(path) for path in args.databases]
    reports = [item for item in results if "violations" in item]
    unreadable = [item for item in results if "error" in item]
    skipped = [item for item in results if "skipped" in item]

    if reports:
        header = f"{'database':44} {'posts':>10} {'has parent':>11} {'dangling':>9} {'FK viol':>8}"
        print(f"{header}\n{'-' * len(header)}")
    for report in reports:
        linked = report.get("linked", 0)
        share = f"{linked / report['posts']:.1%}" if report["posts"] else "-"
        print(f"{report['db']:44} {report['posts']:>10,} {share:>11} "
              f"{report.get('dangling', 0):>9,} {len(report['violations']):>8,}")

    # Say what was not examined. Staying quiet about it is how "nothing to report" becomes
    # indistinguishable from "nothing was checked".
    for report in skipped:
        print(f"{report['db']:44} skipped — {report['skipped']}")
    if unreadable:
        print(f"\nERROR: {len(unreadable)} path(s) could not be read:")
        for report in unreadable:
            print(f"    {report['db']}: {report['error']}")
        return 1
    if not reports:
        print("No pipeline databases found (none had a posts table).")
        return 0

    severed = [report for report in reports if report["posts"] and not report.get("linked")]
    broken = [report for report in reports if report["violations"]]
    if severed:
        print(f"\nWARNING: {len(severed)} database(s) have ZERO thread links — the signature of "
              f"the id-shape import bug, not a constraint failure:")
        for report in severed:
            print(f"    {report['db']} ({report['posts']:,} posts)")
    if broken:
        print(f"\nFAIL: {len(broken)} database(s) violate declared foreign keys:")
        for report in broken:
            tables = sorted({violation[0] for violation in report["violations"]})
            print(f"    {report['db']}: {len(report['violations'])} in {', '.join(tables)}")
        return 1
    print("\nOK: no foreign-key violations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
