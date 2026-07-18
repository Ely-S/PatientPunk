"""
run_peer_gold.py — treat an existing coder's codings as the gold and re-score everyone else.

The re-score used Opus as gold. This treats any already-coded model (e.g. gpt-5.6-luna) as the gold and
judges every other candidate — plus Opus — against it, using the same Opus equivalence-judge, so the only
thing that changes vs the error-vs-Opus numbers is which model is the yardstick. No re-coding needed: the
gold model already coded these posts in the ⑪ run.

Output: data/validation/j11_vs_<tag>.json {manifest, verdicts[]}
"""
from __future__ import annotations
import argparse
import json
import sys
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from utilities import get_client, LLM_TEMPERATURE
from roster_exec import parallel_map
from run_j11_rejudge import judge_post

DV = ROOT / "data" / "validation"
OPUS = "anthropic/claude-opus-4.8"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold-model", required=True, help="slug of an existing coder to treat as gold")
    ap.add_argument("--tag", required=True, help="short name for output file (e.g. luna)")
    ap.add_argument("--judge", default=OPUS)
    ap.add_argument("--coding", type=Path, default=DV / "j11_coding_runs.json")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    client = get_client()
    cod = json.loads(args.coding.read_text(encoding="utf-8"))
    FIELDS = cod["manifest"]["fields"]
    CAND = cod["manifest"]["candidate_models"]
    allcod = defaultdict(dict)
    for c in cod["codings"]:
        allcod[c["model"]][c["sample_id"]] = c["fields"]
    allcod[OPUS] = {g["sample_id"]: g["fields"] for g in cod["gold"]}   # Opus becomes a scored candidate

    GOLDM = args.gold_model
    if GOLDM not in allcod:
        raise SystemExit(f"gold model {GOLDM} not found among coders: {sorted(allcod)}")
    gold = allcod[GOLDM]
    models = [m for m in CAND + [OPUS] if m != GOLDM]
    out = DV / f"j11_vs_{args.tag}.json"
    print(f"gold={GOLDM} | judge={args.judge} | scoring {len(models)} models (incl Opus) | {len(gold)} posts",
          flush=True)

    partial = out.with_suffix(".partial.jsonl")
    if args.fresh and partial.exists():
        partial.unlink()
    done = set(); verdicts = []
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line); verdicts.append(r); done.add((r["model"], r["sample_id"], r["field"]))
            except Exception:
                pass

    tasks = []
    for m in models:
        for s in gold:
            items = [(f, gold[s].get(f), allcod[m].get(s, {}).get(f)) for f in FIELDS
                     if gold[s].get(f) and allcod[m].get(s, {}).get(f)]
            if items and not all((m, s, f) in done for f, _, _ in items):
                tasks.append((m, s, items))
    print(f"{len(done)} cached; {len(tasks)} (model,post) judge calls", flush=True)
    wlock = threading.Lock()

    def judge_one(t):
        m, s, items = t
        verds = judge_post(client, args.judge, items)
        recs = [{"model": m, "sample_id": s, "field": f,
                 "verdict": "parse_failed" if verds is None else verds.get(f, "missing"),
                 "gold_val": gv, "model_val": mv} for f, gv, mv in items]
        with wlock, partial.open("a", encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps(r) + "\n")
        return recs

    new = parallel_map(judge_one, tasks, workers=args.workers, per_key=args.workers,
                       key=lambda _t: "judge", progress=f"vs-{args.tag}", progress_every=40)
    for batch in new:
        if batch:
            verdicts.extend(batch)

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "judgement": f"11_vs_{args.tag}_gold", "gold_model": GOLDM, "judge_model": args.judge,
        "scored_models": models, "fields": FIELDS, "n_posts": len(gold), "temperature": LLM_TEMPERATURE,
    }
    out.write_text(json.dumps({"manifest": manifest, "verdicts": verdicts}, indent=2), encoding="utf-8")
    print(f"Wrote {out} ({len(verdicts)} verdicts vs {args.tag}-gold)", flush=True)


if __name__ == "__main__":
    main()
