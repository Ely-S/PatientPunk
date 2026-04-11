"""Database helpers for the pipeline.

Thin layer over treatment_reports — handles run logging, lookups,
existence checks, and incremental inserts. Keeps classify_sentiment
free of schema details.
"""
import json
import sqlite3
import time
from pathlib import Path

COMMIT_EVERY = 5  # commit after this many writes


def open_db(db_path: Path) -> sqlite3.Connection:
    """Open a database connection with WAL journal mode.

    All code that touches the database should use this instead of
    sqlite3.connect() directly.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def load_synonyms(db_path: Path) -> dict[str, list[str]]:
    """Load canonical_name -> [aliases] from the treatment table."""
    conn = open_db(db_path)
    rows = conn.execute(
        "SELECT canonical_name, aliases FROM treatment WHERE aliases IS NOT NULL"
    ).fetchall()
    conn.close()
    return {name: json.loads(aliases) for name, aliases in rows}


def upsert_treatments(db_path: Path, drugs: set[str], aliases: dict[str, list[str]] | None = None) -> int:
    """Insert drug names into the treatment table. Returns row count."""
    aliases = aliases or {}
    conn = open_db(db_path)
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO treatment (canonical_name, aliases) VALUES (?, ?)",
            ((drug, json.dumps(aliases[drug]) if drug in aliases else None)
             for drug in sorted(drugs)),
        )
    count = conn.execute("SELECT COUNT(*) FROM treatment").fetchone()[0]
    conn.close()
    return count


class ReportWriter:
    """Incremental writer for treatment_reports.

    Creates an extraction_runs row on init, then batches inserts with
    periodic commits. Use as a context manager.
    """

    def __init__(self, db_path: Path, run_config: dict, commit_hash: str):
        self._conn = open_db(db_path)
        self._pending = 0

        cursor = self._conn.execute(
            "INSERT INTO extraction_runs (run_at, commit_hash, extraction_type, config) "
            "VALUES (?, ?, ?, ?)",
            (int(time.time()), commit_hash, "treatment_sentiment",
             json.dumps(run_config)),
        )
        self.run_id = cursor.lastrowid
        self._conn.commit()

        self._drug_ids = {
            row[0].lower(): row[1]
            for row in self._conn.execute("SELECT canonical_name, id FROM treatment")
        }
        self._existing = {
            (row[0], row[1])
            for row in self._conn.execute("SELECT post_id, drug_id FROM treatment_reports")
        }

    def already_classified(self, post_id: str, drug: str) -> bool:
        drug_id = self._drug_ids.get(drug.lower())
        return drug_id is not None and (post_id, drug_id) in self._existing

    def write_one(
        self, post_id: str, drug: str, author: str, sentiment: str, signal: str,
    ) -> bool:
        """Insert a single result. Returns False if drug is unknown. Auto-commits periodically."""
        drug_id = self._drug_ids.get(drug.lower())
        if drug_id is None:
            return False

        self._conn.execute(
            "INSERT INTO treatment_reports "
            "(run_id, post_id, user_id, drug_id, sentiment, signal_strength) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (self.run_id, post_id, author, drug_id, sentiment, signal),
        )
        self._pending += 1
        if self._pending >= COMMIT_EVERY:
            self._conn.commit()
            self._pending = 0
        return True

    def flush(self):
        """Commit any pending writes."""
        if self._pending > 0:
            self._conn.commit()
            self._pending = 0

    def close(self):
        self.flush()
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
