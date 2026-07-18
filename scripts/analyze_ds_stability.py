"""
analyze_ds_stability.py — within-model sentiment stability for deepseek-v4-flash at scale.

Reads data/validation/j7_ds_stability.json (500 pairs x 5 repeats, temp 0) and answers:
  1. Per-pair agreement: how often do all 5 runs give the SAME sentiment?
  2. When they don't, is the flip on DIRECTION (pos<->neg) or the fuzzy boundary (neutral)?
  3. Aggregate stability: is the overall sentiment DISTRIBUTION the same on each of the 5 runs,
     even if individual items wobble? (flips can cancel in aggregate.)
"""
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

DV = Path(__file__).resolve().parent.parent / "data" / "validation"
DIRB = {"positive": "+", "negative": "-", "neutral": "0", "mixed": "0"}


def main():
    d = json.loads((DV / "j7_ds_stability.json").read_text(encoding="utf-8"))
    R = [r for r in d["results"] if not r["parse_failed"] and r["sentiment"]]
    K = d["manifest"]["k"]
    byp = defaultdict(dict)                          # (sample,drug) -> {run: sentiment}
    for r in R:
        byp[(r["sample_id"], r["drug"])][r["run"]] = r["sentiment"]
    full = [p for p, v in byp.items() if len(v) == K]   # pairs with all K runs present

    # 1. per-pair agreement
    ident = sum(1 for p in full if len(set(byp[p].values())) == 1)
    modal_share = Counter()
    for p in full:
        c = Counter(byp[p].values()); modal_share[c.most_common(1)[0][1]] += 1

    # 2. flip type on unstable pairs
    unstable = [p for p in full if len(set(byp[p].values())) > 1]
    dir_flip = sum(1 for p in unstable if "+" in {DIRB[s] for s in byp[p].values()} and "-" in {DIRB[s] for s in byp[p].values()})
    bound_flip = len(unstable) - dir_flip
    # the flip pairs (what<->what)
    flip_pairs = Counter()
    for p in unstable:
        for a, b in combinations(sorted(set(byp[p].values())), 2):
            flip_pairs[(a, b)] += 1

    # mean pairwise run agreement
    agree = tot = 0
    for p in full:
        for a, b in combinations(range(K), 2):
            tot += 1; agree += (byp[p][a] == byp[p][b])
    pair_agree = agree / tot if tot else float("nan")

    # 3. aggregate distribution per run
    cats = ["positive", "negative", "neutral", "mixed"]
    per_run = {k: Counter() for k in range(K)}
    for r in R:
        per_run[r["run"]][r["sentiment"]] += 1
    run_dist = {}
    for k in range(K):
        t = sum(per_run[k].values()); run_dist[k] = {c: per_run[k][c] / t for c in cats}
    spread = {c: max(run_dist[k][c] for k in range(K)) - min(run_dist[k][c] for k in range(K)) for c in cats}

    P = print
    P(f"=== DeepSeek Flash within-model stability — {len(full)} pairs x {K} runs ===")
    P(f"parse-fail rate: {1 - len(R)/(len(byp)*K):.1%}  ({len(R)} good of {len(byp)*K} calls)")
    P(f"\n1. PER-PAIR: {ident}/{len(full)} = {ident/len(full):.0%} pairs identical across all {K} runs")
    P(f"   mean pairwise run agreement: {pair_agree:.0%}")
    P("   modal support distribution (how many of 5 runs agree on the majority call):")
    for k in sorted(modal_share, reverse=True):
        P(f"     {k}/5 agree: {modal_share[k]:>4} pairs ({modal_share[k]/len(full):.0%})")
    P(f"\n2. UNSTABLE pairs ({len(unstable)}): DIRECTION flip (pos<->neg) {dir_flip} "
      f"({dir_flip/len(unstable):.0%}) | boundary/neutral {bound_flip} ({bound_flip/len(unstable):.0%})")
    P("   top flip types:")
    for (a, b), n in flip_pairs.most_common(6):
        P(f"     {a:9}<->{b:9} {n}")
    P("\n3. AGGREGATE distribution per run (does the overall mix hold run-to-run?):")
    P(f"   {'run':>4} " + " ".join(f"{c[:3]:>6}" for c in cats))
    for k in range(K):
        P(f"   {k:>4} " + " ".join(f"{run_dist[k][c]:>6.1%}" for c in cats))
    P(f"   max-min spread across runs: " + " ".join(f"{c[:3]} {spread[c]:.1%}" for c in cats))

    out = {"n_pairs": len(full), "k": K, "pair_identical": ident/len(full),
           "mean_pairwise_run_agreement": pair_agree,
           "modal_share": {str(k): modal_share[k] for k in modal_share},
           "n_unstable": len(unstable), "direction_flip": dir_flip, "boundary_flip": bound_flip,
           "run_dist": run_dist, "aggregate_spread": spread,
           "flip_pairs": {f"{a}|{b}": n for (a, b), n in flip_pairs.items()}}
    (DV / "j7_ds_stability_summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    P(f"\nWrote {DV/'j7_ds_stability_summary.json'}")


if __name__ == "__main__":
    main()
