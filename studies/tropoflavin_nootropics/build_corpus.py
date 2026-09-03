"""Pull every r/Nootropics thread containing a 7,8-DHF-family mention.

Posts and comments are combined into one nested subreddit_posts.json, which is
the format BOTH pipelines read: src/import_posts.py for the sentiment pipeline,
and variable_extraction's Corpus() for the field extractor.
"""
from __future__ import annotations
import hashlib, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]      # repo root
DATA = ROOT.parent / "PatientPunk_data"         # sibling of the repo
DOCS = ROOT.parent.parent                       # posts dump not yet moved into DATA

COMMENTS = DATA / "r_nootropics_comments.jsonl"
POSTS = DOCS / "r_nootropics_posts.jsonl"   # not yet copied into PatientPunk_data

PAT = re.compile(r"(?i)(tropoflavin|hydroxyflavone|\b7[ .,'-]{0,2}8[ .,'-]{0,2}dhf\b|\bdhf\b)")
PRE = (b"dhf", b"flavon", b"tropoflav")


def hits(b: bytes) -> bool:
    low = b.lower()
    return any(k in low for k in PRE)


def hash_author(name):
    if not name or name in ("[deleted]", "[removed]"):
        return "deleted"
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:32]


def iso(ts):
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()


def clean(b):
    return "" if b in ("[deleted]", "[removed]", None) else (b or "")


# ── Pass 1: which threads mention it? ───────────────────────────────────────
threads: set[str] = set()
for path, kind in ((COMMENTS, "c"), (POSTS, "p")):
    n = 0
    with path.open("rb") as fh:
        for b in fh:
            if not hits(b):
                continue
            try:
                o = json.loads(b)
            except Exception:
                continue
            txt = o.get("body") if kind == "c" else \
                ((o.get("title") or "") + " " + (o.get("selftext") or ""))
            if not PAT.search(txt or ""):
                continue
            n += 1
            threads.add((o.get("link_id") or "")[3:] if kind == "c" else o.get("id"))
    print(f"  {path.name}: {n:,} matching items", flush=True)
threads.discard(None)
threads.discard("")
print(f"{len(threads):,} distinct threads to pull\n", flush=True)

# ── Pass 2: pull those threads whole ────────────────────────────────────────
posts_out: dict[str, dict] = {}
with POSTS.open("rb") as fh:
    for b in fh:
        try:
            o = json.loads(b)
        except Exception:
            continue
        pid = o.get("id")
        if pid not in threads:
            continue
        posts_out[pid] = {
            "post_id": pid, "title": o.get("title") or "", "body": clean(o.get("selftext")),
            "author_hash": hash_author(o.get("author")), "created_utc": iso(o["created_utc"]),
            "score": int(o.get("score") or 0), "flair": o.get("link_flair_text") or "",
            "url": f"https://www.reddit.com{o.get('permalink', '') or f'/r/Nootropics/comments/{pid}/'}",
            "num_comments_api": int(o.get("num_comments") or 0),
            "comments_fetched": 0, "comments": [],
        }
print(f"matched {len(posts_out):,} post bodies", flush=True)

orphan = 0
with COMMENTS.open("rb") as fh:
    for b in fh:
        try:
            o = json.loads(b)
        except Exception:
            continue
        link = (o.get("link_id") or "")[3:]
        if link not in threads:
            continue
        if link not in posts_out:
            orphan += 1
            continue
        posts_out[link]["comments"].append({
            "comment_id": o["id"], "body": clean(o.get("body")),
            "author_hash": hash_author(o.get("author")), "created_utc": iso(o["created_utc"]),
            "score": int(o.get("score") or 0), "parent_id": o.get("parent_id") or "",
        })

for p in posts_out.values():
    p["comments"].sort(key=lambda c: c["created_utc"])
    p["comments_fetched"] = len(p["comments"])

out = sorted(posts_out.values(), key=lambda p: p["created_utc"])
dst = HERE / "source"
dst.mkdir(parents=True, exist_ok=True)
# variable_extraction's Corpus() looks for this exact filename
(dst / "subreddit_posts.json").write_text(json.dumps(out), encoding="utf-8")

n_c = sum(len(p["comments"]) for p in out)
print(f"\nwrote {dst / 'subreddit_posts.json'}")
print(f"  {len(out):,} posts + {n_c:,} comments = {len(out) + n_c:,} items "
      f"({(dst / 'subreddit_posts.json').stat().st_size / 1e6:.0f} MB)")
print(f"  {orphan:,} comments dropped (parent submission absent from the posts dump)")
print(f"  distinct authors: "
      f"{len({p['author_hash'] for p in out} | {c['author_hash'] for p in out for c in p['comments']}):,}")
