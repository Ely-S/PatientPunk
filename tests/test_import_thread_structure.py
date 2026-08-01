"""Thread structure has to survive import. No API calls.

Comment.parent_id arrives as `t1_<id>` / `t3_<id>`. Whether the corpus's own
post_id / comment_id carry that prefix depends on the producer, and stripping
unconditionally leaves a bare parent that never matches a prefixed post_id --
so the dangling-parent cleanup nulls all of them. Nothing downstream errors; the
upstream drug context and the "Replying to:" block simply come back empty.
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from import_posts import align_parent_id, import_reddit_posts  # noqa: E402

SCHEMA_SQL = REPO_ROOT / "schema.sql"


def _corpus(prefixed: bool):
    """Two posts, three comments, one of them a reply to another comment."""
    p = (lambda kind, i: f"{kind}_{i}") if prefixed else (lambda kind, i: i)
    return [
        {"author_hash": "a" * 64, "post_id": p("t3", "aaa"), "title": "t", "body": "b",
         "url": "https://reddit.com/r/cfs/x", "created_utc": "2026-01-01T00:00:00Z",
         "comments": [
             {"author_hash": "b" * 64, "comment_id": p("t1", "c1"),
              "parent_id": "t3_aaa", "body": "reply to post",
              "created_utc": "2026-01-01T01:00:00Z"},
             {"author_hash": "c" * 64, "comment_id": p("t1", "c2"),
              "parent_id": "t1_c1", "body": "reply to comment",
              "created_utc": "2026-01-01T02:00:00Z"},
         ]},
        {"author_hash": "d" * 64, "post_id": p("t3", "bbb"), "title": "t2", "body": "b2",
         "url": "https://reddit.com/r/cfs/y", "created_utc": "2026-01-02T00:00:00Z",
         "comments": [
             {"author_hash": "e" * 64, "comment_id": p("t1", "c3"),
              "parent_id": "t3_bbb", "body": "another",
              "created_utc": "2026-01-02T01:00:00Z"},
         ]},
    ]


def _import(tmp_path, corpus):
    src = tmp_path / "subreddit_posts.json"
    src.write_text(json.dumps(corpus), encoding="utf-8")
    db = tmp_path / "posts.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
    import_reddit_posts(conn, src, subreddit="cfs")
    return conn


@pytest.mark.parametrize("prefixed", [True, False], ids=["prefixed-ids", "bare-ids"])
def test_every_comment_keeps_its_parent(tmp_path, prefixed):
    """Both corpus conventions must survive -- db_to_corpus and the Arctic Shift
    scrapers emit prefixed ids; older hand-built corpora stored them bare."""
    conn = _import(tmp_path, _corpus(prefixed))
    kept = conn.execute(
        "SELECT COUNT(*) FROM posts WHERE parent_id IS NOT NULL").fetchone()[0]
    assert kept == 3, "all three comments should still point at their parent"


@pytest.mark.parametrize("prefixed", [True, False], ids=["prefixed-ids", "bare-ids"])
def test_the_parent_actually_resolves(tmp_path, prefixed):
    """A surviving parent_id is worth nothing if it does not join to a real row."""
    conn = _import(tmp_path, _corpus(prefixed))
    orphaned = conn.execute(
        "SELECT COUNT(*) FROM posts c WHERE c.parent_id IS NOT NULL"
        " AND NOT EXISTS (SELECT 1 FROM posts p WHERE p.post_id = c.parent_id)"
    ).fetchone()[0]
    assert orphaned == 0


def test_a_comment_reply_chain_is_walkable(tmp_path):
    """Upstream context walks comment->comment, not just comment->post, so the
    two-hop case is the one --max-upstream-depth 2 exists for."""
    conn = _import(tmp_path, _corpus(prefixed=True))
    row = conn.execute(
        "SELECT p.post_id FROM posts c JOIN posts p ON p.post_id = c.parent_id"
        " WHERE c.post_id = 't1_c2'").fetchone()
    assert row is not None and row[0] == "t1_c1"


def test_a_bare_parent_against_prefixed_ids_is_dropped_not_mangled():
    """t1_ vs t3_ cannot be reconstructed, so a bare parent is unrepairable --
    better a null than an id that silently joins to the wrong row."""
    assert align_parent_id("aaa", ids_prefixed=True) is None
    assert align_parent_id("t3_aaa", ids_prefixed=True) == "t3_aaa"
    assert align_parent_id("t3_aaa", ids_prefixed=False) == "aaa"
    assert align_parent_id(None, ids_prefixed=True) is None
