"""Private SQLite persistence for second-pass probe runs.

``patientpunk.db`` is an input to a probe, never its output. This store keeps
raw responses, source text, quotes, and hashed author IDs behind the private
``data/probes/`` boundary so they cannot accidentally enter a committed
analysis database.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Iterator

from .models import (
    Attempt,
    AttemptStatus,
    Claim,
    CohortMember,
    ProbeRun,
    Unit,
    UnitStatus,
    Usage,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS probe_run (
    run_id              TEXT PRIMARY KEY,
    probe               TEXT NOT NULL,
    spec_hash           TEXT NOT NULL,
    cohort_hash         TEXT NOT NULL,
    source_fingerprint  TEXT NOT NULL,
    unit_set_hash       TEXT NOT NULL,
    config_json         TEXT NOT NULL,
    created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cohort_member (
    run_id       TEXT NOT NULL REFERENCES probe_run(run_id),
    ordinal      INTEGER NOT NULL,
    author_hash  TEXT NOT NULL,
    target       TEXT,
    PRIMARY KEY (run_id, ordinal)
);

CREATE TABLE IF NOT EXISTS unit (
    run_id          TEXT NOT NULL REFERENCES probe_run(run_id),
    unit_key        TEXT NOT NULL,
    author_hash     TEXT NOT NULL,
    target          TEXT,
    character_count INTEGER NOT NULL CHECK (character_count > 0),
    status          TEXT NOT NULL,
    PRIMARY KEY (run_id, unit_key)
);

CREATE TABLE IF NOT EXISTS source_window (
    run_id          TEXT NOT NULL,
    unit_key        TEXT NOT NULL,
    source_window_id TEXT NOT NULL,
    source_type     TEXT NOT NULL,
    source_id       TEXT NOT NULL,
    text            TEXT NOT NULL,
    text_sha256     TEXT NOT NULL,
    PRIMARY KEY (run_id, unit_key, source_window_id),
    FOREIGN KEY (run_id, unit_key)
        REFERENCES unit(run_id, unit_key)
);

CREATE TABLE IF NOT EXISTS attempt (
    run_id              TEXT NOT NULL,
    unit_key            TEXT NOT NULL,
    attempt_no          INTEGER NOT NULL CHECK (attempt_no > 0),
    status              TEXT NOT NULL,
    response_body       TEXT,
    response_sha256     TEXT,
    cache_key           TEXT,
    usage_json          TEXT,
    cache_hit           INTEGER NOT NULL DEFAULT 0,
    billing_uncertain   INTEGER NOT NULL DEFAULT 0,
    error               TEXT,
    recorded_at         TEXT NOT NULL,
    PRIMARY KEY (run_id, unit_key, attempt_no),
    FOREIGN KEY (run_id, unit_key)
        REFERENCES unit(run_id, unit_key)
);

CREATE TABLE IF NOT EXISTS claim (
    run_id           TEXT NOT NULL,
    claim_id         TEXT NOT NULL,
    unit_key         TEXT NOT NULL,
    source_window_id TEXT NOT NULL,
    included         INTEGER NOT NULL CHECK (included IN (0, 1)),
    values_json      TEXT NOT NULL,
    evidence_json    TEXT NOT NULL,
    PRIMARY KEY (run_id, claim_id),
    FOREIGN KEY (run_id, unit_key, source_window_id)
        REFERENCES source_window(run_id, unit_key, source_window_id)
);

CREATE INDEX IF NOT EXISTS idx_cohort_member_run
    ON cohort_member(run_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_unit_run_status
    ON unit(run_id, status);
CREATE INDEX IF NOT EXISTS idx_source_window_unit
    ON source_window(run_id, unit_key, source_window_id);
CREATE INDEX IF NOT EXISTS idx_attempt_cache_status
    ON attempt(cache_key, status);
CREATE INDEX IF NOT EXISTS idx_claim_lookup
    ON claim(run_id, unit_key, source_window_id, included);
"""


def canonical_json(value: object) -> str:
    """Serialize data consistently before storing or hashing it."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def text_sha256(text: str) -> str:
    """Return the checksum used to detect changed private source text."""

    return sha256(text.encode("utf-8")).hexdigest()


class ProbeStore:
    """Transactional store for one probe's private runs.

    The database path is intentionally probe-scoped rather than global. A
    future public analysis can consume de-quoted aggregates without receiving
    the source text, provider response, or evidence quotes stored here.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    @classmethod
    def default_path(cls, probe: str, root: Path | None = None) -> Path:
        """Return the gitignored default path for a probe database."""

        base = root or Path.cwd()
        return base / "data" / "probes" / f"{probe}.db"

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Commit a group of writes atomically, rolling back on failure."""

        try:
            yield self.connection
        except Exception:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    def close(self) -> None:
        """Close the connection and release SQLite resources."""

        self.connection.close()

    def __enter__(self) -> "ProbeStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def save_probe_run(self, run: ProbeRun) -> None:
        """Insert an immutable run identity; reject accidental replacement."""

        self.connection.execute(
            """
            INSERT INTO probe_run (
                run_id, probe, spec_hash, cohort_hash, source_fingerprint,
                unit_set_hash, config_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.probe,
                run.spec_hash,
                run.cohort_hash,
                run.source_fingerprint,
                run.unit_set_hash,
                canonical_json(run.config.model_dump(mode="json")),
                run.created_at.isoformat(),
            ),
        )
        self.connection.commit()

    def save_cohort_members(
        self, run_id: str, members: list[CohortMember]
    ) -> None:
        """Persist the resolved SQL result in the order the caller supplies."""

        with self.transaction() as connection:
            connection.executemany(
                """
                INSERT INTO cohort_member (run_id, ordinal, author_hash, target)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (run_id, ordinal, member.author_hash, member.target)
                    for ordinal, member in enumerate(members)
                ],
            )

    def save_units(self, run_id: str, units: list[Unit]) -> None:
        """Persist units and their private source windows in one transaction."""

        with self.transaction() as connection:
            for unit in units:
                connection.execute(
                    """
                    INSERT INTO unit (
                        run_id, unit_key, author_hash, target,
                        character_count, status
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        unit.unit_key,
                        unit.author_hash,
                        unit.target,
                        unit.character_count,
                        unit.status.value,
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO source_window (
                        run_id, unit_key, source_window_id, source_type,
                        source_id, text, text_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            run_id,
                            unit.unit_key,
                            window.source_window_id,
                            window.source_type,
                            window.source_id,
                            window.text,
                            text_sha256(window.text),
                        )
                        for window in unit.windows
                    ],
                )

    def set_unit_status(
        self, run_id: str, unit_key: str, status: UnitStatus
    ) -> None:
        """Update one unit lifecycle state without rewriting its inputs."""

        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE unit SET status = ?
                WHERE run_id = ? AND unit_key = ?
                """,
                (status.value, run_id, unit_key),
            )

    def record_attempt(self, run_id: str, attempt: Attempt) -> None:
        """Write a response or transport failure before validating it."""

        usage_json = (
            canonical_json(attempt.usage.model_dump(mode="json"))
            if attempt.usage is not None
            else None
        )
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO attempt (
                    run_id, unit_key, attempt_no, status, response_body,
                    response_sha256, cache_key, usage_json, cache_hit,
                    billing_uncertain, error, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    attempt.unit_key,
                    attempt.attempt_no,
                    attempt.status.value,
                    attempt.response_body,
                    attempt.response_sha256,
                    attempt.cache_key,
                    usage_json,
                    int(attempt.cache_hit),
                    int(attempt.billing_uncertain),
                    attempt.error,
                    attempt.recorded_at.isoformat(),
                ),
            )

    def update_attempt_status(
        self,
        run_id: str,
        unit_key: str,
        attempt_no: int,
        status: AttemptStatus,
        *,
        error: str | None = None,
    ) -> None:
        """Advance a received attempt after validation succeeds or fails."""

        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE attempt SET status = ?, error = COALESCE(?, error)
                WHERE run_id = ? AND unit_key = ? AND attempt_no = ?
                """,
                (status.value, error, run_id, unit_key, attempt_no),
            )

    def cached_attempt(self, cache_key: str) -> Attempt | None:
        """Return the latest accepted response for a request cache key."""

        row = self.connection.execute(
            """
            SELECT unit_key, attempt_no, status, response_body,
                   response_sha256, cache_key, usage_json, cache_hit,
                   billing_uncertain, error, recorded_at
            FROM attempt
            WHERE cache_key = ? AND status = ?
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (cache_key, AttemptStatus.ACCEPTED.value),
        ).fetchone()
        if row is None:
            return None
        usage = Usage.model_validate(json.loads(row["usage_json"])) if row["usage_json"] else None
        return Attempt(
            unit_key=row["unit_key"],
            attempt_no=row["attempt_no"],
            status=AttemptStatus(row["status"]),
            response_body=row["response_body"],
            response_sha256=row["response_sha256"],
            cache_key=row["cache_key"],
            usage=usage,
            cache_hit=bool(row["cache_hit"]),
            billing_uncertain=bool(row["billing_uncertain"]),
            error=row["error"],
            recorded_at=datetime.fromisoformat(row["recorded_at"]),
        )

    def save_claim(self, run_id: str, claim: Claim) -> None:
        """Persist one normalized claim after engine and probe validation."""

        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO claim (
                    run_id, claim_id, unit_key, source_window_id, included,
                    values_json, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    claim.claim_id,
                    claim.unit_key,
                    claim.source_window_id,
                    int(claim.included),
                    canonical_json(claim.values),
                    canonical_json(
                        [anchor.model_dump(mode="json") for anchor in claim.evidence]
                    ),
                ),
            )
