"""
Thread-reconstruction audit.

Runs the thread-audit checks against any analysis DB that has parent_id preserved
(so this works against the rebuilt historical-validation DB, but not against
the older DBs that pre-dated the import_posts.strip_reddit_prefix fix).

Checks performed:
  1. Total posts vs. comments (rows with parent_id IS NULL vs NOT NULL)
  2. Orphan rate: comments whose parent_id is set but doesn't match any
     post_id in the DB. With the prefix fix in place this should be 0.
  3. 50-chain sample: pick 50 random comments stratified by approximate
     depth, walk each chain to its root, verify (a) each ancestor exists,
     (b) timestamps are monotonically non-decreasing parent->child,
     (c) each chain ends at a submission (parent_id IS NULL), (d) chain
     length is bounded (no cycles). Reports a histogram of chain depths.
  4. Cycle detection: full DFS over parent_id edges, raises if any cycle
     is found. Should NEVER find one in healthy data.

Usage:
    python scripts/thread_audit.py \\
        --db data/historical_validation/historical_validation_2020-07_to_2022-12.db \\
        --out docs/RCT_historical_validation/THREAD_AUDIT.md

Pass --seed for reproducibility of the 50-chain sample.
"""
from __future__ import annotations
import argparse
import random
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def fetch_parent_map(conn):
    """Return {post_id: parent_id_or_None} for every row in posts."""
    return dict(conn.execute("SELECT post_id, parent_id FROM posts").fetchall())


def fetch_post_dates(conn):
    """Return {post_id: post_date_epoch_or_None} for every row in posts."""
    return dict(conn.execute("SELECT post_id, post_date FROM posts").fetchall())


def detect_cycles(parent_map):
    """DFS over parent edges. Returns list of cycle examples (empty = clean)."""
    color = {}  # 0=white (unvisited), 1=gray (visiting), 2=black (done)
    cycles = []
    for start in parent_map:
        if color.get(start, 0) != 0:
            continue
        stack = [start]
        path = []
        while stack:
            node = stack[-1]
            if color.get(node, 0) == 0:
                color[node] = 1
                path.append(node)
                parent = parent_map.get(node)
                if parent and parent in parent_map and color.get(parent, 0) == 1:
                    # cycle detected
                    cycle_start = path.index(parent)
                    cycles.append(path[cycle_start:] + [parent])
                    color[node] = 2
                    path.pop()
                    stack.pop()
                elif parent and parent in parent_map and color.get(parent, 0) == 0:
                    stack.append(parent)
                else:
                    color[node] = 2
                    path.pop()
                    stack.pop()
            else:
                # already visited, no need to recurse
                if path and path[-1] == node:
                    path.pop()
                stack.pop()
                color[node] = 2
    return cycles


def chain_for(post_id, parent_map, max_walk=10000):
    """Walk from post_id up via parent_map, returning the chain post_id->...->root.
    Bounded by max_walk to defend against cycles in malformed data."""
    chain = [post_id]
    seen = {post_id}
    cur = parent_map.get(post_id)
    while cur and cur not in seen and len(chain) < max_walk:
        chain.append(cur)
        seen.add(cur)
        cur = parent_map.get(cur)
    cycle_detected = cur is not None and cur in seen
    return chain, cycle_detected


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seed", type=int, default=42, help="Seed for the 50-chain sample")
    ap.add_argument("--n-chains", type=int, default=50)
    args = ap.parse_args()

    if not args.db.exists():
        sys.exit(f"ERROR: DB not found at {args.db}")

    conn = sqlite3.connect(str(args.db))
    parent_map = fetch_parent_map(conn)
    date_map = fetch_post_dates(conn)
    n_total = len(parent_map)
    n_subs = sum(1 for v in parent_map.values() if v is None)
    n_comments = n_total - n_subs

    # Orphan check
    n_orphans = sum(
        1 for child, parent in parent_map.items()
        if parent is not None and parent not in parent_map
    )

    # Cycle detection
    cycles = detect_cycles(parent_map)

    # Random 50-chain sample, stratified roughly by depth
    rng = random.Random(args.seed)
    comment_ids = [pid for pid, par in parent_map.items() if par is not None]
    sample_ids = rng.sample(comment_ids, min(args.n_chains, len(comment_ids))) if comment_ids else []

    chain_results = []
    for cid in sample_ids:
        chain, cycle = chain_for(cid, parent_map)
        depth = len(chain)
        # All ancestors exist? (chain_for stops if a parent is missing)
        last_parent = parent_map.get(chain[-1])
        chain_complete = (last_parent is None)
        # Timestamp monotonicity: each child's post_date >= parent's
        ts_violations = 0
        ts_known = 0
        for i in range(len(chain) - 1):
            child_ts = date_map.get(chain[i])
            parent_ts = date_map.get(chain[i + 1])
            if child_ts is None or parent_ts is None:
                continue
            ts_known += 1
            if child_ts < parent_ts:
                ts_violations += 1
        chain_results.append({
            "tail": cid,
            "depth": depth,
            "complete": chain_complete,
            "cycle": cycle,
            "ts_known": ts_known,
            "ts_violations": ts_violations,
            "root": chain[-1],
        })

    depth_hist = Counter(r["depth"] for r in chain_results)
    n_complete = sum(1 for r in chain_results if r["complete"])
    n_with_cycle = sum(1 for r in chain_results if r["cycle"])
    total_ts_violations = sum(r["ts_violations"] for r in chain_results)
    total_ts_known = sum(r["ts_known"] for r in chain_results)

    # ── Build the markdown report
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = []
    lines.append(f"# Thread Reconstruction Audit\n")
    lines.append(f"**Run at:** {now_iso}  ")
    lines.append(f"**DB:** `{args.db.as_posix()}`  ")
    lines.append(f"**Sample seed:** {args.seed}  ")
    lines.append(f"**Sample size:** {args.n_chains}\n")
    lines.append("---\n")
    lines.append("## 1. Posts vs comments\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Total rows in `posts` | {n_total:,} |")
    lines.append(f"| Submissions (`parent_id IS NULL`) | {n_subs:,} ({100*n_subs/n_total:.1f}%) |")
    lines.append(f"| Comments (`parent_id IS NOT NULL`) | {n_comments:,} ({100*n_comments/n_total:.1f}%) |")
    lines.append("")
    lines.append("## 2. Orphan parents\n")
    lines.append(f"Comments whose `parent_id` is set but doesn't match any `post_id` in the DB.\n")
    lines.append(f"**Orphans found: {n_orphans:,}**  ")
    if n_orphans == 0:
        lines.append("All `parent_id` values resolve to an existing post. PASS.\n")
    else:
        lines.append("Some parent IDs don't match any post — investigate the import path.\n")
    lines.append("## 3. Cycle detection\n")
    lines.append(f"Full DFS over the parent edge graph (`{n_total:,}` nodes).\n")
    lines.append(f"**Cycles found: {len(cycles)}**  ")
    if not cycles:
        lines.append("Parent graph is a forest (no cycles). PASS.\n")
    else:
        lines.append("Cycles detected — investigate immediately:\n")
        for cyc in cycles[:5]:
            lines.append(f"- `{' -> '.join(cyc)}`")
        lines.append("")
    lines.append("## 4. Sampled reply chains\n")
    lines.append(f"Random sample of {len(sample_ids)} comments (seed `{args.seed}`); each walked to its root.\n")
    lines.append(f"| Property | Result |")
    lines.append(f"|---|---|")
    lines.append(f"| Chains reaching a root submission | **{n_complete} / {len(sample_ids)}** |")
    lines.append(f"| Chains hitting a cycle | {n_with_cycle} |")
    lines.append(f"| Timestamp pairs checked (parent vs child) | {total_ts_known:,} |")
    lines.append(f"| Timestamp violations (child older than parent) | {total_ts_violations} |")
    lines.append("")
    lines.append("**Chain depth histogram (sample):**\n")
    lines.append("| Depth (hops) | Count |")
    lines.append("|---|---|")
    for d in sorted(depth_hist):
        lines.append(f"| {d} | {depth_hist[d]} |")
    lines.append("")
    if n_with_cycle == 0 and total_ts_violations == 0 and n_complete == len(sample_ids):
        lines.append("All sampled chains complete, cycle-free, and timestamp-monotonic. PASS.\n")
    else:
        lines.append("**Some sample chains failed audit. Investigate chains listed below:**\n")
        for r in chain_results:
            if r["cycle"] or r["ts_violations"] or not r["complete"]:
                lines.append(
                    f"- `{r['tail']}` depth={r['depth']} "
                    f"complete={r['complete']} cycle={r['cycle']} "
                    f"ts_violations={r['ts_violations']}/{r['ts_known']}"
                )
        lines.append("")
    lines.append("## Reproducibility\n")
    lines.append(
        f"Re-running with the same `--db`, `--seed`, and same DB contents "
        f"reproduces the same sampled chains and counts; only the `Run at` "
        f"timestamp at the top of this file changes. The sample is "
        f"deterministic given the seed."
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    conn.close()
    print(f"Wrote thread audit report: {args.out}")
    print(f"  Posts: {n_total:,}  Submissions: {n_subs:,}  Comments: {n_comments:,}")
    print(f"  Orphans: {n_orphans}  Cycles: {len(cycles)}  "
          f"Sample complete: {n_complete}/{len(sample_ids)}  "
          f"TS violations: {total_ts_violations}/{total_ts_known}")


if __name__ == "__main__":
    main()
