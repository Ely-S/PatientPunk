"""Per-treatment evidence coverage for EVERY Long-COVID benchmark + target trial.

NATURAL can only estimate a trial if its intervention has enough author-attributed patient reports
(each author = one causal unit). This streams the LC Reddit corpus once and counts distinct authors
+ mentions per intervention, so COVERAGE (not the self-obtainability heuristic) decides which trials
are runnable. Method matches TrialScout count_distinct_authors (author_fullname or author,
word-boundary alias regex) so counts are comparable to signal_distinct.json.

Covers all 50 LC completed benchmark trials + the 3 prospective targets. Interventions that aren't a
nameable drug/procedure (generic "exercise", rehab apps, self-management programmes) are reported as
N/A — a drug-alias count is meaningless for them (not zero signal, just not alias-measurable).

Run: trial_superset/.venv/Scripts/python.exe trial_superset/measure_coverage.py
Output: data/drug_coverage.csv
"""

from __future__ import annotations

import csv
import json
import os
import re

CORPUS_DIR = r"C:\Users\scgee\OneDrive\Documents\Projects\PatientPunk_data"
CORPUS = [
    ("r_covidlonghaulers_comments_all.jsonl", ("body",)),
    ("r_covidlonghaulers_posts_all.jsonl", ("title", "selftext")),
    ("r_LongCovid_comments.jsonl", ("body",)),
    ("r_LongCovid_posts.jsonl", ("title", "selftext")),
    ("r_LongHaulersRecovery_comments.jsonl", ("body",)),
    ("r_LongHaulersRecovery_posts.jsonl", ("title", "selftext")),
]
OUT = "trial_superset/data/drug_coverage.csv"

# drug_key -> aliases (word-boundary, case-insensitive). Prefer specific multi-word aliases over
# short acronyms to limit false positives; noisy-alias drugs are flagged in NOTE below.
DRUG_ALIASES = {
    "fluvoxamine": ["fluvoxamine", "luvox"],
    "vortioxetine": ["vortioxetine", "trintellix", "brintellix"],
    "lithium": ["lithium"],
    "cyclobenzaprine": ["cyclobenzaprine", "flexeril", "tnx-102", "tnx102", "tonmya"],
    "lau-7b": ["lau-7b", "lau7b", "fenretinide"],
    "nicotinamide_riboside": ["niagen", "nicotinamide riboside", "nicotinamide-riboside"],
    "adapt-232": ["adapt-232", "adapt232", "chisan"],
    "prospekta": ["prospekta"],
    "homeopathy": ["homeopath"],
    "paxlovid_nirmatrelvir": ["paxlovid", "nirmatrelvir"],
    "efgartigimod": ["efgartigimod", "vyvgart"],
    "mesenchymal_stem_cell": ["mesenchymal stem cell", "stem cell", "hb-admsc", "admsc"],
    "hyperbaric_oxygen": ["hyperbaric", "hbot"],
    "l_citrulline": ["l-citrulline", "citrulline"],
    "prednisolone": ["prednisolone", "prednisone"],
    "regenecyte": ["regenecyte"],
    "rintatolimod": ["rintatolimod", "ampligen"],
    "stellate_ganglion_block": ["stellate ganglion"],
    "sulodexide": ["sulodexide"],
    "vitamin_d": ["cholecalciferol", "vitamin d3", "vitamin d"],
    "tdcs": ["tdcs", "transcranial direct current"],
    "plasma_exchange_apheresis": ["plasma exchange", "plasmapheresis", "apheresis", "immunoadsorption"],
    "vagus_nerve_stim": ["vagus nerve", "vagal nerve", "tvns"],
    "oxaloacetate": ["oxaloacetate", "benagene"],
    "tens": ["tens unit", "transcutaneous electrical"],
    # targets
    "tirzepatide": ["tirzepatide", "mounjaro", "zepbound"],
    "naltrexone_ldn": ["low dose naltrexone", "low-dose naltrexone", "naltrexone", "ldn"],
    "pyridostigmine": ["pyridostigmine", "mestinon"],
    "ivig": ["ivig", "intravenous immunoglobulin", "immunoglobulin", "privigen", "gamunex", "octagam", "gammagard"],
}
# alias likely over-counts (off-target sense): "vitamin d"/general supplementation, "vagus nerve"
# (LC theory, not the device), "paxlovid" (mostly ACUTE-covid/rebound, not LC treatment), "prednisone"
# (other conditions), "immunoglobulin" (IgG antibody tests), general "stem cell", etc. -> validate before trusting.
NOISY = {"lithium", "vitamin_d", "mesenchymal_stem_cell", "ivig", "homeopathy", "tens",
         "paxlovid_nirmatrelvir", "vagus_nerve_stim", "prednisolone", "hyperbaric_oxygen"}

# one entry per trial -> (drug_key, role, credibility). Multiple trials can share a drug_key.
TRIALS = [
    ("NCT05874037", "fluvoxamine", "completed", "established"),
    ("NCT05047952", "vortioxetine", "completed", "established"),
    ("NCT05618587", "lithium", "completed", "established"),
    ("NCT05472090", "cyclobenzaprine", "completed", "established"),
    ("NCT05999435", "lau-7b", "completed", "investigational"),
    ("NCT04809974", "nicotinamide_riboside", "completed", "supplement"),
    ("NCT04795557", "adapt-232", "completed", "fringe"),
    ("NCT05074888", "prospekta", "completed", "fringe"),
    ("NCT05104749", "homeopathy", "completed", "fringe"),
    ("NCT05965726", "paxlovid_nirmatrelvir", "completed", "established"),
    ("NCT05576662", "paxlovid_nirmatrelvir", "completed", "established"),
    ("NCT05595369", "paxlovid_nirmatrelvir", "completed", "established"),
    ("NCT05633407", "efgartigimod", "completed", "established"),
    ("NCT05126563", "mesenchymal_stem_cell", "completed", "investigational"),
    ("NCT04842448", "hyperbaric_oxygen", "completed", "procedure"),
    ("NCT07544186", "l_citrulline", "completed", "supplement"),
    ("NCT04657484", "prednisolone", "completed", "established"),
    ("NCT05682560", "regenecyte", "completed", "investigational"),
    ("NCT05592418", "rintatolimod", "completed", "investigational"),
    ("NCT06253806", "stellate_ganglion_block", "completed", "procedure"),
    ("NCT05371925", "sulodexide", "completed", "established"),
    ("NCT06419712", "vitamin_d", "completed", "supplement"),
    ("ISRCTN10942585", "tdcs", "completed", "device"),
    ("NCT04876417", "tdcs", "completed", "device"),
    ("NCT05445674", "plasma_exchange_apheresis", "completed", "procedure"),
    ("NCT05841498", "plasma_exchange_apheresis", "completed", "procedure"),
    ("NCT05445427", "vagus_nerve_stim", "completed", "device"),
    ("NCT05840237", "oxaloacetate", "completed", "supplement"),
    ("NCT05200858", "tens", "completed", "device"),
    # targets
    ("NCT07128082", "tirzepatide", "target", "established"),
    ("NCT06366724", "naltrexone_ldn", "target(LIFT)", "repurposed"),
    ("NCT06366724", "pyridostigmine", "target(LIFT)", "established"),
    ("NCT06305793", "ivig", "target", "clinic_administered"),
]
# interventions with no nameable drug alias — coverage N/A (not zero, just not alias-measurable)
NONMEASURABLE = {
    "NCT04718506": "Exercise", "NCT04900961": "Resistance Exercise", "NCT05003271": "Exercise program",
    "NCT05752331": "Physical activity behavioural modification", "NCT05848518": "Rehabilitation program",
    "NCT05911113": "Sensory re-education", "NCT05961462": "Exercise training",
    "NCT05965739": "BrainHQ", "NCT06016192": "Aerobic exercise", "NCT06294756": "Sulfurous thermal water",
    "NCT06492577": "Pulmonary rehab", "NCT05846126": "RehabCovid telematic", "NCT05965752": "BrainHQ",
    "NCT06136871": "CO-OP procedures", "NCT06214455": "Low-sugar diet / eating window",
    "NCT05024474": "Inspiratory muscle training", "ISRCTN12595520": "Weight management programme",
    "ISRCTN36407216": "LISTEN self-management", "ISRCTN38746119": "LC Optimal Health Programme",
    "ISRCTN15414370": "Online multimodal rehab", "ISRCTN91104012": "ReCOVery telerehab app",
}

ALIAS2DRUG = {a.lower(): d for d, al in DRUG_ALIASES.items() for a in al}
PAT = re.compile(r"\b(" + "|".join(re.escape(a) for a in sorted(ALIAS2DRUG, key=len, reverse=True)) + r")\b", re.I)


def verdict(n):
    return "runnable" if n >= 50 else "thin" if n >= 5 else "no_signal"


def main():
    authors = {d: set() for d in DRUG_ALIASES}
    mentions = {d: 0 for d in DRUG_ALIASES}
    for fname, fields in CORPUS:
        path = os.path.join(CORPUS_DIR, fname)
        if not os.path.exists(path):
            print(f"  [skip] {fname}")
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
    for nct, drug, role, cred in TRIALS:
        da = len(authors[drug])
        rows.append({"trial_nct": nct, "intervention": drug, "role": role, "credibility": cred,
                     "distinct_authors": da, "n_mentions": mentions[drug],
                     "runnable": verdict(da), "alias_note": "over-count risk" if drug in NOISY else ""})
    for nct, iv in NONMEASURABLE.items():
        rows.append({"trial_nct": nct, "intervention": iv, "role": "completed", "credibility": "non_pharmacologic",
                     "distinct_authors": "", "n_mentions": "", "runnable": "N/A_not_nameable", "alias_note": ""})
    rows.sort(key=lambda r: (-1 if r["distinct_authors"] == "" else -r["distinct_authors"], r["trial_nct"]))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["trial_nct", "intervention", "role", "credibility",
                                          "distinct_authors", "n_mentions", "runnable", "alias_note"])
        w.writeheader(); w.writerows(rows)

    meas = [r for r in rows if r["runnable"] != "N/A_not_nameable"]
    runnable = [r for r in meas if r["runnable"] == "runnable"]
    print(f"\n{'trial':<15}{'intervention':<24}{'authors':>8}  {'runnable':<10} {'role'}")
    for r in sorted(meas, key=lambda r: -r["distinct_authors"]):
        print(f"  {r['trial_nct']:<15}{r['intervention']:<24}{r['distinct_authors']:>8}  {r['runnable']:<10} {r['role']} [{r['credibility']}]")
    print(f"\nRUNNABLE trials (>=50 distinct authors): {len(runnable)} / {len(meas)} measurable "
          f"(+{len(NONMEASURABLE)} non-nameable N/A)")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
