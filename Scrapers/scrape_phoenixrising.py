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
    from an external search engine API, or supplied via --thread-list.
  * Only /threads/ and /sitemap*.xml are fetched. A guard refuses any path
    in the robots.txt Disallow list.

Privacy: usernames are SHA-256 hashed before anything is written to disk,
matching scrape_corpus.py. Raw usernames exist only in memory.

Usage:
    # Discover LDN/Mestinon/pyridostigmine threads from the sitemap slug and scrape them
    python scrape_phoenixrising.py --from-sitemap

    # Discover candidate threads via search API query set (BRAVE_SEARCH_API_KEY required)
    # Brave search operators docs:
    # https://api-dashboard.search.brave.com/documentation/resources/search-operators/index.html.md
    python scrape_phoenixrising.py --from-search-api \
        --search-query-file Scrapers/phoenixrising_search_queries.txt

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
import os
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
DEFAULT_SEARCH_QUERY_FILE = Path(__file__).with_name("phoenixrising_search_queries.txt")

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


def fetch_json(
    url: str,
    delay: float,
    retries: int = 5,
    headers: dict[str, str] | None = None,
) -> dict:
    """GET a JSON URL with backoff (for external search API discovery)."""
    last_exc = None
    for attempt in range(retries):
        try:
            req_headers = {
                "User-Agent": UA,
                "Accept": "application/json",
                "Accept-Encoding": "identity",
            }
            if headers:
                req_headers.update(headers)
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
            time.sleep(delay)
            return json.loads(raw.decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            # For invalid API key or exhausted credits, fail fast.
            if e.code in (400, 401, 403):
                raise
            last_exc = e
        except Exception as e:  # noqa: BLE001
            last_exc = e
        wait = 2 ** attempt
        print(f"    search api request failed ({last_exc}); retry in {wait}s", file=sys.stderr)
        time.sleep(wait)
    raise RuntimeError(f"giving up on {url}: {last_exc}")


def hash_username(username: str | None) -> str | None:
    if not username or username.strip().lower() in ("", "guest", "[deleted]"):
        return None
    return hashlib.sha256(username.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Discovery (sitemap)
# ---------------------------------------------------------------------------

THREAD_URL_RE = re.compile(r"^/threads/([^/?#]+)\.(\d+)(?:/.*)?$")


def normalize_thread_url(url: str) -> str | None:
    """Normalize any thread URL variant to canonical /threads/<slug>.<id>/ form."""
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.netloc and parsed.netloc != urllib.parse.urlsplit(BASE).netloc:
        return None
    m = THREAD_URL_RE.match(parsed.path)
    if not m:
        return None
    slug, tid = m.group(1), m.group(2)
    return f"{BASE}/threads/{slug}.{tid}/"


def load_aliases(files: list[str]) -> list[str]:
    aliases: list[str] = []
    for f in files:
        p = Path(f)
        if not p.exists():
            raise FileNotFoundError(f"Alias file not found: {p}")
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            aliases.append(line)
    # Preserve order while de-duping.
    return list(dict.fromkeys(aliases))


def alias_regex(aliases: list[str]) -> re.Pattern:
    if not aliases:
        raise ValueError("Alias list is empty")
    return re.compile(r"\b(?:" + "|".join(re.escape(a) for a in aliases) + r")\b", re.I)


def discover_from_sitemap(delay: float) -> list[str]:
    """Return slug-keyword matched thread URLs from sitemap."""
    index = fetch(f"{BASE}/sitemap.xml", delay)
    sub_sitemaps = re.findall(r"<loc>([^<]+)</loc>", index)
    all_threads: set[str] = set()
    for sm in sub_sitemaps:
        xml = fetch(sm, delay)
        for loc in re.findall(r"<loc>([^<]+)</loc>", xml):
            normalized = normalize_thread_url(loc)
            if normalized:
                all_threads.add(normalized)
    matched = sorted(u for u in all_threads if GENERIC_KW.search(u) or LDN_KW.search(u))
    print(f"  sitemap: {len(all_threads)} threads total, {len(matched)} drug-matched")
    return matched


def load_search_queries(path: Path) -> list[str]:
    queries: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        queries.append(line)
    return list(dict.fromkeys(queries))


def discover_from_search_api(
    query_file: Path,
    api_key: str,
    delay: float,
    max_pages: int = 3,
    per_page: int = 10,
) -> list[str]:
    """Discover thread URLs via Brave Web Search API, scoped to forum domain."""
    # Query syntax reference:
    # https://api-dashboard.search.brave.com/documentation/resources/search-operators/index.html.md
    queries = load_search_queries(query_file)
    if not queries:
        raise ValueError(f"No queries found in {query_file}")
    out: set[str] = set()
    for q in queries:
        scoped = q if "site:forums.phoenixrising.me" in q.lower() else f"site:forums.phoenixrising.me {q}"
        print(f"  search: {q}")
        for page in range(max_pages):
            params = urllib.parse.urlencode(
                {
                    "q": scoped,
                    "count": per_page,
                    "offset": page,
                    "result_filter": "web",
                    "safesearch": "moderate",
                }
            )
            url = f"https://api.search.brave.com/res/v1/web/search?{params}"
            payload = fetch_json(
                url,
                delay,
                headers={"X-Subscription-Token": api_key},
            )
            organic = (payload.get("web") or {}).get("results") or []
            found_this_page = 0
            for row in organic:
                link = row.get("url") or row.get("link") or ""
                normalized = normalize_thread_url(link)
                if normalized:
                    found_this_page += 1
                    out.add(normalized)
            # Stop paginating this query once no organic links are returned.
            if not organic:
                break
            # If this page had no thread links, still allow next page once.
            if found_this_page == 0 and page >= 1:
                break
    matched = sorted(out)
    print(f"  search api: {len(queries)} queries, {len(matched)} unique thread URLs discovered")
    return matched


# ---------------------------------------------------------------------------
# Thread parsing
# ---------------------------------------------------------------------------

def thread_id_from_url(url: str) -> str | None:
    normalized = normalize_thread_url(url)
    m = re.search(r"\.(\d+)/$", normalized or "")
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


def thread_contains_alias(thread: dict, mention_rx: re.Pattern) -> bool:
    if mention_rx.search(thread.get("title", "")):
        return True
    if mention_rx.search(thread.get("body", "")):
        return True
    for c in thread.get("comments", []):
        if mention_rx.search(c.get("body", "")):
            return True
    return False


def scrape_thread(url: str, delay: float, max_pages_cap: int, mention_rx: re.Pattern | None = None) -> dict | None:
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

    thread = {
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
    if mention_rx and not thread_contains_alias(thread, mention_rx):
        return None
    return thread


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Scrape Phoenix Rising threads into PatientPunk corpus JSON.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-sitemap", action="store_true",
                     help="Discover drug-matched threads via sitemap.xml (robots-clean).")
    src.add_argument("--from-search-api", action="store_true",
                     help="Discover candidate threads via external search API query set.")
    src.add_argument("--thread-list", type=str,
                     help="File of thread URLs, one per line.")
    ap.add_argument("--out", type=str, default=str(OUTPUT_DIR / "phoenixrising_posts.json"))
    ap.add_argument("--limit", type=int, default=0, help="Max threads to scrape (0 = all).")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Seconds between requests.")
    ap.add_argument("--max-pages", type=int, default=500, help="Per-thread page cap.")
    ap.add_argument("--search-query-file", default=str(DEFAULT_SEARCH_QUERY_FILE),
                    help="Line-delimited search query file for --from-search-api.")
    ap.add_argument("--search-api-key", default="",
                    help="Brave Search API key (or set BRAVE_SEARCH_API_KEY env var).")
    ap.add_argument("--search-pages", type=int, default=3,
                    help="Max result pages per query for --from-search-api.")
    ap.add_argument("--search-per-page", type=int, default=10,
                    help="Results per search page for --from-search-api (max 20).")
    ap.add_argument("--drug-file", action="append", default=[],
                    help="Alias file path; can be passed multiple times.")
    ap.add_argument("--require-mention", action="store_true",
                    help="Keep only threads with alias match in title/OP/replies (requires --drug-file).")
    ap.add_argument("--no-resume", action="store_true",
                    help="Re-scrape threads already present in --out (default: skip them).")
    args = ap.parse_args()

    if args.require_mention and not args.drug_file:
        ap.error("--require-mention needs at least one --drug-file alias list")
    mention_rx = alias_regex(load_aliases(args.drug_file)) if args.require_mention else None

    started = datetime.now(timezone.utc).isoformat()

    if args.from_sitemap:
        targets = discover_from_sitemap(args.delay)
    elif args.from_search_api:
        api_key = args.search_api_key or os.environ.get("BRAVE_SEARCH_API_KEY", "")
        if not api_key:
            ap.error("--from-search-api needs --search-api-key or BRAVE_SEARCH_API_KEY")
        query_file = Path(args.search_query_file)
        if not query_file.exists():
            ap.error(f"--search-query-file not found: {query_file}")
        if args.search_pages < 1:
            ap.error("--search-pages must be >= 1")
        if args.search_pages > 10:
            ap.error("--search-pages must be <= 10 (Brave offset supports 0..9)")
        if not (1 <= args.search_per_page <= 20):
            ap.error("--search-per-page must be between 1 and 20")
        targets = discover_from_search_api(
            query_file=query_file,
            api_key=api_key,
            delay=args.delay,
            max_pages=args.search_pages,
            per_page=args.search_per_page,
        )
    else:
        targets = []
        for ln in Path(args.thread_list).read_text(encoding="utf-8").splitlines():
            normalized = normalize_thread_url(ln)
            if normalized:
                targets.append(normalized)
        targets = list(dict.fromkeys(targets))

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
    source_name = "sitemap" if args.from_sitemap else ("search-api" if args.from_search_api else args.thread_list)
    print(f"  Source     : {source_name}")
    if args.from_search_api:
        print(f"  Queries    : {args.search_query_file}")
        print(f"  Search cfg : pages/query={args.search_pages}, per_page={args.search_per_page}")
    if args.require_mention:
        print(f"  Mention RX : {len(args.drug_file)} alias file(s), keep mentioning threads only")
    print(f"  Targets    : {len(targets)}  |  to scrape now: {len(todo)}")
    print(f"  Delay      : {args.delay}s   |  Output: {out_path}")
    print("=" * 60)

    results = list(existing)
    total_comments = sum(len(p.get("comments", [])) for p in existing)
    for i, url in enumerate(todo, 1):
        print(f"  [{i}/{len(todo)}] {url}")
        post = scrape_thread(url, args.delay, args.max_pages, mention_rx=mention_rx)
        if post is None:
            if args.require_mention:
                print("        skipped (no alias mention found in thread content)")
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
        "discovery": (
            "sitemap"
            if args.from_sitemap
            else ("search-api:brave" if args.from_search_api else f"thread-list:{args.thread_list}")
        ),
        "search_query_file": args.search_query_file if args.from_search_api else None,
        "search_pages": args.search_pages if args.from_search_api else None,
        "search_per_page": args.search_per_page if args.from_search_api else None,
        "require_mention": bool(args.require_mention),
        "drug_files": args.drug_file,
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
