"""A defensible count of people stating their own 7,8-DHF dose, from raw text.

The loose scan returned 148 authors, but inspection showed three recurring false
positives:

  1. `mg/kg` figures quoted from rodent studies -- a citation, not the author's dose
  2. stack lists, where the nearest milligram figure belongs to a neighbouring
     compound ("Coluracetam 20mg ... 7,8-DHF")
  3. product-label and price descriptions

This applies three filters and reports the count after each, so the attrition is
visible rather than asserted:

  LOOSE   dose within `window` chars of a compound mention
  -/kg    drop mg/kg and any dose inside a study-citation context
  NEAREST drop doses closer to some other drug name than to the compound
  FIRST   require first-person use language near the dose

The drug-name vocabulary is taken from the corpus itself -- the distinct treatment
strings Pipeline B extracted -- rather than a list written from memory.
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

COMPOUND = re.compile(
    r"7\s*[,.\-]?\s*8\s*[-\s]?\s*dhf"
    r"|7\s*[,.\-]?\s*8\s*[-\s]?\s*dihydroxy\s*-?\s*flavone"
    r"|dihydroxyflavone|tropoflavin|eutropoflavin"
    r"|4\s*'?\s*-?\s*dma\s*-?\s*7|4\s*'?\s*-?\s*dma\s*-?\s*dhf|\bdhf\b", re.I)

DOSE = re.compile(r"(?<![\w.])(\d{1,5}(?:\.\d+)?)\s*(mg|mcg|ug|g)\b(\s*/\s*kg)?", re.I)

STUDY = re.compile(r"\b(mice|mouse|rat|rats|rodent|in vivo|in vitro|i\.?p\.?|gavage|"
                   r"study|studies|trial|pubmed|doi|et al|abstract|paper)\b", re.I)

FIRST_PERSON = re.compile(
    r"\b(i|i'?ve|i'?m|my|me)\b[^.!?]{0,80}?\b(take|taking|took|dose|dosed|dosing|"
    r"use|used|using|run|ran|running|start|started|on)\b"
    r"|\b(take|taking|took|dose|dosed|dosing|used|using)\b[^.!?]{0,40}?\b(i|my|me)\b",
    re.I)

MIN_MG, MAX_MG = 0.05, 5000.0


# Data lives beside the checkout, not in it (AGENTS.md).
DEFAULT_DATA_ROOT = Path(
    os.environ.get("PATIENTPUNK_DATA")
    or Path(__file__).resolve().parents[2].parent / "PatientPunk_data")

def to_mg(v, u):
    u = u.lower()
    try:
        x = float(v)
    except ValueError:
        return None
    return x / 1000 if u in ("mcg", "ug") else x * 1000 if u == "g" else x


def drug_vocabulary(linked_db: Path) -> re.Pattern:
    """Other drug names, harvested from what Pipeline B actually extracted here."""
    con = sqlite3.connect(f"file:{linked_db}?mode=ro", uri=True)
    names = set()
    for table, col in (("pipeline_b_dosages", "treatment"),
                       ("pipeline_b_administration_routes", "treatment"),
                       ("pipeline_b_treatment_outcomes", "treatment")):
        for (t,) in con.execute(f"select distinct {col} from {table}"):
            t = (t or "").strip().lower()
            if len(t) < 3 or COMPOUND.search(t):
                continue                      # skip the target compound itself
            t = re.split(r"[+/,]", t)[0].strip()
            if len(t) >= 3:
                names.add(t)
    con.close()
    if not names:
        return re.compile(r"(?!x)x")
    pat = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.compile(rf"\b(?:{pat})\b", re.I)


def classify(text: str, window: int, others: re.Pattern):
    """Best verdict achieved by any dose in this text."""
    best = None
    mentions = [m.span() for m in COMPOUND.finditer(text)]
    if not mentions:
        return None
    rank = {"loose": 1, "nokg": 2, "nearest": 3, "first": 4}
    for dm in DOSE.finditer(text):
        mg = to_mg(dm.group(1), dm.group(2))
        if mg is None or not (MIN_MG <= mg <= MAX_MG):
            continue
        near = min(mentions, key=lambda s: 0 if s[0] <= dm.start() <= s[1]
                   else min(abs(dm.start() - s[1]), abs(s[0] - dm.end())))
        gap = (0 if near[0] <= dm.start() <= near[1]
               else min(abs(dm.start() - near[1]), abs(near[0] - dm.end())))
        if gap > window:
            continue
        verdict = "loose"

        ctx = text[max(0, dm.start() - 150): dm.end() + 150]
        if dm.group(3) or STUDY.search(ctx):
            best = best if best and rank[best] > rank[verdict] else best or verdict
            continue
        verdict = "nokg"

        # is some other drug name closer to this dose than our compound is?
        rival = None
        for om in others.finditer(text):
            g = (0 if om.start() <= dm.start() <= om.end()
                 else min(abs(dm.start() - om.end()), abs(om.start() - dm.end())))
            if rival is None or g < rival:
                rival = g
        if rival is not None and rival < gap:
            best = best if best and rank[best] > rank[verdict] else verdict
            continue
        verdict = "nearest"

        if FIRST_PERSON.search(ctx):
            verdict = "first"
        if best is None or rank[verdict] > rank[best]:
            best = verdict
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA_ROOT,
                    help="data root (default: PATIENTPUNK_DATA env var, else ../PatientPunk_data)")
    ap.add_argument("--window", type=int, default=120)
    ap.add_argument("--show", type=int, default=8)
    args = ap.parse_args()

    runs = args.data / "studies" / "tropoflavin_nootropics" / "runs"
    users = runs / "2026-08-27-linked-dose-route" / "corpus" / "users"
    linked = runs / "2026-08-31-comparator-cohort" / "study" / "nootropics_pipeline_a_b_linked.db"

    others = drug_vocabulary(linked)
    counts = collections.Counter()
    keep = {"nearest": [], "first": []}

    for path in sorted(users.glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        parts = []
        for p in d.get("posts") or []:
            parts += [p.get("title") or "", p.get("body") or ""]
        parts += [c.get("body") or "" for c in (d.get("comments") or [])]
        text = "\n".join(parts)
        v = classify(text, args.window, others)
        if v:
            counts[v] += 1
            if v in keep and len(keep[v]) < args.show:
                m = COMPOUND.search(text)
                keep[v].append((path.stem, text[max(0, m.start()-90): m.start()+150]
                                .replace("\n", " ")))

    order = ["loose", "nokg", "nearest", "first"]
    cum = {k: sum(counts[o] for o in order[order.index(k):]) for k in order}
    print("=" * 74)
    print("AUTHORS STATING A 7,8-DHF DOSE, FROM RAW TEXT (752-author corpus)")
    print("=" * 74)
    print(f"  {'LOOSE   any dose near a mention':52}{cum['loose']:>6}")
    print(f"  {'  after dropping mg/kg and study citations':52}{cum['nokg']:>6}")
    print(f"  {'  after dropping doses nearer another drug name':52}{cum['nearest']:>6}")
    print(f"  {'  after requiring first-person use language':52}{cum['first']:>6}")
    print(f"\n  Pipeline B extracted (original 47 + 12 recovered) : 59")

    for label in ("nearest", "first"):
        print(f"\n  sample [{label}]:")
        for uid, snip in keep[label]:
            print(f"    [{uid[:8]}] ...{snip.strip()[:145]}...")


if __name__ == "__main__":
    main()
