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


def extract_subreddit(url: str | None) -> str | None:
    """Recover the subreddit from a post URL, or None when the URL can't supply it."""
    if url and "/r/" in url:
        return url.split("/r/")[1].split("/")[0]
    return None


def _post_ids_already_imported(conn: sqlite3.Connection, candidates: set[str]) -> set[str]:
    """Of these ids, which does the database already hold?

    Chunked because SQLite caps host parameters per statement (999 on older builds), and a large
    pull can present far more candidate parents than that in one file.
    """
    ids = list(candidates)
    found: set[str] = set()
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        found |= {row[0] for row in conn.execute(
            f"SELECT post_id FROM posts WHERE post_id IN ({','.join('?' * len(chunk))})", chunk)}
    return found


def import_reddit_posts(conn: sqlite3.Connection, input_path: Path, subreddit: str | None = None) -> None:
    """Import subreddit_posts.json into users + posts tables."""
    data = json.loads(input_path.read_text(encoding="utf-8"))
    now = int(datetime.now(timezone.utc).timestamp())

    users: list[UserRow] = []
    posts: list[PostRow] = []
    seen_users: set[str] = set()

    def add_user(author: str | None, sub: str | None) -> None:
        # author is falsy (None, or "" from a non-scraper source) when Reddit reports the account
        # as [deleted]. There is no user row to create, but the post itself must still be imported
        # — see the user_id note in schema.sql. Guarding on truthiness keeps an empty string from
        # being written as a real user, which would contradict the schema and the tests.
        if not author:
            return
        if author not in seen_users:
            seen_users.add(author)
            users.append(UserRow(author, sub, now))

    unattributed = []   # post_ids whose subreddit could not be determined
    for post in data:
        author = post.get("author_hash") or None   # "" / missing -> NULL, same as [deleted]
        sub = subreddit or extract_subreddit(post.get("url"))
        if sub is None:
            unattributed.append(post["post_id"])

        add_user(author, sub)
        posts.append(PostRow(
            post_id=post["post_id"], title=post.get("title"), parent_id=None,
            user_id=author, body_text=post.get("body") or "",
            flair=post.get("flair"), post_date=to_epoch(post.get("created_utc")),
            scraped_at=now,
        ))
        for comment in post.get("comments", []):
            c_author = comment.get("author_hash") or None
            add_user(c_author, sub)
            posts.append(PostRow(
                post_id=comment["comment_id"], title=None,
                parent_id=comment.get("parent_id") or None,   # resolved against known ids below
                user_id=c_author,
                body_text=comment.get("body", ""), flair=None,
                post_date=to_epoch(comment.get("created_utc")), scraped_at=now,
            ))

    # users.source_subreddit is NOT NULL and users are written with INSERT OR IGNORE, so a user
    # carrying an unresolved subreddit is dropped without an error — and the post keeps a user_id
    # pointing at a row that was never created. That is the same silent discard as the [deleted]
    # author case, reached by a different route, so refuse the import instead of half-doing it.
    if unattributed:
        sample = ", ".join(unattributed[:3])
        raise ValueError(
            f"{len(unattributed)} of {len(data)} posts have no resolvable subreddit "
            f"(e.g. {sample}). Their URLs carry no '/r/' segment, so the users on those posts "
            f"would be silently dropped. Pass --subreddit to attribute them explicitly."
        )

    # Resolve each parent against the ids we actually hold. Reddit always sends parent_id
    # prefixed ("t3_abc"), but whether post_id / comment_id are STORED prefixed depends on the
    # source: the Arctic Shift scraper writes "t3_abc"/"t1_abc", while older exports store them
    # bare. Stripping unconditionally matched the bare shape and silently broke the prefixed one —
    # every parent then looked dangling, the cleanup below nulled all of them, and thread structure
    # vanished. That is the defect that left parent_id NULL across 731k rows and made judgement 6
    # structurally inert. Matching against the ids actually present handles both shapes.
    known_ids = {p.post_id for p in posts}
    # A parent imported by an EARLIER run lives in the database, not in this file. Resolving only
    # against the file would null those links, severing every thread that spans two imports —
    # exactly how a corpus pulled in chunks loses its structure, and indistinguishable afterwards
    # from the id-shape bug above. Ask the database about the ids this file cannot account for.
    unmatched = {row.parent_id for row in posts if row.parent_id} - known_ids
    known_ids |= _post_ids_already_imported(
        conn, unmatched | {strip_reddit_prefix(pid) for pid in unmatched})

    resolved = dangling = 0
    for i, row in enumerate(posts):
        if row.parent_id is None:
            continue
        bare = strip_reddit_prefix(row.parent_id)
        match = row.parent_id if row.parent_id in known_ids else (bare if bare in known_ids else None)
        posts[i] = row._replace(parent_id=match)
        resolved += match is not None
        dangling += match is None
    if resolved + dangling:
        log.info(f"Thread links: {resolved} resolved, {dangling} dangling "
                 f"({dangling / (resolved + dangling):.1%} — parents outside the pull window).")
        if resolved == 0:
            raise ValueError(
                f"EVERY parent_id is dangling ({dangling} of them). That is the id-shape mismatch "
                "that destroys thread structure and makes coreference inert. Refusing to write a "
                "corpus with no thread links — the message used to be a log line that callers "
                "missed while the import wrote anyway. (A comments-only export whose parents all "
                "sit outside the pull window looks identical; re-export including the parents.)"
            )

    with conn:
        # posts.parent_id references posts(post_id), and SQLite checks foreign keys per-row by
        # default — so a reply appearing before the comment it answers is rejected outright
        # (INSERT OR IGNORE does NOT suppress foreign-key errors; ON CONFLICT never applies to
        # them). Nothing guarantees Reddit lists a thread parent-first. Deferring moves the check
        # to COMMIT, so order within this transaction stops mattering while a genuinely dangling
        # parent still fails. The pragma resets at every COMMIT, so it belongs here rather than in
        # open_db, where it would silently cover only the first transaction.
        conn.execute("PRAGMA defer_foreign_keys = ON")
        conn.executemany(
            "INSERT OR IGNORE INTO users (user_id, source_subreddit, scraped_at) VALUES (?, ?, ?)",
            users,
        )
        conn.executemany(
            "INSERT OR IGNORE INTO posts (post_id, title, parent_id, user_id, body_text, flair, post_date, scraped_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            posts,
        )
        # INSERT OR IGNORE leaves an already-present row exactly as it was, so re-importing over
        # a database written before the id-shape fix repairs nothing — while the log above happily
        # reports those links as resolved. A repair that silently does nothing is worse than one
        # that refuses. Write the links we resolved onto rows that are still missing them; a
        # genuine top-level post has no resolved parent, so it is never touched.
        repaired = conn.executemany(
            "UPDATE posts SET parent_id = ? WHERE post_id = ? AND parent_id IS NULL",
            [(row.parent_id, row.post_id) for row in posts if row.parent_id],
        ).rowcount

        # Clean dangling parent_ids in SQL
        conn.execute(
            "UPDATE posts SET parent_id = NULL "
            "WHERE parent_id IS NOT NULL AND parent_id NOT IN (SELECT post_id FROM posts)"
        )
    if repaired:
        log.info(f"Repaired {repaired} thread links on rows that were already imported.")

    n = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    log.info(f"Imported {len(users)} users, {n} posts/comments.")

    # Deleted accounts leave text we can still analyse but cannot attribute to a patient. Report
    # the share so it is disclosed up front rather than discovered as a shortfall later — these
    # rows are silently absent from every per-user aggregation.
    orphaned = conn.execute("SELECT COUNT(*) FROM posts WHERE user_id IS NULL").fetchone()[0]
    if orphaned:
        log.warning(f"{orphaned} of {n} rows ({orphaned / n:.1%}) have no author ([deleted] "
                    f"account). Text is retained; they are excluded from per-user aggregation.")


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
