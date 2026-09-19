#!/usr/bin/env python3
"""Import the Twitter treatment dataset into SQLite (users + posts tables).

Twitter analog of import_posts.py. Reads the per-keyword JSON files produced
by the keyword scrape (treatment_wise_tweets/*.json, including
tweets_analysis.json), deduplicates by tweet_id across files, and writes rows
compatible with schema.sql so the drug sentiment pipeline runs unchanged.

Differences from the Reddit importer, by design:
  - parent_id is always NULL: the scrape captured individual tweets with no
    thread structure. Reply-chain features of the pipeline no-op until parents
    are backfilled (see the backfill flag below).
  - user_id is the SHA-256 of the numeric author_id (same hashing convention
    as the Reddit side); the public username is kept in metadata for QA.
  - Records with lang 'qme'/'zxx' (media-only, no parseable text) are dropped.

Usage:
    uv run python src/import_tweets.py \
        --tweets-dir /path/to/treatment_wise_tweets \
        --output-db data/tweets.db
"""
import argparse
import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from utilities.db import open_db

log = logging.getLogger(__name__)

SOURCE = "twitter"
DROP_LANGS = {"qme", "zxx"}


def to_epoch(ts: str | None) -> int | None:
    if not ts:
        return None
    try:
        return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
    except (ValueError, TypeError):
        return None


def ensure_schema(conn: sqlite3.Connection, schema_path: Path) -> None:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='posts'"
    ).fetchone()
    if row is None:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        log.info(f"Applied schema from {schema_path}.")


def import_tweets(conn: sqlite3.Connection, tweets_dir: Path) -> None:
    now = int(datetime.now(timezone.utc).timestamp())
    files = sorted(tweets_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"No .json files found in {tweets_dir}")

    seen: set[str] = set()
    users: dict[str, tuple] = {}
    posts: list[tuple] = []
    dropped_lang = dropped_empty = dupes = 0

    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        for t in data.get("tweets", []):
            tid = t["tweet_id"]
            if tid in seen:
                dupes += 1
                continue
            seen.add(tid)
            if t.get("lang") in DROP_LANGS:
                dropped_lang += 1
                continue
            text = (t.get("text") or "").strip()
            if not text:
                dropped_empty += 1
                continue

            author_hash = hashlib.sha256(str(t["author_id"]).encode()).hexdigest()
            users.setdefault(author_hash, (author_hash, SOURCE, now))
            metadata = {
                "author_username": t.get("author_username"),
                "author_verified": t.get("author_verified"),
                "lang": t.get("lang"),
                "keywords_found": t.get("keywords_found") or [],
                "metrics": t.get("metrics") or {},
                "source_file": f.name,
                "backfilled": False,  # True later for context-only parent rows
            }
            posts.append((
                tid, None, None, author_hash, text, None,
                to_epoch(t.get("created_at")), now, json.dumps(metadata),
            ))

    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO users (user_id, source_subreddit, scraped_at) VALUES (?, ?, ?)",
            list(users.values()),
        )
        conn.executemany(
            "INSERT OR IGNORE INTO posts (post_id, title, parent_id, user_id, body_text, flair, post_date, scraped_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            posts,
        )

    n = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    log.info(
        f"Imported {len(posts)} tweets from {len(files)} files "
        f"({dupes} cross-file duplicates, {dropped_lang} media-only, {dropped_empty} empty skipped). "
        f"{len(users)} users, {n} rows in posts."
    )


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Import Twitter treatment tweets into SQLite")
    parser.add_argument("--tweets-dir", required=True, help="Directory of tweets_*.json files")
    parser.add_argument("--output-db", required=True)
    parser.add_argument("--schema", default=str(Path(__file__).parent.parent / "schema.sql"))
    args = parser.parse_args()

    Path(args.output_db).parent.mkdir(parents=True, exist_ok=True)
    conn = open_db(Path(args.output_db))
    try:
        ensure_schema(conn, Path(args.schema))
        import_tweets(conn, Path(args.tweets_dir))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
