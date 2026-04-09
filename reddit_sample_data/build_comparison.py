"""Build demographics_comparison.csv.

Compares three approaches for the same 100 subreddit posts:
  - pipeline: regex + LLM gap-fill (data/records.csv)
  - llm_post: Haiku-only on the single post text
  - llm_user: Haiku-only on the full user history (where available)

Rows:
  subreddit_post      -- one row per post (100 total)
  user_history_only   -- user history rows whose author has no post in our 100
"""

import collections
import csv
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent

# ── Load data ────────────────────────────────────────────────────────────────

posts_raw = json.load((ROOT / "reddit_sample_data/subreddit_posts.json").open())
post_to_hash = {post["post_id"]: post.get("author_hash") for post in posts_raw}

with open(ROOT / "data/records.csv", encoding="utf-8") as records_csv:
    pipeline = {row["post_id"]: row for row in csv.DictReader(records_csv)}

llm_by_hash = {}   # subreddit_post rows, one per author_hash
llm_user = {}      # user_history rows, one per author_hash

with open(ROOT / "reddit_sample_data/demographics.csv", encoding="utf-8") as demo_csv:
    for row in csv.DictReader(demo_csv):
        author_hash = row["author_hash"]
        if row["source_type"] == "subreddit_post":
            if author_hash not in llm_by_hash:
                llm_by_hash[author_hash] = row
            else:
                for field in ("age", "sex_gender", "location_country", "location_state"):
                    if not llm_by_hash[author_hash].get(field) and row.get(field):
                        llm_by_hash[author_hash][field] = row[field]
        else:
            llm_user[author_hash] = row


# ── Match status ─────────────────────────────────────────────────────────────

def match(value_a: str | None, value_b: str | None) -> str:
    """Compare two extracted field values, returning a match category.

    Returns one of: 'both_empty', 'pipeline_only', 'llm_only', 'agree', 'disagree'.
    Comparison is case-insensitive and strips whitespace.
    """
    value_a = (value_a or "").strip().lower()
    value_b = (value_b or "").strip().lower()
    if not value_a and not value_b:
        return "both_empty"
    if value_a and not value_b:
        return "pipeline_only"
    if not value_a and value_b:
        return "llm_only"
    return "agree" if value_a == value_b else "disagree"


# ── Build rows ───────────────────────────────────────────────────────────────

out = []

for post_id, pipe_row in sorted(pipeline.items()):
    author_hash = post_to_hash.get(post_id)
    llm_post_row = llm_by_hash.get(author_hash, {})
    llm_user_row = llm_user.get(author_hash, {})
    out.append({
        "author_hash":           author_hash or "",
        "post_id":               post_id,
        "source_type":           "subreddit_post",
        # pipeline
        "pipeline_age":          pipe_row.get("age", ""),
        "pipeline_sex":          pipe_row.get("sex_gender", ""),
        "pipeline_loc_country":  pipe_row.get("location_country", ""),
        "pipeline_loc_state":    pipe_row.get("location_us_state", ""),
        # llm post
        "llm_post_age":          llm_post_row.get("age", ""),
        "llm_post_sex":          llm_post_row.get("sex_gender", ""),
        "llm_post_loc_country":  llm_post_row.get("location_country", ""),
        "llm_post_loc_state":    llm_post_row.get("location_state", ""),
        "llm_post_confidence":   llm_post_row.get("confidence", ""),
        "llm_post_evidence":     llm_post_row.get("evidence", ""),
        # llm user history (same author)
        "llm_user_age":          llm_user_row.get("age", ""),
        "llm_user_sex":          llm_user_row.get("sex_gender", ""),
        "llm_user_loc_country":  llm_user_row.get("location_country", ""),
        "llm_user_loc_state":    llm_user_row.get("location_state", ""),
        "llm_user_confidence":   llm_user_row.get("confidence", ""),
        "llm_user_evidence":     llm_user_row.get("evidence", ""),
        # match flags
        "age_pipe_vs_llmpost":   match(pipe_row.get("age"), llm_post_row.get("age")),
        "sex_pipe_vs_llmpost":   match(pipe_row.get("sex_gender"), llm_post_row.get("sex_gender")),
        "loc_pipe_vs_llmpost":   match(pipe_row.get("location_country"), llm_post_row.get("location_country")),
        "age_pipe_vs_llmuser":   match(pipe_row.get("age"), llm_user_row.get("age")),
        "sex_pipe_vs_llmuser":   match(pipe_row.get("sex_gender"), llm_user_row.get("sex_gender")),
        "loc_pipe_vs_llmuser":   match(pipe_row.get("location_country"), llm_user_row.get("location_country")),
        "age_llmpost_vs_llmuser":  match(llm_post_row.get("age"), llm_user_row.get("age")),
        "sex_llmpost_vs_llmuser":  match(llm_post_row.get("sex_gender"), llm_user_row.get("sex_gender")),
        "loc_llmpost_vs_llmuser":  match(llm_post_row.get("location_country"), llm_user_row.get("location_country")),
    })

# User histories with no matching subreddit post in our 100
post_hashes = {hash_ for hash_ in post_to_hash.values() if hash_}
for author_hash, llm_user_row in sorted(llm_user.items()):
    if author_hash not in post_hashes:
        out.append({
            "author_hash":           author_hash,
            "post_id":               "",
            "source_type":           "user_history_only",
            "pipeline_age": "",    "pipeline_sex": "",
            "pipeline_loc_country": "", "pipeline_loc_state": "",
            "llm_post_age": "",    "llm_post_sex": "",
            "llm_post_loc_country": "", "llm_post_loc_state": "",
            "llm_post_confidence": "", "llm_post_evidence": "",
            "llm_user_age":          llm_user_row.get("age", ""),
            "llm_user_sex":          llm_user_row.get("sex_gender", ""),
            "llm_user_loc_country":  llm_user_row.get("location_country", ""),
            "llm_user_loc_state":    llm_user_row.get("location_state", ""),
            "llm_user_confidence":   llm_user_row.get("confidence", ""),
            "llm_user_evidence":     llm_user_row.get("evidence", ""),
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
with open(out_path, "w", newline="", encoding="utf-8") as out_file:
    writer = csv.DictWriter(out_file, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(out)

# ── Summary ──────────────────────────────────────────────────────────────────

post_rows = [r for r in out if r["source_type"] == "subreddit_post"]
user_only  = [r for r in out if r["source_type"] == "user_history_only"]

def tally(rows: list, key: str) -> str:
    """Count match categories across rows for a given comparison key."""
    counts = collections.Counter(row[key] for row in rows)
    return (f"agree={counts['agree']:3d}  disagree={counts['disagree']:3d}  "
            f"pipeline_only={counts['pipeline_only']:3d}  llm_only={counts['llm_only']:3d}  "
            f"both_empty={counts['both_empty']:3d}")

print(f"\nOutput: {out_path}")
print(f"Rows:   {len(out)}  ({len(post_rows)} subreddit_post, {len(user_only)} user_history_only)\n")

print("Pipeline (regex+LLM) vs LLM-post only -- for 100 subreddit posts:")
for field in ("age", "sex", "loc"):
    print(f"  {field}: {tally(post_rows, field+'_pipe_vs_llmpost')}")

print("\nPipeline (regex+LLM) vs LLM-user history -- for same author:")
for field in ("age", "sex", "loc"):
    print(f"  {field}: {tally(post_rows, field+'_pipe_vs_llmuser')}")

print("\nLLM-post vs LLM-user history -- for same author:")
for field in ("age", "sex", "loc"):
    print(f"  {field}: {tally(post_rows, field+'_llmpost_vs_llmuser')}")

print("\nLLM user history (user_history_only rows -- no matching post):")
for field in ("llm_user_age", "llm_user_sex", "llm_user_loc_country"):
    filled = sum(1 for r in user_only if r.get(field))
    print(f"  {field}: {filled}/{len(user_only)} filled")
