"""Classify each intervention into drug_class + drug_accessibility (self-experimentable).

drug_accessibility is the single most NATURAL-relevant trial flag: a drug patients can't obtain
or self-administer (IVIG infusion, a device, a procedure) has little/no Reddit signal regardless
of efficacy. drug_class supports cross-trial generalization + mechanism alignment.

Collects distinct non-placebo DRUG/BIOLOGICAL/DIETARY_SUPPLEMENT intervention names across the
augmented set and classifies each once (LLM, cached). Output: data/drug_classification.csv.

Run: PYTHONPATH=trial_superset trial_superset/.venv/Scripts/python.exe -m drug_classify
"""

from __future__ import annotations

import csv
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from litlabels import cache
from litlabels.extract_labels import _client, MODEL, _parse_json

cache.CACHE_DIR = Path("trial_superset/data/.cache")
DATA = "trial_superset/data"
MANIFEST = f"{DATA}/training_set_manifest_augmented.csv"
LABELED = f"{DATA}/m3_labeled"
OUT = f"{DATA}/drug_classification.csv"
_V = 1

DRUG_TYPES = {"DRUG", "BIOLOGICAL", "DIETARY_SUPPLEMENT"}
CLASSES = ("immunomodulator, antiviral, autonomic_agent, glp1_agonist, antibiotic, antihistamine, "
           "antidepressant, anticoagulant, corticosteroid, jak_inhibitor, analgesic, "
           "supplement_nutraceutical, hormone_metabolic, other")
ACCESS = ("self_obtainable, prescription_oral, clinical_administered, behavioral_or_device")

PROMPT = """Classify this clinical-trial intervention.

INTERVENTION: {name}

Return ONLY JSON:
{{"drug_class": one of [{classes}],
  "drug_accessibility": one of [{access}]}}

Guidance:
- drug_class = mechanism/category. 'supplement_nutraceutical' for vitamins/supplements,
  'autonomic_agent' for pressors/beta-blockers/ivabradine/midodrine, 'hormone_metabolic' for
  GLP-1-adjacent/metabolic if not glp1_agonist, 'other' if none fit.
- drug_accessibility = can a patient realistically OBTAIN and SELF-administer it (=> Reddit signal)?
  - self_obtainable: OTC/supplement, or a repurposed oral Rx patients commonly get themselves
    (low-dose naltrexone, antihistamines, melatonin, common generics).
  - prescription_oral: needs a prescriber but is oral / taken at home.
  - clinical_administered: IV/infusion/injection/device/procedure done in a clinic (IVIG,
    monoclonals, plasmapheresis, devices, nerve blocks).
  - behavioral_or_device: behavioral therapy / exercise / rehab / a hardware device.
Output strictly valid JSON."""


def classify_one(name: str) -> dict:
    payload = {"name": name, "model": MODEL, "v": _V}
    cached = cache.get("m3/drug_classify", payload, 180 * 24 * 3600)
    if cached is not None:
        return cached
    msg = PROMPT.format(name=name[:120], classes=CLASSES, access=ACCESS)
    resp = _client().chat.completions.create(model=MODEL, temperature=0, max_tokens=120,
                                             messages=[{"role": "user", "content": msg}])
    out = _parse_json(resp.choices[0].message.content or "") or {}
    cache.put("m3/drug_classify", payload, out)
    return out


def gather() -> set[str]:
    names: set[str] = set()
    for m in csv.DictReader(open(MANIFEST, encoding="utf-8-sig")):
        sub = "nct_reports_test" if m["split"] == "test" else "nct_reports"
        p = os.path.join(LABELED, m["condition"], sub, f"{m['nct']}.json")
        if not os.path.exists(p):
            continue
        ivs = json.load(open(p, encoding="utf-8")).get("protocolSection", {}).get(
            "armsInterventionsModule", {}).get("interventions", []) or []
        for i in ivs:
            n = (i.get("name") or "").strip()
            if i.get("type") in DRUG_TYPES and n and "placebo" not in n.lower() and "sham" not in n.lower():
                names.add(n[:120])
    return names


def main() -> None:
    names = sorted(gather())
    print(f"{len(names)} distinct interventions to classify ({MODEL})")
    results = list(ThreadPoolExecutor(max_workers=8).map(lambda n: (n, classify_one(n)), names))
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["intervention", "drug_class", "drug_accessibility"])
        w.writeheader()
        for name, c in results:
            w.writerow({"intervention": name, "drug_class": c.get("drug_class", ""),
                        "drug_accessibility": c.get("drug_accessibility", "")})
    from collections import Counter
    print("drug_class:", dict(Counter(c.get("drug_class", "") for _, c in results)))
    print("drug_accessibility:", dict(Counter(c.get("drug_accessibility", "") for _, c in results)))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
