#!/usr/bin/env python3
"""
Single-command reproducibility verification for the RCT historical
validation paper.

Runs every build-time assertion in one shot and prints a PASS/FAIL
summary. Intended for reviewers who want a one-command "is everything
as it should be?" gate without spinning up a Jupyter notebook build.

What this checks:

  - DB integrity (treatment_reports.user_id matches posts.user_id)
  - DB SHA-256 matches the value published in the README
  - Per-drug post_date window (every included report strictly < cutoff;
    zero NULL post_dates)
  - Thread reconstruction (zero dangling parent_ids, zero cycles in
    the parent edge graph)
  - Dedup audit (informational — raw vs unique-user counts, plus
    sensitivity to alternative dedup rules; never fails)
  - Expected-output assertion (every drug's n / pos / pos_pct / p
    matches the frozen expected table within rounding tolerance)

Usage:

    cd docs/RCT_historical_validation/
    python verify.py
    # or with an explicit DB path:
    python verify.py --db data/historical_validation_2020-07_to_2022-12.db

Exit code: 0 if all checks pass, 1 otherwise.

These constants must stay in sync with _build_paper_figures.py. If the
analytical pipeline or DB content changes legitimately, update both.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make sibling module `paths` importable when verify.py is invoked from
# any cwd. paths.py lives next to this file at the package root.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import (  # noqa: E402
    PathResolutionError,
    db_path as resolve_db_path,
)

# ── Constants — must stay in sync with _build_paper_figures.py ─────────────

EXPECTED_DB_SHA256 = "c50fcacd7ce366f397152f5fe4dbb59d5eaf64ba32627faef91dad86fbf6c6f4"

END_2022_EXCLUSIVE = "2023-01-01"

DRUG_CUTOFFS = {
    # drug -> publication_date_yyyy_mm_dd
    "famotidine": "2021-06-07",
    "loratadine": "2021-06-07",
    "prednisone": "2021-10-26",
    "naltrexone": "2022-07-03",
    "paxlovid":   "2024-06-07",
    "colchicine": "2025-10-20",
}

SIG_RANK = {"strong": 3, "moderate": 2, "weak": 1, "n/a": 0, None: 0, "": 0}

EXPECTED_OUTPUTS = {
    "famotidine": {"n": 232, "pos": 179, "pos_pct": 77.155, "p": 3.565e-17},
    "loratadine": {"n":  90, "pos":  73, "pos_pct": 81.111, "p": 1.948e-9},
    "prednisone": {"n": 343, "pos": 167, "pos_pct": 48.688, "p": 0.6658},
    "naltrexone": {"n": 154, "pos": 101, "pos_pct": 65.584, "p": 1.358e-4},
    "paxlovid":   {"n": 196, "pos": 106, "pos_pct": 54.082, "p": 0.2839},
    "colchicine": {"n":  91, "pos":  49, "pos_pct": 53.846, "p": 0.5296},
}


# ── Helpers ────────────────────────────────────────────────────────────────

class CheckResult:
    def __init__(self, name: str, passed: bool, summary: str,
                 details: list[str] | None = None, informational: bool = False):
        self.name = name
        self.passed = passed
        self.summary = summary
        self.details = details or []
        # Informational checks never fail the overall run; they just report.
        self.informational = informational


def epoch_midnight(date_str: str) -> int:
    return int(datetime.strptime(date_str, "%Y-%m-%d").replace(
        tzinfo=timezone.utc).timestamp())


def _fetch_drug_reports(conn, drug, cutoff_ts):
    return conn.execute(
        """
        SELECT tr.user_id, tr.sentiment, tr.signal_strength, p.post_date, tr.post_id
        FROM treatment_reports tr
        JOIN treatment t ON tr.drug_id = t.id
        JOIN posts p ON tr.post_id = p.post_id
        WHERE lower(t.canonical_name) = ?
          AND p.post_date IS NOT NULL
          AND p.post_date < ?
          AND p.user_id != 'deleted'
        """,
        (drug, cutoff_ts),
    ).fetchall()


def _detect_cycles(parent_map: dict[str, str | None]) -> list[list[str]]:
    """Return a list of cycle examples in the parent edge graph (empty = clean)."""
    UNVISITED, VISITING, DONE = 0, 1, 2
    color: dict[str, int] = {}
    cycles: list[list[str]] = []
    for start in parent_map:
        if color.get(start, UNVISITED) != UNVISITED:
            continue
        stack = [start]
        path: list[str] = []
        while stack:
            node = stack[-1]
            c = color.get(node, UNVISITED)
            if c == UNVISITED:
                color[node] = VISITING
                path.append(node)
                parent = parent_map.get(node)
                if parent and parent in parent_map:
                    pcol = color.get(parent, UNVISITED)
                    if pcol == VISITING:
                        i = path.index(parent)
                        cycles.append(path[i:] + [parent])
                        color[node] = DONE
                        if path and path[-1] == node:
                            path.pop()
                        stack.pop()
                        continue
                    if pcol == UNVISITED:
                        stack.append(parent)
                        continue
                color[node] = DONE
                if path and path[-1] == node:
                    path.pop()
                stack.pop()
            else:
                if path and path[-1] == node:
                    path.pop()
                stack.pop()
                color[node] = DONE
    return cycles


# ── Checks ─────────────────────────────────────────────────────────────────

def check_db_integrity(conn) -> CheckResult:
    n_mismatch = conn.execute(
        "SELECT COUNT(*) FROM treatment_reports tr "
        "JOIN posts p ON tr.post_id = p.post_id "
        "WHERE tr.user_id != p.user_id"
    ).fetchone()[0]
    return CheckResult(
        name="DB integrity",
        passed=(n_mismatch == 0),
        summary=f"treatment_reports.user_id mismatches: {n_mismatch} (must be 0)",
    )


def check_db_sha256(db_path: Path) -> CheckResult:
    h = hashlib.sha256()
    with open(db_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    actual = h.hexdigest()
    matches = actual == EXPECTED_DB_SHA256
    details = [] if matches else [
        f"actual:   {actual}",
        f"expected: {EXPECTED_DB_SHA256}",
    ]
    return CheckResult(
        name="DB SHA-256",
        passed=matches,
        summary=f"actual {actual[:16]}…  expected {EXPECTED_DB_SHA256[:16]}…",
        details=details,
    )


def check_window_per_drug(conn) -> CheckResult:
    violations: list[str] = []
    summary_bits: list[str] = []
    for drug, pub_date in DRUG_CUTOFFS.items():
        win_end = min(pub_date, END_2022_EXCLUSIVE)
        cutoff_ts = epoch_midnight(win_end)
        mn, mx, n = conn.execute("""
            SELECT MIN(p.post_date), MAX(p.post_date), COUNT(*)
            FROM treatment_reports tr
            JOIN treatment t ON tr.drug_id = t.id
            JOIN posts p ON tr.post_id = p.post_id
            WHERE lower(t.canonical_name) = ?
              AND p.post_date IS NOT NULL
              AND p.post_date < ?
              AND p.user_id != 'deleted'
        """, (drug, cutoff_ts)).fetchone()
        n_null = conn.execute("""
            SELECT SUM(CASE WHEN p.post_date IS NULL THEN 1 ELSE 0 END)
            FROM treatment_reports tr
            JOIN treatment t ON tr.drug_id = t.id
            JOIN posts p ON tr.post_id = p.post_id
            WHERE lower(t.canonical_name) = ? AND p.user_id != 'deleted'
        """, (drug,)).fetchone()[0] or 0
        if mx is not None and mx >= cutoff_ts:
            mx_iso = datetime.fromtimestamp(mx, tz=timezone.utc).isoformat()
            violations.append(
                f"{drug}: MAX(post_date) = {mx_iso} >= window_end ({win_end} 00:00 UTC)"
            )
        if n_null:
            violations.append(f"{drug}: {n_null} NULL post_dates entered the per-drug query")
        summary_bits.append(f"{drug}={n}")
    return CheckResult(
        name="Per-drug window",
        passed=(not violations),
        summary=("6/6 drugs in-window, 0 NULL post_dates"
                 if not violations else f"{len(violations)} violation(s)"),
        details=violations,
    )


def check_thread_reconstruction(conn) -> CheckResult:
    n_total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    n_orphans = conn.execute("""
        SELECT COUNT(*) FROM posts p
        WHERE p.parent_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM posts q WHERE q.post_id = p.parent_id)
    """).fetchone()[0]
    parent_map = dict(conn.execute("SELECT post_id, parent_id FROM posts"))
    cycles = _detect_cycles(parent_map)
    n_subs = sum(1 for v in parent_map.values() if v is None)
    n_comments = n_total - n_subs
    passed = n_orphans == 0 and not cycles
    details: list[str] = []
    if n_orphans:
        details.append(f"{n_orphans} comments have parent_id with no matching post_id")
    if cycles:
        first = " -> ".join(cycles[0][:6]) + ("…" if len(cycles[0]) > 6 else "")
        details.append(f"{len(cycles)} cycle(s) detected; first: {first}")
    return CheckResult(
        name="Thread reconstruction",
        passed=passed,
        summary=(f"{n_total:,} posts ({n_subs:,} submissions, {n_comments:,} comments), "
                 f"{n_orphans} orphans, {len(cycles)} cycles"),
        details=details,
    )


def check_dedup_audit(conn) -> CheckResult:
    """Informational — reports per-drug raw / unique / multi / mixed / flip
    counts. Never fails (no assertion); reviewer reads the numbers."""
    bits: list[str] = []
    for drug, pub_date in DRUG_CUTOFFS.items():
        win_end = min(pub_date, END_2022_EXCLUSIVE)
        cutoff_ts = epoch_midnight(win_end)
        rows = _fetch_drug_reports(conn, drug, cutoff_ts)
        by_user: dict[str, list[dict]] = collections.defaultdict(list)
        for uid, sent, sig, date, _pid in rows:
            by_user[uid].append({"sent": sent, "sig": sig, "date": date or 0})
        n_users = len(by_user)
        multi = {u: rs for u, rs in by_user.items() if len(rs) > 1}
        n_multi = len(multi)
        n_mixed = sum(
            1 for rs in multi.values()
            if any(r["sent"] == "positive" for r in rs)
            and any(r["sent"] != "positive" for r in rs)
        )
        flip_majority = 0
        flip_any_pos = 0
        for rs in by_user.values():
            rs_sorted = sorted(
                rs, key=lambda r: (r["date"], SIG_RANK.get(r["sig"], 0)), reverse=True,
            )
            chosen_pos = rs_sorted[0]["sent"] == "positive"
            if len(rs) > 1:
                n_pos = sum(1 for r in rs if r["sent"] == "positive")
                if (n_pos > len(rs) / 2) != chosen_pos:
                    flip_majority += 1
                if (n_pos > 0) != chosen_pos:
                    flip_any_pos += 1
        bits.append(
            f"{drug}: raw={len(rows)} users={n_users} multi={n_multi} "
            f"mixed={n_mixed} flip(maj)={flip_majority} flip(any+)={flip_any_pos}"
        )
    return CheckResult(
        name="Dedup audit (informational)",
        passed=True,
        summary="see per-drug breakdown below",
        details=bits,
        informational=True,
    )


def check_expected_outputs(conn) -> CheckResult:
    """V10: re-derive the same per-drug stats the build does, compare to
    EXPECTED_OUTPUTS. Same logic as the build's V10 cell, but standalone."""
    from scipy.stats import binomtest
    from statsmodels.stats.proportion import proportion_confint as wilson  # noqa: F401

    violations: list[str] = []
    matched: list[str] = []
    for drug, pub_date in DRUG_CUTOFFS.items():
        win_end = min(pub_date, END_2022_EXCLUSIVE)
        cutoff_ts = epoch_midnight(win_end)
        rows = _fetch_drug_reports(conn, drug, cutoff_ts)
        # Apply per-(user, drug) "most recent + signal-strength tiebreaker" dedup
        by_user: dict[str, dict] = {}
        for uid, sent, sig, date, _pid in rows:
            d = date or 0
            sig_r = SIG_RANK.get(sig, 0)
            cur = by_user.get(uid)
            if cur is None or (d, sig_r) > (cur["date"], cur["sig_r"]):
                by_user[uid] = {"sent": sent, "date": d, "sig_r": sig_r}
        sentiments = [v["sent"] for v in by_user.values()]
        n = len(sentiments)
        pos = sum(1 for s in sentiments if s == "positive")
        pos_pct = (pos / n * 100) if n else 0
        pval = binomtest(pos, n, 0.5, alternative="two-sided").pvalue if n else 1.0

        exp = EXPECTED_OUTPUTS.get(drug)
        if exp is None:
            violations.append(f"{drug}: no entry in EXPECTED_OUTPUTS")
            continue
        if n != exp["n"]:
            violations.append(f"{drug}: n {n} != expected {exp['n']}")
        if pos != exp["pos"]:
            violations.append(f"{drug}: pos {pos} != expected {exp['pos']}")
        if abs(pos_pct - exp["pos_pct"]) > 0.05:
            violations.append(
                f"{drug}: pos_pct {pos_pct:.3f} differs from expected {exp['pos_pct']:.3f} > 0.05pp"
            )
        if exp["p"] < 1e-4:
            if not (pval < 10 * exp["p"]):
                violations.append(
                    f"{drug}: p {pval:.3g} far from expected tiny {exp['p']:.3g}"
                )
        else:
            rel = abs(pval - exp["p"]) / exp["p"]
            if rel > 1e-3:
                violations.append(
                    f"{drug}: p {pval:.4f} differs from expected {exp['p']:.4f} (rel {rel:.4f})"
                )
        matched.append(f"{drug}: n={n} pos={pos} pos_pct={pos_pct:.3f} p={pval:.4g}")
    return CheckResult(
        name="Expected-output assertion",
        passed=(not violations),
        summary=(f"{len(matched)}/{len(EXPECTED_OUTPUTS)} drugs match the frozen expected table"
                 if not violations else f"{len(violations)} drift violation(s)"),
        details=violations if violations else matched,
    )


# ── Main ───────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    script_dir = Path(__file__).resolve().parent

    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--db", type=Path, default=None,
        help=("Analysis DB path. If omitted, paths.py resolves it: "
              "RCT_DB_PATH env var → anchor walk-up to package root."),
    )
    args = ap.parse_args(argv)

    # Track how the DB path was determined so we can surface it to the
    # reviewer. A stale RCT_DB_PATH from a previous shell session is a real
    # source of confusion; printing the resolution mode makes it obvious.
    if args.db is not None:
        if not args.db.exists():
            print(f"ERROR: DB not found at {args.db}", file=sys.stderr)
            print("       Download from S3 (URL in README) and rerun.", file=sys.stderr)
            return 2
        db_resolved = args.db.resolve()
        resolution_mode = "--db CLI flag"
    elif os.environ.get("RCT_DB_PATH"):
        try:
            db_resolved = resolve_db_path(start=script_dir)
        except PathResolutionError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        resolution_mode = f"RCT_DB_PATH={os.environ['RCT_DB_PATH']!r}"
    else:
        try:
            db_resolved = resolve_db_path(start=script_dir)
        except PathResolutionError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        resolution_mode = "package anchor (default)"

    conn = sqlite3.connect(str(db_resolved))
    try:
        results = [
            check_db_integrity(conn),
            check_db_sha256(db_resolved),
            check_window_per_drug(conn),
            check_thread_reconstruction(conn),
            check_dedup_audit(conn),
            check_expected_outputs(conn),
        ]
    finally:
        conn.close()

    # Pretty-print results
    print()
    print("=" * 68)
    print(" RCT historical validation — reproducibility verification")
    print("=" * 68)
    print(f" DB: {db_resolved}")
    print(f" DB resolution: {resolution_mode}")
    print(f" Run at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print()

    width = max(len(r.name) for r in results)
    for r in results:
        if r.informational:
            tag = "[INFO]"
        elif r.passed:
            tag = "[PASS]"
        else:
            tag = "[FAIL]"
        print(f"  {tag}  {r.name.ljust(width)}    {r.summary}")
        for d in r.details:
            print(f"           {' ' * width}    - {d}")
    print()

    blocking_failed = [r for r in results if not r.passed and not r.informational]
    n_passed = sum(1 for r in results if r.passed and not r.informational)
    n_total = sum(1 for r in results if not r.informational)

    print("=" * 68)
    if blocking_failed:
        print(f" {len(blocking_failed)} of {n_total} CHECK(S) FAILED.")
        for r in blocking_failed:
            print(f"   - {r.name}: {r.summary}")
        print("=" * 68)
        return 1
    print(f" ALL {n_passed} CHECKS PASSED.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
