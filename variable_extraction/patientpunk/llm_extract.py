#!/usr/bin/env python3
"""


Second-pass extraction using Claude Haiku. Reads the same corpus as
``patientpunk.biomedical`` and produces structured records for the same schema
fields.

Designed to run AFTER regex extraction. The merge step combines both passes:
regex hits are high-confidence and LLM hits fill the gaps.

Usage:
    python llm_extract.py                              # base fields, default input
    python llm_extract.py --schema schemas/covidlonghaulers_schema.json
    python llm_extract.py --text "I'm a 34F with POTS, LDN helped my brain fog"
    python llm_extract.py --merge                      # combine with regex results
    python llm_extract.py --limit 10                   # first 10 records only
    python llm_extract.py --workers 20                 # more concurrency (default: 10)
    python llm_extract.py --skip-threshold 0.7         # skip records regex covered 70%+
    python llm_extract.py --focus-gaps                 # only ask LLM about null fields

Speed tips:
    --workers 8 (default) runs 8 requests in parallel - biggest single speedup.
    --skip-threshold 0.7 skips records where regex already found 70%+ of fields.
    --focus-gaps sends a shorter prompt asking only about the fields regex missed.
    Combine all three for maximum speed: --workers 10 --skip-threshold 0.7 --focus-gaps

Requires:
    pip install anthropic python-dotenv

    Copy .env.example to .env and add your Anthropic API key.

Output:
    output/llm_records_{schema_id}.json     # LLM extraction records
    output/merged_records_{schema_id}.json  # Combined regex + LLM (--merge)
"""


import argparse
import json
import os
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

try:
    import anthropic
except ImportError:
    raise ImportError("anthropic is required: pip install anthropic") from None

from .qualitative_standards import EXTRACTION_STANDARDS
from .phase import PhaseResult


# =============================================================================
# CONSTANTS
# =============================================================================

# Model name resolved from _utils (OpenRouter or Anthropic direct)
from ._utils import (
    LLM_PROVIDER,
    LLM_SERVICE_TIER,
    LLMResponseError,
    check_response,
    LLM_TEMPERATURE,
    MODEL_FAST,
    collect_texts_from_post,
    get_llm_client,
    parse_json_response,
    response_text,
    split_retry_batch,
)
from .llm_cache import cached_completion
from .llm_schema import LLMExtraction, parse_extraction
MODEL = MODEL_FAST

# Field names the model invented that aren't in the schema. Dropped from the
# record, but counted here so they surface in the run summary instead of
# vanishing -- a hallucinated name is a prompt/schema signal worth seeing.
_dropped_fields: Counter = Counter()
_dropped_lock = threading.Lock()


def _write_json_atomic(path: Path, data) -> None:
    """Write JSON via ``.tmp`` then ``replace`` so an interrupt can't truncate the file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _record_dropped_fields(names: list[str]) -> None:
    with _dropped_lock:
        _dropped_fields.update(names)
# 4096 truncated the JSON response on long user histories (verbose fields),
# causing PARSE FAILED and silently dropping ~half of the most prolific posters.
# Haiku's hard output ceiling is 8192; use it.
# Override via LLM_MAX_TOKENS for local models (e.g. 1024) so generation
# cannot burn the full budget when the model fails to stop early.
MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "8192") or "8192")
# A maxed input must leave room for its response inside MAX_TOKENS. At 30_000 a
# single record's reply overran 8192 output tokens and got truncated mid-JSON.
# The discovery script learned the same lesson and uses 10_000; 8_000 keeps a
# comfortable margin.
MAX_TEXT_CHARS = 8_000
RETRY_DELAYS = [2, 5, 15, 30]
SAVE_EVERY_N = 10   # flush incremental save every N completed records
# The multi-record array path is unreliable: a record's text holds several
# posts and the model emits one object PER POST ("Expected 1, got N"),
# independent of delimiters -- plus a batch shares one MAX_TOKENS budget. So
# default to 1 record/call: the single-object path in _call_batch_raw is
# count-mismatch-proof and proven on the full corpus. (>1 still works as a
# best-effort batch; split_retry_batch falls back to single calls on failure.)
BATCH_SIZE = 1      # records per LLM call

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
    "conditions": "Medical diagnoses and conditions the patient has",
    "onset_trigger": "What triggered or preceded illness onset (infection, vaccine, surgery, etc.)",
    "symptom_duration": "How long symptoms have lasted",
    "symptom_trajectory": "Whether symptoms are improving, worsening, stable, or relapsing-remitting",
    "age_at_onset": "Patient's age when illness began",
    "medications": "Current or past medications mentioned",
    "treatment_outcome": "Response to specific treatments as 'drug: outcome: symptom' - the treatment, its outcome label, and the symptom it affected (e.g., 'LDN: helped: brain fog', 'metoprolol: worsened: fatigue'). Symptom is optional when not stated.",
    "procedures": "Medical procedures undergone (tilt table test, colonoscopy, MRI, etc.)",
    # activity_level removed -- redundant with functional_status_tier (extension field).
    "work_disability_status": "Work situation (working full-time, part-time, on disability, had to quit, etc.)",
    "mental_health": "Mental health conditions or impacts mentioned",
    "prior_infections": "Prior infections relevant to current illness (EBV, COVID, Lyme, etc.)",
}

BASE_OPTIONAL_DESCRIPTIONS = {
    "occupation": "Patient's occupation or job type",
    "bmi_weight": "BMI or weight mentions",
    "alternative_treatments": "Alternative/complementary treatments (acupuncture, supplements, etc.)",
    "genetic_testing": "Genetic testing mentions (23andMe, MTHFR, HLA typing, etc.)",
    "social_impact": "Social impacts of illness (relationships, isolation, etc.)",
    "trauma_history": "Trauma or adverse childhood experiences",
    "toxic_exposures": "Environmental toxic exposures (mold, chemicals, etc.)",
}



def call_haiku(client: anthropic.Anthropic, system_prompt: str, user_message: str,
               temperature: float | None = None) -> str:
    """Call Haiku with retry/backoff and prompt caching.

    Thread-safe - Anthropic client is thread-safe.
    The system prompt is marked for caching: after the first request Anthropic
    serves it from cache at 1/10th the token cost with lower latency.

    ``temperature`` overrides the default (used to re-ask at a higher temp when a
    temp-0 reply was deterministically malformed JSON).
    """
    temp = LLM_TEMPERATURE if temperature is None else temperature
    system = [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    def _call() -> str:
        for attempt, delay in enumerate([0] + RETRY_DELAYS):
            if delay:
                time.sleep(delay)
            try:
                # Other dialects 400 on service_tier, aborting the run.
                tier = {"service_tier": LLM_SERVICE_TIER} if (
                    LLM_SERVICE_TIER and LLM_PROVIDER == "openai") else {}
                response = client.messages.create(
                    model=MODEL,
                    temperature=temp,
                    max_tokens=MAX_TOKENS,
                    system=system,
                    messages=[{"role": "user", "content": user_message}],
                    **tier,
                )
                return response_text(check_response(response, MODEL))
            except Exception as e:
                # Provider-agnostic retry: works whether the error is raised by the
                # Anthropic SDK or by the OpenAI adapter (OpenRouter / vLLM path).
                # Retry on rate limits (429) and transient 5xx / connection errors;
                # on a non-transient error or the last attempt, re-raise so
                # split_retry_batch can fall back to a smaller batch.
                status = getattr(e, "status_code", None)
                if status is None:
                    status = getattr(getattr(e, "response", None), "status_code", None)
                name = type(e).__name__
                transient = (
                    status == 429
                    or (status is not None and 500 <= status < 600)
                    or "Connection" in name
                    or "Timeout" in name
                )
                if not transient or attempt == len(RETRY_DELAYS):
                    raise
        return ""

    return cached_completion(
        provider=LLM_PROVIDER,
        model=MODEL,
        system=system_prompt,
        prompt=user_message,
        temperature=temp,
        max_tokens=MAX_TOKENS,
        call_fn=_call,
    )


# parse_json_response lives in _utils (shared with demographics / discover)


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


# Optional rule (off by default; enable with --group-guard / PP_GROUP_GUARD=1).
# Stops the model from copying a collective outcome ("this stack helped") onto
# every named treatment -- a *confirmed, measured* source of `helped` inflation
# from stack posts (3-arm week test: helped share 47% -> 43%; ~6% helped->unknown
# vs a 1% noise floor). Left opt-in to preserve default reproducibility; RECOMMENDED
# for any analysis that reports per-drug `helped` rates (see README). Appended to
# the treatment_outcome guidance when enabled.
GROUP_GUARD_RULE = (
    "- GROUPED treatments: when several treatments are named together but only a "
    "COLLECTIVE outcome is given (e.g. 'this stack helped', 'things are improving'), "
    "do NOT copy that outcome onto each item. Use 'unknown' for any treatment whose "
    "individual effect is not separately stated. Assign helped/no_effect/worsened ONLY "
    "to a treatment the text attributes that outcome to specifically."
)


def build_system_prompt(field_descriptions: dict[str, str], *,
                        group_guard: bool = False) -> str:
    fields_block = "\n".join(
        f"  - {field}: {desc}" for field, desc in sorted(field_descriptions.items())
    )
    guard_block = f"\n{GROUP_GUARD_RULE}" if group_guard else ""
    return f"""You are a biomedical data extraction assistant for the PatientPunk research project.
Your job is to read patient-authored text from Reddit and extract structured biomedical information.

{EXTRACTION_STANDARDS}

EXTRACTION RULES:
1. Only extract information that is EXPLICITLY stated in the text. Never infer or guess.
2. If a field cannot be determined from the text, set it to null.
3. Distinguish between what the AUTHOR says about THEMSELVES vs. what they say about OTHERS. Only extract self-reported information for the structured fields.
4. Pay attention to NEGATION: "I don't have POTS" means POTS should NOT be in conditions.
5. Pay attention to TEMPORAL context: "I had fatigue for 6 months but it resolved" - note the resolution.

VALUE FORMAT RULES:
- Each value MUST be 1-5 words. Never write sentences. Never include explanations or mechanisms.
- GOOD: "LDN", "bedbound", "3 years", "isolation", "Paxlovid"
- BAD: "Seed DS-01 probiotic (B. longum, B. infantis, B. adolescentis...)" -- just write "Seed DS-01"
- BAD: "self-employed, lost clients, business continues but impaired" -- just write "lost clients"

FIELD-SPECIFIC RULES:
- conditions: ONLY diagnosed medical conditions (POTS, ME/CFS, MCAS, long COVID, dysautonomia, depression). Do NOT put symptoms here (brain fog, fatigue, pain, tinnitus, migraines, nausea, insomnia -- those are symptoms, not conditions).
- medications: Prescription drugs and daily supplements (LDN, Paxlovid, gabapentin, magnesium, probiotics).
- alternative_treatments: Non-pharmaceutical interventions only (pacing, acupuncture, HBOT, cold exposure, dietary changes). Do NOT duplicate medications or supplements here.
- treatment_outcome: Use the format "drug: outcome: symptom" where outcome is one of: helped, no_effect, worsened, mixed, unknown, and symptom is the specific symptom affected (1-3 words). Omit the symptom if not stated -> "drug: outcome". Examples: "LDN: helped: brain fog", "metoprolol: worsened: fatigue", "Paxlovid: no_effect". Never include dosage, mechanism, or timeline.{guard_block}
- functional_status_tier: Use ONLY one of: bedbound, housebound, severe, moderate, mild, mostly_functional. No sentences.
- social_impact: 1-3 word labels only. GOOD: "isolation", "relationship strain", "lost friends". BAD: "difficulty with daily activities like meal planning and preparation".

SCHEMA FIELDS to extract:
{fields_block}

RESPONSE FORMAT - valid JSON only:
{{
  "fields": {{
    "field_name": ["value1", "value2"] or null
  }}
}}

Include ALL schema fields. Use null when no evidence exists."""


def build_gap_system_prompt(field_descriptions: dict[str, str], null_fields: list[str], *,
                            group_guard: bool = False) -> str:
    """Focused prompt for --focus-gaps mode: only asks about fields regex missed."""
    gap_descs = {f: d for f, d in field_descriptions.items() if f in null_fields}
    fields_block = "\n".join(
        f"  - {field}: {desc}" for field, desc in sorted(gap_descs.items())
    )
    guard_block = f"\n{GROUP_GUARD_RULE}" if group_guard else ""
    return f"""You are a biomedical data extraction assistant for the PatientPunk research project.
Regex extraction already ran on this text. You are filling in ONLY the fields it missed.

{EXTRACTION_STANDARDS}

EXTRACTION RULES:
1. Only extract information EXPLICITLY stated in the text. Never infer or guess.
2. If a field cannot be determined, set it to null.
3. Only extract what the AUTHOR says about THEMSELVES.
4. Respect NEGATION: "I don't have POTS" means POTS not in conditions.
5. Respect TEMPORAL context: past symptoms/treatments should be noted as such.

VALUE FORMAT RULES:
- Each value MUST be 1-5 words. Never write sentences.
- conditions: ONLY diagnosed conditions (POTS, ME/CFS, long COVID). NOT symptoms (brain fog, fatigue, pain).
- treatment_outcome: "drug: outcome: symptom" where outcome is helped/no_effect/worsened/mixed/unknown and symptom is the affected symptom (omit if unstated). E.g. "LDN: helped: brain fog".{guard_block}
- functional_status_tier: ONLY one of: bedbound/housebound/severe/moderate/mild/mostly_functional.
- social_impact: 1-3 word labels only (e.g., "isolation", "relationship strain").
- alternative_treatments: Non-pharmaceutical only. Do NOT duplicate medications here.

FIELDS TO EXTRACT (regex found nothing for these):
{fields_block}

RESPONSE FORMAT - valid JSON only:
{{
  "fields": {{
    "field_name": ["value1", "value2"] or null
  }}
}}

Only include the fields listed above. Use null when no evidence exists."""


def build_user_message(texts: list[str]) -> str:
    combined = "\n\n---\n\n".join(t for t in texts if t)
    if len(combined) > MAX_TEXT_CHARS:
        combined = combined[:MAX_TEXT_CHARS] + "\n\n[TRUNCATED]"
    return f"Extract biomedical information from this patient-authored text:\n\n{combined}"


# =============================================================================
# TEXT COLLECTION - health subreddits prioritised
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


# =============================================================================
# RECORD BUILDING
# =============================================================================

def build_llm_record(
    llm_output: LLMExtraction,
    source: str,
    author_hash: str,
    text_count: int,
    schema: dict | None,
    post_id: str | None = None,
) -> dict:
    """Assemble a record from an already-validated extraction.

    Normalisation lives in llm_schema.parse_extraction, so ``llm_output.fields``
    is guaranteed ``dict[str, list[str] | None]`` by the time it gets here.
    """
    schema_id = schema["schema_id"] if schema else "base"

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
        "fields": dict(llm_output.fields),
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

    # Return prepared item for batching instead of calling LLM here
    return {
        "_ready": True,
        "user_message": user_message,
        "prompt": prompt,
        "source": source,
        "author_hash": author_hash,
        "post_id": post_id,
        "text_count": len(texts),
        "schema": schema,
    }


def _call_batch_raw(client, system_prompt: str, items: list[dict]) -> list[dict]:
    """Send record(s) in one API call. Returns a list of parsed dicts.

    Each item must have key 'user_message' with the per-record text.

    A single record (the default, and the split_retry_batch fallback) asks for
    ONE object and uses the tolerant parser -- no array/count ambiguity, no
    multi-post mis-splitting, and trailing prose is handled. Multiple records
    use the JSON-array path below.
    """
    if len(items) == 1:
        # Re-ask at escalating temperature: at temp 0 a malformed reply (e.g. a
        # stray doubled bracket) is deterministic, so a plain retry repeats it;
        # nudging temperature breaks the determinism and yields valid JSON.
        # LLMResponseError (empty/truncated) is absorbed the same way so hotter
        # temps still get a chance before split_retry_batch falls back.
        for temp in (None, 0.7, 1.0):
            try:
                parsed = parse_json_response(
                    call_haiku(
                        client, system_prompt, items[0]["user_message"],
                        temperature=temp,
                    )
                )
            except LLMResponseError:
                continue
            # Gate on shape, not just decodability: a reply that decodes but has
            # no 'fields' key would otherwise be recorded as a legitimately empty
            # extraction. Re-asking hotter is the same cure as for bad JSON.
            if parsed is not None and parse_extraction(parsed) is not None:
                return [parsed]
        raise ValueError("could not parse single-record response after retries")

    msg = (
        "Extract biomedical information from the following patient-authored records. "
        "Each record is by a DIFFERENT author.\n\n"
        "Return a JSON array with one result object per record, in the same order. "
        "Each object should have 'fields' as specified.\n\n"
    )
    for i, item in enumerate(items, 1):
        # Strip the instruction prefix from each user_message to avoid repeating it
        text = item["user_message"]
        if text.startswith("Extract biomedical"):
            text = text.split("\n\n", 1)[-1]
        # build_user_message joins a user's posts with '---', and Reddit markdown
        # uses '---' horizontal rules -- both collide with the '--- Record N ---'
        # delimiter and make the model split one multi-post record into several
        # objects (-> "Expected 1 results, got N"). Collapse bare rule lines.
        text = re.sub(r"(?m)^[ \t]*-{3,}[ \t]*$", "", text)
        msg += f"--- Record {i} ---\n{text}\n\n"

    raw = call_haiku(client, system_prompt, msg).strip()

    # Tolerant parse: strip ``` fences, then isolate the JSON array span so a
    # leading prose line or trailing content after the array ("Extra data")
    # doesn't break json.loads. A genuinely truncated reply still raises
    # JSONDecodeError, which split_retry_batch handles by splitting smaller.
    if raw.startswith("```"):
        nl = raw.find("\n")                 # find() not index(): a single-line
        if nl != -1:                        # fence (```json[...]```) has no newline
            raw = raw[nl + 1:]
        if raw.endswith("```"):
            raw = raw[:-3]
    start, end = raw.find("["), raw.rfind("]")
    if start != -1 and end > start:
        raw = raw[start:end + 1]

    results = json.loads(raw)
    if not isinstance(results, list):
        raise ValueError(f"Expected JSON array, got {type(results).__name__}")
    if len(results) != len(items):
        raise ValueError(f"Expected {len(items)} results, got {len(results)}")
    # Raise rather than record a malformed element as empty: split_retry_batch
    # halves the batch and the single-item path above re-asks at hotter temps.
    for i, result in enumerate(results):
        if parse_extraction(result) is None:
            raise ValueError(f"malformed result object at index {i} of batch response")
    return results


def _process_batch(
    batch_items: list[tuple],
    client: anthropic.Anthropic,
    system_prompt: str,
    gap_system_prompt_fn,
    schema: dict | None,
    regex_index: dict,
    field_names: list[str],
    skip_threshold: float,
    focus_gaps: bool,
) -> list[dict]:
    """Process a batch of work items. Pre-filters, then sends ready items
    to the LLM in a single multi-item call."""

    # Phase 1: prepare each item (text collection, skip checks)
    prepared = []
    for item_type, item in batch_items:
        result = _process_one(
            item_type, item, client, system_prompt, gap_system_prompt_fn,
            schema, regex_index, field_names, skip_threshold, focus_gaps,
        )
        prepared.append((item_type, item, result))

    # Phase 2: separate ready items from skipped/failed
    ready_indices = []
    ready_items = []
    output = [None] * len(batch_items)

    for i, (item_type, item, result) in enumerate(prepared):
        if result is not None and result.get("_ready"):
            ready_indices.append(i)
            ready_items.append(result)
        else:
            output[i] = result  # skipped or failed

    if not ready_items:
        return [o for o in output]

    # Phase 3: batch LLM call with split-retry
    # Group by prompt (most will share system_prompt, gap prompts differ)
    prompt_groups: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for idx, item in zip(ready_indices, ready_items):
        prompt_groups[item["prompt"]].append((idx, item))

    for prompt, group in prompt_groups.items():
        indices = [idx for idx, _ in group]
        items = [item for _, item in group]

        def call_fn(sub_items, _prompt=prompt):
            return _call_batch_raw(client, _prompt, sub_items)

        # split_retry_batch already absorbs parse failures (bad/short JSON) into
        # per-item None results, so anything that escapes it (auth errors, other
        # non-transient API errors) is fatal and must propagate, not be logged
        # per-record as a generic "PARSE FAILED" that hides the real cause.
        raw_results = split_retry_batch(call_fn, items)

        for idx, item, parsed in zip(indices, items, raw_results):
            def _failed(reason: str) -> dict:
                return {"_failed": True, "reason": reason,
                        "author_hash": item["author_hash"], "post_id": item["post_id"]}

            if parsed is None:
                output[idx] = _failed("no_response")
                continue

            allowed = set(build_field_descriptions(item["schema"]))
            validated = parse_extraction(parsed, allowed_fields=allowed)
            if validated is None:
                output[idx] = _failed("malformed_response")
                continue

            extraction, dropped = validated
            if dropped:
                _record_dropped_fields(dropped)

            # Containment: a single unexpected shape must never abort the run,
            # because split_retry_batch only absorbs parse failures and anything
            # raised here escapes it.
            try:
                output[idx] = build_llm_record(
                    llm_output=extraction,
                    source=item["source"],
                    author_hash=item["author_hash"],
                    text_count=item["text_count"],
                    schema=item["schema"],
                    post_id=item["post_id"],
                )
            except Exception as exc:
                output[idx] = _failed(f"build_error: {type(exc).__name__}")

    return output


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
    group_guard: bool = False,
) -> list[dict]:
    """Process the corpus concurrently through Haiku."""
    system_prompt = build_system_prompt(field_descriptions, group_guard=group_guard)
    field_names = list(field_descriptions.keys())

    def gap_system_prompt_fn(null_fields):
        return build_gap_system_prompt(field_descriptions, null_fields, group_guard=group_guard)

    users_dir = input_dir / "users"
    posts_file = input_dir / "subreddit_posts.json"
    schema_id = schema["schema_id"] if schema else "base"
    _temp = temp_dir if temp_dir else input_dir
    records_file = _temp / f"llm_records_{schema_id}.json"

    # Resume: load existing records and build a set of already-done keys
    records = []
    done_keys: set[tuple] = set()
    with _dropped_lock:
        _dropped_fields.clear()

    if resume and records_file.exists():
        with open(records_file, encoding="utf-8") as f:
            records = json.load(f)
        for rec in records:
            meta = rec.get("record_meta", {})
            done_keys.add((meta.get("author_hash"), meta.get("post_id")))
        print(f"  Resuming - {len(records)} records already done, {len(done_keys)} keys loaded.\n")

    work_items = []
    if users_dir.exists():
        for user_file in sorted(users_dir.glob("*.json")):
            work_items.append(("user", user_file))
    if posts_file.exists():
        with open(posts_file, encoding="utf-8") as f:
            posts = json.load(f)
        for post in posts:
            work_items.append(("post", post))
    # Before the resume filter, not after: --limit caps corpus position, so
    # resuming a capped run never spills past item N.
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

    # Chunk into batches
    batches = [work_items[i:i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    n_batches = len(batches)
    print(f"Processing {total} remaining items in {n_batches} batches "
          f"(batch size {BATCH_SIZE}) with {workers} workers...\n")

    completed = 0
    skipped = 0
    failed = 0
    save_lock = threading.Lock()
    print_lock = threading.Lock()

    def save_incremental():
        # Atomic: write .tmp then replace, so an interrupt can't truncate the
        # checkpoint and break --resume (same pattern as llm_cache.put).
        _write_json_atomic(records_file, records)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_batch_idx = {}
        for batch_idx, batch in enumerate(batches):
            future = executor.submit(
                _process_batch,
                batch,
                client, system_prompt, gap_system_prompt_fn,
                schema, regex_index or {}, field_names,
                skip_threshold, focus_gaps,
            )
            future_to_batch_idx[future] = batch_idx

        for future in as_completed(future_to_batch_idx):
            batch_idx = future_to_batch_idx[future]

            try:
                batch_results = future.result()
            except Exception as exc:
                # A batch only raises for fatal, non-per-record errors (auth
                # failures, non-transient API errors) -- cancel remaining work
                # and fail the whole run loudly instead of limping on with
                # partial/garbage results.
                for f in future_to_batch_idx:
                    f.cancel()
                save_incremental()
                raise RuntimeError(
                    f"LLM extraction aborted at batch {batch_idx+1}/{n_batches}: {exc}"
                ) from exc

            for result in batch_results:
                completed += 1

                if result is None or result.get("_failed"):
                    with print_lock:
                        pid = (result.get("post_id") or "?") if result else "?"
                        print(f"  [{completed}/{total}] {pid} - PARSE FAILED")
                    failed += 1
                    continue

                if result.get("_skipped"):
                    reason = result.get("reason", "?")
                    skipped += 1
                    continue

                with save_lock:
                    records.append(result)

                    n_fields = sum(1 for v in result.get("fields", {}).values() if v is not None)

                    with print_lock:
                        pid = result["record_meta"].get("post_id") or "?"
                        print(f"  [{completed}/{total}] {pid} - {n_fields} fields")

                    if len(records) % SAVE_EVERY_N == 0:
                        save_incremental()

    # Final save
    save_incremental()

    print(f"\n  Total: {already_done} resumed + {completed} new, {skipped} skipped, {failed} failed")
    with _dropped_lock:
        dropped = _dropped_fields.most_common()
    if dropped:
        total = sum(n for _, n in dropped)
        summary = ", ".join(f"{name} ({n}x)" for name, n in dropped[:5])
        print(f"  Dropped {total} value(s) for {len(dropped)} field name(s) not in the schema: {summary}")
    return records


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
        merged.append(merged_record)

    # Post-merge normalization: lowercase all values, canonicalize conditions
    for rec in merged:
        for field_name, field_data in rec.get("fields", {}).items():
            values = field_data.get("values")
            if not values:
                continue
            # Ensure values is a list (LLM sometimes returns bare int/str)
            if not isinstance(values, list):
                values = [values]
                field_data["values"] = values
            # Lowercase all string values
            normalized = [
                v.lower().strip() if isinstance(v, str) else v
                for v in values
            ]
            # Deduplicate after lowering
            seen: set[str] = set()
            deduped: list = []
            for v in normalized:
                key = v if isinstance(v, str) else repr(v)
                if key not in seen:
                    seen.add(key)
                    deduped.append(v)
            field_data["values"] = deduped

    # Multi-field canonicalization: map LLM vocabulary drift to controlled labels.
    # Each field has a dict of {variant: canonical_form}. Values not in the dict
    # are kept as-is (the LLM may discover legitimate new values).
    _CANONICAL_MAPS: dict[str, dict[str, str]] = {
        "conditions": {
            "long-covid": "long covid", "post-covid": "long covid",
            "post covid": "long covid", "pasc": "long covid",
            "myalgic encephalomyelitis": "me/cfs",
            "chronic fatigue syndrome": "me/cfs", "cfs": "me/cfs",
            "post-exertional malaise": "pem", "post-exertional": "pem",
            "post-viral": "post-viral", "post-infectious": "post-viral",
            "small fiber neuropathy": "small fiber neuropathy",
            "sfn": "small fiber neuropathy",
            "ehlers-danlos": "ehlers-danlos syndrome",
            "eds": "ehlers-danlos syndrome", "heds": "ehlers-danlos syndrome",
        },
        "functional_status_tier": {
            "bed bound": "bedbound", "bed-bound": "bedbound",
            "cannot get out of bed": "bedbound", "can't get out of bed": "bedbound",
            "mostly in bed": "bedbound",
            "house bound": "housebound", "house-bound": "housebound",
            "home bound": "housebound", "homebound": "housebound",
            "can't leave house": "housebound", "cannot leave house": "housebound",
            "very severe": "severe",
            "mostly functional": "mostly_functional",
            "mostly normal": "mostly_functional",
            "back to normal": "mostly_functional",
            "fully functional": "mostly_functional",
        },
        # treatment_outcome is handled separately below by a dedicated pass:
        # its values are structured "drug: outcome: symptom" triples, not
        # whole-string categories, so a flat map would never match the outcome
        # token (and we must preserve the drug + symptom around it).
        "social_impact": {
            "isolated": "isolation", "alone": "isolation",
            "lonely": "isolation", "loneliness": "isolation",
            "lost friends": "lost relationships",
            "lost relationships": "lost relationships",
            "relationship strain": "relationship strain",
            "relationship breakdown": "relationship strain",
        },
        "mental_health": {
            "depressed": "depression", "anxious": "anxiety",
            "therapist": "therapy", "counseling": "therapy",
            "psychologist": "therapy", "psychiatrist": "therapy",
        },
        "onset_trigger": {
            "after covid": "covid", "post covid": "covid",
            "covid infection": "covid", "covid-19": "covid",
            "covid-19 infection": "covid", "sars-cov-2": "covid",
            "re infection": "reinfection", "re-infection": "reinfection",
            "second infection": "reinfection", "third infection": "reinfection",
        },
        "doctor_dismissal": {
            "gaslit": "gaslighting", "gas lit": "gaslighting",
            "all in your head": "dismissed",
            "all in my head": "dismissed",
            "psychosomatic": "dismissed",
            "it's just anxiety": "dismissed",
            "no one believes me": "dismissed",
        },
        "work_disability_status": {
            "can't work": "unable to work", "cannot work": "unable to work",
            "unable to work": "unable to work",
            "had to quit": "unable to work",
            "on disability": "on disability", "ssdi": "on disability",
            "back to work": "working", "still working": "working",
            "work from home": "working reduced",
            "part time": "working reduced", "part-time": "working reduced",
            "reduced hours": "working reduced",
        },
        "symptom_trajectory": {
            "getting worse": "worsening", "worse": "worsening",
            "deteriorating": "worsening", "declining": "worsening",
            "getting better": "improving", "improved": "improving",
            "recovery": "improving",
            "back to normal": "recovered", "fully recovered": "recovered",
            "partially recovered": "improving",
            "relapse": "relapsing", "relapsing-remitting": "relapsing",
            "flare": "relapsing",
            "bedbound": "severe decline", "housebound": "severe decline",
        },
    }

    for rec in merged:
        for field_name, canon_map in _CANONICAL_MAPS.items():
            field_data = rec.get("fields", {}).get(field_name, {})
            values = field_data.get("values")
            if not values:
                continue
            canonical: list[str] = []
            seen: set[str] = set()
            for v in values:
                normalized = canon_map.get(v, v) if isinstance(v, str) else v
                key = normalized if isinstance(normalized, str) else repr(normalized)
                if key not in seen:
                    seen.add(key)
                    canonical.append(normalized)
            field_data["values"] = canonical

    # treatment_outcome: canonicalize ONLY the outcome token of each
    # "drug: outcome[: symptom]" triple, preserving the drug and the symptom
    # (re-added so drug x symptom heterogeneity stays analyzable downstream).
    #
    # The outcome synonym set deliberately EXCLUDES vague valence words
    # ("positive", "beneficial", "negative"): mapping those onto helped/worsened
    # imports the same positivity bias the DeepSeek sentiment pass already shows.
    # An unresolved outcome word falls back to "unknown" rather than being
    # guessed as helped -- we keep the drug-was-tried signal without asserting an
    # efficacy direction on weak evidence.
    _OUTCOME_SYNONYMS = {
        "worked": "helped", "improved": "helped", "fixed": "helped",
        "resolved": "helped", "cured": "helped", "effective": "helped",
        "didn't work": "no_effect", "no improvement": "no_effect",
        "didn't help": "no_effect", "ineffective": "no_effect",
        "no benefit": "no_effect", "no change": "no_effect",
        "made worse": "worsened", "side effects": "worsened",
        "adverse": "worsened",
    }
    _OUTCOME_LABELS = {"helped", "no_effect", "worsened", "mixed", "unknown"}

    for rec in merged:
        field_data = rec.get("fields", {}).get("treatment_outcome", {})
        values = field_data.get("values")
        if not values:
            continue
        canonical = []
        seen = set()
        for v in values:
            if not isinstance(v, str):
                continue
            parts = [p.strip() for p in v.split(":")]
            if len(parts) < 2 or not parts[0]:
                # Drop bare outcomes (no drug) here intentionally: with no drug
                # attribution they carry no drug-efficacy signal. Legacy bare
                # outcomes in older records.csv are handled separately by
                # normalize.decompose_treatment_outcome (-> treatment_outcome_label).
                continue
            drug, outcome = parts[0], parts[1]
            # Rejoin parts[2:] so a symptom containing ':' isn't truncated.
            symptom = ":".join(parts[2:]) if len(parts) > 2 else ""
            outcome = _OUTCOME_SYNONYMS.get(outcome, outcome)
            if outcome not in _OUTCOME_LABELS:
                outcome = "unknown"
            rejoined = f"{drug}: {outcome}" + (f": {symptom}" if symptom else "")
            if rejoined not in seen:
                seen.add(rejoined)
                canonical.append(rejoined)
        field_data["values"] = canonical

    return merged


# =============================================================================
# LIBRARY ENTRYPOINT
# =============================================================================

def run_llm_extract(
    *,
    input_dir: Path,
    schema_path: Path | None = None,
    temp_dir: Path | None = None,
    workers: int = 10,
    skip_threshold: float = 0.7,
    focus_gaps: bool = True,
    merge: bool = True,
    resume: bool = False,
    limit: int | None = None,
    group_guard: bool | None = None,
) -> PhaseResult:
    """Run Phase 2 LLM gap-filling over a corpus directory."""
    import os
    from typing import Any

    input_dir = Path(input_dir)
    if not input_dir.exists():
        raise FileNotFoundError(
            f"{input_dir} does not exist. Run scrape_corpus.py first."
        )

    schema = None
    if schema_path:
        schema_path = Path(schema_path)
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
        if "schema_id" not in schema:
            raise ValueError(f"Schema missing 'schema_id': {schema_path}")

    field_descriptions = build_field_descriptions(schema)
    schema_id = schema["schema_id"] if schema else "base"

    if group_guard is None:
        group_guard = os.environ.get("PP_GROUP_GUARD", "").strip().lower() in ("1", "true", "yes")

    out_temp = Path(temp_dir) if temp_dir else input_dir / "temp"
    out_temp.mkdir(parents=True, exist_ok=True)

    regex_index = None
    if skip_threshold > 0 or focus_gaps:
        regex_file = out_temp / f"patientpunk_records_{schema_id}.json"
        regex_index = build_regex_index(regex_file)
        if not regex_index:
            print(
                f"Warning: skip-threshold/focus-gaps active but no regex file found "
                f"({regex_file.name}). Run biomedical extraction first for best results."
            )

    client = get_llm_client()

    print("=" * 60)
    print(f"  PatientPunk LLM Extraction")
    print(f"  Model           : {MODEL}")
    print(f"  Schema          : {schema_id}")
    print(f"  Fields          : {len(field_descriptions)}")
    print(f"  Workers         : {workers}")
    print(f"  Limit           : {limit or 'all'}")
    print(f"  Skip threshold  : {skip_threshold or 'off'}")
    print(f"  Focus gaps      : {'yes' if focus_gaps else 'no'}")
    print(f"  Merge           : {'yes' if merge else 'no'}")
    print(f"  Resume          : {'yes' if resume else 'no'}")
    print(f"  Group guard     : {'on' if group_guard else 'off'}")
    print("=" * 60 + "\n")

    start_time = datetime.now(timezone.utc)

    records = process_corpus(
        client=client,
        input_dir=input_dir,
        temp_dir=out_temp,
        field_descriptions=field_descriptions,
        schema=schema,
        limit=limit,
        workers=workers,
        skip_threshold=skip_threshold,
        focus_gaps=focus_gaps,
        regex_index=regex_index,
        resume=resume,
        group_guard=group_guard,
    )

    duration = (datetime.now(timezone.utc) - start_time).total_seconds()

    records_file = out_temp / f"llm_records_{schema_id}.json"
    _write_json_atomic(records_file, records)

    artifacts = {
        "llm_records": records_file,
    }

    if merge:
        regex_file = out_temp / f"patientpunk_records_{schema_id}.json"
        if regex_file.exists():
            print(f"\nMerging with {regex_file.name}...")
            with open(regex_file, encoding="utf-8") as f:
                regex_records = json.load(f)
            merged = merge_records(regex_records, records)
            merged_file = out_temp / f"merged_records_{schema_id}.json"
            _write_json_atomic(merged_file, merged)
            print(f"  Merged {len(merged)} records -> {merged_file}")
            artifacts["merged_records"] = merged_file
        else:
            print(f"\nWarning: Cannot merge - {regex_file.name} not found.")
            print(f"  Run biomedical extraction first.")

    fields_found = defaultdict(int)
    for rec in records:
        for field, val in rec.get("fields", {}).items():
            if val is not None:
                fields_found[field] += 1

    print(f"\n{'=' * 60}")
    print(f"  Done! ({duration:.0f}s, {len(records)} records)")
    print(f"  LLM records       : {records_file}")
    print(f"\n  Field hit counts (LLM):")
    for field, count in sorted(fields_found.items(), key=lambda x: -x[1]):
        print(f"    {field:<30} {count}")
    print(f"{'=' * 60}")

    fills = sum(
        1 for rec in records
        for field_value in rec.get("fields", {}).values()
        if field_value is not None
    )
    stats: dict[str, Any] = {
        "LLM records": len(records),
        "LLM field fills": fills,
        "avg fills/record": round(fills / len(records), 2) if records else 0,
    }
    if "merged_records" in artifacts:
        stats["merged records"] = len(json.loads(artifacts["merged_records"].read_text(encoding="utf-8")))
    return PhaseResult(artifacts=artifacts, stats=stats)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="LLM-based biomedical extraction for PatientPunk (Claude Haiku).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input-dir", type=Path,
        default=Path(__file__).resolve().parent.parent / "output",
        help="Path to the output/ directory from scrape_corpus.py",
    )
    parser.add_argument("--text", type=str, default=None,
                        help="Test mode: extract from a single string and print results.")
    parser.add_argument("--schema", type=Path, default=None,
                        help="Path to a JSON extension schema file.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N records. Caps position, "
                             "so --resume never reaches N+1.")
    parser.add_argument("--no-merge", action="store_true",
                        help="Disable merging with regex results (merge is on by default).")
    parser.add_argument("--workers", type=int, default=10,
                        help="Number of concurrent API requests (default: 10).")
    parser.add_argument("--skip-threshold", type=float, default=0.7,
                        help="Skip records where regex already found this fraction of fields.")
    parser.add_argument("--no-focus-gaps", action="store_true",
                        help="Disable focused-gap mode.")
    parser.add_argument("--resume", action="store_true",
                        help="Resume a previous run.")
    parser.add_argument("--temp-dir", type=Path, default=None,
                        help="Directory for intermediate output files.")
    parser.add_argument("--group-guard", action="store_true",
                        help="Opt-in group-attribution guard.")
    args = parser.parse_args(argv)

    try:
        schema = None
        if args.schema:
            if not args.schema.exists():
                raise FileNotFoundError(f"Schema file not found: {args.schema}")
            with open(args.schema, encoding="utf-8") as f:
                schema = json.load(f)
            if "schema_id" not in schema:
                raise ValueError(f"Schema missing 'schema_id': {args.schema}")

        field_descriptions = build_field_descriptions(schema)
        group_guard = args.group_guard or os.environ.get(
            "PP_GROUP_GUARD", ""
        ).strip().lower() in ("1", "true", "yes")

        if args.text:
            client = get_llm_client()
            system_prompt = build_system_prompt(field_descriptions, group_guard=group_guard)
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
            else:
                print("Failed to parse LLM response.\nRaw response:")
                print(raw)
            return

        run_llm_extract(
            input_dir=args.input_dir,
            schema_path=args.schema,
            temp_dir=args.temp_dir,
            workers=args.workers,
            skip_threshold=args.skip_threshold,
            focus_gaps=not args.no_focus_gaps,
            merge=not args.no_merge,
            resume=args.resume,
            limit=args.limit,
            group_guard=group_guard,
        )
    except (FileNotFoundError, ValueError, OSError, ImportError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
