"""
run_j6_coreference.py — Judgement ⑥ (coreference) via context ablation.

Coreference = does the model correctly carry a drug named in the UPSTREAM comment into a reply that only
says "it helped"? We can't grade it directly, so we probe it: classify each (comment, drug) WITH its parent
context and WITHOUT (parent stripped), and measure how often the judgement changes. If a model uses
coreference, removing the context should change its answer on **context-necessary** items (drug only in the
parent) far more than on **control** items (drug already in the comment — the noise floor).

Reuses the production classify prompt. Output: data/validation/j6_coreference_runs.json {manifest, records[]}
  record = {model, sample_id, drug, variant(with|without), sentiment, signal, drug_in_comment, parse_failed}
"""
from __future__ import annotations
import argparse
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from utilities import LLM_TEMPERATURE
from roster_exec import parallel_map
from run_j78_classify import classify_one, get_client, SUBREDDIT   # reuse the exact classify call

IRR = ROOT / "data" / "irr_pilot"
OUT_DIR = ROOT / "data" / "validation"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--per-model", type=int, default=3)
    ap.add_argument("--out", type=Path, default=OUT_DIR / "j6_coreference_runs.json")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    client = get_client()
    pol = pd.read_csv(IRR / "human_coder_a.csv", dtype=str, keep_default_na=False)
    ci = pd.read_csv(IRR / "coding_input.csv", dtype=str, keep_default_na=False).set_index("sample_id")
    pol["pu"] = pol["personal_use"].str.strip().str.lower()
    lab = pol[pol.pu.str.startswith(("y", "n"))]

    entries, id_to_text, pairs = {}, {}, []
    for _, r in lab.iterrows():
        s, drug = r["sample_id"], r["drug_mention_verbatim"].strip().lower()
        if s not in ci.index:
            continue
        row = ci.loc[s]
        parent = str(row["parent_context"]).strip()
        if not parent:                      # only items WITH upstream context can test coreference
            continue
        text = row["post_text"]
        if row["unit_type"] == "post" and str(row["title"]).strip():
            text = f"{row['title']}\n\n{text}"
        pid = f"{s}__p"
        id_to_text[pid] = parent
        id_to_text[s] = text
        entries[s] = {"id": s, "text": text, "parent_id": pid, "author": "anon"}
        drug_in_comment = drug in text.lower()
        pairs.append((s, drug, drug_in_comment))
    print(f"{len(pairs)} (comment,drug) pairs WITH parent context | {len(args.models)} models "
          f"| {sum(1 for _,_,c in pairs if not c)} context-necessary | temp={LLM_TEMPERATURE}", flush=True)

    partial = args.out.with_suffix(".partial.jsonl")
    if args.fresh and partial.exists():
        partial.unlink()
    done = set(); records = []
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line); records.append(r); done.add((r["model"], r["sample_id"], r["drug"], r["variant"]))
            except Exception:
                pass
    tasks = [(m, s, d, dic, var) for m in args.models for (s, d, dic) in pairs
             for var in ("with", "without") if (m, s, d, var) not in done]
    print(f"{len(done)} done; {len(tasks)} to run", flush=True)
    wlock = threading.Lock()

    def run_one(t):
        m, s, d, dic, var = t
        entry = dict(entries[s])
        if var == "without":
            entry["parent_id"] = None       # ablate the upstream context
        res = classify_one(client, m, entry, d, id_to_text)
        r = {"model": m, "sample_id": s, "drug": d, "variant": var, "drug_in_comment": dic,
             "sentiment": res["sentiment"], "signal": res["signal"], "parse_failed": res["parse_failed"]}
        with wlock, partial.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(r) + "\n")
        return r

    new = parallel_map(run_one, tasks, workers=args.workers, per_key=args.per_model,
                       key=lambda t: t[0], progress="coref", progress_every=100)
    records += [r for r in new if r]

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "judgement": "6_coreference", "temperature": LLM_TEMPERATURE, "models": args.models,
        "n_pairs": len(pairs), "n_context_necessary": sum(1 for _, _, c in pairs if not c),
        "method": "context ablation — classify with vs without parent context; change-rate vs noise floor",
    }
    args.out.write_text(json.dumps({"manifest": manifest, "records": records}, indent=2), encoding="utf-8")
    print(f"Wrote {args.out} ({len(records)} records)", flush=True)


if __name__ == "__main__":
    main()
