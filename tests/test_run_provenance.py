"""Run provenance: what every extraction_runs row records beyond the caller's own config."""
import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

import utilities
import utilities.db as db
from utilities import LLM_PROVIDER, LLM_REASONING_MODE
from utilities.db import ReportWriter

SCHEMA_SQL = Path(__file__).parent.parent / "schema.sql"
OLD_RUNS_DDL = """  -- extraction_runs before finished_at
    DROP TABLE extraction_runs;
    CREATE TABLE extraction_runs (
        run_id INTEGER PRIMARY KEY, run_at INTEGER NOT NULL, commit_hash TEXT NOT NULL,
        extraction_type TEXT NOT NULL, config TEXT NOT NULL);
"""


def _db(path: Path, old_runs_ddl: bool = False) -> Path:
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8") + (OLD_RUNS_DDL if old_runs_ddl else ""))
    return path


def _run(path: Path, run_id: int) -> tuple[dict, int | None]:
    config, finished_at = sqlite3.connect(path).execute(
        "SELECT config, finished_at FROM extraction_runs WHERE run_id = ?", (run_id,)).fetchone()
    return json.loads(config), finished_at


def test_writer_stamps_provenance_and_marks_only_a_finished_run(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "git_is_dirty", lambda: True)
    path = _db(tmp_path / "study.db")
    with ReportWriter(path, {"provider": "caller's", "limit": 3}, "abc123") as writer:
        clean = writer.run_id
    with pytest.raises(RuntimeError), ReportWriter(path, {}, "abc123") as writer:
        raised = writer.run_id
        raise RuntimeError("step failed")
    config, finished_at = _run(path, clean)
    assert (config["git_dirty"], config["reasoning_mode"], config["limit"]) == (True, LLM_REASONING_MODE, 3)
    assert config["provider"] == "caller's" and finished_at is not None  # a caller-set key is kept
    config, finished_at = _run(path, raised)
    assert (config["provider"], finished_at) == (LLM_PROVIDER, None)


def test_older_database_gains_finished_at_once(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "git_is_dirty", lambda: None)  # git unavailable: JSON null, not false
    old = _db(tmp_path / "old.db", old_runs_ddl=True)
    for _ in range(2):  # the second open must not add the column again
        with ReportWriter(old, {}, "unknown") as writer:
            run_id = writer.run_id
    columns = [row[1] for row in sqlite3.connect(old).execute("PRAGMA table_info(extraction_runs)")]
    assert columns == ["run_id", "run_at", "commit_hash", "extraction_type", "config", "finished_at"]
    assert _run(old, run_id)[0]["git_dirty"] is None


def test_git_dirty_counts_tracked_changes_not_untracked_files(tmp_path, monkeypatch):
    monkeypatch.setattr(utilities, "_root_env", tmp_path / ".env")  # git_is_dirty runs in .env's folder

    def git(*args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=tmp_path, check=True, capture_output=True)

    (tmp_path / "tracked.py").write_text("x = 1\n")
    git("init")
    git("add", "tracked.py")
    git("commit", "-m", "init")
    (tmp_path / "scratch.ipynb").write_text("{}")
    assert utilities.git_is_dirty() is False  # an untracked scratch file is not a code change
    (tmp_path / "tracked.py").write_text("x = 2\n")
    assert utilities.git_is_dirty() is True
