"""Author-level summary of one drug from pipeline databases: who reported, what improved, what went wrong, at what dose.

    python src/summarize_drug.py --drug "urolithin a" --db supplement=path/a.db --db patient=path/b.db [--out report.md]

Eligible = a treatment report with a stated outcome (positive, negative or mixed). An author who appears in several
databases is counted once in the "All" column. Every count is derived from the pipeline's latest views; nothing is
re-extracted.
"""
from __future__ import annotations

import argparse
import collections
import re
import sqlite3
from pathlib import Path

IMPROVED = [  # (label, regex on the symptom the author named); first match wins, last is the catch-all
    ("Energy, stamina, less fatigue", r"energy|stamina|endur|tired|fatigue|vo2|afternoon slump|pem|crash|able to work|high functioning|good days"),
    ("Muscle, strength, exercise recovery", r"muscle|strength|stronger|fitness|exercise|workout|walk|physical|recover|repair|atrophy|tone"),
    ("Brain fog, focus, memory, motivation", r"fog|focus|clarity|cognit|memory|sharp|concentrat|mental|clearly|motivat|learn|attention|verbal|fluen|word|recall|productiv|drive|alert|awake"),
    ("Appetite, digestion", r"appetite|eating|food|digest"),
    ("Sleep", r"sleep|insomnia|nap|middle of the night"),
    ("Pain, headaches", r"pain|headache"),
    ("Heart rate, HRV", r"hrv|heart rate"),
    ("Twitching, tremor, coordination", r"twitch|tremor|coordination|weakness"),
    ("Mood, anxiety, wellbeing", r"mood|anxi|depress|calm|well.?being|happier|uplift|euphor|confiden|social|anhedon|outlook|stress|ptsd|rumination"),
    ("Libido, sexual", r"libido|sexual|erect"),
    ("Skin, hair", r"skin|hair"),
    ("General, no symptom named", r"."),
]
WORSENED = [
    ("Fatigue, drained, first-days crash", r"tired|fatigue|drained|exhaust|knocked|weak|lethar|energy"),
    ("Sleep disruption, vivid dreams", r"sleep|insomnia|dream"),
    ("Cardiovascular or autonomic", r"heart|palpit|hrv|pots|blood pressure|flush|tachy|bpm"),
    ("Gastrointestinal, appetite", r"stomach|diarr|stool|nausea|gut|bowel|appetite|dry mouth"),
    ("Activation, irritability, anxiety", r"anxi|edge|fight|flight|panic|wired|stimul|rage|adrenal|pmdd|irritab|jitter|restless|too strong|too much|paranoi|jaw|clench|grind|uninhibit|loopy|manic|agitat|aggress"),
    ("Tolerance, wears off, crash on stopping", r"toleran|wear|short.?liv|rebound|withdraw|dependen"),
    ("Headache or migraine", r"headache|migraine"),
    ("Cognitive or mood", r"fog|mood|depress|cognit|worse"),
    ("Muscle or joint", r"muscle|joint|pain"),
    ("Skin, itching, hair", r"itch|skin|hair|rash"),
    ("Dizziness", r"dizz"),
    ("Other", r"."),
]
DIRECTIONAL = ("positive", "negative", "mixed")


def categorize(symptom: str | None, table: list[tuple[str, str]]) -> str:
    text = (symptom or "").lower()
    return next(label for label, rx in table if re.search(rx, text))


def load(db: Path, drug: str, label: str) -> dict[str, dict]:
    """Per-author facts for one database: sentiments by date, effect rows by direction, dose amounts in mg."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    drug_id = conn.execute("SELECT id FROM treatment WHERE lower(canonical_name)=lower(?)", (drug,)).fetchone()
    if drug_id is None:
        raise SystemExit(f"{db}: no treatment named {drug!r}")
    authors: dict[str, dict] = {}
    eligible = f"r.drug_id={drug_id[0]} AND r.sentiment IN {DIRECTIONAL}"
    for user, report, sentiment, date in conn.execute(
            f"SELECT r.user_id, r.report_id, r.sentiment, p.post_date FROM treatment_reports r "
            f"JOIN posts p ON p.post_id=r.post_id WHERE {eligible}"):
        a = authors.setdefault(user, {"label": label, "reports": 0, "sentiments": [], "improved": [], "worsened": [],
                                      "no_change": 0, "doses": [], "routes": 0, "severities": []})
        a["reports"] += 1
        a["sentiments"].append((date or 0, sentiment))
        for direction, attribution, symptom, severity in conn.execute(
                "SELECT direction, attribution, symptom, severity FROM report_effects_latest WHERE report_id=?", (report,)):
            if attribution != "target":
                continue
            if direction == "improved":
                a["improved"].append(symptom)
            elif direction == "worsened":
                a["worsened"].append(symptom)
                if severity:
                    a["severities"].append(severity.lower())
            elif direction == "no_change":
                a["no_change"] += 1
        for low, unit, route in conn.execute(
                "SELECT low, unit, route FROM report_doses_latest WHERE report_id=?", (report,)):
            if low is not None and (unit or "").lower() in ("mg", "g"):
                a["doses"].append(low * (1000 if unit.lower() == "g" else 1))
            if route:
                a["routes"] += 1
    return authors


def merge(per_db: list[dict[str, dict]]) -> dict[str, dict]:
    """One record per author across databases (same username hash = same person)."""
    merged: dict[str, dict] = {}
    for authors in per_db:
        for user, a in authors.items():
            m = merged.setdefault(user, {"labels": set(), "reports": 0, "sentiments": [], "improved": [],
                                         "worsened": [], "no_change": 0, "doses": [], "routes": 0, "severities": []})
            m["labels"].add(a["label"])
            for key in ("reports", "no_change", "routes"):
                m[key] += a[key]
            for key in ("sentiments", "improved", "worsened", "doses", "severities"):
                m[key].extend(a[key])
    return merged


def pct(k: int, n: int) -> str:
    return f"{k} ({k / n:.0%})" if n else "0"


def summarize(drug: str, columns: list[tuple[str, dict[str, dict]]]) -> str:
    """Markdown report. ``columns`` = [(label, authors)], the first being the merged 'All'."""
    out = [f"# {drug}: author-level summary", ""]
    head = "| | " + " | ".join(f"{label} ({len(a)})" for label, a in columns) + " |"
    sep = "|---|" + "---:|" * len(columns)

    def row(name: str, f) -> str:
        return f"| {name} | " + " | ".join(str(f(a)) for _, a in columns) + " |"

    out += ["## Dataset", "", head, sep,
            row("Authors", len),
            row("Reports", lambda a: sum(x["reports"] for x in a.values())),
            row("Authors reporting a side effect", lambda a: sum(1 for x in a.values() if x["worsened"])),
            row("Side-effect data points", lambda a: sum(len(x["worsened"]) for x in a.values())),
            row("Authors reporting a dosage", lambda a: sum(1 for x in a.values() if x["doses"])),
            row("Dosage data points", lambda a: sum(len(x["doses"]) for x in a.values())),
            row("Authors stating a route", lambda a: sum(1 for x in a.values() if x["routes"])), ""]

    def latest(a: dict) -> str:
        return max(a["sentiments"])[1]

    out += ["## Sentiment", "", head, sep,
            row("Positive, latest report", lambda a: pct(sum(1 for x in a.values() if latest(x) == "positive"), len(a))),
            row("Negative, latest report", lambda a: pct(sum(1 for x in a.values() if latest(x) == "negative"), len(a))),
            row("Negative at any point", lambda a: pct(sum(1 for x in a.values() if any(s == "negative" for _, s in x["sentiments"])), len(a))),
            row("Any improvement attributed", lambda a: pct(sum(1 for x in a.values() if x["improved"]), len(a))),
            row("Said it did nothing", lambda a: pct(sum(1 for x in a.values() if x["no_change"]), len(a))),
            row("Any side effect attributed", lambda a: pct(sum(1 for x in a.values() if x["worsened"]), len(a))),
            row("Called a side effect severe", lambda a: pct(sum(1 for x in a.values() if any(
                s in ("severe", "life_threatening") for s in x["severities"])), len(a))),
            row("Stated any severity", lambda a: pct(sum(1 for x in a.values() if x["severities"]), len(a))), ""]

    for title, key, table in (("What it improved", "improved", IMPROVED), ("Side effects", "worsened", WORSENED)):
        out += [f"## {title}", "", head, sep]
        for label, _ in table:
            out.append(row(label, lambda a, label=label, key=key: pct(
                sum(1 for x in a.values() if any(categorize(s, table) == label for s in x[key])), len(a))))
        out.append("")

    out += ["## Side effects by stated dose", "", "| Daily amount | Authors | Any side effect | Any improvement | Latest positive |",
            "|---|---:|---:|---:|---:|"]
    merged = columns[0][1]
    bands = collections.defaultdict(list)
    for a in merged.values():
        if a["doses"]:
            mg = min(a["doses"])
            bands["500 mg" if mg <= 600 else "1000 mg" if mg <= 1200 else "above 1000 mg"].append(a)
    for band in ("500 mg", "1000 mg", "above 1000 mg"):
        g = bands.get(band, [])
        if g:
            out.append(f"| {band} | {len(g)} | {sum(1 for a in g if a['worsened'])} | "
                       f"{sum(1 for a in g if a['improved'])} | {sum(1 for a in g if latest(a) == 'positive')} |")
    out.append("")
    out.append("Authors with no stated amount are not placed. Counts are authors; a symptom row is one sentence "
               "the author wrote, attributed to the drug by the effects step.")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--drug", required=True, help="canonical treatment name as stored in each database")
    ap.add_argument("--db", action="append", required=True, metavar="LABEL=PATH",
                    help="a pipeline database with its column label; repeat for several")
    ap.add_argument("--out", type=Path, help="write the markdown here instead of stdout")
    args = ap.parse_args()
    per_db = []
    for spec in args.db:
        label, _, path = spec.partition("=")
        if not path:
            ap.error("--db takes LABEL=PATH")
        per_db.append((label, load(Path(path), args.drug, label)))
    columns = [("All", merge([a for _, a in per_db]))] + per_db if len(per_db) > 1 else per_db
    text = summarize(args.drug, columns)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
