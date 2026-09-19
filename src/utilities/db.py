"""Database helpers for the pipeline.

Thin layer over treatment_reports — handles run logging, lookups,
existence checks, and incremental inserts. Keeps classify_sentiment
free of schema details.
"""
import json
import sqlite3
import time
from pathlib import Path

COMMIT_EVERY = 50  # commit after this many writes

# Kept identical to schema.sql so the dose step also works on databases created before the table existed.
REPORT_DOSES_DDL = """
CREATE TABLE IF NOT EXISTS report_doses (
    dose_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES treatment_reports(report_id),
    run_id    INTEGER NOT NULL REFERENCES extraction_runs(run_id),
    ordinal   INTEGER NOT NULL,
    low       REAL NOT NULL,
    high      REAL NOT NULL,
    unit      TEXT,                   -- as the author wrote it (mg, mL, IU, drops, capsules...); NULL for a bare number
    route     TEXT,
    outcome   TEXT CHECK (outcome IN ('positive', 'negative', 'neutral', 'unclear')),
    quote     TEXT
);
CREATE INDEX IF NOT EXISTS idx_rd_report ON report_doses(report_id);
-- Runs append; nothing is deleted. Each report's rows from its most recent dose run:
CREATE VIEW IF NOT EXISTS report_doses_latest AS
    SELECT d.* FROM report_doses d
    WHERE d.run_id = (SELECT MAX(run_id) FROM report_doses WHERE report_id = d.report_id);
"""


def post_text(title: str | None, body_text: str | None, parent_id: str | None) -> str:
    """Reconstruct display text for a post row.

    Top-level posts (parent_id is None) combine title + body; replies use body only.
    """
    if parent_id is None:
        return f"{title or ''} {body_text or ''}".strip()
    return body_text or ""


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
    """Incremental writer for treatment_reports and report_doses.

    Creates an extraction_runs row on init, then batches inserts with
    periodic commits. Use as a context manager. ``extraction_type`` names the
    run: "treatment_sentiment" (default) or "report_doses".
    """

    def __init__(self, db_path: Path, run_config: dict, commit_hash: str,
                 extraction_type: str = "treatment_sentiment"):
        self._conn = open_db(db_path)
        self._conn.executescript(REPORT_DOSES_DDL)
        self._pending = 0

        cursor = self._conn.execute(
            "INSERT INTO extraction_runs (run_at, commit_hash, extraction_type, config) "
            "VALUES (?, ?, ?, ?)",
            (int(time.time()), commit_hash, extraction_type,
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
        side_effects: list[str] | None = None,
    ) -> bool:
        """Insert a single result. Returns False if drug is unknown. Auto-commits periodically."""
        drug_id = self._drug_ids.get(drug.lower())
        if drug_id is None:
            return False

        self._conn.execute(
            "INSERT INTO treatment_reports "
            "(run_id, post_id, user_id, drug_id, sentiment, signal_strength, side_effects) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self.run_id, post_id, author, drug_id, sentiment, signal,
                json.dumps(side_effects) if side_effects else None,
            ),
        )
        self._pending += 1
        if self._pending >= COMMIT_EVERY:
            self._conn.commit()
            self._pending = 0
        return True

    def write_doses(self, report_id: int, doses) -> int:
        """Insert ``doses`` (objects with low, high, unit, route, outcome, quote — e.g.
        pipeline.doses.DoseValue) as this run's rows for an existing treatment report.
        Append only, like treatment_reports: earlier runs' rows stay, and the
        report_doses_latest view returns each report's most recent run. An unknown
        report_id raises ValueError. Returns the number written."""
        if self._conn.execute(
            "SELECT 1 FROM treatment_reports WHERE report_id = ?", (report_id,)
        ).fetchone() is None:
            raise ValueError(f"treatment report {report_id} does not exist")
        self._conn.executemany(
            "INSERT INTO report_doses (report_id, run_id, ordinal, low, high, unit, route, outcome, quote) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (report_id, self.run_id, ordinal, d.low, d.high, d.unit, d.route, d.outcome, d.quote)
                for ordinal, d in enumerate(doses)  # 0-based, like the study's other ordinal columns
            ],
        )
        self._pending += len(doses)  # one per row written, so COMMIT_EVERY means rows here too
        if self._pending >= COMMIT_EVERY:
            self.flush()
        return len(doses)

    def write_effects(self, report_id: int, effects) -> int:
        """Insert ``effects`` (objects with domain, symptom, direction, attribution, quote, dose —
        e.g. pipeline.effects.EffectValue) as this run's rows for an existing treatment report.
        Append only, like report_doses; report_effects_latest returns each report's most recent
        run. An unknown report_id raises ValueError. Returns the number written."""
        if self._conn.execute(
            "SELECT 1 FROM treatment_reports WHERE report_id = ?", (report_id,)
        ).fetchone() is None:
            raise ValueError(f"treatment report {report_id} does not exist")
        self._conn.executemany(
            "INSERT INTO report_effects (report_id, run_id, ordinal, domain, symptom, direction, attribution, quote, dose_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (report_id, self.run_id, ordinal, e.domain, e.symptom, e.direction, e.attribution, e.quote, e.dose)
                for ordinal, e in enumerate(effects)  # 0-based, like report_doses
            ],
        )
        self._pending += len(effects)
        if self._pending >= COMMIT_EVERY:
            self.flush()
        return len(effects)

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
