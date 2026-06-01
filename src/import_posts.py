#!/usr/bin/env python3
"""Import Reddit posts JSON into SQLite. This populates the users and posts tables."""
import argparse
import json
import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple


class UserRow(NamedTuple):
    user_id: str
    source_subreddit: str | None
    scraped_at: int


class PostRow(NamedTuple):
    post_id: str
    title: str | None
    parent_id: str | None
    user_id: str
    body_text: str
    flair: str | None
    post_date: int | None
    scraped_at: int

from utilities.db import open_db

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


def strip_reddit_prefix(reddit_id: str | None) -> str | None:
    """Strip Reddit's `t1_` (comment) or `t3_` (submission) kind prefix.

    Reddit's API serializes comment.parent_id as `t1_<id>` (parent is a comment)
    or `t3_<id>` (parent is a submission), but post_id / comment_id themselves
    are stored bare. Without stripping, the `parent_id NOT IN (SELECT post_id)`
    cleanup below treats every prefixed parent_id as dangling and nulls it,
    silently destroying thread structure on import.
    """
    if reddit_id is None:
        return None
    if reddit_id.startswith(("t1_", "t3_")):
        return reddit_id[3:]
    return reddit_id


def extract_subreddit(url: str | None) -> str:
    if url and "/r/" in url:
        return url.split("/r/")[1].split("/")[0]
    return None


def import_reddit_posts(conn: sqlite3.Connection, input_path: Path, subreddit: str | None = None) -> None:
    """Import subreddit_posts.json into users + posts tables."""
    data = json.loads(input_path.read_text(encoding="utf-8"))
    now = int(datetime.now(timezone.utc).timestamp())

    users: list[UserRow] = []
    posts: list[PostRow] = []
    seen_users: set[str] = set()

    def add_user(author: str, sub: str) -> None:
        if author not in seen_users:
            seen_users.add(author)
            users.append(UserRow(author, sub, now))

    for post in data:
        author = post["author_hash"]
        sub = subreddit or extract_subreddit(post.get("url"))

        add_user(author, sub)
        posts.append(PostRow(
            post_id=post["post_id"], title=post.get("title"), parent_id=None,
            user_id=author, body_text=post.get("body") or "",
            flair=post.get("flair"), post_date=to_epoch(post.get("created_utc")),
            scraped_at=now,
        ))
        for comment in post.get("comments", []):
            c_author = comment["author_hash"]
            add_user(c_author, sub)
            posts.append(PostRow(
                post_id=comment["comment_id"], title=None,
                parent_id=strip_reddit_prefix(comment.get("parent_id")),
                user_id=c_author,
                body_text=comment.get("body", ""), flair=None,
                post_date=to_epoch(comment.get("created_utc")), scraped_at=now,
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
