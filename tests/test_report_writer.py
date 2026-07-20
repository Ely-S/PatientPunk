"""ReportWriter must persist the provenance fields, not just the sentiment.

Drives the real writer. An earlier version of these tests hand-wrote the INSERT statement and
asserted on it, which exercised SQLite rather than our code — it would have passed even if
write_one dropped a column entirely.

Covers three distinctions the pipeline now depends on:
  - attribution: 'specific' vs 'collective'  (per-drug rates filter on it)
  - drug_source: 'direct' vs 'context'       (coreference-inherited rows are the least validated)
  - side_effects: [] means "looked, found none"; NULL means "not captured"
"""
import sqlite3
from pathlib import Path

import pytest

from utilities.db import ReportWriter

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"


@pytest.fixture
def db(tmp_path):
    """A schema-shaped DB with the one user/post/drug write_one needs to resolve."""
    path = tmp_path / "t.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO users (user_id, source_subreddit, scraped_at) VALUES ('u1', 'clh', 0)")
    conn.execute("INSERT INTO posts (post_id, user_id, body_text, scraped_at) "
                 "VALUES ('p1', 'u1', 'I take LDN', 0)")
    conn.execute("INSERT INTO treatment (id, canonical_name) VALUES (1, 'ldn')")
    conn.commit()
    conn.close()
    return path


def _row(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(
            "SELECT sentiment, signal_strength, attribution, drug_source, side_effects "
            "FROM treatment_reports").fetchone()
    finally:
        conn.close()


def test_persists_attribution_drug_source_and_empty_side_effects(db):
    with ReportWriter(db, run_config={}, commit_hash="test") as writer:
        assert writer.write_one(post_id="p1", drug="ldn", author="u1", sentiment="positive",
                           signal="weak", side_effects=[], attribution="collective",
                           drug_source="context") is not False
    # [] must survive as an empty JSON array, not collapse to NULL
    assert _row(db) == ("positive", "weak", "collective", "context", "[]")


def test_defaults_are_specific_direct_and_null_side_effects(db):
    """A caller that ignores the new fields must behave exactly as before."""
    with ReportWriter(db, run_config={}, commit_hash="test") as writer:
        writer.write_one(post_id="p1", drug="ldn", author="u1", sentiment="neutral", signal="n/a")
    assert _row(db) == ("neutral", "n/a", "specific", "direct", None)


def test_genuine_neutral_is_written(db):
    """The writer gate used to drop signal='n/a' rows; they are data and must reach the DB."""
    with ReportWriter(db, run_config={}, commit_hash="test") as writer:
        writer.write_one(post_id="p1", drug="ldn", author="u1", sentiment="neutral", signal="n/a")
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM treatment_reports").fetchone()[0] == 1
    conn.close()


def test_audit_does_not_claim_a_row_the_writer_refused(tmp_path):
    """status="written" was predicted from the gate, never checked against the write.

    write_one returns False for a drug absent from the treatment table, so the sidecar whose
    entire job is reconciling against the DB over-counted exactly the rows the DB never
    received. Raised by the grok-4.5 review panel.
    """
    import sqlite3
    from pathlib import Path
    from utilities.db import open_db, ReportWriter

    schema = Path(__file__).resolve().parent.parent / "schema.sql"
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.executescript(schema.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO users VALUES ('u', 'test', 0)")
    conn.execute("INSERT INTO posts (post_id,user_id,body_text,scraped_at) VALUES ('p','u','x',0)")
    conn.commit(); conn.close()

    with ReportWriter(db, run_config={}, commit_hash="x") as writer:
        assert writer.write_one("p", "a_drug_never_canonicalised", "u", "positive", "strong") is False

    with open_db(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM treatment_reports").fetchone()[0] == 0
