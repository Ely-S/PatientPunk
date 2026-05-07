"""
Dedup-sample audit.

Samples multi-report (user, drug) pairs from the analysis DB and renders
each candidate report alongside the one the dedup rule retained, so a
reviewer can spot-check whether the rule picked sensibly.

Dedup rule under audit: "most recent post wins (by full UTC timestamp);
signal_strength breaks ties on the same UTC timestamp (strong > moderate
> weak > n/a). Exact-timestamp ties are rare in practice, so signal
strength acts as a near-vestigial tiebreaker — most decisions reduce
to 'most recent post wins'."

Output: a markdown file with one section per drug, showing N sampled
multi-report users and their full report list with the retained row
clearly marked. The pool is restricted to the same in-window /
non-deleted-user filter the analysis uses.

Usage:
    python scripts/dedup_sample_audit.py \\
        --db docs/RCT_historical_validation/data/historical_validation_2020-07_to_2022-12.db \\
        --out docs/RCT_historical_validation/DEDUP_AUDIT.md
"""
from __future__ import annotations
import argparse
import collections
import random
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DRUG_CUTOFFS = {
    'famotidine':  ('2021-06-07', 'Glynne et al. 2021'),
    'loratadine':  ('2021-06-07', 'Glynne et al. 2021'),
    'prednisone':  ('2021-10-26', 'Utrero-Rico et al. 2021'),
    'naltrexone':  ('2022-07-03', "O'Kelly et al. 2022"),
    'paxlovid':    ('2024-06-07', 'Geng et al. 2024 (STOP-PASC)'),
    'colchicine':  ('2025-10-20', 'Bassi et al. 2025'),
}
END_2022_EXCLUSIVE = '2023-01-01'
SIG_RANK = {"strong": 3, "moderate": 2, "weak": 1, "n/a": 0, None: 0, "": 0}


def epoch_midnight(date_str):
    return int(datetime.strptime(date_str, '%Y-%m-%d').replace(
        tzinfo=timezone.utc).timestamp())


def fetch_drug_reports(conn, drug, cutoff_ts):
    return conn.execute(
        '''
        SELECT tr.user_id, tr.sentiment, tr.signal_strength, p.post_date, tr.post_id
        FROM treatment_reports tr
        JOIN treatment t ON tr.drug_id = t.id
        JOIN posts p ON tr.post_id = p.post_id
        WHERE lower(t.canonical_name) = ?
          AND p.post_date IS NOT NULL
          AND p.post_date < ?
          AND p.user_id != 'deleted'
        ''',
        (drug, cutoff_ts),
    ).fetchall()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--per-drug", type=int, default=5,
                    help="Sample size per drug; total sampled pairs = per-drug * 6.")
    args = ap.parse_args()

    if not args.db.exists():
        sys.exit(f"ERROR: DB not found at {args.db}")

    conn = sqlite3.connect(str(args.db))
    rng = random.Random(args.seed)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Render the DB path with forward slashes so the audit file reads the same
    # on every platform (the script may run on Windows but reviewers may read
    # the file on Linux / macOS).
    db_display = args.db.as_posix()

    lines = []
    lines.append("# Deduplication Sample Audit")
    lines.append("")
    lines.append(f"**Generated:** {now_iso}")
    lines.append(f"**DB:** `{db_display}`")
    lines.append(f"**Sample seed:** {args.seed}  ")
    lines.append(f"**Per-drug sample size:** {args.per_drug}  ")
    lines.append("")
    lines.append("This file samples multi-report (user, drug) pairs from the")
    lines.append("analysis DB and shows each user's full set of reports for that")
    lines.append("drug, with the report retained by the dedup rule clearly marked")
    lines.append("(`** RETAINED **` row). The audit is for reviewers to spot-check")
    lines.append("that the rule \"most recent post wins (by full UTC timestamp);")
    lines.append("signal_strength breaks ties on the same UTC timestamp\" picked")
    lines.append("sensibly — i.e., that we're not systematically picking against")
    lines.append("the user's settled view. Exact-timestamp ties are rare, so the")
    lines.append("signal-strength tiebreaker fires only occasionally; most picks")
    lines.append("are simply the most-recent post.")
    lines.append("")
    lines.append("If you find a case where the retained row looks like a poor")
    lines.append("representation of the user's overall opinion, that's a")
    lines.append("methodology finding worth raising in review.")
    lines.append("")
    lines.append("---")
    lines.append("")

    total_sampled = 0
    for drug, (pub_date, paper) in DRUG_CUTOFFS.items():
        win_end = min(pub_date, END_2022_EXCLUSIVE)
        cutoff_ts = epoch_midnight(win_end)
        rows = fetch_drug_reports(conn, drug, cutoff_ts)

        # Group by user
        by_user = collections.defaultdict(list)
        for uid, sent, sig, date, pid in rows:
            by_user[uid].append({
                "sent": sent, "sig": sig or "n/a", "date": date or 0, "pid": pid,
            })

        multi = {u: rs for u, rs in by_user.items() if len(rs) > 1}
        mixed = {
            u: rs for u, rs in multi.items()
            if any(r["sent"] == "positive" for r in rs)
            and any(r["sent"] != "positive" for r in rs)
        }

        # Sample preferring mixed-signal users (where dedup choice matters most)
        target = min(args.per_drug, len(multi))
        n_mixed_sample = min(len(mixed), max(1, target * 2 // 3))
        n_other_sample = target - n_mixed_sample
        mixed_pool = sorted(mixed.keys())
        other_pool = sorted(set(multi) - set(mixed))
        sampled = []
        if mixed_pool:
            sampled.extend(rng.sample(mixed_pool, min(n_mixed_sample, len(mixed_pool))))
        if other_pool:
            sampled.extend(rng.sample(other_pool, min(n_other_sample, len(other_pool))))
        # Pad with random multi-users if we still under target
        if len(sampled) < target:
            remaining = sorted(set(multi) - set(sampled))
            if remaining:
                sampled.extend(rng.sample(remaining, min(target - len(sampled), len(remaining))))

        lines.append(f"## {drug} ({paper})")
        lines.append("")
        lines.append(f"Multi-report users in this drug's window: **{len(multi):,}** "
                     f"(of which **{len(mixed):,}** are mixed-signal — pos+nonpos).")
        lines.append(f"Showing {len(sampled)} sampled users below.")
        lines.append("")

        for uid in sampled:
            rs = by_user[uid]
            rs_sorted = sorted(
                rs,
                key=lambda r: (r["date"], SIG_RANK.get(r["sig"], 0)),
                reverse=True,
            )
            retained_pid = rs_sorted[0]["pid"]
            uid_short = uid[:16] + "…" if len(uid) > 16 else uid
            lines.append(f"### user `{uid_short}` ({len(rs)} reports)")
            lines.append("")
            lines.append("| | post_date (UTC) | sentiment | signal | post_id |")
            lines.append("|---|---|---|---|---|")
            for r in rs_sorted:
                marker = "**RETAINED**" if r["pid"] == retained_pid else ""
                d_iso = (datetime.fromtimestamp(r["date"], tz=timezone.utc)
                         .strftime("%Y-%m-%d %H:%M") if r["date"] else "—")
                lines.append(
                    f"| {marker} | {d_iso} | {r['sent']} | {r['sig']} "
                    f"| `{r['pid']}` |"
                )
            lines.append("")
        lines.append("---")
        lines.append("")
        total_sampled += len(sampled)

    lines.append("## Reproducibility")
    lines.append("")
    lines.append(
        f"Re-running `scripts/dedup_sample_audit.py --db <db> --out <out> "
        f"--seed {args.seed} --per-drug {args.per_drug}` against the same DB "
        f"reproduces the same sampled rows, aside from the `Generated` "
        f"timestamp at the top of this file. Total sampled (user, drug) "
        f"pairs: **{total_sampled}**."
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    conn.close()
    print(f"Wrote {args.out}")
    print(f"  total sampled pairs: {total_sampled}")


if __name__ == "__main__":
    main()
