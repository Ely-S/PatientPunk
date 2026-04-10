#!/usr/bin/env python3
"""Import Reddit posts JSON into SQLite."""
import argparse
import json
import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from database_scripts.db import open_db

log = logging.getLogger(__name__)


def to_epoch(ts: str | int | None) -> int | None:
    if ts is None:
        return None
    if isinstance(ts, int):
        return ts
    try:
        return int(datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp())
    except (ValueError, TypeError):
        return None


def extract_subreddit(url: str | None) -> str:
    if url and "/r/" in url:
        return url.split("/r/")[1].split("/")[0]
    return "unknown"


def import_reddit_posts(conn: sqlite3.Connection, input_path: Path, subreddit: str | None = None) -> None:
    """Import subreddit_posts.json into users + posts tables."""
    data = json.loads(input_path.read_text())
    now = int(datetime.now(timezone.utc).timestamp())

    users: list[tuple] = []
    posts: list[tuple] = []
    seen_users: set[str] = set()

    def add_user(author: str, sub: str) -> None:
        if author not in seen_users:
            seen_users.add(author)
            users.append((author, sub, now))

    for post in data:
        author = post["author_hash"]
        sub = subreddit or extract_subreddit(post.get("url"))
        add_user(author, sub)
        posts.append((
            post["post_id"], post.get("title"), None, author,
            post.get("body") or "", post.get("flair"),
            to_epoch(post.get("created_utc")), now,
        ))
        for comment in post.get("comments", []):
            c_author = comment["author_hash"]
            add_user(c_author, sub)
            posts.append((
                comment["comment_id"], None, comment.get("parent_id"), c_author,
                comment.get("body", ""), None,
                to_epoch(comment.get("created_utc")), now,
            ))

    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO users (user_id, source_subreddit, scraped_at) VALUES (?, ?, ?)",
            users,
        )
        conn.executemany(
            "INSERT OR IGNORE INTO posts (post_id, title, parent_id, user_id, body_text, flair, post_date, scraped_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            posts,
        )
        # Clean dangling parent_ids in SQL
        conn.execute(
            "UPDATE posts SET parent_id = NULL "
            "WHERE parent_id IS NOT NULL AND parent_id NOT IN (SELECT post_id FROM posts)"
        )

    n = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    log.info(f"Imported {len(users)} users, {n} posts/comments.")


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Import Reddit posts into SQLite")
    parser.add_argument("--reddit-posts", required=True)
    parser.add_argument("--output-db", required=True)
    parser.add_argument("--subreddit")
    args = parser.parse_args()

    with closing(open_db(Path(args.output_db))) as conn:
        import_reddit_posts(conn, Path(args.reddit_posts), args.subreddit)


if __name__ == "__main__":
    main()
