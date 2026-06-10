#!/usr/bin/env python3
"""Phoenix Rising forum scraper for PatientPunk.

Scrapes patient self-report threads from the Phoenix Rising ME/CFS forum
(XenForo 2) and emits JSON in the SAME corpus schema as scrape_corpus.py,
so the existing pipeline (import_posts.py -> run_sentiment_pipeline.py)
ingests it unchanged; the importer is configured to map this forum hostname
to `phoenixrising` when no `--subreddit` override is provided.

Mapping forum -> corpus:
    thread        -> one "post" object (the opening post / OP)
    every reply   -> a "comment" object under that post
    reply quoting -> comment.parent_id points at the quoted post; otherwise
                     it points at the OP, so the pipeline's drugs_context
                     reply-chain inheritance works for forum threads too.

Discovery is robots.txt-compliant:
  * /search/ is Disallowed, so we never hit the on-site search.
  * Threads are discovered from sitemap.xml (Allowed) by keyword in the slug,
    or supplied via --thread-list.
  * Only /threads/ and /sitemap*.xml are fetched. A guard refuses any path
    in the robots.txt Disallow list.

Privacy: usernames are SHA-256 hashed before anything is written to disk,
matching scrape_corpus.py. Raw usernames exist only in memory.

Usage:
    # Discover LDN/Mestinon/pyridostigmine threads from the sitemap and scrape them
    python scrape_phoenixrising.py --from-sitemap

    # Scrape a specific list of thread URLs (one per line)
    python scrape_phoenixrising.py --thread-list phoenixrising_targets.txt

    # Quick test: first 3 threads only
    python scrape_phoenixrising.py --thread-list phoenixrising_targets.txt --limit 3 \
        --out output/pr_test.json

Dependencies: beautifulsoup4 (HTML parsing). HTTP uses the standard library.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

BASE = "https://forums.phoenixrising.me"
UA = "Mozilla/5.0 (compatible; PatientPunk-research/0.1; +https://github.com/Ely-S/PatientPunk)"
DEFAULT_DELAY = 2.5  # seconds between requests (polite; robots.txt sets no crawl-delay)
OUTPUT_DIR = Path(__file__).parent.parent / "output"

# robots.txt Disallow list (fetched 2026-06; see README). We only ever request
# /threads/ and /sitemap*.xml, but guard anyway so we never wander into these.
ROBOTS_DISALLOW = (
    "/whats-new/", "/account/", "/attachments/", "/goto/", "/posts/",
    "/login/", "/admin.php", "/members/", "/blog-articles/", "/articles/",
    "/search/", "/index.php?members/",
)

# Default drug keywords. naltrexone/mestinon/pyridostigmine match as substrings;
# "ldn" must be a slug token (-ldn- / -ldn. / /ldn-) to avoid matching "couldnt" etc.
GENERIC_KW = re.compile(r"(naltrexon|mestinon|pyridostigmine)", re.I)
LDN_KW = re.compile(r"(/|-)ldn(-|\.)", re.I)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _check_robots(url: str) -> None:
    if "://" in url:
        parsed = urllib.parse.urlsplit(url)
        path = parsed.path
        if parsed.query:
            path = f"{path}?{parsed.query}"
    else:
        path = url
    for bad in ROBOTS_DISALLOW:
        if path.startswith(bad):
            raise ValueError(f"Refusing to fetch robots.txt-Disallowed path: {path}")


def fetch(url: str, delay: float, retries: int = 5) -> str:
    """GET a URL as text with polite delay and exponential backoff."""
    _check_robots(url)
    last_exc = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "text/html,application/xhtml+xml,application/xml",
                    "Accept-Encoding": "identity",
                },
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
            time.sleep(delay)
            return raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            # Don't retry hard client errors.
            if e.code in (403, 404, 410):
                raise
            last_exc = e
        except Exception as e:  # noqa: BLE001
            last_exc = e
        wait = 2 ** attempt
        print(f"    request failed ({last_exc}); retry in {wait}s", file=sys.stderr)
        time.sleep(wait)
    raise RuntimeError(f"giving up on {url}: {last_exc}")


def hash_username(username: str | None) -> str | None:
    if not username or username.strip().lower() in ("", "guest", "[deleted]"):
        return None
    return hashlib.sha256(username.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Discovery (sitemap)
# ---------------------------------------------------------------------------

THREAD_RE = re.compile(r"https://forums\.phoenixrising\.me/threads/[a-z0-9-]+\.\d+/")


def discover_from_sitemap(delay: float) -> list[str]:
    """Return drug-matched thread URLs from the XenForo sitemap index."""
    index = fetch(f"{BASE}/sitemap.xml", delay)
    sub_sitemaps = re.findall(r"<loc>([^<]+)</loc>", index)
    all_threads: set[str] = set()
    for sm in sub_sitemaps:
        xml = fetch(sm, delay)
        for loc in re.findall(r"<loc>([^<]+)</loc>", xml):
            normalized = loc.strip()
            if normalized and not normalized.endswith("/"):
                normalized += "/"
            if THREAD_RE.fullmatch(normalized):
                all_threads.add(normalized)
            elif THREAD_RE.match(normalized):
                all_threads.add(THREAD_RE.match(normalized).group(0))
    matched = sorted(u for u in all_threads if GENERIC_KW.search(u) or LDN_KW.search(u))
    print(f"  sitemap: {len(all_threads)} threads total, {len(matched)} drug-matched")
    return matched


# ---------------------------------------------------------------------------
# Thread parsing
# ---------------------------------------------------------------------------

def thread_id_from_url(url: str) -> str | None:
    m = re.search(r"\.(\d+)/?(?:page-\d+/?)?$", url)
    return m.group(1) if m else None


def page_url(thread_url: str, n: int) -> str:
    base = thread_url.rstrip("/")
    return base if n <= 1 else f"{base}/page-{n}"


def max_page(html: str, thread_id: str) -> int:
    pages = re.findall(rf"/threads/[^\"'/]+\.{thread_id}/page-(\d+)", html)
    return max((int(p) for p in pages), default=1)


def parse_posts(html: str) -> list[dict]:
    """Parse all posts on a thread page into raw dicts (document order)."""
    soup = BeautifulSoup(html, "html.parser")
    articles = soup.select("article.message--post") or soup.select("article.message")
    out: list[dict] = []
    for art in articles:
        author = (art.get("data-author") or "").strip()

        # Post id: from article id (js-post-NNN) or a descendant data-content.
        pid = None
        m = re.search(r"post-(\d+)", art.get("id", "") or "")
        if not m:
            holder = art.select_one('[data-content^="post-"], [data-lb-id^="post-"]')
            if holder:
                attr = holder.get("data-content") or holder.get("data-lb-id") or ""
                m = re.search(r"post-(\d+)", attr)
        if m:
            pid = m.group(1)
        if not pid:
            continue  # can't anchor this post; skip

        # Timestamp (prefer unix epoch from data-time).
        created = None
        t = art.select_one("time.u-dt") or art.select_one("time")
        if t:
            if t.get("data-time"):
                try:
                    created = int(t["data-time"])
                except (TypeError, ValueError):
                    created = None
            if created is None and t.get("datetime"):
                created = t["datetime"]

        # Reactions / likes as a rough "score".
        score = 0
        react = art.select_one("[data-reaction-score]")
        if react:
            try:
                score = int(react["data-reaction-score"])
            except (TypeError, ValueError):
                score = 0

        # Body. Scope to this post's message-body bbWrapper (excludes signatures).
        body_el = art.select_one(".message-body .bbWrapper") or art.select_one(".bbWrapper")
        parent_pid = None
        text = ""
        if body_el is not None:
            # Record the first quoted post (reply-chain parent) before stripping.
            bq = body_el.select_one('blockquote[data-source^="post:"], blockquote[data-source^="post :"]')
            if bq:
                mq = re.search(r"post:\s*(\d+)", bq.get("data-source", ""))
                if mq:
                    parent_pid = mq.group(1)
            # Remove quote blocks, scripts, styles so we keep only this author's words.
            for junk in body_el.select("blockquote, .bbCodeBlock--quote, script, style, .js-unfurl"):
                junk.decompose()
            text = body_el.get_text("\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()

        out.append({
            "pid": pid,
            "author": author,
            "created": created,
            "score": score,
            "body": text,
            "parent_pid": parent_pid,
        })
    return out


def scrape_thread(url: str, delay: float, max_pages_cap: int) -> dict | None:
    tid = thread_id_from_url(url)
    if not tid:
        print(f"  ! could not parse thread id from {url}", file=sys.stderr)
        return None
    try:
        html1 = fetch(url, delay)
    except Exception as e:  # noqa: BLE001
        print(f"  ! failed {url}: {e}", file=sys.stderr)
        return None

    soup = BeautifulSoup(html1, "html.parser")
    title_el = soup.select_one("h1.p-title-value")
    title = title_el.get_text(strip=True) if title_el else ""
    prefix_el = soup.select_one("h1.p-title-value .label")
    flair = prefix_el.get_text(strip=True) if prefix_el else None

    n_pages = min(max_page(html1, tid), max_pages_cap)
    raw_posts = parse_posts(html1)
    for n in range(2, n_pages + 1):
        try:
            raw_posts.extend(parse_posts(fetch(page_url(url, n), delay)))
        except Exception as e:  # noqa: BLE001
            print(f"  ! failed {url} page {n}: {e}", file=sys.stderr)
            break

    # Dedup posts by pid (page overlaps, sticky first-post echoes).
    seen: set[str] = set()
    posts: list[dict] = []
    for p in raw_posts:
        if p["pid"] in seen:
            continue
        seen.add(p["pid"])
        posts.append(p)
    if not posts:
        print(f"  ! no posts parsed for {url}", file=sys.stderr)
        return None

    op = posts[0]
    op_key = f"pr-{op['pid']}"
    valid_ids = {f"pr-{p['pid']}" for p in posts}
    comments = []
    for p in posts[1:]:
        quoted_parent = f"pr-{p['parent_pid']}" if p["parent_pid"] else None
        parent = quoted_parent if quoted_parent in valid_ids else op_key
        comments.append({
            "comment_id": f"pr-{p['pid']}",
            "body": p["body"],
            "author_hash": hash_username(p["author"]),
            "created_utc": p["created"],
            "score": p["score"],
            "parent_id": parent,
            "url": f"{url}#post-{p['pid']}",
        })

    return {
        "post_id": op_key,
        "title": title,
        "body": op["body"],
        "author_hash": hash_username(op["author"]),
        "created_utc": op["created"],
        "score": op["score"],
        "num_comments_api": len(comments),
        "comments_fetched": len(comments),
        "url": url,
        "flair": flair,
        "thread_id": tid,
        "pages": n_pages,
        "comments": comments,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Scrape Phoenix Rising threads into PatientPunk corpus JSON.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-sitemap", action="store_true",
                     help="Discover drug-matched threads via sitemap.xml (robots-clean).")
    src.add_argument("--thread-list", type=str,
                     help="File of thread URLs, one per line.")
    ap.add_argument("--out", type=str, default=str(OUTPUT_DIR / "phoenixrising_posts.json"))
    ap.add_argument("--limit", type=int, default=0, help="Max threads to scrape (0 = all).")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Seconds between requests.")
    ap.add_argument("--max-pages", type=int, default=500, help="Per-thread page cap.")
    ap.add_argument("--no-resume", action="store_true",
                    help="Re-scrape threads already present in --out (default: skip them).")
    args = ap.parse_args()

    started = datetime.now(timezone.utc).isoformat()

    if args.from_sitemap:
        targets = discover_from_sitemap(args.delay)
    else:
        targets = [ln.strip() for ln in Path(args.thread_list).read_text().splitlines() if ln.strip()]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    existing: list[dict] = []
    done_ids: set[str] = set()
    if out_path.exists() and not args.no_resume:
        try:
            loaded = json.loads(out_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, list) or any(not isinstance(item, dict) for item in loaded):
                raise ValueError(f"{out_path} does not contain a list of thread objects")
            existing = loaded
            done_ids = {p.get("thread_id") for p in existing}
            print(f"  resume: {len(existing)} threads already in {out_path.name}")
        except (ValueError, OSError):
            existing = []

    todo = [u for u in targets if thread_id_from_url(u) not in done_ids]
    if args.limit:
        todo = todo[:args.limit]

    print("=" * 60)
    print(f"  Source     : {'sitemap' if args.from_sitemap else args.thread_list}")
    print(f"  Targets    : {len(targets)}  |  to scrape now: {len(todo)}")
    print(f"  Delay      : {args.delay}s   |  Output: {out_path}")
    print("=" * 60)

    results = list(existing)
    total_comments = sum(len(p.get("comments", [])) for p in existing)
    for i, url in enumerate(todo, 1):
        print(f"  [{i}/{len(todo)}] {url}")
        post = scrape_thread(url, args.delay, args.max_pages)
        if post is None:
            continue
        results.append(post)
        total_comments += len(post["comments"])
        # Incremental, crash-safe write after every thread.
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"        OP + {len(post['comments'])} replies over {post['pages']} page(s) — \"{post['title'][:60]}\"")

    finished = datetime.now(timezone.utc).isoformat()
    meta = {
        "source": "Phoenix Rising ME/CFS Forums (forums.phoenixrising.me)",
        "scraper": "scrape_phoenixrising.py",
        "discovery": "sitemap" if args.from_sitemap else f"thread-list:{args.thread_list}",
        "threads_total_targeted": len(targets),
        "threads_in_output": len(results),
        "total_replies": total_comments,
        "scrape_started_at": started,
        "scrape_finished_at": finished,
        "robots_compliance": "Skips all robots.txt Disallow paths; only /threads/ and /sitemap*.xml fetched.",
        "privacy": "All usernames SHA-256 hashed before write; raw usernames never persisted.",
        "notes": {
            "parent_linkage": "Replies that quote a post link to it; otherwise link to the thread OP.",
            "body": "Quote blocks stripped from each post so only that author's words remain.",
            "score": "Reaction/like count when present, else 0.",
        },
    }
    meta_path = out_path.with_name(out_path.stem.replace("_posts", "") + "_metadata.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 60)
    print(f"  Done. {len(results)} threads, {total_comments} replies.")
    print(f"  Posts : {out_path}")
    print(f"  Meta  : {meta_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
