"""
run_ds_sentiment_stability.py — within-model sentiment stability for ONE model at scale.

The roster ⑦ run used 116 pairs x 3 repeats. This zooms in on the production candidate
(deepseek-v4-flash): ~500 real (post, drug) pairs x K repeats through the EXACT production
classify path (system_prompt + classify_one), temperature pinned. Answers: at scale, does
DeepSeek Flash return the same sentiment run-to-run, and is its distribution stable across runs?

Pairs are built from the 300-post IRR frame (coding_input.csv) joined to the (sample, drug)
pairs a human coder tagged (ai_coder_*.csv), personal-use pairs first so sentiment is a real
signal rather than a wall of neutrals.

Output: data/validation/j7_ds_stability.json {manifest, results[]}
  result = {sample_id, drug, run, sentiment, signal, parse_failed}
"""
from __future__ import annotations
import argparse
import glob
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from utilities import get_client, LLM_TEMPERATURE
from roster_exec import parallel_map
from run_j78_classify import classify_one          # exact production classify path

IRR = ROOT / "data" / "irr_pilot"
OUT = ROOT / "data" / "validation" / "j7_ds_stability.json"
MODEL = "deepseek/deepseek-v4-flash"


def build_pairs(n_target: int):
    ci = pd.read_csv(IRR / "coding_input.csv", dtype=str, keep_default_na=False).set_index("sample_id")
    # union the (sample, drug, personal_use) tags across all human/AI coder files, dedup on (sample, drug)
    rows = []
    for f in sorted(glob.glob(str(IRR / "ai_coder_*.csv"))) + sorted(glob.glob(str(IRR / "human_coder_*.csv"))):
        d = pd.read_csv(f, dtype=str, keep_default_na=False)
        if "drug_mention_verbatim" not in d.columns:
            continue
        for _, r in d.iterrows():
            rows.append((r["sample_id"], r["drug_mention_verbatim"].strip().lower(),
                         r.get("personal_use", "").strip().lower()))
    seen, pu_pairs, other_pairs = set(), [], []
    for s, drug, pu in rows:
        if not drug or s not in ci.index or (s, drug) in seen:
            continue
        seen.add((s, drug))
        (pu_pairs if pu.startswith("y") else other_pairs).append((s, drug))
    pairs = (pu_pairs + other_pairs)[:n_target]   # personal-use first, then top up to target

    id_to_text, entries = {}, {}
    for s, _ in pairs:
        if s in entries:
            continue
        row = ci.loc[s]
        text = row["post_text"]
        if row["unit_type"] == "post" and str(row["title"]).strip():
            text = f"{row['title']}\n\n{text}"
        pid = None
        if str(row["parent_context"]).strip():
            pid = f"{s}__p"; id_to_text[pid] = row["parent_context"]
        id_to_text[s] = text
        entries[s] = {"id": s, "text": text, "parent_id": pid, "author": "anon"}
    return pairs, entries, id_to_text, len(pu_pairs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500, help="number of (post, drug) pairs")
    ap.add_argument("--k", type=int, default=5, help="repeats per pair")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    client = get_client()
    pairs, entries, id_to_text, n_pu = build_pairs(args.n)
    print(f"{len(pairs)} pairs ({n_pu} personal-use) x k={args.k} = {len(pairs)*args.k} calls "
          f"| model={MODEL} | temp={LLM_TEMPERATURE}", flush=True)

    partial = OUT.with_suffix(".partial.jsonl")
    if args.fresh and partial.exists():
        partial.unlink()
    done, results = set(), []
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line); results.append(r); done.add((r["sample_id"], r["drug"], r["run"]))
            except Exception:
                pass

    tasks = [(s, d, k) for (s, d) in pairs for k in range(args.k) if (s, d, k) not in done]
    print(f"{len(done)} done (resume); {len(tasks)} to run", flush=True)
    wlock = threading.Lock()

    def run_one(t):
        s, d, k = t
        res = classify_one(client, MODEL, entries[s], d, id_to_text)
        r = {"sample_id": s, "drug": d, "run": k,
             "sentiment": res["sentiment"], "signal": res["signal"], "parse_failed": res["parse_failed"]}
        with wlock, partial.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(r) + "\n")
        return r

    new = parallel_map(run_one, tasks, workers=args.workers, per_key=args.workers,
                       key=lambda _t: "ds", progress="ds-stab", progress_every=100)
    results += [r for r in new if r]

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(), "model": MODEL,
        "temperature": LLM_TEMPERATURE, "k": args.k, "n_pairs": len(pairs), "n_personal_use": n_pu,
        "method": "within-model sentiment stability at scale via production classify_one",
    }
    OUT.write_text(json.dumps({"manifest": manifest, "results": results}, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} ({len(results)} classifications)", flush=True)


if __name__ == "__main__":
    main()
