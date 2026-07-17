"""
run_j2_drugid.py — Judgement 2 (drug identification): roster run + dual-truth P/R/F1.

Same template as ① alias, but this judgement reads a POST and returns the SET of drugs
mentioned (extract_batch), so correctness needs both precision AND recall:

  1. Each candidate model extracts drugs from each post.
  2. Score against two truth sources:
       - string-in-post floor — objective: an extracted drug that literally appears in the
         post text is definitely correct (RxNorm's analog for ②), but it misses paraphrase
         ("an oral antibiotic" -> "antibiotic") and abbreviations resolved from context.
       - Opus-as-judge — reads the post + the UNION of all models' extractions, rules each
         correct/hallucinated AND lists drugs in the post that every model missed. One call
         per post (cheap), gives a per-post GOLD present-set for recall.
  3. Validate the judge: on string-confirmed extractions, Opus should agree "correct".
  4. Cross-model divergence: Jaccard of extraction sets per post.

Precision = correct / extracted. Recall = correct / gold-present-set. F1 = harmonic mean.
Opus is the source of truth, never a candidate. Uses roster_exec for fast, rate-limit-aware
parallelism (interleave across models, per-model concurrency cap).

Output: data/validation/j2_drugid_runs.json  {manifest, extractions[], judge[], posts{}}
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from utilities import get_client, llm_call, parse_json_array, parse_json_object, LLMParseError, LLM_TEMPERATURE
from prompts.intervention_config import EXTRACT_PROMPT
from roster_exec import parallel_map

IRR = ROOT / "data" / "irr_pilot"
OUT_DIR = ROOT / "data" / "validation"


def extract_drugs(client, model: str, text: str) -> list[str]:
    """Extract the drug set from one post with an explicit model (mirrors extract_batch)."""
    msg = EXTRACT_PROMPT + "\n--- 1 ---\n" + text + "\n\n"
    try:
        # 1200 not 400: reasoning models spend output tokens thinking before the JSON.
        arr = parse_json_array(llm_call(client, msg, model=model, max_tokens=1200))
        inner = arr[0] if (arr and isinstance(arr[0], list)) else arr
        return sorted({str(d).lower().strip() for d in inner if d and str(d).strip()})
    except Exception:
        return []


JUDGE_PROMPT = """You are checking a drug/treatment extraction from a Reddit post.

Post:
{post}

Models extracted these candidate drugs / supplements / treatments from the post:
{numbered}

Task:
1. For EACH numbered candidate, decide "correct" if it is a drug, supplement, or medical
   treatment actually MENTIONED in the post (brand/generic/abbreviation/misspelling count, and
   generic references like "an antibiotic" count) — otherwise "hallucinated" (not in the post,
   or not a treatment).
2. List any drugs/supplements/treatments that ARE mentioned in the post but are missing from the
   candidate list.

Return ONLY JSON:
{{"verdicts": [{{"item": "...", "verdict": "correct"}}], "missed": ["..."]}}"""


def judge_post(client, judge_model: str, post: str, union: list[str]) -> dict:
    """Opus rules each union item correct/hallucinated and lists drugs missed by all models."""
    numbered = "\n".join(f"{i+1}. {a}" for i, a in enumerate(union)) if union else "(none extracted)"
    prompt = JUDGE_PROMPT.format(post=post, numbered=numbered)
    try:
        obj = parse_json_object(llm_call(client, prompt, model=judge_model, max_tokens=60 * (len(union) + 8) + 200))
        verd = {}
        for v in obj.get("verdicts", []):
            it = str(v.get("item", "")).lower().strip()
            if it:
                verd[it] = "correct" if str(v.get("verdict", "")).lower().startswith("correct") else "hallucinated"
        for a in union:
            verd.setdefault(a, "hallucinated")
        missed = sorted({str(x).lower().strip() for x in obj.get("missed", []) if str(x).strip()})
        return {"verdicts": verd, "missed": missed}
    except (LLMParseError, Exception):
        return {"verdicts": {a: "ungraded" for a in union}, "missed": []}


def select_posts(ci: pd.DataFrame, f1: dict, n: int) -> list[str]:
    """~75% posts that contain drugs (spread across drug-count), ~25% drug-free (hallucination test)."""
    n_tx = {s: f1.get(s, {}).get("n_treatments", 0) for s in ci.sample_id}
    with_drugs = sorted([s for s in ci.sample_id if n_tx[s] >= 1], key=lambda s: n_tx[s])
    without = [s for s in ci.sample_id if n_tx[s] == 0]
    n_with = min(len(with_drugs), int(round(n * 0.75)))
    # stratified spread across drug counts
    buckets = defaultdict(list)
    for s in with_drugs:
        buckets[n_tx[s]].append(s)
    picked_with, sizes = [], sorted(buckets)
    while len(picked_with) < n_with and any(buckets[k] for k in sizes):
        for k in sizes:
            if buckets[k] and len(picked_with) < n_with:
                picked_with.append(buckets[k].pop(0))
    picked_without = without[: n - len(picked_with)]
    return picked_with + picked_without


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--posts", type=int, default=40)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--judge", default="anthropic/claude-opus-4.8")
    ap.add_argument("--workers", type=int, default=40)
    ap.add_argument("--per-model", type=int, default=3)
    ap.add_argument("--judge-workers", type=int, default=12)
    ap.add_argument("--out", type=Path, default=OUT_DIR / "j2_drugid_runs.json")
    args = ap.parse_args()

    client = get_client()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ci = pd.read_csv(IRR / "coding_input.csv", dtype=str, keep_default_na=False)
    f1 = json.loads((IRR / "f1_treatment_vocab.json").read_text(encoding="utf-8"))

    sample_ids = select_posts(ci, f1, args.posts)
    text_of = {}
    for _, r in ci[ci.sample_id.isin(sample_ids)].iterrows():
        t = r["post_text"]
        if r["unit_type"] == "post" and str(r["title"]).strip():
            t = f"{r['title']}\n\n{t}"
        text_of[r["sample_id"]] = t

    print(f"{len(sample_ids)} posts x {len(args.models)} models extractions + judge={args.judge} "
          f"| temp={LLM_TEMPERATURE} | workers={args.workers} (<= {args.per_model}/model)", flush=True)

    # 1) extraction across roster x posts
    ext_tasks = [(m, s) for m in args.models for s in sample_ids]

    def run_ext(t):
        m, s = t
        return {"model": m, "sample_id": s, "drugs": extract_drugs(client, m, text_of[s])}

    extractions = parallel_map(run_ext, ext_tasks, workers=args.workers, per_key=args.per_model,
                               key=lambda t: t[0], progress="extraction")

    # 2) Opus-judge per post on the union of all models' extractions
    union = defaultdict(set)
    for e in extractions:
        union[e["sample_id"]].update(e["drugs"])

    def run_judge(s):
        return {"sample_id": s, **judge_post(client, args.judge, text_of[s], sorted(union[s]))}

    judge = parallel_map(run_judge, sample_ids, workers=args.judge_workers,
                         per_key=args.judge_workers, key=lambda _s: "judge",
                         progress="judge", progress_every=10)

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "judgement": "2_drug_identification",
        "temperature": LLM_TEMPERATURE,
        "candidate_models": args.models,
        "judge_model": args.judge,
        "n_posts": len(sample_ids),
        "truth_sources": ["string_in_post", "opus_judge"],
    }
    args.out.write_text(json.dumps(
        {"manifest": manifest, "extractions": extractions, "judge": judge,
         "posts": {s: text_of[s] for s in sample_ids}}, indent=2), encoding="utf-8")
    print(f"Wrote {args.out} ({len(extractions)} extractions, {len(judge)} posts judged)", flush=True)


if __name__ == "__main__":
    main()
