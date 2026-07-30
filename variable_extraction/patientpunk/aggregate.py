"""Per-patient corpus aggregation.

Collapse a posts-with-nested-comments corpus (``subreddit_posts.json``) into ONE
synthetic "post" per author -- a per-PATIENT document -- so extraction runs once
per author instead of once per post. This (1) matches the clustering unit
(``cluster-prep`` aggregates per author on the output anyway) and (2) cuts LLM
cost several-fold: a patient with 10 posts becomes one call, not ten.

True per-patient: every text segment is attributed to ITS OWN author -- a comment
by author B under a post by author A counts toward B, not A. So commenters become
patients too. Use ``min_items`` to drop authors with too little text to profile.

The output is a normal ``subreddit_posts.json`` (each entry a synthetic post with
the author's combined text in ``body``, no nested comments), so the rest of the
pipeline -- LLM extraction, discovery, CSV, codebook -- runs UNCHANGED on the
aggregated corpus. ``collect_texts_from_post`` reads title/body (comments are
excluded to avoid cross-author attribution), and the aggregated entries carry
their combined text in ``body``, so it is picked up as-is.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

# Mirror extraction modules' _keep_text: drop empty / moderator-removed / user-deleted text.
_DROP = {"", "[removed]", "[deleted]"}


def _keep(text: object) -> str:
    t = (text or "").strip() if isinstance(text, str) else ""
    return "" if t in _DROP else t


def aggregate_corpus_by_author(
    posts: list[dict],
    *,
    min_items: int = 1,
    sep: str = "\n\n---\n\n",
) -> tuple[list[dict], dict]:
    """Group every post/comment text segment by its own ``author_hash``.

    Returns ``(synthetic_posts, stats)``. Each synthetic post::

        {author_hash, post_id="agg_<hash12>", title="", body=<joined segments>,
         comments=[], num_comments=0, n_items=<k>, subreddits="<name:count ...>",
         aggregated=True}

    Authors with fewer than ``min_items`` non-empty segments are dropped.

    ``subreddits`` counts which communities the patient's segments came from. We
    want to keep this information for analysis later as the redditors' posts are
    aggregated into one document.
    """
    segments: dict[str, list[str]] = defaultdict(list)
    subreddit_counts: dict[str, Counter] = defaultdict(Counter)
    n_posts = 0
    n_comments = 0
    for post in posts:
        n_posts += 1
        pa = (post.get("author_hash") or "").strip()
        title = _keep(post.get("title"))
        body = _keep(post.get("body"))
        block = "\n\n".join(t for t in (title, body) if t)
        post_subreddit = (post.get("subreddit") or "").strip()
        if pa and block:
            segments[pa].append(block)
            if post_subreddit:
                subreddit_counts[pa][post_subreddit] += 1
        for comment in post.get("comments") or []:
            n_comments += 1
            ca = (comment.get("author_hash") or "").strip()
            cb = _keep(comment.get("body"))
            if ca and cb:
                segments[ca].append(cb)
                comment_subreddit = (
                    comment.get("subreddit") or post_subreddit).strip()
                if comment_subreddit:
                    subreddit_counts[ca][comment_subreddit] += 1

    out: list[dict] = []
    dropped = 0
    for author, segs in sorted(segments.items()):
        if len(segs) < min_items:
            dropped += 1
            continue
        out.append({
            "author_hash": author,
            "post_id": f"agg_{author[:12]}",
            "title": "",
            "body": sep.join(segs),
            "comments": [],
            "num_comments": 0,
            "n_items": len(segs),
            "subreddits": " ".join(
                f"{name}:{count}"
                for name, count in subreddit_counts[author].most_common()),
            "aggregated": True,
        })

    chars = sorted(len(p["body"]) for p in out)
    stats = {
        "in_posts": n_posts,
        "in_comments": n_comments,
        "authors_seen": len(segments),
        "patients_out": len(out),
        "dropped_below_min": dropped,
        "min_items": min_items,
        "avg_items_per_patient": (
            round(sum(p["n_items"] for p in out) / len(out), 2) if out else 0
        ),
        "median_body_chars": chars[len(chars) // 2] if chars else 0,
        "max_body_chars": chars[-1] if chars else 0,
    }
    return out, stats


def read_posts(input_dir: Path) -> list[dict]:
    """Load ``subreddit_posts.json`` from a corpus directory."""
    f = input_dir / "subreddit_posts.json"
    if not f.exists():
        raise FileNotFoundError(f"no subreddit_posts.json in {input_dir}")
    return json.loads(f.read_text(encoding="utf-8"))


def write_corpus(output_dir: Path, posts: list[dict]) -> Path:
    """Write synthetic posts as ``<output_dir>/subreddit_posts.json``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "subreddit_posts.json"
    out.write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
