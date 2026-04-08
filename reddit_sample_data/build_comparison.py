"""Build demographics_comparison.csv.

Compares three approaches for the same 100 subreddit posts:
  - pipeline: regex + LLM gap-fill (data/records.csv)
  - llm_post: Haiku-only on the single post text
  - llm_user: Haiku-only on the full user history (where available)

Rows:
  subreddit_post      - one row per post (100 total)
  user_history_only   - user history rows whose author has no post in our 100
"""

import collections
import csv
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent

# ── Load data ────────────────────────────────────────────────────────────────

posts_raw = json.load((ROOT / "reddit_sample_data/subreddit_posts.json").open())
post_to_hash = {p["post_id"]: p.get("author_hash") for p in posts_raw}

pipeline = {}
for row in csv.DictReader(
    open(ROOT / "data/records.csv", encoding="utf-8")
):
    pipeline[row["post_id"]] = row

llm_by_hash = {}   # subreddit_post rows, one per author_hash
llm_user = {}      # user_history rows, one per author_hash

for row in csv.DictReader(
    open(ROOT / "reddit_sample_data/demographics.csv", encoding="utf-8")
):
    h = row["author_hash"]
    if row["source_type"] == "subreddit_post":
        if h not in llm_by_hash:
            llm_by_hash[h] = row
        else:
            for f in ("age", "sex_gender", "location_country", "location_state"):
                if not llm_by_hash[h].get(f) and row.get(f):
                    llm_by_hash[h][f] = row[f]
    else:
        llm_user[h] = row


# ── Match status ─────────────────────────────────────────────────────────────

def match(a, b):
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    if not a and not b: return "both_empty"
    if a and not b:     return "pipeline_only"
    if not a and b:     return "llm_only"
    return "agree" if a == b else "disagree"


# ── Build rows ───────────────────────────────────────────────────────────────

out = []

for pid, p in sorted(pipeline.items()):
    h = post_to_hash.get(pid)
    l = llm_by_hash.get(h, {})
    u = llm_user.get(h, {})
    out.append({
        "author_hash":           h or "",
        "post_id":               pid,
        "source_type":           "subreddit_post",
        # pipeline
        "pipeline_age":          p.get("age", ""),
        "pipeline_sex":          p.get("sex_gender", ""),
        "pipeline_loc_country":  p.get("location_country", ""),
        "pipeline_loc_state":    p.get("location_us_state", ""),
        # llm post
        "llm_post_age":          l.get("age", ""),
        "llm_post_sex":          l.get("sex_gender", ""),
        "llm_post_loc_country":  l.get("location_country", ""),
        "llm_post_loc_state":    l.get("location_state", ""),
        "llm_post_confidence":   l.get("confidence", ""),
        "llm_post_evidence":     l.get("evidence", ""),
        # llm user history (same author)
        "llm_user_age":          u.get("age", ""),
        "llm_user_sex":          u.get("sex_gender", ""),
        "llm_user_loc_country":  u.get("location_country", ""),
        "llm_user_loc_state":    u.get("location_state", ""),
        "llm_user_confidence":   u.get("confidence", ""),
        "llm_user_evidence":     u.get("evidence", ""),
        # match flags
        "age_pipe_vs_llmpost":   match(p.get("age"), l.get("age")),
        "sex_pipe_vs_llmpost":   match(p.get("sex_gender"), l.get("sex_gender")),
        "loc_pipe_vs_llmpost":   match(p.get("location_country"), l.get("location_country")),
        "age_pipe_vs_llmuser":   match(p.get("age"), u.get("age")),
        "sex_pipe_vs_llmuser":   match(p.get("sex_gender"), u.get("sex_gender")),
        "loc_pipe_vs_llmuser":   match(p.get("location_country"), u.get("location_country")),
        "age_llmpost_vs_llmuser":  match(l.get("age"), u.get("age")),
        "sex_llmpost_vs_llmuser":  match(l.get("sex_gender"), u.get("sex_gender")),
        "loc_llmpost_vs_llmuser":  match(l.get("location_country"), u.get("location_country")),
    })

# User histories with no matching subreddit post in our 100
post_hashes = set(h for h in post_to_hash.values() if h)
for h, u in sorted(llm_user.items()):
    if h not in post_hashes:
        out.append({
            "author_hash":           h,
            "post_id":               "",
            "source_type":           "user_history_only",
            "pipeline_age": "",    "pipeline_sex": "",
            "pipeline_loc_country": "", "pipeline_loc_state": "",
            "llm_post_age": "",    "llm_post_sex": "",
            "llm_post_loc_country": "", "llm_post_loc_state": "",
            "llm_post_confidence": "", "llm_post_evidence": "",
            "llm_user_age":          u.get("age", ""),
            "llm_user_sex":          u.get("sex_gender", ""),
            "llm_user_loc_country":  u.get("location_country", ""),
            "llm_user_loc_state":    u.get("location_state", ""),
            "llm_user_confidence":   u.get("confidence", ""),
            "llm_user_evidence":     u.get("evidence", ""),
            "age_pipe_vs_llmpost":   "n/a", "sex_pipe_vs_llmpost": "n/a", "loc_pipe_vs_llmpost": "n/a",
            "age_pipe_vs_llmuser":   "n/a", "sex_pipe_vs_llmuser": "n/a", "loc_pipe_vs_llmuser": "n/a",
            "age_llmpost_vs_llmuser": "n/a", "sex_llmpost_vs_llmuser": "n/a", "loc_llmpost_vs_llmuser": "n/a",
        })

# ── Write ────────────────────────────────────────────────────────────────────

fieldnames = [
    "author_hash", "post_id", "source_type",
    "pipeline_age", "pipeline_sex", "pipeline_loc_country", "pipeline_loc_state",
    "llm_post_age", "llm_post_sex", "llm_post_loc_country", "llm_post_loc_state",
    "llm_post_confidence", "llm_post_evidence",
    "llm_user_age", "llm_user_sex", "llm_user_loc_country", "llm_user_loc_state",
    "llm_user_confidence", "llm_user_evidence",
    "age_pipe_vs_llmpost",  "sex_pipe_vs_llmpost",  "loc_pipe_vs_llmpost",
    "age_pipe_vs_llmuser",  "sex_pipe_vs_llmuser",  "loc_pipe_vs_llmuser",
    "age_llmpost_vs_llmuser", "sex_llmpost_vs_llmuser", "loc_llmpost_vs_llmuser",
]

out_path = ROOT / "reddit_sample_data/demographics_comparison.csv"
with open(out_path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(out)

# ── Summary ──────────────────────────────────────────────────────────────────

post_rows = [r for r in out if r["source_type"] == "subreddit_post"]
user_only  = [r for r in out if r["source_type"] == "user_history_only"]

def tally(rows, key):
    c = collections.Counter(r[key] for r in rows)
    return (f"agree={c['agree']:3d}  disagree={c['disagree']:3d}  "
            f"pipeline_only={c['pipeline_only']:3d}  llm_only={c['llm_only']:3d}  "
            f"both_empty={c['both_empty']:3d}")

print(f"\nOutput: {out_path}")
print(f"Rows:   {len(out)}  ({len(post_rows)} subreddit_post, {len(user_only)} user_history_only)\n")

print("Pipeline (regex+LLM) vs LLM-post only — for 100 subreddit posts:")
for field in ("age", "sex", "loc"):
    print(f"  {field}: {tally(post_rows, field+'_pipe_vs_llmpost')}")

print("\nPipeline (regex+LLM) vs LLM-user history — for same author:")
for field in ("age", "sex", "loc"):
    print(f"  {field}: {tally(post_rows, field+'_pipe_vs_llmuser')}")

print("\nLLM-post vs LLM-user history — for same author:")
for field in ("age", "sex", "loc"):
    print(f"  {field}: {tally(post_rows, field+'_llmpost_vs_llmuser')}")

print("\nLLM user history (user_history_only rows — no matching post):")
for field in ("llm_user_age", "llm_user_sex", "llm_user_loc_country"):
    filled = sum(1 for r in user_only if r.get(field))
    print(f"  {field}: {filled}/{len(user_only)} filled")
