"""
analyze_cheap_consensus.py — the deployable question: can 2-3 CHEAP cross-lab models,
consensus-gated, with a judge panel for the leftovers, code variables reliably?

Two analyses, both from already-collected data:

  PART A — blind-spot cross-check (gold-quirk vs genuine error).
    On cells where >=50% of the 22 models disagree with Opus-gold, do the models AGREE
    WITH EACH OTHER (semantically)?  If yes, the gold is the outlier (quirk), not the models.

  PART B — cheap cross-lab consensus + judge-panel architecture.
    Producers = 3 cheap cross-lab models {deepseek-v4-flash (DeepSeek), gemini-3.1-flash-lite
    (Google), gpt-5-mini (OpenAI)}.  Per (post,field) cell:
      * >=2 agree on a value (semantically)  -> ACCEPT the consensus value
      * all 3 leave it empty                 -> ACCEPT absent
      * otherwise (contested)                -> ESCALATE to a judge/panel
    Measures coverage, accuracy vs gold, escalation rate, cost — overall and per tier — and
    compares to each producer solo and to the best single model (grok-4.5).

Inputs:  j11_coding_runs.json (raw values + Opus gold), j11_rejudge.json (model-vs-gold
         semantic verdicts), j11_cheap_consensus_semantic.json (model-vs-model semantic).
Output:  data/validation/j11_cheap_arch.json  {partA, partB, examples, manifest}
"""
from __future__ import annotations
import json
from collections import defaultdict, Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DV = ROOT / "data" / "validation"

TRIO = ["deepseek/deepseek-v4-flash", "google/gemini-3.1-flash-lite", "openai/gpt-5-mini"]
STRONG = "x-ai/grok-4.5"
GOLD = "anthropic/claude-opus-4.8"

TIER = {
 "Tier-1": ["age","age_at_onset","infection_count","long_covid_duration_months","time_to_diagnosis",
            "symptom_duration","dosage","procedures","prior_infections","onset_trigger","location_country",
            "biomarker_results","dietary_interventions","vaccination_status","sex_gender",
            "work_disability_status","diagnosis_source","clinical_trial_participation","covid_wave",
            "location_us_state","ethnicity"],
 "Tier-2": ["conditions","medications","alternative_treatments","mental_health","functional_status_tier",
            "activity_level","symptom_trajectory"],
 "Tier-3": ["social_impact","healthcare_costs","diagnostic_odyssey","doctor_dismissal","misdiagnosis",
            "healthcare_system","treatment_outcome","family_history","hormonal_events"],
}
FT = {f: t for t, fs in TIER.items() for f in fs}


def pop(v):
    if v is None:
        return False
    if isinstance(v, list):
        return any(str(x).strip() and str(x).strip().lower() not in ("n/a", "none", "unknown") for x in v)
    return bool(str(v).strip()) and str(v).strip().lower() not in ("n/a", "none", "unknown")


def main():
    cod = json.loads((DV / "j11_coding_runs.json").read_text(encoding="utf-8"))
    FIELDS = cod["manifest"]["fields"]
    codings = defaultdict(dict)
    for c in cod["codings"]:
        codings[c["model"]][c["sample_id"]] = c["fields"]
    gold = {g["sample_id"]: g["fields"] for g in cod["gold"]}
    SIDS = sorted(gold)

    # model-vs-gold semantic verdicts (co-populated only)
    rj = json.loads((DV / "j11_rejudge.json").read_text(encoding="utf-8"))["verdicts"]
    vg = {}                                   # (model, sid, field) -> verdict vs gold
    for r in rj:
        vg[(r["model"], r["sample_id"], r["field"])] = r["verdict"]

    # model-vs-model semantic verdicts (co-populated only), symmetric lookup
    ps = json.loads((DV / "j11_cheap_consensus_semantic.json").read_text(encoding="utf-8"))["records"]
    mm = {}                                   # frozenset({a,b}), sid, field -> verdict
    for r in ps:
        a, b = r["pair"].split("|")
        mm[(frozenset((a, b)), r["sample_id"], r["field"])] = r["verdict"]

    AGREE = {"equivalent"}                     # strict agreement
    AGREE_L = {"equivalent", "model_subset"}   # lenient (partial-overlap counts)

    # ============ PART A — blind-spot cross-check ============
    # per cell, fraction of the 22 models "different" from gold
    cell_models = defaultdict(list)            # (sid,field) -> [verdict...]
    for (m, s, f), v in vg.items():
        cell_models[(s, f)].append(v)
    FOUR = TRIO + [STRONG]
    partA_cells = []
    for (s, f), verds in cell_models.items():
        n = len(verds)
        if n < 8:
            continue
        frac_diff = sum(v == "different" for v in verds) / n
        # mutual agreement among the 4 semantic-judged models on this cell
        pair_verds = [mm[(frozenset(p), s, f)] for p in combinations(FOUR, 2)
                      if (frozenset(p), s, f) in mm]
        mutual = (sum(v in AGREE_L for v in pair_verds) / len(pair_verds)) if pair_verds else None
        partA_cells.append({"sid": s, "field": f, "tier": FT[f], "frac_diff_vs_gold": frac_diff,
                            "n_models": n, "mutual_agree": mutual, "n_pairs": len(pair_verds)})

    blind = [c for c in partA_cells if c["frac_diff_vs_gold"] >= 0.5 and c["mutual_agree"] is not None]
    non_blind = [c for c in partA_cells if c["frac_diff_vs_gold"] < 0.5 and c["mutual_agree"] is not None]
    # split blind-spot cells by whether the judged models agree with EACH OTHER
    quirk = [c for c in blind if c["mutual_agree"] >= 0.66]     # models agree, gold is the outlier
    genuine = [c for c in blind if c["mutual_agree"] < 0.34]    # models scatter -> genuinely hard
    mid = [c for c in blind if 0.34 <= c["mutual_agree"] < 0.66]

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else float("nan")

    partA = {
        "n_cells": len(partA_cells),
        "n_blind": len(blind), "n_non_blind": len(non_blind),
        "mutual_agree_blind": mean([c["mutual_agree"] for c in blind]),
        "mutual_agree_non_blind": mean([c["mutual_agree"] for c in non_blind]),
        "quirk_share": len(quirk) / len(blind) if blind else float("nan"),
        "genuine_share": len(genuine) / len(blind) if blind else float("nan"),
        "mid_share": len(mid) / len(blind) if blind else float("nan"),
        "n_quirk": len(quirk), "n_genuine": len(genuine), "n_mid": len(mid),
    }

    # illustrative gold-quirk examples: models agree with each other, gold differs
    ex = []
    for c in sorted(quirk, key=lambda c: -c["frac_diff_vs_gold"])[:12]:
        s, f = c["sid"], c["field"]
        gv = gold[s][f]
        mvals = {m.split("/")[-1]: codings[m].get(s, {}).get(f) for m in FOUR}
        mvals = {k: v for k, v in mvals.items() if pop(v)}
        ex.append({"field": f, "tier": c["tier"], "frac_diff": round(c["frac_diff_vs_gold"], 2),
                   "gold": gv, "models_agree_on": mvals})

    # ============ PART B — cheap cross-lab consensus architecture ============
    def trio_consensus(s, f, agree_set):
        """return ('value', winning_model) | ('absent', None) | ('escalate', None)."""
        popped = [m for m in TRIO if pop(codings[m].get(s, {}).get(f))]
        # any cross-lab pair that agrees on a value?
        for a, b in combinations(TRIO, 2):
            if a in popped and b in popped:
                v = mm.get((frozenset((a, b)), s, f))
                if v in agree_set:
                    return ("value", a)   # a's value == b's value semantically; pick a as representative
        if not popped:
            return ("absent", None)
        return ("escalate", None)

    def eval_arch(agree_set):
        by_tier = defaultdict(lambda: Counter())
        rows = defaultdict(lambda: Counter())   # 'overall'
        gold_pop_cells = defaultdict(lambda: Counter())  # recall universe per tier
        for s in SIDS:
            for f in FIELDS:
                t = FT[f]
                gp = pop(gold[s].get(f))
                dec, rep = trio_consensus(s, f, agree_set)
                bt = by_tier[t]; ov = rows["overall"]
                bt["total"] += 1; ov["total"] += 1
                if gp:
                    bt["gold_pop"] += 1; ov["gold_pop"] += 1
                if dec == "value":
                    bt["accept_value"] += 1; ov["accept_value"] += 1
                    if gp:
                        v = vg.get((rep, s, f))
                        ok = v in ("equivalent", "model_subset")
                        bt["val_correct" if ok else "val_wrong"] += 1
                        ov["val_correct" if ok else "val_wrong"] += 1
                        bt["recovered" if ok else "recovered_wrong"] += 1
                        ov["recovered" if ok else "recovered_wrong"] += 1
                    else:
                        bt["overextract"] += 1; ov["overextract"] += 1   # gold empty, trio asserted
                elif dec == "absent":
                    bt["accept_absent"] += 1; ov["accept_absent"] += 1
                    if gp:
                        bt["miss"] += 1; ov["miss"] += 1                  # gold had value, trio empty
                    else:
                        bt["true_absent"] += 1; ov["true_absent"] += 1
                else:
                    bt["escalate"] += 1; ov["escalate"] += 1
                    if gp:
                        bt["escalate_goldpop"] += 1; ov["escalate_goldpop"] += 1
        return rows["overall"], by_tier

    ov, by_tier = eval_arch(AGREE)
    ov_l, by_tier_l = eval_arch(AGREE_L)

    def summarize(c):
        tot = c["total"]
        auto = c["accept_value"] + c["accept_absent"]
        auto_correct = c["val_correct"] + c["true_absent"]
        auto_wrong = c["val_wrong"] + c["overextract"] + c["miss"]
        # value-consensus accuracy on gold-populated cells (the covariate-relevant number)
        vc_goldpop = c["val_correct"] + c["val_wrong"]
        return {
            "total": tot,
            "coverage": auto / tot,
            "auto_accuracy": auto_correct / auto if auto else float("nan"),
            "escalation_rate": c["escalate"] / tot,
            "accept_value": c["accept_value"], "accept_absent": c["accept_absent"], "escalate": c["escalate"],
            "value_consensus_error": (c["val_wrong"] / vc_goldpop) if vc_goldpop else float("nan"),
            "n_value_consensus_goldpop": vc_goldpop,
            "overextract": c["overextract"], "miss": c["miss"], "true_absent": c["true_absent"],
            "gold_pop": c["gold_pop"],
            # of the gold-populated (covariate) cells: recovered / missed / escalated
            "recall_recovered": c["val_correct"] / c["gold_pop"] if c["gold_pop"] else float("nan"),
            "recall_missed": c["miss"] / c["gold_pop"] if c["gold_pop"] else float("nan"),
            "recall_escalated": c["escalate_goldpop"] / c["gold_pop"] if c["gold_pop"] else float("nan"),
            "recall_wrongvalue": c["val_wrong"] / c["gold_pop"] if c["gold_pop"] else float("nan"),
        }

    partB = {
        "trio": TRIO,
        "strict": {"overall": summarize(ov), "tiers": {t: summarize(by_tier[t]) for t in TIER}},
        "lenient": {"overall": summarize(ov_l), "tiers": {t: summarize(by_tier_l[t]) for t in TIER}},
    }

    # ---- baselines: each producer solo, and the best single model (grok-4.5) — value error vs gold ----
    def solo_stats(m):
        diff = tot = 0
        over = under = 0
        per_tier = defaultdict(lambda: [0, 0])   # tier -> [diff, co]
        for s in SIDS:
            for f in FIELDS:
                mp = pop(codings[m].get(s, {}).get(f)); gp = pop(gold[s].get(f))
                if mp and gp:
                    tot += 1
                    per_tier[FT[f]][1] += 1
                    if vg.get((m, s, f)) == "different":
                        diff += 1; per_tier[FT[f]][0] += 1
                elif mp and not gp:
                    over += 1
                elif gp and not mp:
                    under += 1
        return {"model": m.split("/")[-1], "value_error": diff / tot if tot else float("nan"),
                "n_co": tot, "overextract_cells": over, "underextract_cells": under,
                "tier_error": {t: (per_tier[t][0] / per_tier[t][1] if per_tier[t][1] else float("nan"))
                               for t in TIER}}

    baselines = [solo_stats(m) for m in TRIO + [STRONG]]
    # mean solo cheap error per tier
    solo_tier_err = {t: mean([b["tier_error"][t] for b in baselines[:3]]) for t in TIER}

    # ---- recommended tier-differentiated policy rollup ----
    # Tier-1: cheap consensus auto-accepts value+absent; contested -> judge
    # Tier-2: cheap consensus auto-accepts, but escalate contested (11% leak flagged)
    # Tier-3: cheap consensus for ABSENCE only; ALL populated-value cells -> judge (co-failure 38%)
    def policy_rollup():
        judge_calls = auto_cells = total = 0
        correct = wrong = 0
        for s in SIDS:
            for f in FIELDS:
                t = FT[f]; total += 1
                gp = pop(gold[s].get(f))
                dec, rep = trio_consensus(s, f, AGREE)
                if t == "Tier-3" and dec == "value":
                    judge_calls += 1                 # never trust cheap value-consensus on Tier-3
                    continue
                if dec == "escalate":
                    judge_calls += 1
                    continue
                auto_cells += 1
                if dec == "value":
                    ok = vg.get((rep, s, f)) in ("equivalent", "model_subset") if gp else False
                    correct += ok; wrong += (not ok)
                else:  # absent
                    correct += (not gp); wrong += gp
        return {"judge_call_rate": judge_calls / total, "auto_rate": auto_cells / total,
                "auto_accuracy": correct / auto_cells if auto_cells else float("nan"),
                "judge_calls": judge_calls, "total": total}
    policy = policy_rollup()

    # cross-lab consensus value error (strict) = P(different | >=2 cheap cross-lab agree on a populated, gold-populated cell)
    cc = partB["strict"]["overall"]["value_consensus_error"]
    solo_mean_err = mean([b["value_error"] for b in baselines[:3]])

    manifest = {
        "trio": TRIO, "strong_ref": STRONG, "gold": GOLD,
        "note": "consensus = >=2 of 3 cross-lab cheap models agree (semantic, Opus judge). "
                "value-consensus error is measured only on gold-populated cells via the model-vs-gold verdict "
                "of an agreeing member; over/under-extraction measured deterministically by presence.",
        "solo_mean_value_error": solo_mean_err, "consensus_value_error": cc,
    }

    out = {"manifest": manifest, "partA": partA, "partA_examples": ex,
           "partB": partB, "baselines": baselines, "solo_tier_err": solo_tier_err, "policy": policy}
    (DV / "j11_cheap_arch.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    # ---- console summary ----
    P = print
    P("\n===== PART A — blind-spot cross-check =====")
    P(f"cells analysed: {partA['n_cells']}  |  blind-spot (>=50% of models differ from gold): {partA['n_blind']}")
    P(f"mutual agreement AMONG the 4 judged models:  blind-spot {partA['mutual_agree_blind']:.0%}  "
      f"vs non-blind {partA['mutual_agree_non_blind']:.0%}")
    P(f"  of blind-spot cells: {partA['quirk_share']:.0%} GOLD-QUIRK (models agree >=66% w/ each other), "
      f"{partA['genuine_share']:.0%} genuine scatter, {partA['mid_share']:.0%} mixed")
    P(f"  (n: quirk {partA['n_quirk']}, genuine {partA['n_genuine']}, mid {partA['n_mid']})")
    P("\n  gold-quirk examples (models agree with each other, gold differs):")
    for e in ex[:6]:
        P(f"   [{e['tier']}] {e['field']}: gold={e['gold']}  ||  models={e['models_agree_on']}")

    P("\n===== PART B — cheap cross-lab consensus + judge panel =====")
    o = partB["strict"]["overall"]
    P(f"3 cheap cross-lab producers: {', '.join(m.split('/')[-1] for m in TRIO)}")
    P(f"overall: coverage {o['coverage']:.0%} auto-resolved, auto-accuracy {o['auto_accuracy']:.1%}, "
      f"escalation {o['escalation_rate']:.0%}")
    P(f"cross-lab value-consensus error (gold-populated): {cc:.1%}  vs  solo cheap mean {solo_mean_err:.1%}  "
      f"(~{solo_mean_err/cc:.1f}x lower)" if cc else "")
    P(f"\n  per tier (strict consensus):")
    P(f"  {'tier':7} {'cover':>6} {'auto-acc':>9} {'escal':>6} {'val-cons-err':>12} {'recall(recov/miss/escal)':>26}")
    for t in TIER:
        st = partB["strict"]["tiers"][t]
        P(f"  {t:7} {st['coverage']:>6.0%} {st['auto_accuracy']:>9.1%} {st['escalation_rate']:>6.0%} "
          f"{st['value_consensus_error']:>12.1%} "
          f"{st['recall_recovered']:>7.0%}/{st['recall_missed']:.0%}/{st['recall_escalated']:.0%}")
    P("\n  solo producer value-error vs gold (overall | Tier-1 / Tier-2 / Tier-3):")
    for b in baselines:
        te = b["tier_error"]
        P(f"   {b['model']:26} {b['value_error']:.1%}  |  "
          f"{te['Tier-1']:.1%} / {te['Tier-2']:.1%} / {te['Tier-3']:.1%}")
    P("\n  CONSENSUS vs SOLO value-error by tier (the apples-to-apples win):")
    for t in TIER:
        ce = partB["strict"]["tiers"][t]["value_consensus_error"]; se = solo_tier_err[t]
        P(f"   {t}: cross-lab consensus {ce:.1%}  vs  solo cheap {se:.1%}  "
          f"(~{se/ce:.1f}x lower)" if ce else f"   {t}: consensus {ce}")
    P("\n===== RECOMMENDED tier-differentiated policy =====")
    P(f"  auto-resolved {policy['auto_rate']:.0%} of cells at {policy['auto_accuracy']:.1%} accuracy; "
      f"judge/panel called on {policy['judge_call_rate']:.0%} "
      f"(= Tier-1/2 contested + ALL Tier-3 populated-value cells)")
    P(f"\nWrote {DV/'j11_cheap_arch.json'}")


if __name__ == "__main__":
    main()
