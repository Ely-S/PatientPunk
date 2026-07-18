"""
run_j78_classify.py — Judgements 7 (sentiment) + 8 (signal) roster classify run.

Both come out of the SAME classify call, so one run covers both. These are the SUBJECTIVE
family — no accuracy vs a gold; the axes are consistency:
  - within-model (K repeats, temp 0)  -> variability
  - cross-model (one run each)         -> do models agree? (Krippendorff alpha + pairwise)
  - vs-Polina (the human reference)    -> do models track the human coder?

We run the REAL production classify prompt (system_prompt) across the roster on the 116
Polina-labelled (post, drug) pairs, capturing sentiment (nominal) and signal (ordinal) per
repeat. Bounded non-streaming call + checkpointing. The Krippendorff analysis is done in the
notebooks via scripts/compute_alphas.py.

Output: data/validation/j78_classify_runs.json  {manifest, results[], polina[]}
  result = {model, sample_id, drug, run, sentiment, signal, parse_failed}
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from utilities import get_client, parse_json_object, LLM_TEMPERATURE
from roster_exec import parallel_map
from models import ClassificationResult
from prompts.intervention_config import system_prompt
from pipeline.classify import format_entry

IRR = ROOT / "data" / "irr_pilot"
OUT_DIR = ROOT / "data" / "validation"
SUBREDDIT = "Long COVID"


def _bounded_call(client, model, system, user, max_tokens=800, timeout=60.0) -> str:
    c = client.with_options(timeout=timeout, max_retries=1)
    base = dict(model=model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user}])
    try:
        try:
            msg = c.messages.create(temperature=0, **base)
        except anthropic.BadRequestError as e:
            if "temperature" in str(e).lower():
                msg = c.messages.create(**base)
            else:
                raise
        return "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", None) == "text")
    except Exception:
        return ""


JSON_TAIL = '\n\nRespond ONLY with JSON: {"sentiment":"positive/negative/mixed/neutral","signal":"strong/moderate/weak/n/a","side_effects":["..."]}'


def classify_one(client, model, entry, drug, id_to_text) -> dict:
    sysp = system_prompt(drug, None, SUBREDDIT)
    raw = _bounded_call(client, model, sysp, format_entry(entry, id_to_text) + JSON_TAIL, max_tokens=800, timeout=60.0)
    try:
        r = ClassificationResult.model_validate(parse_json_object(raw))
        se = [str(x).lower().strip() for x in (r.side_effects or []) if str(x).strip()]
        return {"sentiment": r.sentiment, "signal": r.signal, "side_effects": se, "parse_failed": False}
    except Exception:
        return {"sentiment": None, "signal": None, "side_effects": [], "parse_failed": True}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--k", type=int, default=3, help="repeats per (model, pair) for within-model variability")
    ap.add_argument("--workers", type=int, default=40)
    ap.add_argument("--per-model", type=int, default=3)
    ap.add_argument("--out", type=Path, default=OUT_DIR / "j78_classify_runs.json")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="cap number of labelled pairs (0 = all, for smoke tests)")
    args = ap.parse_args()

    client = get_client()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pol = pd.read_csv(IRR / "human_coder_a.csv", dtype=str, keep_default_na=False)
    ci = pd.read_csv(IRR / "coding_input.csv", dtype=str, keep_default_na=False).set_index("sample_id")
    pol["pu"] = pol["personal_use"].str.strip().str.lower()
    lab = pol[(pol.pu.str.startswith("y")) & (pol.sentiment.str.strip() != "")]

    # entries (post text + injected parent context) and the labelled (sample, drug) pairs
    id_to_text, entries, pairs, polina = {}, {}, [], []
    for _, r in lab.iterrows():
        s, drug = r["sample_id"], r["drug_mention_verbatim"].strip().lower()
        if s not in ci.index:
            continue
        row = ci.loc[s]
        if s not in entries:
            text = row["post_text"]
            if row["unit_type"] == "post" and str(row["title"]).strip():
                text = f"{row['title']}\n\n{text}"
            pid = None
            if str(row["parent_context"]).strip():
                pid = f"{s}__p"; id_to_text[pid] = row["parent_context"]
            id_to_text[s] = text
            entries[s] = {"id": s, "text": text, "parent_id": pid, "author": "anon"}
        pairs.append((s, drug))
        polina.append({"sample_id": s, "drug": drug,
                       "sentiment": r["sentiment"].strip().lower(), "signal": r["signal_strength"].strip().lower()})

    if args.limit:
        pairs, polina = pairs[:args.limit], polina[:args.limit]

    print(f"{len(pairs)} labelled pairs x {len(args.models)} models x k={args.k} "
          f"| temp={LLM_TEMPERATURE} | workers={args.workers}", flush=True)

    partial = args.out.with_suffix(".partial.jsonl")
    if args.fresh and partial.exists():
        partial.unlink()
    done = {}
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line); done[(r["model"], r["sample_id"], r["drug"], r["run"])] = r
            except Exception:
                pass

    tasks = [(m, s, d, k) for m in args.models for (s, d) in pairs for k in range(args.k)
             if (m, s, d, k) not in done]
    print(f"{len(done)} done (resume); {len(tasks)} to run", flush=True)
    wlock = threading.Lock()

    def run_one(t):
        m, s, d, k = t
        res = classify_one(client, m, entries[s], d, id_to_text)
        r = {"model": m, "sample_id": s, "drug": d, "run": k, **res}
        with wlock, partial.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(r) + "\n")
        return r

    new = parallel_map(run_one, tasks, workers=args.workers, per_key=args.per_model,
                       key=lambda t: t[0], progress="classify", progress_every=100)
    results = list(done.values()) + [r for r in new if r]

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "judgements": ["7_sentiment", "8_signal"], "temperature": LLM_TEMPERATURE,
        "candidate_models": args.models, "k": args.k, "subreddit_prompt": SUBREDDIT,
        "n_pairs": len(pairs), "reference": "human_coder_a (Polina)",
        "method": "subjective — within-model + cross-model + vs-Polina Krippendorff alpha",
    }
    args.out.write_text(json.dumps({"manifest": manifest, "results": results, "polina": polina}, indent=2),
                        encoding="utf-8")
    print(f"Wrote {args.out} ({len(results)} classifications)", flush=True)


if __name__ == "__main__":
    main()
