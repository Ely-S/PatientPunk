"""A post whose author is [deleted] must still be imported, with a null user_id, no invented user
row, and its thread links to and from it intact.
"""
import json
import sqlite3
from pathlib import Path

import pytest

from import_posts import import_reddit_posts

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"

FIXTURE = [{
    "post_id": "t3_root",
    "title": "Anyone else?",
    "body": "written by an account that has since been deleted",
    "author_hash": None,                      # [deleted] account
    "created_utc": "2026-01-01T00:00:00+00:00",
    "flair": None,
    "url": "https://reddit.com/r/covidlonghaulers/comments/root",
    "comments": [{
        "comment_id": "t1_kid",
        "body": "it helped me too",           # meaningless without its parent for context
        "author_hash": "u_alive",
        "created_utc": "2026-01-02T00:00:00+00:00",
        "parent_id": "t3_root",               # Reddit sends the t3_ prefix
    }],
}]


@pytest.fixture
def conn(tmp_path):
    path = tmp_path / "posts.json"
    path.write_text(json.dumps(FIXTURE), encoding="utf-8")
    c = sqlite3.connect(tmp_path / "t.db")
    c.executescript(SCHEMA.read_text(encoding="utf-8"))
    import_reddit_posts(c, path, subreddit="covidlonghaulers")
    return c


def test_deleted_author_post_is_imported_with_null_user(conn):
    row = conn.execute("SELECT user_id, body_text FROM posts WHERE post_id='t3_root'").fetchone()
    assert row is not None, "the [deleted]-author post was dropped entirely"
    assert row[0] is None
    assert "deleted" in row[1]


def test_reply_keeps_its_thread_link_to_a_deleted_parent(conn):
    """The t3_ prefix is stripped AND the parent survives, so the cleanup can't sever the thread."""
    parent = conn.execute("SELECT parent_id FROM posts WHERE post_id='t1_kid'").fetchone()[0]
    assert parent == "t3_root"


def test_no_user_row_is_invented_for_a_deleted_account(conn):
    users = [row[0] for row in conn.execute("SELECT user_id FROM users")]
    assert users == ["u_alive"]
