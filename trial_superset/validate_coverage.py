"""Validate the raw coverage counts: what fraction of mentions are ON-TARGET for NATURAL?

Raw distinct-author counts are upper bounds — an alias like "paxlovid" catches mostly ACUTE-covid
talk, "vitamin d" catches general supplementation, "immunoglobulin" catches IgG antibody tests, etc.
This reservoir-samples ~N real mentions per drug (one corpus pass) and LLM-classifies each as an
on-target personal treatment report for Long COVID vs off-target, giving an effective-coverage estimate
= raw_authors x on_target_fraction. Clean-alias controls (fluvoxamine, oxaloacetate, LDN) sanity-check
the method (should score high).

Run: PYTHONPATH=trial_superset trial_superset/.venv/Scripts/python.exe -m validate_coverage
Output: data/coverage_validation.csv (+ coverage_validation_samples.jsonl for audit)
"""

from __future__ import annotations

import csv
import json
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor

from measure_coverage import DRUG_ALIASES, CORPUS, CORPUS_DIR
from litlabels.extract_labels import _client, MODEL, _parse_json

random.seed(42)
N = 20
OUT = "trial_superset/data/coverage_validation.csv"
SAMPLES = "trial_superset/data/coverage_validation_samples.jsonl"
COVERAGE = "trial_superset/data/drug_coverage.csv"

# validate EVERY runnable drug (>=50 raw authors) so each trial gets a real on-target report count.
VALIDATE = ["naltrexone_ldn", "vitamin_d", "vagus_nerve_stim", "prednisolone", "plasma_exchange_apheresis",
            "hyperbaric_oxygen", "stellate_ganglion_block", "pyridostigmine", "ivig", "paxlovid_nirmatrelvir",
            "tirzepatide", "fluvoxamine", "l_citrulline", "tens", "lithium", "nicotinamide_riboside",
            "vortioxetine", "rintatolimod", "oxaloacetate", "cyclobenzaprine", "sulodexide", "efgartigimod",
            "mesenchymal_stem_cell", "homeopathy"]

PROMPT = """These are Reddit snippets from Long COVID communities that mention "{drug}". For NATURAL we
need reports where an individual personally used (or is seriously trying) {drug} as a treatment for
THEIR OWN Long COVID and describes some experience/response.

For each snippet return on_target=true ONLY if it's a personal Long-COVID treatment report for {drug}.
Mark on_target=false for: acute-COVID use (treating the initial infection, not long COVID), general
theory/mechanism/news, a lab test (e.g. immunoglobulin/IgG antibody testing), someone else's use, a
question with no personal use, or an unrelated sense of the word.

Return ONLY JSON: {{"results":[{{"idx":int,"on_target":true/false,"category":"long_covid_treatment|acute_covid|general_theory|lab_test|other_person|question_only|unrelated"}}]}}"""


# WORD-BOUNDARY regex per drug (same as measure_coverage's count) — bare substring matched
# "ldn" inside "couldn't"/"wouldn't" and centered snippets on garbage. This centers on a real match.
DRUG_PAT = {d: re.compile(r"\b(" + "|".join(re.escape(a) for a in DRUG_ALIASES[d]) + r")\b", re.I)
            for d in VALIDATE}


def sample_corpus():
    res = {d: [] for d in VALIDATE}
    seen = {d: 0 for d in VALIDATE}
    for fname, fields in CORPUS:
        path = os.path.join(CORPUS_DIR, fname)
        if not os.path.exists(path):
            continue
        print(f"  sampling {fname} ...")
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                text = " ".join(str(d.get(f, "") or "") for f in fields)
                if not text:
                    continue
                for drug in VALIDATE:
                    m = DRUG_PAT[drug].search(text)
                    if not m:
                        continue
                    seen[drug] += 1
                    snip = text[max(0, m.start() - 220):m.end() + 220].replace("\n", " ").strip()
                    if len(res[drug]) < N:
                        res[drug].append(snip)
                    else:
                        j = random.randint(0, seen[drug] - 1)
                        if j < N:
                            res[drug][j] = snip
    return res


def classify(drug, snippets):
    numbered = "\n".join(f"[{i}] {s[:400]}" for i, s in enumerate(snippets))
    try:
        resp = _client().chat.completions.create(
            model=MODEL, temperature=0,
            messages=[{"role": "user", "content": PROMPT.format(drug=drug) + "\n\n" + numbered}])
        data = _parse_json(resp.choices[0].message.content) or {}
        return {r["idx"]: r for r in data.get("results", []) if isinstance(r, dict) and "idx" in r}
    except Exception as e:
        print(f"   {drug}: classify error {str(e)[:60]}")
        return {}


def main():
    raw = {r["intervention"]: int(r["distinct_authors"]) for r in
           csv.DictReader(open(COVERAGE, encoding="utf-8-sig")) if r["distinct_authors"] not in ("", None)}
    res = sample_corpus()

    audit = []

    def work(drug):
        snips = res[drug]
        if not snips:
            return drug, 0, 0
        cls = classify(drug, snips)
        on = sum(1 for i in range(len(snips)) if cls.get(i, {}).get("on_target"))
        for i, s in enumerate(snips):
            audit.append({"drug": drug, "on_target": cls.get(i, {}).get("on_target"),
                          "category": cls.get(i, {}).get("category", ""), "snippet": s[:300]})
        return drug, len(snips), on

    rows = []
    for drug, n, on in ThreadPoolExecutor(max_workers=6).map(work, VALIDATE):
        frac = on / n if n else 0.0
        rw = raw.get(drug, 0)
        rows.append({"intervention": drug, "n_sampled": n, "n_on_target": on,
                     "on_target_frac": round(frac, 2), "raw_authors": rw,
                     "effective_authors": int(rw * frac),
                     "control": "yes" if drug in ("fluvoxamine", "oxaloacetate", "naltrexone_ldn") else "",
                     "still_runnable": "yes" if rw * frac >= 50 else "NO (drops out)"})
    rows.sort(key=lambda r: -r["effective_authors"])
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["intervention", "n_sampled", "n_on_target", "on_target_frac",
                                          "raw_authors", "effective_authors", "control", "still_runnable"])
        w.writeheader(); w.writerows(rows)
    with open(SAMPLES, "w", encoding="utf-8") as f:
        for a in audit:
            f.write(json.dumps(a) + "\n")

    print(f"\n{'intervention':<24}{'sampled':>8}{'on-tgt':>8}{'frac':>6}{'raw':>7}{'eff':>7}  {'runnable?'}")
    for r in rows:
        tag = " (control)" if r["control"] else ""
        print(f"  {r['intervention']:<22}{r['n_sampled']:>8}{r['n_on_target']:>8}{r['on_target_frac']:>6}"
              f"{r['raw_authors']:>7}{r['effective_authors']:>7}  {r['still_runnable']}{tag}")
    print(f"\n-> {OUT}  (+ {SAMPLES} for audit)")


if __name__ == "__main__":
    main()
