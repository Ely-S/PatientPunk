#!/usr/bin/env python3
"""


Automatically discovers new biomedical fields from patient-authored text and
extracts them across the full corpus. Both stages run on Haiku:

  Stage 1 : Scan corpus → discover new field candidates with examples
  Stage 2 : Extract the discovered fields from every corpus record

Usage:
    # Full pipeline on default corpus
    python -m patientpunk.discover

    # Include existing schema as context (so it doesn't rediscover known fields)
    python -m patientpunk.discover --schema schemas/covidlonghaulers_schema.json

    # Limit corpus scan to N records (cost control for Stage 1)
    python -m patientpunk.discover --limit 20

    # Custom input path
    python -m patientpunk.discover --input-dir ../output/

Requires:
    pip install anthropic python-dotenv

Output:
    schemas/discovered_{timestamp}.json                  # Generated extension schema
    output/discovered_records_{schema_id}.json           # Full extraction results
    output/discovered_field_report_{schema_id}.json      # Discovery report + coverage stats
"""


import argparse
import builtins
import json
import os
import random
import sys
import threading
import time

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# Windows cp1252 terminal can't encode unicode arrows, emoji, etc. from LLM output.
# Override print globally in this module to replace non-ASCII chars.
_original_print = builtins.print

def print(*args, **kwargs):
    safe_args = [
        str(a).encode("ascii", "replace").decode("ascii") if isinstance(a, str) else a
        for a in args
    ]
    _original_print(*safe_args, **kwargs)
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

try:
    import anthropic
except ImportError:
    raise ImportError("anthropic is required: pip install anthropic") from None

from . import llm_extract
from .qualitative_standards import FIELD_DESIGN_STANDARDS
from .phase import PhaseResult


# =============================================================================
# CONSTANTS
# =============================================================================

# Model names resolved from _utils (OpenRouter or Anthropic direct)
from ._utils import (
    LLM_PROVIDER,
    check_response,
    LLM_TEMPERATURE,
    MODEL_FAST,
    collect_texts_from_post as _collect_texts_from_post,
    get_llm_client,
    parse_json_response,
    response_text,
)
from .llm_cache import cached_completion
HAIKU = MODEL_FAST
# Discovery responses are verbose JSON (examples, descriptions, vocabulary per field).
# 4096 was too low -- batches of 14+ posts regularly hit the ceiling and returned
# truncated JSON, causing PARSE FAILED on every batch. Haiku's hard max is 8192;
# Sonnet 3.5+ supports up to 8192 as well.
MAX_TOKENS_HAIKU = 8192
# Each discovered field requires ~600-800 chars of JSON (description, examples,
# vocabulary). 14 posts already generates ~16k chars of response which barely
# fits in 8192 tokens. Keeping batches to ~10 posts each stays comfortably under
# the output limit. 30k was too large.
MAX_TEXT_CHARS = 10_000
# Per-item text cap for stage 1 discovery. Discovery only needs to *spot* patterns,
# not read every word. Capping each item keeps batches dense (fewer API calls).
MAX_TEXT_CHARS_PER_ITEM_PHASE1 = 0
REQUEST_DELAY_S = 0.5
RETRY_DELAYS = [2, 5, 15, 30]

# How many example snippets Haiku should find per candidate field
EXAMPLES_PER_FIELD = 8
# Minimum examples a candidate field must have to qualify
MIN_EXAMPLES = 3



def call_model(
    client: anthropic.Anthropic,
    model: str,
    system_prompt: str,
    user_message: str,
    max_tokens: int = MAX_TOKENS_HAIKU,
) -> str:
    """Call a model with retry logic and prompt caching. Returns the text response."""

    def _call() -> str:
        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                print(f"    Retrying in {delay}s (attempt {attempt + 1})...")
                time.sleep(delay)
            try:
                response = client.messages.create(
                    model=model,
                    temperature=LLM_TEMPERATURE,
                    max_tokens=max_tokens,
                    system=[
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": "user", "content": user_message}],
                )
                return response_text(check_response(response, model))
            except (anthropic.RateLimitError, anthropic.InternalServerError):
                if attempt == len(RETRY_DELAYS):
                    raise
                print(f"    Rate limited / server error.")
            except anthropic.APIStatusError as e:
                if e.status_code in (429, 500, 502, 503, 529) and attempt < len(RETRY_DELAYS):
                    print(f"    API error {e.status_code}.")
                else:
                    raise
        return ""

    return cached_completion(
        provider=LLM_PROVIDER,
        model=model,
        system=system_prompt,
        prompt=user_message,
        temperature=LLM_TEMPERATURE,
        max_tokens=max_tokens,
        call_fn=_call,
    )


# parse_json_response lives in _utils (shared with llm_extract / demographics)


# =============================================================================
# CORPUS HELPERS
# =============================================================================

def collect_texts_from_user(user_data: dict) -> list[str]:
    texts = []
    for post in user_data.get("posts", []):
        if post.get("title"):
            texts.append(post["title"])
        if post.get("body"):
            texts.append(post["body"])
    for comment in user_data.get("comments", []):
        if comment.get("body"):
            texts.append(comment["body"])
    return texts


def collect_texts_from_post(post: dict) -> list[str]:
    """Title + body ONLY: comments are written by OTHER users, so including
    them attributes their content to the post author (same as biomedical.py /
    llm_extract.py; commenters are captured via the aggregate path)."""
    texts: list[str] = []
    for raw in _collect_texts_from_post(post, include_comments=False):
        kept = (raw or "").strip()
        if kept and kept not in ("[removed]", "[deleted]"):
            texts.append(kept)
    return texts


def load_corpus_texts(
    input_dir: Path,
    limit: int | None = None,
    posts_only: bool = False,
) -> list[dict]:
    """Load corpus into a list of {source, author_hash, post_id, texts} dicts.

    When posts_only=True, skip user histories. This is useful for field
    discovery where user histories introduce noise from
    unrelated subreddits -- we only want patterns from the target subreddit.
    """
    items = []
    users_dir = input_dir / "users"
    posts_file = input_dir / "subreddit_posts.json"

    if users_dir.exists() and not posts_only:
        for user_file in sorted(users_dir.glob("*.json")):
            with open(user_file, encoding="utf-8") as f:
                user_data = json.load(f)
            texts = collect_texts_from_user(user_data)
            if texts:
                items.append({
                    "source": "user_history",
                    "author_hash": user_data.get("author_hash", "unknown"),
                    "post_id": None,
                    "texts": texts,
                })

    if posts_file.exists():
        with open(posts_file, encoding="utf-8") as f:
            posts = json.load(f)
        for post in posts:
            texts = collect_texts_from_post(post)
            if texts:
                items.append({
                    "source": "subreddit_post",
                    "author_hash": post.get("author_hash", "unknown"),
                    "post_id": post.get("post_id"),
                    "texts": texts,
                })

    if limit:
        items = items[:limit]
    return items


# =============================================================================
# PHASE 1: DISCOVER (Haiku)
# =============================================================================

def build_discovery_prompt(known_fields: list, schema_data: dict | None = None) -> str:
    known_lines = []
    for f in known_fields:
        if isinstance(f, dict):
            desc = f.get("description", "")
            known_lines.append(f"  - {f['name']}: {desc}" if desc else f"  - {f['name']}")
        else:
            known_lines.append(f"  - {f}")
    known_block = "\n".join(known_lines)

    health_block = ""
    if schema_data:
        high_bleed = [
            (fname, fdata.get("_bleed_rate_last_run", 0))
            for fname, fdata in schema_data.get("extension_fields", {}).items()
            if fdata.get("_bleed_rate_last_run") is not None
            and fdata.get("_bleed_rate_last_run") >= 0.10
        ]
        if high_bleed:
            lines = "\n".join(
                f"  - {name} ({rate:.0%} bleed) - patterns are capturing too much context"
                for name, rate in sorted(high_bleed, key=lambda x: -x[1])
            )
            health_block = f"""
HIGH BLEED WARNING - these existing fields had excessive bleed in the last run.
Do NOT re-suggest these fields. If you see similar patterns, define them more narrowly:
{lines}
"""
    return f"""You are a biomedical research assistant for the PatientPunk project.
Your job is to read patient-authored text from Reddit chronic illness communities and
identify RECURRING biomedical patterns that are NOT already captured by the existing
extraction schema.

EXISTING FIELDS (do NOT suggest these or anything that overlaps with them):
{known_block}
{health_block}

WHAT TO LOOK FOR:
- Patterns that appear across MULTIPLE posts/users (not one-off mentions)
- Information a medical researcher would want to query or filter on
- Things that are specific enough to define clearly, not vague categories

IDEAL FIELD TYPES - in order of preference:
1. CATEGORICAL (best): a small fixed set of labels. e.g. "bedbound", "housebound", "mild", "moderate"
2. NAMED ENTITY (good): a specific thing - drug name, test name, specialist type, supplement name
3. SHORT MEASUREMENT (acceptable): a number + unit. e.g. "6 months", "100mg", "3 years"
4. Avoid: open-ended free text, narrative summaries, multi-clause values

MODEL CODEBOOK - emulate these field definitions exactly:

  vaccination_status:
    description: COVID vaccination status (categorical)
    examples:
      "I'm unvaccinated and got long covid"  →  extracted_value: "unvaccinated"
      "I had 3 Pfizer doses before I got sick"  →  extracted_value: "Pfizer"
      "boosted twice and still got long covid"  →  extracted_value: "boosted"
    negative_examples:
      "I read about the vaccine rollout" (discussing vaccines, not personal status)
      "my doctor mentioned the vaccine" (not the patient's own status)

  specialist_type_seen:
    description: Medical specialty the patient consulted (named entity, categorical)
    examples:
      "my rheumatologist ran every test"  →  extracted_value: "rheumatologist"
      "saw a cardiologist for the POTS"  →  extracted_value: "cardiologist"
      "referred to a neurologist finally"  →  extracted_value: "neurologist"
    negative_examples:
      "I wish I could see a specialist" (desire, not actual visit)
      "my doctor referred me somewhere" (no specific specialty named)

  functional_status_tier:
    description: Functional capacity level (categorical - one of: bedbound, housebound, severe, moderate, mild)
    examples:
      "I've been bedbound for 3 months"  →  extracted_value: "bedbound"
      "mostly housebound, can't leave without crashing"  →  extracted_value: "housebound"
      "I'm moderate - can do light tasks"  →  extracted_value: "moderate"
    negative_examples:
      "I went to bed early" (bedtime, not disability)
      "I stayed home today" (one-off, not chronic limitation)

{FIELD_DESIGN_STANDARDS}

BAD field suggestions (avoid these patterns):
- "general_health" (too vague - fails operationalization test)
- "patient_narrative" (not queryable - fails parsimony)
- "medication_details" (double-barreled - overlaps existing fields)
- ANY field whose extracted_value would be a full sentence or multi-clause summary
  (fails the "would two coders agree?" test - the answer is always no for free text)

CRITICAL RULES FOR extracted_value:
- 1-2 words is IDEAL. 3-4 words is acceptable. 5 words is the absolute maximum.
- It is the LITERAL VALUE the extractor will return - not a narrative, not a summary
- GOOD: "bedbound", "rheumatologist", "Pfizer", "no effect", "LDN", "6 months"
- BAD: "LDN started at 6-month mark, reported as helpful" (narrative - fails parsimony)
- BAD: "saw improvement after starting magnesium glycinate" (sentence - not a category)
- BAD: "LDN → partial; Zepbound → none; Luvox initiated" (double-barreled - split it)
- If the field captures entity names → extracted_value = just the entity name (1-2 words)
- If the field captures outcomes/labels → extracted_value = just the label word(s)

NEGATIVE EXAMPLES - for each field, also provide 2-3 sentences that look superficially
similar but should NOT be extracted. These help the extractor avoid false positives.
A negative example is a sentence from the same community that uses similar words but
does NOT actually contain the field value. Think about construct validity: what sentence
would FAIL the operationalization test even though it uses the right words?

RESPONSE FORMAT - return valid JSON:
{{
  "discovered_fields": [
    {{
      "field_name": "snake_case_name",
      "description": "What this field captures and why it matters for research",
      "examples": [
        {{
          "text": "exact quote from the source text that demonstrates this field",
          "extracted_value": "short entity or label only (1-5 words max)"
        }}
      ],
      "negative_examples": [
        {{
          "text": "sentence that looks similar but should NOT be extracted for this field"
        }}
      ],
      "frequency_hint": "common|occasional|rare",
      "research_value": "One sentence on why a researcher would want this field",
      "allowed_values": ["value1", "value2", "value3"],
      "trigger_vocabulary": ["diagnosed with", "started taking", "housebound"]
    }}
  ]
}}

For categorical or ordinal fields where the complete set of valid values is known, list
them all in `allowed_values`. Use null for open-ended named-entity fields (drug names,
supplement names, specialist names) where the full value space cannot be enumerated.
Good candidates for allowed_values: severity tiers, yes/no presence flags, status
categories, outcome labels.

For each field, include `trigger_vocabulary`: a list of 3-5 words or short phrases that
typically appear near a true positive in patient text. These are NOT the extracted values
- they are trigger words in context (e.g. 'diagnosed with', 'started taking',
'housebound').

Find {EXAMPLES_PER_FIELD} example snippets per field. Only suggest fields where you found
at least {MIN_EXAMPLES} distinct examples. Return 5-15 fields maximum.
If you find no new fields, return {{"discovered_fields": []}} - do NOT return plain text."""


def run_phase1_discovery(
    client: anthropic.Anthropic,
    corpus_items: list[dict],
    known_fields: list,
    workers: int = 10,
    per_item_chars: int = MAX_TEXT_CHARS_PER_ITEM_PHASE1,
    schema_data: dict | None = None,
) -> list[dict]:
    """Stage 1: Haiku scans corpus concurrently to discover new field candidates."""
    print("\n" + "=" * 60)
    print("  Stage 1: Candidate Scan (Haiku)")
    print("  Scanning corpus for new field candidates...")
    print("=" * 60 + "\n")

    system_prompt = build_discovery_prompt(known_fields, schema_data=schema_data)

    all_candidates: dict[str, dict] = {}
    merge_lock = threading.Lock()
    print_lock = threading.Lock()

    # Split corpus into batches. Each item is truncated to per_item_chars so more
    # items fit per batch - fewer API calls, lower cost.
    batch_texts = []
    current_batch = []
    current_len = 0

    for item in corpus_items:
        combined = "\n".join(item["texts"])
        if per_item_chars and len(combined) > per_item_chars:
            combined = combined[:per_item_chars] + "\n[TRUNCATED]"
        if current_len + len(combined) > MAX_TEXT_CHARS:
            if current_batch:
                batch_texts.append(current_batch)
            current_batch = [combined]
            current_len = len(combined)
        else:
            current_batch.append(combined)
            current_len += len(combined)
    if current_batch:
        batch_texts.append(current_batch)

    total_batches = len(batch_texts)
    print(f"  {len(corpus_items)} corpus items in {total_batches} batch(es)\n")

    def process_batch(args: tuple) -> tuple[int, list | None]:
        i, batch = args
        batch_text = "\n\n---NEW POST/USER---\n\n".join(batch)
        if len(batch_text) > MAX_TEXT_CHARS:
            batch_text = batch_text[:MAX_TEXT_CHARS] + "\n[TRUNCATED]"
        user_message = (
            "Analyze these patient-authored texts and identify recurring biomedical "
            "patterns not covered by the existing schema:\n\n" + batch_text
        )
        raw = call_model(client, HAIKU, system_prompt, user_message)
        parsed = parse_json_response(raw)
        if not parsed or "discovered_fields" not in parsed:
            return i, None
        return i, parsed["discovered_fields"]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(process_batch, (i, batch)): (i, len(batch))
            for i, batch in enumerate(batch_texts, 1)
        }
        for future in as_completed(futures):
            i, batch_len = futures[future]
            try:
                _, fields = future.result()
            except Exception as e:
                with print_lock:
                    print(f"  Batch {i}/{total_batches} ERROR: {e}")
                continue

            if fields is None:
                with print_lock:
                    print(f"  Batch {i}/{total_batches} ({batch_len} items) PARSE FAILED")
                continue

            with print_lock:
                print(f"  Batch {i}/{total_batches} ({batch_len} items) found {len(fields)} candidates")

            with merge_lock:
                for field in fields:
                    name = field.get("field_name", "").strip().lower().replace(" ", "_")
                    if not name:
                        continue
                    if name not in all_candidates:
                        all_candidates[name] = {
                            "description": "",
                            "examples": [],
                            "negative_examples": [],
                            "frequency_hints": [],
                            "research_value": "",
                            "trigger_vocabulary": [],
                            "allowed_values_sets": [],
                        }
                    entry = all_candidates[name]
                    if not entry["description"] and field.get("description"):
                        entry["description"] = field["description"]
                    if not entry["research_value"] and field.get("research_value"):
                        entry["research_value"] = field["research_value"]
                    if field.get("frequency_hint"):
                        entry["frequency_hints"].append(field["frequency_hint"])
                    for ex in field.get("examples", []):
                        if ex.get("text") and len(entry["examples"]) < EXAMPLES_PER_FIELD * 2:
                            existing_vals = {(e.get("extracted_value") or "").lower() for e in entry["examples"]}
                            if (ex.get("extracted_value") or "").lower() not in existing_vals:
                                entry["examples"].append(ex)
                    for neg in field.get("negative_examples", []):
                        if neg.get("text") and len(entry["negative_examples"]) < EXAMPLES_PER_FIELD:
                            existing_negs = {n["text"].lower() for n in entry["negative_examples"]}
                            if neg["text"].lower() not in existing_negs:
                                entry["negative_examples"].append(neg)
                    # Improvement 1: accumulate trigger_vocabulary
                    for word in field.get("trigger_vocabulary", []):
                        if word and word.lower() not in {w.lower() for w in entry["trigger_vocabulary"]}:
                            if len(entry["trigger_vocabulary"]) < 8:
                                entry["trigger_vocabulary"].append(word)
                    # Improvement 3: accumulate allowed_values sets
                    av = field.get("allowed_values")
                    if av and isinstance(av, list):
                        entry["allowed_values_sets"].append({v.lower() for v in av})

    # Filter to candidates with enough examples
    qualified = []
    for name, data in sorted(all_candidates.items(), key=lambda x: -len(x[1]["examples"])):
        if len(data["examples"]) >= MIN_EXAMPLES:
            # Improvement 3: resolve allowed_values union
            if data["allowed_values_sets"]:
                union = set().union(*data["allowed_values_sets"])
                allowed_values = sorted(union)
            else:
                allowed_values = None
            qualified.append({
                "field_name": name,
                "description": data["description"],
                "examples": data["examples"][:EXAMPLES_PER_FIELD],
                "negative_examples": data["negative_examples"][:EXAMPLES_PER_FIELD],
                "frequency_hint": max(set(data["frequency_hints"]), key=data["frequency_hints"].count)
                    if data["frequency_hints"] else "occasional",
                "research_value": data["research_value"],
                "trigger_vocabulary": data["trigger_vocabulary"],
                "allowed_values": allowed_values,
            })

    print(f"\n  Qualified candidates (>={MIN_EXAMPLES} examples): {len(qualified)}")
    for c in qualified:
        print(f"    {c['field_name']:<35} ({len(c['examples'])} examples, {c['frequency_hint']})")

    return qualified


# =============================================================================
# STAGE 2: EXTRACT DISCOVERED FIELDS (Haiku)
# =============================================================================

SAVE_EVERY_N = 20


def run_discovered_extract(
    client: anthropic.Anthropic,
    discovered_fields: list[dict],
    corpus_items: list[dict],
    workers: int = 10,
    resume: bool = False,
    records_file: Path | None = None,
) -> list[dict]:
    """Stage 2: Haiku extracts the discovered fields from every corpus record."""
    print("\n" + "=" * 60)
    print("  Stage 2: Extraction (Haiku)")
    print(f"  {len(discovered_fields)} discovered field(s) x {len(corpus_items)} records")
    print("=" * 60 + "\n")

    field_names = [f["field_name"] for f in discovered_fields]
    records: list[dict] = [
        {
            "_patientpunk_version": "2.0",
            "_extraction_method": "llm_discovered",
            "_extracted_at": datetime.now(timezone.utc).isoformat(),
            "record_meta": {
                "author_hash": item["author_hash"],
                "source": item["source"],
                "post_id": item.get("post_id"),
                "text_count": len(item["texts"]),
            },
            "discovered_fields": {
                name: {"values": None, "confidence": None, "source": "llm_discovered"}
                for name in field_names
            },
        }
        for item in corpus_items
    ]

    # Resume: records already extracted in a previous run keep their values and
    # are not re-sent to the model.
    todo = list(enumerate(zip(corpus_items, records)))
    if resume and records_file and records_file.exists():
        with open(records_file, encoding="utf-8") as f:
            existing = json.load(f)
        existing_index = {
            (rec.get("record_meta", {}).get("author_hash"),
             rec.get("record_meta", {}).get("post_id")): rec
            for rec in existing
        }
        done = set()
        for i, rec in enumerate(records):
            meta = rec["record_meta"]
            key = (meta["author_hash"], meta["post_id"])
            if key in existing_index:
                records[i] = existing_index[key]
                done.add(i)
        todo = [(i, pair) for i, pair in todo if i not in done]
        print(f"  Resumed: {len(done)} records loaded from existing file")

    # Controlled-vocabulary maps: values outside allowed_values are dropped.
    field_av_maps: dict[str, dict[str, str] | None] = {}
    for f in discovered_fields:
        av = f.get("allowed_values")
        field_av_maps[f["field_name"]] = {v.lower(): v for v in av} if av else None

    field_lines = []
    for f in discovered_fields:
        line = f"  - {f['field_name']}: {f['description']}"
        if f.get("allowed_values"):
            line += f" - ONLY return one of: {json.dumps(f['allowed_values'])}"
        field_lines.append(line)
    field_desc_block = "\n".join(field_lines)

    system_prompt = f"""You are a biomedical data extraction assistant for PatientPunk.
Extract ONLY the following discovered fields from patient-authored text.
Only extract explicitly stated information. Return null for fields with no evidence.
Any dose or quantity MUST keep its unit ("5 mg", "250 mcg"); a bare number is unusable.

FIELDS TO EXTRACT:
{field_desc_block}

RESPONSE FORMAT - valid JSON:
{{
  "fields": {{
    "field_name": ["value1", "value2"] or null
  }}
}}

Include ALL listed fields. Use null when no evidence exists."""

    save_lock = threading.Lock()
    print_lock = threading.Lock()
    stats = {"filled": 0, "completed": 0, "failed": 0}

    def process_item(args: tuple) -> None:
        record_i, (item, record) = args

        combined = "\n\n---NEW POST---\n\n".join(item["texts"])
        if len(combined) > MAX_TEXT_CHARS:
            combined = combined[:MAX_TEXT_CHARS] + "\n[TRUNCATED]"

        user_message = (
            f"Extract these specific fields: {', '.join(field_names)}\n\n"
            f"Each section separated by ---NEW POST--- is a separate Reddit post or comment. "
            f"Do not quote or combine text that spans across these boundaries.\n\n"
            f"Text:\n{combined}"
        )

        raw = call_model(client, HAIKU, system_prompt, user_message)
        parsed = parse_json_response(raw)

        local_fills = 0
        if parsed and "fields" in parsed:
            for field_name, values in parsed["fields"].items():
                if not values or field_name not in record["discovered_fields"]:
                    continue
                if isinstance(values, str):
                    values = [values]
                values = [v for v in values if v]
                av_map = field_av_maps.get(field_name)
                if av_map is not None:
                    values = [
                        av_map[v.lower()] for v in values
                        if isinstance(v, str) and v.lower() in av_map
                    ]
                if not values:
                    continue  # nothing survived the allowed_values filter
                record["discovered_fields"][field_name].update(
                    {"values": values, "confidence": "medium"}
                )
                local_fills += 1

        with save_lock:
            records[record_i] = record
            stats["filled"] += local_fills
            if not parsed or "fields" not in parsed:
                stats["failed"] += 1
            stats["completed"] += 1
            n = stats["completed"]
            if n % 10 == 0 or n == len(todo):
                with print_lock:
                    print(
                        f"  {n}/{len(todo)} "
                        f"({stats['filled']} fills, {stats['failed']} failed)",
                        flush=True,
                    )
            if records_file and n % SAVE_EVERY_N == 0:
                with open(records_file, "w", encoding="utf-8") as f:
                    json.dump(records, f, ensure_ascii=False, indent=2)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(process_item, t) for t in todo]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                with print_lock:
                    print(f"  Worker error: {e}")

    print(f"\n  Extracted {stats['filled']} field values across {len(todo)} records")
    return records


# =============================================================================
# SCHEMA GENERATION
# =============================================================================

def generate_schema(
    validated_fields: list[dict],
    base_schema_id: str | None,
) -> dict:
    """Create a brand-new extension schema JSON from validated fields."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    discovered_at = datetime.now(timezone.utc).isoformat()
    schema_id = f"discovered_{timestamp}"

    schema = {
        "schema_id": schema_id,
        "_description": (
            f"Auto-discovered extension schema generated by patientpunk.discover. "
            f"All fields are tagged source: llm_discovered."
        ),
        "_generated_at": discovered_at,
        "_base_schema": base_schema_id,
        "_version": "1.0",
        "include_base_fields": [],
        "extension_fields": {},
    }

    for field in validated_fields:
        schema["extension_fields"][field["field_name"]] = {
            "description": field["description"],
            "confidence": field.get("confidence", "medium"),
            "source": "llm_discovered",
            "_discovered_at": discovered_at,
            "frequency_hint": field.get("frequency_hint", "occasional"),
            "research_value": field.get("research_value", ""),
            "allowed_values": field.get("allowed_values"),
        }

    return schema


def merge_into_schema(
    validated_fields: list[dict],
    existing_schema: dict,
) -> tuple[dict, int, int]:
    """Merge newly discovered fields into an existing schema in-place.

    New fields are tagged with _discovered_at. Existing fields are never
    overwritten - run again with an updated schema to skip them next time.

    Returns (updated_schema, added_count, skipped_count).
    """
    discovered_at = datetime.now(timezone.utc).isoformat()
    existing_fields = existing_schema.setdefault("extension_fields", {})
    added = 0
    skipped = 0

    for field in validated_fields:
        name = field["field_name"]
        if name in existing_fields:
            skipped += 1
            continue
        existing_fields[name] = {
            "description": field["description"],
            "confidence": field.get("confidence", "medium"),
            "source": "llm_discovered",
            "_discovered_at": discovered_at,
            "frequency_hint": field.get("frequency_hint", "occasional"),
            "research_value": field.get("research_value", ""),
            "allowed_values": field.get("allowed_values"),
        }
        added += 1

    return existing_schema, added, skipped


# =============================================================================
# SCHEMA HEALTH UPDATE (Improvement 6)
# =============================================================================

def run_schema_health_update(schema_path: Path, records_file: Path) -> None:
    """Compute per-field bleed rates from extracted records and write back to schema."""
    print("\n" + "=" * 60)
    print("  Schema Health Update")
    print("=" * 60 + "\n")

    with open(records_file, encoding="utf-8") as f:
        records = json.load(f)

    # Count extractions and bleed instances per field
    field_total: dict[str, int] = defaultdict(int)
    field_bleed: dict[str, int] = defaultdict(int)

    for record in records:
        for fname, fdata in record.get("discovered_fields", {}).items():
            values = fdata.get("values") or []
            for val in values:
                if not isinstance(val, str):
                    continue
                field_total[fname] += 1
                if len(val.split()) >= 10:
                    field_bleed[fname] += 1

    # Load and update schema
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)

    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    print(f"  {'Field':<40} {'Extractions':>12} {'Bleed':>8} {'Rate':>8}")
    print(f"  {'-'*40} {'-'*12} {'-'*8} {'-'*8}")

    for fname, fdata in schema.get("extension_fields", {}).items():
        total = field_total.get(fname, 0)
        bleed = field_bleed.get(fname, 0)
        rate = bleed / total if total > 0 else None
        fdata["_bleed_rate_last_run"] = rate
        fdata["_last_health_check"] = now
        updated += 1
        flag = " *** HIGH BLEED" if rate is not None and rate >= 0.10 else ""
        rate_str = f"{rate:.0%}" if rate is not None else "no data"
        print(f"  {fname:<40} {total:>12} {bleed:>8} {rate_str:>8}{flag}")

    with open(schema_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)

    print(f"\n  Updated {updated} fields in {schema_path.name}")


# =============================================================================
# LIBRARY ENTRYPOINT
# =============================================================================

def run_discovery(
    *,
    input_dir: Path,
    schema_path: Path | None = None,
    temp_dir: Path | None = None,
    workers: int = 10,
    limit: int | None = None,
    resume: bool = False,
    candidates_file: Path | None = None,
    sample: int | None = None,
    per_item_chars: int = 0,
    stop_after: Literal["candidates"] | None = None,
) -> PhaseResult:
    """Run two-stage LLM field discovery.

    Parameters
    ----------
    stop_after:
        If ``"candidates"``, run only candidate generation (or load
        ``candidates_file``), write ``phase1_candidates.json``, and return.
        Used by ``PipelineConfig.discovery_mode="review"`` for Marimo review.
    """
    from typing import Any

    input_dir = Path(input_dir)
    if not input_dir.exists():
        raise FileNotFoundError(
            f"{input_dir} does not exist. Run scrape_corpus.py first."
        )

    out_temp = Path(temp_dir) if temp_dir else input_dir / "temp"
    out_temp.mkdir(parents=True, exist_ok=True)

    existing_schema = None
    # Known-to-discovery fields = every field the base LLM extraction already
    # covers, so discovery doesn't re-suggest them.
    _base_field_names = sorted(
        set(llm_extract.BASE_FIELD_DESCRIPTIONS) | set(llm_extract.BASE_OPTIONAL_DESCRIPTIONS)
    )
    known_fields_seen: set[str] = set()
    known_fields: list = []
    for name in _base_field_names:
        if name not in known_fields_seen:
            known_fields_seen.add(name)
            known_fields.append(name)

    if schema_path:
        schema_path = Path(schema_path)
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")
        with open(schema_path, encoding="utf-8") as f:
            existing_schema = json.load(f)
        for fname, fdata in existing_schema.get("extension_fields", {}).items():
            if fname not in known_fields_seen:
                known_fields_seen.add(fname)
                known_fields.append({"name": fname, "description": fdata.get("description", "")})

    base_schema_id = existing_schema["schema_id"] if existing_schema else None
    client = get_llm_client()

    print("=" * 60)
    print("  PatientPunk Field Discovery Pipeline")
    print(f"  Models        : Haiku (scan + extract)")
    print(f"  Target schema : {schema_path or 'new file (no --schema)'}")
    print(f"  Known fields  : {len(known_fields)}")
    print(f"  Corpus limit  : {sample and f'sample {sample}' or limit or 'all'}")
    print(f"  Per-item chars: {per_item_chars or 'unlimited'}")
    print(f"  Workers       : {workers}")
    print(f"  Resume        : {'yes' if resume else 'no'}")
    print("=" * 60)

    start_time = datetime.now(timezone.utc)
    phase1_candidates_path = out_temp / "phase1_candidates.json"

    print("\nLoading corpus...")
    corpus_items = load_corpus_texts(input_dir, limit=None, posts_only=True)
    print(f"  {len(corpus_items)} items loaded")

    if candidates_file:
        candidates_file = Path(candidates_file)
        if not candidates_file.exists():
            raise FileNotFoundError(f"Candidates file not found: {candidates_file}")
        with open(candidates_file, encoding="utf-8") as f:
            candidates = json.load(f)
        print(f"\nLoaded {len(candidates)} stage 1 candidates from {candidates_file} (skipping stage 1)")
    else:
        phase1_items = corpus_items
        if sample and sample < len(phase1_items):
            phase1_items = random.sample(phase1_items, sample)
            print(f"  Using random sample of {sample} items for stage 1")
        elif limit and limit < len(phase1_items):
            phase1_items = phase1_items[:limit]
            print(f"  Using first {limit} items for stage 1")

        candidates = run_phase1_discovery(
            client, phase1_items, known_fields,
            workers=workers,
            per_item_chars=per_item_chars,
            schema_data=existing_schema,
        )

        if candidates:
            with open(phase1_candidates_path, "w", encoding="utf-8") as f:
                json.dump(candidates, f, ensure_ascii=False, indent=2)
            print(f"\n  Stage 1 saved: {phase1_candidates_path}")

    if stop_after == "candidates":
        with open(phase1_candidates_path, "w", encoding="utf-8") as f:
            json.dump(candidates, f, ensure_ascii=False, indent=2)
        print(f"\n  Stage 1 saved: {phase1_candidates_path}")
        print(f"\n  Stopped after candidates ({len(candidates)}) for review.")
        return PhaseResult(
            artifacts={"candidates": phase1_candidates_path},
            stats={"candidates": len(candidates)},
        )

    def _write_empty_report(candidates_found: int, candidates_validated: int) -> Path:
        # Written even when nothing was discovered so `promote` (which locates
        # reports via find_latest_discovery/find_discovery_reports, matched on
        # pipeline_run.base_schema) can tell "discovery ran and found nothing"
        # apart from "discovery was never run" -- the two look identical to a
        # caller if only a nonzero-candidate run leaves a report behind.
        end_time = datetime.now(timezone.utc)
        report = {
            "pipeline_run": {
                "started_at": start_time.isoformat(),
                "finished_at": end_time.isoformat(),
                "duration_seconds": (end_time - start_time).total_seconds(),
                "corpus_items": len(corpus_items),
                "discovery_limit": limit,
                "base_schema": base_schema_id,
            },
            "discovery_results": {
                "candidates_found": candidates_found,
                "candidates_validated": candidates_validated,
                "candidates_rejected": candidates_found - candidates_validated,
            },
            "field_stats": {},
            "schema_file": None,
            "records_file": None,
        }
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = out_temp / f"discovered_field_report_empty_{timestamp}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return report_file

    artifacts: dict[str, Path] = {}
    if not candidates:
        print("\nNo new fields discovered. The existing schema may already cover this corpus well.")
        artifacts["report"] = _write_empty_report(0, 0)
        return PhaseResult(artifacts=artifacts, stats={"fields discovered": 0})

    validated_fields = candidates

    schema = generate_schema(validated_fields, base_schema_id)
    schema_file = out_temp / f"{schema['schema_id']}.json"
    with open(schema_file, "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)
    print(f"\n  Discovery schema saved: {schema_file}")
    artifacts["schema"] = schema_file

    schema_id = schema["schema_id"]
    records_file = out_temp / f"discovered_records_{schema_id}.json"
    records = run_discovered_extract(
        client, validated_fields, corpus_items,
        workers=workers,
        resume=resume,
        records_file=records_file,
    )

    with open(records_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    artifacts["records"] = records_file

    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    field_stats = {}
    for field in validated_fields:
        fname = field["field_name"]
        hits = sum(
            1 for r in records
            if r.get("discovered_fields", {}).get(fname, {}).get("values")
        )
        field_stats[fname] = {
            "hits": hits,
            "coverage": hits / len(records) if records else 0,
            "frequency_hint": field.get("frequency_hint", "occasional"),
            "source": "llm_discovered",
        }

    report = {
        "pipeline_run": {
            "started_at": start_time.isoformat(),
            "finished_at": end_time.isoformat(),
            "duration_seconds": duration,
            "corpus_items": len(corpus_items),
            "discovery_limit": limit,
            "base_schema": base_schema_id,
        },
        "discovery_results": {
            "candidates_found": len(candidates),
            "candidates_validated": len(validated_fields),
            "candidates_rejected": len(candidates) - len(validated_fields),
        },
        "field_stats": field_stats,
        "schema_file": str(schema_file),
        "records_file": str(records_file),
    }

    report_file = out_temp / f"discovered_field_report_{schema_id}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    artifacts["report"] = report_file

    print(f"\n{'=' * 60}")
    print(f"  Pipeline Complete ({duration:.0f}s)")
    print(f"  Candidates discovered : {len(candidates)}")
    print(f"  Fields validated      : {len(validated_fields)}")
    print(f"  Records extracted     : {len(records)}")
    print(f"  Schema                : {schema_file}")
    print(f"  Records               : {records_file}")
    print(f"  Report                : {report_file}")
    print(f"\n  Discovered fields:")
    for fname, stats in sorted(field_stats.items(), key=lambda x: -x[1]["hits"]):
        print(f"    {fname:<35} hits: {stats['hits']:>3} ({stats['coverage']:.0%})")
    print(f"{'=' * 60}")

    record_count = len(records)
    covered = sum(
        1 for rec in records
        if any(fd.get("values") for fd in rec.get("discovered_fields", {}).values())
    )
    out_stats: dict[str, Any] = {
        "fields discovered": len(field_stats),
        "records with any hit": f"{covered}/{record_count}",
        "coverage %": f"{round(covered / record_count * 100, 1) if record_count else 0}%",
    }
    return PhaseResult(artifacts=artifacts, stats=out_stats)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Multi-model field discovery pipeline for PatientPunk.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input-dir", type=Path,
        default=Path(__file__).resolve().parent.parent / "output",
    )
    parser.add_argument("--schema", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--candidates", type=Path, default=None)
    parser.add_argument("--sample", type=int, default=None)
    parser.add_argument("--per-item-chars", type=int, default=MAX_TEXT_CHARS_PER_ITEM_PHASE1)
    parser.add_argument("--temp-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        run_discovery(
            input_dir=args.input_dir,
            schema_path=args.schema,
            temp_dir=args.temp_dir,
            workers=args.workers,
            limit=args.limit,
            resume=args.resume,
            candidates_file=args.candidates,
            sample=args.sample,
            per_item_chars=args.per_item_chars,
        )
    except (FileNotFoundError, ValueError, OSError, ImportError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
