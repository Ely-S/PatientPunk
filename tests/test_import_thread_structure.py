"""A comment tree has to survive import: every comment ends up under the node it
was posted under, whichever id convention the corpus uses. No API calls.
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from import_posts import align_parent_id, import_reddit_posts  # noqa: E402

# child -> parent. Three deep plus a sibling: --max-upstream-depth 2 walks >1 hop.
TREE = {"c1": "aaa", "c2": "c1", "c3": "c2", "c4": "aaa"}
POST = "aaa"


def _wire(label: str) -> str:
    """Reddit's form, which parent_id uses whatever the producer's own ids look like."""
    return f"{'t3' if label == POST else 't1'}_{label}"


@pytest.fixture(params=[True, False], ids=["prefixed-ids", "bare-ids"])
def imported_tree(request, tmp_path):
    """Import TREE and read the edges back, in the corpus's own labels."""
    ident = _wire if request.param else (lambda label: label)
    src = tmp_path / "subreddit_posts.json"
    src.write_text(json.dumps([{
        "author_hash": "a" * 64, "post_id": ident(POST), "title": "t", "body": "b",
        "url": "https://reddit.com/r/cfs/x", "created_utc": "2026-01-01T00:00:00Z",
        "comments": [
            {"author_hash": "b" * 64, "comment_id": ident(child), "parent_id": _wire(parent),
             "body": f"reply {child}", "created_utc": "2026-01-01T01:00:00Z"}
            for child, parent in TREE.items()
        ]}]), encoding="utf-8")

    conn = sqlite3.connect(tmp_path / "posts.db")
    conn.executescript((REPO_ROOT / "schema.sql").read_text(encoding="utf-8"))
    # PRAGMA foreign_keys is per-connection, and production imports on a fresh
    # connection where it is OFF. With them ON a bad parent_id raises at INSERT
    # instead of reaching the cleanup that nulls it.
    conn.execute("PRAGMA foreign_keys = OFF")
    import_reddit_posts(conn, src, subreddit="cfs")

    label = {ident(l): l for l in (POST, *TREE)}
    rows = conn.execute(
        f"SELECT post_id, parent_id FROM posts WHERE post_id IN ({','.join('?' * len(TREE))})",
        [ident(c) for c in TREE]).fetchall()
    return {label[child]: label.get(parent, parent) for child, parent in rows}


def test_the_comment_tree_survives_import(imported_tree):
    """Catches a parent that survives but points at the wrong node, which counting
    non-null parents does not."""
    assert imported_tree == TREE


def test_a_bare_parent_against_prefixed_ids_is_dropped_not_mangled():
    """A malformed corpus, not a tree that failed to survive: t1_ vs t3_ cannot be
    reconstructed from a bare id, so a null beats a wrong join."""
    assert align_parent_id("aaa", ids_prefixed=True) is None
    assert align_parent_id("t3_aaa", ids_prefixed=True) == "t3_aaa"
    assert align_parent_id("t3_aaa", ids_prefixed=False) == "aaa"
    assert align_parent_id(None, ids_prefixed=True) is None
