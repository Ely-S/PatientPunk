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


def _import(tmp_path, prefixed: bool):
    """One post and two comments: a reply to the post, and a reply to that reply."""
    p = (lambda kind, i: f"{kind}_{i}") if prefixed else (lambda kind, i: i)
    corpus = [{
        "author_hash": "a" * 64, "post_id": p("t3", "aaa"), "title": "t", "body": "b",
        "url": "https://reddit.com/r/cfs/x", "created_utc": "2026-01-01T00:00:00Z",
        "comments": [
            {"author_hash": "b" * 64, "comment_id": p("t1", "c1"), "parent_id": "t3_aaa",
             "body": "reply to post", "created_utc": "2026-01-01T01:00:00Z"},
            {"author_hash": "c" * 64, "comment_id": p("t1", "c2"), "parent_id": "t1_c1",
             "body": "reply to comment", "created_utc": "2026-01-01T02:00:00Z"},
        ]}]
    src = tmp_path / "subreddit_posts.json"
    src.write_text(json.dumps(corpus), encoding="utf-8")
    conn = sqlite3.connect(tmp_path / "posts.db")
    conn.executescript((REPO_ROOT / "schema.sql").read_text(encoding="utf-8"))
    import_reddit_posts(conn, src, subreddit="cfs")
    return conn


@pytest.mark.parametrize("prefixed", [True, False], ids=["prefixed-ids", "bare-ids"])
def test_every_comment_keeps_a_parent_that_resolves(tmp_path, prefixed):
    """Fails on main for prefixed ids: all parents null. A surviving parent_id is
    worth nothing if it does not join, so both halves are asserted together."""
    conn = _import(tmp_path, prefixed)
    kept, orphaned = conn.execute(
        "SELECT (SELECT COUNT(*) FROM posts WHERE parent_id IS NOT NULL),"
        "       (SELECT COUNT(*) FROM posts c WHERE c.parent_id IS NOT NULL"
        "         AND NOT EXISTS (SELECT 1 FROM posts p WHERE p.post_id = c.parent_id))"
    ).fetchone()
    assert (kept, orphaned) == (2, 0)


def test_a_bare_parent_against_prefixed_ids_is_dropped_not_mangled():
    """t1_ vs t3_ cannot be reconstructed, so a bare parent is unrepairable --
    better a null than an id that silently joins to the wrong row."""
    assert align_parent_id("aaa", ids_prefixed=True) is None
    assert align_parent_id("t3_aaa", ids_prefixed=True) == "t3_aaa"
    assert align_parent_id("t3_aaa", ids_prefixed=False) == "aaa"
    assert align_parent_id(None, ids_prefixed=True) is None
