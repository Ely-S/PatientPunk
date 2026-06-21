"""Read-only evidence tools over the sentiment SQLite DB (`data/posts.db`).

Five JSON-able functions the EvidencePacket builder calls. Each is read-only,
never writes, and degrades gracefully on an unknown drug (`found: False`) — it
NEVER fabricates a row. All numbers come straight from `treatment_reports`.

This module is part of the `src/` (sentiment) system. It imports ONLY from
`utilities` — never `patientpunk` / `variable_extraction` (frozen decoupling
boundary). Imports are bare because pyproject sets `pythonpath = ["src"]`.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from utilities.db import load_synonyms, open_db, post_text

# Order signal strength so "strong" floats to the top of LIMIT-k example pulls.
# Mirrors verify.py's SIG_RANK (higher = stronger).
SIG_RANK: dict[str | None, int] = {"strong": 3, "moderate": 2, "weak": 1, "n/a": 0, None: 0, "": 0}

# Snippet length for verbatim example text. Verbatim only — never paraphrase.
_SNIPPET_CHARS = 400

# The four sentiment buckets we always report (pre-seeded to 0).
SENTIMENTS = ("positive", "negative", "mixed", "neutral")


def _resolve_drug(name: str, db_path: str | Path) -> str:
    """Resolve a free-text drug query to a canonical name (case-insensitive over
    canonical_name + aliases); unmatched -> lowercased passthrough. No LLM."""
    q = (name or "").strip().lower()
    if not q:
        return q
    synonyms = load_synonyms(Path(db_path))  # canonical -> [aliases]

    # Build a flat lookup of every known surface form -> canonical.
    surface_to_canonical: dict[str, str] = {}
    conn = open_db(Path(db_path))
    try:
        for (canonical,) in conn.execute("SELECT canonical_name FROM treatment"):
            surface_to_canonical.setdefault(canonical.strip().lower(), canonical)
    finally:
        conn.close()
    for canonical, aliases in synonyms.items():
        surface_to_canonical.setdefault(canonical.strip().lower(), canonical)
        for alias in aliases or []:
            surface_to_canonical.setdefault(str(alias).strip().lower(), canonical)

    return surface_to_canonical.get(q, q)


def get_sentiment_breakdown(drug: str, db_path: str | Path) -> dict:
    """Raw sentiment counts for one drug -> {found, drug, n_reports, counts{4 buckets}}."""
    canonical = _resolve_drug(drug, db_path)
    counts: dict[str, int] = {s: 0 for s in SENTIMENTS}
    conn = open_db(Path(db_path))
    try:
        rows = conn.execute(
            "SELECT tr.sentiment, COUNT(*) "
            "FROM treatment_reports tr "
            "JOIN treatment t ON tr.drug_id = t.id "
            "WHERE t.canonical_name = ? COLLATE NOCASE "
            "GROUP BY tr.sentiment",
            (canonical,),
        ).fetchall()
    finally:
        conn.close()
    n_reports = 0
    for sentiment, c in rows:
        n_reports += c
        if sentiment in counts:
            counts[sentiment] += c
        else:  # unexpected label — surface it under its own key rather than drop
            counts[sentiment] = counts.get(sentiment, 0) + c
    return {
        "found": n_reports > 0,
        "drug": canonical,
        "n_reports": n_reports,
        "counts": counts,
    }


def get_example_reports(drug: str, sentiment: str, k: int, db_path: str | Path) -> dict:
    """Up to k verbatim example reports of one sentiment, strongest signal first."""
    canonical = _resolve_drug(drug, db_path)
    k = max(0, int(k))
    conn = open_db(Path(db_path))
    try:
        rows = conn.execute(
            "SELECT tr.post_id, tr.user_id, tr.signal_strength, "
            "       p.title, p.body_text, p.parent_id "
            "FROM treatment_reports tr "
            "JOIN treatment t ON tr.drug_id = t.id "
            "JOIN posts p ON tr.post_id = p.post_id "
            "WHERE t.canonical_name = ? COLLATE NOCASE "
            "  AND tr.sentiment = ? "
            "ORDER BY CASE tr.signal_strength "
            "           WHEN 'strong' THEN 0 WHEN 'moderate' THEN 1 "
            "           WHEN 'weak' THEN 2 ELSE 3 END",
            (canonical, sentiment),
        ).fetchall()
    finally:
        conn.close()

    examples = []
    for post_id, user_id, signal, title, body_text, parent_id in rows[:k]:
        text = post_text(title, body_text, parent_id)
        snippet = text[:_SNIPPET_CHARS].strip()
        examples.append(
            {
                "post_id": post_id,
                "user_id": user_id,
                "signal": signal or "n/a",
                "sentiment": sentiment,
                "text": snippet,
            }
        )
    return {
        "found": bool(examples),
        "drug": canonical,
        "sentiment": sentiment,
        "examples": examples,
    }


def get_side_effects(drug: str, db_path: str | Path) -> dict:
    """Tally reported side effects for one drug, most-common first."""
    canonical = _resolve_drug(drug, db_path)
    conn = open_db(Path(db_path))
    try:
        rows = conn.execute(
            "SELECT tr.side_effects "
            "FROM treatment_reports tr "
            "JOIN treatment t ON tr.drug_id = t.id "
            "WHERE t.canonical_name = ? COLLATE NOCASE "
            "  AND tr.side_effects IS NOT NULL "
            "  AND tr.side_effects != '' "
            "  AND tr.side_effects != '[]'",
            (canonical,),
        ).fetchall()
    finally:
        conn.close()

    counter: Counter[str] = Counter()
    for (raw,) in rows:
        try:
            effects = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(effects, list):
            continue
        for effect in effects:
            label = str(effect).strip().lower()
            if label:
                counter[label] += 1

    side_effects = [{"effect": effect, "count": count} for effect, count in counter.most_common()]
    return {
        "found": bool(side_effects),
        "drug": canonical,
        "side_effects": side_effects,
    }


def list_drugs(min_reports: int, db_path: str | Path) -> dict:
    """List drugs with >= min_reports reports + deduped-user counts, report-count desc."""
    min_reports = max(0, int(min_reports))
    conn = open_db(Path(db_path))
    try:
        rows = conn.execute(
            "SELECT t.canonical_name, COUNT(*) AS n_reports, "
            "       COUNT(DISTINCT tr.user_id) AS n_users "
            "FROM treatment_reports tr "
            "JOIN treatment t ON tr.drug_id = t.id "
            "GROUP BY t.canonical_name "
            "HAVING n_reports >= ? "
            "ORDER BY n_reports DESC, t.canonical_name ASC",
            (min_reports,),
        ).fetchall()
    finally:
        conn.close()
    drugs = [
        {"drug": name, "n_reports": n_reports, "n_users": n_users}
        for name, n_reports, n_users in rows
    ]
    return {"found": bool(drugs), "min_reports": min_reports, "drugs": drugs}


def get_caveats(drug: str, db_path: str | Path) -> dict:
    """Methodology caveats for one drug: report/user/subreddit counts; small_n_warning < 30 users."""
    canonical = _resolve_drug(drug, db_path)
    conn = open_db(Path(db_path))
    try:
        n_reports, n_users = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT tr.user_id) "
            "FROM treatment_reports tr "
            "JOIN treatment t ON tr.drug_id = t.id "
            "WHERE t.canonical_name = ? COLLATE NOCASE",
            (canonical,),
        ).fetchone()
        subreddits = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT u.source_subreddit "
                "FROM treatment_reports tr "
                "JOIN treatment t ON tr.drug_id = t.id "
                "JOIN users u ON tr.user_id = u.user_id "
                "WHERE t.canonical_name = ? COLLATE NOCASE "
                "  AND u.source_subreddit IS NOT NULL",
                (canonical,),
            ).fetchall()
        ]
    finally:
        conn.close()

    n_reports = n_reports or 0
    n_users = n_users or 0
    return {
        "found": n_reports > 0,
        "drug": canonical,
        "n_reports": n_reports,
        "n_users": n_users,
        "subreddits": subreddits,
        "small_n_warning": n_users < 30,
        "self_report": True,
        "is_anecdotal": True,
    }
