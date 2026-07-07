#!/usr/bin/env python3
"""Run paginated Brave discovery for LDN + Mestinon query sets.

Outputs:
  - Per-set JSON result files with per-query pagination stats + discovered URLs
  - required_pages.txt (union of all discovered canonical thread URLs)
  - minimum_query_set.json / .txt (smallest query subset that covers all pages)
  - summary.csv (one row per query)

Example:
  python scripts/brave_query_set_cover.py \
    --ldn-query-file Scrapers/phoenixrising_search_queries_ldn.txt \
    --mestinon-query-file Scrapers/phoenixrising_search_queries_mestinon.txt \
    --api-key "$BRAVE_SEARCH_API_KEY"
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import os
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
FORUM_HOST = "forums.phoenixrising.me"
DEFAULT_LDN_QUERY_FILE = Path("Scrapers/phoenixrising_search_queries_ldn.txt")
DEFAULT_MESTINON_QUERY_FILE = Path("Scrapers/phoenixrising_search_queries_mestinon.txt")
DEFAULT_OUT_DIR = Path("output/brave_query_analysis")


@dataclass(frozen=True)
class QueryRef:
    set_name: str
    index: int
    query: str

    @property
    def key(self) -> str:
        return f"{self.set_name}:{self.index:02d}"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Paginate Brave query sets and compute minimum query cover for discovered pages."
    )
    ap.add_argument("--ldn-query-file", type=Path, default=DEFAULT_LDN_QUERY_FILE)
    ap.add_argument("--mestinon-query-file", type=Path, default=DEFAULT_MESTINON_QUERY_FILE)
    ap.add_argument("--api-key", default="", help="Brave API key (or BRAVE_SEARCH_API_KEY env var).")
    ap.add_argument("--count", type=int, default=20, help="Results per page (Brave max 20).")
    ap.add_argument("--max-pages", type=int, default=10, help="Max pages per query (Brave offset 0..9).")
    ap.add_argument("--delay", type=float, default=0.5, help="Delay between API requests (seconds).")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--no-timestamp-dir", action="store_true",
                    help="Write directly to --out-dir instead of a timestamped subdirectory.")
    ap.add_argument("--exact-max-queries", type=int, default=18,
                    help="Run exact minimum set cover only when total query count <= this value.")
    ap.add_argument(
        "--write-min-query-files",
        action="store_true",
        help="Write ldn_min_queries.txt and mestinon_min_queries.txt from chosen minimum cover.",
    )
    args = ap.parse_args()

    if not args.api_key:
        args.api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
    if not args.api_key:
        ap.error("Missing API key. Set --api-key or BRAVE_SEARCH_API_KEY.")

    if not (1 <= args.count <= 20):
        ap.error("--count must be between 1 and 20")
    if not (1 <= args.max_pages <= 10):
        ap.error("--max-pages must be between 1 and 10")
    if args.delay < 0:
        ap.error("--delay must be >= 0")

    for p in (args.ldn_query_file, args.mestinon_query_file):
        if not p.exists():
            ap.error(f"Query file not found: {p}")

    return args


def load_queries(path: Path) -> list[str]:
    queries: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        queries.append(line)
    return list(dict.fromkeys(queries))


def normalize_thread_url(url: str) -> str | None:
    """Normalize to canonical Phoenix Rising /threads/<slug>.<id>/ URL."""
    parsed = urllib.parse.urlsplit((url or "").strip())
    if parsed.netloc and parsed.netloc != FORUM_HOST:
        return None
    path = parsed.path or ""
    if not path.startswith("/threads/"):
        return None
    # Keep only /threads/<slug>.<id>/ and strip page suffixes/anchors/etc.
    parts = path.split("/")
    if len(parts) < 3:
        return None
    thread_piece = parts[2]  # <slug>.<id>
    if "." not in thread_piece:
        return None
    slug, thread_id = thread_piece.rsplit(".", 1)
    if not slug or not thread_id.isdigit():
        return None
    return f"https://{FORUM_HOST}/threads/{slug}.{thread_id}/"


def brave_web_search(api_key: str, query: str, count: int, offset: int) -> dict[str, Any]:
    params = urllib.parse.urlencode(
        {
            "q": query,
            "count": count,
            "offset": offset,
            "result_filter": "web",
            "safesearch": "moderate",
        }
    )
    req = urllib.request.Request(
        f"{BRAVE_SEARCH_URL}?{params}",
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
            "User-Agent": "PatientPunk-brave-query-set-cover/0.1",
        },
    )
    last_exc: Exception | None = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
            payload: dict[str, Any] = json.loads(raw.decode("utf-8", errors="replace"))
            return payload
        except urllib.error.HTTPError as e:
            last_exc = e
            if e.code == 429:
                time.sleep(2 + attempt * 3)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_exc = e
            time.sleep(2 + attempt * 2)
    raise RuntimeError(
        f"Brave query failed after retries (offset={offset}): {query!r} | last_error={last_exc}"
    )


def discover_query_urls(
    api_key: str,
    query: str,
    count: int,
    max_pages: int,
    delay: float,
) -> tuple[set[str], list[dict[str, Any]]]:
    urls: set[str] = set()
    page_stats: list[dict[str, Any]] = []

    for page in range(max_pages):
        payload = brave_web_search(api_key=api_key, query=query, count=count, offset=page)
        rows = ((payload.get("web") or {}).get("results") or [])
        before = len(urls)
        for row in rows:
            normalized = normalize_thread_url(row.get("url") or "")
            if normalized:
                urls.add(normalized)
        added = len(urls) - before
        more_results = bool((payload.get("query") or {}).get("more_results_available", False))
        page_stats.append(
            {
                "offset": page,
                "web_results": len(rows),
                "new_thread_urls": added,
                "cumulative_thread_urls": len(urls),
                "more_results_available": more_results,
            }
        )
        if not rows or not more_results:
            break
        if delay:
            time.sleep(delay)
    return urls, page_stats


def greedy_set_cover(
    required: set[str],
    query_to_urls: dict[str, set[str]],
) -> list[str]:
    uncovered = set(required)
    chosen: list[str] = []
    candidates = set(query_to_urls.keys())

    while uncovered:
        best_key = None
        best_gain_set: set[str] = set()
        for key in sorted(candidates):
            gain = query_to_urls[key] & uncovered
            if not gain:
                continue
            if len(gain) > len(best_gain_set):
                best_key = key
                best_gain_set = gain
        if best_key is None:
            break
        chosen.append(best_key)
        uncovered -= best_gain_set
        candidates.remove(best_key)
    return chosen


def exact_min_set_cover(required: set[str], query_to_urls: dict[str, set[str]]) -> list[str] | None:
    keys = sorted(query_to_urls.keys())
    if not required:
        return []
    for k in range(1, len(keys) + 1):
        for combo in itertools.combinations(keys, k):
            covered: set[str] = set()
            for key in combo:
                covered |= query_to_urls[key]
            if required <= covered:
                return list(combo)
    return None


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()

    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.out_dir if args.no_timestamp_dir else (args.out_dir / now)
    run_dir.mkdir(parents=True, exist_ok=True)

    query_sets = {
        "ldn": load_queries(args.ldn_query_file),
        "mestinon": load_queries(args.mestinon_query_file),
    }

    all_query_results: list[dict[str, Any]] = []
    query_to_urls: dict[str, set[str]] = {}
    set_level: dict[str, Any] = {}

    print(f"Running Brave discovery -> {run_dir}")
    for set_name, queries in query_sets.items():
        print(f"  {set_name}: {len(queries)} queries")
        set_rows: list[dict[str, Any]] = []
        set_union: set[str] = set()
        for idx, query in enumerate(queries, 1):
            qref = QueryRef(set_name=set_name, index=idx, query=query)
            urls, page_stats = discover_query_urls(
                api_key=args.api_key,
                query=query,
                count=args.count,
                max_pages=args.max_pages,
                delay=args.delay,
            )
            query_to_urls[qref.key] = set(urls)
            set_union |= urls
            row = {
                "query_key": qref.key,
                "query": query,
                "thread_url_count": len(urls),
                "thread_urls": sorted(urls),
                "page_stats": page_stats,
            }
            set_rows.append(row)
            all_query_results.append(row)
            print(f"    {qref.key} -> {len(urls)} canonical thread URLs")
        set_payload = {
            "set_name": set_name,
            "query_file": str(args.ldn_query_file if set_name == "ldn" else args.mestinon_query_file),
            "query_count": len(queries),
            "union_thread_url_count": len(set_union),
            "union_thread_urls": sorted(set_union),
            "queries": set_rows,
        }
        write_json(run_dir / f"{set_name}_results.json", set_payload)
        set_level[set_name] = set_payload

    required_pages: set[str] = set()
    for urls in query_to_urls.values():
        required_pages |= urls

    (run_dir / "required_pages.txt").write_text(
        "\n".join(sorted(required_pages)) + ("\n" if required_pages else ""),
        encoding="utf-8",
    )

    greedy_cover_keys = greedy_set_cover(required=required_pages, query_to_urls=query_to_urls)
    greedy_covered: set[str] = set()
    for key in greedy_cover_keys:
        greedy_covered |= query_to_urls[key]

    exact_cover_keys: list[str] | None = None
    if len(query_to_urls) <= args.exact_max_queries:
        exact_cover_keys = exact_min_set_cover(required=required_pages, query_to_urls=query_to_urls)

    chosen_keys = exact_cover_keys if exact_cover_keys is not None else greedy_cover_keys
    chosen_method = "exact" if exact_cover_keys is not None else "greedy"

    min_payload = {
        "method": chosen_method,
        "required_page_count": len(required_pages),
        "chosen_query_count": len(chosen_keys),
        "chosen_queries": [
            {
                "query_key": key,
                "query": next(r["query"] for r in all_query_results if r["query_key"] == key),
                "thread_url_count": len(query_to_urls[key]),
            }
            for key in chosen_keys
        ],
        "covered_page_count": len(set().union(*(query_to_urls[k] for k in chosen_keys))) if chosen_keys else 0,
        "missing_page_count": len(required_pages - set().union(*(query_to_urls[k] for k in chosen_keys))) if chosen_keys else len(required_pages),
    }
    write_json(run_dir / "minimum_query_set.json", min_payload)
    (run_dir / "minimum_query_set.txt").write_text(
        "\n".join(
            [
                f"method={min_payload['method']}",
                f"required_page_count={min_payload['required_page_count']}",
                f"chosen_query_count={min_payload['chosen_query_count']}",
                *[
                    f"{q['query_key']} | urls={q['thread_url_count']} | {q['query']}"
                    for q in min_payload["chosen_queries"]
                ],
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    if args.write_min_query_files:
        key_to_query = {row["query_key"]: row["query"] for row in all_query_results}
        ldn_min = [key_to_query[k] for k in chosen_keys if k.startswith("ldn:")]
        mestinon_min = [key_to_query[k] for k in chosen_keys if k.startswith("mestinon:")]
        (run_dir / "ldn_min_queries.txt").write_text(
            "\n".join(ldn_min) + ("\n" if ldn_min else ""),
            encoding="utf-8",
        )
        (run_dir / "mestinon_min_queries.txt").write_text(
            "\n".join(mestinon_min) + ("\n" if mestinon_min else ""),
            encoding="utf-8",
        )

    with (run_dir / "summary.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["query_key", "query", "thread_url_count", "set_name"])
        for row in sorted(all_query_results, key=lambda r: r["query_key"]):
            writer.writerow([row["query_key"], row["query"], row["thread_url_count"], row["query_key"].split(":")[0]])

    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "ldn_query_file": str(args.ldn_query_file),
        "mestinon_query_file": str(args.mestinon_query_file),
        "count": args.count,
        "max_pages": args.max_pages,
        "delay": args.delay,
        "query_sets": {
            "ldn_query_count": len(query_sets["ldn"]),
            "mestinon_query_count": len(query_sets["mestinon"]),
            "total_query_count": len(all_query_results),
        },
        "totals": {
            "required_page_count": len(required_pages),
            "greedy_query_count": len(greedy_cover_keys),
            "exact_query_count": len(exact_cover_keys) if exact_cover_keys is not None else None,
            "greedy_covered_count": len(greedy_covered),
        },
    }
    write_json(run_dir / "run_metadata.json", metadata)

    print("\nDone.")
    print(f"  Required pages (union): {len(required_pages)}")
    print(f"  Minimum query set ({chosen_method}): {len(chosen_keys)} queries")
    if args.write_min_query_files:
        print("  Wrote min query files: ldn_min_queries.txt, mestinon_min_queries.txt")
    print(f"  Output directory: {run_dir}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)
