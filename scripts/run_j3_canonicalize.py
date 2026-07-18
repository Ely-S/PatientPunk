"""
run_j3_canonicalize.py — Judgement ③ (canonicalisation) across the roster.

Canonicalisation is the merge/split decision: do "LDN" and "low dose naltrexone" collapse to one drug?
We have a clean gold for this — the ⑪... no, the ① alias generation (j1_alias_runs.json) produced many
surface forms of the 6 target drugs, so we KNOW which names should merge (all aliases of naltrexone → one
group). We feed a deduped list of those aliases to pipeline.canonicalize.canonicalize_batch under each
roster model and score the merge decisions against that known grouping + cross-model agreement.

Output: data/validation/j3_canonicalize_runs.json {manifest, gold{alias:drug}, canon{model:{name:canon}}}
"""
from __future__ import annotations
import argparse
import json
import sys
import threading
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from utilities import get_client, LLM_TEMPERATURE
from roster_exec import parallel_map
from pipeline.canonicalize import canonicalize_batch

DV = ROOT / "data" / "validation"


def build_names(per_drug_cap: int):
    """From j1 alias generations, build a deduped alias list + gold {alias: drug}."""
    j1 = json.loads((DV / "j1_alias_runs.json").read_text(encoding="utf-8"))
    by_drug = defaultdict(Counter)
    for g in j1["generations"]:
        drug = g["drug"].lower().strip()
        for a in g.get("aliases", []):
            a = str(a).lower().strip()
            if a:
                by_drug[drug][a] += 1
    gold, names = {}, []
    for drug, cnt in by_drug.items():
        # always include the drug's own name; then its most-common aliases
        picks = [drug] + [a for a, _ in cnt.most_common(per_drug_cap) if a != drug]
        for a in picks[:per_drug_cap]:
            if a not in gold:          # first-seen drug wins on the rare shared alias
                gold[a] = drug; names.append(a)
    return names, gold


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--per-drug-cap", type=int, default=22, help="aliases per drug (bounds the list size)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", type=Path, default=DV / "j3_canonicalize_runs.json")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    client = get_client()
    names, gold = build_names(args.per_drug_cap)
    print(f"{len(names)} alias surface-forms over {len(set(gold.values()))} drugs | {len(args.models)} models",
          flush=True)

    partial = args.out.with_suffix(".partial.jsonl")
    if args.fresh and partial.exists():
        partial.unlink()
    done = {}
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line); done[r["model"]] = r["canon"]
            except Exception:
                pass
    todo = [m for m in args.models if m not in done]
    print(f"{len(done)} models cached; {len(todo)} to run", flush=True)
    wlock = threading.Lock()

    def run_one(model):
        try:
            canon = canonicalize_batch(client, names, model=model)   # {name: canonical}
        except Exception:
            canon = None
        with wlock, partial.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"model": model, "canon": canon}) + "\n")
        return model, canon

    new = parallel_map(run_one, todo, workers=args.workers, per_key=1,
                       key=lambda m: m, progress="canon", progress_every=4)
    canon = dict(done)
    for m, c in new:
        if c is not None:
            canon[m] = c

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "judgement": "3_canonicalize", "temperature": LLM_TEMPERATURE,
        "models": args.models, "n_names": len(names), "n_drugs": len(set(gold.values())),
        "gold_source": "j1_alias_runs (known drug->alias groupings)",
    }
    args.out.write_text(json.dumps({"manifest": manifest, "gold": gold, "canon": canon}, indent=2),
                        encoding="utf-8")
    print(f"Wrote {args.out} ({len([c for c in canon.values() if c])} models with results)", flush=True)


if __name__ == "__main__":
    main()
