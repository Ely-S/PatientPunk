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
import sys
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

from patientpunk._utils import MODEL_FAST
MODEL = MODEL_FAST

# Per-record character budget. User histories can be very long - we take
# the first MAX_CHARS characters, which usually covers enough posts to
# capture repeated self-mentions of age/sex.
MAX_CHARS = 8000

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


def call_haiku(client: anthropic.Anthropic, author_hash: str,
               source_type: str, text: str) -> dict:
    """Single API call. Returns a result dict."""
    base = {
        "author_hash": author_hash,
        "source_type": source_type,
        "age": None,
        "sex_gender": None,
        "location_country": None,
        "location_state": None,
        "confidence": "none",
        "evidence": "",
    }

    if not text.strip():
        base["evidence"] = "no text content"
        return base

    user_msg = (
        "Extract demographic information from the following Reddit "
        f"post(s) by a single author:\n\n{text}"
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()

        # Strip accidental markdown code fences
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(
                l for l in lines
                if not l.strip().startswith("```") and not l.strip() == "json"
            )

        data = json.loads(raw)
        base.update({
            "age": data.get("age"),
            "sex_gender": data.get("sex_gender"),
            "location_country": data.get("location_country"),
            "location_state": data.get("location_state"),
            "confidence": data.get("confidence", "low"),
            "evidence": str(data.get("evidence", ""))[:200],
        })
    except json.JSONDecodeError as e:
        base["confidence"] = "parse_error"
        base["evidence"] = f"JSON parse error: {e} | raw: {raw[:80]}"
    except Exception as e:
        base["confidence"] = "error"
        base["evidence"] = str(e)[:120]

    return base


def process_record(client, record, source_type, max_chars=MAX_CHARS):
    author_hash = record.get("author_hash", "unknown")
    text = build_text(record, source_type, max_chars=max_chars)
    return call_haiku(client, author_hash, source_type, text)


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
        default=Path(__file__).parent.parent.parent / "data" / "demographics.csv",
        help="Output CSV file path (default: data/demographics.csv)",
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

    print(f"\nProcessing {len(work_items)} records with {args.workers} workers...\n")

    results = []
    n = len(work_items)
    completed = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_item = {
            executor.submit(process_record, client, rec, src, max_chars): (rec, src)
            for rec, src in work_items
        }
        for future in as_completed(future_to_item):
            result = future.result()
            results.append(result)
            completed += 1

            age_str = str(result["age"]) if result["age"] is not None else "-"
            sex_str = result["sex_gender"] or "-"
            loc_str = result["location_country"] or "-"
            src_short = "post" if result["source_type"] == "subreddit_post" else "user"
            hash_short = (result["author_hash"] or "unknown")[:10]
            print(
                f"  [{completed:3d}/{n}] {src_short} {hash_short}..."
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
