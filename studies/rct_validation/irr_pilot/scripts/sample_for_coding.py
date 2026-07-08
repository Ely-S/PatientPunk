"""
Pull a stratified sample of posts from the raw patientpunk JSON for
intercoder reliability coding. Produces two CSVs:

  coding_input.csv  — given to human coders / AI coders (blind: no AI labels)
  ai_labels.csv     — analyst-only; the pipeline's labels joined back by sample_id

Pilot run: 50 posts from the r/covidlonghaulers 1-month JSON that was the
source for patientpunk.db. Posts are sampled across three strata to exercise
both precision (AI found a drug — can humans agree?) and recall (post looks
druggy to a keyword regex but AI found nothing — are humans catching things
the pipeline missed?).

Usage (run from the repo root):
    python studies/rct_validation/irr_pilot/scripts/sample_for_coding.py --n 50 --seed 42

Outputs land in data/irr_pilot/ (gitignored).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────

SOURCE_JSON = (
    Path.home()
    / "OneDrive"
    / "Documents"
    / "Projects"
    / "PatientPunk_data"
    / "subreddit_posts_month_1081posts.json"
)
DB_PATH = Path("data/patientpunk.db")
TAGGED_MENTIONS = Path("data/drug_pipeline/tagged_mentions.json")
CANONICAL_MAP = Path("data/drug_pipeline/canonical_map.json")
OUT_DIR = Path("data/irr_pilot")
SUBREDDIT_LABEL = "covidlonghaulers"  # the source JSON omits the subreddit field

# ─── Upstream context depth ──────────────────────────────────────────────────
# The AI pipeline (post-2026-04-11) inherits drug mentions from up to 2
# ancestors via max_upstream_depth=2. For IRR validity, both (a) the AI
# labels in ai_labels.csv must be filtered to only pairs that depth=2 would
# produce, and (b) human coders must see the same upstream chain the AI
# saw — so parent_context is capped at 2 hops.
AI_UPSTREAM_DEPTH = 2

# ─── Drug-likeness heuristic (for stratum 2) ──────────────────────────────────
# This regex flags posts that *look* like they might discuss a treatment even
# when the AI extracted nothing. Coders on these posts reveal AI recall gaps.

DRUG_KEYWORD_RE = re.compile(
    r"\b("
    r"mg|mcg|dose|dosage|pill|tablet|capsule|prescription|prescribed|"
    r"took|taking|tried|started|stopped|"
    r"ssri|snri|nsaid|statin|beta.?blocker|"
    r"ibuprofen|tylenol|acetaminophen|aspirin|advil|aleve|motrin|"
    r"naltrexone|ldn|gabapentin|lyrica|pregabalin|"
    r"prozac|zoloft|lexapro|paxil|wellbutrin|cymbalta|effexor|"
    r"xanax|ativan|klonopin|valium|"
    r"magnesium|b12|vitamin\s?d|iron|zinc|"
    r"melatonin|nac|coq10|glutathione|"
    r"antihistamine|benadryl|zyrtec|claritin|allegra|"
    r"compression|pt\b|physical therapy|"
    r"steroid|prednisone|cortisol|"
    r"paxlovid|metformin|ivermectin|fluvoxamine"
    r")\b",
    re.IGNORECASE,
)


# ─── Stratum composition for the pilot ────────────────────────────────────────

STRATA = {
    # Tests precision + sentiment agreement. Half the sample.
    "ai_found_drug": 0.50,
    # Tests AI recall: post looks druggy but AI saw nothing. Critical for
    # claiming the pipeline doesn't miss obvious drugs.
    "no_ai_drug_keyword_match": 0.30,
    # Tests AI specificity (and gives humans easy "no drug here" controls).
    "no_ai_drug_random": 0.20,
}


def compute_valid_pairs_under_depth(
    tagged_mentions_path: Path,
    canonical_map_path: Path,
    max_depth: int,
) -> dict[str, set[str]]:
    """For each entry, the set of canonical drugs that would be classified
    if the pipeline ran with max_upstream_depth=max_depth.

    An entry's valid drugs = drugs_direct (extracted from its own text) ∪
    drugs_context_depth=max_depth (inherited from ancestors within max_depth
    hops).

    Returns {entry_id: {canonical_drug, ...}}.

    Mirrors the logic in src/pipeline/extract.py::compute_upstream_mentioned_drugs.
    """
    if not tagged_mentions_path.exists():
        raise FileNotFoundError(f"tagged_mentions not found: {tagged_mentions_path}")
    tagged = json.loads(tagged_mentions_path.read_text(encoding="utf-8"))
    if canonical_map_path.exists():
        canon_map = json.loads(canonical_map_path.read_text(encoding="utf-8"))
    else:
        # The pipeline only writes canonicalized_mentions.json (per-entry canonical
        # names already applied), not a raw->canonical map. For stratification we
        # only need to know "did the AI find ANY drug?", so an identity map is fine.
        canon_map = {}
        print(f"  Note: {canonical_map_path.name} not found; using identity canonicalization.")

    id_to_direct: dict[str, list[str]] = {
        e["id"]: list(e.get("drugs_direct") or []) for e in tagged
    }
    id_to_parent: dict[str, str | None] = {
        e["id"]: e.get("parent_id") for e in tagged
    }

    # Memoized upstream traversal up to max_depth hops.
    cache: dict[tuple[str, int], tuple[str, ...]] = {}

    def upstream(eid: str, remaining: int) -> tuple[str, ...]:
        key = (eid, remaining)
        if key in cache:
            return cache[key]
        if remaining == 0:
            cache[key] = ()
            return ()
        pid = id_to_parent.get(eid)
        if not pid:
            cache[key] = ()
            return ()
        parent_drugs = tuple(id_to_direct.get(pid, []))
        grandparent = upstream(pid, remaining - 1)
        # Order-preserving dedupe
        merged = tuple(dict.fromkeys(parent_drugs + grandparent))
        cache[key] = merged
        return merged

    def canonicalize(raw: str) -> str:
        return canon_map.get(raw, raw)

    valid: dict[str, set[str]] = {}
    for eid, direct in id_to_direct.items():
        context = upstream(eid, max_depth)
        raw_set = set(direct) | set(context)
        valid[eid] = {canonicalize(r) for r in raw_set}
    return valid


def load_ai_labels(
    db_path: Path,
    valid_pairs: dict[str, set[str]] | None = None,
) -> dict[str, list[dict]]:
    """Return {post_id: [{drug, sentiment, signal_strength}, ...]} from the DB.

    If valid_pairs is provided, rows are filtered to only include
    (post_id, canonical_drug) combinations that would have been produced
    under the depth-capped pipeline run.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    # Pull all treatment_reports rows ordered newest-run-first, then dedupe
    # on (post, drug) below — first row wins, so the most recent label for
    # each pair survives. The DB may contain rows from multiple prior runs
    # (some with reclassify=true), producing duplicate pairs.
    rows = conn.execute(
        "SELECT tr.post_id, t.canonical_name, tr.sentiment, tr.signal_strength "
        "FROM treatment_reports tr "
        "JOIN treatment t ON t.id = tr.drug_id "
        "ORDER BY tr.run_id DESC, tr.report_id DESC"
    ).fetchall()
    conn.close()

    labels: dict[str, list[dict]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    kept = dropped = deduped = 0
    for post_id, drug, sentiment, signal_strength in rows:
        if valid_pairs is not None:
            allowed = valid_pairs.get(post_id, set())
            if drug not in allowed:
                dropped += 1
                continue
        # Dedupe on (post, canonical_drug) — pipeline occasionally emits
        # the same pair more than once within a single run.
        key = (post_id, drug)
        if key in seen:
            deduped += 1
            continue
        seen.add(key)
        labels[post_id].append(
            {"drug": drug, "sentiment": sentiment, "signal_strength": signal_strength}
        )
        kept += 1
    if valid_pairs is not None:
        print(
            f"  ai_labels filtered to depth=2: "
            f"{kept:,} pairs kept, {dropped:,} dropped, {deduped:,} deduped"
        )
    return labels


def fmt_date(created_utc) -> str:
    """Arctic-shift timestamps are ints; the scraper JSON may have strings."""
    if created_utc is None:
        return ""
    try:
        t = int(created_utc)
    except (TypeError, ValueError):
        return str(created_utc)[:10]
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")


def main():
    global SOURCE_JSON, DB_PATH, TAGGED_MENTIONS, CANONICAL_MAP
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50, help="total sample size")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility")
    ap.add_argument("--min-chars", type=int, default=100, help="min body_text length")
    ap.add_argument("--max-chars", type=int, default=800, help="max body_text length")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR,
                    help="output directory (default: data/irr_pilot)")
    ap.add_argument("--source-json", type=Path, default=SOURCE_JSON,
                    help="source posts JSON (default: PatientPunk_data/subreddit_posts_month_1081posts.json)")
    ap.add_argument("--db-path", type=Path, default=DB_PATH,
                    help="SQLite DB containing classified treatment_reports (default: data/patientpunk.db)")
    ap.add_argument("--tagged-mentions", type=Path, default=TAGGED_MENTIONS,
                    help="tagged_mentions.json from the pipeline (default: data/drug_pipeline/tagged_mentions.json)")
    ap.add_argument("--canonical-map", type=Path, default=CANONICAL_MAP,
                    help="canonical_map.json from the pipeline (default: data/drug_pipeline/canonical_map.json)")
    args = ap.parse_args()
    # Override module-level constants with CLI args (some helpers reference them)
    SOURCE_JSON = args.source_json
    DB_PATH = args.db_path
    TAGGED_MENTIONS = args.tagged_mentions
    CANONICAL_MAP = args.canonical_map

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    random.seed(args.seed)

    # ── Load raw posts + comments from JSON. The pipeline extracts from both,
    #    so the codable pool is (top-level post) ∪ (comments with parent context).
    raw = json.loads(SOURCE_JSON.read_text(encoding="utf-8"))
    print(f"Loaded {len(raw):,} posts from {SOURCE_JSON.name}")

    # ── Compute valid (entry, drug) pairs that would exist under depth=2
    #    (so ai_labels matches the pipeline's current upstream-depth behavior).
    valid_pairs = compute_valid_pairs_under_depth(
        TAGGED_MENTIONS, CANONICAL_MAP, max_depth=AI_UPSTREAM_DEPTH
    )
    print(f"Depth={AI_UPSTREAM_DEPTH} valid pairs computed for {len(valid_pairs):,} entries")

    # ── Load AI labels from the pipeline-processed DB, filtered to depth=2
    ai_labels = load_ai_labels(DB_PATH, valid_pairs=valid_pairs)
    print(f"AI labels found for {len(ai_labels):,} distinct post_ids in {DB_PATH.name}")

    # ── Build an id → record lookup so we can walk parent chains. Some
    #    sampled comments will be replies to OTHER comments (not the post
    #    directly), and the AI pipeline traverses the full upstream chain
    #    via max_upstream_depth. Humans must see the same chain for the IRR
    #    comparison to be valid.
    id_to_record: dict[str, dict] = {}
    for post in raw:
        pid = post.get("post_id")
        if pid:
            id_to_record[pid] = {
                "type": "post",
                "title": post.get("title") or "",
                "body": (post.get("body") or "").strip(),
                "parent_id": None,
            }
        for c in post.get("comments", []):
            cid = c.get("comment_id")
            if cid:
                id_to_record[cid] = {
                    "type": "comment",
                    "body": (c.get("body") or "").strip(),
                    "parent_id": c.get("parent_id"),
                }

    def build_parent_chain(comment: dict, max_hops: int = AI_UPSTREAM_DEPTH) -> str:
        """Walk parent_id upward up to max_hops; render the chain as text.

        Matches the AI pipeline's max_upstream_depth behavior — the AI
        inherits drug mentions from at most max_hops ancestors, so humans
        see the same slice of upstream context.

        Result is ordered root → immediate-parent, separated by horizontal
        rules so coders can read top-down to follow the conversation.
        For deeply nested comments, only the nearest max_hops ancestors are
        shown; the original post may be out of scope if the chain is long.
        """
        chain: list[str] = []
        current_pid = comment.get("parent_id")
        visited: set[str] = set()
        hops = 0
        while (
            current_pid
            and current_pid in id_to_record
            and current_pid not in visited
            and hops < max_hops
        ):
            hops += 1
            visited.add(current_pid)
            rec = id_to_record[current_pid]
            if rec["type"] == "post":
                block = f"[Parent post: {rec['title']}]\n\n{rec['body']}".strip()
                chain.insert(0, block)
                break  # reached top of thread
            else:
                block = f"[Upstream reply]\n{rec['body']}"
                chain.insert(0, block)
                current_pid = rec["parent_id"]
        return "\n\n---\n\n".join(chain)

    # ── Build codable pool: top-level posts + long-enough comments
    codable: list[dict] = []
    for post in raw:
        # 1) Top-level post as a codable unit
        body = (post.get("body") or "").strip()
        if args.min_chars <= len(body) <= args.max_chars:
            pid = post.get("post_id")
            codable.append(
                {
                    "post_id": pid,
                    "unit_type": "post",
                    "title": post.get("title") or "",
                    "body": body,
                    "parent_context": "",
                    "created_utc": post.get("created_utc"),
                    "flair": post.get("flair"),
                    "has_ai_drug": bool(ai_labels.get(pid)),
                    "has_keyword": bool(DRUG_KEYWORD_RE.search(body)),
                }
            )
        # 2) Each comment as its own codable unit, with FULL upstream chain
        # as context (parent post + any intermediate replies). No truncation —
        # the AI pipeline sees the full chain, so coders must too.
        for c in post.get("comments", []):
            c_body = (c.get("body") or "").strip()
            if not (args.min_chars <= len(c_body) <= args.max_chars):
                continue
            cid = c.get("comment_id")
            parent_ctx = build_parent_chain(c)
            codable.append(
                {
                    "post_id": cid,
                    "unit_type": "comment",
                    "title": "",
                    "body": c_body,
                    "parent_context": parent_ctx,
                    "created_utc": c.get("created_utc"),
                    "flair": None,
                    "has_ai_drug": bool(ai_labels.get(cid)),
                    "has_keyword": bool(DRUG_KEYWORD_RE.search(c_body)),
                }
            )
    print(
        f"Codable pool (len {args.min_chars}\u2013{args.max_chars} chars): {len(codable):,} "
        f"(AI-drug: {sum(p['has_ai_drug'] for p in codable)}, "
        f"keyword-only: {sum(p['has_keyword'] and not p['has_ai_drug'] for p in codable)}, "
        f"neither: {sum(not p['has_keyword'] and not p['has_ai_drug'] for p in codable)})"
    )

    # ── Stratified sample
    pool_ai = [p for p in codable if p["has_ai_drug"]]
    pool_kw = [p for p in codable if not p["has_ai_drug"] and p["has_keyword"]]
    pool_rand = [p for p in codable if not p["has_ai_drug"] and not p["has_keyword"]]

    n_ai = round(args.n * STRATA["ai_found_drug"])
    n_kw = round(args.n * STRATA["no_ai_drug_keyword_match"])
    n_rand = args.n - n_ai - n_kw

    def take(pool, k, label):
        if len(pool) < k:
            print(f"  WARN: stratum '{label}' has only {len(pool)} candidates, wanted {k}")
            k = len(pool)
        return random.sample(pool, k), k

    ai_sample, n_ai = take(pool_ai, n_ai, "ai_found_drug")
    kw_sample, n_kw = take(pool_kw, n_kw, "no_ai_drug_keyword_match")
    rand_sample, n_rand = take(pool_rand, n_rand, "no_ai_drug_random")

    sampled = (
        [("ai_found_drug", p) for p in ai_sample]
        + [("no_ai_drug_keyword_match", p) for p in kw_sample]
        + [("no_ai_drug_random", p) for p in rand_sample]
    )
    random.shuffle(sampled)  # mix strata so coders can't infer from order

    print(
        f"Sampled: {n_ai} ai-found + {n_kw} keyword-only + {n_rand} random "
        f"= {len(sampled)} total"
    )

    # ── Write coding_input.csv (blind)
    coder_path = out_dir / "coding_input.csv"
    with coder_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "sample_id",
                "subreddit",
                "post_date",
                "unit_type",
                "title",
                "parent_context",
                "post_text",
            ]
        )
        for i, (stratum, p) in enumerate(sampled, start=1):
            sid = f"irr-pilot-{i:03d}"
            w.writerow(
                [
                    sid,
                    SUBREDDIT_LABEL,
                    fmt_date(p["created_utc"]),
                    p["unit_type"],
                    p["title"],
                    p["parent_context"],
                    p["body"],
                ]
            )

    # ── Write ai_labels.csv (analyst-only — do NOT distribute to coders)
    ai_path = out_dir / "ai_labels.csv"
    with ai_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "sample_id",
                "source_post_id",
                "stratum",
                "ai_drug_count",
                "ai_drugs",
                "ai_sentiments",
                "ai_signal_strengths",
                "keyword_match",
            ]
        )
        for i, (stratum, p) in enumerate(sampled, start=1):
            sid = f"irr-pilot-{i:03d}"
            labels = ai_labels.get(p["post_id"], [])
            w.writerow(
                [
                    sid,
                    p["post_id"],
                    stratum,
                    len(labels),
                    "|".join(l["drug"] for l in labels),
                    "|".join(l["sentiment"] for l in labels),
                    "|".join(l["signal_strength"] for l in labels),
                    "yes" if p["has_keyword"] else "no",
                ]
            )

    # ── Write an empty coder-output template so humans/AI fill it in
    template_path = out_dir / "coder_output_template.csv"
    with template_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "sample_id",
                "coder_id",
                "drug_mention_verbatim",
                "personal_use",     # yes / no — mirrors the pipeline's
                                    # prefilter step: did the author
                                    # personally use this treatment?
                "sentiment",
                "signal_strength",
                "confidence",
                "notes",
            ]
        )
        # Seed one row per sample so coders see the expected format;
        # they replace/add rows as they go.
        for i, (_, _) in enumerate(sampled, start=1):
            sid = f"irr-pilot-{i:03d}"
            w.writerow([sid, "", "", "", "", "", "", ""])

    print()
    print(f"Wrote {coder_path} ({len(sampled)} rows \u2014 distribute to coders)")
    print(f"Wrote {ai_path} ({len(sampled)} rows \u2014 analyst-only)")
    print(f"Wrote {template_path} (template for coders to fill in)")


if __name__ == "__main__":
    main()
