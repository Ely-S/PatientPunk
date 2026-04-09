"""
patientpunk.db
~~~~~~~~~~~~~~
SQLite ETL and query layer.

Loads output from both pipelines into a shared database keyed on author_hash,
then exposes a single query function for treatment outcome analysis.

Usage:
    from patientpunk.db import init_db, load_corpus, load_extractions, load_sentiment
    from patientpunk.db import query_treatment_outcomes

    conn = init_db(Path("patientpunk.db"))
    load_corpus(conn, Path("data/"))
    run_id = load_extractions(conn, Path("data/demographics.csv"))
    load_sentiment(conn, Path("outputs/sentiment_cache.json"),
                   Path("outputs/canonical_map.json"), run_id)
    df = query_treatment_outcomes(conn, drug="ldn", condition="POTS")
"""

from __future__ import annotations

import csv
import json
import sqlite3
import time
from pathlib import Path


# ── Sentiment / signal encoding ────────────────────────────────────────────────

_SENTIMENT_SCORE: dict[str, float] = {
    "positive": 1.0,
    "mixed":    0.5,
    "neutral":  0.0,
    "negative": -1.0,
}

_SIGNAL_SCORE: dict[str, float] = {
    "strong":   1.0,
    "moderate": 0.67,
    "weak":     0.33,
    "n/a":      0.0,
}


# ── Database setup ─────────────────────────────────────────────────────────────

def init_db(db_path: Path, schema_sql: Path | None = None) -> sqlite3.Connection:
    """
    Create (or open) the SQLite database and apply schema.sql.

    If the tables already exist this is a no-op -- safe to call repeatedly.
    """
    if schema_sql is None:
        schema_sql = Path(__file__).parent.parent.parent / "schema.sql"

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    ddl = schema_sql.read_text(encoding="utf-8")
    # Wrap in IF NOT EXISTS so it's idempotent
    ddl_idempotent = ddl.replace(
        "CREATE TABLE ", "CREATE TABLE IF NOT EXISTS "
    ).replace(
        "CREATE INDEX ", "CREATE INDEX IF NOT EXISTS "
    )
    conn.executescript(ddl_idempotent)
    conn.commit()
    return conn


def _register_run(conn: sqlite3.Connection, model: str, config: dict) -> int:
    """Insert an extraction_runs row and return its run_id."""
    cur = conn.execute(
        "INSERT INTO extraction_runs (run_at, model, config) VALUES (?, ?, ?)",
        (int(time.time()), model, json.dumps(config)),
    )
    conn.commit()
    return cur.lastrowid


# ── ETL: corpus ────────────────────────────────────────────────────────────────

def load_corpus(conn: sqlite3.Connection, corpus_dir: Path) -> int:
    """
    Load subreddit_posts.json -> users + posts tables.

    Returns the number of posts inserted.
    """
    posts_file = corpus_dir / "subreddit_posts.json"
    if not posts_file.exists():
        raise FileNotFoundError(f"Not found: {posts_file}")

    posts = json.loads(posts_file.read_text(encoding="utf-8"))
    inserted = 0

    for post in posts:
        author_hash = post.get("author_hash") or ""
        post_id = post.get("post_id") or post.get("id") or ""
        if not author_hash or not post_id:
            continue

        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, source_subreddit, scraped_at)"
            " VALUES (?, ?, ?)",
            (author_hash, post.get("subreddit", "covidlonghaulers"), int(time.time())),
        )

        body = "\n".join(filter(None, [post.get("title", ""), post.get("body", "")]))
        metadata = json.dumps({
            k: post[k] for k in ("score", "num_comments", "url", "flair")
            if k in post
        })
        post_date = post.get("created_utc")
        if isinstance(post_date, str):
            # ISO string -> unix int best-effort
            try:
                from datetime import datetime
                post_date = int(datetime.fromisoformat(post_date).timestamp())
            except ValueError:
                post_date = None

        conn.execute(
            "INSERT OR IGNORE INTO posts"
            " (post_id, user_id, body_text, metadata, post_date, scraped_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (post_id, author_hash, body, metadata, post_date, int(time.time())),
        )
        inserted += 1

    conn.commit()
    return inserted


# ── ETL: Shaun's pipeline ──────────────────────────────────────────────────────

def load_extractions(
    conn: sqlite3.Connection,
    csv_path: Path,
    run_id: int | None = None,
) -> int:
    """
    Load a CSV with extraction data -> user_profiles + conditions.

    Supports both formats:
    - demographics_deductive.csv (columns: author_hash, age, sex_gender,
      location_country, location_state)
    - records.csv (columns: author_hash, age, sex_gender, location_country,
      location_us_state, conditions, ...)

    Loads demographics into user_profiles and conditions (if present)
    into the conditions table.

    Returns the run_id used (creates one if not supplied).
    """
    if run_id is None:
        run_id = _register_run(conn, "extraction_pipeline", {"source": str(csv_path)})

    with open(csv_path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    conditions_inserted = 0
    for row in rows:
        author_hash = (row.get("author_hash") or "").strip()
        if not author_hash:
            continue

        # Ensure the user exists (corpus may not have been loaded yet)
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, source_subreddit, scraped_at)"
            " VALUES (?, ?, ?)",
            (author_hash, "covidlonghaulers", int(time.time())),
        )

        # Demographics -> user_profiles
        # Reject multi-value fields (pipe-separated) -- these are noisy
        # extractions from user histories mentioning OTHER people.
        age_bucket = _bucketize_age(row.get("age", ""))
        raw_sex = (row.get("sex_gender") or "").strip().lower()
        # Accept only clean sex/gender values, reject Reddit shorthand
        # like "22f", "m8", "f3" which are age+gender packed together.
        _VALID_SEX = {"male", "female", "man", "woman", "non-binary", "nonbinary",
                      "trans", "transgender", "m", "f"}
        sex = raw_sex if raw_sex in _VALID_SEX else None
        # Support both column names: location_state and location_us_state
        state = row.get("location_state", "") or row.get("location_us_state", "")
        raw_loc = " / ".join(filter(None, [
            row.get("location_country", ""),
            state,
        ]))
        location = raw_loc if raw_loc and raw_loc.count("|") == 0 else (raw_loc.split("|")[0].strip() if raw_loc else None)

        # Check if a profile already exists (from a prior load_extractions call)
        existing = conn.execute(
            "SELECT age_bucket, sex, location FROM user_profiles"
            " WHERE user_id = ?",
            (author_hash,),
        ).fetchone()

        if existing:
            # Merge: only fill NULLs, never overwrite existing values
            final_age = existing[0] or age_bucket or None
            final_sex = existing[1] or sex
            final_loc = existing[2] or (location or None)
            conn.execute(
                "UPDATE user_profiles SET age_bucket=?, sex=?, location=?"
                " WHERE user_id=?",
                (final_age, final_sex, final_loc, author_hash),
            )
        else:
            conn.execute(
                "INSERT INTO user_profiles"
                " (user_id, run_id, age_bucket, sex, location)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    author_hash,
                    run_id,
                    age_bucket or None,
                    sex,
                    location or None,
                ),
            )

        # Conditions -> conditions table (if column exists)
        conditions_raw = (row.get("conditions") or "").strip()
        post_id = (row.get("post_id") or "").strip() or None
        if conditions_raw:
            for condition_name in conditions_raw.split(" | "):
                condition_name = condition_name.strip().lower()
                if condition_name:
                    conn.execute(
                        "INSERT INTO conditions"
                        " (run_id, user_id, post_id, condition_type, condition_name)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (run_id, author_hash, post_id, "illness", condition_name),
                    )
                    conditions_inserted += 1

    conn.commit()
    return run_id


def _bucketize_age(raw: str) -> str | None:
    """Convert a raw age string to a decade bucket like '30s'.

    Multi-value strings (e.g. "8 | 22 | 37") from user history extraction
    are rejected -- they contain ages of OTHER people, not the author.
    Only single clean values are bucketed.
    """
    raw = raw.strip()
    if not raw or "|" in raw:
        return None
    # Handle decade strings like "20s", "30s", "mid-30s", "early 40s"
    if raw.endswith("s") and raw[:-1].isdigit():
        return raw  # already a bucket
    try:
        age = int(float(raw))
        if age < 10 or age > 110:
            return None  # implausible age
        decade = (age // 10) * 10
        return f"{decade}s"
    except (ValueError, TypeError):
        return None


def load_conditions(
    conn: sqlite3.Connection,
    merged_records_json: Path,
    run_id: int | None = None,
) -> int:
    """
    Load conditions from merged_records_*.json -> conditions table.

    Returns the run_id used.
    """
    if run_id is None:
        run_id = _register_run(conn, "biomedical_regex+llm", {"source": str(merged_records_json)})

    records = json.loads(merged_records_json.read_text(encoding="utf-8"))
    inserted = 0

    for rec in records:
        meta = rec.get("record_meta", {})
        author_hash = meta.get("author_hash", "")
        post_id = meta.get("post_id")
        fields = rec.get("fields", rec.get("base", {}))

        # Ensure user row exists
        if author_hash:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, source_subreddit, scraped_at)"
                " VALUES (?, ?, ?)",
                (author_hash, "covidlonghaulers", int(time.time())),
            )

        conditions_field = fields.get("conditions", {})
        values = conditions_field.get("values") if isinstance(conditions_field, dict) else None
        if not values:
            continue

        for condition_name in values:
            if not condition_name:
                continue
            conn.execute(
                "INSERT INTO conditions"
                " (run_id, user_id, post_id, condition_type, condition_name)"
                " VALUES (?, ?, ?, ?, ?)",
                (run_id, author_hash or None, post_id, "illness", condition_name.lower()),
            )
            inserted += 1

    conn.commit()
    return run_id


# ── ETL: Polina's pipeline ─────────────────────────────────────────────────────

def load_sentiment(
    conn: sqlite3.Connection,
    sentiment_cache_json: Path,
    canonical_map_json: Path | None = None,
    run_id: int | None = None,
) -> int:
    """
    Load sentiment_cache.json -> treatment + treatment_reports tables.

    Cache keys are "{entry_id}:{drug_name}". Splits on the first colon only.
    Entries with signal=n/a are already excluded from the cache by classify_sentiment.py.

    Returns the run_id used.
    """
    if run_id is None:
        run_id = _register_run(conn, "sentiment_classifier", {"source": str(sentiment_cache_json)})

    cache = json.loads(sentiment_cache_json.read_text(encoding="utf-8"))

    # Load canonical map if available (maps synonyms -> canonical name)
    canonical: dict[str, str] = {}
    if canonical_map_json and canonical_map_json.exists():
        canonical = json.loads(canonical_map_json.read_text(encoding="utf-8"))

    # Drug name -> db id cache (avoids repeated SELECTs)
    drug_id_cache: dict[str, int] = {}

    inserted = 0

    for composite_key, entry in cache.items():
        # ── KEY SPLIT ────────────────────────────────────────────────────────
        # The key format is "entry_id:drug_name" -- split on first colon only
        # so that drug names containing colons (rare but possible) survive.
        if ":" not in composite_key:
            continue
        entry_id, drug_raw = composite_key.split(":", 1)

        # Resolve canonical drug name
        drug_name = canonical.get(drug_raw, drug_raw).strip().lower()
        if not drug_name:
            continue

        # Ensure user + post/comment exist (sentiment entries can reference
        # comments t1_... not in the posts table). posts.user_id is NOT NULL
        # so we use a placeholder for deleted/missing authors.
        author_hash = entry.get("author", "")
        effective_user = author_hash or "__unknown__"
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, source_subreddit, scraped_at)"
            " VALUES (?, ?, ?)",
            (effective_user, "covidlonghaulers", int(time.time())),
        )
        conn.execute(
            "INSERT OR IGNORE INTO posts"
            " (post_id, user_id, body_text, scraped_at)"
            " VALUES (?, ?, ?, ?)",
            (entry_id, effective_user, entry.get("text", ""), int(time.time())),
        )

        # Upsert treatment row
        if drug_name not in drug_id_cache:
            cur = conn.execute(
                "INSERT OR IGNORE INTO treatment (canonical_name) VALUES (?)",
                (drug_name,),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id FROM treatment WHERE canonical_name = ? COLLATE NOCASE",
                (drug_name,),
            ).fetchone()
            drug_id_cache[drug_name] = row[0]

        drug_id = drug_id_cache[drug_name]

        sentiment_raw = entry.get("sentiment", "neutral")
        signal_raw = entry.get("signal", "n/a")
        sentiment_score = _SENTIMENT_SCORE.get(sentiment_raw, 0.0)
        signal_score = _SIGNAL_SCORE.get(signal_raw, 0.0)

        # Ensure user and post/comment entry exist (sentiment can come from
        # comments t1_... which aren't in the posts table loaded from
        # subreddit_posts.json -- insert stub rows to satisfy FKs).
        if author_hash:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, source_subreddit, scraped_at)"
                " VALUES (?, ?, ?)",
                (author_hash, "covidlonghaulers", int(time.time())),
            )
        conn.execute(
            "INSERT INTO treatment_reports"
            " (run_id, post_id, user_id, drug_id, sentiment, signal_strength, sentiment_raw)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                entry_id,
                effective_user,
                drug_id,
                sentiment_score,
                signal_score,
                json.dumps({"sentiment": sentiment_raw, "signal": signal_raw}),
            ),
        )
        inserted += 1

    conn.commit()
    return run_id


# ── Query ──────────────────────────────────────────────────────────────────────

def query_treatment_outcomes(
    conn: sqlite3.Connection,
    drug: str | None = None,
    condition: str | None = None,
    sex: str | None = None,
    age_bucket: str | None = None,
) -> list[dict]:
    """
    Return treatment outcome statistics, optionally filtered by cohort.

    Parameters
    ----------
    drug:       canonical drug name (e.g. "ldn"). None = all drugs.
    condition:  condition name substring match (e.g. "POTS"). None = all.
    sex:        sex/gender value (e.g. "female"). None = all.
    age_bucket: decade bucket (e.g. "30s"). None = all.

    Returns
    -------
    list[dict] with keys:
        drug, n_reports, pct_positive, pct_negative, pct_mixed, pct_neutral,
        avg_sentiment, avg_signal
    """
    params: list = []
    where_clauses: list[str] = []

    if drug:
        where_clauses.append("t.canonical_name = ? COLLATE NOCASE")
        params.append(drug)

    if condition:
        where_clauses.append(
            "EXISTS ("
            "  SELECT 1 FROM conditions c"
            "  WHERE c.user_id = tr.user_id"
            "  AND LOWER(c.condition_name) LIKE LOWER(?)"
            ")"
        )
        params.append(f"%{condition}%")

    if sex:
        where_clauses.append(
            "EXISTS ("
            "  SELECT 1 FROM user_profiles up"
            "  WHERE up.user_id = tr.user_id"
            "  AND LOWER(up.sex) = LOWER(?)"
            ")"
        )
        params.append(sex)

    if age_bucket:
        where_clauses.append(
            "EXISTS ("
            "  SELECT 1 FROM user_profiles up"
            "  WHERE up.user_id = tr.user_id"
            "  AND up.age_bucket = ?"
            ")"
        )
        params.append(age_bucket)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    sql = f"""
        SELECT
            t.canonical_name                                           AS drug,
            COUNT(*)                                                   AS n_reports,
            ROUND(100.0 * SUM(CASE WHEN tr.sentiment > 0.7 THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                                       AS pct_positive,
            ROUND(100.0 * SUM(CASE WHEN tr.sentiment < -0.7 THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                                       AS pct_negative,
            ROUND(100.0 * SUM(CASE WHEN tr.sentiment BETWEEN 0.1 AND 0.7 THEN 1 ELSE 0 END)
                  / COUNT(*), 1)                                        AS pct_mixed,
            ROUND(100.0 * SUM(CASE WHEN tr.sentiment = 0.0 THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                                       AS pct_neutral,
            ROUND(AVG(tr.sentiment), 3)                                AS avg_sentiment,
            ROUND(AVG(tr.signal_strength), 3)                         AS avg_signal
        FROM treatment_reports tr
        JOIN treatment t ON t.id = tr.drug_id
        {where_sql}
        GROUP BY t.canonical_name
        ORDER BY n_reports DESC, avg_sentiment DESC
    """
    cols = ["drug", "n_reports", "pct_positive", "pct_negative",
            "pct_mixed", "pct_neutral", "avg_sentiment", "avg_signal"]
    rows = conn.execute(sql, params).fetchall()
    return [dict(zip(cols, row)) for row in rows]


def list_drugs(conn: sqlite3.Connection) -> list[str]:
    """Return all canonical drug names that have at least one sentiment report."""
    rows = conn.execute(
        "SELECT DISTINCT t.canonical_name FROM treatment t"
        " JOIN treatment_reports tr ON tr.drug_id = t.id"
        " ORDER BY t.canonical_name"
    ).fetchall()
    return [r[0] for r in rows]


def list_conditions(conn: sqlite3.Connection) -> list[str]:
    """Return all distinct condition names in the database."""
    rows = conn.execute(
        "SELECT DISTINCT condition_name FROM conditions ORDER BY condition_name"
    ).fetchall()
    return [r[0] for r in rows]


# ── Discovery merge ────────────────────────────────────────────────────────────

def merge_selected(
    validated_fields: list[dict],
    selected_names: set[str],
    schema_path: Path,
) -> dict:
    """
    Merge selected validated fields into a schema JSON file.

    Only fields whose ``field_name`` is in ``selected_names`` are written.
    Each selected field is inserted (or overwritten) in the schema's
    ``extension_fields`` dict.

    Parameters
    ----------
    validated_fields:
        List of validated candidate dicts (Phase 2 pipeline output).
    selected_names:
        Set of field_name strings to keep.
    schema_path:
        Path to the schema JSON file to update in-place.

    Returns
    -------
    The updated schema dict (also written to disk).
    """
    import datetime

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    extension_fields: dict = schema.setdefault("extension_fields", {})

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    for field in validated_fields:
        name = field.get("field_name", "")
        if name not in selected_names:
            continue
        extension_fields[name] = {
            "description":            field.get("description", ""),
            "confidence":             field.get("confidence", "medium"),
            "source":                 field.get("source", "llm_discovered"),
            "_discovered_at":         now,
            "hit_rate_at_discovery":  field.get("hit_rate", 0.0),
            "coverage":               field.get("coverage"),
            "frequency_hint":         field.get("frequency_hint", "occasional"),
            "research_value":         field.get("research_value", ""),
            "patterns":               field.get("patterns", []),
            "llm_only":               field.get("llm_only", False),
            "extractability_note":    field.get("extractability_note", ""),
            "allowed_values":         field.get("allowed_values"),
            "trigger_vocabulary":     field.get("trigger_vocabulary", []),
        }

    schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    return schema
