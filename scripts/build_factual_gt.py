"""
build_factual_gt.py — a frozen factual gold from CROSS-LAB FRONTIER CONSENSUS (judgement ⑪).

The honest replacement for a single-Opus gold. A panel of four different-lab frontier models
(Opus/Anthropic, Gemini-3.1-Pro/Google, GPT-5.1/OpenAI, Grok-4.5/xAI) codes the 30 posts; where
>=3 of the 4 agree (semantically) on a value — or >=3 leave a field empty — that cell gets a
frozen gold. Where they split, the cell is CONTESTED and gets no gold (we don't fake an accuracy
number on a genuinely underdetermined field). Then every non-panel model is scored only on the
gold cells, per tier, and we report the contested rate as the irreducible ambiguity.

Byproduct: the Opus-dissent rate — how often the incumbent single-model gold was itself the
outlier against the cross-lab consensus.

Inputs:  j11_coding_runs.json (values + Opus gold), j11_frontier_panel_semantic.json (panel
         pairwise agreement), j11_rejudge.json (candidate-vs-Opus, used to score candidates
         against the consensus where Opus is in it).
Output:  data/validation/j11_factual_gt.json
"""
from __future__ import annotations
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path

DV = Path(__file__).resolve().parent.parent / "data" / "validation"

PANEL = ["anthropic/claude-opus-4.8", "google/gemini-3.1-pro-preview",
         "openai/gpt-5.1", "x-ai/grok-4.5"]
OPUS = "anthropic/claude-opus-4.8"
AGREE = {"equivalent", "model_subset"}

TIER = {
 "Tier-1": ["age","age_at_onset","infection_count","long_covid_duration_months","time_to_diagnosis",
   "symptom_duration","dosage","procedures","prior_infections","onset_trigger","location_country",
   "biomarker_results","dietary_interventions","vaccination_status","sex_gender","work_disability_status",
   "diagnosis_source","clinical_trial_participation","covid_wave","location_us_state","ethnicity"],
 "Tier-2": ["conditions","medications","alternative_treatments","mental_health","functional_status_tier",
   "activity_level","symptom_trajectory"],
 "Tier-3": ["social_impact","healthcare_costs","diagnostic_odyssey","doctor_dismissal","misdiagnosis",
   "healthcare_system","treatment_outcome","family_history","hormonal_events"]}
FT = {f: t for t, fs in TIER.items() for f in fs}


def pop(v):
    if v is None:
        return False
    if isinstance(v, list):
        return any(str(x).strip() and str(x).strip().lower() not in ("n/a", "none", "unknown") for x in v)
    return bool(str(v).strip()) and str(v).strip().lower() not in ("n/a", "none", "unknown")


def largest_agreeing_set(members, sid, field, mm):
    """Largest subset of `members` that is pairwise-agreeing (a clique on the equivalence graph)."""
    best = []
    # members is <=4, brute force all subsets from big to small
    for k in range(len(members), 1, -1):
        for sub in combinations(members, k):
            if all(mm.get((frozenset((a, b)), sid, field)) in AGREE for a, b in combinations(sub, 2)):
                return list(sub)
        if best:
            break
    return best


def main():
    cod = json.loads((DV / "j11_coding_runs.json").read_text(encoding="utf-8"))
    FIELDS = cod["manifest"]["fields"]
    codings = defaultdict(dict)
    for c in cod["codings"]:
        codings[c["model"]][c["sample_id"]] = c["fields"]
    codings[OPUS] = {g["sample_id"]: g["fields"] for g in cod["gold"]}
    gold_src = codings[OPUS]
    SIDS = sorted(gold_src)

    ps = json.loads((DV / "j11_frontier_panel_semantic.json").read_text(encoding="utf-8"))["records"]
    mm = {}
    for r in ps:
        a, b = r["pair"].split("|")
        mm[(frozenset((a, b)), r["sample_id"], r["field"])] = r["verdict"]

    rj = json.loads((DV / "j11_rejudge.json").read_text(encoding="utf-8"))["verdicts"]
    vg = {(r["model"], r["sample_id"], r["field"]): r["verdict"] for r in rj}

    # ---- build the consensus gold ----
    gt = {}                        # (sid,field) -> {"kind": value|absent|contested, "consensus": [models], "opus_in": bool}
    for s in SIDS:
        for f in FIELDS:
            populated = [m for m in PANEL if pop(codings[m].get(s, {}).get(f))]
            absent = [m for m in PANEL if not pop(codings[m].get(s, {}).get(f))]
            if len(populated) >= 3:
                clique = largest_agreeing_set(populated, s, f, mm)
                if len(clique) >= 3:
                    gt[(s, f)] = {"kind": "value", "consensus": clique, "opus_in": OPUS in clique}
                    continue
            if len(absent) >= 3:
                gt[(s, f)] = {"kind": "absent", "consensus": absent, "opus_in": OPUS in absent}
                continue
            gt[(s, f)] = {"kind": "contested", "consensus": [], "opus_in": False}

    # ---- GT coverage + Opus-dissent, per tier ----
    cov = defaultdict(lambda: {"value": 0, "absent": 0, "contested": 0})
    opus_dissent = defaultdict(lambda: [0, 0])   # tier -> [dissent, value_cells]
    for (s, f), g in gt.items():
        t = FT[f]; cov[t][g["kind"]] += 1
        if g["kind"] == "value":
            opus_dissent[t][1] += 1
            if not g["opus_in"]:
                opus_dissent[t][0] += 1

    # ---- score candidates (non-panel) on value-gold cells where Opus is in the consensus ----
    candidates = [m for m in codings if m not in PANEL]
    def score(m):
        per = defaultdict(lambda: [0, 0])    # tier -> [correct, n]
        for (s, f), g in gt.items():
            if g["kind"] != "value" or not g["opus_in"]:
                continue                      # proxy candidate-vs-gold via candidate-vs-Opus (valid only when Opus in consensus)
            if not pop(codings[m].get(s, {}).get(f)):
                continue                      # candidate didn't populate -> not a value-accuracy cell (recall handled elsewhere)
            v = vg.get((m, s, f))
            if v is None:
                continue
            t = FT[f]; per[t][1] += 1; per[t][0] += (v in AGREE)
        return {t: (per[t][0] / per[t][1] if per[t][1] else None, per[t][1]) for t in TIER}

    scores = {m.split("/")[-1]: score(m) for m in candidates}

    out = {
        "panel": PANEL, "n_posts": len(SIDS),
        "coverage": {t: dict(cov[t]) for t in TIER},
        "opus_dissent": {t: {"dissent": opus_dissent[t][0], "value_cells": opus_dissent[t][1],
                             "rate": (opus_dissent[t][0] / opus_dissent[t][1] if opus_dissent[t][1] else None)}
                         for t in TIER},
        "candidate_accuracy": scores,
        "note": "gold = >=3 of 4 cross-lab frontier models agree (value) or >=3 leave empty (absent); "
                "else contested (no gold). candidate accuracy scored on value-gold cells where Opus is in "
                "the consensus, via the candidate-vs-Opus semantic verdict.",
    }
    (DV / "j11_factual_gt.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    P = print
    P(f"=== FACTUAL GT from cross-lab frontier consensus ({len(SIDS)} posts) ===")
    P("\nGT coverage — how much of the schema even HAS a knowable answer:")
    P(f"  {'tier':7} {'value-gold':>10} {'absent-gold':>11} {'contested':>10} {'gold%':>7}")
    for t in TIER:
        c = cov[t]; tot = c["value"] + c["absent"] + c["contested"]; goldpct = (c["value"] + c["absent"]) / tot
        P(f"  {t:7} {c['value']:>10} {c['absent']:>11} {c['contested']:>10} {goldpct:>7.0%}")
    P("\nOpus-dissent — how often the incumbent single-model gold was the OUTLIER vs cross-lab consensus:")
    for t in TIER:
        od = opus_dissent[t]
        if od[1]:
            P(f"  {t}: {od[0]}/{od[1]} value-gold cells = {od[0]/od[1]:.0%}")
    P("\nCandidate TRUE accuracy vs consensus gold (value cells, Opus in consensus):")
    P(f"  {'model':26} {'Tier-1':>8} {'Tier-2':>8} {'Tier-3':>8}")
    for m in sorted(scores, key=lambda m: -(scores[m]['Tier-1'][0] or 0)):
        sc = scores[m]
        def fmt(t): a, n = sc[t]; return f"{a:.0%}({n})" if a is not None else "  -  "
        P(f"  {m:26} {fmt('Tier-1'):>8} {fmt('Tier-2'):>8} {fmt('Tier-3'):>8}")
    P(f"\nWrote {DV/'j11_factual_gt.json'}")


if __name__ == "__main__":
    main()
