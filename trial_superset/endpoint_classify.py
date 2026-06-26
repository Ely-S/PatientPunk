"""Classify trial primary endpoints into domain / modality / self_reportable / instrument.

The signal NATURAL needs: is a training trial's endpoint the same KIND as the endpoint of the
test trial we're predicting? Corpus signal is patient self-report, so a fatigue/function PRO is
informative for predicting a fatigue trial; a lab/imaging biomarker is near-noise regardless of drug.

Collects the distinct endpoint strings (training result-outcomes from the sidecar + test trials'
registered primaries) and classifies each ONCE via LLM against a fixed taxonomy. Cached.
Output: data/endpoint_classification.csv  (endpoint_text -> domain, modality, self_reportable, instrument)

Run: PYTHONPATH=trial_superset trial_superset/.venv/Scripts/python.exe -m endpoint_classify
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
SIDECAR = f"{DATA}/labels_sidecar.csv"
MANIFEST = f"{DATA}/training_set_manifest_augmented.csv"
LABELED = f"{DATA}/m3_labeled"
OUT = f"{DATA}/endpoint_classification.csv"
_V = 1

DOMAINS = ("fatigue, functional_capacity, cognition, autonomic, pain, sleep, quality_of_life, "
           "mood_psych, respiratory, cardiovascular, immune_inflammatory, biomarker_lab, "
           "microbiologic, composite, other")
MODALITIES = "patient_reported, performance_test, physiologic, biomarker_lab, clinician_assessed, composite"

PROMPT = """Classify this clinical-trial PRIMARY ENDPOINT into a fixed taxonomy.

ENDPOINT: {text}

Return ONLY JSON:
{{"endpoint_domain": one of [{domains}],
  "endpoint_modality": one of [{modalities}],
  "self_reportable": "yes" | "partial" | "no",
  "instrument": "short canonical scale/test name if identifiable (FSS, RAND-36, SF-36, 6MWD, FIQ, OHQ, MoCA, VAS, PROMIS, ...) else null"}}

Guidance:
- endpoint_domain = the clinical construct measured. 'biomarker_lab' for labs/imaging, 'microbiologic'
  for pathogen detection, 'composite' for genuinely multi-domain composite scores.
- endpoint_modality = HOW it's measured: patient_reported (questionnaire/PRO), performance_test
  (6MWD, exercise/CPET), physiologic (BP, HR, tilt-table), biomarker_lab (blood/imaging), clinician_assessed.
- self_reportable = would a patient PERCEIVE and post about a change in this? symptom PROs -> yes;
  functional/performance -> partial; labs/imaging/physiologic -> no.
Output strictly valid JSON."""


def classify_one(text: str) -> dict:
    payload = {"text": text, "model": MODEL, "v": _V}
    cached = cache.get("m3/endpoint_classify", payload, 180 * 24 * 3600)
    if cached is not None:
        return cached
    msg = PROMPT.format(text=text[:400], domains=DOMAINS, modalities=MODALITIES)
    resp = _client().chat.completions.create(model=MODEL, temperature=0, max_tokens=300,
                                             messages=[{"role": "user", "content": msg}])
    out = _parse_json(resp.choices[0].message.content or "") or {}
    cache.put("m3/endpoint_classify", payload, out)
    return out


def gather_endpoints() -> set[str]:
    texts: set[str] = set()
    # training endpoints: the result outcome titles in the sidecar
    if os.path.exists(SIDECAR):
        for r in csv.DictReader(open(SIDECAR, encoding="utf-8-sig")):
            if r["outcome"].strip():
                texts.add(r["outcome"].strip())
    # test endpoints: registered primary outcomes from the test trial JSONs
    for m in csv.DictReader(open(MANIFEST, encoding="utf-8-sig")):
        if m["split"] != "test":
            continue
        p = os.path.join(LABELED, m["condition"], "nct_reports_test", f"{m['nct']}.json")
        if not os.path.exists(p):
            continue
        ps = json.load(open(p, encoding="utf-8")).get("protocolSection", {})
        for o in ps.get("outcomesModule", {}).get("primaryOutcomes", []) or []:
            meas = (o.get("measure") or "").strip()
            if meas:
                texts.add(meas[:120])
    return texts


def main() -> None:
    texts = sorted(gather_endpoints())
    print(f"{len(texts)} distinct endpoints to classify ({MODEL})")
    results = list(ThreadPoolExecutor(max_workers=8).map(lambda t: (t, classify_one(t)), texts))
    cols = ["endpoint_text", "endpoint_domain", "endpoint_modality", "self_reportable", "instrument"]
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for text, c in results:
            w.writerow({"endpoint_text": text,
                        "endpoint_domain": c.get("endpoint_domain", ""),
                        "endpoint_modality": c.get("endpoint_modality", ""),
                        "self_reportable": c.get("self_reportable", ""),
                        "instrument": c.get("instrument") or ""})
    from collections import Counter
    dom = Counter(c.get("endpoint_domain", "") for _, c in results)
    sr = Counter(c.get("self_reportable", "") for _, c in results)
    print("by domain:", dict(dom))
    print("by self_reportable:", dict(sr))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
