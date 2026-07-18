"""
run_j10_discovery.py — Judgement 10 (variable discovery): roster run + Opus-judged quality.

Track B, step 1. Each model reads a batch of patient posts and proposes NEW fields to extract
(beyond the fixed schema) — `discover_fields.py`'s Phase 1. Eli's finding: models propose wildly
different NUMBERS of fields, so the headline here is cross-model DIVERGENCE (do models even agree
on WHAT to extract?), and correctness is Opus-as-judge on each proposed field's quality.

  - Each candidate model proposes fields on the SAME fixed batches of posts.
  - Opus-as-judge rules each proposed field keep/junk (distinct, well-defined, research-useful
    biomedical covariate, not redundant with the schema) -> per-model precision.
  - Cross-model divergence: Jaccard of proposed field-name sets (expected LOW — the finding).

Reuses the real production prompt (`build_discovery_prompt`) so we test the actual judgement, and
routes the roster through src/utilities.llm_call (OpenRouter + reasoning-safe). Opus is truth, never
a candidate. Uses roster_exec for fast, rate-limit-aware parallelism.

Output: data/validation/j10_discovery_runs.json  {manifest, proposals[], judge{}, batches[]}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "Scrapers" / "demographic_extraction"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(DEMO))

import anthropic

from utilities import get_client, llm_call, parse_json_object, LLMParseError, LLM_TEMPERATURE
from roster_exec import parallel_map
from discover_fields import build_discovery_prompt, parse_json_response
from llm_extract import build_field_descriptions

POSTS = ROOT / "Scrapers" / "output" / "subreddit_posts.json"
SCHEMA = DEMO / "schemas" / "covidlonghaulers_schema.json"
OUT_DIR = ROOT / "data" / "validation"

DISCOVERY_USER = ("Analyze these patient-authored texts and identify recurring biomedical patterns "
                  "not covered by the existing schema:\n\n")


def _norm(f: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(f).lower().strip()).strip("_")


def post_text(p: dict) -> str:
    parts = [p.get("title", ""), p.get("body", "") or ""]
    parts += [c.get("body", "") for c in p.get("comments", []) if c.get("body")]
    return "\n\n".join(x for x in parts if x)


def make_batches(posts: list, batch_chars: int) -> list[str]:
    batches, cur, cur_len = [], [], 0
    for p in posts:
        t = post_text(p)
        if cur and cur_len + len(t) > batch_chars:
            batches.append("\n\n---NEW POST/USER---\n\n".join(cur)); cur, cur_len = [], 0
        cur.append(t); cur_len += len(t)
    if cur:
        batches.append("\n\n---NEW POST/USER---\n\n".join(cur))
    return batches


def _extract_fields(raw: str) -> list[tuple[str, str]]:
    """Pull (field_name, description) pairs from a discovery response.

    The production prompt asks for 8 verbatim patient-quote examples per field, and models
    routinely emit those with unescaped quotes/newlines that break strict JSON. We only need
    the field NAME and DESCRIPTION for this judgement, so try clean JSON first, then fall back
    to a tolerant regex that survives malformed (or truncated) example arrays."""
    for parser in (parse_json_response, parse_json_object):
        try:
            obj = parser(raw)
            if isinstance(obj, dict) and isinstance(obj.get("discovered_fields"), list):
                return [(f.get("field_name", ""), f.get("description", ""))
                        for f in obj["discovered_fields"] if isinstance(f, dict)]
        except Exception:
            pass
    out = []
    for m in re.finditer(r'"field_name"\s*:\s*"([^"]+)"(.*?)(?="field_name"\s*:|\Z)', raw, re.S):
        dm = re.search(r'"description"\s*:\s*"([^"]{0,300})', m.group(2))
        out.append((m.group(1), dm.group(1) if dm else ""))
    return out


def _bounded_call(client, model: str, system: str, user: str,
                  max_tokens: int = 10000, timeout: float = 90.0) -> str:
    """Non-streaming call with a HARD per-request timeout. Streaming does not reliably
    time out when a slow reasoning model trickles a huge discovery output, so a single
    call could hang the whole sweep for minutes. Non-streaming + an explicit timeout +
    max_retries=1 bounds every call to ~timeout seconds; on timeout/error return ''."""
    c = client.with_options(timeout=timeout, max_retries=1)
    base = dict(model=model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user}])
    try:
        try:
            msg = c.messages.create(temperature=0, **base)
        except anthropic.BadRequestError as e:
            if "temperature" in str(e).lower():
                msg = c.messages.create(**base)  # opus-4.8 / reasoning models reject temperature
            else:
                raise
        return "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", None) == "text")
    except Exception:
        return ""


def discover(client, model: str, system: str, batch_text: str) -> list[dict]:
    """Return [{field_name, description}] proposed by one model for one batch."""
    raw = _bounded_call(client, model, system, DISCOVERY_USER + batch_text, max_tokens=10000, timeout=90.0)
    out = []
    for name, desc in _extract_fields(raw):
        n = _norm(name)
        if n:
            out.append({"field_name": n, "description": desc})
    return out


JUDGE_PROMPT = """You are reviewing proposed EXTRACTION FIELDS for a patient-data research schema built
from Reddit chronic-illness posts. The schema already covers these fields (do not keep anything redundant
with them):
{known}

Models proposed these NEW candidate fields (name: description):
{numbered}

For EACH, decide:
- "keep": a distinct, well-defined, research-useful biomedical/clinical covariate that is NOT redundant
  with the existing schema or another proposal, and is plausibly extractable from patient text.
- "drop": redundant, too vague/broad, not biomedical, double-barreled, or not extractable.

Return ONLY JSON: {{"verdicts": [{{"field": "...", "verdict": "keep"}}]}}"""


def judge_fields(client, judge_model: str, known: list[str], field_descs: dict[str, str]) -> dict:
    names = sorted(field_descs)
    numbered = "\n".join(f"{i+1}. {n}: {field_descs[n][:160]}" for i, n in enumerate(names))
    prompt = JUDGE_PROMPT.format(known=", ".join(known), numbered=numbered)
    try:
        obj = parse_json_object(llm_call(client, prompt, model=judge_model, max_tokens=40 * len(names) + 400))
        verd = {}
        for v in obj.get("verdicts", []):
            f = _norm(v.get("field", ""))
            if f:
                verd[f] = "keep" if str(v.get("verdict", "")).lower().startswith("keep") else "drop"
        for n in names:
            verd.setdefault(n, "drop")
        return verd
    except (LLMParseError, Exception):
        return {n: "ungraded" for n in names}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--posts", type=int, default=30)
    ap.add_argument("--batch-chars", type=int, default=9000)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--judge", default="anthropic/claude-opus-4.8")
    ap.add_argument("--workers", type=int, default=40)
    ap.add_argument("--per-model", type=int, default=3)
    ap.add_argument("--out", type=Path, default=OUT_DIR / "j10_discovery_runs.json")
    ap.add_argument("--fresh", action="store_true", help="ignore/clear the resume checkpoint and start over")
    args = ap.parse_args()

    client = get_client()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    posts = json.loads(POSTS.read_text(encoding="utf-8"))[: args.posts]
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    known_fields = sorted(build_field_descriptions(schema).keys())
    system = build_discovery_prompt(known_fields, schema)
    batches = make_batches(posts, args.batch_chars)

    print(f"{len(posts)} posts -> {len(batches)} batches x {len(args.models)} models "
          f"| judge={args.judge} | temp={LLM_TEMPERATURE} | workers={args.workers}", flush=True)

    # Resume checkpoint: every completed (model, batch) is appended to a JSONL as it lands, so a
    # kill/hang never loses finished work — and a re-run (even with MORE models) skips what's done.
    partial = args.out.with_suffix(".partial.jsonl")
    if args.fresh and partial.exists():
        partial.unlink()
    done: dict = {}
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line); done[(r["model"], r["batch"])] = r
            except Exception:
                pass
    tasks = [(m, bi) for m in args.models for bi in range(len(batches)) if (m, bi) not in done]
    print(f"{len(done)} (model,batch) already done — resuming; {len(tasks)} to run", flush=True)

    _wlock = threading.Lock()

    def run_one(t):
        m, bi = t
        r = {"model": m, "batch": bi, "fields": discover(client, m, system, batches[bi])}
        with _wlock, partial.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(r) + "\n")
        return r

    new = parallel_map(run_one, tasks, workers=args.workers, per_key=args.per_model,
                       key=lambda t: t[0], progress="discovery")
    proposals = list(done.values()) + [r for r in new if r]

    # union of proposed fields (first description wins) for the judge
    descs: dict[str, str] = {}
    for p in proposals:
        for f in p["fields"]:
            descs.setdefault(f["field_name"], f["description"])
    verdicts = judge_fields(client, args.judge, known_fields, descs)

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "judgement": "10_variable_discovery",
        "temperature": LLM_TEMPERATURE,
        "candidate_models": args.models, "judge_model": args.judge,
        "n_posts": len(posts), "n_batches": len(batches), "n_known_fields": len(known_fields),
        "truth_sources": ["opus_judge"],
    }
    args.out.write_text(json.dumps(
        {"manifest": manifest, "proposals": proposals, "judge": verdicts,
         "known_fields": known_fields, "descriptions": descs}, indent=2), encoding="utf-8")
    print(f"Wrote {args.out} ({len(proposals)} model-batch proposals, {len(descs)} unique fields judged)", flush=True)


if __name__ == "__main__":
    main()
