"""Count, from raw post text, how many distinct authors state a dose for 7,8-DHF.

Independent of the extraction pipeline. The 59 figure comes from Pipeline B output,
and Pipeline B is known to under-extract (issue #143), so this measures the source
directly: find a compound mention, look for a mass quantity near it, count authors.

Deliberately generous. A number with a mass unit close to a compound mention is
counted, without checking that the dose is the author's own or that it belongs to
that compound rather than a neighbour. So this is an UPPER BOUND on how many people
state a dose, which is the right shape for testing whether 59 is too low.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 4'-DMA needs care: bare "dma" collides with MDMA and DMAE, so it is only
# accepted when attached to a dhf/flavone token or written as 4-dma / 4'-dma.
COMPOUND = re.compile(
    r"7\s*[,.\-]?\s*8\s*[-\s]?\s*dhf"
    r"|7\s*[,.\-]?\s*8\s*[-\s]?\s*dihydroxy\s*-?\s*flavone"
    r"|dihydroxyflavone"
    r"|tropoflavin"
    r"|eutropoflavin"
    r"|4\s*'?\s*-?\s*dma\s*-?\s*7"
    r"|4\s*'?\s*-?\s*dma\s*-?\s*dhf"
    r"|\bdhf\b",
    re.I)

DOSE = re.compile(r"(?<![\w.])(\d{1,5}(?:\.\d+)?)\s*(mg|milligram|mcg|ug|microgram|g|gram)s?\b",
                  re.I)

# Plausible human doses, in mg. Filters out "7,8" itself, years, prices, study
# figures in the gram range that are obviously not a person's dose.
MIN_MG, MAX_MG = 0.05, 5000.0


# Data lives beside the checkout, not in it (AGENTS.md).
DEFAULT_DATA_ROOT = Path(
    os.environ.get("PATIENTPUNK_DATA")
    or Path(__file__).resolve().parents[2].parent / "PatientPunk_data")

def to_mg(value: str, unit: str) -> float | None:
    unit = unit.lower()
    try:
        x = float(value)
    except ValueError:
        return None
    if unit.startswith(("mcg", "ug", "micro")):
        return x / 1000
    if unit in ("g", "gram", "grams"):
        return x * 1000
    return x


def hits(text: str, window: int):
    """Yield (compound_span, dose_mg, snippet) for doses near a compound mention."""
    if not text:
        return
    mentions = [m.span() for m in COMPOUND.finditer(text)]
    if not mentions:
        return
    for dm in DOSE.finditer(text):
        mg = to_mg(dm.group(1), dm.group(2))
        if mg is None or not (MIN_MG <= mg <= MAX_MG):
            continue
        for (a, b) in mentions:
            gap = 0 if a <= dm.start() <= b else min(abs(dm.start() - b), abs(a - dm.end()))
            if gap <= window:
                lo, hi = max(0, min(a, dm.start()) - 60), max(b, dm.end()) + 60
                yield (a, b), mg, text[lo:hi].replace("\n", " ")
                break


def scan_comparators(db: Path, window: int):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    authors, per_author, examples = set(), collections.Counter(), []
    mention_authors = set()
    n = 0
    for user_id, title, body in con.execute(
            "select user_id, title, body_text from posts"):
        n += 1
        text = f"{title or ''}\n{body or ''}"
        if not COMPOUND.search(text):
            continue
        mention_authors.add(user_id)
        found = list(hits(text, window))
        if found:
            authors.add(user_id)
            per_author[user_id] += len(found)
            if len(examples) < 12:
                examples.append((user_id, found[0][1], found[0][2]))
    return dict(scanned=n, mention_authors=mention_authors, dose_authors=authors,
                per_author=per_author, examples=examples)


def scan_corpus_dir(users: Path, window: int):
    authors, mention_authors = set(), set()
    for path in users.glob("*.json"):
        d = json.loads(path.read_text(encoding="utf-8"))
        parts = []
        for p in d.get("posts") or []:
            parts += [p.get("title") or "", p.get("body") or ""]
        parts += [c.get("body") or "" for c in (d.get("comments") or [])]
        text = "\n".join(parts)
        if not COMPOUND.search(text):
            continue
        mention_authors.add(path.stem)
        if any(hits(text, window)):
            authors.add(path.stem)
    return mention_authors, authors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA_ROOT,
                    help="data root (default: PATIENTPUNK_DATA env var, else ../PatientPunk_data)")
    ap.add_argument("--window", type=int, default=120,
                    help="max chars between a compound mention and the dose")
    args = ap.parse_args()

    runs = args.data / "studies" / "tropoflavin_nootropics" / "runs"
    comp_db = runs / "2026-08-31-comparator-cohort" / "sentiment" / "comparators.db"
    users = runs / "2026-08-27-linked-dose-route" / "corpus" / "users"

    print("=" * 72)
    print(f"RAW TEXT SCAN  (dose within {args.window} chars of a compound mention)")
    print("=" * 72)

    print("\nA. Pipeline B's own corpus -- the 752 author histories it was given")
    m, d = scan_corpus_dir(users, args.window)
    print(f"   authors mentioning the compound      : {len(m)}")
    print(f"   authors with a dose near a mention   : {len(d)}   <- compare to 59")

    print("\nB. Full r/Nootropics corpus in comparators.db")
    r = scan_comparators(comp_db, args.window)
    print(f"   posts/comments scanned               : {r['scanned']:,}")
    print(f"   authors mentioning the compound      : {len(r['mention_authors'])}")
    print(f"   authors with a dose near a mention   : {len(r['dose_authors'])}")
    print(f"   ...not in Pipeline B's 752-author corpus: "
          f"{len(r['dose_authors'] - set(p.stem for p in users.glob('*.json')))}")

    print("\n   sample hits (verify these read as real doses):")
    for uid, mg, snip in r["examples"]:
        print(f"     [{uid[:8]}] {mg:>8.1f} mg | ...{snip[:150].strip()}...")


if __name__ == "__main__":
    main()
