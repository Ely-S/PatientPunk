"""
run_conditions_fix_judge.py — test the Tier-2 `conditions` fix by re-scoring.

Takes every (model, post) `conditions` value the Opus re-score already ruled (the BEFORE), applies the
Tier-2 fix (conditions_fix.fix_conditions) to both the model value AND the gold, and re-judges the FIXED
pair with the same Opus judge + prompt (the AFTER). Same judge, same prompt, same items — so the only
thing that changed is the fix, and the before->after delta is the fix's effect.

Empty-after cases are handled without a call: both empty -> equivalent (both had only symptoms); one empty
-> different (the fix revealed one side carried no real condition).

Output: data/validation/j11_conditions_fix.json {manifest, records[]}
  record = {model, sample_id, before, after, raw_gold, raw_model, fixed_gold, fixed_model}
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
from conditions_fix import fix_conditions
from roster_exec import parallel_map

DV = ROOT / "data" / "validation"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rejudge", type=Path, default=DV / "j11_rejudge.json")
    ap.add_argument("--judge", default="anthropic/claude-opus-4.8")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", type=Path, default=DV / "j11_conditions_fix.json")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    client = get_client()
    rej = json.loads(args.rejudge.read_text(encoding="utf-8"))
    conds = [v for v in rej["verdicts"]
             if v["field"] == "conditions" and v["verdict"] in ("equivalent", "model_subset", "different")]
    print(f"{len(conds)} conditions (model,post) values ruled in the re-score | judge={args.judge}", flush=True)

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
    todo = [v for v in conds if (v["model"], v["sample_id"]) not in done]
    print(f"{len(done)} done (resume); {len(todo)} to run", flush=True)
    wlock = threading.Lock()

    def _judge(gold_list, model_list):
        if gold_list and model_list:
            verds = judge_post(client, args.judge, [("conditions", gold_list, model_list)])
            return "parse_failed" if verds is None else verds.get("conditions", "different")
        return "equivalent" if (not gold_list and not model_list) else "different"

    def run_one(v):
        fg = fix_conditions(v["gold"]); fm = fix_conditions(v["model_val"])
        # BOTH judged in the SAME single-field context, so before_iso -> after isolates the fix alone
        # (v["verdict"] is the original multi-field verdict, kept only as cross-reference).
        before_iso = _judge(v["gold"], v["model_val"])
        after = _judge(fg, fm)
        r = {"model": v["model"], "sample_id": v["sample_id"], "before_multi": v["verdict"],
             "before": before_iso, "after": after,
             "raw_gold": v["gold"], "raw_model": v["model_val"], "fixed_gold": fg, "fixed_model": fm}
        with wlock, partial.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(r) + "\n")
        return r

    new = parallel_map(run_one, todo, workers=args.workers, per_key=args.workers,
                       key=lambda _v: "judge", progress="cond-fix", progress_every=40)
    records = list(done.values()) + [r for r in new if r]

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "judgement": "11_conditions_tier2_fix", "field": "conditions",
        "judge_model": args.judge, "temperature": LLM_TEMPERATURE,
        "fix": "surface canonicalization + symptoms-vs-conditions boundary rule (conditions_fix.py)",
        "n": len(records),
    }
    args.out.write_text(json.dumps({"manifest": manifest, "records": records}, indent=2), encoding="utf-8")
    print(f"Wrote {args.out} ({len(records)} records)", flush=True)


if __name__ == "__main__":
    main()
