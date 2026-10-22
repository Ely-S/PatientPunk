"""Author-by-dose tables for one drug in a pipeline database: dose bands, route, titration.

    python scripts/dose_bands.py --db data/posts.db --drug "4'-dma-7,8-dhf" \
        --bands 10,25,50 --capsule-mg 10

The unit is an author at a dose band: each author counts once per band they state, however
many reports they wrote at it. The outcome is the author's latest report stating that band.
An entry has a side effect if any of that author's reports at that band carries an adverse
sentence attributed to the drug. --capsule-mg converts capsule and pill counts to milligrams,
which is what authors do themselves when a product has one strength.

Route rows use only doses where the author states an amount and a route on the same row; the
median amount is context, not a dose-response, because a band is a daily total while a route
describes one administration.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import sqlite3
import statistics
import sys
from pathlib import Path

DIRECTIONAL = ("positive", "negative", "mixed")
CAPSULES = ("capsule", "capsules", "cap", "caps", "pill", "pills")


def _when(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return datetime.datetime.fromisoformat(str(value).replace("Z", "")).timestamp()
        except ValueError:
            return 0.0


def _bands(cuts: list[float]) -> list[tuple[float, float, str]]:
    edges = [0.0, *cuts, float("inf")]
    out = []
    for low, high in zip(edges, edges[1:]):
        if high == float("inf"):
            out.append((low, high, f"{low:g} mg and up"))
        elif low == 0:
            out.append((low, high, f"under {high:g} mg"))
        else:
            out.append((low, high, f"{low:g} to under {high:g} mg"))
    return out


def load(db: Path, drug: str, cuts: list[float], capsule_mg: float | None, cap_mg: float) -> dict:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    row = conn.execute("SELECT id FROM treatment WHERE lower(canonical_name)=lower(?)", (drug,)).fetchone()
    if row is None:
        sys.exit(f"{db}: no treatment named {drug!r}")
    drug_id = row[0]
    reports = {
        report_id: (user_id, sentiment, _when(post_date))
        for report_id, user_id, sentiment, post_date in conn.execute(
            "SELECT r.report_id, r.user_id, r.sentiment, p.post_date FROM treatment_reports r "
            f"JOIN posts p ON p.post_id=r.post_id WHERE r.drug_id=? AND r.sentiment IN {DIRECTIONAL}", (drug_id,))
    }
    adverse = collections.Counter()
    for report_id, in conn.execute(
            "SELECT report_id FROM report_effects_latest WHERE direction='worsened' AND attribution='target'"):
        if report_id in reports:
            adverse[report_id] += 1
    bands = _bands(cuts)
    def band_of(mg: float) -> str:
        return next(name for low, high, name in bands if low <= mg < high)
    doses = []
    for report_id, low, unit, route, quote in conn.execute(
            "SELECT report_id, low, unit, route, quote FROM report_doses_latest WHERE low IS NOT NULL"):
        if report_id not in reports:
            continue
        kind = (unit or "").lower()
        if kind == "g":
            mg = low * 1000
        elif kind in ("mg", "mgs", "milligrams"):
            mg = low
        elif capsule_mg and kind in CAPSULES:
            mg = low * capsule_mg
        else:
            continue
        if mg > cap_mg:
            continue
        doses.append({"report": report_id, "author": reports[report_id][0], "mg": mg, "route": route,
                      "band": band_of(mg), "quote": quote, "from_capsules": kind in CAPSULES})
    return {"reports": reports, "adverse": adverse, "doses": doses, "bands": [b[2] for b in bands]}


def band_table(data: dict) -> list[str]:
    by_report = collections.defaultdict(set)
    for d in data["doses"]:
        by_report[d["report"]].add(d["band"])
    entries: dict[tuple[str, str], list] = collections.defaultdict(list)
    for report_id, bands in by_report.items():
        author, sentiment, when = data["reports"][report_id]
        for band in bands:
            entries[(author, band)].append((when, report_id, sentiment, data["adverse"].get(report_id, 0)))
    stats = collections.defaultdict(lambda: [0, 0, 0])
    for (_author, band), reps in entries.items():
        latest = max(reps, key=lambda r: (r[0], r[1]))
        s = stats[band]
        s[0] += 1
        s[1] += latest[2] == "positive"
        s[2] += any(r[3] for r in reps)
    out = ["## Author-dose entries", "",
           "| Daily dose | Author-dose entries | Positive on latest report at that dose | Entries with a side effect |",
           "|---|---:|---:|---:|"]
    for band in data["bands"]:
        n, positive, side = stats[band]
        if n:
            out.append(f"| {band} | {n} | {positive / n:.0%} | {side / n:.0%} |")
    out.append(f"| all stated doses | {sum(stats[b][0] for b in data['bands'])} | | |")
    return out + [""]


def route_table(data: dict) -> list[str]:
    paired = [d for d in data["doses"] if d["route"]]
    by_route = collections.defaultdict(list)
    for d in paired:
        by_route[d["route"]].append(d)
    out = ["## Route, where the amount and the route are on the same dose row", "",
           "| Route | Authors | Dose rows | Median mg | Range | Positive on latest | With a side effect |",
           "|---|---:|---:|---:|---|---:|---:|"]
    for route, rows in sorted(by_route.items(), key=lambda kv: -len({d["author"] for d in kv[1]})):
        amounts = [d["mg"] for d in rows]
        authors = {d["author"] for d in rows}
        latest: dict[str, tuple] = {}
        for d in rows:
            author, sentiment, when = data["reports"][d["report"]]
            if author not in latest or (when, d["report"]) > latest[author][0]:
                latest[author] = ((when, d["report"]), sentiment)
        side = {d["author"] for d in rows if data["adverse"].get(d["report"], 0)}
        positive = sum(1 for v in latest.values() if v[1] == "positive")
        out.append(f"| {route} | {len(authors)} | {len(rows)} | {statistics.median(amounts):g} | "
                   f"{min(amounts):g} to {max(amounts):g} | {positive} of {len(authors)} | {len(side)} of {len(authors)} |")
    return out + [""]


def titration(data: dict) -> list[str]:
    by_author = collections.defaultdict(list)
    for d in data["doses"]:
        author, _sentiment, when = data["reports"][d["report"]]
        by_author[author].append((when, d["report"], d["mg"], d["quote"]))
    out = ["## Authors stating two or more different amounts", "",
           "Read these by hand: a single post describing two amounts, a stated range and a change in "
           "frequency all land here, and only some are a change over time.", ""]
    movers = {a: sorted(rows) for a, rows in by_author.items() if len({r[2] for r in rows}) >= 2}
    out.append(f"{len(movers)} of {len(by_author)} authors with a stated amount.")
    out.append("")
    for author, rows in sorted(movers.items()):
        amounts = ", ".join(f"{r[2]:g}" for r in rows)
        out.append(f"- `{author[:8]}` {amounts} mg")
        for _when_value, _report, mg, quote in rows:
            out.append(f"    - {mg:g} mg: {(quote or '').strip()[:160]}")
    return out + [""]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--drug", required=True)
    ap.add_argument("--bands", default="25,50,100", help="comma-separated mg cut points (default 25,50,100)")
    ap.add_argument("--capsule-mg", type=float, default=None,
                    help="convert capsule and pill counts at this many mg each; omit to skip those rows")
    ap.add_argument("--max-mg", type=float, default=500.0, help="drop amounts above this as product-label leaks")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    cuts = [float(x) for x in args.bands.split(",") if x.strip()]
    data = load(args.db, args.drug, cuts, args.capsule_mg, args.max_mg)
    capsules = sum(1 for d in data["doses"] if d["from_capsules"])
    lines = [f"# {args.drug}: dose, route and titration", "",
             f"{len(data['reports'])} eligible reports, {len(data['doses'])} dose rows "
             f"({capsules} from capsule counts), {len({d['author'] for d in data['doses']})} authors with an amount.", ""]
    lines += band_table(data) + route_table(data) + titration(data)
    text = "\n".join(lines)
    args.out.write_text(text, encoding="utf-8") if args.out else print(text)


if __name__ == "__main__":
    main()
