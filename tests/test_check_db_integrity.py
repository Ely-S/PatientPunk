"""check_db_integrity.py must read every database it is given and never write to one."""
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(*paths) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "check_db_integrity.py"),
                           *map(str, paths)], capture_output=True, text=True)


def test_it_reports_a_database_without_writing_to_it(tmp_path):
    # A '#' in the name once ended the URI early, dropping mode=ro, so SQLite created an
    # empty "corpus" file and the real database went unchecked.
    db = tmp_path / "corpus#1.db"
    conn = sqlite3.connect(db)
    conn.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
    conn.execute("INSERT INTO users VALUES ('u', 'test', 0)")
    conn.execute("INSERT INTO posts (post_id, user_id, body_text, scraped_at) VALUES ('t3_a', 'u', 'x', 0)")
    conn.commit()
    conn.close()

    result = run(db)
    assert result.returncode == 0 and "corpus#1.db" in result.stdout
    assert not (tmp_path / "corpus").exists()


def test_a_path_it_cannot_read_fails_the_run(tmp_path):
    result = run(tmp_path / "missing.db", tmp_path)
    assert result.returncode == 1
    assert result.stdout.count("could not be read") == 2
