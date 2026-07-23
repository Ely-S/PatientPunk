"""The integrity checker must never report success for something it did not examine.

It is meant to gate a run, so the dangerous failure is not a crash — it is exiting 0 while
having checked nothing. Both cases here did exactly that:

  - a '#' in a filename truncated the interpolated URI, which discarded `mode=ro` along with
    it; SQLite then CREATED a stray empty file and the script reported "no pipeline databases
    found" for a database that had 118k rows. A read-only tool writing to disk, reporting clean.
  - a mistyped or non-file path raised FileNotFoundError out of argument handling.

Both were found by the grok-4.5 and gemini-3.1-pro review panels, independently.
"""
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_db_integrity.py"
SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"


def run(*paths) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, paths)],
                          capture_output=True, text=True)


@pytest.fixture
def pipeline_db(tmp_path):
    """A valid pipeline database whose filename contains a URI metacharacter."""
    path = tmp_path / "corpus#1.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO users VALUES ('u', 'test', 0)")
    conn.execute("INSERT INTO posts (post_id, user_id, body_text, scraped_at) "
                 "VALUES ('t3_a', 'u', 'x', 0)")
    conn.commit()
    conn.close()
    return path


def test_a_hash_in_the_filename_does_not_hide_the_database(pipeline_db):
    result = run(pipeline_db)
    assert "no pipeline databases found" not in result.stdout.lower()
    assert "corpus#1.db" in result.stdout
    assert result.returncode == 0


def test_it_does_not_create_a_database_at_the_truncated_path(pipeline_db):
    """The precise regression: '#' ended the URI, so `mode=ro` was dropped and SQLite opened —
    and therefore created — a fresh database at everything before the '#'.

    Sidecars of the intended file (-wal, -shm) are normal SQLite bookkeeping, not writes to
    the data, so they are allowed; a file at the truncated path is the bug.
    """
    truncated = pipeline_db.parent / pipeline_db.name.split("#")[0]
    before = set(pipeline_db.parent.iterdir())
    run(pipeline_db)
    assert not truncated.exists(), f"checker created a database at {truncated.name}"
    created = {path for path in pipeline_db.parent.iterdir()} - before
    assert all(path.name.startswith(pipeline_db.name) for path in created), \
        f"checker created unrelated files: {[path.name for path in created]}"


def test_an_unreadable_path_fails_loudly_instead_of_passing(tmp_path):
    result = run(tmp_path / "does_not_exist.db")
    assert result.returncode != 0, "a path it could not read must not exit 0"
    assert "could not be read" in result.stdout


def test_a_directory_argument_is_reported_not_crashed(tmp_path):
    result = run(tmp_path)
    assert result.returncode != 0
    assert "Traceback" not in result.stderr


def test_a_relative_path_is_inspected_not_crashed(pipeline_db, monkeypatch):
    """`data/corpus.db` is how anyone would actually invoke this.

    Path.as_uri() refuses a relative path, so the URI fix from the previous round raised
    ValueError straight out of argument handling. Raised by the grok-4.5 panel.
    """
    monkeypatch.chdir(pipeline_db.parent)
    result = run(Path(pipeline_db.name))
    assert "Traceback" not in result.stderr
    assert result.returncode == 0, result.stdout + result.stderr
    assert pipeline_db.name in result.stdout
