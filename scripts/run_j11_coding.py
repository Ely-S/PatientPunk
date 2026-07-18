"""
run_j11_coding.py — Judgement 11 (variable coding): roster run + Opus-gold P/R/F1.

Track B, step 2. Given the FIXED covidlonghaulers schema (37 fields), each model reads a post and
codes a value (or null) for every field — `llm_extract.py`. Correctness = per-field precision/recall
vs an Opus-coded gold (Opus codes the same posts against the same schema; verification of a factual
extraction). Opus is truth, never scored as a candidate.

Reuses the real production coding prompt (build_system_prompt / build_user_message) and routes the
roster through a BOUNDED non-streaming call (hard per-request timeout — reasoning models can be slow)
with incremental JSONL CHECKPOINTING (a kill/hang never loses finished work; re-runs resume/add).

Output: data/validation/j11_coding_runs.json  {manifest, codings[], gold[], posts{}}
  coding/gold record = {model|"__gold__", sample_id, fields:{field:[values]|None}}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "Scrapers" / "demographic_extraction"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(DEMO))

from utilities import get_client, parse_json_object, LLM_TEMPERATURE
from roster_exec import parallel_map
from llm_extract import build_field_descriptions, build_system_prompt, build_user_message, parse_json_response

POSTS = ROOT / "Scrapers" / "output" / "subreddit_posts.json"
SCHEMA = DEMO / "schemas" / "covidlonghaulers_schema.json"
OUT_DIR = ROOT / "data" / "validation"


def _bounded_call(client, model, system, user, max_tokens=4000, timeout=90.0) -> str:
    """Non-streaming call with a hard per-request timeout (streaming doesn't reliably time out on
    slow reasoning models). On timeout/error return ''."""
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


def _norm_fields(obj) -> dict:
    fields = obj.get("fields", {}) if isinstance(obj, dict) else {}
    out = {}
    for f, v in fields.items():
        if v is None or v == "" or v == []:
            out[f] = None
        elif isinstance(v, list):
            vals = [str(x).lower().strip() for x in v if x is not None and str(x).strip()]
            out[f] = vals or None
        else:
            out[f] = [str(v).lower().strip()]
    return out


def _parse_coding(raw: str, known: list[str]) -> dict:
    """Extract {fields: {field: value}} tolerantly.

    Coded values embed patient phrases that routinely break strict JSON (e.g. a value like
    "'stuck' diaphragm"). Try clean JSON first; then, because we KNOW the 37 field names, pull
    each field's value independently by name — a broken quote in one value garbles only that
    field, not the whole record (which strict parsing would drop to empty)."""
    for parser in (parse_json_object, parse_json_response):
        try:
            o = parser(raw)
            if isinstance(o, dict) and isinstance(o.get("fields"), dict):
                return o
        except Exception:
            pass
    fields = {}
    for f in known:
        m = re.search(rf'"{re.escape(f)}"\s*:\s*(null|\[[^\]]*\])', raw)
        if not m:
            continue
        val = m.group(1)
        fields[f] = None if val == "null" else (re.findall(r'"((?:[^"\\]|\\.)*)"', val) or None)
    return {"fields": fields}


def code_post(client, model, system, text, known) -> dict:
    # 8000 tokens: a content-rich post fills many of the 37 fields with multi-value lists.
    raw = _bounded_call(client, model, system, build_user_message([text]), max_tokens=8000, timeout=90.0)
    return _norm_fields(_parse_coding(raw, known))


def post_text(p: dict, cap: int = 12000) -> str:
    parts = [p.get("title", ""), p.get("body", "") or ""]
    parts += [c.get("body", "") for c in p.get("comments", []) if c.get("body")]
    return "\n\n".join(x for x in parts if x)[:cap]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--posts", type=int, default=30)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--judge", default="anthropic/claude-opus-4.8")
    ap.add_argument("--workers", type=int, default=40)
    ap.add_argument("--per-model", type=int, default=3)
    ap.add_argument("--out", type=Path, default=OUT_DIR / "j11_coding_runs.json")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    client = get_client()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    posts = json.loads(POSTS.read_text(encoding="utf-8"))[: args.posts]
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    field_desc = build_field_descriptions(schema)
    known = sorted(field_desc)
    system = build_system_prompt(field_desc)
    texts = {p["post_id"]: post_text(p) for p in posts}
    sample_ids = list(texts)

    print(f"{len(sample_ids)} posts x {len(args.models)} models coding {len(field_desc)} fields "
          f"+ gold={args.judge} | temp={LLM_TEMPERATURE} | workers={args.workers}", flush=True)

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

    # candidates x posts, plus gold (judge) x posts, all as (model_or_gold, sample_id) tasks
    all_tasks = [(m, s) for m in args.models for s in sample_ids] + [("__gold__", s) for s in sample_ids]
    tasks = [t for t in all_tasks if t not in done]
    print(f"{len(done)} already done (resume); {len(tasks)} to run", flush=True)

    wlock = threading.Lock()

    def run_one(t):
        m, s = t
        model = args.judge if m == "__gold__" else m
        r = {"model": m, "sample_id": s, "fields": code_post(client, model, system, texts[s], known)}
        with wlock, partial.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(r) + "\n")
        return r

    new = parallel_map(run_one, tasks, workers=args.workers, per_key=args.per_model,
                       key=lambda t: t[0], progress="coding", progress_every=40)
    records = list(done.values()) + [r for r in new if r]

    codings = [r for r in records if r["model"] != "__gold__"]
    gold = [{"sample_id": r["sample_id"], "fields": r["fields"]} for r in records if r["model"] == "__gold__"]

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "judgement": "11_variable_coding", "temperature": LLM_TEMPERATURE,
        "candidate_models": args.models, "judge_model": args.judge,
        "n_posts": len(sample_ids), "schema_id": schema.get("schema_id", "covidlonghaulers_v1"),
        "fields": known, "truth_sources": ["opus_gold"],
    }
    args.out.write_text(json.dumps(
        {"manifest": manifest, "codings": codings, "gold": gold, "posts": texts}, indent=2), encoding="utf-8")
    print(f"Wrote {args.out} ({len(codings)} codings, {len(gold)} gold)", flush=True)


if __name__ == "__main__":
    main()
