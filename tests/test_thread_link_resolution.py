"""Thread links must survive import whichever id shape the source uses.

Reddit always sends comment.parent_id prefixed ("t3_abc"). Whether post_id / comment_id are
STORED prefixed depends on the source: the Arctic Shift scraper writes "t3_abc"/"t1_abc", older
exports store them bare. The importer used to strip the prefix from parent_id unconditionally,
which matched the bare shape and silently broke the prefixed one — every parent then looked
dangling, the cleanup nulled all of them, and thread structure vanished.

That is the defect that left parent_id NULL across 731,526 rows and made judgement 6 structurally
inert, and it was invisible in normal operation because nothing enforced the reference.

These drive the real open_db, so they follow production's foreign-key setting rather than pinning
one — an earlier version asserted FKs were OFF "to mirror production", which quietly became a lie
the moment open_db started enforcing them.
"""
import json
import sqlite3
from pathlib import Path

import pytest

from import_posts import import_reddit_posts
from utilities.db import open_db

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

    conn = open_db(db)   # the connection production actually uses
    import_reddit_posts(conn, src, subreddit="covidlonghaulers")

    parent = conn.execute("SELECT parent_id FROM posts WHERE post_id=?", (comment_id,)).fetchone()[0]
    conn.close()
    assert parent == post_id, f"thread link severed for {label}"


def test_a_reply_listed_before_its_parent_still_imports(tmp_path):
    """Nothing guarantees Reddit lists a thread parent-first.

    posts.parent_id is self-referential, SQLite checks foreign keys per row by default, and
    INSERT OR IGNORE does NOT suppress foreign-key errors (ON CONFLICT never applies to them) —
    so a reply inserted ahead of the comment it answers is rejected outright once open_db
    enforces. The importer defers the check to COMMIT so insert order stops mattering.
    """
    fixture = [{
        "post_id": "t3_root", "title": "t", "body": "root", "author_hash": "u1",
        "created_utc": "2026-01-01T00:00:00+00:00", "flair": None,
        "url": "https://reddit.com/r/covidlonghaulers/comments/root",
        "comments": [
            {"comment_id": "t1_child", "body": "replying to the sibling below", "author_hash": "u2",
             "created_utc": "2026-01-03T00:00:00+00:00", "parent_id": "t1_parent"},
            {"comment_id": "t1_parent", "body": "the parent, listed second", "author_hash": "u3",
             "created_utc": "2026-01-02T00:00:00+00:00", "parent_id": "t3_root"},
        ],
    }]
    src = tmp_path / "posts.json"
    src.write_text(json.dumps(fixture), encoding="utf-8")
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.close()

    conn = open_db(db)
    import_reddit_posts(conn, src, subreddit="covidlonghaulers")
    links = dict(conn.execute("SELECT post_id, parent_id FROM posts ORDER BY post_id"))
    conn.close()
    assert links["t1_child"] == "t1_parent", "out-of-order reply lost its link"
    assert links["t1_parent"] == "t3_root"


def test_import_refuses_a_corpus_whose_every_parent_dangles(tmp_path):
    """The all-dangling case used to log 'do not proceed' and then proceed anyway."""
    fixture = [{
        "post_id": "t3_root", "title": "t", "body": "root", "author_hash": "u1",
        "created_utc": "2026-01-01T00:00:00+00:00", "flair": None,
        "url": "https://reddit.com/r/covidlonghaulers/comments/root",
        "comments": [{
            "comment_id": "t1_kid", "body": "orphan", "author_hash": "u2",
            "created_utc": "2026-01-02T00:00:00+00:00",
            "parent_id": "t1_not_in_this_file",
        }],
    }]
    src = tmp_path / "posts.json"
    src.write_text(json.dumps(fixture), encoding="utf-8")
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.close()

    conn = open_db(db)
    with pytest.raises(ValueError, match="EVERY parent_id is dangling"):
        import_reddit_posts(conn, src, subreddit="covidlonghaulers")
    conn.close()


def test_a_parent_imported_by_an_earlier_run_still_resolves(tmp_path):
    """Threads that span two imports must survive — a corpus is often pulled in chunks.

    Parents were resolved only against the ids in the current file, so a reply to a post
    imported earlier looked dangling and had its link nulled. Indistinguishable afterwards from
    the id-shape bug this module exists to fix, and with the all-dangling guard in place a
    chunk of pure replies now fails outright instead. Raised by the gemini-3.1-pro panel.
    """
    def write(name, payload):
        path = tmp_path / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    first = write("first.json", [{
        "post_id": "t3_root", "title": "t", "body": "root", "author_hash": "u1",
        "created_utc": "2026-01-01T00:00:00+00:00", "flair": None,
        "url": "https://reddit.com/r/covidlonghaulers/comments/root", "comments": [],
    }])
    second = write("second.json", [{
        "post_id": "t3_other", "title": "t", "body": "other", "author_hash": "u1",
        "created_utc": "2026-01-01T00:00:00+00:00", "flair": None,
        "url": "https://reddit.com/r/covidlonghaulers/comments/other",
        "comments": [{
            "comment_id": "t1_kid", "body": "reply to a post from the earlier file",
            "author_hash": "u2", "created_utc": "2026-01-02T00:00:00+00:00",
            "parent_id": "t3_root",
        }],
    }])

    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.close()

    conn = open_db(db)
    import_reddit_posts(conn, first, subreddit="covidlonghaulers")
    import_reddit_posts(conn, second, subreddit="covidlonghaulers")
    link = conn.execute("SELECT parent_id FROM posts WHERE post_id='t1_kid'").fetchone()[0]
    conn.close()
    assert link == "t3_root", "thread link severed across incremental imports"


def test_reimporting_repairs_links_an_earlier_buggy_run_nulled(tmp_path):
    """A repair re-import must actually repair, or say it didn't.

    posts are written with INSERT OR IGNORE, which leaves an existing row exactly as it was —
    so re-importing over a database written before the id-shape fix changed nothing while the
    log cheerfully reported the links as resolved. Raised by the grok-4.5 panel; it matters for
    master_gap/posts.db (731,526 rows, 0% linked), where a repair attempt is the obvious move.
    """
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO users VALUES ('u', 'test', 0)")
    conn.execute("INSERT INTO posts (post_id,user_id,body_text,scraped_at) VALUES ('t3_root','u','root',0)")
    # what the old importer left behind: the row survives, its link does not
    conn.execute("INSERT INTO posts (post_id,user_id,parent_id,body_text,scraped_at) "
                 "VALUES ('t1_kid','u',NULL,'kid',0)")
    conn.commit()
    conn.close()

    src = tmp_path / "posts.json"
    src.write_text(json.dumps([{
        "post_id": "t3_root", "title": "t", "body": "root", "author_hash": "u",
        "created_utc": "2026-01-01T00:00:00+00:00", "flair": None,
        "url": "https://reddit.com/r/covidlonghaulers/comments/root",
        "comments": [{"comment_id": "t1_kid", "body": "kid", "author_hash": "u",
                      "created_utc": "2026-01-02T00:00:00+00:00", "parent_id": "t3_root"}],
    }]), encoding="utf-8")

    conn = open_db(db)
    import_reddit_posts(conn, src, subreddit="covidlonghaulers")
    links = dict(conn.execute("SELECT post_id, parent_id FROM posts"))
    conn.close()
    assert links["t1_kid"] == "t3_root", "re-import silently failed to repair the link"
    assert links["t3_root"] is None, "a genuine top-level post must not gain a parent"
