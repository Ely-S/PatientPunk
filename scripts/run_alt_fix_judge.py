"""
run_alt_fix_judge.py — test the Tier-2 RxNorm tool on `alternative_treatments` by re-scoring.

Same matched-context design as the conditions prototype: every (model, post) alternative_treatments value
the Opus re-score ruled is re-judged BEFORE (raw) and AFTER (RxNorm-canonicalized), BOTH in the same
single-field context, so the delta isolates the tool. The tool is alt_treatments_rxnorm.fix_alt (link each
substance to its RxNorm concept name; keep non-substances verbatim), applied to model AND gold.

Output: data/validation/j11_alt_fix.json {manifest, records[]}
"""
from __future__ import annotations
import argparse
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from utilities import get_client, LLM_TEMPERATURE
from run_j11_rejudge import judge_post
from alt_treatments_rxnorm import fix_alt, load_cache
from roster_exec import parallel_map

DV = ROOT / "data" / "validation"
FIELD = "alternative_treatments"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rejudge", type=Path, default=DV / "j11_rejudge.json")
    ap.add_argument("--judge", default="anthropic/claude-opus-4.8")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", type=Path, default=DV / "j11_alt_fix.json")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    client = get_client()
    cache = load_cache()
    linked = sum(1 for v in cache.values() if v.get("rxcui"))
    print(f"RxNorm cache: {linked}/{len(cache)} terms linked", flush=True)
    rej = json.loads(args.rejudge.read_text(encoding="utf-8"))
    items = [v for v in rej["verdicts"]
             if v["field"] == FIELD and v["verdict"] in ("equivalent", "model_subset", "different")]
    print(f"{len(items)} {FIELD} values ruled in the re-score | judge={args.judge}", flush=True)

    partial = args.out.with_suffix(".partial.jsonl")
    if args.fresh and partial.exists():
        partial.unlink()
    done = {}
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line); done[(r["model"], r["sample_id"])] = r
            except Exception:
                pass
    todo = [v for v in items if (v["model"], v["sample_id"]) not in done]
    print(f"{len(done)} done (resume); {len(todo)} to run", flush=True)
    wlock = threading.Lock()

    def _judge(gold_list, model_list):
        if gold_list and model_list:
            verds = judge_post(client, args.judge, [(FIELD, gold_list, model_list)])
            return "parse_failed" if verds is None else verds.get(FIELD, "different")
        return "equivalent" if (not gold_list and not model_list) else "different"

    def run_one(v):
        fg = fix_alt(v["gold"], cache); fm = fix_alt(v["model_val"], cache)
        before_iso = _judge(v["gold"], v["model_val"])
        after = _judge(fg, fm)
        r = {"model": v["model"], "sample_id": v["sample_id"], "before_multi": v["verdict"],
             "before": before_iso, "after": after,
             "raw_gold": v["gold"], "raw_model": v["model_val"], "fixed_gold": fg, "fixed_model": fm}
        with wlock, partial.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(r) + "\n")
        return r

    new = parallel_map(run_one, todo, workers=args.workers, per_key=args.workers,
                       key=lambda _v: "judge", progress="alt-fix", progress_every=40)
    records = list(done.values()) + [r for r in new if r]

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "judgement": "11_alt_treatments_tier2_rxnorm", "field": FIELD,
        "judge_model": args.judge, "temperature": LLM_TEMPERATURE,
        "tool": "RxNorm concept canonicalization via keyless RxNav (alt_treatments_rxnorm.py)",
        "rxnorm_terms_linked": linked, "n": len(records),
    }
    args.out.write_text(json.dumps({"manifest": manifest, "records": records}, indent=2), encoding="utf-8")
    print(f"Wrote {args.out} ({len(records)} records)", flush=True)


if __name__ == "__main__":
    main()
