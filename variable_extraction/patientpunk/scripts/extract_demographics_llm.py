#!/usr/bin/env python3
"""

LLM-only demographic extraction for PatientPunk.

Extracts age, sex/gender, and location from:
  - subreddit_posts.json  (one record per post author)
  - users/*.json          (one record per user, full history)

No regex. Haiku reads the text and returns only what the author states
directly about themselves. The prompt explicitly instructs the model to
ignore mentions of other people.

Output: output/demographics.csv

Usage:
    # Both posts and user histories (default)
    python extract_demographics_llm.py

    # Explicit input directory
    python extract_demographics_llm.py --input-dir ../../reddit_sample_data

    # Posts only
    python extract_demographics_llm.py --posts-only

    # User histories only
    python extract_demographics_llm.py --users-only

    # Custom output path
    python extract_demographics_llm.py --output ../../reddit_posts_only/demographics.csv
"""


import argparse
import csv
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)  # PatientPunk/.env (canonical)
load_dotenv(Path(__file__).parent.parent / ".env", override=True)       # variable_extraction/.env (fallback)

# Shared qualitative coding standards - injected into the system prompt so the
# model applies research-grade rigour to demographic coding decisions.
sys.path.insert(0, str(Path(__file__).parent.parent))
from patientpunk.qualitative_standards import DEMOGRAPHIC_STANDARDS

from patientpunk._utils import LLM_TEMPERATURE, MODEL_FAST, split_retry_batch
MODEL = MODEL_FAST

# Per-record character budget. User histories can be very long - we take
# the first MAX_CHARS characters, which usually covers enough posts to
# capture repeated self-mentions of age/sex.
MAX_CHARS = 8000
# Multi-record array prompts mis-split when a record's text holds several posts
# (model emits one object per post -> count mismatch); default to 1 record/call
# via the single-object path in _call_haiku_batch_raw. (>1 still works as a
# best-effort batch with split_retry_batch falling back to single calls.)
BATCH_SIZE = 1  # records per LLM call

SYSTEM_PROMPT = f"""\
You are a demographic data extractor for a medical research project about long COVID.

Your task: read one or more Reddit posts written by a SINGLE author and extract only
the demographic information that author states directly about themselves.

{DEMOGRAPHIC_STANDARDS}

Rules:
- Extract ONLY age, sex/gender, and location the author states about THEMSELVES.
- Ignore all mentions of other people (e.g. "my 65-year-old father", "she said").
- Do not guess or infer from indirect clues (e.g. a username, a pronoun used by
  someone replying to them).
- If the author explicitly writes "I'm 25M" or "I am a 34-year-old woman" or
  "I live in California" - capture that.
- For user histories across multiple posts: the author often repeats their
  demographics. Use the most explicit and consistent statement.
- Return null for any field you cannot find with reasonable confidence.

Respond with ONLY valid JSON - no explanation, no markdown fences:
{{
  "age": <integer or null>,
  "sex_gender": <"male" | "female" | "non-binary" | other string | null>,
  "location_country": <country name or null>,
  "location_state": <US state name or abbreviation or null>,
  "confidence": <"high" | "medium" | "low">,
  "evidence": <one short quote or phrase that led to each finding, max 120 chars>
}}\
"""


def build_text(record: dict, source_type: str, max_chars: int = MAX_CHARS) -> str:
    """Assemble the text block to send to the LLM."""
    if source_type == "subreddit_post":
        parts = []
        title = record.get("title", "")
        body = record.get("body", "") or ""
        if title:
            parts.append(f"Post title: {title}")
        if body:
            parts.append(f"Post body:\n{body}")
        # Only include comments written by the same author
        author_hash = record.get("author_hash")
        for comment in record.get("comments", []):
            if comment.get("author_hash") == author_hash:
                cb = comment.get("body", "") or ""
                if cb:
                    parts.append(f"Author comment:\n{cb}")
        text = "\n\n".join(parts)

    else:  # user_history
        posts = record.get("posts", [])
        parts = []
        for post in posts:
            subreddit = post.get("subreddit", "")
            title = post.get("title", "") or ""
            body = (post.get("body", "") or "").strip()
            if body in ("[removed]", "[deleted]", ""):
                body = ""
            chunk = f"[r/{subreddit}] {title}"
            if body:
                chunk += f"\n{body}"
            parts.append(chunk.strip())
        text = "\n\n---\n\n".join(p for p in parts if p)

    # Truncate to keep token costs predictable
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[... truncated]"
    return text


def _make_empty_result(author_hash: str, source_type: str, evidence: str = "") -> dict:
    return {
        "author_hash": author_hash,
        "source_type": source_type,
        "age": None,
        "sex_gender": None,
        "location_country": None,
        "location_state": None,
        "confidence": "none",
        "evidence": evidence,
    }


def _strip_markdown_fences(raw: str) -> str:
    # Handles both multi-line fences (```json\n{...}\n```) and SINGLE-LINE
    # fences (```json{...}```). The old splitlines() filter blanked the
    # single-line form (its only line starts with ```), breaking the default
    # single-record path; _parse_one_object's {...} span also handles oddities.
    raw = raw.strip()
    if raw.startswith("```"):
        nl = raw.find("\n")
        if nl != -1:
            raw = raw[nl + 1:]          # multi-line: drop the ```lang opening line
        else:
            raw = raw[3:]               # single-line: drop the opening ```
            if raw[:4].lower() == "json":
                raw = raw[4:]           # ... and the json language tag
        if raw.endswith("```"):
            raw = raw[:-3]
    return raw.strip()


def _parse_one_object(text: str) -> dict | None:
    """Tolerant single-object JSON parse: strip fences, then isolate the {...}
    span so leading/trailing prose doesn't break json.loads."""
    text = _strip_markdown_fences(text.strip())
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            obj = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    return obj if isinstance(obj, dict) else None


_RETRY_DELAYS = [2, 5, 15, 30]


def _create_with_retry(client, **kwargs):
    """client.messages.create with provider-agnostic retry/backoff on transient
    errors (429 / 5xx / connection / timeout) -- parity with
    llm_extract.call_haiku, so a long demographics job survives a temporary blip
    instead of failing the batch. Non-transient errors re-raise immediately."""
    for attempt, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            return client.messages.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - provider-agnostic transient check
            status = getattr(exc, "status_code", None)
            if status is None:
                status = getattr(getattr(exc, "response", None), "status_code", None)
            name = type(exc).__name__
            transient = (
                status == 429
                or (status is not None and 500 <= status < 600)
                or "Connection" in name or "Timeout" in name
            )
            if not transient or attempt == len(_RETRY_DELAYS):
                raise


def _call_haiku_batch_raw(client, items: list[dict]) -> list[dict]:
    """Send record(s) in one API call. Returns a list of parsed dicts.

    Each item must have keys: author_hash, source_type, text.

    A single record (the default, and the split_retry_batch fallback) asks for
    ONE object via the system prompt's native format and re-asks at escalating
    temperature on a parse failure -- no array/count ambiguity and no multi-post
    mis-splitting. Multiple records use the JSON-array path below.
    """
    if len(items) == 1:
        for temp in (LLM_TEMPERATURE, 0.7, 1.0):
            response = _create_with_retry(
                client,
                model=MODEL,
                temperature=temp,
                max_tokens=300,
                system=[{"type": "text", "text": SYSTEM_PROMPT,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": items[0]["text"]}],
            )
            parsed = _parse_one_object(response.content[0].text)
            if parsed is not None:
                return [parsed]
        raise ValueError("could not parse single-record demographics response")

    msg = (
        "Extract demographic information from the following Reddit records. "
        "Each record is by a DIFFERENT author.\n\n"
        "Return a JSON array with one result object per record, in the same "
        "order. Each object has: age, sex_gender, location_country, "
        "location_state, confidence, evidence.\n\n"
    )
    for i, item in enumerate(items, 1):
        # Collapse bare '---' rule lines so they don't read as the
        # '--- Record N ---' delimiter and split one record into several objects.
        text = re.sub(r"(?m)^[ \t]*-{3,}[ \t]*$", "", item["text"])
        msg += f"--- Record {i} ---\n{text}\n\n"

    response = _create_with_retry(
        client,
        model=MODEL,
        temperature=LLM_TEMPERATURE,
        max_tokens=len(items) * 300,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": msg}],
    )
    # Reuse the canonical (single-line-fence-safe) stripper, then isolate the
    # JSON array span so leading/trailing prose doesn't break json.loads.
    raw = _strip_markdown_fences(response.content[0].text)
    start, end = raw.find("["), raw.rfind("]")
    if start != -1 and end > start:
        raw = raw[start:end + 1]
    results = json.loads(raw)
    if not isinstance(results, list):
        raise ValueError(f"Expected JSON array, got {type(results).__name__}")
    if len(results) != len(items):
        raise ValueError(f"Expected {len(items)} results, got {len(results)}")
    return results


def process_batch(client, batch: list[tuple], max_chars=MAX_CHARS) -> list[dict]:
    """Process a batch of (record, source_type) tuples via multi-item LLM call.

    Uses split_retry_batch for automatic retry on parse failures.
    """
    # Prepare items with text
    items = []
    for record, source_type in batch:
        author_hash = record.get("author_hash", "unknown")
        text = build_text(record, source_type, max_chars=max_chars)
        items.append({
            "author_hash": author_hash,
            "source_type": source_type,
            "text": text,
        })

    # Skip-empty items (no text)
    non_empty_indices = [i for i, it in enumerate(items) if it["text"].strip()]
    if not non_empty_indices:
        return [_make_empty_result(it["author_hash"], it["source_type"], "no text content")
                for it in items]

    non_empty_items = [items[i] for i in non_empty_indices]

    def call_fn(sub_items):
        return _call_haiku_batch_raw(client, sub_items)

    try:
        raw_results = split_retry_batch(call_fn, non_empty_items)
    except Exception as e:
        # Total failure — return error results
        return [_make_empty_result(it["author_hash"], it["source_type"], f"batch error: {e}")
                for it in items]

    # Map results back, filling in empties
    output = [_make_empty_result(it["author_hash"], it["source_type"], "no text content")
              for it in items]
    for idx, raw in zip(non_empty_indices, raw_results):
        it = items[idx]
        result = _make_empty_result(it["author_hash"], it["source_type"])
        if raw is not None and isinstance(raw, dict):
            result.update({
                "age": raw.get("age"),
                "sex_gender": raw.get("sex_gender"),
                "location_country": raw.get("location_country"),
                "location_state": raw.get("location_state"),
                "confidence": raw.get("confidence", "low"),
                "evidence": str(raw.get("evidence", ""))[:200],
            })
        else:
            result["confidence"] = "error"
            result["evidence"] = "failed to parse after retries"
        output[idx] = result
    return output


def main():
    parser = argparse.ArgumentParser(
        description="LLM-only demographic extraction (age, sex/gender, location).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python extract_demographics_llm.py
  python extract_demographics_llm.py --input-dir ../../reddit_sample_data
  python extract_demographics_llm.py --posts-only
  python extract_demographics_llm.py --users-only
  python extract_demographics_llm.py --output ../../reddit_posts_only/demographics.csv
        """,
    )
    parser.add_argument(
        "--input-dir", type=Path,
        default=Path(__file__).parent.parent.parent / "reddit_sample_data",
        help="Directory containing subreddit_posts.json and/or users/ (default: reddit_sample_data/)",
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).parent.parent.parent / "output" / "demographics.csv",
        help="Output CSV file path (default: output/demographics.csv)",
    )
    parser.add_argument(
        "--workers", type=int, default=10,
        help="Concurrent API workers (default: 10)",
    )
    parser.add_argument(
        "--posts-only", action="store_true",
        help="Only process subreddit_posts.json, skip users/",
    )
    parser.add_argument(
        "--users-only", action="store_true",
        help="Only process users/*.json, skip subreddit_posts.json",
    )
    parser.add_argument(
        "--max-chars", type=int, default=MAX_CHARS,
        help=f"Max characters of text to send per record (default: {MAX_CHARS})",
    )
    args = parser.parse_args()

    max_chars = args.max_chars

    from patientpunk._utils import get_llm_client
    client = get_llm_client()
    work_items = []  # list of (record_dict, source_type_str)

    # --- Load subreddit posts ---
    if not args.users_only:
        posts_file = args.input_dir / "subreddit_posts.json"
        if posts_file.exists():
            posts = json.loads(posts_file.read_text(encoding="utf-8"))
            print(f"  Posts loaded        : {len(posts)} from {posts_file.name}")
            for post in posts:
                work_items.append((post, "subreddit_post"))
        else:
            print(f"  Warning: {posts_file} not found - skipping posts")

    # --- Load user history files ---
    if not args.posts_only:
        users_dir = args.input_dir / "users"
        if users_dir.exists():
            user_files = sorted(users_dir.glob("*.json"))
            print(f"  User histories loaded: {len(user_files)} files from {users_dir.name}/")
            for uf in user_files:
                try:
                    data = json.loads(uf.read_text(encoding="utf-8"))
                    work_items.append((data, "user_history"))
                except Exception as e:
                    print(f"    Warning: could not read {uf.name}: {e}")
        else:
            print(f"  Warning: {users_dir} not found - skipping user histories")

    # Chunk work items into batches
    batches = [
        work_items[i:i + BATCH_SIZE]
        for i in range(0, len(work_items), BATCH_SIZE)
    ]
    n_batches = len(batches)
    print(
        f"\nProcessing {len(work_items)} records in {n_batches} batches "
        f"(batch size {BATCH_SIZE}) with {args.workers} workers...\n"
    )

    results = []
    completed = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_batch = {
            executor.submit(process_batch, client, batch, max_chars): batch
            for batch in batches
        }
        for future in as_completed(future_to_batch):
            batch_results = future.result()
            results.extend(batch_results)
            completed += 1

            for result in batch_results:
                age_str = str(result["age"]) if result["age"] is not None else "-"
                sex_str = result["sex_gender"] or "-"
                loc_str = result["location_country"] or "-"
                src_short = "post" if result["source_type"] == "subreddit_post" else "user"
                hash_short = (result["author_hash"] or "unknown")[:10]
                print(
                    f"  [batch {completed}/{n_batches}] {src_short} {hash_short}..."
                    f"  age={age_str:<4} sex={sex_str:<12} loc={loc_str}"
                )

    # Sort: subreddit posts first, then user histories; within each by author_hash
    results.sort(key=lambda r: (0 if r["source_type"] == "subreddit_post" else 1,
                                 r["author_hash"] or ""))

    # Write CSV
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "author_hash", "source_type",
        "age", "sex_gender", "location_country", "location_state",
        "confidence", "evidence",
    ]
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # --- Summary ---
    posts_results = [r for r in results if r["source_type"] == "subreddit_post"]
    user_results  = [r for r in results if r["source_type"] == "user_history"]

    def coverage(lst, field):
        if not lst:
            return "n/a"
        n_filled = sum(1 for r in lst if r[field] is not None)
        return f"{n_filled}/{len(lst)} ({100 * n_filled // len(lst)}%)"

    print(f"\n{'='*55}")
    print(f"  SUMMARY")
    print(f"{'='*55}")
    print(f"  Total records      : {len(results)}")
    print(f"  Subreddit posts    : {len(posts_results)}")
    print(f"  User histories     : {len(user_results)}")
    errors = sum(1 for r in results if r["confidence"] in ("error", "parse_error"))
    print(f"  Errors             : {errors}")
    print()
    print(f"  {'Field':<22} {'Posts':>10}  {'Users':>10}  {'Total':>10}")
    print(f"  {'-'*54}")
    for field in ("age", "sex_gender", "location_country"):
        print(
            f"  {field:<22} "
            f"{coverage(posts_results, field):>10}  "
            f"{coverage(user_results, field):>10}  "
            f"{coverage(results, field):>10}"
        )
    print(f"{'='*55}")
    print(f"\n  Output: {args.output}\n")


if __name__ == "__main__":
    main()
