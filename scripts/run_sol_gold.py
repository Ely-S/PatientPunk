"""
run_sol_gold.py — treat GPT-5.6 Sol as the ground truth and re-score everyone against it.

The re-score judged every candidate against OPUS's codings (Opus = gold). This asks the complementary
question: if GPT-5.6 *Sol* codes the same 30 posts and we treat *its* codings as truth, how does each
model's error look — and crucially, how does OPUS itself score as a candidate?

Steps: (1) Sol codes the 30 posts on the same 37-field schema, identically to how the 22 candidates + Opus
coded them (reuses the production coding prompt). (2) Every candidate AND Opus is judged against Sol-gold by
the SAME Opus equivalence-judge used for the re-score, so the ONLY thing that changed vs the existing
error-vs-Opus numbers is which model is the gold.

Output: data/validation/j11_vs_sol.json {manifest, sol_gold, verdicts[]}
  verdict = {model, sample_id, field, verdict, sol_val, model_val}
"""
from __future__ import annotations
import argparse
import json
import sys
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "Scrapers" / "demographic_extraction"))

import anthropic

from utilities import get_client, LLM_TEMPERATURE
from roster_exec import parallel_map
from run_j11_coding import _parse_coding, _norm_fields, post_text, POSTS, SCHEMA
from llm_extract import build_field_descriptions, build_system_prompt, build_user_message
from run_j11_rejudge import judge_post

DV = ROOT / "data" / "validation"
OPUS = "anthropic/claude-opus-4.8"


def _sol_call(client, model, system, user, max_tokens=12000, timeout=150.0) -> str:
    """Coding call with reasoning_effort=minimal — Sol reasons itself into timeouts on dense posts
    (118s / occasional timeout); minimal reasoning fixes it (~43s, same field yield as Luna)."""
    c = client.with_options(timeout=timeout, max_retries=1)
    base = dict(model=model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user}],
                extra_body={"reasoning": {"effort": "minimal"}})
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sol", default="openai/gpt-5.6-sol")
    ap.add_argument("--judge", default=OPUS)
    ap.add_argument("--coding", type=Path, default=DV / "j11_coding_runs.json")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", type=Path, default=DV / "j11_vs_sol.json")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    client = get_client()
    cod = json.loads(args.coding.read_text(encoding="utf-8"))
    FIELDS = cod["manifest"]["fields"]
    CAND = cod["manifest"]["candidate_models"]
    posts = json.loads(POSTS.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    field_desc = build_field_descriptions(schema)
    system = build_system_prompt(field_desc)
    sample_ids = {g["sample_id"] for g in cod["gold"]}
    texts = {p["post_id"]: post_text(p) for p in posts if p["post_id"] in sample_ids}
    print(f"{len(texts)} posts | Sol={args.sol} | judge={args.judge} | {len(CAND)} candidates + Opus", flush=True)

    # ---- phase 1: Sol codes the posts (Sol-gold) ----
    sol_path = args.out.with_name("j11_sol_gold.json")
    if sol_path.exists() and not args.fresh:
        sol_gold = json.loads(sol_path.read_text(encoding="utf-8"))
        print(f"loaded cached Sol-gold ({len(sol_gold)} posts)", flush=True)
    else:
        def code_one(sid):
            raw = _sol_call(client, args.sol, system, build_user_message([texts[sid]]))
            return sid, _norm_fields(_parse_coding(raw, FIELDS))   # unwrap ["fields"] + normalize
        res = parallel_map(code_one, list(texts), workers=args.workers, per_key=args.workers,
                           key=lambda _s: "sol", progress="sol-code", progress_every=10)
        sol_gold = {sid: fields for sid, fields in res if fields is not None}
        sol_path.write_text(json.dumps(sol_gold, indent=2), encoding="utf-8")
        print(f"Sol coded {len(sol_gold)} posts", flush=True)

    # ---- phase 2: judge every model (candidates + Opus-as-candidate) vs Sol-gold ----
    allcod = defaultdict(dict)
    for c in cod["codings"]:
        allcod[c["model"]][c["sample_id"]] = c["fields"]
    allcod[OPUS] = {g["sample_id"]: g["fields"] for g in cod["gold"]}   # Opus now a scored candidate
    models = CAND + [OPUS]

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

    tasks = []
    for m in models:
        for s in sol_gold:
            items = [(f, sol_gold[s].get(f), allcod[m].get(s, {}).get(f)) for f in FIELDS
                     if sol_gold[s].get(f) and allcod[m].get(s, {}).get(f)]
            if items and not all((m, s, f) in done for f, _, _ in items):
                tasks.append((m, s, items))
    print(f"{len(done)} field-verdicts cached; {len(tasks)} (model,post) judge calls to run", flush=True)
    wlock = threading.Lock()

    def judge_one(t):
        m, s, items = t
        verds = judge_post(client, args.judge, items)
        out = []
        for f, sv, mv in items:
            v = "parse_failed" if verds is None else verds.get(f, "missing")
            out.append({"model": m, "sample_id": s, "field": f, "verdict": v, "sol_val": sv, "model_val": mv})
        with wlock, partial.open("a", encoding="utf-8") as fh:
            for rec in out:
                fh.write(json.dumps(rec) + "\n")
        return out

    new = parallel_map(judge_one, tasks, workers=args.workers, per_key=args.workers,
                       key=lambda _t: "judge", progress="vs-sol", progress_every=40)
    for batch in new:
        if batch:
            verdicts.extend(batch)

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "judgement": "11_vs_sol_gold", "sol_model": args.sol, "judge_model": args.judge,
        "candidate_models": CAND, "opus_scored_as_candidate": OPUS, "fields": FIELDS,
        "n_posts": len(sol_gold), "temperature": LLM_TEMPERATURE,
    }
    args.out.write_text(json.dumps({"manifest": manifest, "sol_gold": sol_gold, "verdicts": verdicts}, indent=2),
                        encoding="utf-8")
    print(f"Wrote {args.out} ({len(verdicts)} verdicts vs Sol-gold)", flush=True)


if __name__ == "__main__":
    main()
