#!/usr/bin/env python3
"""Free (no-LLM) real-world USE counts for the FDA comment, per target drug.

Counts off-label *discussion* (not efficacy): how many posts mention each drug,
how many unique participants, over what time span, self-reported dosing patterns,
and barrier mentions (sourcing/compounding, cost/insurance, prescriber reluctance).

These map to the doc's Section 6 ("characterize USE & UNMET NEED") and Section 7
(barriers). Run after import_posts.py. No API key required.

    .venv/bin/python scripts/free_use_counts.py --db data/phoenixrising.db
"""
from __future__ import annotations

import argparse
import re
import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path

DRUGS = {
    "low-dose naltrexone (LDN)": ["naltrexone", "low dose naltrexone", "low-dose naltrexone",
                                   "ldn", "ultra-low-dose naltrexone", "uldn", "low-dose ntx",
                                   "ntx", "compounded naltrexone"],
    "pyridostigmine / Mestinon": ["pyridostigmine", "mestinon", "pyridostigmine bromide",
                                   "mestinon timespan", "regonol", "generic pyridostigmine",
                                   "pyridostigmine er", "pyridostigmine cr"],
}

# Barrier term groups (case-insensitive). Each maps to a regex.
BARRIERS = {
    "sourcing / compounding": re.compile(
        r"\b(compound\w*|compounding pharmacy|without (?:a )?prescription|no prescription|"
        r"where (?:can|do|to) (?:i|you|we) (?:get|buy|order|source)|order(?:ing)? online|"
        r"reputable pharmacy|liquid (?:form|version)|make your own|diy)\b", re.I),
    "cost / insurance": re.compile(
        r"\b(afford\w*|expensive|cheap\w*|cost\w*|price\w*|insurance|covered|coverage|"
        r"out of pocket|reimburs\w*|\$\s?\d+)\b", re.I),
    "prescriber reluctance / access": re.compile(
        r"\b(off[- ]label|won'?t prescribe|refuse[ds]? to prescribe|reluctant|"
        r"convince (?:my|the|a) (?:doctor|gp|dr)|find a (?:doctor|gp|dr|prescriber)|"
        r"my (?:doctor|gp|dr) (?:won'?t|wouldn'?t|refused|didn'?t want)|prescriber|"
        r"none of my doctors|no doctor)\b", re.I),
}

DOSE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*mg\b", re.I)


def alias_regex(aliases: list[str]) -> re.Pattern:
    return re.compile(r"\b(?:" + "|".join(re.escape(a) for a in aliases) + r")\b", re.I)


def reconstruct_text(title, body, parent_id) -> str:
    if parent_id is None:
        return f"{title or ''} {body or ''}".strip()
    return body or ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    rows = conn.execute(
        "SELECT post_id, title, parent_id, user_id, body_text, post_date FROM posts"
    ).fetchall()

    # Pre-reconstruct text per row.
    recs = [(pid, reconstruct_text(t, b, par), uid, pdate)
            for (pid, t, par, uid, b, pdate) in rows]

    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    n_toplevel = sum(1 for r in rows if r[2] is None)  # top-level posts (~thread count)
    print(f"Corpus: {len(recs)} posts/comments, {total_users} unique participants, "
          f"{n_toplevel} top-level posts (Phoenix Rising ME/CFS forum).\n")

    for label, aliases in DRUGS.items():
        rx = alias_regex(aliases)
        hits = [(pid, txt, uid, pdate) for (pid, txt, uid, pdate) in recs if rx.search(txt)]
        users = {uid for _, _, uid, _ in hits if uid}
        dates = [d for _, _, _, d in hits if d]
        print("=" * 64)
        print(f"{label}")
        print("=" * 64)
        print(f"  Posts directly mentioning it : {len(hits)}")
        print(f"  Unique participants          : {len(users)}")
        if dates:
            print(f"  Discussion span              : {date.fromtimestamp(min(dates))} "
                  f"-> {date.fromtimestamp(max(dates))}")

        # Self-reported dosing
        doses = Counter()
        for _, txt, _, _ in hits:
            for m in DOSE_RE.findall(txt):
                try:
                    doses[float(m)] += 1
                except ValueError:
                    pass
        if doses:
            ldn_window = sum(c for d, c in doses.items() if 0 < d <= 4.5)
            total_dose_mentions = sum(doses.values())
            print(f"  Posts with an explicit mg dose: "
                  f"{sum(1 for _,t,_,_ in hits if DOSE_RE.search(t))}  "
                  f"({total_dose_mentions} dose figures)")
            top = ", ".join(f"{d:g}mg×{c}" for d, c in sorted(doses.items(), key=lambda kv: -kv[1])[:8])
            print(f"  Most-cited doses             : {top}")
            if "naltrexone" in aliases:
                print(f"  Dose figures in LDN window (≤4.5mg): {ldn_window}/{total_dose_mentions} "
                      f"({100*ldn_window/total_dose_mentions:.0f}%)")

        # Barriers (within posts that directly mention this drug)
        print(f"  Barrier mentions (among those {len(hits)} posts):")
        for bname, brx in BARRIERS.items():
            n = sum(1 for _, txt, _, _ in hits if brx.search(txt))
            print(f"     - {bname:<34}: {n} posts")
        print()

    conn.close()


if __name__ == "__main__":
    main()
