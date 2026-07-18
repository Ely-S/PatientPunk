"""
run_j5_attribution.py — Judgement 5 (attribution) A/B run.

Tests GROUP-ATTRIBUTION inflation. On multi-treatment posts the current classifier
prompt credits an overall improvement to EVERY drug named in the stack:

    intervention_config.py:135  "MULTIPLE DRUGS: If the author takes {name} alongside
    other treatments and reports improvement, classify as positive/weak if {name} is
    named in the stack."

That rule inflates the per-drug positive rate — a collective outcome is assigned to
each treatment individually. This run measures the effect size with a paired A/B test:

  Variant A (A_current) = the production prompt, unchanged.
  Variant B (B_strict)  = the SAME prompt with the MULTIPLE DRUGS block swapped for a
                          strict per-drug attribution rule ("being in the stack is not
                          enough — classify positive only if the author specifically
                          credits this treatment").

For each multi-treatment IRR post (F1 fixture) and each treatment named, both variants
run across the given models at pinned temperature 0 (P1). Because the same (post, drug)
is scored under both variants, the notebook can run a PAIRED test (McNemar) on whether
the positive rate drops under B. "Pass" = positive rate drops under B, same sign across
models. This is prompt-grounded — no gold labels needed.

Output: data/irr_pilot/j5_attribution_runs.json  {manifest, records[]}
  record = {sample_id, drug, model, variant, sentiment, signal, parse_failed}

Usage:
    python scripts/run_j5_attribution.py --limit 30 --max-treatments 6 \
        --models anthropic/claude-sonnet-4.6 anthropic/claude-haiku-4.5
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pydantic import ValidationError

from utilities import get_client, llm_call, parse_json_array, parse_json_object, LLMParseError, LLM_TEMPERATURE
from models import ClassificationResult
from prompts.intervention_config import system_prompt
from pipeline.classify import format_entry

IRR = ROOT / "data" / "irr_pilot"
SUBREDDIT = "Long COVID"  # held constant so only the MULTIPLE DRUGS block differs A vs B

# The strict per-drug attribution rule that replaces the current MULTIPLE DRUGS block.
# Phrased with "this treatment" (not the drug name) so it needs no name substitution.
STRICT_MULTI_BLOCK = """MULTIPLE DRUGS: If the author takes this treatment alongside other treatments and
  reports an overall improvement WITHOUT specifically crediting this treatment, classify
  as neutral — a collective outcome cannot be attributed to one treatment in the stack.
  Classify positive ONLY when the author specifically attributes the benefit to this
  treatment (names it as what helped, ranks it among what worked, or describes its own
  individual effect). Merely being present in the stack is NOT enough.
  Only use mixed if the author themselves expresses uncertainty about whether it helped.

"""


def strict_variant(prompt: str) -> str:
    """Swap the current MULTIPLE DRUGS block (up to REPLY CHAIN) for the strict rule."""
    out = re.sub(r"MULTIPLE DRUGS:.*?(?=REPLY CHAIN:)", STRICT_MULTI_BLOCK, prompt, flags=re.S)
    if out == prompt:
        raise SystemExit("Prompt swap failed — MULTIPLE DRUGS / REPLY CHAIN anchors not found.")
    return out


def classify_drug_batch(client, model, entries, id_to_text, system_prompt_str):
    """Classify entries (all for one drug) under one model + system prompt.

    Mirrors pipeline.classify.classify_batch, but takes an explicit model (so we can
    sweep models without racing on the MODEL_STRONG global) and tags parse-failure
    fallbacks (P2)."""
    msg = f"Classify each entry separately. Return a JSON array of {len(entries)} objects.\n\n"
    for i, e in enumerate(entries):
        msg += f"--- Entry {i + 1} ---\n{format_entry(e, id_to_text)}\n\n"
    msg += (
        f'Return ONLY a JSON array of {len(entries)} objects, each with "sentiment" '
        f'(positive/negative/mixed/neutral), "signal" (strong/moderate/weak/n/a), '
        f'and "side_effects" (array of short lowercase strings, or []).'
    )
    try:
        results = parse_json_array(
            llm_call(client, msg, model=model, system=system_prompt_str, max_tokens=80 * len(entries))
        )
        if len(results) != len(entries):
            raise LLMParseError(f"expected {len(entries)}, got {len(results)}")
        return [ClassificationResult.model_validate(r) for r in results]
    except (LLMParseError, ValidationError):
        out = []
        for e in entries:  # per-item fallback
            try:
                raw = llm_call(
                    client,
                    format_entry(e, id_to_text)
                    + '\n\nRespond ONLY with JSON: {"sentiment":"...","signal":"...","side_effects":[...]}',
                    model=model, system=system_prompt_str, max_tokens=100,
                )
                out.append(ClassificationResult.model_validate(parse_json_object(raw)))
            except (LLMParseError, ValidationError):
                out.append(ClassificationResult(sentiment="neutral", signal="n/a", parse_failed=True))
        return out


def build_entries(picked, ci):
    """Return (entry_of, id_to_text, pairs) for the picked multi-treatment samples."""
    ci = ci.set_index("sample_id")
    entry_of, id_to_text, pairs = {}, {}, []
    for sample_id, meta in picked:
        row = ci.loc[sample_id]
        text = row["post_text"]
        if row["unit_type"] == "post" and str(row["title"]).strip():
            text = f"{row['title']}\n\n{text}"
        parent_id = None
        if str(row["parent_context"]).strip():
            parent_id = f"{sample_id}__parent"
            id_to_text[parent_id] = row["parent_context"]
        entry = {"id": sample_id, "text": text, "parent_id": parent_id, "author": "anon"}
        entry_of[sample_id] = entry
        id_to_text[sample_id] = text
        for drug in meta["treatments"]:
            pairs.append((sample_id, drug))
    return entry_of, id_to_text, pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30, help="number of multi-treatment posts")
    ap.add_argument("--max-treatments", type=int, default=6, help="cap treatments per post (bounds pair count)")
    ap.add_argument("--models", nargs="+",
                    default=["anthropic/claude-sonnet-4.6", "anthropic/claude-haiku-4.5"])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", type=Path, default=IRR / "j5_attribution_runs.json")
    args = ap.parse_args()

    f1 = json.loads((IRR / "f1_treatment_vocab.json").read_text(encoding="utf-8"))
    ci = pd.read_csv(IRR / "coding_input.csv", dtype=str, keep_default_na=False)

    # Pick multi-treatment posts spread ACROSS stack sizes (2..max_treatments), round-robin
    # by size, up to --limit. A spread (not smallest-first) is essential: group-attribution
    # fan-out should grow with stack size, so the sample must vary stack size to test that.
    multi = [(s, v) for s, v in f1.items()
             if v["is_multi_treatment"] and 2 <= v["n_treatments"] <= args.max_treatments]
    buckets: dict[int, list] = defaultdict(list)
    for s, v in multi:
        buckets[v["n_treatments"]].append((s, v))
    for k in buckets:
        buckets[k].sort()  # deterministic order within a size
    sizes = sorted(buckets)
    picked = []
    while len(picked) < args.limit and any(buckets[k] for k in sizes):
        for k in sizes:
            if buckets[k]:
                picked.append(buckets[k].pop(0))
                if len(picked) >= args.limit:
                    break

    entry_of, id_to_text, pairs = build_entries(picked, ci)

    by_drug = defaultdict(list)
    for sample_id, drug in pairs:
        by_drug[drug].append(sample_id)

    # Tasks: one classify call per (model, variant, drug, batch<=5 samples).
    tasks = []
    for model in args.models:
        for variant in ("A_current", "B_strict"):
            for drug, samples in by_drug.items():
                for i in range(0, len(samples), 5):
                    tasks.append((model, variant, drug, samples[i:i + 5]))

    # interleave by model — a model-major submission order hammers each model in turn (the throttling
    # that corrupted the Sol coding); round-robin across models spreads the load.
    _bym = defaultdict(list)
    for t in tasks:
        _bym[t[0]].append(t)
    interleaved = []
    while any(_bym.values()):
        for m in list(_bym):
            if _bym[m]:
                interleaved.append(_bym[m].pop(0))
    tasks = interleaved

    client = get_client()
    print(f"{len(picked)} posts | {len(pairs)} (post,drug) pairs | {len(args.models)} models "
          f"| 2 variants | {len(tasks)} classify calls | temp={LLM_TEMPERATURE}")

    def run_task(task):
        model, variant, drug, samples = task
        sp = system_prompt(drug, None, SUBREDDIT)
        if variant == "B_strict":
            sp = strict_variant(sp)
        entries = [entry_of[s] for s in samples]
        try:
            results = classify_drug_batch(client, model, entries, id_to_text, sp)
        except Exception:
            return []   # API error (e.g. timeout) — skip; resume retries these tasks
        return [
            {"sample_id": s, "drug": drug, "model": model, "variant": variant,
             "sentiment": r.sentiment, "signal": r.signal, "parse_failed": bool(r.parse_failed)}
            for s, r in zip(samples, results)
        ]

    # crash-safe checkpoint: append each task's records to a partial jsonl and skip done tasks on
    # resume (so a mid-run credit-out / rate-limit doesn't lose everything, as it did on the first run).
    partial = args.out.with_suffix(".partial.jsonl")
    done_keys, records = set(), []
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line); records.append(r); done_keys.add((r["model"], r["variant"], r["sample_id"], r["drug"]))
            except Exception:
                pass
    tasks = [t for t in tasks if not all((t[0], t[1], s, t[2]) in done_keys for s in t[3])]
    print(f"{len(done_keys)} records checkpointed; {len(tasks)} tasks to run")
    import threading as _th
    _wlock = _th.Lock()

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_task, t) for t in tasks]
        for fut in as_completed(futures):
            recs = fut.result()
            with _wlock, partial.open("a", encoding="utf-8") as fh:
                for r in recs:
                    fh.write(json.dumps(r) + "\n")
            records.extend(recs)
            done += 1
            if done % 25 == 0 or done == len(tasks):
                print(f"  {done}/{len(tasks)} calls done, {len(records)} records")

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "judgement": "5_attribution",
        "temperature": LLM_TEMPERATURE,
        "max_upstream_depth": 2,
        "subreddit_prompt": SUBREDDIT,
        "models": args.models,
        "n_posts": len(picked),
        "n_pairs": len(pairs),
        "variants": {
            "A_current": "production prompt (MULTIPLE DRUGS credits the stack)",
            "B_strict": "per-drug attribution guard (stack presence is not enough)",
        },
        "fixture": "f1_treatment_vocab.json",
    }
    args.out.write_text(json.dumps({"manifest": manifest, "records": records}, indent=2), encoding="utf-8")
    print(f"Wrote {args.out} ({len(records)} records)")


if __name__ == "__main__":
    main()
