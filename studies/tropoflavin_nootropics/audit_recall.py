"""Did extraction find the compounds that are demonstrably in the text?

Coverage has only ever been reported as absolute counts -- "752 author histories",
"202 compound exposures" -- with no denominator. 202 out of what? This supplies the
denominator by scanning the corpus the extractor was given, so a recall collapse shows
up as a number instead of as a quiet absence.

What the denominator is, and is not
-----------------------------------
"Mentions the compound in their text" is NOT "took the compound". The extraction prompt
deliberately excludes a treatment someone only asked about, was offered and declined, or
cited a study on. So the miss rate here is an UPPER BOUND on recall loss, not a measured
one, and it should be read as a trend and regression signal rather than quoted as a
defect count. To turn it into a true recall figure, intersect the corpus with an
independent judgement that the author actually used the compound -- the sentiment
pipeline's treatment_reports is one such source, and shares the author_hash namespace.

It also reports the other half. Instructing a model to be exhaustive buys recall and
costs attribution: it starts pairing a compound with whatever dose is nearby. So every
extracted dose and route is corroborated against the source text, and anything whose
value sits far from any mention of the compound it was attributed to is flagged.

Usage
-----
    python audit_recall.py --corpus <dir of user JSON> --records <records.csv> \
        --aliases aliases_78dhf.txt [--window 400] [--verbose]

Exit code is 1 if recall falls below --min-recall, so a run can gate on it.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Fields whose contents actually reach pipeline_b_compound_exposures. A compound named
# only in `medications` produces no exposure row, which is the failure this separates out.
STRUCTURED = ("dosage", "administration_route", "treatment_outcome")


def alias_pattern(aliases: list[str]) -> re.Pattern:
    """One regex over every spelling, longest first so `dhf` cannot mask `7,8-dhf`."""
    parts = [re.escape(a.strip()) for a in sorted(aliases, key=len, reverse=True) if a.strip()]
    # Spelling in the wild varies in its separators; treat them as interchangeable.
    parts = [p.replace(r"\-", r"[\s,.\-]?").replace(r"\.", r"[\s,.\-]?").replace(r"\ ", r"[\s,.\-]?")
             for p in parts]
    return re.compile("|".join(parts), re.I)


def author_text(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    chunks = []
    for post in data.get("posts") or []:
        chunks += [post.get("title") or "", post.get("body") or ""]
    for c in data.get("comments") or []:
        chunks.append(c.get("body") or "")
    return "\n".join(chunks)


def pairs(value: str, pat: re.Pattern) -> list[tuple[str, str]]:
    """`treatment: value` items whose treatment names a target compound."""
    out = []
    for item in (value or "").split("|"):
        if ":" in item:
            t, v = item.split(":", 1)
            if pat.search(t):
                out.append((t.strip(), v.strip()))
    return out


def corroborated(text: str, value: str, pat: re.Pattern, window: int) -> bool | None:
    """Does this value appear near a mention of the compound it was attributed to?

    None when the value carries no distinctive token to look for ("unspecified",
    "oral"); those are reported separately rather than counted either way.
    """
    num = re.search(r"[\d.]+", value)
    if not num:
        return None
    mentions = [m.start() for m in pat.finditer(text)]
    hits = [m.start() for m in re.finditer(re.escape(num.group()), text)]
    if not mentions or not hits:
        return False
    return min(abs(h - m) for h in hits for m in mentions) <= window


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, required=True, help="directory of per-author JSON")
    ap.add_argument("--records", type=Path, required=True, help="records.csv from the run")
    ap.add_argument("--aliases", type=Path, required=True, help="one alias per line")
    ap.add_argument("--window", type=int, default=400,
                    help="chars a dose may sit from a compound mention (default 400)")
    ap.add_argument("--min-recall", type=float, default=0.0,
                    help="exit 1 below this named-in-record recall (0-1)")
    ap.add_argument("--verbose", action="store_true", help="list every affected author")
    args = ap.parse_args()

    pat = alias_pattern(args.aliases.read_text(encoding="utf-8").splitlines())
    rows = {r["author_hash"]: r for r in csv.DictReader(
        args.records.open(encoding="utf-8"))}

    in_text, named, structured, missed, meds_only = [], [], [], [], []
    for path in sorted(args.corpus.glob("*.json")):
        h = path.stem
        text = author_text(path)
        if not pat.search(text):
            continue                              # nothing to find; not a miss
        in_text.append(h)
        row = rows.get(h)
        if row is None:
            missed.append(h)
            continue
        anywhere = any(pat.search(row.get(f) or "")
                       for f in ("medications", *STRUCTURED))
        usable = any(pat.search(row.get(f) or "") for f in STRUCTURED)
        if usable:
            structured.append(h)
        if anywhere:
            named.append(h)
            if not usable:
                meds_only.append(h)
        else:
            missed.append(h)

    n = len(in_text)
    print("=" * 74)
    print("EXTRACTION RECALL against the corpus the extractor was given")
    print("=" * 74)
    print("  NOTE: the denominator is 'mentions the compound', not 'took it'. The prompt")
    print("  excludes treatments merely discussed, so misses below are an UPPER BOUND.")
    if not n:
        print("no author in the corpus mentions any alias -- nothing to measure")
        return 0
    pct = lambda k: f"{100 * k / n:5.1f}%"
    print(f"  authors whose text mentions the compound : {n}")
    print(f"  ...named anywhere in their record        : {len(named):>4}  {pct(len(named))}")
    print(f"  ...with it in a structured field         : {len(structured):>4}  {pct(len(structured))}"
          "   <- the only ones that reach an exposure row")
    print(f"  ...named in medications only             : {len(meds_only):>4}  {pct(len(meds_only))}"
          "   <- recognised, unusable downstream")
    print(f"  ...absent from the record entirely       : {len(missed):>4}  {pct(len(missed))}"
          "   <- recall misses")

    ok_d = bad_d = unchecked = 0
    flagged = []
    for h in structured:
        row, text = rows[h], None
        for field in ("dosage", "administration_route"):
            for treatment, value in pairs(row.get(field), pat):
                if text is None:
                    text = author_text(args.corpus / f"{h}.json")
                verdict = corroborated(text, value, pat, args.window)
                if verdict is None:
                    unchecked += 1
                elif verdict:
                    ok_d += 1
                else:
                    bad_d += 1
                    flagged.append((h, field, treatment, value))

    print(f"\n  attribution check (numeric values, +/-{args.window} chars)")
    print(f"    corroborated near a mention : {ok_d}")
    print(f"    NOT corroborated            : {bad_d}"
          + ("   <- likely paired with another compound's dose" if bad_d else ""))
    print(f"    no numeric token to check   : {unchecked}   (routes, 'unspecified', frequencies)")
    if flagged and args.verbose:
        print("\n    flagged:")
        for h, f, t, v in flagged:
            print(f"      [{h[:8]}] {f:22} {t} -> {v}")

    recall = len(named) / n
    if recall < args.min_recall:
        print(f"\nFAIL: recall {recall:.3f} below --min-recall {args.min_recall}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
