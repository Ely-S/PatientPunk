"""
run_pair_semantic.py — how much of the N×N model disagreement is REAL vs a Jaccard artifact?

The N×N agreement matrix uses token-Jaccard, which scores "34" vs "34 years old" as 0.33 and "2" vs
"at least 2" as 0 even when the models agree. This re-measures a few model PAIRS with the Opus
semantic-equivalence judge (the same one the ⑪ re-score used), so we can compare Jaccard agreement vs
true semantic agreement — overall and split by field type.

Output: data/validation/j11_pair_semantic.json {manifest, records[]}
  record = {pair, sample_id, field, verdict, jaccard, a_val, b_val}
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import threading
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from utilities import get_client, LLM_TEMPERATURE
from roster_exec import parallel_map
from run_j11_rejudge import judge_post

DV = ROOT / "data" / "validation"
JUDGE = "anthropic/claude-opus-4.8"

# pairs spanning the Jaccard range: highest same-lab, two frontier cross-lab, a low/outlier cross-lab
PAIRS = [
    ("google/gemini-3.5-flash", "google/gemini-3.1-flash-lite"),   # Jaccard 61% (same lab, top)
    ("anthropic/claude-opus-4.8", "x-ai/grok-4.5"),                 # two strong, cross-lab
    ("anthropic/claude-sonnet-4.6", "openai/gpt-5.1"),              # frontier cross-lab
    ("openai/gpt-5.4-nano", "mistralai/mistral-small-2603"),        # low Jaccard, outlier-ish
]


def _norm(x):
    if isinstance(x, list): x = " ".join(map(str, x))
    return set(re.sub(r"[^a-z0-9 ]", " ", str(x).lower()).split())


def _jac(a, b):
    a, b = _norm(a), _norm(b)
    return len(a & b) / len(a | b) if (a | b) else 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coding", type=Path, default=DV / "j11_coding_runs.json")
    ap.add_argument("--judge", default=JUDGE)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--out", type=Path, default=DV / "j11_pair_semantic.json")
    ap.add_argument("--models", nargs="+", help="if given, judge ALL unordered pairs among these models (N×N)")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    pairs = list(combinations(args.models, 2)) if args.models else PAIRS

    client = get_client()
    cod = json.loads(args.coding.read_text(encoding="utf-8"))
    FIELDS = cod["manifest"]["fields"]
    codings = {}
    for c in cod["codings"]:
        codings.setdefault(c["model"], {})[c["sample_id"]] = c["fields"]
    codings["anthropic/claude-opus-4.8"] = {g["sample_id"]: g["fields"] for g in cod["gold"]}
    samples = set().union(*[set(codings[m]) for m in {x for p in pairs for x in p}])

    tasks = []
    for a, b in pairs:
        for s in samples:
            fa, fb = codings.get(a, {}).get(s, {}), codings.get(b, {}).get(s, {})
            items = [(f, fa.get(f), fb.get(f)) for f in FIELDS if fa.get(f) and fb.get(f)]
            if items:
                tasks.append((a, b, s, items))
    print(f"{len(PAIRS)} pairs | {len(tasks)} (pair,post) semantic judge calls | judge={args.judge}", flush=True)

    partial = args.out.with_suffix(".partial.jsonl")
    if args.fresh and partial.exists():
        partial.unlink()
    done, records = set(), []
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line); records.append(r); done.add((r["pair"], r["sample_id"], r["field"]))
            except Exception:
                pass
    todo = [t for t in tasks
            if not all((f"{t[0]}|{t[1]}", t[2], f) in done for f, _, _ in t[3])]
    print(f"{len(done)} cached; {len(todo)} to run", flush=True)
    wlock = threading.Lock()

    def run_one(t):
        a, b, s, items = t
        verds = judge_post(client, args.judge, items)   # judges: does b agree with a
        out = []
        for f, av, bv in items:
            v = "parse_failed" if verds is None else verds.get(f, "missing")
            out.append({"pair": f"{a}|{b}", "sample_id": s, "field": f, "verdict": v,
                        "jaccard": _jac(av, bv), "a_val": av, "b_val": bv})
        with wlock, partial.open("a", encoding="utf-8") as fh:
            for r in out:
                fh.write(json.dumps(r) + "\n")
        return out

    new = parallel_map(run_one, todo, workers=args.workers, per_key=args.workers,
                       key=lambda _t: "judge", progress="pair-sem", progress_every=20)
    for batch in new:
        if batch:
            records.extend(batch)

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "judgement": "11_pair_semantic", "judge_model": args.judge, "pairs": pairs,
        "fields": FIELDS, "temperature": LLM_TEMPERATURE,
    }
    args.out.write_text(json.dumps({"manifest": manifest, "records": records}, indent=2), encoding="utf-8")
    print(f"Wrote {args.out} ({len(records)} field records)", flush=True)


if __name__ == "__main__":
    main()
