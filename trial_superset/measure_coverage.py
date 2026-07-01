"""Per-treatment evidence coverage for the Long-COVID benchmark + target drugs.

NATURAL can only estimate a trial if its drug has enough author-attributed patient reports (each
author = one causal unit). This streams the Long-COVID Reddit corpus once and counts distinct
authors + mentions per drug, so we know which trials are actually RUNNABLE before wiring the
evidence plane. Method matches TrialScout's count_distinct_authors (author_fullname or author,
word-boundary alias regex) so counts are comparable to signal_distinct.json.

Run: trial_superset/.venv/Scripts/python.exe trial_superset/measure_coverage.py
Output: data/drug_coverage.csv
"""

from __future__ import annotations

import csv
import json
import os
import re

CORPUS_DIR = r"C:\Users\scgee\OneDrive\Documents\Projects\PatientPunk_data"
CORPUS = [  # (file, text-fields) — all three LC subreddits, posts + comments
    ("r_covidlonghaulers_comments_all.jsonl", ("body",)),
    ("r_covidlonghaulers_posts_all.jsonl", ("title", "selftext")),
    ("r_LongCovid_comments.jsonl", ("body",)),
    ("r_LongCovid_posts.jsonl", ("title", "selftext")),
    ("r_LongHaulersRecovery_comments.jsonl", ("body",)),
    ("r_LongHaulersRecovery_posts.jsonl", ("title", "selftext")),
]
OUT = "trial_superset/data/drug_coverage.csv"

# drug -> (aliases, trial NCT, role, credibility). Covers every benchmark + target intervention.
DRUGS = {
    "fluvoxamine":    (["fluvoxamine", "luvox"], "NCT05874037", "completed_benchmark", "established"),
    "vortioxetine":   (["vortioxetine", "trintellix", "brintellix"], "NCT05047952", "completed_benchmark", "established"),
    "lithium":        (["lithium"], "NCT05618587", "completed_benchmark", "established"),
    "cyclobenzaprine": (["cyclobenzaprine", "flexeril", "tnx-102", "tnx102", "tonmya"], "NCT05472090", "completed_benchmark", "established"),
    "lau-7b":         (["lau-7b", "lau7b", "fenretinide"], "NCT05999435", "completed_benchmark", "investigational"),
    "nicotinamide_riboside": (["niagen", "nicotinamide riboside", "nicotinamide-riboside"], "NCT04809974", "completed_benchmark", "supplement"),
    "adapt-232":      (["adapt-232", "adapt232", "chisan"], "NCT04795557", "completed_benchmark", "fringe"),
    "prospekta":      (["prospekta"], "NCT05074888", "completed_benchmark", "fringe"),
    "homeopathy":     (["homeopath"], "NCT05104749", "completed_benchmark", "fringe"),
    "tirzepatide":    (["tirzepatide", "mounjaro", "zepbound"], "NCT07128082", "prospective_target", "established"),
    "naltrexone_ldn": (["low dose naltrexone", "low-dose naltrexone", "naltrexone", "ldn"], "NCT06366724", "prospective_target(LIFT)", "repurposed"),
    "pyridostigmine": (["pyridostigmine", "mestinon"], "NCT06366724", "prospective_target(LIFT)", "established"),
    "ivig":           (["ivig", "intravenous immunoglobulin", "immunoglobulin", "privigen", "gamunex", "octagam", "gammagard"], "NCT06305793", "prospective_target", "clinic_administered"),
}
ALIAS2DRUG = {a.lower(): d for d, v in DRUGS.items() for a in v[0]}
PAT = re.compile(r"\b(" + "|".join(re.escape(a) for a in sorted(ALIAS2DRUG, key=len, reverse=True)) + r")\b", re.I)


def verdict(n):
    return "runnable" if n >= 50 else "thin" if n >= 5 else "no_signal"


def main():
    authors = {d: set() for d in DRUGS}
    mentions = {d: 0 for d in DRUGS}
    for fname, fields in CORPUS:
        path = os.path.join(CORPUS_DIR, fname)
        if not os.path.exists(path):
            print(f"  [skip] {fname} not found")
            continue
        print(f"  scanning {fname} ...")
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                text = " ".join(str(d.get(f, "") or "") for f in fields)
                if not text:
                    continue
                hits = PAT.findall(text)
                if not hits:
                    continue
                auth = d.get("author_fullname") or d.get("author") or ""
                if auth in ("", "[deleted]", "AutoModerator", "None"):
                    auth = None
                for h in set(x.lower() for x in hits):
                    drug = ALIAS2DRUG[h]
                    mentions[drug] += 1
                    if auth:
                        authors[drug].add(auth)

    rows = []
    for drug, (al, nct, role, cred) in DRUGS.items():
        da = len(authors[drug])
        rows.append({"drug": drug, "trial_nct": nct, "role": role, "credibility": cred,
                     "distinct_authors": da, "n_mentions": mentions[drug], "runnable": verdict(da)})
    rows.sort(key=lambda r: -r["distinct_authors"])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["drug", "trial_nct", "role", "credibility",
                                          "distinct_authors", "n_mentions", "runnable"])
        w.writeheader(); w.writerows(rows)

    print(f"\n{'drug':<22}{'authors':>9}{'mentions':>10}  {'runnable':<10} role")
    for r in rows:
        print(f"  {r['drug']:<20}{r['distinct_authors']:>9}{r['n_mentions']:>10}  {r['runnable']:<10} {r['role']} [{r['credibility']}]")
    runnable = [r for r in rows if r["runnable"] == "runnable"]
    print(f"\nRUNNABLE (>=50 distinct authors): {len(runnable)}/{len(rows)} -> {[r['drug'] for r in runnable]}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
