"""Thread links must survive import whichever id shape the source uses.

Reddit always sends comment.parent_id prefixed ("t3_abc"). Whether post_id / comment_id are
STORED prefixed depends on the source: the Arctic Shift scraper writes "t3_abc"/"t1_abc", older
exports store them bare. The importer used to strip the prefix from parent_id unconditionally,
which matched the bare shape and silently broke the prefixed one — every parent then looked
dangling, the cleanup nulled all of them, and thread structure vanished.

That is the defect that left parent_id NULL across 731,526 rows and made judgement 6 structurally
inert. It is invisible in normal operation: PRAGMA foreign_keys is per-connection and open_db
never enables it, so nothing raises — the links just quietly disappear.
"""
import json
import sqlite3
from pathlib import Path

import pytest

from import_posts import import_reddit_posts

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"


@pytest.mark.parametrize("post_id,comment_id,label", [
    ("t3_root", "t1_kid", "prefixed ids (Arctic Shift scraper)"),
    ("root", "kid", "bare ids (older exports)"),
])
def test_reply_keeps_its_parent_link(tmp_path, post_id, comment_id, label):
    fixture = [{
        "post_id": post_id, "title": "t", "body": "root post", "author_hash": "u1",
        "created_utc": "2026-01-01T00:00:00+00:00", "flair": None,
        "url": "https://reddit.com/r/covidlonghaulers/comments/root",
        "comments": [{
            "comment_id": comment_id, "body": "it helped me too", "author_hash": "u2",
            "created_utc": "2026-01-02T00:00:00+00:00",
            "parent_id": "t3_root",          # Reddit always sends this prefixed
        }],
    }]
    src = tmp_path / "posts.json"
    src.write_text(json.dumps(fixture), encoding="utf-8")
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.close()

    # Reopen the way production does: PRAGMA foreign_keys is per-connection and open_db does not
    # set it, so a mismatch cannot raise — it can only silently null the link.
    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 0, "test must mirror production"
    import_reddit_posts(conn, src, subreddit="covidlonghaulers")

    parent = conn.execute("SELECT parent_id FROM posts WHERE post_id=?", (comment_id,)).fetchone()[0]
    conn.close()
    assert parent == post_id, f"thread link severed for {label}"
