#!/usr/bin/env python3
"""
database_utils.py — Import data into SQLite database.

Assumes database was created with schema.sql first:
    sqlite3 data/posts.db < schema.sql

Usage:
    python src/database_scripts/database_utils.py --reddit-posts data/subreddit_posts.json --output-db data/posts.db
    python src/database_scripts/database_utils.py --tagged-mentions outputs/tagged_mentions.json --output-db data/posts.db
    python src/database_scripts/database_utils.py --reddit-posts data/posts.json --tagged-mentions outputs/tagged_mentions.json --output-db data/posts.db
"""
import argparse
import json
import logging
import sqlite3
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import chain
from pathlib import Path
from typing import TypedDict

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


class UserRow(TypedDict):
    user_id: str
    source_subreddit: str
    scraped_at: int


class PostRow(TypedDict):
    post_id: str
    title: str | None
    parent_id: str | None
    user_id: str
    body_text: str
    flair: str | None
    post_date: int | None
    scraped_at: int


class TreatmentRow(TypedDict):
    canonical_name: str
    treatment_class: str | None
    aliases: str | None  # JSON array
    notes: str | None


@dataclass
class ImportStats:
    users: int
    posts: int
    comments: int


def to_epoch(ts: str | int | None) -> int | None:
    """Convert timestamp to Unix epoch seconds. Handles ISO strings or passthrough ints."""
    if ts is None:
        return None
    if isinstance(ts, int):
        return ts
    try:
        return int(datetime.fromisoformat(ts).timestamp())
    except (ValueError, TypeError):
        return None


def extract_subreddit(url: str | None) -> str:
    """Extract subreddit name from a Reddit URL."""
    if url and "/r/" in url:
        return url.split("/r/")[1].split("/")[0]
    return "unknown"


def make_post_row(
    post_id: str,
    body: str,
    user_id: str,
    created_utc: str | int | None,
    now: int,
    title: str | None = None,
    parent_id: str | None = None,
    flair: str | None = None,
) -> PostRow:
    """Create a post row dict."""
    return PostRow(
        post_id=post_id,
        title=title,
        parent_id=parent_id,
        user_id=user_id,
        body_text=body,
        flair=flair,
        post_date=to_epoch(created_utc),
        scraped_at=now,
    )


def load_posts(input_path: Path, subreddit_override: str | None = None) -> tuple[list[UserRow], list[PostRow]]:
    """Load subreddit_posts.json and return (users, posts) rows."""
    data = json.loads(input_path.read_text())
    now = int(datetime.now(timezone.utc).timestamp())

    users: dict[str, UserRow] = {}
    posts: list[PostRow] = []

    def ensure_user(author: str, subreddit: str) -> None:
        if author not in users:
            users[author] = UserRow(user_id=author, source_subreddit=subreddit, scraped_at=now)

    for post in data:
        author = post["author_hash"]
        subreddit = subreddit_override or extract_subreddit(post.get("url"))

        ensure_user(author, subreddit)
        posts.append(make_post_row(
            post_id=post["post_id"],
            body=post.get("body") or "",
            user_id=author,
            created_utc=post.get("created_utc"),
            now=now,
            title=post.get("title"),
            flair=post.get("flair"),
        ))

        for comment in post.get("comments", []):
            comment_author = comment["author_hash"]
            ensure_user(comment_author, subreddit)
            posts.append(make_post_row(
                post_id=comment["comment_id"],
                body=comment.get("body", ""),
                user_id=comment_author,
                created_utc=comment.get("created_utc"),
                now=now,
                parent_id=comment.get("parent_id"),
            ))

    return list(users.values()), posts


def open_db(db_path: Path) -> sqlite3.Connection:
    """Open database connection. Assumes schema.sql was already run."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def import_reddit_posts(conn: sqlite3.Connection, input_path: Path, subreddit: str | None = None) -> ImportStats:
    """Import reddit posts into existing database. Returns import statistics."""
    users, posts = load_posts(input_path, subreddit)

    with conn:  # transaction
        conn.executemany(
            "INSERT OR IGNORE INTO users (user_id, source_subreddit, scraped_at) "
            "VALUES (:user_id, :source_subreddit, :scraped_at)",
            users,
        )
        conn.executemany(
            "INSERT OR IGNORE INTO posts (post_id, title, parent_id, user_id, body_text, flair, post_date, scraped_at) "
            "VALUES (:post_id, :title, :parent_id, :user_id, :body_text, :flair, :post_date, :scraped_at)",
            posts,
        )

    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    post_count = conn.execute("SELECT COUNT(*) FROM posts WHERE parent_id IS NULL").fetchone()[0]
    comment_count = conn.execute("SELECT COUNT(*) FROM posts WHERE parent_id IS NOT NULL").fetchone()[0]

    return ImportStats(users=user_count, posts=post_count, comments=comment_count)


def import_treatments(conn: sqlite3.Connection, tagged_path: Path, canonical_map_path: Path | None = None) -> int:
    """Build treatment table from tagged_mentions.json and optional canonical_map.json.

    Returns the number of treatments inserted.
    """
    tagged: list[dict] = json.loads(tagged_path.read_text())

    # Invert canonical map: canonical_name -> [aliases]
    aliases_for: dict[str, list[str]] = defaultdict(list)
    if canonical_map_path and canonical_map_path.exists():
        for raw, canonical in json.loads(canonical_map_path.read_text()).items():
            if raw != canonical:
                aliases_for[canonical].append(raw)

    # Collect unique non-empty drug names
    all_drugs = {
        drug for entry in tagged
        for drug in chain(entry.get("drugs_direct", []), entry.get("drugs_context", []))
        if drug.strip()
    }

    def make_row(drug: str) -> TreatmentRow:
        aliases = aliases_for.get(drug)
        return TreatmentRow(
            canonical_name=drug,
            treatment_class=None,
            aliases=json.dumps(aliases) if aliases else None,
            notes=None,
        )

    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO treatment (canonical_name, treatment_class, aliases, notes) "
            "VALUES (:canonical_name, :treatment_class, :aliases, :notes)",
            (make_row(drug) for drug in sorted(all_drugs)),
        )

    return conn.execute("SELECT COUNT(*) FROM treatment").fetchone()[0]


def main():
    parser = argparse.ArgumentParser(description="Create SQLite database from JSON sources")
    parser.add_argument("--reddit-posts", help="Path to subreddit_posts.json")
    parser.add_argument("--tagged-mentions", help="Path to tagged_mentions.json (for treatment table)")
    parser.add_argument("--canonical-map", help="Path to canonical_map.json (optional, for treatment aliases)")
    parser.add_argument("--output-db", required=True, help="Path for output .db file")
    parser.add_argument("--subreddit", help="Override subreddit name (default: extracted from URLs)")
    args = parser.parse_args()

    db_path = Path(args.output_db)
    with closing(open_db(db_path)) as conn:
        if args.reddit_posts:
            stats = import_reddit_posts(conn, Path(args.reddit_posts), args.subreddit)
            log.info(f"Imported reddit posts: {stats.users} users, {stats.posts} posts, {stats.comments} comments")

        if args.tagged_mentions:
            canon_path = Path(args.canonical_map) if args.canonical_map else None
            count = import_treatments(conn, Path(args.tagged_mentions), canon_path)
            log.info(f"Imported {count} treatments")

    log.info(f"Wrote {db_path}")


if __name__ == "__main__":
    main()
