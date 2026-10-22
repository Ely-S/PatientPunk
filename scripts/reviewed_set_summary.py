"""Author-level tables from a Codex-reviewed package database (the review layer's own schema).

    python scripts/reviewed_set_summary.py REVIEWED.db [--drug-label "7,8-DHF"]

A reviewed package keys its rows on (community, report_id): report ids repeat across
communities, so joining on report_id alone multiplies effect and dose rows. Eligible report
= include_in_analysis, sentiment_eligible, author_eligible all 1 and a directional sentiment.
Adverse effect = include_as_adverse 1. Dose = a review-confirmed row with an amount.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import sqlite3
import sys
from pathlib import Path

DIRECTIONAL = ("positive", "negative", "mixed")


def _when(value) -> float:
    """post_date is a unix stamp in some packages and an ISO string in others."""
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return datetime.datetime.fromisoformat(str(value).replace("Z", "")).timestamp()
        except ValueError:
            return 0.0


def load(db: Path) -> dict:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    reports = {
        (community, report_id): (author, sentiment, _when(post_date))
        for community, report_id, author, sentiment, post_date in conn.execute(
            "SELECT community, report_id, author, sentiment, post_date FROM reviewed_reports "
            "WHERE include_in_analysis=1 AND sentiment_eligible=1 AND author_eligible=1 "
            f"AND sentiment IN {DIRECTIONAL}")
    }
    authors: dict[str, dict] = {}
    for author, sentiment, when in reports.values():
        a = authors.setdefault(author, {"sentiments": [], "adverse": [], "severities": [], "doses": [], "routes": 0})
        a["sentiments"].append((when, sentiment))
    for community, report_id, symptom, severity, category in conn.execute(
            "SELECT community, report_id, symptom, severity, category FROM reviewed_effects WHERE include_as_adverse=1"):
        row = reports.get((community, report_id))
        if row is None:
            continue
        a = authors[row[0]]
        a["adverse"].append((category or "uncategorised", symptom))
        if severity:
            a["severities"].append(severity.lower())
    for community, report_id, low, unit, band, route in conn.execute(
            "SELECT community, report_id, low, unit, band, route FROM reviewed_doses "
            "WHERE review_status LIKE '%confirmed%'"):
        row = reports.get((community, report_id))
        if row is None:
            continue
        a = authors[row[0]]
        if low is not None and (unit or "").lower() in ("mg", "mgs", "milligrams"):
            a["doses"].append((low, band, route))
        if route:
            a["routes"] += 1
    return {"reports": reports, "authors": authors}


def report(data: dict, label: str) -> str:
    authors = data["authors"]
    n = len(authors)
    latest = {a: max(v["sentiments"])[1] for a, v in authors.items()}
    adverse = {a for a, v in authors.items() if v["adverse"]}
    severe = {a for a, v in authors.items() if any(s in ("severe", "life_threatening") for s in v["severities"])}
    out = [f"# {label}: reviewed set, author level", "",
           f"| | {label} ({n}) |", "|---|---:|",
           f"| Eligible reports | {len(data['reports'])} |",
           f"| Positive on latest report | {sum(1 for s in latest.values() if s == 'positive')} |",
           f"| Any side effect | {len(adverse)} |",
           f"| Called a side effect severe | {len(severe)} |",
           f"| Stated any severity | {sum(1 for v in authors.values() if v['severities'])} |",
           f"| Authors with a stated amount | {sum(1 for v in authors.values() if v['doses'])} |",
           f"| Authors stating a route | {sum(1 for v in authors.values() if v['routes'])} |", ""]
    by_category = collections.Counter()
    for a in adverse:
        for category, _symptom in {(c, s) for c, s in authors[a]["adverse"]}:
            by_category[category] += 0
        for category in {c for c, _ in authors[a]["adverse"]}:
            by_category[category] += 1
    out += ["## Side-effect categories (authors)", "", "| Category | Authors |", "|---|---:|"]
    out += [f"| {c} | {k} |" for c, k in by_category.most_common()]
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("database", type=Path)
    ap.add_argument("--drug-label", default="target compound")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if not args.database.exists():
        sys.exit(f"{args.database}: not found")
    text = report(load(args.database), args.drug_label)
    args.out.write_text(text, encoding="utf-8") if args.out else print(text)


if __name__ == "__main__":
    main()
