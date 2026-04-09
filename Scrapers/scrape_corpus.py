#!/usr/bin/env python3
"""Reddit corpus scraper for PatientPunk — via Arctic Shift API.

By default fetches all posts from r/covidlonghaulers in the past 2 months,
with full comment trees, then scrapes the full available history for each
unique post author.

All usernames are SHA-256 hashed before being written to disk.

Usage:
    python scrape_corpus.py                            # last 2 months, posts only
    python scrape_corpus.py --comments                 # posts + comment trees
    python scrape_corpus.py --months 3                 # last 3 months
    python scrape_corpus.py --weeks 6                  # last 6 weeks
    python scrape_corpus.py --comments --user-histories           # posts + comments + histories
    python scrape_corpus.py --comments --user-histories --enrich-profiles  # everything

Arctic Shift API docs: https://github.com/ArthurHeitmann/arctic_shift
Base URL: https://arctic-shift.photon-reddit.com
"""

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

API_BASE = "https://arctic-shift.photon-reddit.com"
REDDIT_USER_AGENT = "patientpunk-scraper/0.1 (corpus research)"
SUBREDDIT = "covidlonghaulers"
REQUEST_DELAY = 1.0       # seconds between Arctic Shift calls
REDDIT_REQUEST_DELAY = 7  # seconds between Reddit calls (~10/min unauthenticated)
OUTPUT_DIR = Path(__file__).parent.parent / "data"
USERS_DIR = OUTPUT_DIR / "users"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def utc_iso(ts: int | float | str) -> str:
    """Convert a value to ISO 8601 UTC string.

    Arctic Shift returns created_utc as an ISO string in most cases but
    sometimes as a unix timestamp (int/float). Handle both.
    """
    if isinstance(ts, str):
        return ts
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def window_start_iso(months: int | None, weeks: int | None) -> tuple[str, str]:
    """Return (ISO timestamp string, human label) for the start of the scrape window.

    Uses Z suffix and no microseconds — Arctic Shift rejects +00:00 offsets.
    """
    if weeks is not None:
        dt = datetime.now(timezone.utc) - timedelta(weeks=weeks)
        label = f"{weeks} week(s)"
    else:
        dt = datetime.now(timezone.utc) - timedelta(days=30 * (months or 2))
        label = f"{months or 2} month(s)"
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), label


def hash_username(username: str) -> str:
    return hashlib.sha256(username.encode()).hexdigest()


def polite_sleep(delay: float = REQUEST_DELAY):
    time.sleep(delay)


def api_get(url: str, params: dict | None = None, headers: dict | None = None,
            max_retries: int = 5) -> dict:
    """GET with exponential backoff on failure."""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"    Request failed ({e}), retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise


def arctic_get(endpoint: str, params: dict) -> dict:
    return api_get(f"{API_BASE}{endpoint}", params=params)


def paginate_all(endpoint: str, base_params: dict, label: str = "") -> list[dict]:
    """Paginate through an Arctic Shift search endpoint using created_utc cursors.

    Returns all matching items sorted ascending by created_utc.
    Stops when a page returns fewer than 100 items (last page) or the
    returned created_utc exceeds the 'before' bound if one is set.
    """
    params = {**base_params, "limit": 100, "sort": "asc"}
    all_items: list[dict] = []
    page = 0

    while True:
        page += 1
        if label:
            print(f"    {label} — page {page} ({len(all_items)} items so far)...")

        data = arctic_get(endpoint, params)
        items = data.get("data", [])
        if not items:
            break

        all_items.extend(items)

        # Advance cursor to just after the last item's timestamp
        last_ts = items[-1].get("created_utc", "")
        if not last_ts:
            break
        params["after"] = last_ts

        # If we got a partial page we've hit the end
        if len(items) < 100:
            break

        polite_sleep()

    return all_items


# ---------------------------------------------------------------------------
# Phase 0: Count posts before downloading
# ---------------------------------------------------------------------------

def count_posts_in_window(subreddit: str, after: str) -> tuple[int, list[dict]]:
    """Paginate through all post stubs (id + created_utc only) to get a count.

    Returns (count, list_of_stubs). The stubs are reused in Phase 1 so we
    don't make a second full-metadata pass.
    """
    print(f"  Counting posts since {after[:10]}...")
    stubs = paginate_all(
        "/api/posts/search",
        {
            "subreddit": subreddit,
            "after": after,
        },
        label="counting",
    )
    return len(stubs), stubs


# ---------------------------------------------------------------------------
# Phase 1: Full post + comment download
# ---------------------------------------------------------------------------

def fetch_full_post(post_id: str) -> dict | None:
    """Fetch full metadata for a single post by ID."""
    data = arctic_get("/api/posts/ids", {"ids": post_id})
    items = data.get("data", [])
    return items[0] if items else None


def fetch_comments_for_post(post_id: str) -> list[dict]:
    """Fetch the full comment tree for a single post via Arctic Shift."""
    raw = paginate_all(
        "/api/comments/search",
        {"link_id": f"t3_{post_id}"},
    )
    return [build_comment(c) for c in raw]


def build_comment(c: dict) -> dict:
    author = c.get("author")
    author_hash = hash_username(author) if author and author != "[deleted]" else None
    return {
        "comment_id": f"t1_{c.get('id', '')}",
        "body": c.get("body", ""),
        "author_hash": author_hash,
        "created_utc": utc_iso(c.get("created_utc", "")),
        "score": c.get("score", 0),
        "parent_id": c.get("parent_id", ""),
        # NOTE: depth from Arctic Shift is always 0 and unreliable.
        # Reconstruct nesting by tracing parent_id chains if needed.
    }


def build_post(p: dict, comments: list[dict] | None = None) -> dict:
    author = p.get("author")
    author_hash = hash_username(author) if author and author != "[deleted]" else None
    comments = comments or []
    return {
        "post_id": f"t3_{p.get('id', '')}",
        "title": p.get("title", ""),
        "body": p.get("selftext", ""),
        "author_hash": author_hash,
        "created_utc": utc_iso(p.get("created_utc", "")),
        "score": p.get("score", 0),
        # num_comments_api is unreliable — often 0 even when comments exist.
        # Use comments_fetched for the actual count.
        "num_comments_api": p.get("num_comments", 0),
        "comments_fetched": len(comments),
        "url": f"https://reddit.com{p.get('permalink', '')}",
        "flair": p.get("link_flair_text"),
        "comments": comments,
    }


# ---------------------------------------------------------------------------
# Phase 2: User history
# ---------------------------------------------------------------------------

def scrape_user_history(username: str, enrich: bool = False) -> dict | None:
    """Scrape a user's full post and comment history from Arctic Shift."""
    author_hash = hash_username(username)

    try:
        user_posts_raw = paginate_all(
            "/api/posts/search",
            {"author": username},
            label="posts",
        )
    except Exception as e:
        print(f"    Failed to fetch posts for {author_hash[:12]}...: {e}")
        return None

    polite_sleep()

    try:
        user_comments_raw = paginate_all(
            "/api/comments/search",
            {"author": username},
            label="comments",
        )
    except Exception as e:
        print(f"    Failed to fetch comments for {author_hash[:12]}...: {e}")
        return None

    posts = [
        {
            "post_id": f"t3_{p.get('id', '')}",
            "subreddit": p.get("subreddit", ""),
            "title": p.get("title", ""),
            "body": p.get("selftext", ""),
            "created_utc": utc_iso(p.get("created_utc", "")),
            "score": p.get("score", 0),
            "num_comments": p.get("num_comments", 0),
        }
        for p in user_posts_raw
    ]

    comments = [
        {
            "comment_id": f"t1_{c.get('id', '')}",
            "subreddit": c.get("subreddit", ""),
            "body": c.get("body", ""),
            "created_utc": utc_iso(c.get("created_utc", "")),
            "score": c.get("score", 0),
            "parent_id": c.get("parent_id", ""),
        }
        for c in user_comments_raw
    ]

    result = {
        "author_hash": author_hash,
        "profile": None,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "posts": posts,
        "comments": comments,
    }

    if enrich:
        print(f"    Fetching Reddit profile...")
        polite_sleep(REDDIT_REQUEST_DELAY)
        profile = fetch_reddit_profile(username)
        result["profile"] = profile
        if not profile:
            print(f"    Profile unavailable (deleted/suspended?)")

    return result


# ---------------------------------------------------------------------------
# Reddit profile enrichment (optional)
# ---------------------------------------------------------------------------

def fetch_reddit_profile(username: str) -> dict | None:
    """Fetch a user's profile from Reddit's public about.json endpoint.

    No API key needed — unauthenticated access (~10 req/min limit).
    """
    url = f"https://www.reddit.com/user/{username}/about.json"
    headers = {"User-Agent": REDDIT_USER_AGENT}
    try:
        data = api_get(url, headers=headers)
    except Exception as e:
        print(f"    Could not fetch Reddit profile: {e}")
        return None

    user_data = data.get("data", {})
    if not user_data:
        return None

    user_sub = user_data.get("subreddit", {})
    return {
        "account_created_utc": utc_iso(user_data.get("created_utc", 0)),
        "link_karma": user_data.get("link_karma", 0),
        "comment_karma": user_data.get("comment_karma", 0),
        "total_karma": user_data.get("total_karma", 0),
        "bio": user_sub.get("public_description", ""),
        "avatar_url": user_data.get("icon_img", ""),
        "snoovatar_url": user_data.get("snoovatar_img", ""),
        "banner_url": user_sub.get("banner_img", ""),
        "is_gold": user_data.get("is_gold", False),
        "is_mod": user_data.get("is_mod", False),
        "verified": user_data.get("verified", False),
        "has_verified_email": user_data.get("has_verified_email", False),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

HELP_TEXT = """
scrape_corpus.py — PatientPunk Reddit Corpus Scraper
=====================================================
Scrapes posts, comments, and author data from r/covidlonghaulers
via the Arctic Shift public API. No Reddit API key required.

FLAGS
-----
Time window (mutually exclusive, default: --months 2):
  --months N          Scrape posts from the last N months
  --weeks N           Scrape posts from the last N weeks

What to collect (combine freely):
  --comments          Fetch full comment trees for every post
  --user-histories    Scrape each post author's full Reddit history
  --enrich-profiles   Fetch Reddit profile data per author (avatar, bio,
                      karma, account age). Requires --user-histories.

Limits:
  --limit-posts N     Stop after downloading N posts (useful for testing).

EXAMPLES
--------
  python scrape_corpus.py                                  # posts only, last 2 months
  python scrape_corpus.py --limit-posts 80                 # first 80 posts, last 2 months
  python scrape_corpus.py --weeks 1 --comments             # quick 1-week sample with comments
  python scrape_corpus.py --months 3 --comments            # 3 months of posts + comments
  python scrape_corpus.py --months 3 --comments \\
      --user-histories                                     # + author histories (~4-6 hrs)
  python scrape_corpus.py --months 3 --comments \\
      --user-histories --enrich-profiles                   # everything (run overnight)

OUTPUT
------
  output/subreddit_posts.json     All posts in window (+ comments if --comments)
  output/users/{hash}.json        One file per author (only with --user-histories)
  output/corpus_metadata.json     Run summary and stats

  All usernames are SHA-256 hashed. Raw usernames are never written to disk.

TIME ESTIMATES (3-month window, ~500 posts, ~400 authors)
----------------------------------------------------------
  Posts only                      ~30-45 min
  + --comments                    ~1-2 hrs
  + --user-histories              +2-4 hrs
  + --enrich-profiles             +~1 hr
  Full run                        4-7 hrs total (run overnight)

For full documentation see SCRAPER_HELP.md
"""


def main():
    parser = argparse.ArgumentParser(
        description="Scrape r/covidlonghaulers corpus via Arctic Shift.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=HELP_TEXT,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--months",
        type=int,
        help="How many months back to scrape (default: 2 if neither --months nor --weeks is passed).",
    )
    group.add_argument(
        "--weeks",
        type=int,
        help="How many weeks back to scrape. Mutually exclusive with --months.",
    )
    parser.add_argument(
        "--comments",
        action="store_true",
        help="Fetch full comment trees for each post. Adds significant time "
             "for high-volume subreddits.",
    )
    parser.add_argument(
        "--user-histories",
        action="store_true",
        help="Scrape each post author's full Reddit history across all subreddits. "
             "Adds 2-4 hours for a typical 3-month window.",
    )
    parser.add_argument(
        "--enrich-profiles",
        action="store_true",
        help="Fetch Reddit profile data (avatar, bio, karma, account age) for each "
             "author. Requires --user-histories. Adds ~7s per user.",
    )
    parser.add_argument(
        "--limit-posts",
        type=int,
        default=None,
        metavar="N",
        help="Stop after downloading N posts. Useful for quick tests without "
             "waiting for the full window to download.",
    )
    args = parser.parse_args()

    if args.enrich_profiles and not args.user_histories:
        parser.error("--enrich-profiles requires --user-histories")
    if args.months is None and args.weeks is None:
        args.months = 2  # default

    OUTPUT_DIR.mkdir(exist_ok=True)
    USERS_DIR.mkdir(exist_ok=True)

    scrape_started = datetime.now(timezone.utc).isoformat()
    after_ts, window_label = window_start_iso(args.months, args.weeks)

    print("=" * 60)
    print(f"  Subreddit : r/{SUBREDDIT}")
    print(f"  Window    : last {window_label} (since {after_ts[:10]})")
    print(f"  Post limit: {args.limit_posts if args.limit_posts else 'none (all)'}")
    print(f"  Comments  : {'yes' if args.comments else 'no'}")
    print(f"  Histories : {'yes' if args.user_histories else 'no'}")
    print(f"  Profiles  : {'yes' if args.enrich_profiles else 'no'}")
    print("=" * 60)

    # -----------------------------------------------------------------------
    # Phase 0: Count posts in window
    # -----------------------------------------------------------------------
    print(f"\n[Phase 0] Measuring posts in window...")
    post_count, post_stubs = count_posts_in_window(SUBREDDIT, after_ts)
    print(f"  Found {post_count} posts to download.")
    if args.limit_posts and args.limit_posts < post_count:
        post_stubs = post_stubs[:args.limit_posts]
        post_count = len(post_stubs)
        print(f"  Limiting to first {post_count} posts (--limit-posts).")
    print()

    # -----------------------------------------------------------------------
    # Phase 1: Download full posts (+ comments if requested)
    # -----------------------------------------------------------------------
    phase1_label = "posts + comments" if args.comments else "posts"
    print(f"[Phase 1] Downloading {post_count} {phase1_label}...")

    unique_authors: dict[str, str] = {}  # username -> hash (in-memory only)
    posts = []
    deleted_post_authors = 0
    duplicate_posts_skipped = 0
    # Dedup key: (author, normalised_title) — catches same author posting same question twice
    seen_post_keys: set[tuple] = set()

    for i, stub in enumerate(post_stubs, 1):
        post_id = stub.get("id", "")
        fetch_label = "fetching post + comments" if args.comments else "fetching post"
        print(f"  Post {i}/{post_count}: t3_{post_id} — {fetch_label}...")

        # Fetch full post metadata
        full_post = fetch_full_post(post_id)
        if full_post is None:
            print(f"    Could not fetch post t3_{post_id}, skipping.")
            continue
        polite_sleep()

        # Deduplicate: skip if same author has already posted the same title
        author = stub.get("author") or ""
        dedup_key = (author.lower(), (full_post.get("title") or "").strip().lower())
        if dedup_key in seen_post_keys and author:
            print(f"    Duplicate post detected (same author + title), skipping.")
            duplicate_posts_skipped += 1
            continue
        seen_post_keys.add(dedup_key)

        # Fetch comments only if flag is set
        comments = fetch_comments_for_post(post_id) if args.comments else []
        post_data = build_post(full_post, comments)
        posts.append(post_data)

        if author and author != "[deleted]":
            unique_authors[author] = post_data["author_hash"]
        else:
            deleted_post_authors += 1

        polite_sleep()

    with open(OUTPUT_DIR / "subreddit_posts.json", "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved {len(posts)} posts to subreddit_posts.json.")

    # -----------------------------------------------------------------------
    # Phase 2: User histories (optional)
    # -----------------------------------------------------------------------
    authors_list = list(unique_authors.items())
    total_authors = len(authors_list)

    authors_scraped = 0
    authors_failed = 0
    total_user_posts = 0
    total_user_comments = 0
    subreddits_seen: set[str] = set()

    if not args.user_histories:
        print(f"\n[Phase 2] Skipping user histories (pass --user-histories to enable).")
    else:
        print(f"\n[Phase 2] {total_authors} unique post authors. Scraping histories...")
        if args.enrich_profiles:
            print(f"  (Profile enrichment adds ~7s per user — est. {total_authors * 7 // 60}m {total_authors * 7 % 60}s extra)\n")

        for i, (username, author_hash) in enumerate(authors_list, 1):
            print(f"  User {i}/{total_authors}: {author_hash[:12]}...")
            user_data = scrape_user_history(username, enrich=args.enrich_profiles)
            if user_data is None:
                authors_failed += 1
                continue

            authors_scraped += 1
            total_user_posts += len(user_data["posts"])
            total_user_comments += len(user_data["comments"])
            for p in user_data["posts"]:
                subreddits_seen.add(p["subreddit"])
            for c in user_data["comments"]:
                subreddits_seen.add(c["subreddit"])

            user_file = USERS_DIR / f"{author_hash}.json"
            with open(user_file, "w", encoding="utf-8") as f:
                json.dump(user_data, f, ensure_ascii=False, indent=2)

            polite_sleep()

    # -----------------------------------------------------------------------
    # Phase 3: Metadata
    # -----------------------------------------------------------------------
    scrape_finished = datetime.now(timezone.utc).isoformat()
    metadata = {
        "subreddit": SUBREDDIT,
        "window": window_label,
        "window_after": after_ts,
        "posts_scraped": len(posts),
        "duplicate_posts_skipped": duplicate_posts_skipped,
        "unique_authors": total_authors,
        "user_histories_scraped": args.user_histories,
        "authors_with_history": authors_scraped,
        "authors_deleted_or_suspended": deleted_post_authors + authors_failed,
        "total_user_posts_collected": total_user_posts,
        "total_user_comments_collected": total_user_comments,
        "subreddits_seen": sorted(subreddits_seen),
        "scrape_started_at": scrape_started,
        "scrape_finished_at": scrape_finished,
        "profiles_enriched": args.enrich_profiles,
        "source": "Arctic Shift API (https://arctic-shift.photon-reddit.com)",
        "data_quality_notes": {
            "num_comments_api": "Unreliable — use comments_fetched field instead.",
            "score": "Often 1 for recently posted content; Arctic Shift may capture posts before voting accumulates.",
            "comment_depth": "Removed — Arctic Shift always returns 0. Trace parent_id chains to reconstruct nesting.",
            "duplicates": "Same-author + same-title posts are detected and skipped. See duplicate_posts_skipped.",
        },
    }
    with open(OUTPUT_DIR / "corpus_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print(f"\n{'=' * 60}")
    print(f"  Done!")
    print(f"  Window            : last {window_label}")
    print(f"  Posts downloaded  : {len(posts)}"
          + (f" (capped at --limit-posts {args.limit_posts})" if args.limit_posts else ""))
    print(f"  Duplicates skipped: {duplicate_posts_skipped}")
    print(f"  Unique authors    : {total_authors}")
    if args.user_histories:
        print(f"  Histories scraped : {authors_scraped}")
        print(f"  Authors skipped   : {deleted_post_authors + authors_failed}")
        print(f"  User posts        : {total_user_posts}")
        print(f"  User comments     : {total_user_comments}")
        print(f"  Subreddits seen   : {len(subreddits_seen)}")
    else:
        print(f"  Histories scraped : skipped (--user-histories not passed)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
