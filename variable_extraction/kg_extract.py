#!/usr/bin/env python3
"""
Claims-based knowledge-graph extraction prototype (issue #90).

Extracts patient CLAIMS (free-text primary + typed payload + verbatim source span)
into a SQLite tuple store, instead of forcing the LLM into ~40 fixed schema slots.
Then compares the result head-to-head against the existing flat extraction of the
SAME posts.

    python kg_extract.py run --limit 20      # smoke test
    python kg_extract.py run                 # full corpus (default 1000 posts)
    python kg_extract.py compare             # KG vs flat report

Design principle (from the issue):
    Extraction creates claims. Normalization creates meaning. Analytics creates knowledge.
Normalization is deliberately NOT implemented -- entity_links is created and left empty.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import statistics
import sys
import threading
import time
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from patientpunk._utils import (
    LLM_PROVIDER,
    LLM_TEMPERATURE,
    MODEL_FAST,
    check_response,
    collect_texts_from_post,
    get_llm_client,
    parse_json_response,
    response_text,
)
from patientpunk.llm_cache import cached_completion

_HERE = Path(__file__).parent
_ROOT = _HERE.parent
DEFAULT_CORPUS = _ROOT / "output_deepseek_1000" / "subreddit_posts.json"
DEFAULT_BASELINE = _ROOT / "output_deepseek_1000" / "records.csv"
DEFAULT_OUT_DIR = _ROOT / "output_kg"

MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "8192"))
RETRY_DELAYS = [2, 5, 15]

# The model sometimes writes one of these instead of omitting a key it can't evidence
# (rule 2 asks it not to). Normalize them to "" so the existing empty-value drop below
# still catches them, rather than relying on prompt compliance alone.
PLACEHOLDER_VALUES = {"not specified", "unknown", "none mentioned", "none", "n/a", "unspecified"}


# =============================================================================
# CLAIM CONTRACT
# =============================================================================

# claim_type -> (primary free-text key, structured keys)
CLAIM_TYPES: dict[str, tuple[str, tuple[str, ...]]] = {
    "attribute": ("attribute_text", (
        "age", "sex", "ethnicity", "location", "location_country", "location_us_state",
        "occupation", "functional_state", "family_history", "healthcare_system",
        "insurance_status", "vaccination_status", "clinical_trial_participation")),
    "diagnostic": ("condition_text", (
        "diagnosis_status", "provider_type", "test_used", "age_at_diagnosis", "misdiagnosis")),
    "symptom": ("symptom_text", (
        "severity", "duration", "trajectory", "triggers", "frequency")),
    "treatment_response": ("treatment_text", (
        "dose", "duration", "response", "benefits", "side_effects", "sentiment")),
    "insight": ("belief_text", ("hypothesis_type", "patient_expressed_confidence")),
}

RELATIONS = {"TREATS", "CO_OCCURS_WITH", "CAUSED_BY", "SUPPORTS", "CONTRADICTS"}


def build_system_prompt() -> str:
    blocks = []
    for ctype, (primary, extras) in CLAIM_TYPES.items():
        keys = ", ".join([f"{primary} (REQUIRED)", *extras])
        blocks.append(f'  "{ctype}": {{{keys}}}')
    types_doc = "\n".join(blocks)
    return f"""You extract structured CLAIMS from a patient's own account of their illness.

A claim is one atomic thing the author says about THEMSELVES, anchored to a verbatim
quote from the text. Emit as many claims as the text supports -- do not summarise, do
not merge two statements into one claim, do not invent.

CLAIM TYPES and their payload keys (omit any key you cannot evidence from the text):
{types_doc}

RULES
1. source_span MUST be copied VERBATIM from the post -- an exact substring, not a paraphrase.
2. The REQUIRED *_text key is free text taken from the author's own wording. Structured keys
   are extracted ALONGSIDE it, never instead of it. A claim with only the *_text key is fine
   and is better than a dropped claim. Never write a placeholder ("not specified", "unknown",
   "none mentioned") into a key you cannot evidence -- omit the key entirely instead.
3. FACTS vs BELIEFS. What happened to the author (diagnoses, symptoms, treatments and their
   outcomes) are facts -> attribute/diagnostic/symptom/treatment_response. What the author
   thinks, theorises, suspects, or hopes is a BELIEF -> "insight", never a fact-bearing claim.
   Example: "my POTS is caused by MCAS" is an insight, not a diagnostic claim.
4. Only claims about the AUTHOR. Skip anything about their spouse, child, friend, or a study
   population.
5. confidence: 0.0-1.0, how clearly the text supports the claim.
6. edges link two claims YOU emitted, by local_id: TREATS (treatment -> symptom/condition),
   CO_OCCURS_WITH, CAUSED_BY (cause -> effect), SUPPORTS, CONTRADICTS. Omit if none apply.
7. Demographic attribute keys (ethnicity, location_country, location_us_state,
   healthcare_system, insurance_status, vaccination_status, clinical_trial_participation)
   must come from an EXPLICIT statement, never inferred from spelling, idiom, or context.
   healthcare_system is the TYPE of system/payer only -- "NHS", "private insurance",
   "Medicare", "uninsured". It is NOT which clinic, provider, or care step the author used
   (a GP visit, an ER visit, a waitlist, a referral); those belong in the *_text field or
   provider_type on a diagnostic claim, never in healthcare_system.
   vaccination_status: e.g. "unvaccinated", "2 doses Pfizer".

Return ONLY JSON, no prose:
{{"claims": [{{"local_id": "c1", "claim_type": "symptom", "confidence": 0.9,
    "source_span": "exact quote", "payload": {{"symptom_text": "brain fog", "severity": "severe"}}}}],
 "edges": [{{"from": "c2", "to": "c1", "relation": "TREATS", "confidence": 0.6}}]}}

If the text contains nothing about the author's own health, return {{"claims": [], "edges": []}}."""


# =============================================================================
# TUPLE STORE
# =============================================================================

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id     INTEGER PRIMARY KEY,
    run_at     INTEGER NOT NULL,
    provider   TEXT, model TEXT, prompt_sha TEXT,
    config     TEXT NOT NULL,
    config_sha TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS claims (
    claim_id      TEXT PRIMARY KEY,
    run_id        INTEGER NOT NULL REFERENCES runs(run_id),
    patient_id    TEXT NOT NULL,
    post_id       TEXT,
    claim_type    TEXT NOT NULL,
    source_span   TEXT NOT NULL,
    confidence    REAL,
    payload       TEXT NOT NULL,      -- JSON
    span_grounded INTEGER NOT NULL    -- 1 = source_span is verbatim in the post
);
-- the tuple store: one row per (claim, predicate, value)
CREATE TABLE IF NOT EXISTS claim_facts (
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    run_id   INTEGER NOT NULL,
    key      TEXT NOT NULL,
    value    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claim_edges (
    edge_id    INTEGER PRIMARY KEY,
    run_id     INTEGER NOT NULL,
    from_claim TEXT NOT NULL REFERENCES claims(claim_id),
    to_claim   TEXT NOT NULL REFERENCES claims(claim_id),
    relation   TEXT NOT NULL,
    properties TEXT,
    confidence REAL
);
-- landing spot for the deferred normalization layer; this prototype never writes it
CREATE TABLE IF NOT EXISTS entity_links (
    claim_id      TEXT NOT NULL REFERENCES claims(claim_id),
    ontology      TEXT NOT NULL,
    code          TEXT NOT NULL,
    label         TEXT,
    linker_run_id INTEGER,
    confidence    REAL
);
CREATE TABLE IF NOT EXISTS post_status (
    post_id  TEXT NOT NULL,
    run_id   INTEGER NOT NULL,
    status   TEXT NOT NULL,           -- ok | failed
    n_claims INTEGER NOT NULL DEFAULT 0,
    error    TEXT,
    PRIMARY KEY (post_id, run_id)
);
CREATE INDEX IF NOT EXISTS idx_claims_patient ON claims(patient_id, claim_type);
CREATE INDEX IF NOT EXISTS idx_claims_post    ON claims(post_id);
CREATE INDEX IF NOT EXISTS idx_facts_kv       ON claim_facts(key, value);
CREATE INDEX IF NOT EXISTS idx_facts_claim    ON claim_facts(claim_id);
"""


def open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def get_or_create_run(conn: sqlite3.Connection, config: dict) -> tuple[int, bool]:
    """Return (run_id, resumed). Runs are keyed by their config hash, so re-running
    the same prompt+model+corpus continues the same run instead of forking one."""
    blob = json.dumps(config, sort_keys=True)
    sha = hashlib.sha256(blob.encode()).hexdigest()[:16]
    row = conn.execute("SELECT run_id FROM runs WHERE config_sha = ?", (sha,)).fetchone()
    if row:
        return row[0], True
    cur = conn.execute(
        "INSERT INTO runs (run_at, provider, model, prompt_sha, config, config_sha)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (int(time.time()), config["provider"], config["model"],
         config["prompt_sha"], blob, sha),
    )
    conn.commit()
    return cur.lastrowid, False


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


def call_llm(client, system_prompt: str, user_message: str, label: str = "?",
             temperature: float = LLM_TEMPERATURE) -> str:
    """One cached, retried LLM call. Only transient failures are retried."""
    def _call() -> str:
        for attempt, delay in enumerate([0, *RETRY_DELAYS]):
            if delay:
                time.sleep(delay)
            try:
                resp = client.messages.create(
                    model=MODEL_FAST,
                    temperature=temperature,
                    max_tokens=MAX_TOKENS,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                )
                return response_text(check_response(resp, MODEL_FAST))
            except Exception as e:
                print(f"  [retry] {label} attempt {attempt + 1}: {type(e).__name__}: "
                      f"{str(e)[:160]}", flush=True)
                if not _is_transient(e) or attempt == len(RETRY_DELAYS):
                    raise
        return ""

    return cached_completion(
        provider=LLM_PROVIDER, model=MODEL_FAST, system=system_prompt,
        prompt=user_message, temperature=temperature, max_tokens=MAX_TOKENS,
        call_fn=_call,
    )


_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text.lower()).strip()


def parse_claims(raw: str, post_text: str, stats: Counter) -> tuple[list[dict], list[dict]]:
    """Validate an LLM response into (claims, edges). Everything rejected is counted."""
    data = parse_json_response(raw)
    if not isinstance(data, dict):
        raise ValueError("response was not a JSON object")

    norm_post = _norm(post_text)
    claims: list[dict] = []
    for item in data.get("claims") or []:
        if not isinstance(item, dict):
            stats["claim_not_object"] += 1
            continue
        ctype = str(item.get("claim_type") or "").strip().lower()
        if ctype not in CLAIM_TYPES:
            stats[f"bad_claim_type:{ctype[:24]}"] += 1
            continue
        payload = item.get("payload")
        if not isinstance(payload, dict):
            stats["missing_payload"] += 1
            continue
        primary, known = CLAIM_TYPES[ctype]
        payload = {k: ("" if isinstance(v, str) and v.strip().lower() in PLACEHOLDER_VALUES else v)
                   for k, v in payload.items()}
        payload = {k: v for k, v in payload.items() if v not in (None, "", [], {})}
        if not str(payload.get(primary, "")).strip():
            stats[f"missing_primary:{ctype}"] += 1
            continue
        # Unknown keys are KEPT (they are signal about what the model wants to say)
        # but counted so prompt/schema drift is visible in the run summary.
        for k in payload:
            if k != primary and k not in known:
                stats[f"extra_key:{ctype}.{k}"] += 1
        span = str(item.get("source_span") or "").strip()
        try:
            conf = float(item.get("confidence"))
        except (TypeError, ValueError):
            conf = None
        claims.append({
            "local_id": str(item.get("local_id") or f"c{len(claims) + 1}"),
            "claim_type": ctype,
            "source_span": span,
            "confidence": conf,
            "payload": payload,
            "span_grounded": int(bool(span) and _norm(span) in norm_post),
        })

    by_local = {c["local_id"]: c for c in claims}
    edges: list[dict] = []
    for item in data.get("edges") or []:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("relation") or "").strip().upper()
        src, dst = str(item.get("from") or ""), str(item.get("to") or "")
        if rel not in RELATIONS:
            stats[f"bad_relation:{rel[:24]}"] += 1
            continue
        if src not in by_local or dst not in by_local or src == dst:
            stats["dangling_edge"] += 1
            continue
        try:
            conf = float(item.get("confidence"))
        except (TypeError, ValueError):
            conf = None
        edges.append({"from": src, "to": dst, "relation": rel, "confidence": conf})

    return claims, edges


def _fact_rows(claim_id: str, run_id: int, claim: dict) -> list[tuple]:
    rows = [(claim_id, run_id, "claim_type", claim["claim_type"])]
    if claim["source_span"]:
        rows.append((claim_id, run_id, "source_span", claim["source_span"]))
    for key, value in claim["payload"].items():
        values = value if isinstance(value, list) else [value]
        for v in values:
            text = str(v).strip()
            if text:
                rows.append((claim_id, run_id, key, text))
    return rows


def store_post(conn: sqlite3.Connection, lock: threading.Lock, run_id: int,
               post: dict, claims: list[dict], edges: list[dict]) -> None:
    ids = {c["local_id"]: str(uuid.uuid4()) for c in claims}
    claim_rows, fact_rows = [], []
    for c in claims:
        cid = ids[c["local_id"]]
        claim_rows.append((cid, run_id, post["author_hash"], post.get("post_id"),
                           c["claim_type"], c["source_span"], c["confidence"],
                           json.dumps(c["payload"], ensure_ascii=False), c["span_grounded"]))
        fact_rows.extend(_fact_rows(cid, run_id, c))
    edge_rows = [(run_id, ids[e["from"]], ids[e["to"]], e["relation"], None, e["confidence"])
                 for e in edges]
    with lock:
        conn.executemany(
            "INSERT INTO claims (claim_id, run_id, patient_id, post_id, claim_type,"
            " source_span, confidence, payload, span_grounded)"
            " VALUES (?,?,?,?,?,?,?,?,?)", claim_rows)
        conn.executemany(
            "INSERT INTO claim_facts (claim_id, run_id, key, value) VALUES (?,?,?,?)",
            fact_rows)
        conn.executemany(
            "INSERT INTO claim_edges (run_id, from_claim, to_claim, relation, properties,"
            " confidence) VALUES (?,?,?,?,?,?)", edge_rows)
        conn.execute(
            "INSERT OR REPLACE INTO post_status (post_id, run_id, status, n_claims, error)"
            " VALUES (?,?,?,?,?)", (post.get("post_id"), run_id, "ok", len(claims), None))
        conn.commit()


def mark_failed(conn: sqlite3.Connection, lock: threading.Lock, run_id: int,
                post: dict, reason: str) -> None:
    with lock:
        conn.execute(
            "INSERT OR REPLACE INTO post_status (post_id, run_id, status, n_claims, error)"
            " VALUES (?,?,?,?,?)", (post.get("post_id"), run_id, "failed", 0, reason[:500]))
        conn.commit()


def cmd_run(args: argparse.Namespace) -> None:
    posts = json.loads(args.corpus.read_text(encoding="utf-8"))
    if args.limit:
        posts = posts[:args.limit]
    posts = [p for p in posts if p.get("author_hash")]

    system_prompt = build_system_prompt()
    config = {
        "provider": LLM_PROVIDER, "model": MODEL_FAST, "temperature": LLM_TEMPERATURE,
        "prompt_sha": hashlib.sha256(system_prompt.encode()).hexdigest()[:16],
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

    client = get_llm_client()
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
                raw = call_llm(client, system_prompt, body, label=label, temperature=temp)
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
# COMPARISON vs the flat extraction
# =============================================================================

META_COLS = {"author_hash", "source", "post_id", "text_count", "schema_id",
             "extraction_method", "extracted_at"}

# Which claim types could plausibly carry a given flat field's signal.
FIELD_TO_TYPES: dict[str, tuple[str, ...]] = {
    "conditions": ("diagnostic",),
    "diagnosis_source": ("diagnostic",),
    "diagnostic_odyssey": ("diagnostic",),
    "misdiagnosis": ("diagnostic",),
    "time_to_diagnosis": ("diagnostic",),
    "prior_infections": ("diagnostic", "symptom"),
    "infection_count": ("diagnostic", "symptom"),
    "covid_wave": ("diagnostic", "attribute"),
    "medications": ("treatment_response",),
    "dosage": ("treatment_response",),
    "treatment_outcome": ("treatment_response",),
    "alternative_treatments": ("treatment_response",),
    "dietary_interventions": ("treatment_response",),
    "procedures": ("treatment_response", "diagnostic"),
    "clinical_trial_participation": ("treatment_response",),
    "vaccination_status": ("treatment_response", "attribute"),
    "symptom_duration": ("symptom",),
    "symptom_trajectory": ("symptom",),
    "onset_trigger": ("symptom", "diagnostic", "insight"),
    "long_covid_duration_months": ("symptom", "diagnostic"),
    "age_at_onset": ("symptom", "diagnostic", "attribute"),
    "mental_health": ("symptom", "diagnostic"),
    "biomarker_results": ("diagnostic",),
    "age": ("attribute",),
    "sex_gender": ("attribute",),
    "location_country": ("attribute",),
    "location_us_state": ("attribute",),
    "ethnicity": ("attribute",),
    "family_history": ("attribute", "diagnostic"),
    "hormonal_events": ("attribute", "symptom"),
    "functional_status_tier": ("attribute", "symptom"),
    "work_disability_status": ("attribute", "symptom"),
    "social_impact": ("attribute", "symptom", "insight"),
    "healthcare_costs": ("attribute", "insight"),
    "healthcare_system": ("attribute", "insight"),
    "doctor_dismissal": ("insight", "diagnostic"),
}

_STOP = {"the", "a", "an", "of", "and", "or", "to", "in", "for", "with", "my", "i",
         "was", "is", "it", "on", "at", "no", "not", "yes", "unknown", "none", "n/a"}
_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> set[str]:
    # Numbers are kept at any length: ages ("34") and durations ("18") are exactly
    # the values a length filter would silently delete, faking a retention miss.
    return {t for t in _TOKEN.findall(text.lower())
            if (len(t) > 2 or t.isdigit()) and t not in _STOP}


def matches(value: str, haystack: set[str]) -> bool:
    """True if most content tokens of *value* appear in *haystack*."""
    tv = tokens(value)
    if not tv:
        return False
    return len(tv & haystack) / len(tv) >= 0.6


def cmd_compare(args: argparse.Namespace) -> None:
    conn = open_db(args.db)
    run_id = args.run_id or conn.execute(
        "SELECT run_id FROM runs ORDER BY run_at DESC LIMIT 1").fetchone()[0]

    baseline = {r["post_id"]: r for r in csv.DictReader(
        args.baseline.open(encoding="utf-8"))}
    fields = [c for c in next(iter(baseline.values())) if c not in META_COLS]

    # KG side, restricted to posts the baseline also covers.
    claims_by_post: dict[str, list[dict]] = defaultdict(list)
    for pid, ctype, span, payload_json in conn.execute(
            "SELECT post_id, claim_type, source_span, payload FROM claims"
            " WHERE run_id = ?", (run_id,)):
        if pid not in baseline:
            continue
        payload = json.loads(payload_json)
        primary = CLAIM_TYPES[ctype][0]
        claims_by_post[pid].append({
            "type": ctype,
            "text": span + " " + " ".join(str(v) for v in payload.values()),
            "primary": str(payload.get(primary, "")),
        })
    processed = [r[0] for r in conn.execute(
        "SELECT post_id FROM post_status WHERE run_id = ? AND status = 'ok'", (run_id,))]
    posts = [p for p in processed if p in baseline]
    n = len(posts)
    if not n:
        sys.exit("No overlap between kg.db posts and the baseline records.csv.")

    # --- 1/2. yield + coverage ---
    kg_counts = [len(claims_by_post.get(p, [])) for p in posts]
    flat_counts = [sum(1 for f in fields if (baseline[p].get(f) or "").strip()) for p in posts]
    type_dist = Counter(c["type"] for p in posts for c in claims_by_post.get(p, []))

    # --- 3. per-field retention, split by whether the KG made any claim at all ---
    # A post where the KG abstained is not the same failure as a post where it
    # produced claims but dropped a value: abstention is usually the KG refusing to
    # attribute a study abstract / news repost to the author, which the flat schema does.
    retention: dict[str, list[int]] = defaultdict(list)   # engaged posts only
    abstain_cells: Counter = Counter()                    # field -> cells on abstained posts
    abstained = [p for p in posts if not claims_by_post.get(p)]
    for p in posts:
        claims = claims_by_post.get(p, [])
        by_type: dict[str, set[str]] = defaultdict(set)
        for c in claims:
            by_type[c["type"]] |= tokens(c["text"])
        for f in fields:
            cell = (baseline[p].get(f) or "").strip()
            if not cell:
                continue
            if not claims:
                abstain_cells[f] += 1
                continue
            scope = set()
            for t in FIELD_TO_TYPES.get(f, tuple(CLAIM_TYPES)):
                scope |= by_type.get(t, set())
            retention[f].append(
                int(any(matches(v, scope) for v in cell.split(" | ") if v.strip())))

    # --- 4. new signal: claims with no counterpart in the baseline row ---
    novel: list[tuple[str, str, str]] = []
    n_novel = 0
    for p in posts:
        flat_tokens = tokens(" ".join(
            (baseline[p].get(f) or "") for f in fields))
        for c in claims_by_post.get(p, []):
            if c["primary"] and not matches(c["primary"], flat_tokens):
                n_novel += 1
                if len(novel) < 15:
                    novel.append((p, c["type"], c["primary"]))

    # --- 5/6/7. grounding, graph, cost ---
    grounded = conn.execute(
        "SELECT AVG(span_grounded) FROM claims WHERE run_id=?", (run_id,)).fetchone()[0] or 0
    rels = Counter(dict(conn.execute(
        "SELECT relation, COUNT(*) FROM claim_edges WHERE run_id=? GROUP BY 1", (run_id,))))
    n_edges = sum(rels.values())
    linked = conn.execute(
        "SELECT COUNT(DISTINCT c) FROM (SELECT from_claim AS c FROM claim_edges WHERE run_id=?"
        " UNION SELECT to_claim FROM claim_edges WHERE run_id=?)", (run_id, run_id)).fetchone()[0]
    n_claims = sum(kg_counts)
    n_facts = conn.execute(
        "SELECT COUNT(*) FROM claim_facts WHERE run_id=?", (run_id,)).fetchone()[0]
    failed = conn.execute(
        "SELECT COUNT(*) FROM post_status WHERE run_id=? AND status='failed'",
        (run_id,)).fetchone()[0]

    ret_rows = sorted(
        ((f, sum(v) / len(v), len(v)) for f, v in retention.items() if v),
        key=lambda r: r[1])

    lines = []
    add = lines.append
    add(f"# Knowledge graph vs flat extraction (run_id={run_id})\n")
    add(f"- posts compared: **{n}** (baseline `{args.baseline.name}`, same posts, same model)")
    add(f"- failed posts: {failed}\n")
    add("## 1. Yield per post\n")
    add("| | claims / filled cells per post |")
    add("|---|---|")
    add(f"| KG claims   | mean **{statistics.mean(kg_counts):.2f}**, "
        f"median {statistics.median(kg_counts):.0f}, max {max(kg_counts)} |")
    add(f"| flat fields | mean **{statistics.mean(flat_counts):.2f}**, "
        f"median {statistics.median(flat_counts):.0f}, max {max(flat_counts)} "
        f"(of {len(fields)} possible) |")
    add(f"\nTuples in the store: **{n_facts}** facts across {n_claims} claims "
        f"({n_facts / max(n, 1):.2f} per post).\n")
    add("Claims by type:\n")
    for t, c in type_dist.most_common():
        add(f"- `{t}`: {c} ({c / max(n_claims, 1) * 100:.0f}%)")
    add("\n## 2. Post coverage\n")
    add(f"- posts with >=1 claim: **{sum(1 for c in kg_counts if c) / n * 100:.1f}%**")
    add(f"- posts with >=1 filled flat field: {sum(1 for c in flat_counts if c) / n * 100:.1f}%")
    add(f"- posts where the KG abstained entirely: {len(abstained)} "
        f"({len(abstained) / n * 100:.1f}%), carrying {sum(abstain_cells.values())} "
        f"baseline cells\n")
    add("## 3. Baseline retention per flat field, on posts where the KG engaged (worst first)\n")
    add("Does the value the flat schema recorded still exist somewhere in the claims for that"
        " post? Restricted to the "
        f"{n - len(abstained)} posts with >=1 claim -- abstentions are counted separately in"
        " section 3b, because the KG is instructed to claim only about the AUTHOR and refuses"
        " posts (study abstracts, news reposts) the flat schema attributes anyway.\n")
    add("Retention is a LOWER BOUND: the match is lexical (>=60% of the cell's content"
        " tokens present in the claim), so a claim that says the same thing in the author's"
        " words ('couldn't leave the house' vs `social_impact: isolation`) scores as a miss.\n")
    add("| field | retained | n non-empty |")
    add("|---|---|---|")
    for f, rate, cnt in ret_rows:
        add(f"| {f} | {rate * 100:.0f}% | {cnt} |")
    overall = sum(sum(v) for v in retention.values()) / max(
        sum(len(v) for v in retention.values()), 1)
    add(f"\n**Overall retention: {overall * 100:.1f}%** of non-empty baseline cells on"
        " engaged posts.\n")
    add("### 3b. Baseline cells on posts the KG abstained from\n")
    add("Each of these is either a real KG miss or a baseline over-attribution."
        " Sample the posts before deciding.\n")
    add("| field | cells lost to abstention |")
    add("|---|---|")
    for f, c in abstain_cells.most_common(15):
        add(f"| {f} | {c} |")
    add("\nAbstained posts to eyeball: "
        + ", ".join(f"`{p}`" for p in abstained[:10]) + "\n")
    add("## 4. New signal\n")
    add(f"- claims with no counterpart anywhere in the baseline row: **{n_novel}** "
        f"({n_novel / max(n_claims, 1) * 100:.0f}% of claims, {n_novel / n:.2f} per post)\n")
    add("Samples:\n")
    for p, t, txt in novel:
        add(f"- `{p}` [{t}] {txt[:180]}")
    add("\n## 5. Grounding\n")
    add(f"- claims whose `source_span` is verbatim in the post: **{grounded * 100:.1f}%**\n")
    add("## 6. Graph\n")
    add(f"- edges: {n_edges} ({n_edges / n:.2f} per post); "
        f"claims in >=1 edge: {linked / max(n_claims, 1) * 100:.0f}%")
    for r, c in rels.most_common():
        add(f"  - `{r}`: {c}")
    add("")

    report = "\n".join(lines)
    print("\n" + report)
    out_md = args.out or args.db.parent / "kg_vs_flat.md"
    out_md.write_text(report, encoding="utf-8")
    out_csv = out_md.with_suffix(".csv")
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["field", "retention", "n_nonempty", "baseline_fill_rate"])
        for f, rate, cnt in ret_rows:
            w.writerow([f, round(rate, 3), cnt, round(cnt / n, 3)])
    print(f"  Wrote {out_md}\n  Wrote {out_csv}")


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
