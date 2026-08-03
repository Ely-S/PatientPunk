"""A comment tree has to survive import: every comment ends up under the node it
was posted under, whichever id convention the corpus uses. No API calls.
"""

import json
import logging
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


# A producer can prefix post_ids and comment_ids independently, so all four
# combinations are corpora the importer has to align correctly.
CONVENTIONS = {
    "prefixed-ids": _wire,
    "bare-ids": lambda label: label,
    "bare-posts": lambda label: label if label == POST else _wire(label),
    "bare-comments": lambda label: _wire(label) if label == POST else label,
}


@pytest.fixture(params=list(CONVENTIONS), ids=list(CONVENTIONS))
def imported_tree(request, tmp_path):
    """Import TREE and read the edges back, in the corpus's own labels."""
    ident = CONVENTIONS[request.param]
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


@pytest.mark.parametrize("parents, expected", [
    (["t3_aaa", "t3_outside_the_slice"], "Parent resolved for 1/2 comments (50.0%)"),
    (["t3_outside_the_slice", "t3_also_outside"], "NO comment kept its parent"),
], ids=["a-slice-boundary", "nothing-resolves"])
def test_the_import_reports_the_resolution_rate(tmp_path, caplog, parents, expected):
    """Foreign keys are off, so an unresolved parent is nulled rather than raised,
    and a slice boundary looks exactly like an id-convention bug. Only the rate
    separates them: the bug this branch fixes reads as 0%."""
    src = tmp_path / "subreddit_posts.json"
    src.write_text(json.dumps([{
        "author_hash": "a" * 64, "post_id": "t3_aaa", "title": "t", "body": "b",
        "url": "https://reddit.com/r/cfs/x", "created_utc": "2026-01-01T00:00:00Z",
        "comments": [
            {"author_hash": chr(98 + i) * 64, "comment_id": f"t1_c{i}", "parent_id": parent,
             "body": "r", "created_utc": "2026-01-01T01:00:00Z"}
            for i, parent in enumerate(parents)
        ]}]), encoding="utf-8")
    conn = sqlite3.connect(tmp_path / "posts.db")
    conn.executescript((REPO_ROOT / "schema.sql").read_text(encoding="utf-8"))
    conn.execute("PRAGMA foreign_keys = OFF")

    with caplog.at_level(logging.INFO):
        import_reddit_posts(conn, src, subreddit="cfs")
    assert expected in caplog.text


def test_each_kind_is_aligned_independently():
    """A t3_ parent follows the post convention, a t1_ parent the comment one. One
    global flag cannot express that, and breaks one edge or the other."""
    bare_posts = {"t3": False, "t1": True}
    assert align_parent_id("t3_aaa", bare_posts) == "aaa"
    assert align_parent_id("t1_c1", bare_posts) == "t1_c1"


def test_a_bare_parent_is_dropped_not_mangled():
    """A bare parent names no kind, so against any prefixed ids it is unrepairable --
    a null beats an id that silently joins to the wrong row."""
    all_bare = {"t3": False, "t1": False}
    all_prefixed = {"t3": True, "t1": True}
    assert align_parent_id("aaa", all_prefixed) is None
    assert align_parent_id("aaa", all_bare) == "aaa"
    assert align_parent_id("t3_aaa", all_prefixed) == "t3_aaa"
    assert align_parent_id("t3_aaa", all_bare) == "aaa"
    assert align_parent_id(None, all_prefixed) is None
