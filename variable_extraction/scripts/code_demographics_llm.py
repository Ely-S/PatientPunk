#!/usr/bin/env python3
"""

Inductive + deductive demographic coder for PatientPunk.

Performs structured qualitative coding of demographic information from
patient-authored Reddit text using Claude Haiku.  Supports two complementary
coding approaches:

  DEDUCTIVE (top-down): Extract predefined demographic fields - age,
    sex/gender, location_country, location_state - from author self-reports.

  INDUCTIVE (bottom-up): Discover NEW demographic categories that emerge
    from the data - ethnicity, occupation, disability status, insurance type,
    education level, etc. - without a predefined codebook.

Both approaches enforce a strict self-reference constraint: only demographics
the author states about themselves are extracted.

Usage:
    # Both modes (default)
    python code_demographics_llm.py --input-dir ../../reddit_sample_data

    # Deductive only (same as extract_demographics_llm.py)
    python code_demographics_llm.py --input-dir ../../reddit_sample_data --mode deductive

    # Inductive only (discovery)
    python code_demographics_llm.py --input-dir ../../reddit_sample_data --mode inductive

    # Posts only / users only
    python code_demographics_llm.py --input-dir ../../reddit_sample_data --posts-only
    python code_demographics_llm.py --input-dir ../../reddit_sample_data --users-only

Output:
    {output-dir}/demographics_deductive.csv   - predefined fields (deductive mode)
    {output-dir}/demographics_inductive.json  - per-record discovered categories (inductive mode)
    {output-dir}/demographics_codebook.json   - aggregated category frequencies (inductive mode)

Requires:
    pip install anthropic python-dotenv
"""


import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import anthropic
from dotenv import load_dotenv

# Load API key: project root first, then local fallback.
load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# Shared qualitative coding standards.
sys.path.insert(0, str(Path(__file__).parent.parent))
from patientpunk.qualitative_standards import (
    DEMOGRAPHIC_STANDARDS,
    INDUCTIVE_DEMOGRAPHIC_STANDARDS,
)

from patientpunk._utils import MODEL_FAST
MODEL = MODEL_FAST
MAX_CHARS = 8000


# =============================================================================
# PROMPTS
# =============================================================================

def build_system_prompt(mode: str) -> str:
    """Build the system prompt based on coding mode."""

    base_context = (
        "You are a demographic data coder for the PatientPunk medical research "
        "project studying long COVID.  You read Reddit posts written by a SINGLE "
        "author and code demographic information using rigorous qualitative "
        "research methods.\n\n"
    )

    if mode == "deductive":
        return f"""{base_context}{DEMOGRAPHIC_STANDARDS}

TASK: DEDUCTIVE CODING - extract these predefined demographic fields:

Rules:
- Extract ONLY what the author states about THEMSELVES.
- Ignore all mentions of other people.
- Do not guess or infer from indirect clues.
- For user histories across multiple posts: use the most explicit, consistent statement.
- Return null for any field you cannot find with reasonable confidence.

Respond with ONLY valid JSON - no explanation, no markdown fences:
{{
  "age": <integer or null>,
  "sex_gender": <"male" | "female" | "non-binary" | other string | null>,
  "location_country": <country name or null>,
  "location_state": <US state name or abbreviation or null>,
  "confidence": <"high" | "medium" | "low">,
  "evidence": <shortest quote supporting your extractions, max 120 chars>
}}"""

    elif mode == "inductive":
        return f"""{base_context}{INDUCTIVE_DEMOGRAPHIC_STANDARDS}

TASK: INDUCTIVE CODING - discover demographic categories from this text.

Do NOT extract age, sex/gender, or location (those are handled separately).
Instead, identify OTHER demographic characteristics the author mentions about
themselves: occupation, education, ethnicity, disability status, insurance,
marital status, veteran status, caregiver role, etc.

Respond with ONLY valid JSON - no explanation, no markdown fences:
{{
  "discovered_demographics": [
    {{
      "field_name": "snake_case_name (e.g. occupation_sector, marital_status)",
      "value": "short categorical label (1-3 words)",
      "evidence": "exact quote from text (max 120 chars)",
      "confidence": "high | medium | low"
    }}
  ]
}}

Return {{"discovered_demographics": []}} if no demographic self-reports are found.
Do NOT return demographics about other people.
Do NOT return clinical information (symptoms, medications, diagnoses)."""

    else:  # both
        return f"""{base_context}{DEMOGRAPHIC_STANDARDS}

{INDUCTIVE_DEMOGRAPHIC_STANDARDS}

TASK: COMBINED DEDUCTIVE + INDUCTIVE DEMOGRAPHIC CODING

Part 1 - DEDUCTIVE: Extract these predefined fields:
  age, sex_gender, location_country, location_state

Part 2 -- INDUCTIVE: Discover OTHER demographic categories the author mentions
about themselves (e.g. occupation, education, ethnicity, disability status,
insurance type, marital status, veteran status, caregiver role).
Do NOT re-extract age, sex/gender, or location in the inductive section.
Do NOT include clinical information (symptoms, medications, diagnoses).

Rules (apply to BOTH parts):
- Extract ONLY what the author states about THEMSELVES.
- Ignore all mentions of other people.
- Do not guess or infer from indirect clues.
- For user histories: use the most explicit, consistent statement.
- Return null / empty list when no evidence exists.

Respond with ONLY valid JSON - no explanation, no markdown fences:
{{
  "age": <integer or null>,
  "sex_gender": <"male" | "female" | "non-binary" | other string | null>,
  "location_country": <country name or null>,
  "location_state": <US state name or abbreviation or null>,
  "confidence": <"high" | "medium" | "low">,
  "evidence": <shortest quote for deductive fields, max 120 chars>,
  "discovered_demographics": [
    {{
      "field_name": "snake_case_name",
      "value": "short categorical label (1-3 words)",
      "evidence": "exact quote from text (max 120 chars)",
      "confidence": "high | medium | low"
    }}
  ]
}}"""


# =============================================================================
# TEXT ASSEMBLY
# =============================================================================

def build_text(record: dict, source_type: str, max_chars: int = MAX_CHARS) -> str:
    """Assemble the text block to send to the LLM."""
    if source_type == "subreddit_post":
        parts = []
        title = record.get("title", "")
        body = record.get("body", "") or ""
        if title:
            parts.append(f"Post title: {title}")
        if body and body not in ("[removed]", "[deleted]"):
            parts.append(f"Post body:\n{body}")
        author_hash = record.get("author_hash")
        for comment in record.get("comments", []):
            if comment.get("author_hash") == author_hash:
                cb = comment.get("body", "") or ""
                if cb and cb not in ("[removed]", "[deleted]"):
                    parts.append(f"Author comment:\n{cb}")
        text = "\n\n".join(parts)
    else:  # user_history
        parts = []
        for post in record.get("posts", []):
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

    if len(text) > max_chars:
        text = text[:max_chars] + "\n[... truncated]"
    return text


# =============================================================================
# API CALL
# =============================================================================

def call_haiku(
    client: anthropic.Anthropic,
    system_prompt: str,
    text: str,
    author_hash: str,
    source_type: str,
    mode: str,
) -> dict:
    """Single API call.  Returns a result dict."""
    base = {
        "author_hash": author_hash,
        "source_type": source_type,
    }

    if not text.strip():
        base["error"] = "no text content"
        if mode in ("deductive", "both"):
            base.update(age=None, sex_gender=None, location_country=None,
                        location_state=None, confidence="none", evidence="")
        if mode in ("inductive", "both"):
            base["discovered_demographics"] = []
        return base

    user_msg = (
        "Code demographic information from the following Reddit "
        f"post(s) by a single author:\n\n{text}"
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=800,  # larger than deductive-only to allow discoveries
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()

        # Strip accidental markdown code fences
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(
                l for l in lines
                if not l.strip().startswith("```") and l.strip() != "json"
            )

        data = json.loads(raw)

        if mode in ("deductive", "both"):
            base.update({
                "age": data.get("age"),
                "sex_gender": data.get("sex_gender"),
                "location_country": data.get("location_country"),
                "location_state": data.get("location_state"),
                "confidence": data.get("confidence", "low"),
                "evidence": str(data.get("evidence", ""))[:200],
            })
        if mode in ("inductive", "both"):
            base["discovered_demographics"] = data.get("discovered_demographics", [])

    except json.JSONDecodeError as e:
        base["error"] = f"JSON parse error: {e}"
        if mode in ("deductive", "both"):
            base.update(age=None, sex_gender=None, location_country=None,
                        location_state=None, confidence="parse_error", evidence="")
        if mode in ("inductive", "both"):
            base["discovered_demographics"] = []
    except Exception as e:
        base["error"] = str(e)[:200]
        if mode in ("deductive", "both"):
            base.update(age=None, sex_gender=None, location_country=None,
                        location_state=None, confidence="error", evidence="")
        if mode in ("inductive", "both"):
            base["discovered_demographics"] = []

    return base


# =============================================================================
# CODEBOOK AGGREGATION (inductive mode)
# =============================================================================

def build_codebook(results: list[dict]) -> dict:
    """Aggregate discovered demographic categories across all records.

    Returns a dict mapping field_name → {description, values, count, examples}.
    """
    codebook: dict[str, dict] = {}
    for result in results:
        for disc in result.get("discovered_demographics", []):
            fname = disc.get("field_name", "").strip()
            if not fname:
                continue
            value = (disc.get("value") or "").strip()
            evidence = (disc.get("evidence") or "").strip()
            confidence = disc.get("confidence", "low")

            if fname not in codebook:
                codebook[fname] = {
                    "field_name": fname,
                    "record_count": 0,
                    "values": defaultdict(int),
                    "examples": [],
                }
            entry = codebook[fname]
            entry["record_count"] += 1
            if value:
                entry["values"][value] += 1
            if evidence and len(entry["examples"]) < 5:
                entry["examples"].append({
                    "value": value,
                    "evidence": evidence,
                    "confidence": confidence,
                    "author_hash": result.get("author_hash", "")[:10],
                })

    # Convert defaultdicts to plain dicts and sort by frequency
    for entry in codebook.values():
        entry["values"] = dict(
            sorted(entry["values"].items(), key=lambda x: -x[1])
        )
        entry["unique_values"] = len(entry["values"])

    # Sort codebook by record count descending
    sorted_codebook = dict(
        sorted(codebook.items(), key=lambda x: -x[1]["record_count"])
    )
    return sorted_codebook


# =============================================================================
# OUTPUT WRITERS
# =============================================================================

def write_deductive_csv(results: list[dict], output_path: Path) -> None:
    """Write deductive demographics to CSV."""
    fieldnames = [
        "author_hash", "source_type", "age", "sex_gender",
        "location_country", "location_state", "confidence", "evidence",
    ]
    rows = sorted(results, key=lambda r: (
        0 if r.get("source_type") == "subreddit_post" else 1,
        r.get("author_hash") or "",
    ))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"\n  Deductive CSV: {output_path} ({len(rows)} rows)")


def write_inductive_json(results: list[dict], output_path: Path) -> None:
    """Write per-record inductive discoveries to JSON."""
    records = []
    for r in results:
        discoveries = r.get("discovered_demographics", [])
        if discoveries:
            records.append({
                "author_hash": r.get("author_hash", ""),
                "source_type": r.get("source_type", ""),
                "discovered_demographics": discoveries,
            })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    total_discoveries = sum(len(r["discovered_demographics"]) for r in records)
    print(f"  Inductive JSON: {output_path} ({len(records)} records, {total_discoveries} discoveries)")


def write_codebook_json(codebook: dict, output_path: Path) -> None:
    """Write aggregated codebook to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(codebook, f, indent=2, ensure_ascii=False)
    print(f"  Codebook JSON:  {output_path} ({len(codebook)} categories)")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Inductive + deductive demographic coder (LLM-only).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Coding modes:
  deductive   Extract predefined fields: age, sex_gender, location_country, location_state
  inductive   Discover new demographic categories from the data
  both        Do both in a single LLM pass (default)

Examples:
  python code_demographics_llm.py --input-dir ../../reddit_sample_data
  python code_demographics_llm.py --input-dir ../../reddit_sample_data --mode deductive
  python code_demographics_llm.py --input-dir ../../reddit_sample_data --mode inductive
  python code_demographics_llm.py --input-dir ../../reddit_sample_data --posts-only
        """,
    )
    parser.add_argument(
        "--input-dir", type=Path,
        default=Path(__file__).parent.parent.parent / "reddit_sample_data",
        help="Directory containing subreddit_posts.json and/or users/",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Output directory (default: {input-dir})",
    )
    parser.add_argument(
        "--mode", choices=["deductive", "inductive", "both"], default="both",
        help="Coding mode (default: both)",
    )
    parser.add_argument(
        "--workers", type=int, default=10,
        help="Concurrent API workers (default: 10)",
    )
    parser.add_argument(
        "--posts-only", action="store_true",
        help="Only process subreddit_posts.json",
    )
    parser.add_argument(
        "--users-only", action="store_true",
        help="Only process users/*.json histories",
    )
    parser.add_argument(
        "--max-chars", type=int, default=MAX_CHARS,
        help=f"Max characters per record (default: {MAX_CHARS})",
    )
    args = parser.parse_args()

    output_dir = args.output_dir or args.input_dir
    max_chars = args.max_chars

    from patientpunk._utils import get_llm_client
    client = get_llm_client()
    system_prompt = build_system_prompt(args.mode)
    work_items: list[tuple[dict, str]] = []

    # --- Load corpus ---
    if not args.users_only:
        posts_file = args.input_dir / "subreddit_posts.json"
        if posts_file.exists():
            posts = json.loads(posts_file.read_text(encoding="utf-8"))
            print(f"  Posts loaded        : {len(posts)} from {posts_file.name}")
            for post in posts:
                work_items.append((post, "subreddit_post"))

    if not args.posts_only:
        users_dir = args.input_dir / "users"
        if users_dir.is_dir():
            user_files = sorted(users_dir.glob("*.json"))
            print(f"  User files loaded   : {len(user_files)} from users/")
            for uf in user_files:
                user = json.loads(uf.read_text(encoding="utf-8"))
                work_items.append((user, "user_history"))

    if not work_items:
        sys.exit("No data found in --input-dir. Check the path.")

    print(f"\n  Mode                : {args.mode}")
    print(f"  Total records       : {len(work_items)}")
    print(f"  Workers             : {args.workers}")
    print(f"  Max chars/record    : {max_chars}")

    # --- Process concurrently ---
    results: list[dict] = []
    errors = 0

    def process_one(item: tuple[dict, str]) -> dict:
        record, source_type = item
        author_hash = record.get("author_hash") or "unknown"
        text = build_text(record, source_type, max_chars=max_chars)
        return call_haiku(client, system_prompt, text, author_hash, source_type, args.mode)

    print(f"\n  Processing {len(work_items)} records with {args.workers} workers...\n")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process_one, item): i for i, item in enumerate(work_items)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                results.append(result)
                if "error" in result:
                    errors += 1
                # Progress indicator
                done = len(results)
                if done % 20 == 0 or done == len(work_items):
                    print(f"    {done}/{len(work_items)} done", end="\r")
            except Exception as e:
                errors += 1
                print(f"  [{idx}] Error: {e}")

    print(f"\n\n  Completed: {len(results)} results, {errors} errors")

    # --- Write outputs ---
    if args.mode in ("deductive", "both"):
        write_deductive_csv(results, output_dir / "demographics_deductive.csv")

    if args.mode in ("inductive", "both"):
        write_inductive_json(results, output_dir / "demographics_inductive.json")
        codebook = build_codebook(results)
        write_codebook_json(codebook, output_dir / "demographics_codebook.json")

        # Print codebook summary
        if codebook:
            print(f"\n  Discovered demographic categories:")
            print(f"  {'Category':<35} {'Records':>8}  {'Values':>7}  Top value")
            print(f"  {'-'*35} {'-'*8}  {'-'*7}  {'-'*30}")
            for fname, entry in list(codebook.items())[:20]:
                top_val = next(iter(entry["values"]), "-")
                print(f"  {fname:<35} {entry['record_count']:>8}  "
                      f"{entry['unique_values']:>7}  {top_val}")

    # --- Coverage summary (deductive) ---
    if args.mode in ("deductive", "both"):
        for src in ("subreddit_post", "user_history"):
            subset = [r for r in results if r.get("source_type") == src]
            if not subset:
                continue
            n = len(subset)
            age_n = sum(1 for r in subset if r.get("age") is not None)
            sex_n = sum(1 for r in subset if r.get("sex_gender") is not None)
            loc_n = sum(1 for r in subset if r.get("location_country") is not None)
            print(f"\n  Coverage ({src}, n={n}):")
            print(f"    age:      {age_n}/{n} ({age_n/n*100:.0f}%)")
            print(f"    sex:      {sex_n}/{n} ({sex_n/n*100:.0f}%)")
            print(f"    location: {loc_n}/{n} ({loc_n/n*100:.0f}%)")

    print()


if __name__ == "__main__":
    main()
