"""Thread structure has to survive import. No API calls.

This tests to see if the comments pointer to the parent post survives import.  
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from import_posts import align_parent_id, import_reddit_posts  # noqa: E402


@pytest.fixture(params=[True, False], ids=["prefixed-ids", "bare-ids"])
def imported(request, tmp_path):
    """Import one post and two comments -- a reply to the post, and a reply to that
    reply -- under either id convention.

    Yields {label: (parent_id as stored, whether it joins to a real row)}, keyed by
    the comment's logical name so both conventions assert identically.
    """
    ident = ((lambda kind, name: f"{kind}_{name}") if request.param
             else (lambda kind, name: name))
    corpus = [{
        "author_hash": "a" * 64, "post_id": ident("t3", "aaa"), "title": "t", "body": "b",
        "url": "https://reddit.com/r/cfs/x", "created_utc": "2026-01-01T00:00:00Z",
        "comments": [
            {"author_hash": "b" * 64, "comment_id": ident("t1", "c1"), "parent_id": "t3_aaa",
             "body": "reply to post", "created_utc": "2026-01-01T01:00:00Z"},
            {"author_hash": "c" * 64, "comment_id": ident("t1", "c2"), "parent_id": "t1_c1",
             "body": "reply to comment", "created_utc": "2026-01-01T02:00:00Z"},
        ]}]
    src = tmp_path / "subreddit_posts.json"
    src.write_text(json.dumps(corpus), encoding="utf-8")
    conn = sqlite3.connect(tmp_path / "posts.db")
    conn.executescript((REPO_ROOT / "schema.sql").read_text(encoding="utf-8"))
    # schema.sql sets PRAGMA foreign_keys = ON, but that is per-connection and
    # production loads the schema through the sqlite3 CLI, then imports over a
    # separate connection where it defaults to OFF. Match that, or a bad
    # parent_id raises at INSERT here while production silently nulls it.
    conn.execute("PRAGMA foreign_keys = OFF")
    import_reddit_posts(conn, src, subreddit="cfs")

    rows = {}
    for label in ("c1", "c2"):
        row = conn.execute(
            "SELECT parent_id, EXISTS(SELECT 1 FROM posts p WHERE p.post_id = c.parent_id)"
            "  FROM posts c WHERE c.post_id = ?", (ident("t1", label),)).fetchone()
        if row is not None:
            rows[label] = (row[0], bool(row[1]))
    return rows


def test_every_comment_keeps_a_parent_that_resolves(imported):
    """Fails on main under prefixed ids: a stripped parent cannot match an unstripped
    post_id, so the dangling-parent cleanup nulls every one of them.

    A surviving parent_id is worth nothing if it does not join, so both halves are
    checked -- a fix that guessed t3_ where it should have guessed t1_ would satisfy
    the first and fail the second.
    """
    assert sorted(imported) == ["c1", "c2"], "a comment did not import at all"

    dropped = sorted(c for c, (parent, _) in imported.items() if parent is None)
    dangling = sorted(c for c, (parent, joins) in imported.items() if parent and not joins)

    assert not dropped, f"import dropped the parent of: {dropped}"
    assert not dangling, f"parent_id set but joins to no row: {dangling}"


def test_a_bare_parent_against_prefixed_ids_is_dropped_not_mangled():
    """t1_ vs t3_ cannot be reconstructed, so a bare parent is unrepairable --
    better a null than an id that silently joins to the wrong row."""
    assert align_parent_id("aaa", ids_prefixed=True) is None
    assert align_parent_id("t3_aaa", ids_prefixed=True) == "t3_aaa"
    assert align_parent_id("t3_aaa", ids_prefixed=False) == "aaa"
    assert align_parent_id(None, ids_prefixed=True) is None
