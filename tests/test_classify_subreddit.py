"""Which community the classification prompt claims the text came from. No API calls."""

import itertools
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from pipeline.classify import _infer_subreddit  # noqa: E402

SCHEMA_SQL = REPO_ROOT / "schema.sql"


_seq = itertools.count()


def _db(tmp_path, users):
    """users: list of (user_id, source_subreddit). Fresh file per call."""
    path = tmp_path / f"posts{next(_seq)}.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.executemany(
        "INSERT INTO users (user_id, source_subreddit, scraped_at) VALUES (?,?,0)", users)
    conn.commit()
    conn.close()
    return path


def test_picks_the_largest_community(tmp_path):
    """Was DISTINCT ... LIMIT 1 with no ORDER BY -- whichever row SQLite handed back."""
    path = _db(tmp_path, [("a", "cfs"), ("b", "covidlonghaulers"),
                          ("c", "covidlonghaulers"), ("d", "covidlonghaulers")])
    assert _infer_subreddit(path) == "covidlonghaulers"


def test_is_stable_across_calls(tmp_path):
    path = _db(tmp_path, [("a", "cfs"), ("b", "pots"), ("c", "lyme")])
    assert len({_infer_subreddit(path) for _ in range(5)}) == 1


def test_blank_values_never_win(tmp_path):
    """schema.sql makes source_subreddit NOT NULL, so the old "from r/None" needed a
    hand-built DB -- but blanks pass the constraint and outnumbering the real value
    was enough to win a bare COUNT."""
    path = _db(tmp_path, [("a", ""), ("b", "  "), ("c", ""), ("d", "pmdd")])
    assert _infer_subreddit(path) == "pmdd"


def test_falls_back_when_no_user_has_one(tmp_path):
    assert _infer_subreddit(_db(tmp_path, [("a", "")])) == "Long COVID"
    assert _infer_subreddit(_db(tmp_path, [])) == "Long COVID"
