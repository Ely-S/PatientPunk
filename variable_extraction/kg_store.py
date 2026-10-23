"""SQLite tuple store for extracted claims.

One row per claim, one row per (claim, key, value) fact, plus edges and per-post
status for resumable runs. Written by kg_extract, read by kg_compare.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

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

