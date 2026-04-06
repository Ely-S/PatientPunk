#!/usr/bin/env python3
"""Multi-model field discovery pipeline for PatientPunk.

Automatically discovers new biomedical fields from patient-authored text,
generates regex patterns for them, validates the patterns, and extracts
across the full corpus. Uses a two-model architecture:

  - Haiku: cheap, fast — scans corpus for field candidates, extracts bulk data
  - Sonnet: precise — writes and validates regex patterns

Pipeline phases:
  Phase 1 (Haiku)  : Scan corpus → discover new field candidates with examples
  Phase 2 (Sonnet) : For each candidate → write regex → test against examples → iterate
  Phase 3 (regex)  : Run validated patterns across full corpus (no LLM, free)
  Phase 4 (Haiku)  : Fill gaps — for records where regex missed, Haiku extracts directly

Usage:
    # Full pipeline on default corpus
    python discover_fields.py

    # Include existing schema as context (so it doesn't rediscover known fields)
    python discover_fields.py --schema schemas/covidlonghaulers_schema.json

    # Limit corpus scan to N records (cost control for Phase 1)
    python discover_fields.py --limit 20

    # Skip Phase 4 (no gap-filling, just discovery + regex)
    python discover_fields.py --no-fill

    # Custom input path
    python discover_fields.py --input-dir ../output/

Requires:
    pip install anthropic python-dotenv

Output:
    schemas/discovered_{timestamp}.json                  # Generated extension schema
    output/discovered_records_{schema_id}.json           # Full extraction results
    output/discovered_field_report_{schema_id}.json      # Discovery report + coverage stats
"""

import argparse
import json
import os
import random
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    sys.exit("python-dotenv is required: pip install python-dotenv")

try:
    import anthropic
except ImportError:
    sys.exit("anthropic is required: pip install anthropic")

load_dotenv(Path(__file__).parent / ".env")        # demographic_extraction/.env
load_dotenv(Path(__file__).parent.parent / ".env")  # Scrapers/.env (fallback)


def _finditer_with_timeout(pattern, text: str, timeout: float = 2.0) -> list:
    """Run pattern.finditer(text) in a thread; raise TimeoutError if it takes too long.

    Catastrophic backtracking in LLM-generated patterns can hang indefinitely.
    This caps each pattern at `timeout` seconds and returns whatever matched so far,
    raising TimeoutError so the caller can log and skip the offending pattern.
    """
    results: list = []
    exc: list = []

    def _run():
        try:
            results.extend(pattern.finditer(text))
        except Exception as e:
            exc.append(e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"Pattern timed out after {timeout}s")
    if exc:
        raise exc[0]
    return results


# =============================================================================
# CONSTANTS
# =============================================================================

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
MAX_TOKENS_HAIKU = 4096
MAX_TOKENS_SONNET = 4096
MAX_TEXT_CHARS = 30_000
# Text cap for Phase 3 regex matching. Keeps each operation bounded even for
# users with thousands of posts. Patterns generally match early in text.
MAX_TEXT_CHARS_PHASE3 = 30_000
# Per-item text cap for Phase 1 discovery. Discovery only needs to *spot* patterns,
# not read every word. Capping each item keeps batches dense (fewer API calls).
MAX_TEXT_CHARS_PER_ITEM_PHASE1 = 0
REQUEST_DELAY_S = 0.5
RETRY_DELAYS = [2, 5, 15, 30]

# How many example snippets Haiku should find per candidate field
EXAMPLES_PER_FIELD = 8
# Max iterations for Sonnet to refine a regex
MAX_REGEX_ITERATIONS = 3
# Minimum examples a field must have to proceed to regex generation
MIN_EXAMPLES = 3


# =============================================================================
# API HELPERS
# =============================================================================

def get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or api_key.startswith("sk-ant-your-"):
        sys.exit(
            "ANTHROPIC_API_KEY not set or still placeholder.\n"
            "  1. Copy .env.example to .env\n"
            "  2. Add your key from https://console.anthropic.com/settings/keys"
        )
    return anthropic.Anthropic(api_key=api_key)


def call_model(
    client: anthropic.Anthropic,
    model: str,
    system_prompt: str,
    user_message: str,
    max_tokens: int = MAX_TOKENS_HAIKU,
) -> str:
    """Call a model with retry logic and prompt caching. Returns the text response."""
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            print(f"    Retrying in {delay}s (attempt {attempt + 1})...")
            time.sleep(delay)
        try:
            response = client.messages.create(
                model=model,
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
            return response.content[0].text
        except anthropic.RateLimitError:
            if attempt == len(RETRY_DELAYS):
                raise
            print(f"    Rate limited.")
        except anthropic.APIStatusError as e:
            if e.status_code >= 500 and attempt < len(RETRY_DELAYS):
                print(f"    API error {e.status_code}.")
            else:
                raise
    return ""


def parse_json_response(text: str) -> dict | list | None:
    """Extract JSON from an LLM response, handling markdown code fences."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Find the outermost JSON structure
        for opener, closer in [("{", "}"), ("[", "]")]:
            start = text.find(opener)
            end = text.rfind(closer) + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    continue
    return None


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
    texts = []
    if post.get("title"):
        texts.append(post["title"])
    if post.get("body"):
        texts.append(post["body"])
    for comment in post.get("comments", []):
        if comment.get("body"):
            texts.append(comment["body"])
    return texts


def load_corpus_texts(input_dir: Path, limit: int | None = None) -> list[dict]:
    """Load corpus into a list of {source, author_hash, post_id, texts} dicts."""
    items = []
    users_dir = input_dir / "users"
    posts_file = input_dir / "subreddit_posts.json"

    if users_dir.exists():
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
                f"  - {name} ({rate:.0%} bleed) — patterns are capturing too much context"
                for name, rate in sorted(high_bleed, key=lambda x: -x[1])
            )
            health_block = f"""
HIGH BLEED WARNING — these existing fields had excessive bleed in the last run.
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

IDEAL FIELD TYPES — in order of preference:
1. CATEGORICAL (best): a small fixed set of labels. e.g. "bedbound", "housebound", "mild", "moderate"
2. NAMED ENTITY (good): a specific thing — drug name, test name, specialist type, supplement name
3. SHORT MEASUREMENT (acceptable): a number + unit. e.g. "6 months", "100mg", "3 years"
4. Avoid: open-ended free text, narrative summaries, multi-clause values

MODEL CODEBOOK — emulate these field definitions exactly:

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
    description: Functional capacity level (categorical — one of: bedbound, housebound, severe, moderate, mild)
    examples:
      "I've been bedbound for 3 months"  →  extracted_value: "bedbound"
      "mostly housebound, can't leave without crashing"  →  extracted_value: "housebound"
      "I'm moderate — can do light tasks"  →  extracted_value: "moderate"
    negative_examples:
      "I went to bed early" (bedtime, not disability)
      "I stayed home today" (one-off, not chronic limitation)

CODEBOOK BEST PRACTICES (graduate research methods level):

1. LEVELS OF MEASUREMENT — choose the right one:
   - Nominal: unordered categories. e.g. vaccine brand (Pfizer, Moderna, AstraZeneca).
     Use when categories have no natural order. Each value is just a label.
   - Ordinal: ordered categories. e.g. severity (mild < moderate < severe < bedbound).
     Use when rank matters but intervals between ranks are not equal.
   - Avoid interval/ratio for text extraction — you can't reliably extract "pain = 7.3".
   Rule of thumb: if you can't sort the values meaningfully, it's nominal.
   If you can sort them but can't do math on them, it's ordinal.

2. MUTUALLY EXCLUSIVE AND EXHAUSTIVE (MEE):
   Every observation should fit into exactly ONE category, and every possible
   observation should fit into SOME category.
   - Bad: categories "mild" and "moderate" overlap if "mildly moderate" is possible
   - Bad: categories that don't cover "unknown" or "not mentioned" leave gaps
   - Fix: design categories so no value could reasonably belong to two of them,
     and add catch-all options for edge cases if needed.

3. OPERATIONALIZATION — the bridge between concept and measurement:
   A field is only useful if you can define exactly what text evidence counts as
   an instance of it. Ask: "Would two independent coders agree on whether this
   sentence belongs in this field?" If not, the definition is too loose.
   - Bad operationalization: "supplement_efficacy" — too vague, coders will disagree
   - Good operationalization: "supplement_reported_helpful" with categorical values
     (helped / no effect / worsened / mixed) — coders will agree

4. PARSIMONY — fewer, cleaner categories beat many overlapping ones:
   3-7 categories per field is a good target. More than 10 usually means the field
   is actually two fields, or the categories aren't truly distinct.
   - Bad: 15 different specialist types with overlapping scope
   - Good: 6-8 core specialist types (rheumatologist, cardiologist, neurologist,
     immunologist, gastroenterologist, psychiatrist, endocrinologist, "other")

5. AVOID DOUBLE-BARRELED FIELDS — one field, one concept:
   If a field tries to capture two things at once, split it.
   - Bad: "medication_and_outcome" (two concepts)
   - Good: separate "medication_tried" and "treatment_outcome" fields
   A signal that a field is double-barreled: the extracted_value needs punctuation
   (→, ;, :) to hold it together.

6. CONSTRUCT VALIDITY — does the extracted value actually measure the concept?
   The text evidence must be a reliable indicator of the underlying concept,
   not just a surface-level linguistic match.
   - Bad construct validity: capturing "worked" as treatment_outcome — "it worked out
     that I couldn't go" is not a treatment outcome
   - Good construct validity: require "worked" adjacent to a medication name

7. UNIT OF OBSERVATION — what does one extracted value represent?
   Be explicit: is one value per sentence? Per post? Per medication? Per patient?
   Most fields here are per-patient. If a field is per-medication, the value should
   be just the medication name (not a sentence about it).

BAD field suggestions (avoid these patterns):
- "general_health" (too vague — fails operationalization test)
- "patient_narrative" (not queryable — fails parsimony)
- "medication_details" (double-barreled — overlaps existing fields)
- ANY field whose extracted_value would be a full sentence or multi-clause summary
  (fails the "would two coders agree?" test — the answer is always no for free text)

CRITICAL RULES FOR extracted_value:
- 1-2 words is IDEAL. 3-4 words is acceptable. 5 words is the absolute maximum.
- It is the LITERAL VALUE the regex capture group will return — not a narrative, not a summary
- GOOD: "bedbound", "rheumatologist", "Pfizer", "no effect", "LDN", "6 months"
- BAD: "LDN started at 6-month mark, reported as helpful" (narrative — fails parsimony)
- BAD: "saw improvement after starting magnesium glycinate" (sentence — not a category)
- BAD: "LDN → partial; Zepbound → none; Luvox initiated" (double-barreled — split it)
- If the field captures entity names → extracted_value = just the entity name (1-2 words)
- If the field captures outcomes/labels → extracted_value = just the label word(s)

NEGATIVE EXAMPLES — for each field, also provide 2-3 sentences that look superficially
similar but should NOT be extracted. These help the regex engine avoid false positives.
A negative example is a sentence from the same community that uses similar words but
does NOT actually contain the field value. Think about construct validity: what sentence
would FAIL the operationalization test even though it uses the right words?

Set `regex_extractable: false` for fields where the value requires semantic understanding,
is too variable in phrasing, or is inherently relational/sequential (e.g.
'medication_trial_sequence' — the value depends on understanding a multi-step narrative
that no pattern can reliably capture). Set true for entity names, categorical labels,
and measurements.

RESPONSE FORMAT — return valid JSON:
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
      "regex_extractable": true,
      "extractability_note": "brief reason if false — what makes this hard to regex",
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
— they are trigger words in context (e.g. 'diagnosed with', 'started taking',
'housebound').

Find {EXAMPLES_PER_FIELD} example snippets per field. Only suggest fields where you found
at least {MIN_EXAMPLES} distinct examples. Return 5-15 fields maximum.
If you find no new fields, return {{"discovered_fields": []}} — do NOT return plain text."""


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
    # items fit per batch — fewer API calls, lower cost.
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
                            "regex_extractable_votes": [],
                            "extractability_note": "",
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
                            existing_vals = {e.get("extracted_value", "").lower() for e in entry["examples"]}
                            if ex.get("extracted_value", "").lower() not in existing_vals:
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
                    # Improvement 2: accumulate regex_extractable votes and note
                    entry["regex_extractable_votes"].append(field.get("regex_extractable", True))
                    if not entry["extractability_note"] and field.get("extractability_note"):
                        entry["extractability_note"] = field["extractability_note"]
                    # Improvement 3: accumulate allowed_values sets
                    av = field.get("allowed_values")
                    if av and isinstance(av, list):
                        entry["allowed_values_sets"].append({v.lower() for v in av})

    # Filter to candidates with enough examples
    qualified = []
    for name, data in sorted(all_candidates.items(), key=lambda x: -len(x[1]["examples"])):
        if len(data["examples"]) >= MIN_EXAMPLES:
            # Improvement 2: resolve regex_extractable votes
            votes = data["regex_extractable_votes"]
            regex_extractable = (sum(votes) / max(len(votes), 1)) >= 0.5 if votes else True
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
                "regex_extractable": regex_extractable,
                "extractability_note": data["extractability_note"],
                "allowed_values": allowed_values,
            })

    print(f"\n  Qualified candidates (>={MIN_EXAMPLES} examples): {len(qualified)}")
    for c in qualified:
        print(f"    {c['field_name']:<35} ({len(c['examples'])} examples, {c['frequency_hint']})")

    return qualified


# =============================================================================
# PHASE 2: BUILD REGEX (Sonnet)
# =============================================================================

SONNET_SYSTEM_PROMPT = """You are an expert regex engineer for the PatientPunk biomedical research project.
Your job is to write Python regex patterns that extract specific biomedical information from
informal patient-authored Reddit text.

RULES FOR WRITING PATTERNS:
1. Use Python re module syntax (not PCRE or other flavors)
2. All patterns will be compiled with re.IGNORECASE flag — do NOT include (?i) in patterns
3. Patterns should capture the VALUE in a group when possible (use parentheses)
4. Be generous with word boundaries (\\b) to avoid false matches inside other words
5. Account for informal spelling, abbreviations, and Reddit conventions
6. Prefer multiple simple patterns over one complex monster pattern
7. Use non-capturing groups (?:...) for alternation structure, capturing groups for values
8. Avoid patterns that are so broad they'll match unrelated content
9. CAPTURE GROUP LENGTH: 1-2 words is ideal, 3-4 acceptable, 5 the hard maximum.
   NEVER write (.+), (.{{0,50}}), or any open-ended quantifier in a capture group.
   Use specific word lists, \\b boundaries, or fixed short quantifiers instead.
10. FALSE POSITIVES MATTER: you will be shown negative examples that must NOT match.
    A pattern scoring 100% hit rate but firing on negatives is a failing pattern.

NEGATION HANDLING — a critical source of false positives:
Patient text frequently negates the exact terms you want to capture:
"not bedbound", "never tried LDN", "I don't have POTS", "no longer housebound".
A naive pattern fires on all of these incorrectly.

CORRECT APPROACH — use positive context anchors instead of the bare term:
Rather than matching the term alone, require a positive context verb before it
that would not appear in a negated sentence.

  BAD:  \\b(bedbound)\\b  — fires on "not bedbound"
  GOOD: \\b(?:I(?:'m| am)|currently|have been|been|become)\\s+(?:\\w+\\s+)?(bedbound)\\b

  BAD:  \\b(LDN)\\b  — fires on "never tried LDN"
  GOOD: \\b(?:taking|started|on|tried|using|began)\\s+(?:low.dose\\s+)?(LDN)\\b

  BAD:  \\b(POTS)\\b  — fires on "don't have POTS"
  GOOD: \\b(?:diagnosed with|have|my|confirmed)\\s+(POTS)\\b

Python's `re` module requires fixed-width lookbehinds, so you CANNOT write
`(?<!not\\s+value)` with variable spacing. Use positive context anchors instead.

Common positive anchors by field type:
  Status/severity:  "I'm", "I am", "currently", "been", "become", "remain"
  Medication use:   "taking", "on", "started", "tried", "prescribed", "began"
  Diagnosis:        "diagnosed with", "have", "confirmed", "positive for"
  Specialist visit: "saw", "seeing", "referred to", "appointment with", "consulted"

MODEL PATTERNS — write patterns like these:

  GOOD — categorical field with enumerated values (best):
    Field: vaccination_status
    \\b(unvaccinated|not vaccinated|no vaccine)\\b
    \\b(pfizer|moderna|astrazeneca|johnson|novavax|mrna)\\b(?:\\s+vaccine)?
    \\b(boosted|double vaxxed|triple vaxxed|fully vaccinated)\\b
    → capture group returns one word from a known list. Cannot bleed.

  GOOD — named entity anchored by context verb (good):
    Field: specialist_type_seen
    \\b(?:saw|seeing|referred to|consulted?|appointment with)\\s+(?:a|my|an)?\\s*(rheumatologist|cardiologist|neurologist|immunologist|endocrinologist|gastroenterologist|psychiatrist|pulmonologist)\\b
    → captures exactly one known word, context verb prevents false positives.

  GOOD — short measurement (acceptable):
    Field: long_covid_duration_months
    \\b([1-9][0-9]?)\\s*months?\\s+(?:of\\s+)?(?:long.?covid|pasc|symptoms|this)\\b
    → captures a number, \\b stops it at the word boundary.

  BAD — open capture group (never do this):
    \\b(?:tried|started|took)\\s+([A-Za-z][A-Za-z0-9\\-]+(?:\\s+[A-Za-z][A-Za-z0-9\\-]+){{0,3}})
    → ({0,3}) still matches 1-4 arbitrary words. Use a named word list instead.

  BAD — no anchor, grabs context:
    ([A-Za-z]+(?:[- ][A-Za-z]+){{0,3}})\\s+(?:helps?|works?)
    → matches "pages and security guards are really good" — anything before "helps".

RESPONSE FORMAT — return valid JSON:
{{
  "patterns": [
    "regex_pattern_1",
    "regex_pattern_2"
  ],
  "reasoning": "Brief explanation of what each pattern targets"
}}

MEASUREMENT PRINCIPLES FOR PATTERN DESIGN:

- Sensitivity vs specificity tradeoff: a broad pattern catches more true positives
  but also more false positives. A narrow pattern misses edge cases but is reliable.
  For research data, SPECIFICITY is usually more valuable than sensitivity — a smaller
  clean dataset beats a large noisy one. Err on the side of precision.

- Operationalization in regex: your pattern is your operationalization. It defines
  exactly what text evidence counts as an instance of the field. If the pattern fires
  on a sentence that a human coder would say "that's not really about X", your
  operationalization is wrong — tighten the pattern.

- Inter-rater reliability proxy: ask yourself "would two researchers looking at a
  match agree it belongs in this field?" If a match is ambiguous, the pattern is
  too broad. Disambiguate with more context in the trigger (words before/after the
  capture group), not by widening the capture group.

Write 2-6 patterns per field. Each pattern should target a different way patients express
the same concept. Prefer patterns with enumerated word lists over open capture groups."""


def evaluate_patterns(
    patterns: list[str],
    examples: list[dict],
    negative_examples: list[dict] | None = None,
) -> dict:
    """Test compiled patterns against positive and negative example texts.

    Positive examples: patterns must match these (hit rate).
    Negative examples: patterns must NOT match these (false positive rate).
    Both rates are reported back to Sonnet so it can self-correct in both directions.
    """
    compiled = []
    compile_errors = []
    for p in patterns:
        try:
            compiled.append(re.compile(p, re.I))
        except re.error as e:
            compile_errors.append({"pattern": p, "error": str(e)})

    # Test positive examples
    hits = []
    misses = []
    for ex in examples:
        text = ex.get("text", "")
        expected = ex.get("extracted_value", "")
        matched = False
        matched_by = None
        captured_value = None
        for cp in compiled:
            m = cp.search(text)
            if m:
                matched = True
                matched_by = cp.pattern
                captured_value = (m.group(1) if m.lastindex else m.group(0)) or m.group(0)
                break
        if matched:
            hits.append({
                "text": text,
                "expected_value": expected,
                "captured_value": captured_value,
                "matched_by": matched_by,
            })
        else:
            misses.append({
                "text": text,
                "expected_value": expected,
            })

    # Test negative examples — these should NOT match
    false_positives = []
    true_negatives = []
    for neg in (negative_examples or []):
        text = neg.get("text", "")
        matched = False
        matched_by = None
        captured_value = None
        for cp in compiled:
            m = cp.search(text)
            if m:
                matched = True
                matched_by = cp.pattern
                captured_value = (m.group(1) if m.lastindex else m.group(0)) or m.group(0)
                break
        if matched:
            false_positives.append({
                "text": text,
                "captured_value": captured_value,
                "matched_by": matched_by,
            })
        else:
            true_negatives.append({"text": text})

    n_neg = len(negative_examples) if negative_examples else 0
    fp_rate = len(false_positives) / n_neg if n_neg > 0 else 0.0

    return {
        "total_examples": len(examples),
        "hits": len(hits),
        "misses": len(misses),
        "hit_rate": len(hits) / len(examples) if examples else 0,
        "compile_errors": compile_errors,
        "missed_examples": misses,
        "hit_details": hits,
        "total_negatives": n_neg,
        "false_positives": len(false_positives),
        "false_positive_rate": fp_rate,
        "false_positive_details": false_positives,
    }


def run_phase2_build_regex(
    client: anthropic.Anthropic,
    candidates: list[dict],
    workers: int = 10,
) -> list[dict]:
    """Stage 2: Sonnet writes and tests regex for each candidate."""
    print("\n" + "=" * 60)
    print("  Stage 2: Regex Generation (Sonnet)")
    print("  Writing and validating patterns for each field...")
    print("=" * 60 + "\n")

    validated_fields = []
    print_lock = threading.Lock()
    results_lock = threading.Lock()
    total = len(candidates)

    def process_field(i: int, candidate: dict, total: int):
        """Process a single field candidate; returns (result_dict_or_None, list_of_log_lines)."""
        log: list[str] = []

        name = candidate["field_name"]
        desc = candidate["description"]
        examples = candidate["examples"]
        negative_examples = candidate.get("negative_examples", [])

        # Improvement 2: skip fields that the LLM flagged as not regex-extractable
        if not candidate.get("regex_extractable", True):
            log.append(
                f"  [{i}/{total}] {name} — SKIPPED "
                f"(llm_only: {candidate.get('extractability_note', 'not regex-extractable')})"
            )
            return {
                "field_name": name,
                "description": desc,
                "patterns": [],
                "hit_rate": 0,
                "examples_tested": 0,
                "confidence": "low",
                "frequency_hint": candidate.get("frequency_hint", "occasional"),
                "research_value": candidate.get("research_value", ""),
                "source": "llm_discovered",
                "llm_only": True,
                "extractability_note": candidate.get("extractability_note", ""),
                "allowed_values": candidate.get("allowed_values"),
                "trigger_vocabulary": candidate.get("trigger_vocabulary", []),
            }, log

        log.append(f"  [{i}/{total}] {name}")
        log.append(f"    Description: {desc[:80]}...")
        log.append(f"    Examples: {len(examples)}  Negatives: {len(negative_examples)}")

        # Build positive examples block
        examples_block = "\n".join(
            f"  - Text: \"{ex['text']}\"\n    Capture: \"{ex.get('extracted_value', '?')}\"  "
            f"← this is the SHORT value (1-5 words) the capture group should return"
            for ex in examples
        )

        # Build negative examples block
        negatives_block = ""
        if negative_examples:
            neg_lines = "\n".join(
                f"  - \"{neg['text']}\""
                for neg in negative_examples
            )
            negatives_block = (
                f"\nTexts that look similar but must NOT match:\n{neg_lines}\n"
                f"Your patterns must avoid matching these — they are false positive traps.\n"
            )

        # Improvement 1: trigger vocabulary anchor block
        trigger_vocab = candidate.get("trigger_vocabulary", [])
        anchor_block = ""
        if trigger_vocab:
            anchor_block = (
                f"\nAnchor vocabulary (words that typically appear near a true positive):\n"
                f"  {', '.join(trigger_vocab)}\n"
                f"Use these as context anchors in lookbehind/lookahead when designing patterns.\n"
            )

        # Improvement 3: allowed values block
        allowed_values = candidate.get("allowed_values")
        av_block = ""
        if allowed_values:
            av_block = (
                f"\nAllowed values for this field: {json.dumps(allowed_values)}\n"
                f"Build tight alternation patterns using ONLY these values: "
                f"\\b({'|'.join(re.escape(v) for v in allowed_values)})\\b\n"
                f"Do NOT use open capture groups — the value MUST be one of the listed options.\n"
            )

        user_message = (
            f"Write Python regex patterns to extract the field '{name}'.\n\n"
            f"Description: {desc}\n\n"
            f"IMPORTANT: The capture group must return only a SHORT value (1-5 words) — "
            f"just the entity name or label. Do NOT write patterns with broad capture groups "
            f"that grab long phrases or full sentences.\n\n"
            f"Positive examples (patterns MUST match these):\n{examples_block}\n"
            f"{negatives_block}"
            f"{anchor_block}"
            f"{av_block}\n"
            f"Remember: patterns are compiled with re.IGNORECASE."
        )

        best_patterns = []
        best_hit_rate = 0.0
        report = None

        for iteration in range(MAX_REGEX_ITERATIONS):
            if iteration > 0 and report is not None:
                # Build detailed test results so Sonnet sees exactly what happened
                passed_block = ""
                if report["hit_details"]:
                    passed_lines = []
                    for h in report["hit_details"]:
                        passed_lines.append(
                            f"  PASS: \"{h['text']}\"\n"
                            f"    Expected: \"{h['expected_value']}\"  |  Captured: \"{h['captured_value']}\"\n"
                            f"    Matched by: {h['matched_by']}"
                        )
                    passed_block = "PASSED examples:\n" + "\n".join(passed_lines) + "\n\n"

                missed_block = "\n".join(
                    f"  FAIL: \"{m['text']}\"\n    Expected: \"{m['expected_value']}\"  |  Captured: nothing"
                    for m in report["missed_examples"]
                )

                fp_block = ""
                if report["false_positive_details"]:
                    fp_lines = "\n".join(
                        f"  FALSE POSITIVE: \"{fp['text']}\"\n"
                        f"    Incorrectly captured: \"{fp['captured_value']}\"\n"
                        f"    Matched by: {fp['matched_by']}"
                        for fp in report["false_positive_details"]
                    )
                    fp_block = (
                        f"\nFALSE POSITIVES — your patterns matched these but should NOT have "
                        f"({report['false_positives']}/{report['total_negatives']} = "
                        f"{report['false_positive_rate']:.0%} false positive rate):\n"
                        f"{fp_lines}\n"
                        f"Tighten these patterns — add anchors, require more specific context, "
                        f"or narrow the capture group.\n"
                    )

                error_block = ""
                if report["compile_errors"]:
                    error_block = "\n\nCOMPILE ERRORS (fix or replace these):\n" + "\n".join(
                        f"  - {e['pattern']} → {e['error']}" for e in report["compile_errors"]
                    )

                user_message = (
                    f"Your previous patterns for '{name}' scored "
                    f"{report['hit_rate']:.0%} hit rate ({report['hits']}/{report['total_examples']}) "
                    f"and {report['false_positive_rate']:.0%} false positive rate "
                    f"({report['false_positives']}/{report['total_negatives']}).\n\n"
                    f"Goal: maximise hit rate AND minimise false positives.\n\n"
                    f"Full test results:\n\n"
                    f"{passed_block}"
                    f"FAILED examples:\n{missed_block}"
                    f"{fp_block}"
                    f"{error_block}\n\n"
                    f"{anchor_block}"
                    f"{av_block}"
                    f"Previous patterns:\n" +
                    "\n".join(f"  - {p}" for p in best_patterns) +
                    f"\n\nWrite an IMPROVED set of patterns. Keep patterns that worked. "
                    f"Fix patterns that caused false positives by adding tighter anchors or "
                    f"narrower capture groups. Add or modify patterns to catch FAILED examples. "
                    f"Reminder: capture groups must return only 1-5 words."
                )

            iter_line = f"    Iteration {iteration + 1}/{MAX_REGEX_ITERATIONS}..."

            raw = call_model(client, SONNET, SONNET_SYSTEM_PROMPT, user_message, MAX_TOKENS_SONNET)
            parsed = parse_json_response(raw)

            if not parsed or "patterns" not in parsed:
                log.append(iter_line + " PARSE FAILED")
                continue

            patterns = parsed["patterns"]
            report = evaluate_patterns(patterns, examples, negative_examples)

            fp_info = (
                f"  FP: {report['false_positives']}/{report['total_negatives']}"
                if report["total_negatives"] > 0 else ""
            )
            log.append(
                iter_line
                + f" {report['hits']}/{report['total_examples']} matched ({report['hit_rate']:.0%})"
                + fp_info
            )

            if report["compile_errors"]:
                log.append(f"    ⚠ {len(report['compile_errors'])} compile error(s)")

            if report["hit_rate"] > best_hit_rate:
                best_hit_rate = report["hit_rate"]
                # Only keep patterns that actually compile
                best_patterns = [
                    p for p in patterns
                    if p not in [e["pattern"] for e in report["compile_errors"]]
                ]

            if report["hit_rate"] >= 0.8:
                break

        if best_patterns and best_hit_rate >= 0.5:
            result = {
                "field_name": name,
                "description": desc,
                "patterns": best_patterns,
                "hit_rate": best_hit_rate,
                "examples_tested": len(examples),
                "confidence": "medium",
                "frequency_hint": candidate.get("frequency_hint", "occasional"),
                "research_value": candidate.get("research_value", ""),
                "source": "llm_discovered",
                "llm_only": False,
                "extractability_note": candidate.get("extractability_note", ""),
                "allowed_values": candidate.get("allowed_values"),
                "trigger_vocabulary": candidate.get("trigger_vocabulary", []),
            }
            log.append(f"    ACCEPTED ({best_hit_rate:.0%} hit rate, {len(best_patterns)} patterns)")
        else:
            result = None
            log.append(f"    REJECTED (best hit rate: {best_hit_rate:.0%})")

        return result, log

    futures = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for i, candidate in enumerate(candidates, 1):
            future = executor.submit(process_field, i, candidate, total)
            futures[future] = i

        for future in as_completed(futures):
            result, log_lines = future.result()
            with print_lock:
                for line in log_lines:
                    print(line)
            if result is not None:
                with results_lock:
                    validated_fields.append(result)

    print(f"\n  Validated fields: {len(validated_fields)}/{len(candidates)}")
    return validated_fields


# =============================================================================
# PHASE 3: EXTRACT WITH NEW REGEX (free)
# =============================================================================

def run_phase3_regex_extract(
    validated_fields: list[dict],
    corpus_items: list[dict],
    workers: int = 10,
) -> list[dict]:
    """Stage 3: Run the new regex patterns across the full corpus (parallel)."""
    print("\n" + "=" * 60)
    print("  Stage 3: Regex Extraction")
    print(f"  {len(corpus_items)} records, {workers} workers, "
          f"text cap {MAX_TEXT_CHARS_PHASE3 // 1000}k chars/record")
    print("=" * 60 + "\n")

    # Compile all patterns once, shared across threads (re compiled objects are thread-safe)
    field_patterns: dict[str, list] = {}
    field_allowed_values: dict[str, dict[str, str] | None] = {}
    for field in validated_fields:
        # Improvement 2: skip llm_only fields (no patterns to compile)
        if field.get("llm_only"):
            continue
        compiled = []
        for p in field["patterns"]:
            try:
                compiled.append(re.compile(p, re.I))
            except re.error:
                continue
        if compiled:
            field_patterns[field["field_name"]] = compiled
        # Improvement 3: build allowed values map for normalization
        av = field.get("allowed_values")
        if av:
            field_allowed_values[field["field_name"]] = {v.lower(): v for v in av}
        else:
            field_allowed_values[field["field_name"]] = None

    total = len(corpus_items)
    records: list[dict | None] = [None] * total  # pre-sized so order is preserved
    field_hit_counts: dict[str, int] = defaultdict(int)
    print_lock = threading.Lock()
    counts_lock = threading.Lock()
    stats = {"hits": 0, "timeouts": 0, "done": 0}

    def process_item(idx: int, item: dict) -> None:
        # Run each text segment individually to prevent cross-post regex bleed.
        # Concatenating all texts into one blob lets capture groups span post
        # boundaries, pulling in unrelated content from the next post/comment.
        texts = item["texts"]

        extracted: dict[str, list] = {}
        record_hits = 0
        record_timeouts = 0
        timeout_msgs: list[str] = []

        for field_name, patterns in field_patterns.items():
            matches: list[str] = []
            chars_seen = 0
            for text in texts:
                if chars_seen >= MAX_TEXT_CHARS_PHASE3:
                    break
                text_slice = text
                remaining = MAX_TEXT_CHARS_PHASE3 - chars_seen
                if len(text_slice) > remaining:
                    text_slice = text_slice[:remaining]
                chars_seen += len(text_slice)
                for pat in patterns:
                    try:
                        found = _finditer_with_timeout(pat, text_slice, timeout=2.0)
                    except TimeoutError:
                        record_timeouts += 1
                        timeout_msgs.append(
                            f"    ⚠ timeout: '{field_name}' — {pat.pattern[:60]}"
                        )
                        continue
                    for m in found:
                        value = m.group(1) if m.lastindex else m.group(0)
                        if value is None:
                            continue
                        value = value.strip()
                        if value and value.lower() not in [v.lower() for v in matches]:
                            matches.append(value)
            # Improvement 3 / 7: normalize matches to canonical allowed values
            av_map = field_allowed_values.get(field_name)
            if av_map is not None:
                normalized = []
                for val in matches:
                    canonical = av_map.get(val.lower())
                    if canonical is not None:
                        normalized.append(canonical)
                matches = normalized
            if matches:
                extracted[field_name] = matches
                record_hits += 1

        record = {
            "_patientpunk_version": "2.0",
            "_extraction_method": "discovered_regex",
            "_extracted_at": datetime.now(timezone.utc).isoformat(),
            "record_meta": {
                "author_hash": item["author_hash"],
                "source": item["source"],
                "post_id": item.get("post_id"),
                "text_count": len(item["texts"]),
            },
            "discovered_fields": {
                fname: {
                    "values": extracted.get(fname),
                    "provenance": "regex" if extracted.get(fname) else None,
                    "confidence": "medium" if extracted.get(fname) else None,
                    "source": "llm_discovered",
                }
                for fname in field_patterns
            },
        }

        with counts_lock:
            records[idx] = record
            stats["hits"] += record_hits
            stats["timeouts"] += record_timeouts
            stats["done"] += 1
            for fname in extracted:
                field_hit_counts[fname] += 1
            n = stats["done"]

        with print_lock:
            timeout_str = f"  ⚠{record_timeouts}" if record_timeouts else ""
            print(
                f"  [{n}/{total}] {(item.get('author_hash') or '?')[:10]}...  "
                f"{record_hits} fields hit{timeout_str}",
                flush=True,
            )
            for msg in timeout_msgs:
                print(msg, flush=True)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(process_item, i, item)
            for i, item in enumerate(corpus_items)
        ]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                with print_lock:
                    print(f"  ERROR: {e}", flush=True)

    print(f"\n  Done. {stats['hits']} total field hits across {total} records"
          + (f", {stats['timeouts']} timeout(s)" if stats["timeouts"] else ""))
    print(f"\n  Regex hit counts:")
    for field, count in sorted(field_hit_counts.items(), key=lambda x: -x[1]):
        print(f"    {field:<35} {count}/{total} ({count/total:.0%})")

    return records  # type: ignore[return-value]


# =============================================================================
# PHASE 4: FILL GAPS (Haiku)
# =============================================================================

SAVE_EVERY_N = 20


def run_phase4_fill_gaps(
    client: anthropic.Anthropic,
    validated_fields: list[dict],
    corpus_items: list[dict],
    phase3_records: list[dict],
    workers: int = 10,
    resume: bool = False,
    records_file: Path | None = None,
) -> list[dict]:
    """Stage 4: Haiku fills in fields that regex missed (concurrent)."""
    print("\n" + "=" * 60)
    print("  Stage 4: Gap Filling (Haiku)")
    print("  LLM extracting where regex missed...")
    print("=" * 60 + "\n")

    # Resume: load existing records and merge back over the Phase 3 baseline
    already_done = 0
    if resume and records_file and records_file.exists():
        with open(records_file, encoding="utf-8") as f:
            existing = json.load(f)
        existing_index: dict[tuple, dict] = {}
        for rec in existing:
            meta = rec.get("record_meta", {})
            key = (meta.get("author_hash"), meta.get("post_id"))
            existing_index[key] = rec
        for i, rec in enumerate(phase3_records):
            meta = rec.get("record_meta", {})
            key = (meta.get("author_hash"), meta.get("post_id"))
            if key in existing_index:
                phase3_records[i] = existing_index[key]
        already_done = len(existing_index)
        print(f"  Resumed: {already_done} records loaded from existing file")

    # Find records where at least one discovered field is still null
    gaps = []
    for i, (item, record) in enumerate(zip(corpus_items, phase3_records)):
        null_fields = [
            f for f, data in record.get("discovered_fields", {}).items()
            if data.get("values") is None
        ]
        if null_fields:
            gaps.append((i, item, record, null_fields))

    if not gaps:
        print("  No gaps to fill — regex covered everything!")
        return phase3_records

    print(f"  {len(gaps)} records have gaps to fill\n")

    # Improvement 3 / 7: build allowed_values maps for normalization in Phase 4
    field_av_maps: dict[str, dict[str, str] | None] = {}
    for f in validated_fields:
        av = f.get("allowed_values")
        field_av_maps[f["field_name"]] = {v.lower(): v for v in av} if av else None

    # Build field descriptions for the prompt (Improvement 3: include allowed values)
    field_lines = []
    for f in validated_fields:
        line = f"  - {f['field_name']}: {f['description']}"
        if f.get("allowed_values"):
            line += f" — ONLY return one of: {json.dumps(f['allowed_values'])}"
        field_lines.append(line)
    field_desc_block = "\n".join(field_lines)

    system_prompt = f"""You are a biomedical data extraction assistant for PatientPunk.
Extract ONLY the following discovered fields from patient-authored text.
Only extract explicitly stated information. Return null for fields with no evidence.

FIELDS TO EXTRACT:
{field_desc_block}

RESPONSE FORMAT — valid JSON:
{{
  "fields": {{
    "field_name": ["value1", "value2"] or null
  }}
}}

Include ALL listed fields. Use null when no evidence exists."""

    save_lock = threading.Lock()
    print_lock = threading.Lock()
    stats = {"filled": 0, "completed": 0, "failed": 0}

    def process_gap(args: tuple) -> None:
        record_i, item, record, null_fields = args

        combined = "\n\n---NEW POST---\n\n".join(item["texts"])
        if len(combined) > MAX_TEXT_CHARS:
            combined = combined[:MAX_TEXT_CHARS] + "\n[TRUNCATED]"

        user_message = (
            f"Extract these specific fields: {', '.join(null_fields)}\n\n"
            f"Each section separated by ---NEW POST--- is a separate Reddit post or comment. "
            f"Do not quote or combine text that spans across these boundaries.\n\n"
            f"Text:\n{combined}"
        )

        raw = call_model(client, HAIKU, system_prompt, user_message)
        parsed = parse_json_response(raw)

        local_fills = 0
        if parsed and "fields" in parsed:
            for field_name, values in parsed["fields"].items():
                if values and field_name in record.get("discovered_fields", {}):
                    current = record["discovered_fields"][field_name]
                    if current.get("values") is None:
                        if isinstance(values, str):
                            values = [values]
                        values = [v for v in values if v]
                        # Improvement 3 / 7: normalize to allowed values if applicable
                        av_map = field_av_maps.get(field_name)
                        if av_map is not None and isinstance(values, list):
                            values = [av_map[v.lower()] for v in values if isinstance(v, str) and v.lower() in av_map]
                        elif av_map is not None and isinstance(values, str):
                            values = [av_map[values.lower()]] if values.lower() in av_map else []
                        if not values:
                            continue  # skip if normalization eliminated all values
                        if values:
                            current["values"] = values
                            current["provenance"] = "llm_filled"
                            current["confidence"] = "low"
                            local_fills += 1

        with save_lock:
            phase3_records[record_i] = record
            stats["filled"] += local_fills
            if not parsed or "fields" not in parsed:
                stats["failed"] += 1
            stats["completed"] += 1
            n = stats["completed"]
            if n % 10 == 0 or n == len(gaps):
                with print_lock:
                    print(
                        f"  {n}/{len(gaps)} "
                        f"({stats['filled']} fills, {stats['failed']} failed)",
                        flush=True,
                    )
            # Incremental save
            if records_file and n % SAVE_EVERY_N == 0:
                with open(records_file, "w", encoding="utf-8") as f:
                    json.dump(phase3_records, f, ensure_ascii=False, indent=2)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(process_gap, g) for g in gaps]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                with print_lock:
                    print(f"  Worker error: {e}")

    print(f"\n  Filled {stats['filled']} field gaps across {len(gaps)} records")
    return phase3_records


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
            f"Auto-discovered extension schema generated by discover_fields.py. "
            f"All fields are tagged source: llm_discovered."
        ),
        "_generated_at": discovered_at,
        "_base_schema": base_schema_id,
        "_version": "1.0",
        "include_base_fields": [],
        "override_base_patterns": {},
        "extension_fields": {},
    }

    for field in validated_fields:
        schema["extension_fields"][field["field_name"]] = {
            "description": field["description"],
            "confidence": field.get("confidence", "medium"),
            "source": "llm_discovered",
            "_discovered_at": discovered_at,
            "hit_rate_at_discovery": field.get("hit_rate", 0),
            "frequency_hint": field.get("frequency_hint", "occasional"),
            "research_value": field.get("research_value", ""),
            "patterns": field["patterns"],
            "llm_only": field.get("llm_only", False),
            "extractability_note": field.get("extractability_note", ""),
            "allowed_values": field.get("allowed_values"),
        }

    return schema


def merge_into_schema(
    validated_fields: list[dict],
    existing_schema: dict,
) -> tuple[dict, int, int]:
    """Merge newly discovered fields into an existing schema in-place.

    New fields are tagged with _discovered_at. Existing fields are never
    overwritten — run again with an updated schema to skip them next time.

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
            "hit_rate_at_discovery": field.get("hit_rate", 0),
            "frequency_hint": field.get("frequency_hint", "occasional"),
            "research_value": field.get("research_value", ""),
            "patterns": field["patterns"],
            "llm_only": field.get("llm_only", False),
            "extractability_note": field.get("extractability_note", ""),
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
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Multi-model field discovery pipeline for PatientPunk.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Pipeline phases:
  Phase 1 (Haiku)  : Scan corpus for new field candidates with examples
  Phase 2 (Sonnet) : Write regex patterns, test against examples, self-iterate
  Phase 3 (regex)  : Run validated patterns across full corpus (free).
                     Each text segment is matched individually — regex never
                     runs across a concatenated blob — to prevent cross-post
                     bleed where capture groups would pull content from the
                     wrong post or comment.
  Phase 4 (Haiku)  : Fill gaps where regex missed. Posts are separated by
                     ---NEW POST--- and Haiku is instructed not to span
                     boundaries when extracting.

Defaults (fast mode on by default):
  --workers 10           Phase 1 and Phase 4 run 10 concurrent API calls
  --per-item-chars 0     Full text per item (default). Use --per-item-chars 3000
                         for ~4x cheaper Phase 1 once you're done testing.
  Phase 4 enabled        Use --no-fill to skip gap filling
  No resume              Use --resume to continue a previous Phase 4 run

Schema library workflow (recommended):
  Pass --schema to merge discoveries into your disease-specific schema file.
  Each new field is tagged _discovered_at. Existing fields are never overwritten.
  Run repeatedly — each run adds only what's new.

  python discover_fields.py --schema schemas/covidlonghaulers_schema.json
  python discover_fields.py --schema schemas/covidlonghaulers_schema.json --limit 20 --no-fill

  Then use the same schema everywhere:
  python extract_biomedical.py --schema schemas/covidlonghaulers_schema.json
  python llm_extract.py --schema schemas/covidlonghaulers_schema.json

Standalone workflow (no --schema):
  Creates schemas/discovered_{timestamp}.json with this run's fields only.

  python discover_fields.py                              # full pipeline (fast, 10 workers)
  python discover_fields.py --limit 20 --no-fill         # cheap test run
  python discover_fields.py --workers 1                  # sequential (debug)
  python discover_fields.py --resume                     # continue interrupted Phase 4
  python discover_fields.py --candidates output/phase1_candidates.json  # skip Phase 1
  python discover_fields.py --sample 50                  # random 50-item sample (diverse + cheap)
  python discover_fields.py --per-item-chars 0           # send full text per item (thorough)

Output:
  --schema provided  : updates the schema file in place
  no --schema        : schemas/discovered_{timestamp}.json  (new file each run)
  output/discovered_records_{schema_id}.json             extraction results (saved incrementally)
  output/discovered_field_report_{schema_id}.json        coverage stats and report

All auto-discovered fields are tagged source: llm_discovered and _discovered_at (timestamp).

Cost estimate (~220 posts corpus): Phase 1 ~$0.05-0.15, Phase 2 ~$0.50-2.00,
Phase 4 ~$0.05-0.15. Total ~$1-3. Use --limit 20 --no-fill to test cheaply first.
        """,
    )
    parser.add_argument(
        "--input-dir", type=Path,
        default=Path(__file__).parent.parent / "output",
        help="Path to the output/ directory from scrape_corpus.py",
    )
    parser.add_argument(
        "--schema", type=Path, default=None,
        help=(
            "Disease-specific schema file to update (e.g. schemas/covidlonghaulers_schema.json). "
            "Discovered fields are merged INTO this file — existing fields are never overwritten, "
            "new fields are tagged with _discovered_at. "
            "Without --schema, a new discovered_{timestamp}.json file is created instead."
        ),
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit Phase 1 corpus scan to N records (cost control)",
    )
    parser.add_argument(
        "--no-fill", action="store_true",
        help="Skip Phase 4 (gap filling). Only discover + generate regex.",
    )
    parser.add_argument(
        "--workers", type=int, default=10,
        help="Concurrent API workers for Phase 1 and Phase 4 (default: 10). Use --workers 1 to disable.",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume Phase 4 from an existing records file, skipping already-filled records.",
    )
    parser.add_argument(
        "--candidates", type=Path, default=None,
        help=(
            "Load Phase 1 candidates from a saved JSON file and skip Phase 1 entirely. "
            "Phase 1 results are always saved to output/phase1_candidates.json after each run. "
            "Note: run_pipeline.py auto-detects output/phase1_candidates.json and passes it "
            "automatically — use --candidates here to override or specify a different file."
        ),
    )
    parser.add_argument(
        "--sample", type=int, default=None,
        help=(
            "Randomly sample N corpus items for Phase 1 instead of using all (or --limit). "
            "More representative than --limit (which takes the first N alphabetically). "
            "Example: --sample 50"
        ),
    )
    parser.add_argument(
        "--per-item-chars", type=int, default=MAX_TEXT_CHARS_PER_ITEM_PHASE1,
        help=(
            "Max characters taken from each corpus item in Phase 1 (default: 0 = full text). "
            "Smaller = denser batches = fewer API calls = lower cost. "
            "Example: --per-item-chars 3000 for ~4x cheaper Phase 1."
        ),
    )
    parser.add_argument(
        "--temp-dir", type=Path, default=None,
        help="Directory for intermediate output files (default: {input-dir}/temp/).",
    )
    args = parser.parse_args()

    output_dir = args.input_dir
    if not output_dir.exists():
        sys.exit(f"Error: {output_dir} does not exist. Run scrape_corpus.py first.")

    temp_dir = args.temp_dir if args.temp_dir else output_dir / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Load existing schema for context
    existing_schema = None
    _base_field_names = [
        "age", "sex_gender", "location_country", "healthcare_system",
        "conditions", "onset_trigger", "diagnosis_source", "time_to_diagnosis",
        "misdiagnosis", "symptom_duration", "symptom_trajectory", "age_at_onset",
        "medications", "treatment_outcome", "procedures",
        "activity_level", "work_disability_status", "mental_health",
        "doctor_dismissal", "diagnostic_odyssey",
        "prior_infections", "hormonal_events", "family_history",
        "location_us_state", "ethnicity", "occupation", "bmi_weight",
        "dosage", "dietary_interventions", "alternative_treatments",
        "genetic_testing", "social_impact", "trauma_history",
        "toxic_exposures", "healthcare_costs",
    ]
    # Improvement 5: build known_fields as a list supporting both strings and dicts
    known_fields_seen: set[str] = set()
    known_fields: list = []
    for name in _base_field_names:
        if name not in known_fields_seen:
            known_fields_seen.add(name)
            known_fields.append(name)

    if args.schema:
        if not args.schema.exists():
            sys.exit(f"Schema file not found: {args.schema}")
        with open(args.schema, encoding="utf-8") as f:
            existing_schema = json.load(f)
        # Add extension fields WITH descriptions (Improvement 5: cross-field distinctiveness)
        for fname, fdata in existing_schema.get("extension_fields", {}).items():
            if fname not in known_fields_seen:
                known_fields_seen.add(fname)
                known_fields.append({"name": fname, "description": fdata.get("description", "")})

    base_schema_id = existing_schema["schema_id"] if existing_schema else None

    client = get_client()

    print("=" * 60)
    print("  PatientPunk Field Discovery Pipeline")
    print(f"  Models      : Haiku (scan/fill) + Sonnet (regex)")
    print(f"  Target schema : {args.schema or 'new file (no --schema)'}")
    print(f"  Known fields  : {len(known_fields)}")
    print(f"  Corpus limit  : {args.sample and f'sample {args.sample}' or args.limit or 'all'}")
    print(f"  Per-item chars: {args.per_item_chars or 'unlimited'}")
    print(f"  Gap fill      : {'yes' if not args.no_fill else 'no'}")
    print(f"  Workers       : {args.workers}")
    print(f"  Resume        : {'yes' if args.resume else 'no'}")
    print("=" * 60)

    start_time = datetime.now(timezone.utc)
    candidates_file = temp_dir / "phase1_candidates.json"

    # Always load corpus — needed for Phase 3 and 4 regardless of whether
    # Phase 1 runs or is loaded from cache.
    print("\nLoading corpus...")
    corpus_items = load_corpus_texts(output_dir, limit=None)  # Phase 3 always uses full corpus
    print(f"  {len(corpus_items)} items loaded")

    # Phase 1: Discover (or load from cache)
    if args.candidates:
        if not args.candidates.exists():
            sys.exit(f"Candidates file not found: {args.candidates}")
        with open(args.candidates, encoding="utf-8") as f:
            candidates = json.load(f)
        print(f"\nLoaded {len(candidates)} Phase 1 candidates from {args.candidates} (skipping Phase 1)")
        print(f"  NOTE: Old cache files lack new keys (trigger_vocabulary, allowed_values, etc.).")
        print(f"  If you see missing-key errors, regenerate by removing --candidates.")
    else:
        # Apply limit/sample only for Phase 1 scan
        phase1_items = corpus_items
        if args.sample and args.sample < len(phase1_items):
            phase1_items = random.sample(phase1_items, args.sample)
            print(f"  Using random sample of {args.sample} items for Phase 1")
        elif args.limit and args.limit < len(phase1_items):
            phase1_items = phase1_items[:args.limit]
            print(f"  Using first {args.limit} items for Phase 1")

        candidates = run_phase1_discovery(
            client, phase1_items, known_fields,
            workers=args.workers,
            per_item_chars=args.per_item_chars,
            schema_data=existing_schema,
        )

        if candidates:
            with open(candidates_file, "w", encoding="utf-8") as f:
                json.dump(candidates, f, ensure_ascii=False, indent=2)
            print(f"\n  Phase 1 saved: {candidates_file}")
            print(f"  (If Phase 2 fails, resume with: --candidates {candidates_file})")

    if not candidates:
        print("\nNo new fields discovered. The existing schema may already cover this corpus well.")
        return

    # Phase 2: Build regex
    validated_fields = run_phase2_build_regex(client, candidates, workers=args.workers)

    if not validated_fields:
        print("\nNo fields passed regex validation. Try with more corpus data (increase --limit).")
        return

    regex_fields = [f for f in validated_fields if not f.get("llm_only")]
    llm_only_fields = [f for f in validated_fields if f.get("llm_only")]
    if llm_only_fields:
        print(f"\n  {len(llm_only_fields)} llm_only field(s) (no regex, Phase 4 gap-fill only):")
        for f in llm_only_fields:
            print(f"    {f['field_name']}: {f.get('extractability_note', 'not regex-extractable')}")

    # Always generate a new discovery schema file in temp/.
    # If --schema was provided it is used READ-ONLY for known-field context —
    # discovered fields are never merged back into it, keeping the curated
    # schema clean. Each run produces its own discovered_{timestamp}.json.
    schema = generate_schema(validated_fields, base_schema_id)
    schema_file = temp_dir / f"{schema['schema_id']}.json"
    with open(schema_file, "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)
    print(f"\n  Discovery schema saved: {schema_file}")

    # Phase 3: Extract with new regex across the full corpus
    records = run_phase3_regex_extract(validated_fields, corpus_items, workers=args.workers)

    # Phase 4: Fill gaps
    schema_id = schema["schema_id"]
    records_file = temp_dir / f"discovered_records_{schema_id}.json"
    if not args.no_fill:
        records = run_phase4_fill_gaps(
            client, validated_fields, corpus_items, records,
            workers=args.workers,
            resume=args.resume,
            records_file=records_file,
        )

    # Save records (final write — Phase 4 also saves incrementally)
    with open(records_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    # Schema health update skipped — discovered fields now live in temp/,
    # not in the curated --schema file, so bleed rates are not written back.

    # Build and save report
    end_time = datetime.now(timezone.utc)
    duration = (end_time - start_time).total_seconds()

    field_stats = {}
    for field in validated_fields:
        fname = field["field_name"]
        regex_hits = sum(
            1 for r in records
            if r.get("discovered_fields", {}).get(fname, {}).get("provenance") == "regex"
        )
        llm_hits = sum(
            1 for r in records
            if r.get("discovered_fields", {}).get(fname, {}).get("provenance") == "llm_filled"
        )
        field_stats[fname] = {
            "regex_hits": regex_hits,
            "llm_filled": llm_hits,
            "total_hits": regex_hits + llm_hits,
            "coverage": (regex_hits + llm_hits) / len(records) if records else 0,
            "hit_rate_at_discovery": field.get("hit_rate", 0),
            "pattern_count": len(field["patterns"]),
            "source": "llm_discovered",
        }

    report = {
        "pipeline_run": {
            "started_at": start_time.isoformat(),
            "finished_at": end_time.isoformat(),
            "duration_seconds": duration,
            "corpus_items": len(corpus_items),
            "discovery_limit": args.limit,
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

    report_file = temp_dir / f"discovered_field_report_{schema_id}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  Pipeline Complete ({duration:.0f}s)")
    print(f"  Candidates discovered : {len(candidates)}")
    print(f"  Fields validated      : {len(validated_fields)}")
    print(f"  Records extracted     : {len(records)}")
    print(f"  Schema                : {schema_file}")
    print(f"  Records               : {records_file}")
    print(f"  Report                : {report_file}")
    print(f"\n  Discovered fields:")
    for fname, stats in sorted(field_stats.items(), key=lambda x: -x[1]["total_hits"]):
        print(
            f"    {fname:<35} "
            f"regex: {stats['regex_hits']:>3}  "
            f"llm: {stats['llm_filled']:>3}  "
            f"total: {stats['total_hits']:>3} ({stats['coverage']:.0%})"
        )
    print(f"{'=' * 60}")

    print(f"\n  Next steps:")
    print(f"  1. Review {schema_file.name} — edit/remove fields as needed")
    print(f"  2. Run regex extractor with the new schema:")
    print(f"       python extract_biomedical.py --schema schemas/{schema_file.name}")
    print(f"  3. Or use it with llm_extract.py for merged results:")
    print(f"       python llm_extract.py --schema schemas/{schema_file.name} --merge")


if __name__ == "__main__":
    main()
