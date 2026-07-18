"""
run_j11_rejudge.py — Judgement 11 value re-score with a SEMANTIC judge.

The ⑪ notebook scored coded values by Jaccard set-overlap, which massively understates accuracy
on free-text values: "2" vs "at least 2 (second infection)" scores 0 despite being the same answer.
This re-score replaces Jaccard with an Opus ruling of semantic equivalence, so we learn the TRUE
value accuracy and which fields are genuinely mis-coded vs merely phrased differently.

For each (model, post), Opus reads the co-populated fields (gold value vs model value) and rules each:
  - equivalent   : same meaning (paraphrase / formatting / number written differently)
  - model_subset : model is correct but less complete than gold (fewer of the same items)
  - different    : genuine conflict or unrelated value (a real coding error)

Reuses the cached ⑪ codings (no re-extraction). Bounded non-streaming call + checkpointing.

Output: data/validation/j11_rejudge.json  {manifest, verdicts[]}
  verdict = {model, sample_id, field, verdict, gold, model_val}
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from utilities import get_client, parse_json_object, LLM_TEMPERATURE
from roster_exec import parallel_map

DV = ROOT / "data" / "validation"


def _bounded_call(client, model, prompt, max_tokens=3000, timeout=90.0) -> str:
    c = client.with_options(timeout=timeout, max_retries=1)
    try:
        try:
            msg = c.messages.create(model=model, max_tokens=max_tokens, temperature=0,
                                    messages=[{"role": "user", "content": prompt}])
        except anthropic.BadRequestError as e:
            if "temperature" in str(e).lower():
                msg = c.messages.create(model=model, max_tokens=max_tokens,
                                        messages=[{"role": "user", "content": prompt}])
            else:
                raise
        return "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", None) == "text")
    except Exception:
        return ""


PROMPT = """You are checking whether a model's extracted value for a patient-data field MEANS THE SAME as the
reference (gold) value. Judge SEMANTIC equivalence — ignore wording, capitalization, formatting, and how a
number is written. A value list that names the same things in different words is equivalent.

For EACH field, output exactly one verdict:
- "equivalent": the model value means the same as gold (paraphrase, reformatting, "2" vs "at least 2", or the
  same conditions named differently all count as equivalent).
- "model_subset": the model value is CORRECT but LESS COMPLETE than gold (gold lists more of the same items).
- "different": the model value conflicts with, or is unrelated to, gold — a genuine coding error.

Fields (field | gold value | model value):
{block}

Return ONLY JSON: {{"verdicts": [{{"field": "...", "verdict": "equivalent"}}]}}"""


def judge_post(client, judge, items):
    """items: list of (field, gold_list, model_list). Returns {field: verdict}, or None if the
    judge call failed / produced unparseable output (so parse-failure is NOT miscounted as a
    genuine 'different' verdict — critical when benchmarking cheap, format-unreliable judges)."""
    block = "\n".join(f'{i+1}. {f} | gold={json.dumps(g)} | model={json.dumps(m)}'
                      for i, (f, g, m) in enumerate(items))
    try:
        # Generous ceiling + timeout so REASONING judges (e.g. qwen3) can spend tokens thinking and
        # still emit the JSON answer — a tight budget starves the answer and looks like a parse failure.
        obj = parse_json_object(_bounded_call(client, judge, PROMPT.format(block=block),
                                              max_tokens=max(3000, 80 * len(items) + 1200), timeout=150.0))
        out = {}
        for v in obj.get("verdicts", []):
            f = str(v.get("field", "")).strip()
            vv = str(v.get("verdict", "")).strip().lower()
            if f:
                out[f] = vv if vv in ("equivalent", "model_subset", "different") else "unparsed"
        return out
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, default=DV / "j11_coding_runs.json")
    ap.add_argument("--judge", default="anthropic/claude-opus-4.8")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", type=Path, default=DV / "j11_rejudge.json")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    client = get_client()
    d = json.loads(args.inp.read_text(encoding="utf-8"))
    GOLD = {g["sample_id"]: g["fields"] for g in d["gold"]}
    FIELDS = d["manifest"]["fields"]
    cod = defaultdict(dict)
    for c in d["codings"]:
        cod[c["model"]][c["sample_id"]] = c["fields"]
    CAND = d["manifest"]["candidate_models"]

    # one judge task per (model, sample) that has >=1 co-populated field
    tasks = []
    for m in CAND:
        for s, gf in GOLD.items():
            items = [(f, gf.get(f), cod[m].get(s, {}).get(f)) for f in FIELDS
                     if gf.get(f) and cod[m].get(s, {}).get(f)]
            if items:
                tasks.append((m, s, items))
    print(f"{len(tasks)} (model,post) judge calls over {len(CAND)} models | judge={args.judge}", flush=True)

    partial = args.out.with_suffix(".partial.jsonl")
    if args.fresh and partial.exists():
        partial.unlink()
    done = set()
    verdicts = []
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line); verdicts.append(r); done.add((r["model"], r["sample_id"], r["field"]))
            except Exception:
                pass
    todo = [(m, s, items) for (m, s, items) in tasks if not all((m, s, f) in done for f, _, _ in items)]
    print(f"{len(done)} field-verdicts already done; {len(todo)} (model,post) calls to run", flush=True)
    wlock = threading.Lock()

    def run_one(t):
        m, s, items = t
        verds = judge_post(client, args.judge, items)
        out = []
        for f, g, mv in items:
            # None => whole call failed to parse; missing field => judge ruled others but not this one.
            # Both are tracked distinctly from a genuine equivalent/subset/different verdict.
            v = "parse_failed" if verds is None else verds.get(f, "missing")
            rec = {"model": m, "sample_id": s, "field": f, "verdict": v,
                   "gold": g, "model_val": mv}
            out.append(rec)
        with wlock, partial.open("a", encoding="utf-8") as fh:
            for rec in out:
                fh.write(json.dumps(rec) + "\n")
        return out

    new = parallel_map(run_one, todo, workers=args.workers, per_key=args.workers,
                       key=lambda _t: "judge", progress="rejudge", progress_every=40)
    for batch in new:
        if batch:
            verdicts.extend(batch)

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "judgement": "11_value_rejudge", "source": args.inp.name,
        "judge_model": args.judge, "candidate_models": CAND, "fields": FIELDS,
        "n_posts": len(GOLD), "temperature": LLM_TEMPERATURE,
        "verdict_scale": "equivalent | model_subset | different",
    }
    args.out.write_text(json.dumps({"manifest": manifest, "verdicts": verdicts}, indent=2), encoding="utf-8")
    print(f"Wrote {args.out} ({len(verdicts)} field verdicts)", flush=True)


if __name__ == "__main__":
    main()
