"""An unresolvable subreddit must stop the import, not silently drop users.

`users.source_subreddit` is NOT NULL and users are written with INSERT OR IGNORE, so a user row
carrying sub=None fails the constraint and is discarded without an error — while the post keeps a
user_id pointing at a row that was never created. Same silent discard as the [deleted]-author
case, reached by a different route: a post URL with no '/r/' segment and no --subreddit argument.
"""
import json
import sqlite3
from pathlib import Path

import pytest

from import_posts import import_reddit_posts

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"

FIXTURE = [{
    "post_id": "t3_nosub",
    "title": "no subreddit in this url",
    "body": "text",
    "author_hash": "u_someone",
    "created_utc": "2026-01-01T00:00:00+00:00",
    "flair": None,
    "url": "https://reddit.com/comments/nosub",   # no '/r/' segment
    "comments": [],
}]


@pytest.fixture
def posts_json(tmp_path):
    path = tmp_path / "posts.json"
    path.write_text(json.dumps(FIXTURE), encoding="utf-8")
    return path


def test_import_refuses_when_the_subreddit_cannot_be_resolved(tmp_path, posts_json):
    conn = sqlite3.connect(tmp_path / "t.db")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="no resolvable subreddit"):
        import_reddit_posts(conn, posts_json)   # no subreddit= argument


def test_the_explicit_subreddit_argument_rescues_the_same_file(tmp_path, posts_json):
    conn = sqlite3.connect(tmp_path / "t.db")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    import_reddit_posts(conn, posts_json, subreddit="covidlonghaulers")
    assert conn.execute(
        "SELECT source_subreddit FROM users WHERE user_id='u_someone'"
    ).fetchone() == ("covidlonghaulers",)
