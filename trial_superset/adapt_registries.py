"""Adapt non-CT.gov (ISRCTN) Long-COVID RCTs into CT.gov-shaped trials her pipeline can ingest.

Lever #1 (mine_registries.py) finds ISRCTN LC RCTs absent from CT.gov, but their records aren't
CT.gov JSON, so NATURAL can't read them. This adapter bridges that gap:

  ISRCTN registry record (design) + linked results paper (per-arm outcome)
      --LLM extract-->  a compact schema
      --clone a REAL CT.gov trial as a structural template, overwrite the semantic fields-->
      a CT.gov-shaped trial JSON that loads in her ClinicalTrial, passes check_trial, and whose
      Experiment reads the per-arm primary outcome as the label.

Cloning a real trial as the template guarantees every structurally-required field exists; we only
overwrite identification / conditions / design / arms / eligibility / status / results. Covariates
are NOT reliable for adapted trials (same limitation as papers-as-labels) and are neutralized.

Output: data/adapted_registries/<ISRCTN>.json + data/adapted_registries_manifest.csv
Run: PYTHONPATH=trial_superset trial_superset/.venv/Scripts/python.exe -m adapt_registries
"""

from __future__ import annotations

import copy
import csv
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

import requests

from build_augmented import synth_outcome_measure
from build_improved import terms_of, classify
from litlabels import europe_pmc
from litlabels.extract_labels import _client, MODEL, _parse_json, relevant_fulltext, _oa_pmcid
from run_study import build_cfg

MINED = "trial_superset/data/mined_registries.csv"
OUTDIR = "trial_superset/data/adapted_registries"
MANIFEST = "trial_superset/data/adapted_registries_manifest.csv"
TEMPLATE_POOL = "trial_superset/data/m2_outputs/long_covid/nct_reports"
ISRCTN_API = "https://www.isrctn.com/api/query/format/default"
ROLE2TYPE = {"experimental": "EXPERIMENTAL", "active_comparator": "ACTIVE_COMPARATOR",
             "active comparator": "ACTIVE_COMPARATOR", "placebo": "PLACEBO_COMPARATOR",
             "control": "PLACEBO_COMPARATOR"}

PROMPT = """You are given (1) an ISRCTN clinical-trial registry record and (2) the full text of its \
results paper, for a trial in Long COVID (post-acute sequelae of COVID-19). Extract a compact schema \
of the design and the per-arm PRIMARY outcome actually reported in the paper.

Return ONLY JSON:
{
 "is_extractable": true/false,        // false if the paper does not report a per-arm primary result
 "is_randomized": true/false,
 "enrolled_patients": true/false,     // true = patients (not healthy volunteers)
 "is_long_covid": true/false,
 "primary_outcome_title": "...",
 "unit_of_measure": "...",
 "outcome_kind": "continuous_mean" | "proportion" | "count",
 "higher_is_better": true/false,
 "result_public_date": "YYYY-MM-DD or YYYY-MM",
 "arms": [ {"label":"...", "role":"experimental|active_comparator|placebo",
            "intervention":"drug/therapy name", "n": integer, "value": number} ]
}
"value" = that arm's primary-outcome value (group MEAN for continuous_mean; rate in [0,1] for \
proportion; count for count). Include every arm. Set is_extractable=false unless you can give numeric \
n and value for at least the experimental and one comparator arm."""


def _tag(xml: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, re.S)
    return re.sub(r"<[^>]+>", " ", m.group(1)).strip() if m else ""


def fetch_isrctn(trial_id: str) -> str:
    r = requests.get(ISRCTN_API, params={"q": trial_id},
                     headers={"accept": "application/xml"}, timeout=60)
    return r.text if r.status_code == 200 else ""


def candidate_fulltexts(trial_id: str, source_papers: str) -> list[str]:
    """OA full texts to extract from: papers that cited this ISRCTN id, then an EPMC id search."""
    pmcids, seen = [], set()
    for p in (source_papers or "").split(";"):
        if p.startswith("PMC") and p not in seen:
            pmcids.append(p); seen.add(p)
    for x in europe_pmc.search(f'"{trial_id}"', page_size=10).get("resultList", {}).get("result", []):
        pm = _oa_pmcid(x)
        if pm and pm not in seen:
            pmcids.append(pm); seen.add(pm)
    out = []
    for pm in pmcids[:6]:
        xml = europe_pmc.fulltext_xml("PMC", pm)
        if xml:
            out.append(relevant_fulltext(xml)[:40000])
    return out


def extract_schema(isrctn_xml: str, paper_text: str) -> dict | None:
    reg = "\n".join(f"{t}: {_tag(isrctn_xml, t)}" for t in
                    ("title", "studyDesign", "interventionType", "participantType", "condition",
                     "intervention", "primaryOutcome"))
    try:
        resp = _client().chat.completions.create(
            model=MODEL, temperature=0,
            messages=[{"role": "user", "content":
                       f"{PROMPT}\n\n=== ISRCTN RECORD ===\n{reg}\n\n=== RESULTS PAPER ===\n{paper_text}"}])
        return _parse_json(resp.choices[0].message.content)
    except Exception:
        return None


def build_ctgov(template: dict, trial_id: str, schema: dict) -> dict:
    """Clone the template and MUTATE specific fields (preserving every template-required field);
    build arm/outcome list items by copying a template item as the base so required keys survive."""
    j = copy.deepcopy(template)
    p = j["protocolSection"]
    date = (schema.get("result_public_date") or "").strip() or "2024-01"
    title = (schema.get("primary_outcome_title") or trial_id)[:120]

    idm = p.setdefault("identificationModule", {})
    idm["nctId"] = trial_id; idm["briefTitle"] = title; idm["officialTitle"] = title

    sm = p.setdefault("statusModule", {})
    sm["overallStatus"] = "COMPLETED"
    sm["completionDateStruct"] = {"date": date}
    sm["resultsFirstPostDateStruct"] = {"date": date}
    sm.setdefault("statusVerifiedDate", date)

    p.setdefault("designModule", {}).setdefault("designInfo", {})
    p["designModule"]["designInfo"]["allocation"] = "RANDOMIZED"
    p["designModule"]["designInfo"]["interventionModel"] = "PARALLEL"

    p.setdefault("conditionsModule", {})["conditions"] = ["Post-COVID-19 Condition"]
    p.setdefault("eligibilityModule", {})["healthyVolunteers"] = False
    p.setdefault("descriptionModule", {})["briefSummary"] = "Adapted from ISRCTN registry + results paper."

    # build arm/intervention/outcome items from a template item as base (keeps required keys)
    aim = p.setdefault("armsInterventionsModule", {})
    base_arm = (aim.get("armGroups") or [{}])[0]
    base_iv = (aim.get("interventions") or [{}])[0]
    armgroups, interventions = [], []
    for a in schema.get("arms", []):
        atype = ROLE2TYPE.get((a.get("role") or "").lower().strip(), "EXPERIMENTAL")
        iv = (a.get("intervention") or "").strip()
        ag = copy.deepcopy(base_arm)
        ag.update({"label": a.get("label", ""), "type": atype, "interventionNames": [iv] if iv else []})
        ag.pop("interventionList", None)
        armgroups.append(ag)
        if iv:
            ivd = copy.deepcopy(base_iv)
            ivd.update({"type": "OTHER" if atype == "PLACEBO_COMPARATOR" else "DRUG",
                        "name": iv, "armGroupLabels": [a.get("label", "")]})
            interventions.append(ivd)
    p["armsInterventionsModule"]["armGroups"] = armgroups
    p["armsInterventionsModule"]["interventions"] = interventions

    om_mod = p.setdefault("outcomesModule", {})
    base_out = (om_mod.get("primaryOutcomes") or [{}])[0]
    po = copy.deepcopy(base_out); po["measure"] = title
    om_mod["primaryOutcomes"] = [po]

    if "contactsLocationsModule" in p:           # neutralize template covariate (location) leakage
        p["contactsLocationsModule"]["locations"] = []

    om = synth_outcome_measure({"arms": [{"title": a.get("label"), "n": a.get("n"), "value": a.get("value")}
                                         for a in schema.get("arms", [])],
                                "primary_outcome_title": title,
                                "unit_of_measure": schema.get("unit_of_measure", "")})
    j["resultsSection"] = {"participantFlowModule": {},
                           "baselineCharacteristicsModule": {"groups": [], "measures": []},
                           "outcomeMeasuresModule": {"outcomeMeasures": [om] if om else []}}
    return j


def validate(trial_id: str, filters) -> tuple[bool, bool]:
    """(passes check_trial, Experiment yields a label). Reads OUTDIR/nct_reports/<id>.json."""
    from naturalv2.clinical_trial import ClinicalTrial
    from naturalv2.utils import check_trial
    from naturalv2.experiment import Experiment
    path = os.path.join(OUTDIR, "nct_reports", f"{trial_id}.json")
    try:
        t = ClinicalTrial.from_json_file(path)
    except Exception:
        return (False, False)
    if not check_trial(t, filters)[1]:
        return (False, False)
    try:
        exp = Experiment(OUTDIR, trial_id, "noparallel_notbinary", "completed", require_binary_endpoint=False)
        return (True, len(exp.avg_potential_outcomes) > 0)
    except Exception:
        return (True, False)


def main() -> None:
    from naturalv2.cli.create_study import resolve_trial_filters
    filters = resolve_trial_filters(build_cfg("x"))
    os.makedirs(os.path.join(OUTDIR, "nct_reports"), exist_ok=True)

    # structural template: the first long_covid trial that passes check_trial
    from naturalv2.clinical_trial import ClinicalTrial
    from naturalv2.utils import check_trial
    template = None
    for f in sorted(os.listdir(TEMPLATE_POOL)):
        if f.endswith(".json"):
            tt = ClinicalTrial.from_json_file(os.path.join(TEMPLATE_POOL, f))
            if check_trial(tt, filters)[1]:
                template = json.load(open(os.path.join(TEMPLATE_POOL, f), encoding="utf-8")); break
    print(f"template: {template['protocolSection']['identificationModule']['nctId']}")

    usable = [r for r in csv.DictReader(open(MINED, encoding="utf-8-sig"))
              if r["registry"] == "ISRCTN" and r.get("usable") == "True"]
    print(f"adapting {len(usable)} usable ISRCTN LC RCTs ({MODEL})\n")

    def work(r):
        tid = r["trial_id"]
        xml = fetch_isrctn(tid)
        for text in candidate_fulltexts(tid, r.get("source_papers", "")):
            schema = extract_schema(xml, text)
            if schema and schema.get("is_extractable") and schema.get("is_long_covid") and schema.get("arms"):
                path = os.path.join(OUTDIR, "nct_reports", f"{tid}.json")
                json.dump(build_ctgov(template, tid, schema), open(path, "w", encoding="utf-8"))
                ok, lab = validate(tid, filters)
                drug = any("drug" in (a.get("intervention", "") or "").lower() or
                           classify([a.get("intervention", "")], "long_covid") for a in schema["arms"])
                return {"trial_id": tid, "linked": True, "extractable": True, "passes_check_trial": ok,
                        "has_label": lab, "n_arms": len(schema["arms"]),
                        "primary_outcome": schema.get("primary_outcome_title", "")[:60],
                        "date": schema.get("result_public_date", ""),
                        "intervention_type": r.get("intervention_type", "")}
        return {"trial_id": tid, "linked": bool(xml), "extractable": False, "passes_check_trial": False,
                "has_label": False, "intervention_type": r.get("intervention_type", "")}

    rows = list(ThreadPoolExecutor(max_workers=5).map(work, usable))
    cols = ["trial_id", "linked", "extractable", "passes_check_trial", "has_label", "n_arms",
            "intervention_type", "date", "primary_outcome"]
    with open(MANIFEST, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)

    good = [r for r in rows if r.get("has_label")]
    print(f"\nadapted + VALIDATED (loads, passes check_trial, has label): {len(good)} / {len(usable)}")
    for r in good:
        print(f"   {r['trial_id']} [{r['intervention_type']:12s}] {r['n_arms']} arms, {r['date']} | {r['primary_outcome']}")
    print(f"\n-> {OUTDIR}/ + {MANIFEST}")
    print("These are CT.gov-shaped and ingest-ready; fold into the long_covid Study via build_augmented (next step).")


if __name__ == "__main__":
    main()
