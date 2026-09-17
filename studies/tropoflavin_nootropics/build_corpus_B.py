"""Build pipeline B's input: one users/<author_hash>.json per 7,8-DHF mentioner.

Pipeline B has no --drug flag. Its unit is the patient, not the drug, so the
equivalent of targeting is a pre-filtered corpus: only authors who named the
compound themselves.

subreddit_posts.json cannot be used for this. Corpus._texts_from_post reads
title+body only and deliberately excludes comments ("other users' text"), so
feeding it the thread corpus would extract 1,047 post authors and silently drop
all 1,448 comment mentions. Commenters only reach the extractor via users/.
"""
from __future__ import annotations
import json, re, sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
SRC = HERE / "source" / "subreddit_posts.json"
OUT = HERE / "source_B" / "users"

PAT = re.compile(r"(?i)(tropoflavin|hydroxyflavone|\b7[ .,'-]{0,2}8[ .,'-]{0,2}dhf\b|\bdhf\b)")


def epoch(iso_s: str) -> int:
    try:
        return int(datetime.fromisoformat(iso_s).timestamp())
    except Exception:
        return 0


corpus = json.loads(SRC.read_text(encoding="utf-8"))

# Pass 1 — who named it?
mentioners: set[str] = set()
for p in corpus:
    if PAT.search((p.get("title") or "") + " " + (p.get("body") or "")):
        mentioners.add(p["author_hash"])
    for c in p["comments"]:
        if PAT.search(c.get("body") or ""):
            mentioners.add(c["author_hash"])
mentioners.discard("deleted")
print(f"{len(mentioners):,} distinct authors named the compound")

# Pass 2 — collect everything those authors wrote inside these threads
users: dict[str, dict] = {
    a: {"author_hash": a, "account_created_utc": None, "total_karma": None,
        "scraped_at": None, "posts": [], "comments": []}
    for a in mentioners
}
for p in corpus:
    a = p["author_hash"]
    if a in users:
        users[a]["posts"].append({
            "post_id": p["post_id"], "subreddit": "Nootropics",
            "title": p.get("title") or "", "body": p.get("body") or "",
            "created_utc": epoch(p["created_utc"]), "score": p.get("score", 0),
            "num_comments": p.get("num_comments_api", 0),
        })
    for c in p["comments"]:
        a = c["author_hash"]
        if a in users:
            users[a]["comments"].append({
                "comment_id": c["comment_id"], "subreddit": "Nootropics",
                "body": c.get("body") or "", "created_utc": epoch(c["created_utc"]),
                "score": c.get("score", 0), "parent_id": c.get("parent_id") or "",
            })

OUT.mkdir(parents=True, exist_ok=True)
for old in OUT.glob("*.json"):
    old.unlink()

kept = 0
for a, u in users.items():
    if not u["posts"] and not u["comments"]:
        continue
    (OUT / f"{a}.json").write_text(json.dumps(u), encoding="utf-8")
    kept += 1

n_p = sum(len(u["posts"]) for u in users.values())
n_c = sum(len(u["comments"]) for u in users.values())
print(f"wrote {kept:,} user files to {OUT}")
print(f"  {n_p:,} posts + {n_c:,} comments = {n_p + n_c:,} texts")
print(f"  median items/author: "
      f"{sorted(len(u['posts']) + len(u['comments']) for u in users.values())[kept // 2]}")
