"""
analyze_between_model_sentiment.py — WHERE do the 22 models disagree on sentiment, and does
between-model agreement mean anything?

Panel alpha 0.64 says "moderate disagreement" but not what kind. This asks the questions that
decide whether cross-model sentiment agreement is usable as a reliability signal the way ⑪'s
cross-lab consensus was:

  1. When two models disagree, is it POSITIVE<->NEGATIVE (the effectiveness call) or a fuzzy
     boundary (pos/neutral, neutral/mixed)?  -- hard disagreement vs benign granularity.
  2. Per item: how concentrated is the model vote? what share of items are contested?
  3. Directional bias: on the items Polina calls NEGATIVE/NEUTRAL, do the models still skew
     positive?  -- if yes, agreement encodes the shared prompt lean, not correctness.
  4. Does high model-consensus predict agreement with Polina? (does the ⑪ filter transfer?)
  5. Is the disagreement lab-structured (same-lab agree more)?

Reads data/validation/j78_classify_runs.json.
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DV = ROOT / "data" / "validation"

LAB = lambda m: m.split("/")[0]
SH = lambda m: m.split("/")[-1]
DIR = {"positive": "+", "negative": "-", "neutral": "0", "mixed": "0"}   # direction bucket


def mode(xs):
    xs = [x for x in xs if x]
    return Counter(xs).most_common(1)[0][0] if xs else None


def main():
    d = json.loads((DV / "j78_classify_runs.json").read_text(encoding="utf-8"))
    R = d["results"]
    POL = {(p["sample_id"], p["drug"]): p.get("sentiment") for p in d["polina"]}
    # collapse 3 runs -> per-model modal call
    byk = defaultdict(list)
    for r in R:
        if not r["parse_failed"] and r["sentiment"]:
            byk[(r["model"], r["sample_id"], r["drug"])].append(r["sentiment"])
    call = {k: mode(v) for k, v in byk.items()}
    models = sorted({k[0] for k in call})
    items = sorted({(k[1], k[2]) for k in call})

    # ---------- 1. pairwise disagreement confusion ----------
    pair_conf = Counter()
    n_pairs_total = n_pairs_disagree = 0
    for (s, dr) in items:
        present = [(m, call[(m, s, dr)]) for m in models if (m, s, dr) in call]
        for (ma, ca), (mb, cb) in combinations(present, 2):
            n_pairs_total += 1
            if ca != cb:
                n_pairs_disagree += 1
                pair_conf[tuple(sorted((ca, cb)))] += 1
    posneg = pair_conf[("negative", "positive")]
    hard = posneg
    boundary = n_pairs_disagree - hard

    # ---------- 2. per-item vote concentration ----------
    conc = []
    contested_dir = contested_bound = 0
    for (s, dr) in items:
        votes = [call[(m, s, dr)] for m in models if (m, s, dr) in call]
        if not votes:
            continue
        c = Counter(votes); top = c.most_common(1)[0][1]; share = top / len(votes)
        # does the item contain BOTH a positive and a negative vote? (direction contested)
        dirs = {DIR[v] for v in votes}
        conc.append((s, dr, share, len(votes), "+" in dirs and "-" in dirs))
        if share < 0.6:
            if "+" in dirs and "-" in dirs:
                contested_dir += 1
            else:
                contested_bound += 1
    strong = sum(1 for *_, sh, n, _ in [(x[0], x[1], x[2], x[3], x[4]) for x in conc] if sh >= 0.8)
    ge80 = sum(1 for x in conc if x[2] >= 0.8)
    lt60 = sum(1 for x in conc if x[2] < 0.6)
    dir_split = sum(1 for x in conc if x[4])   # any item with both a + and a - vote

    # ---------- 3. directional bias vs Polina ----------
    def model_dist_when_polina(label):
        cnt = Counter()
        for (s, dr) in items:
            if POL.get((s, dr)) != label:
                continue
            for m in models:
                v = call.get((m, s, dr))
                if v:
                    cnt[v] += 1
        tot = sum(cnt.values())
        return {k: cnt[k] / tot for k in ("positive", "negative", "neutral", "mixed")} if tot else {}, tot

    on_neg, n_neg = model_dist_when_polina("negative")
    on_neu, n_neu = model_dist_when_polina("neutral")
    on_pos, n_pos = model_dist_when_polina("positive")

    # overall positive rate: models vs Polina
    allmodel = Counter(v for v in call.values() if v)
    m_posrate = allmodel["positive"] / sum(allmodel.values())
    pol_cnt = Counter(v for v in POL.values() if v)
    p_posrate = pol_cnt["positive"] / sum(pol_cnt.values()) if pol_cnt else float("nan")

    # ---------- 4. does model-consensus predict Polina agreement? ----------
    bins = {"strong (>=80%)": [], "mod (60-80%)": [], "contested (<60%)": []}
    for (s, dr) in items:
        if (s, dr) not in POL or not POL[(s, dr)]:
            continue
        votes = [call[(m, s, dr)] for m in models if (m, s, dr) in call]
        if not votes:
            continue
        c = Counter(votes); modal, top = c.most_common(1)[0]; share = top / len(votes)
        agree = (modal == POL[(s, dr)])
        b = "strong (>=80%)" if share >= 0.8 else "mod (60-80%)" if share >= 0.6 else "contested (<60%)"
        bins[b].append(agree)
    # also: when models STRONGLY agree, how often is the consensus positive but Polina not?
    strong_pos_wrong = strong_pos_tot = 0
    for (s, dr) in items:
        if (s, dr) not in POL or not POL[(s, dr)]:
            continue
        votes = [call[(m, s, dr)] for m in models if (m, s, dr) in call]
        if not votes:
            continue
        c = Counter(votes); modal, top = c.most_common(1)[0]; share = top / len(votes)
        if share >= 0.8 and modal == "positive":
            strong_pos_tot += 1
            if POL[(s, dr)] != "positive":
                strong_pos_wrong += 1

    # ---------- 5. lab structure ----------
    same_agree = same_tot = cross_agree = cross_tot = 0
    for (s, dr) in items:
        present = [(m, call[(m, s, dr)]) for m in models if (m, s, dr) in call]
        for (ma, ca), (mb, cb) in combinations(present, 2):
            if LAB(ma) == LAB(mb):
                same_tot += 1; same_agree += (ca == cb)
            else:
                cross_tot += 1; cross_agree += (ca == cb)

    P = print
    P("\n===== BETWEEN-MODEL SENTIMENT — where they split =====")
    P(f"items={len(items)}  models={len(models)}  (per-model modal over 3 runs)")
    P(f"\n1. Pairwise disagreement: {n_pairs_disagree}/{n_pairs_total} = {n_pairs_disagree/n_pairs_total:.0%} of model-pairs "
      f"disagree on a given item.")
    P(f"   of those disagreements: POSITIVE<->NEGATIVE (hard) {hard/n_pairs_disagree:.0%}  |  "
      f"fuzzy-boundary (involves neutral/mixed) {boundary/n_pairs_disagree:.0%}")
    P("   top disagreement class-pairs:")
    for k, v in pair_conf.most_common(6):
        P(f"     {k[0]:9}<->{k[1]:9} {v/n_pairs_disagree:>5.0%}")
    P(f"\n2. Per-item vote concentration: {ge80/len(conc):.0%} of items have >=80% model consensus; "
      f"{lt60/len(conc):.0%} are contested (<60%).")
    P(f"   items with BOTH a positive and a negative vote (direction genuinely split): "
      f"{dir_split}/{len(conc)} = {dir_split/len(conc):.0%}")
    P(f"   of the contested items: {contested_dir} split on DIRECTION, {contested_bound} on the boundary")
    P(f"\n3. Directional bias (the shared-lean canary):")
    P(f"   overall positive-rate:  models {m_posrate:.0%}  vs  Polina {p_posrate:.0%}")
    P(f"   on Polina-NEGATIVE items (n={n_neg}): models say "
      f"pos {on_neg.get('positive',0):.0%} / neg {on_neg.get('negative',0):.0%} / "
      f"neu {on_neg.get('neutral',0):.0%} / mix {on_neg.get('mixed',0):.0%}")
    P(f"   on Polina-NEUTRAL  items (n={n_neu}): models say "
      f"pos {on_neu.get('positive',0):.0%} / neg {on_neu.get('negative',0):.0%} / "
      f"neu {on_neu.get('neutral',0):.0%} / mix {on_neu.get('mixed',0):.0%}")
    P(f"   on Polina-POSITIVE items (n={n_pos}): models say "
      f"pos {on_pos.get('positive',0):.0%} / neg {on_pos.get('negative',0):.0%} / "
      f"neu {on_pos.get('neutral',0):.0%} / mix {on_pos.get('mixed',0):.0%}")
    P(f"\n4. Does consensus predict Polina-agreement?")
    for b, xs in bins.items():
        if xs:
            P(f"   {b:18}: modal matches Polina {sum(xs)/len(xs):.0%}  (n={len(xs)})")
    P(f"   strong-consensus POSITIVE items where Polina disagrees: {strong_pos_wrong}/{strong_pos_tot} = "
      f"{strong_pos_wrong/strong_pos_tot:.0%}" if strong_pos_tot else "   (no strong-pos items)")
    P(f"\n5. Lab structure: same-lab agree {same_agree/same_tot:.0%} (n={same_tot})  vs  "
      f"cross-lab {cross_agree/cross_tot:.0%} (n={cross_tot})  -> gap {(same_agree/same_tot-cross_agree/cross_tot):+.0%}")

    out = {
        "n_items": len(items), "n_models": len(models),
        "pair_disagree_rate": n_pairs_disagree / n_pairs_total,
        "hard_share": hard / n_pairs_disagree, "boundary_share": boundary / n_pairs_disagree,
        "pair_conf": {f"{k[0]}|{k[1]}": v for k, v in pair_conf.items()},
        "item_ge80": ge80 / len(conc), "item_contested": lt60 / len(conc),
        "item_direction_split": dir_split / len(conc),
        "contested_direction": contested_dir, "contested_boundary": contested_bound,
        "model_posrate": m_posrate, "polina_posrate": p_posrate,
        "on_polina_negative": on_neg, "n_polina_negative": n_neg,
        "on_polina_neutral": on_neu, "n_polina_neutral": n_neu,
        "on_polina_positive": on_pos, "n_polina_positive": n_pos,
        "consensus_vs_polina": {b: (sum(xs) / len(xs), len(xs)) for b, xs in bins.items() if xs},
        "strong_pos_polina_disagree": (strong_pos_wrong, strong_pos_tot),
        "same_lab_agree": same_agree / same_tot, "cross_lab_agree": cross_agree / cross_tot,
    }
    (DV / "j7_between_model.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    P(f"\nWrote {DV/'j7_between_model.json'}")


if __name__ == "__main__":
    main()
