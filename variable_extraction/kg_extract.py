#!/usr/bin/env python3
"""
Claims-based knowledge-graph extraction prototype (issue #90).

Extracts patient CLAIMS (a free-text statement in the author's words + typed keys +
a verbatim source span) into a SQLite tuple store, instead of forcing the LLM into
~40 fixed schema slots. Then compares the result head-to-head against the existing
flat extraction of the SAME posts.

    python kg_extract.py run --limit 20      # smoke test
    python kg_extract.py run                 # full corpus (default 1000 posts)
    python kg_extract.py compare             # KG vs flat report

The claim contract lives in kg_prompts (pydantic models -> JSON schema + instructions
+ validation), the tuple store in kg_store, the evaluation in kg_compare. This module
is the LLM call, the retry ladder, and the run loop.

Design principle (from the issue):
    Extraction creates claims. Normalization creates meaning. Analytics creates knowledge.
Normalization is deliberately NOT implemented -- entity_links is created and left empty.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import dspy
from dspy.utils.exceptions import AdapterParseError
from pydantic import TypeAdapter, ValidationError

from kg_compare import DEFAULT_BASELINE, cmd_compare
from kg_prompts import ENVELOPE, Claim, Edge, ExtractClaims, build_instructions
from kg_store import get_or_create_run, mark_failed, open_db, store_post
from patientpunk._utils import (
    LLM_PROVIDER,
    LLM_TEMPERATURE,
    MODEL_FAST,
    LLMResponseError,
    collect_texts_from_post,
    parse_json_response,
    resolve_llm_config,
)
from patientpunk.llm_cache import cached_completion

_HERE = Path(__file__).parent
_ROOT = _HERE.parent
DEFAULT_CORPUS = _ROOT / "output_deepseek_1000" / "subreddit_posts.json"
DEFAULT_OUT_DIR = _ROOT / "output_kg"

MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "8192"))
RETRY_DELAYS = [2, 5, 15]

# The model sometimes writes one of these instead of omitting a key it can't evidence
# (rule 2 asks it not to). Dropping them before validation makes an unevidenced key read
# as absent, rather than relying on prompt compliance alone.
PLACEHOLDER_VALUES = {"not specified", "unknown", "none mentioned", "none", "n/a", "unspecified"}


def _lm_kwargs(cfg: dict) -> tuple[str, dict]:
    """Map the repo's provider config onto a litellm model string + kwargs."""
    provider, model = cfg["provider"], cfg["model_fast"]
    kwargs: dict = {"api_key": cfg["api_key"] or "EMPTY"}
    if provider == "openai":
        name = f"openai/{model}"
        kwargs["api_base"] = cfg["base_url"] or "http://localhost:8000/v1"
        if cfg.get("service_tier"):
            kwargs["service_tier"] = cfg["service_tier"]
    elif provider == "openrouter":
        # MODEL_FAST is already "anthropic/claude-haiku-4.5"-style; litellm
        # knows OpenRouter's /v1 base URL itself. The provider default in
        # _utils is the Anthropic-shaped endpoint (no /v1), which litellm
        # must NOT receive -- only forward a base_url the user overrode.
        name = f"openrouter/{model}"
        if cfg["base_url"] and cfg["base_url"] != "https://openrouter.ai/api":
            kwargs["api_base"] = cfg["base_url"]
    else:
        name = f"anthropic/{model}"
        if cfg["base_url"]:
            kwargs["api_base"] = cfg["base_url"]
    return name, kwargs


# =============================================================================
# EXTRACTION
# =============================================================================

def _is_truncated(exc: BaseException) -> bool:
    return "truncated at max_tokens" in str(exc)


def _is_transient(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    name = type(exc).__name__
    # "provider returned null content" is a bare 200 with an empty body -- a
    # blip worth retrying as-is. Truncation is excluded: retrying the same
    # input at the same max_tokens would just truncate again (the caller
    # handles that by shrinking the input instead).
    return (status == 429 or (status is not None and 500 <= status < 600)
            or "Connection" in name or "Timeout" in name
            or (name == "LLMResponseError" and not _is_truncated(exc)))


def _finish_reason(lm: dspy.LM) -> str | None:
    if not lm.history:
        return None
    try:
        return lm.history[-1]["response"].choices[0].finish_reason
    except (AttributeError, IndexError, TypeError, KeyError):
        return None


def _truncated(model: str) -> LLMResponseError:
    return LLMResponseError(
        f"{model}: response truncated at max_tokens (raise LLM_MAX_TOKENS "
        f"or shrink the batch)")


def _classify(exc: Exception, lm: dspy.LM) -> Exception:
    """Map a DSPy parse failure onto the exception the retry ladder understands."""
    if not isinstance(exc, AdapterParseError):
        return exc
    if _finish_reason(lm) in ("length", "max_tokens"):
        return _truncated(MODEL_FAST)
    if "empty or null" in str(exc):
        # Bare 200 with an empty body -- a blip worth retrying as-is.
        return LLMResponseError(f"{MODEL_FAST}: provider returned null content")
    # Genuinely unparseable structured output -> ValueError so the caller's
    # hotter-temperature retry gets a shot at it.
    return ValueError(f"unparseable structured response: {str(exc)[:200]}")


def call_llm(extractor: dspy.Predict, cfg: dict, instructions: str,
             user_message: str, label: str = "?",
             temperature: float = LLM_TEMPERATURE) -> str:
    """One cached, retried LLM call. Only transient failures are retried."""
    model_name, lm_kwargs = _lm_kwargs(cfg)

    def _call() -> str:
        for attempt, delay in enumerate([0, *RETRY_DELAYS]):
            if delay:
                time.sleep(delay)
            # A fresh LM per attempt keeps lm.history unambiguous (this runs on
            # many threads) and carries no state worth keeping -- DSPy's own
            # cache is off; the disk cache below is the one that matters.
            lm = dspy.LM(model_name, temperature=temperature, max_tokens=MAX_TOKENS,
                         cache=False, num_retries=0, **lm_kwargs)
            try:
                with dspy.context(lm=lm, adapter=dspy.JSONAdapter()):
                    pred = extractor(post_text=user_message)
                # finish_reason is checked even on a clean parse: json_repair
                # can silently close a truncated JSON payload, which would
                # otherwise be cached as a quietly incomplete result.
                if _finish_reason(lm) in ("length", "max_tokens"):
                    raise _truncated(MODEL_FAST)
                return json.dumps({
                    "claims": [c.model_dump() for c in pred.claims],
                    "edges": [e.model_dump(by_alias=True) for e in pred.edges],
                }, ensure_ascii=False)
            except Exception as e:
                err = _classify(e, lm)
                print(f"  [retry] {label} attempt {attempt + 1}: {type(err).__name__}: "
                      f"{str(err)[:160]}", flush=True)
                if not _is_transient(err) or attempt == len(RETRY_DELAYS):
                    if err is e:
                        raise
                    raise err from e
        return ""

    return cached_completion(
        provider=LLM_PROVIDER, model=MODEL_FAST, system=instructions,
        prompt=user_message, temperature=temperature, max_tokens=MAX_TOKENS,
        call_fn=_call,
    )


_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text.lower()).strip()


_CLAIM = TypeAdapter(Claim)


def _drop_empty(item: dict) -> dict:
    """Strip empty and placeholder values so an unevidenced key reads as absent."""
    return {k: v for k, v in item.items()
            if v not in (None, "", [], {})
            and not (isinstance(v, str) and v.strip().lower() in PLACEHOLDER_VALUES)}


def _reject_key(item: dict, exc: ValidationError) -> str:
    """A stable stats key for a claim the models refused, e.g. `invalid:symptom.symptom_text`."""
    ctype = str(item.get("claim_type") or "?").strip().lower()[:24]
    err = exc.errors()[0]
    if err["type"].startswith("union_tag"):
        return f"bad_claim_type:{ctype}"
    return f"invalid:{ctype}.{err['loc'][-1] if err['loc'] else '?'}"


def parse_claims(raw: str, post_text: str, stats: Counter) -> tuple[list[dict], list[dict]]:
    """Validate an LLM response into (claims, edges). Everything rejected is counted.

    Pure function of (response JSON, post text) -- the seam the regression tests use.
    Shape, claim type, required keys and confidence are enforced by the models in
    kg_prompts; what is left here is what types cannot express: placeholder stripping,
    span grounding, and edges that point at claims we did not keep.
    """
    data = parse_json_response(raw)
    if not isinstance(data, dict):
        raise ValueError("response was not a JSON object")

    norm_post = _norm(post_text)
    claims: list[dict] = []
    for item in data.get("claims") or []:
        if not isinstance(item, dict):
            stats["claim_not_object"] += 1
            continue
        try:
            claim = _CLAIM.validate_python(_drop_empty(item))
        except ValidationError as e:
            stats[_reject_key(item, e)] += 1
            continue
        # Unknown keys are KEPT (they are signal about what the model wants to say)
        # but counted so prompt/schema drift is visible in the run summary.
        for key in claim.model_extra or {}:
            stats[f"extra_key:{claim.claim_type}.{key}"] += 1
        span = claim.source_span.strip()
        claims.append({
            "local_id": claim.local_id or f"c{len(claims) + 1}",
            "claim_type": claim.claim_type,
            "source_span": span,
            "confidence": claim.confidence,
            "payload": claim.model_dump(exclude_none=True, exclude=set(ENVELOPE)),
            "span_grounded": int(bool(span) and _norm(span) in norm_post),
        })

    by_local = {c["local_id"] for c in claims}
    edges: list[dict] = []
    for item in data.get("edges") or []:
        if not isinstance(item, dict):
            continue
        try:
            edge = Edge.model_validate(item)
        except ValidationError:
            stats[f"bad_relation:{str(item.get('relation'))[:24]}"] += 1
            continue
        if edge.from_ not in by_local or edge.to not in by_local or edge.from_ == edge.to:
            stats["dangling_edge"] += 1
            continue
        edges.append({"from": edge.from_, "to": edge.to, "relation": edge.relation,
                      "confidence": edge.confidence})

    return claims, edges



def cmd_run(args: argparse.Namespace) -> None:
    posts = json.loads(args.corpus.read_text(encoding="utf-8"))
    if args.limit:
        posts = posts[:args.limit]
    posts = [p for p in posts if p.get("author_hash")]

    instructions = build_instructions()
    config = {
        "provider": LLM_PROVIDER, "model": MODEL_FAST, "temperature": LLM_TEMPERATURE,
        "framework": "dspy",
        "prompt_sha": hashlib.sha256(instructions.encode()).hexdigest()[:16],
        "corpus": str(args.corpus), "max_chars": args.max_chars,
    }
    conn = open_db(args.db)
    run_id, resumed = get_or_create_run(conn, config)
    done = {r[0] for r in conn.execute(
        "SELECT post_id FROM post_status WHERE run_id = ? AND status = 'ok'", (run_id,))}
    todo = [p for p in posts if p.get("post_id") not in done]

    print(f"\nKG extraction  run_id={run_id}{' (resumed)' if resumed else ''}  "
          f"model={MODEL_FAST} via {LLM_PROVIDER}")
    print(f"  corpus: {args.corpus}  ({len(posts)} posts, {len(done)} already done)")
    print(f"  db:     {args.db}")
    print(f"  {len(todo)} to process with {args.workers} workers\n")
    if not todo:
        print("  nothing to do.")
        return

    cfg = resolve_llm_config()
    extractor = dspy.Predict(ExtractClaims.with_instructions(instructions))
    lock = threading.Lock()
    stats: Counter = Counter()
    counts = Counter()
    t0 = time.time()

    def work(post: dict) -> int:
        full_text = "\n\n".join(collect_texts_from_post(post))
        if not full_text.strip():
            mark_failed(conn, lock, run_id, post, "empty text")
            return 0
        label = post.get("post_id", "?")
        max_chars = args.max_chars
        hot_retry_used = False
        while True:
            body = full_text[:max_chars]
            try:
                temp = LLM_TEMPERATURE + 0.3 if hot_retry_used else LLM_TEMPERATURE
                raw = call_llm(extractor, cfg, instructions, body, label=label,
                               temperature=temp)
                claims, edges = parse_claims(raw, body, stats)
            except Exception as e:
                # Long posts can generate more claims than fit in MAX_TOKENS output;
                # shrinking the input gives the model less to report on.
                if _is_truncated(e) and max_chars > 1000:
                    max_chars //= 2
                    continue
                # A bad JSON parse is often a one-off formatting slip; re-asking
                # at a hotter temperature (a fresh cache key) breaks the loop.
                if isinstance(e, (ValueError, json.JSONDecodeError)) and not hot_retry_used:
                    hot_retry_used = True
                    continue
                raise
            store_post(conn, lock, run_id, post, claims, edges)
            return len(claims)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(work, p): p for p in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            post = futures[fut]
            try:
                n = fut.result()
                counts["ok"] += 1
                counts["claims"] += n
            except Exception as e:
                counts["failed"] += 1
                mark_failed(conn, lock, run_id, post, f"{type(e).__name__}: {e}")
                print(f"  ! {post.get('post_id')}: {type(e).__name__}: {str(e)[:160]}")
            if i % 50 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} posts  {counts['claims']} claims  "
                      f"{counts['failed']} failed  ({time.time() - t0:.0f}s)", flush=True)

    print(f"\nDone in {time.time() - t0:.0f}s: {counts['ok']} ok, {counts['failed']} failed, "
          f"{counts['claims']} claims")
    for ctype, n in conn.execute(
            "SELECT claim_type, COUNT(*) FROM claims WHERE run_id=? GROUP BY 1 ORDER BY 2 DESC",
            (run_id,)):
        print(f"    {ctype:20} {n}")
    n_edges = conn.execute(
        "SELECT COUNT(*) FROM claim_edges WHERE run_id=?", (run_id,)).fetchone()[0]
    grounded = conn.execute(
        "SELECT AVG(span_grounded) FROM claims WHERE run_id=?", (run_id,)).fetchone()[0] or 0
    print(f"    edges                {n_edges}")
    print(f"    verbatim spans       {grounded * 100:.1f}%")
    if stats:
        print("\n  rejected / unexpected (top 15):")
        for key, n in stats.most_common(15):
            print(f"    {key:44} {n}")
    print(f"\n  next: python {Path(__file__).name} compare --db {args.db}")


# =============================================================================

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Extract claims into the tuple store.")
    r.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    r.add_argument("--db", type=Path, default=DEFAULT_OUT_DIR / "kg.db")
    r.add_argument("--limit", type=int, default=None)
    r.add_argument("--workers", type=int, default=10)
    r.add_argument("--max-chars", type=int, default=8000)
    r.set_defaults(fn=cmd_run)

    c = sub.add_parser("compare", help="Compare the claim graph to the flat extraction.")
    c.add_argument("--db", type=Path, default=DEFAULT_OUT_DIR / "kg.db")
    c.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    c.add_argument("--run-id", type=int, default=None)
    c.add_argument("--out", type=Path, default=None)
    c.set_defaults(fn=cmd_compare)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
