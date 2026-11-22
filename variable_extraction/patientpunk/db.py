"""
patientpunk.db
~~~~~~~~~~~~~~
SQLite ETL and query layer.

Loads output from both pipelines into a shared database keyed on author_hash,
then exposes a single query function for treatment outcome analysis.

Schema design
-------------
* ``variables`` is the **canonical EAV** store for extracted fields (one row per
  author_hash × field × run).  Prefer querying / loading into this table when
  you need flexible, sparse, multi-run variable data.
* ``unified`` is a **derived wide table** built by ``load_db.build_unified`` for
  clustering / notebook convenience (one row per record with pivoted columns).
  It is not the source of truth — regenerate it from ``variables`` + related
  tables after new loads.

Usage:
    from patientpunk.db import init_db, load_extractions, load_variables
    from patientpunk.db import query_treatment_outcomes

    conn = init_db(Path("patientpunk.db"))            # over a copy of posts.db
    run_id = load_extractions(conn, Path("output/records.csv"))
    load_variables(conn, Path("output/records.csv"), run_id)
    rows = query_treatment_outcomes(conn, drug="ldn", condition="POTS")

Drug sentiment (treatment / treatment_reports, with TEXT sentiment values) is
written directly to the database by src/run_sentiment_pipeline.py; this module
reads it for queries but no longer ingests a separate sentiment-cache file.
"""

from __future__ import annotations

import csv
import json
import re
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

# Columns in records.csv that are metadata, not extracted variables.
# Mirrors export_csv.META_COLUMNS (+ source_type for the
# demographics CSV).  Used by load_variables to decide which columns are data.
VARIABLE_META_COLUMNS: set[str] = {
    "author_hash", "source", "source_type", "post_id", "text_count",
    "subreddits", "schema_id", "extraction_method", "extracted_at",
}

# records.csv demographic columns that no longer feed profiles or derived tables;
# demographics come only from user_profiles_latest.
LEGACY_DEMOGRAPHIC_COLUMNS: set[str] = {
    "age", "sex_gender", "location_country", "location_state", "location_us_state",
}


# ── Database setup ─────────────────────────────────────────────────────────────

def init_db(db_path: Path, schema_sql: Path | None = None) -> sqlite3.Connection:
    """
    Create (or open) the SQLite database and apply schema.sql.

    If the tables already exist this is a no-op -- safe to call repeatedly.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn, schema_sql)
    return conn


def apply_schema(conn: sqlite3.Connection, schema_sql: Path | None = None) -> None:
    """Apply schema.sql to an open connection, creating only what is missing."""
    if schema_sql is None:
        schema_sql = Path(__file__).parent.parent.parent / "schema.sql"
    ddl = schema_sql.read_text(encoding="utf-8")
    # Wrap in IF NOT EXISTS so it's idempotent
    ddl_idempotent = ddl.replace(
        "CREATE TABLE ", "CREATE TABLE IF NOT EXISTS "
    ).replace(
        "CREATE INDEX ", "CREATE INDEX IF NOT EXISTS "
    )
    conn.executescript(ddl_idempotent)
    # A column added to a table after databases with that table existed: CREATE TABLE IF NOT EXISTS skips it.
    if "age" not in {row[1] for row in conn.execute("PRAGMA table_info(user_profiles)")}:
        conn.execute("ALTER TABLE user_profiles ADD COLUMN age INTEGER")
    conn.commit()


def register_run(
    conn: sqlite3.Connection,
    extraction_type: str,
    config: dict,
    commit_hash: str = "unknown",
) -> int:
    """Insert an extraction_runs row and return its run_id.

    Columns match schema.sql (run_at, commit_hash, extraction_type, config),
    mirroring src/utilities/db.py's ReportWriter so both pipelines record run
    provenance the same way.  (The previous version inserted a nonexistent
    ``model`` column.)
    """
    cur = conn.execute(
        "INSERT INTO extraction_runs (run_at, commit_hash, extraction_type, config)"
        " VALUES (?, ?, ?, ?)",
        (int(time.time()), commit_hash, extraction_type, json.dumps(config)),
    )
    conn.commit()
    return cur.lastrowid


# ── ETL: Shaun's pipeline ──────────────────────────────────────────────────────

def load_extractions(
    conn: sqlite3.Connection,
    csv_path: Path,
    run_id: int | None = None,
) -> int:
    """
    Load the ``conditions`` column of records.csv into the conditions table.

    Demographic columns are ignored: user_profiles is written only by
    src/extract_demographics_conditions.py.

    Returns the run_id used (creates one if not supplied).
    """
    if run_id is None:
        run_id = register_run(conn, "extraction_pipeline", {"source": str(csv_path)})

    with open(csv_path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    # post_ids valid for the conditions FK; per-patient/aggregated records carry
    # synthetic post_ids (e.g. "agg_<hash>") absent from posts -> NULL those.
    valid_posts = {r[0] for r in conn.execute("SELECT post_id FROM posts")}
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

        # Self/other for conditions is enforced upstream (LLM prompts +
        # title/body-only collectors). Pipe-separated multi values are
        # legitimate (one patient, several conditions); skip empty/duplicate tokens.
        conditions_raw = (row.get("conditions") or "").strip()
        post_id = (row.get("post_id") or "").strip() or None
        if post_id is not None and post_id not in valid_posts:
            post_id = None  # synthetic/aggregated id -> no FK target
        if conditions_raw:
            seen_conditions: set[str] = set()
            for condition_name in conditions_raw.split(" | "):
                condition_name = condition_name.strip().lower()
                if not condition_name or condition_name in seen_conditions:
                    continue
                seen_conditions.add(condition_name)
                conn.execute(
                    "INSERT INTO conditions"
                    " (run_id, user_id, post_id, condition_type, condition_name)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (run_id, author_hash, post_id, "illness", condition_name),
                )

    conn.commit()
    return run_id


def load_variables(
    conn: sqlite3.Connection,
    csv_path: Path,
    run_id: int,
    skip_columns: set[str] | None = None,
) -> int:
    """Load every extracted variable column from records.csv into the EAV
    ``variables`` table -- one row per non-empty, non-metadata cell.

    Unlike :func:`load_extractions` (conditions only), this preserves every
    column -- including the inductively-discovered variables -- except the
    legacy demographic columns, so the wide records.csv is queryable inside the
    unified database.

    Returns the number of EAV rows inserted.
    """
    skip = VARIABLE_META_COLUMNS | LEGACY_DEMOGRAPHIC_COLUMNS
    if skip_columns:
        skip |= set(skip_columns)

    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        value_cols = [
            c for c in fieldnames
            if c not in skip
            and not c.endswith("__confidence")
        ]
        inserted = 0
        for row in reader:
            author_hash = (row.get("author_hash") or "").strip()
            if not author_hash:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, source_subreddit, scraped_at)"
                " VALUES (?, ?, ?)",
                (author_hash, "covidlonghaulers", int(time.time())),
            )
            post_id = (row.get("post_id") or "").strip() or None
            for col in value_cols:
                value = (row.get(col) or "").strip()
                if not value:
                    continue
                conn.execute(
                    "INSERT INTO variables (run_id, user_id, post_id, field, value)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (run_id, author_hash, post_id, col, value),
                )
                inserted += 1

    conn.commit()
    return inserted


def _bucketize_age(raw: str | None) -> str | None:
    """Convert a raw age string to a decade bucket like '30s'.

    Handles plain ages ("34" -> "30s") and decade strings including qualitative
    forms ("20s", "30s", "mid-30s", "early 40s", "late 20s" -> "20s"/"30s"/"40s").
    Multi-value strings (e.g. "8 | 22 | 37") from user-history extraction are
    rejected -- they contain ages of OTHER people, not the author.
    Returns None for missing/empty/unparseable input.
    """
    if not raw:
        return None
    raw = raw.strip().lower()
    if not raw or "|" in raw:
        return None
    # Decade strings: "20s", "30s", "mid-30s", "early 40s", "late 20s", ...
    m = re.search(r"(\d{1,3})\s*s\b", raw)
    if m:
        decade = (int(m.group(1)) // 10) * 10
        return f"{decade}s" if 10 <= decade <= 110 else None
    # Plain numeric age: "34", "34.0"
    try:
        age = int(float(raw))
    except (ValueError, TypeError):
        return None
    if age < 10 or age > 110:
        return None  # implausible age
    return f"{(age // 10) * 10}s"


def latest_profiles(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    """Each user's current profile from user_profiles_latest: {user_id: {age, age_bucket, sex, location}},
    as strings, "" where empty. ``age`` is also "" on a database whose schema predates that column."""
    cursor = conn.execute("SELECT * FROM user_profiles_latest")
    columns = [d[0] for d in cursor.description]
    profiles = {}
    for values in cursor:
        row = dict(zip(columns, values))
        profiles[row["user_id"]] = {
            k: "" if row.get(k) is None else str(row[k]) for k in ("age", "age_bucket", "sex", "location")}
    return profiles


# ── Query ──────────────────────────────────────────────────────────────────────

def query_treatment_outcomes(
    conn: sqlite3.Connection,
    drug: str | None = None,
    condition: str | None = None,
    sex: str | None = None,
    age_bucket: str | None = None,
) -> list[dict]:
    """
    Return treatment outcome statistics, excluding n/a signals, optionally filtered by cohort.

    Parameters
    ----------
    drug:       canonical drug name (e.g. "ldn"). None = all drugs.
    condition:  condition name substring match (e.g. "POTS"). None = all.
    sex:        sex/gender value (e.g. "female"). None = all.
    age_bucket: decade bucket (e.g. "30s"). None = all.

    sex and age_bucket match each user's current profile (user_profiles_latest).

    Returns
    -------
    list[dict] with keys:
        drug, n_reports, pct_positive, pct_negative, pct_mixed, pct_neutral,
        avg_sentiment, avg_signal
    """
    params: list = []
    where_clauses: list[str] = ["tr.signal_strength != 'n/a'"]

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
            "  SELECT 1 FROM user_profiles_latest up"
            "  WHERE up.user_id = tr.user_id"
            "  AND LOWER(up.sex) = LOWER(?)"
            ")"
        )
        params.append(sex)

    if age_bucket:
        where_clauses.append(
            "EXISTS ("
            "  SELECT 1 FROM user_profiles_latest up"
            "  WHERE up.user_id = tr.user_id"
            "  AND up.age_bucket = ?"
            ")"
        )
        params.append(age_bucket)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # Sentiment / signal are stored as TEXT (positive/negative/mixed/neutral,
    # strong/moderate/weak/n/a) by src/run_sentiment_pipeline.py.  Build the
    # numeric avg_* expressions from the shared score maps.
    sent_case = "CASE tr.sentiment " + " ".join(
        f"WHEN '{k}' THEN {v}" for k, v in _SENTIMENT_SCORE.items()
    ) + " ELSE NULL END"
    sig_case = "CASE tr.signal_strength " + " ".join(
        f"WHEN '{k}' THEN {v}" for k, v in _SIGNAL_SCORE.items()
    ) + " ELSE NULL END"

    sql = f"""
        SELECT
            t.canonical_name                                           AS drug,
            COUNT(*)                                                   AS n_reports,
            ROUND(100.0 * SUM(CASE WHEN tr.sentiment = 'positive' THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                                       AS pct_positive,
            ROUND(100.0 * SUM(CASE WHEN tr.sentiment = 'negative' THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                                       AS pct_negative,
            ROUND(100.0 * SUM(CASE WHEN tr.sentiment = 'mixed' THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                                       AS pct_mixed,
            ROUND(100.0 * SUM(CASE WHEN tr.sentiment = 'neutral' THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                                       AS pct_neutral,
            ROUND(AVG({sent_case}), 3)                                 AS avg_sentiment,
            ROUND(AVG({sig_case}), 3)                                  AS avg_signal
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
