"""Posts by [deleted] accounts must survive import, not vanish.

The scraper sets author_hash=None when Reddit reports the account as [deleted]. posts.user_id was
NOT NULL and the importer uses INSERT OR IGNORE, so those rows failed the constraint and were
silently discarded — body text and all. Worse, dropping a [deleted] parent comment orphaned its
surviving replies, whose parent_id then looked dangling and got nulled, severing the thread.

The text is retained now with user_id NULL; per-user aggregation filters it out explicitly.
"""
import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"


def _db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    return conn


def test_posts_user_id_is_nullable():
    conn = _db()
    notnull = {row[1]: row[3] for row in conn.execute("PRAGMA table_info(posts)")}
    assert notnull["user_id"] == 0, "posts.user_id must be nullable to retain [deleted]-author text"
    conn.close()


def test_deleted_author_row_survives_insert_or_ignore():
    """The exact regression: OR IGNORE used to swallow the NOT NULL violation and drop the row."""
    conn = _db()
    conn.execute("INSERT OR IGNORE INTO users VALUES ('u1', 'covidlonghaulers', 0)")
    rows = [
        ("t3_a", None, "u1", "kept - has author", 0),
        ("t3_b", None, None, "kept - [deleted] author, text preserved", 0),
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO posts (post_id, parent_id, user_id, body_text, scraped_at) "
        "VALUES (?, ?, ?, ?, ?)", rows)
    bodies = {r[0] for r in conn.execute("SELECT body_text FROM posts")}
    assert len(bodies) == 2, "the [deleted]-author row was dropped"
    assert any("preserved" in b for b in bodies)
    conn.close()


def test_reply_to_a_deleted_author_keeps_its_thread_link():
    """A surviving [deleted] parent keeps replies attached, so coreference still resolves."""
    conn = _db()
    conn.execute("INSERT OR IGNORE INTO users VALUES ('u1', 'covidlonghaulers', 0)")
    conn.executemany(
        "INSERT OR IGNORE INTO posts (post_id, parent_id, user_id, body_text, scraped_at) "
        "VALUES (?, ?, ?, ?, ?)",
        [("t3_root", None, None, "deleted author, still here", 0),
         ("t1_kid", "t3_root", "u1", "reply that needs its parent for context", 0)])
    # the dangling-parent cleanup must NOT sever this link, because the parent now exists
    conn.execute("UPDATE posts SET parent_id = NULL "
                 "WHERE parent_id IS NOT NULL AND parent_id NOT IN (SELECT post_id FROM posts)")
    parent = conn.execute("SELECT parent_id FROM posts WHERE post_id='t1_kid'").fetchone()[0]
    assert parent == "t3_root", "reply was orphaned by the deleted-author parent being dropped"
    conn.close()


def test_per_user_aggregation_excludes_unattributed_rows():
    conn = _db()
    conn.execute("INSERT OR IGNORE INTO users VALUES ('u1', 'covidlonghaulers', 0)")
    conn.executemany(
        "INSERT OR IGNORE INTO posts (post_id, parent_id, user_id, body_text, scraped_at) "
        "VALUES (?, ?, ?, ?, ?)",
        [("t3_a", None, "u1", "attributed", 0), ("t3_b", None, None, "unattributed", 0)])
    total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    attributed = conn.execute(
        "SELECT COUNT(*) FROM posts WHERE user_id IS NOT NULL").fetchone()[0]
    assert (total, attributed) == (2, 1)
    conn.close()
