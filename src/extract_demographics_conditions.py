#!/usr/bin/env python3
"""
run_demographics.py — Extract demographics and conditions from user posts.

Reads from the posts table, groups by user, sends to Haiku for extraction,
and writes to user_profiles and conditions tables.

Usage:
    python src/run_demographics.py --db data/posts.db
    python src/run_demographics.py --db data/posts.db --limit 50
"""
import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utilities.db import open_db
from utilities import get_client, get_git_commit, llm_call, log, parse_json_object, MODEL_FAST
from prompts.demographic_prompt import DEMOGRAPHICS_PROMPT


# ═════════════════════════════════════════════════════════════════════════════
# LLM extraction
# ═════════════════════════════════════════════════════════════════════════════

def extract_demographics(client, texts: list[str], *, max_posts: int = 10, max_chars: int = 500) -> dict:
    """Call Haiku to extract demographics from a user's posts."""
    combined = "\n---\n".join(t[:max_chars] for t in texts[:max_posts])
    raw = llm_call(client, DEMOGRAPHICS_PROMPT + combined, model=MODEL_FAST, max_tokens=300)
    try:
        result = parse_json_object(raw)
    except Exception:
        return {"age_bucket": None, "sex": None, "location": None, "conditions": []}
    return {
        "age_bucket": result.get("age_bucket"),
        "sex": result.get("sex"),
        "location": result.get("location"),
        "conditions": result.get("conditions") or [],
    }


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════


def run_demographics(db_path: Path, *, limit: int = 0, max_posts: int = 10, max_chars: int = 500):
    client = get_client()
    conn = open_db(db_path)

    with closing(open_db(db_path)) as conn:
        # Create extraction run
        run_config = {"limit": limit, "model": MODEL_FAST, "max_posts": max_posts, "max_chars": max_chars}
        cursor = conn.execute(
            "INSERT INTO extraction_runs (run_at, commit_hash, extraction_type, config) VALUES (?, ?, ?, ?)",
            (int(time.time()), get_git_commit(), "demographics", json.dumps(run_config)),
        )
        run_id = cursor.lastrowid
        conn.commit()
        log.info(f"Extraction run {run_id}")

    # Load posts grouped by user (limit applies to number of distinct users)
    rows = conn.execute(
        "SELECT p.user_id, p.body_text FROM posts p "
        + ("INNER JOIN (SELECT DISTINCT user_id FROM posts LIMIT ?) u ON p.user_id = u.user_id " if limit else "")
        + "ORDER BY p.user_id, p.post_date",
        (limit,) if limit else (),
    ).fetchall()

    users: dict[str, list[str]] = defaultdict(list)
    for user_id, body in rows:
        users[user_id].append(body)

    log.info(f"Processing {len(users)} users ({len(rows)} posts)")

    profiles_written = 0
    conditions_written = 0

    for i, (user_id, texts) in enumerate(users.items()):
        result = extract_demographics(client, texts, max_posts=max_posts, max_chars=max_chars)

        age_bucket, sex, location = result["age_bucket"], result["sex"], result["location"]
        if any([age_bucket, sex, location]):
            conn.execute(
                "INSERT OR REPLACE INTO user_profiles (user_id, run_id, age_bucket, sex, location) "
                "VALUES (?, ?, ?, ?, ?)"p,
                (user_id, run_id, age_bucket, sex, location),
            )
            profiles_written += 1

        for cond in result.get("conditions", []):
            name = cond.get("condition_name", "").strip().lower()
            ctype = cond.get("condition_type", "illness")
            if ctype not in ("illness", "symptom"):
                ctype = "illness"
            if name:
                conn.execute(
                    "INSERT INTO conditions (run_id, user_id, post_id, condition_type, condition_name, severity) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (run_id, user_id, None, ctype, name, None),
                )
                conditions_written += 1

        if (i + 1) % 10 == 0:
            log.info(f"  ... {i + 1}/{len(users)} users")

    conn.commit()
    conn.close()
    log.info(f"Done: {profiles_written} profiles, {conditions_written} conditions written")


def main():
    parser = argparse.ArgumentParser(description="Extract demographics and conditions from user posts")
    parser.add_argument("--db", required=True, help="Path to SQLite database")
    parser.add_argument("--limit", type=int, default=0, help="Limit to N users (0 = all)")
    parser.add_argument("--max-posts", type=int, default=10, help="Max posts per user to send to LLM")
    parser.add_argument("--max-chars", type=int, default=500, help="Max characters per post to send to LLM")
    args = parser.parse_args()

    run_demographics(Path(args.db), limit=args.limit, max_posts=args.max_posts, max_chars=args.max_chars)


if __name__ == "__main__":
    main()
