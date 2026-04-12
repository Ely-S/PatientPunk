#!/usr/bin/env python3
"""
Transform Arctic Shift bulk download files into subreddit_posts.json.

Arctic Shift's download tool produces two separate NDJSON files:
  - posts file: one JSON object per line, each a Reddit submission
  - comments file: one JSON object per line, each a Reddit comment

This script:
  1. Reads both files (supports .zst compressed or plain .jsonl/.ndjson)
  2. Groups comments under their parent posts via link_id
  3. Hashes all usernames (SHA-256) for privacy
  4. Outputs subreddit_posts.json in the same format as scrape_corpus.py

Usage:
    python transform_arctic_shift.py --posts posts.ndjson --comments comments.ndjson
    python transform_arctic_shift.py --posts posts.zst --comments comments.zst
    python transform_arctic_shift.py --posts posts.ndjson --comments comments.ndjson --output data/subreddit_posts.json

The output is compatible with both pipelines (Shaun's variable_extraction
and Polina's src/run_pipeline.py).
"""

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def hash_username(username: str) -> str:
    """SHA-256 hash of username for privacy."""
    return hashlib.sha256(username.encode()).hexdigest()


def utc_iso(ts) -> str:
    """Convert a value to ISO 8601 UTC string."""
    if isinstance(ts, str):
        return ts
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return ""


def open_ndjson(path: Path):
    """Yield JSON objects from an NDJSON file. Supports .zst compression."""
    if path.suffix == ".zst":
        try:
            import zstandard as zstd
        except ImportError:
            sys.exit("zstandard package required for .zst files: pip install zstandard")
        with open(path, "rb") as fh:
            dctx = zstd.ZstdDecompressor()
            with dctx.stream_reader(fh) as reader:
                import io
                text_stream = io.TextIOWrapper(reader, encoding="utf-8")
                for line in text_stream:
                    line = line.strip()
                    if line:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            continue
    else:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue


def build_comment(c: dict) -> dict:
    """Transform an Arctic Shift comment into our format."""
    author = c.get("author")
    author_hash = hash_username(author) if author and author != "[deleted]" else None
    return {
        "comment_id": f"t1_{c.get('id', '')}",
        "body": c.get("body", ""),
        "author_hash": author_hash,
        "created_utc": utc_iso(c.get("created_utc", "")),
        "score": c.get("score", 0),
        "parent_id": c.get("parent_id", ""),
    }


def build_post(p: dict, comments: list[dict]) -> dict:
    """Transform an Arctic Shift post into our format."""
    author = p.get("author")
    author_hash = hash_username(author) if author and author != "[deleted]" else None
    return {
        "post_id": f"t3_{p.get('id', '')}",
        "title": p.get("title", ""),
        "body": p.get("selftext", ""),
        "author_hash": author_hash,
        "created_utc": utc_iso(p.get("created_utc", "")),
        "score": p.get("score", 0),
        "num_comments_api": p.get("num_comments", 0),
        "comments_fetched": len(comments),
        "url": f"https://reddit.com{p.get('permalink', '')}",
        "flair": p.get("link_flair_text"),
        "comments": comments,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Transform Arctic Shift bulk downloads into subreddit_posts.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python transform_arctic_shift.py --posts posts.ndjson --comments comments.ndjson
  python transform_arctic_shift.py --posts posts.zst --comments comments.zst
  python transform_arctic_shift.py --posts posts.ndjson --comments comments.ndjson --output 6mo.json
        """,
    )
    parser.add_argument("--posts", required=True, type=Path, help="Path to posts NDJSON file (.ndjson, .jsonl, or .zst)")
    parser.add_argument("--comments", required=True, type=Path, help="Path to comments NDJSON file (.ndjson, .jsonl, or .zst)")
    parser.add_argument("--output", type=Path, default=Path("data/subreddit_posts.json"), help="Output path (default: data/subreddit_posts.json)")
    parser.add_argument("--subreddit", default="covidlonghaulers", help="Subreddit name for filtering (default: covidlonghaulers)")
    args = parser.parse_args()

    print(f"Reading posts from {args.posts}...")
    posts_by_id: dict[str, dict] = {}
    post_count = 0
    for p in open_ndjson(args.posts):
        # Filter to subreddit if specified
        sub = (p.get("subreddit") or "").lower()
        if args.subreddit and sub != args.subreddit.lower():
            continue
        post_id = p.get("id", "")
        posts_by_id[post_id] = p
        post_count += 1
        if post_count % 5000 == 0:
            print(f"  {post_count} posts read...")
    print(f"  {post_count} posts loaded.")

    print(f"\nReading comments from {args.comments}...")
    comments_by_post: dict[str, list[dict]] = defaultdict(list)
    comment_count = 0
    skipped = 0
    for c in open_ndjson(args.comments):
        # link_id is "t3_<post_id>" — extract the post_id
        link_id = c.get("link_id", "")
        if link_id.startswith("t3_"):
            post_id = link_id[3:]
        else:
            post_id = link_id

        # Only keep comments for posts we have
        if post_id in posts_by_id:
            comments_by_post[post_id].append(build_comment(c))
            comment_count += 1
        else:
            skipped += 1

        if (comment_count + skipped) % 50000 == 0:
            print(f"  {comment_count} comments matched, {skipped} skipped...")
    print(f"  {comment_count} comments matched to posts, {skipped} skipped (no matching post).")

    # Deduplicate posts by (author, title) — same logic as scrape_corpus.py
    print(f"\nBuilding output...")
    seen_keys: set[tuple] = set()
    output: list[dict] = []
    duplicates = 0

    for post_id, p in sorted(posts_by_id.items(), key=lambda x: x[1].get("created_utc", 0)):
        author = (p.get("author") or "").lower()
        title = (p.get("title") or "").strip().lower()
        dedup_key = (author, title)
        if dedup_key in seen_keys and author:
            duplicates += 1
            continue
        seen_keys.add(dedup_key)

        # Sort comments by created_utc
        post_comments = comments_by_post.get(post_id, [])
        post_comments.sort(key=lambda c: c.get("created_utc", ""))

        output.append(build_post(p, post_comments))

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total_comments = sum(p["comments_fetched"] for p in output)
    deleted_authors = sum(1 for p in output if p["author_hash"] is None)

    print(f"\n{'=' * 60}")
    print(f"  Done!")
    print(f"  Posts:              {len(output)}")
    print(f"  Duplicates skipped: {duplicates}")
    print(f"  Total comments:     {total_comments}")
    print(f"  Deleted authors:    {deleted_authors}")
    if output:
        print(f"  Date range:         {output[0]['created_utc'][:10]} to {output[-1]['created_utc'][:10]}")
    print(f"  Output:             {args.output}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
