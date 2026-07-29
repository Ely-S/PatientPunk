#!/usr/bin/env python3
"""
Transform a scraped Reddit SQLite database into subreddit_posts.json.

The database holds two flat tables -- ``posts`` and ``comments`` -- joined by
``comments.link_id`` (``t3_<post id>``). The pipeline wants one JSON array of
posts with their comments nested, usernames hashed.

Output matches transform_arctic_shift.py field for field, so both routes into
the pipeline produce the same shape.

Exports every subreddit in the database by default. The unit of analysis is the
patient, and a patient who posts in two communities is still one person, so
splitting the corpus by community would fragment them into partial records.
Which communities a patient wrote in is kept on the record itself as
``subreddits`` counts. Narrow with --subreddit only for a deliberately
single-community run.

Usage:
    python db_to_corpus.py --db reddit.db
    python db_to_corpus.py --db reddit.db --subreddit covidlonghaulers cfs
    python db_to_corpus.py --db reddit.db --since 2024-01-01 --out-dir ../output
    python db_to_corpus.py --db reddit.db --list
"""

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

DELETED = {"[deleted]", "[removed]", "", None}


def hash_username(username: str) -> str:
    return hashlib.sha256(username.encode()).hexdigest()


def author_hash(author) -> str | None:
    """Hash a username, or None for deleted/absent authors.

    Never returns the raw name: it reaches records.csv otherwise, and every
    downstream artifact joins on the hash.
    """
    return None if author in DELETED else hash_username(author)


def utc_iso(ts) -> str:
    if isinstance(ts, str):
        return ts
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return ""


def parse_date(s: str) -> int:
    """Parse YYYY-MM-DD into a UTC epoch second."""
    return int(datetime.strptime(s, "%Y-%m-%d")
               .replace(tzinfo=timezone.utc).timestamp())


def list_subreddits(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT subreddit, COUNT(*) FROM posts GROUP BY 1 ORDER BY 2 DESC")
    print(f"{'subreddit':<28}{'posts':>10}{'comments':>12}")
    counts = dict(conn.execute(
        "SELECT subreddit, COUNT(*) FROM comments GROUP BY 1"))
    for sub, n in rows:
        print(f"{sub:<28}{n:>10,}{counts.get(sub, 0):>12,}")


def build_comment(row: sqlite3.Row) -> dict:
    return {
        "comment_id": f"t1_{row['id']}",
        "body": row["body"] or "",
        "author_hash": author_hash(row["author"]),
        "created_utc": utc_iso(row["created_utc"]),
        "score": row["score"] or 0,
        "parent_id": row["parent_id"] or "",
    }


def build_post(row: sqlite3.Row, comments: list[dict]) -> dict:
    return {
        "post_id": f"t3_{row['id']}",
        "title": row["title"] or "",
        "body": row["selftext"] or "",
        "author_hash": author_hash(row["author"]),
        "created_utc": utc_iso(row["created_utc"]),
        "score": row["score"] or 0,
        "num_comments_api": row["num_comments"] or 0,
        "comments_fetched": len(comments),
        "url": f"https://reddit.com{row['permalink'] or ''}",
        "flair": None,
        "subreddit": row["subreddit"],
        "comments": comments,
    }


def check_writable(out_path: Path, force: bool) -> None:
    """Refuse to overwrite an existing corpus unless asked.

    A symlink is the dangerous case: writing through one replaces whatever it
    points at, and corpus directories accumulate links to other corpora. Give
    each run its own --out-dir instead.
    """
    if not out_path.exists() and not out_path.is_symlink():
        return
    if force:
        return
    what = f"a symlink to {out_path.resolve()}" if out_path.is_symlink() else "a file"
    raise FileExistsError(
        f"{out_path} is already {what}. Give this run its own --out-dir, "
        f"or pass --force to overwrite."
    )


def convert(db: Path, subreddits: list[str] | None, out_path: Path,
            since: int | None, until: int | None) -> dict:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    where: list[str] = []
    args: list = []
    if subreddits:
        where.append(f"subreddit IN ({','.join('?' * len(subreddits))})")
        args.extend(subreddits)
    if since is not None:
        where.append("created_utc >= ?")
        args.append(since)
    if until is not None:
        where.append("created_utc < ?")
        args.append(until)
    clause = " AND ".join(where) if where else "1"

    # Comments first, bucketed by their post, so each post is emitted once.
    by_post: dict[str, list[dict]] = defaultdict(list)
    n_comments = 0
    for row in conn.execute(f"SELECT * FROM comments WHERE {clause}", args):
        by_post[(row["link_id"] or "")[3:]].append(build_comment(row))
        n_comments += 1

    posts = []
    for row in conn.execute(f"SELECT * FROM posts WHERE {clause}", args):
        posts.append(build_post(row, by_post.get(row["id"], [])))

    posts.sort(key=lambda p: p["created_utc"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False)

    orphans = sum(len(v) for k, v in by_post.items()
                  if k not in {p["post_id"][3:] for p in posts})
    per_sub = Counter(p["subreddit"] for p in posts)
    return {
        "per_subreddit": per_sub,
        "posts": len(posts),
        "comments": n_comments,
        "orphan_comments": orphans,
        "authors": len({p["author_hash"] for p in posts if p["author_hash"]}),
        "first": posts[0]["created_utc"][:10] if posts else "-",
        "last": posts[-1]["created_utc"][:10] if posts else "-",
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Transform a scraped Reddit SQLite DB into subreddit_posts.json")
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--subreddit", nargs="+", metavar="NAME",
                    help="Restrict to these subreddits (default: all of them)")
    ap.add_argument("--out-dir", type=Path, default=Path("output"),
                    help="Directory to write subreddit_posts.json into")
    ap.add_argument("--since", help="Only posts/comments on or after YYYY-MM-DD")
    ap.add_argument("--until", help="Only posts/comments before YYYY-MM-DD")
    ap.add_argument("--list", action="store_true",
                    help="List the subreddits in the database and exit")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite an existing subreddit_posts.json")
    a = ap.parse_args()

    if not a.db.exists():
        print(f"No such database: {a.db}", file=sys.stderr)
        return 1
    if a.list:
        list_subreddits(sqlite3.connect(f"file:{a.db}?mode=ro", uri=True))
        return 0

    out = a.out_dir / "subreddit_posts.json"
    try:
        check_writable(out, a.force)
    except FileExistsError as exc:
        print(exc, file=sys.stderr)
        return 1
    stats = convert(a.db, a.subreddit, out,
                    parse_date(a.since) if a.since else None,
                    parse_date(a.until) if a.until else None)
    if not stats["posts"]:
        which = ", ".join(a.subreddit) if a.subreddit else "any subreddit"
        print(f"No posts for {which}. Try --list.", file=sys.stderr)
        return 1

    print(f"  -> {out}")
    for name, n in stats["per_subreddit"].most_common():
        print(f"     r/{name:<26}{n:>9,} posts")
    print(f"  posts             {stats['posts']:,}")
    print(f"  comments          {stats['comments']:,}")
    print(f"  distinct authors  {stats['authors']:,}")
    print(f"  window            {stats['first']} -> {stats['last']}")
    if stats["orphan_comments"]:
        print(f"  orphan comments   {stats['orphan_comments']:,} DROPPED "
              "(their parent post is outside this window, so there is nothing to "
              "nest them under; widen --since/--until to keep them)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
