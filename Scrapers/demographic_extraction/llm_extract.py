#!/usr/bin/env python3
"""LLM-based biomedical extractor for PatientPunk.

Second-pass extraction using Claude Haiku. Reads the same corpus as
extract_biomedical.py and produces structured records for the same schema
fields, PLUS suggests new fields the schema doesn't cover yet.

Designed to run AFTER regex extraction. The merge step combines both passes:
regex hits are high-confidence, LLM hits fill the gaps, and suggested fields
inform future schema evolution.

Usage:
    python llm_extract.py                              # base fields, default input
    python llm_extract.py --schema schemas/covidlonghaulers_schema.json
    python llm_extract.py --text "I'm a 34F with POTS, LDN helped my brain fog"
    python llm_extract.py --merge                      # combine with regex results
    python llm_extract.py --limit 10                   # cost control / testing
    python llm_extract.py --workers 10                 # more concurrency (default: 8)
    python llm_extract.py --skip-threshold 0.7         # skip records regex covered 70%+
    python llm_extract.py --focus-gaps                 # only ask LLM about null fields

Speed tips:
    --workers 8 (default) runs 8 requests in parallel — biggest single speedup.
    --skip-threshold 0.7 skips records where regex already found 70%+ of fields.
    --focus-gaps sends a shorter prompt asking only about the fields regex missed.
    Combine all three for maximum speed: --workers 10 --skip-threshold 0.7 --focus-gaps

Requires:
    pip install anthropic python-dotenv

    Copy .env.example to .env and add your Anthropic API key.

Output:
    output/llm_records_{schema_id}.json           # LLM extraction records
    output/llm_field_suggestions_{schema_id}.json  # Suggested new fields
    output/merged_records_{schema_id}.json         # Combined regex + LLM (--merge)
"""

import argparse
import json
import os
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

load_dotenv(Path(__file__).parent / ".env")              # demographic_extraction/.env
load_dotenv(Path(__file__).parent.parent / ".env")        # Scrapers/.env (fallback)
load_dotenv(Path(__file__).parent.parent.parent / ".env") # project root .env (fallback)


# =============================================================================
# CONSTANTS
# =============================================================================

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096
MAX_TEXT_CHARS = 30_000
RETRY_DELAYS = [2, 5, 15, 30]
SAVE_EVERY_N = 10   # flush incremental save every N completed records

# Subreddits known to contain health/chronic illness content.
# Text from these is prioritised when building the per-record prompt so the
# most relevant content always fits within MAX_TEXT_CHARS.
HEALTH_SUBREDDITS = {
    "covidlonghaulers", "longcovid", "cfs", "chronicfatigue",
    "mecfs", "pots", "dysautonomia", "mcas", "fibromyalgia",
    "ehlersdanlos", "lupus", "multiplesclerosis", "rheumatoidarthritis",
    "crohnsdisease", "ulcerativecolitis", "hashimotos", "lyme",
    "sarcoidosis", "interstitialcystitis", "endometriosis", "pcos",
    "chronicpain", "chronicillness", "invisibleillness", "spoonie",
    "autoimmune", "smallfiberneuropathy", "vaccinelonghauler",
    "longcovidwarriors", "postcovidrecovery",
}

BASE_FIELD_DESCRIPTIONS = {
    "age": "Patient's current age in years (numeric)",
    "sex_gender": "Biological sex or gender identity (e.g., female, male, non-binary)",
    "location_country": "Country of residence",
    "healthcare_system": "Healthcare system (NHS, Medicare, private insurance, etc.)",
    "conditions": "Medical diagnoses and conditions the patient has",
    "onset_trigger": "What triggered or preceded illness onset (infection, vaccine, surgery, etc.)",
    "diagnosis_source": "Who provided the diagnosis (specialist, GP, self-diagnosed, etc.)",
    "time_to_diagnosis": "How long it took to receive a diagnosis (e.g., '3 years', '14 months')",
    "misdiagnosis": "Previous incorrect diagnoses received",
    "symptom_duration": "How long symptoms have lasted",
    "symptom_trajectory": "Whether symptoms are improving, worsening, stable, or relapsing-remitting",
    "age_at_onset": "Patient's age when illness began",
    "medications": "Current or past medications mentioned",
    "treatment_outcome": "Response to specific treatments — MUST include both the treatment AND the outcome as a pair (e.g., 'LDN: helped brain fog', 'metoprolol: reduced heart rate but caused fatigue')",
    "procedures": "Medical procedures undergone (tilt table test, colonoscopy, MRI, etc.)",
    "activity_level": "Functional capacity (bedbound, housebound, limited, mostly functional, fully recovered)",
    "work_disability_status": "Work situation (working full-time, part-time, on disability, had to quit, etc.)",
    "mental_health": "Mental health conditions or impacts mentioned",
    "doctor_dismissal": "Experiences of being dismissed or disbelieved by doctors",
    "diagnostic_odyssey": "Long journey to diagnosis — many doctors, years undiagnosed",
    "prior_infections": "Prior infections relevant to current illness (EBV, COVID, Lyme, etc.)",
    "hormonal_events": "Hormonal events related to illness (pregnancy, menopause, puberty, etc.)",
    "family_history": "Family history of relevant medical conditions",
}

BASE_OPTIONAL_DESCRIPTIONS = {
    "location_us_state": "US state of residence",
    "ethnicity": "Patient's ethnicity or race (self-reported)",
    "occupation": "Patient's occupation or job type",
    "bmi_weight": "BMI or weight mentions",
    "dosage": "Medication dosages (e.g., '4.5mg LDN', '200mg CoQ10')",
    "dietary_interventions": "Dietary changes tried (gluten-free, low histamine, carnivore, etc.)",
    "alternative_treatments": "Alternative/complementary treatments (acupuncture, supplements, etc.)",
    "genetic_testing": "Genetic testing mentions (23andMe, MTHFR, HLA typing, etc.)",
    "social_impact": "Social impacts of illness (relationships, isolation, etc.)",
    "trauma_history": "Trauma or adverse childhood experiences",
    "toxic_exposures": "Environmental toxic exposures (mold, chemicals, etc.)",
    "healthcare_costs": "Out-of-pocket costs, insurance denials, financial burden",
}


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


def call_haiku(client: anthropic.Anthropic, system_prompt: str, user_message: str) -> str:
    """Call Haiku with retry/backoff and prompt caching.

    Thread-safe — Anthropic client is thread-safe.
    The system prompt is marked for caching: after the first request Anthropic
    serves it from cache at 1/10th the token cost with lower latency.
    """
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
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
        except anthropic.APIStatusError as e:
            if e.status_code >= 500 and attempt < len(RETRY_DELAYS):
                continue
            raise
    return ""


def parse_json_response(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                return None
    return None


# =============================================================================
# PROMPT CONSTRUCTION
# =============================================================================

def build_field_descriptions(schema: dict | None) -> dict[str, str]:
    fields = dict(BASE_FIELD_DESCRIPTIONS)
    if schema:
        for field in schema.get("include_base_fields", []):
            if field in BASE_OPTIONAL_DESCRIPTIONS:
                fields[field] = BASE_OPTIONAL_DESCRIPTIONS[field]
        for field, defn in schema.get("extension_fields", {}).items():
            fields[field] = defn.get("description", field)
    return fields


def build_system_prompt(field_descriptions: dict[str, str]) -> str:
    fields_block = "\n".join(
        f"  - {field}: {desc}" for field, desc in sorted(field_descriptions.items())
    )
    return f"""You are a biomedical data extraction assistant for the PatientPunk research project.
Your job is to read patient-authored text from Reddit and extract structured biomedical information.

EXTRACTION RULES:
1. Only extract information that is EXPLICITLY stated in the text. Never infer or guess.
2. If a field cannot be determined from the text, set it to null.
3. For treatment_outcome, ALWAYS pair the treatment with its outcome (e.g., "LDN: helped fatigue"). A treatment mentioned without an outcome goes in "medications" only, NOT in treatment_outcome.
4. Distinguish between what the AUTHOR says about THEMSELVES vs. what they say about OTHERS. Only extract self-reported information for the structured fields.
5. Pay attention to NEGATION: "I don't have POTS" means POTS should NOT be in conditions.
6. Pay attention to TEMPORAL context: "I had fatigue for 6 months but it resolved" — note the resolution.

SCHEMA FIELDS to extract:
{fields_block}

RESPONSE FORMAT — valid JSON only:
{{
  "fields": {{
    "field_name": ["value1", "value2"] or null
  }},
  "suggested_fields": [
    {{
      "field_name": "proposed_field_name_in_snake_case",
      "description": "What this captures and why it's scientifically useful",
      "values": ["value from this text"],
      "frequency_hint": "common|occasional|rare"
    }}
  ]
}}

Include ALL schema fields. Use null when no evidence exists.
For suggested_fields: 0-5 biomedically interesting observations that don't fit existing fields."""


def build_gap_system_prompt(field_descriptions: dict[str, str], null_fields: list[str]) -> str:
    """Focused prompt for --focus-gaps mode: only asks about fields regex missed."""
    gap_descs = {f: d for f, d in field_descriptions.items() if f in null_fields}
    fields_block = "\n".join(
        f"  - {field}: {desc}" for field, desc in sorted(gap_descs.items())
    )
    return f"""You are a biomedical data extraction assistant for the PatientPunk research project.
Regex extraction already ran on this text. You are filling in ONLY the fields it missed.

EXTRACTION RULES:
1. Only extract information EXPLICITLY stated in the text. Never infer or guess.
2. If a field cannot be determined, set it to null.
3. For treatment_outcome, ALWAYS pair treatment with outcome (e.g., "LDN: helped brain fog").
4. Only extract what the AUTHOR says about THEMSELVES.
5. Respect NEGATION: "I don't have POTS" → POTS not in conditions.
6. Respect TEMPORAL context: past symptoms/treatments should be noted as such.

FIELDS TO EXTRACT (regex found nothing for these):
{fields_block}

RESPONSE FORMAT — valid JSON only:
{{
  "fields": {{
    "field_name": ["value1", "value2"] or null
  }},
  "suggested_fields": [
    {{
      "field_name": "proposed_field_name_in_snake_case",
      "description": "What this captures and why it's scientifically useful",
      "values": ["value from this text"],
      "frequency_hint": "common|occasional|rare"
    }}
  ]
}}

Only include the fields listed above. Use null when no evidence exists."""


def build_user_message(texts: list[str]) -> str:
    combined = "\n\n---\n\n".join(t for t in texts if t)
    if len(combined) > MAX_TEXT_CHARS:
        combined = combined[:MAX_TEXT_CHARS] + "\n\n[TRUNCATED]"
    return f"Extract biomedical information from this patient-authored text:\n\n{combined}"


# =============================================================================
# TEXT COLLECTION — health subreddits prioritised
# =============================================================================

def collect_texts_from_user(user_data: dict) -> list[str]:
    """Collect texts, health-subreddit posts first so truncation keeps the best content."""
    health_texts = []
    other_texts = []

    for post in user_data.get("posts", []):
        sub = post.get("subreddit", "").lower()
        bucket = health_texts if sub in HEALTH_SUBREDDITS else other_texts
        if post.get("title"):
            bucket.append(post["title"])
        if post.get("body"):
            bucket.append(post["body"])

    for comment in user_data.get("comments", []):
        sub = comment.get("subreddit", "").lower()
        bucket = health_texts if sub in HEALTH_SUBREDDITS else other_texts
        if comment.get("body"):
            bucket.append(comment["body"])

    return health_texts + other_texts


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


# =============================================================================
# RECORD BUILDING
# =============================================================================

def build_llm_record(
    llm_output: dict,
    source: str,
    author_hash: str,
    text_count: int,
    schema: dict | None,
    post_id: str | None = None,
) -> dict:
    schema_id = schema["schema_id"] if schema else "base"
    fields = llm_output.get("fields", {})

    for key in fields:
        val = fields[key]
        if val is None:
            continue
        if isinstance(val, str):
            fields[key] = [val]
        elif isinstance(val, list):
            fields[key] = [v for v in val if v] or None

    return {
        "_patientpunk_version": "2.0",
        "_extraction_method": "llm",
        "_model": MODEL,
        "_schema_id": schema_id,
        "_extracted_at": datetime.now(timezone.utc).isoformat(),
        "record_meta": {
            "author_hash": author_hash,
            "source": source,
            "text_count": text_count,
            "post_id": post_id,
        },
        "fields": fields,
        "suggested_fields": llm_output.get("suggested_fields", []),
    }


# =============================================================================
# SKIP / FOCUS-GAPS HELPERS
# =============================================================================

def build_regex_index(regex_file: Path) -> dict:
    """Index regex records by (author_hash, post_id) for skip/focus-gap lookups."""
    if not regex_file.exists():
        return {}
    with open(regex_file, encoding="utf-8") as f:
        records = json.load(f)
    index = {}
    for rec in records:
        meta = rec.get("record_meta", {})
        key = (meta.get("author_hash"), meta.get("post_id"))
        index[key] = rec
    return index


def regex_coverage(regex_rec: dict, field_names: list[str]) -> tuple[float, list[str]]:
    """Return (coverage_fraction, list_of_null_fields) for a regex record."""
    base = regex_rec.get("base", {})
    ext = regex_rec.get("extension", {}) or {}
    null_fields = []
    for f in field_names:
        entry = base.get(f) or ext.get(f)
        has_value = bool(entry and isinstance(entry, dict) and entry.get("values"))
        if not has_value:
            null_fields.append(f)
    coverage = 1.0 - (len(null_fields) / len(field_names)) if field_names else 1.0
    return coverage, null_fields


# =============================================================================
# CONCURRENT CORPUS PROCESSING
# =============================================================================

def _process_one(
    item_type: str,
    item,
    client: anthropic.Anthropic,
    system_prompt: str,
    gap_system_prompt_fn,   # callable(null_fields) -> str, or None
    schema: dict | None,
    regex_index: dict,
    field_names: list[str],
    skip_threshold: float,
    focus_gaps: bool,
) -> dict | None:
    """Process a single work item. Runs inside a thread."""
    if item_type == "user":
        with open(item, encoding="utf-8") as f:
            user_data = json.load(f)
        texts = collect_texts_from_user(user_data)
        author_hash = user_data.get("author_hash", "unknown")
        source = "user_history"
        post_id = None
    else:
        texts = collect_texts_from_post(item)
        author_hash = item.get("author_hash", "unknown")
        source = "subreddit_post"
        post_id = item.get("post_id")

    if not texts or all(not t.strip() for t in texts):
        return {"_skipped": True, "reason": "no_text", "author_hash": author_hash, "post_id": post_id}

    # Check regex coverage for skip / focus-gap logic
    regex_rec = regex_index.get((author_hash, post_id))
    null_fields = field_names[:]  # default: all fields are null

    if regex_rec and field_names:
        coverage, null_fields = regex_coverage(regex_rec, field_names)
        if skip_threshold > 0 and coverage >= skip_threshold:
            return {"_skipped": True, "reason": "regex_covered", "author_hash": author_hash, "post_id": post_id}

    # Choose prompt
    if focus_gaps and null_fields and len(null_fields) < len(field_names):
        prompt = gap_system_prompt_fn(null_fields)
    else:
        prompt = system_prompt

    user_message = build_user_message(texts)
    raw = call_haiku(client, prompt, user_message)
    parsed = parse_json_response(raw)

    if parsed is None:
        return {"_failed": True, "author_hash": author_hash, "post_id": post_id}

    record = build_llm_record(
        llm_output=parsed,
        source=source,
        author_hash=author_hash,
        text_count=len(texts),
        schema=schema,
        post_id=post_id,
    )
    return record


def process_corpus(
    client: anthropic.Anthropic,
    input_dir: Path,
    field_descriptions: dict[str, str],
    schema: dict | None,
    limit: int | None = None,
    workers: int = 8,
    skip_threshold: float = 0.0,
    focus_gaps: bool = False,
    regex_index: dict | None = None,
    resume: bool = False,
    temp_dir: Path | None = None,
) -> tuple[list[dict], list[dict]]:
    """Process the corpus concurrently through Haiku."""
    system_prompt = build_system_prompt(field_descriptions)
    field_names = list(field_descriptions.keys())

    def gap_system_prompt_fn(null_fields):
        return build_gap_system_prompt(field_descriptions, null_fields)

    users_dir = input_dir / "users"
    posts_file = input_dir / "subreddit_posts.json"
    schema_id = schema["schema_id"] if schema else "base"
    _temp = temp_dir if temp_dir else input_dir
    records_file = _temp / f"llm_records_{schema_id}.json"

    # Resume: load existing records and build a set of already-done keys
    records = []
    all_suggestions = []
    done_keys: set[tuple] = set()

    if resume and records_file.exists():
        with open(records_file, encoding="utf-8") as f:
            records = json.load(f)
        for rec in records:
            meta = rec.get("record_meta", {})
            done_keys.add((meta.get("author_hash"), meta.get("post_id")))
            for suggestion in rec.get("suggested_fields", []):
                all_suggestions.append(suggestion)
        print(f"  Resuming — {len(records)} records already done, {len(done_keys)} keys loaded.\n")

    work_items = []
    if users_dir.exists():
        for user_file in sorted(users_dir.glob("*.json")):
            work_items.append(("user", user_file))
    if posts_file.exists():
        with open(posts_file, encoding="utf-8") as f:
            posts = json.load(f)
        for post in posts:
            work_items.append(("post", post))
    if limit:
        work_items = work_items[:limit]

    # Filter out already-completed items when resuming
    if done_keys:
        def item_key(item_type, item):
            if item_type == "user":
                # Need to peek at the file to get the hash
                try:
                    with open(item, encoding="utf-8") as f:
                        d = json.load(f)
                    return (d.get("author_hash"), None)
                except Exception:
                    return (None, None)
            else:
                return (item.get("author_hash"), item.get("post_id"))

        remaining = []
        for item_type, item in work_items:
            if item_key(item_type, item) not in done_keys:
                remaining.append((item_type, item))
        skipped_resume = len(work_items) - len(remaining)
        work_items = remaining
        if skipped_resume:
            print(f"  Skipping {skipped_resume} already-completed records.\n")

    total = len(work_items)
    already_done = len(records)
    print(f"Processing {total} remaining items with {workers} workers...\n")

    completed = 0
    skipped = 0
    failed = 0
    save_lock = threading.Lock()
    print_lock = threading.Lock()

    def save_incremental():
        with open(records_file, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_label = {}
        for item_type, item in work_items:
            if item_type == "user":
                label = f"user/{item.stem[:12]}"
            else:
                label = f"post/{item.get('post_id', '?')}"

            future = executor.submit(
                _process_one,
                item_type, item,
                client, system_prompt, gap_system_prompt_fn,
                schema, regex_index or {}, field_names,
                skip_threshold, focus_gaps,
            )
            future_to_label[future] = label

        for future in as_completed(future_to_label):
            label = future_to_label[future]
            completed += 1

            try:
                result = future.result()
            except Exception as exc:
                with print_lock:
                    print(f"  [{completed}/{total}] {label} — ERROR: {exc}")
                failed += 1
                continue

            if result is None or result.get("_failed"):
                with print_lock:
                    print(f"  [{completed}/{total}] {label} — PARSE FAILED")
                failed += 1
                continue

            if result.get("_skipped"):
                reason = result.get("reason", "?")
                skipped += 1
                with print_lock:
                    print(f"  [{completed}/{total}] {label} — skipped ({reason})")
                continue

            with save_lock:
                records.append(result)
                for suggestion in result.get("suggested_fields", []):
                    suggestion["_from_record"] = (result["record_meta"].get("author_hash") or "unknown")[:12]
                    all_suggestions.append(suggestion)

                n_fields = sum(1 for v in result.get("fields", {}).values() if v is not None)
                n_suggestions = len(result.get("suggested_fields", []))

                with print_lock:
                    print(f"  [{completed}/{total}] {label} — {n_fields} fields, {n_suggestions} suggestions")

                if len(records) % SAVE_EVERY_N == 0:
                    save_incremental()

    # Final save
    save_incremental()

    print(f"\n  Total: {already_done} resumed + {completed} new, {skipped} skipped, {failed} failed")
    return records, all_suggestions


# =============================================================================
# MERGE
# =============================================================================

def merge_records(regex_records: list[dict], llm_records: list[dict]) -> list[dict]:
    """Merge regex and LLM records by (author_hash, post_id)."""
    llm_index = {}
    for rec in llm_records:
        meta = rec.get("record_meta", {})
        key = (meta.get("author_hash"), meta.get("post_id"))
        llm_index[key] = rec

    merged = []
    for regex_rec in regex_records:
        meta = regex_rec.get("record_meta", {})
        key = (meta.get("author_hash"), meta.get("post_id"))
        llm_rec = llm_index.pop(key, None)

        merged_record = {
            "_patientpunk_version": "2.0",
            "_extraction_method": "merged",
            "_schema_id": regex_rec.get("_schema_id", "base"),
            "_extracted_at": datetime.now(timezone.utc).isoformat(),
            "record_meta": meta,
            "fields": {},
        }

        regex_base = regex_rec.get("base", {})
        regex_ext = regex_rec.get("extension", {}) or {}
        llm_fields = llm_rec.get("fields", {}) if llm_rec else {}

        all_field_names = set(regex_base.keys()) | set(regex_ext.keys()) | set(llm_fields.keys())

        for field in sorted(all_field_names):
            regex_entry = regex_base.get(field) or regex_ext.get(field)
            regex_values = None
            if regex_entry and isinstance(regex_entry, dict):
                regex_values = regex_entry.get("values")
            elif regex_entry and isinstance(regex_entry, list):
                regex_values = regex_entry

            llm_values = llm_fields.get(field)

            if regex_values and llm_values:
                combined = list(regex_values)
                for v in llm_values:
                    v_lower = v.lower().strip() if isinstance(v, str) else v
                    if not any(
                        (e.lower().strip() if isinstance(e, str) else e) == v_lower
                        for e in combined
                    ):
                        combined.append(v)
                merged_record["fields"][field] = {
                    "values": combined,
                    "regex_values": regex_values,
                    "llm_values": llm_values,
                    "provenance": "both",
                    "confidence": "high",
                }
            elif regex_values:
                merged_record["fields"][field] = {
                    "values": regex_values,
                    "regex_values": regex_values,
                    "llm_values": None,
                    "provenance": "regex_only",
                    "confidence": regex_entry.get("confidence") if isinstance(regex_entry, dict) else "medium",
                }
            elif llm_values:
                merged_record["fields"][field] = {
                    "values": llm_values,
                    "regex_values": None,
                    "llm_values": llm_values,
                    "provenance": "llm_only",
                    "confidence": "medium",
                }
            else:
                merged_record["fields"][field] = {
                    "values": None,
                    "provenance": None,
                    "confidence": None,
                }

        if llm_rec and llm_rec.get("suggested_fields"):
            merged_record["suggested_fields"] = llm_rec["suggested_fields"]

        merged.append(merged_record)

    # LLM-only records with no matching regex record
    for llm_rec in llm_index.values():
        llm_fields = llm_rec.get("fields", {})
        merged_record = {
            "_patientpunk_version": "2.0",
            "_extraction_method": "llm_only",
            "_schema_id": llm_rec.get("_schema_id", "base"),
            "_extracted_at": datetime.now(timezone.utc).isoformat(),
            "record_meta": llm_rec.get("record_meta", {}),
            "fields": {},
        }
        for field in sorted(llm_fields.keys()):
            llm_values = llm_fields[field]
            merged_record["fields"][field] = {
                "values": llm_values,
                "regex_values": None,
                "llm_values": llm_values,
                "provenance": "llm_only" if llm_values else None,
                "confidence": "medium" if llm_values else None,
            }
        if llm_rec.get("suggested_fields"):
            merged_record["suggested_fields"] = llm_rec["suggested_fields"]
        merged.append(merged_record)

    return merged


def aggregate_suggestions(all_suggestions: list[dict]) -> list[dict]:
    by_name = defaultdict(lambda: {"count": 0, "descriptions": set(), "example_values": [], "frequency_hints": []})
    for s in all_suggestions:
        name = s.get("field_name", "").strip().lower().replace(" ", "_")
        if not name:
            continue
        entry = by_name[name]
        entry["count"] += 1
        if s.get("description"):
            entry["descriptions"].add(s["description"])
        for v in (s.get("values") or []):
            if v and v not in entry["example_values"][:10]:
                entry["example_values"].append(v)
        if s.get("frequency_hint"):
            entry["frequency_hints"].append(s["frequency_hint"])
    return [
        {
            "field_name": name,
            "times_suggested": data["count"],
            "descriptions": sorted(data["descriptions"]),
            "example_values": data["example_values"][:10],
            "frequency_hints": data["frequency_hints"][:5],
        }
        for name, data in sorted(by_name.items(), key=lambda x: -x[1]["count"])
    ]


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="LLM-based biomedical extraction for PatientPunk (Claude Haiku).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Defaults: 10 workers, skip-threshold 0.7, focus-gaps on, merge on.

Examples:
  python llm_extract.py                              # run with all defaults
  python llm_extract.py --schema schemas/covidlonghaulers_schema.json
  python llm_extract.py --limit 5                    # test on 5 records first
  python llm_extract.py --text "34F with POTS, LDN helped"
  python llm_extract.py --no-merge                   # skip the merge step
  python llm_extract.py --skip-threshold 0.0         # process every record
  python llm_extract.py --no-focus-gaps              # send full prompt every time
  python llm_extract.py --resume                     # continue a crashed/interrupted run
        """,
    )
    parser.add_argument(
        "--input-dir", type=Path,
        default=Path(__file__).parent.parent / "output",
        help="Path to the output/ directory from scrape_corpus.py",
    )
    parser.add_argument(
        "--text", type=str, default=None,
        help="Test mode: extract from a single string and print results.",
    )
    parser.add_argument(
        "--schema", type=Path, default=None,
        help="Path to a JSON extension schema file.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Process at most N records (cost control / testing).",
    )
    parser.add_argument(
        "--no-merge", action="store_true",
        help="Disable merging with regex results (merge is on by default).",
    )
    parser.add_argument(
        "--workers", type=int, default=10,
        help="Number of concurrent API requests (default: 10).",
    )
    parser.add_argument(
        "--skip-threshold", type=float, default=0.7,
        help="Skip records where regex already found this fraction of fields "
             "(0.0-1.0, default: 0.7). Set to 0.0 to disable skipping.",
    )
    parser.add_argument(
        "--no-focus-gaps", action="store_true",
        help="Disable focused-gap mode and send the full prompt for every record.",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume a previous run — skip records already in llm_records_{schema_id}.json.",
    )
    parser.add_argument(
        "--temp-dir", type=Path, default=None,
        help="Directory for intermediate output files (default: {input-dir}/temp/).",
    )
    args = parser.parse_args()

    # Load schema
    schema = None
    if args.schema:
        if not args.schema.exists():
            sys.exit(f"Schema file not found: {args.schema}")
        with open(args.schema, encoding="utf-8") as f:
            schema = json.load(f)
        if "schema_id" not in schema:
            sys.exit(f"Schema missing 'schema_id': {args.schema}")

    field_descriptions = build_field_descriptions(schema)
    schema_id = schema["schema_id"] if schema else "base"

    # Test mode
    if args.text:
        client = get_client()
        system_prompt = build_system_prompt(field_descriptions)
        user_message = build_user_message([args.text])
        print(f"Sending to {MODEL}...\n")
        raw = call_haiku(client, system_prompt, user_message)
        parsed = parse_json_response(raw)
        if parsed:
            print("=== Extracted fields ===")
            for field in sorted(parsed.get("fields", {})):
                val = parsed["fields"][field]
                if val is not None:
                    print(f"  {field}: {val}")
            suggestions = parsed.get("suggested_fields", [])
            if suggestions:
                print(f"\n=== Suggested new fields ({len(suggestions)}) ===")
                for s in suggestions:
                    print(f"  {s.get('field_name')}: {s.get('values')} — {s.get('description')}")
        else:
            print("Failed to parse LLM response.\nRaw response:")
            print(raw)
        return

    # Full corpus mode
    output_dir = args.input_dir
    if not output_dir.exists():
        sys.exit(f"Error: {output_dir} does not exist. Run scrape_corpus.py first.")

    temp_dir = args.temp_dir if args.temp_dir else output_dir / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Resolve flag inversions
    do_merge = not args.no_merge
    focus_gaps = not args.no_focus_gaps

    # Build regex index for skip/focus-gaps (reads extract_biomedical output from temp/)
    regex_index = None
    if args.skip_threshold > 0 or focus_gaps:
        regex_file = temp_dir / f"patientpunk_records_{schema_id}.json"
        regex_index = build_regex_index(regex_file)
        if not regex_index:
            print(f"Warning: skip-threshold/focus-gaps active but no regex file found "
                  f"({regex_file.name}). Run extract_biomedical.py first for best results.")

    client = get_client()

    print("=" * 60)
    print(f"  PatientPunk LLM Extraction")
    print(f"  Model           : {MODEL}")
    print(f"  Schema          : {schema_id}")
    print(f"  Fields          : {len(field_descriptions)}")
    print(f"  Workers         : {args.workers}")
    print(f"  Limit           : {args.limit or 'all'}")
    print(f"  Skip threshold  : {args.skip_threshold or 'off'}")
    print(f"  Focus gaps      : {'yes' if focus_gaps else 'no'}")
    print(f"  Merge           : {'yes' if do_merge else 'no'}")
    print(f"  Resume          : {'yes' if args.resume else 'no'}")
    print("=" * 60 + "\n")

    start_time = datetime.now(timezone.utc)

    records, all_suggestions = process_corpus(
        client=client,
        input_dir=output_dir,
        temp_dir=temp_dir,
        field_descriptions=field_descriptions,
        schema=schema,
        limit=args.limit,
        workers=args.workers,
        skip_threshold=args.skip_threshold,
        focus_gaps=focus_gaps,
        regex_index=regex_index,
        resume=args.resume,
    )

    duration = (datetime.now(timezone.utc) - start_time).total_seconds()

    # Write LLM records to temp/ (already saved incrementally, this is the final flush)
    records_file = temp_dir / f"llm_records_{schema_id}.json"
    with open(records_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    # Aggregate suggestions
    ranked_suggestions = aggregate_suggestions(all_suggestions)
    suggestions_file = temp_dir / f"llm_field_suggestions_{schema_id}.json"
    with open(suggestions_file, "w", encoding="utf-8") as f:
        json.dump(ranked_suggestions, f, ensure_ascii=False, indent=2)

    # Merge
    if do_merge:
        regex_file = temp_dir / f"patientpunk_records_{schema_id}.json"
        if regex_file.exists():
            print(f"\nMerging with {regex_file.name}...")
            with open(regex_file, encoding="utf-8") as f:
                regex_records = json.load(f)
            merged = merge_records(regex_records, records)
            merged_file = temp_dir / f"merged_records_{schema_id}.json"
            with open(merged_file, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
            print(f"  Merged {len(merged)} records → {merged_file}")
        else:
            print(f"\nWarning: Cannot merge — {regex_file.name} not found.")
            print(f"  Run extract_biomedical.py first.")

    # Summary
    fields_found = defaultdict(int)
    for rec in records:
        for field, val in rec.get("fields", {}).items():
            if val is not None:
                fields_found[field] += 1

    print(f"\n{'=' * 60}")
    print(f"  Done! ({duration:.0f}s, {len(records)} records)")
    print(f"  LLM records       : {records_file}")
    print(f"  Field suggestions : {suggestions_file}")
    print(f"\n  Field hit counts (LLM):")
    for field, count in sorted(fields_found.items(), key=lambda x: -x[1]):
        print(f"    {field:<30} {count}")
    if ranked_suggestions:
        print(f"\n  Top suggested new fields:")
        for s in ranked_suggestions[:10]:
            desc = s['descriptions'][0][:60] if s['descriptions'] else '?'
            print(f"    {s['field_name']:<30} ({s['times_suggested']}x) — {desc}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
