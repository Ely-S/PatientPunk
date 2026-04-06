#!/usr/bin/env python3
"""
extract_mentions.py — Extract drug mentions from Reddit posts.

Step 1 of the pipeline. Outputs tagged_mentions.json with drugs found in each post/comment.
This includes the drugs found in the direct text of the post/comment and the drugs 
found in the ancestor posts/comments.
The output file is tagged_mentions.json.
The output format is:
    {
        "id": "t3_1scqprg",
        "author": "u_1234567890",
        "text": "I took 100mg of LSD last night and it was amazing!",
        "post_title": "I took 100mg of LSD last night and it was amazing!",
        "parent_id": "t3_1scq2ks",
        "created_utc": 1717334400,
        "drugs_direct": ["lsd"],
        "drugs_context": ["psychedelic"]
    }
Usage:
    python src/scripts/extract_mentions.py --posts-file data/subreddit_posts.json --output-dir data/outputs
    python src/scripts/extract_mentions.py --posts-file data/subreddit_posts.json --output-dir data/outputs --limit 50 regenerate-cache
"""
import json
import sys
from collections import Counter
from functools import cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from prompts.intervention_config import EXTRACT_PROMPT
from utilities import MODEL_FAST, parse_json_array, log

BATCH_SIZE = 20
SAVE_EVERY = 5


def extract_batch(client, texts: list[str], _depth: int = 0) -> list[list[str]]:
    """Ask Haiku to extract drug mentions from a batch of texts."""
    msg = EXTRACT_PROMPT + "\n" + "".join(
        f"--- {i+1} ---\n{text[:600]}\n\n" for i, text in enumerate(texts)
    )
    resp = client.messages.create(
        model=MODEL_FAST,
        max_tokens=len(texts) * 80,
        messages=[{"role": "user", "content": msg}],
    )
    results = parse_json_array(resp.content[0].text)

    if len(results) == len(texts):
        return results

    # Retry with smaller batches (up to 2 levels of recursion)
    if len(texts) > 1 and _depth < 2:
        log.warning(f"Mismatch ({len(results)}/{len(texts)}) — retrying as smaller batches...")
        mid = len(texts) // 2
        return extract_batch(client, texts[:mid], _depth + 1) + extract_batch(client, texts[mid:], _depth + 1)

    log.warning(f"Expected {len(texts)} results, got {len(results)}")
    return [[] for _ in texts]


def compute_ancestor_drugs(id_to_parent: dict, id_to_drugs: dict) -> dict[str, list[str]]:
    """Pre-compute ancestor drugs using memoization."""
    @cache
    def ancestors(eid: str) -> tuple[str, ...]:
        parent_id = id_to_parent.get(eid)
        if not parent_id:
            return ()
        parent_drugs = tuple(id_to_drugs.get(parent_id, []))
        return tuple(dict.fromkeys(parent_drugs + ancestors(parent_id)))

    return {eid: list(ancestors(eid)) for eid in id_to_parent}


def run_extraction(client, output_dir: Path, posts_file: Path, limit: int = 100, regenerate_cache: bool = False):
    """Main extraction logic — called by pipeline or standalone."""
    tagged_path = output_dir / "tagged_mentions.json"

    posts = json.loads(posts_file.read_text())
    if limit:
        posts = posts[:limit]
    log.info(f"Loaded {len(posts)} posts.")

    # Load existing tagged_mentions as cache
    if tagged_path.exists() and not regenerate_cache:
        existing = json.loads(tagged_path.read_text())
        id_to_drugs = {e["id"]: e["drugs_direct"] for e in existing}
    else:
        id_to_drugs = {}

    # Collect all items
    all_items, id_to_parent = [], {}
    for post in posts:
        pid, ts = post["post_id"], post["created_utc"]
        text = f"{post.get('title', '')} {post.get('body') or ''}".strip()
        all_items.append((pid, text, post["author_hash"], None, post.get("title", ""), ts))
        id_to_parent[pid] = None

        for c in post.get("comments", []):
            cid = c["comment_id"]
            all_items.append((cid, c.get("body", ""), c["author_hash"], c.get("parent_id"),
                             post.get("title", ""), c.get("created_utc", ts)))
            id_to_parent[cid] = c.get("parent_id")

    # Extract uncached items
    to_do = [(eid, text) for eid, text, *_ in all_items if eid not in id_to_drugs and text.strip()]
    log.info(f"{len(id_to_drugs)} cached, {len(to_do)} to extract...")

    def save_tagged():
        """Rebuild and save tagged_mentions.json."""
        ancestor_drugs = compute_ancestor_drugs(id_to_parent, id_to_drugs)
        tagged = [
            {"id": eid, "author": author, "text": text, "post_title": title,
             "parent_id": parent_id, "created_utc": ts,
             "drugs_direct": id_to_drugs.get(eid, []), "drugs_context": ancestor_drugs.get(eid, [])}
            for eid, text, author, parent_id, title, ts in all_items
            if id_to_drugs.get(eid) or ancestor_drugs.get(eid)
        ]
        tagged_path.write_text(json.dumps(tagged, indent=2))
        return tagged

    batches_since_save = 0
    for i in range(0, len(to_do), BATCH_SIZE):
        batch = to_do[i:i + BATCH_SIZE]
        eids, texts = zip(*batch) if batch else ([], [])
        try:
            for eid, drugs in zip(eids, extract_batch(client, list(texts))):
                id_to_drugs[eid] = [d.lower().strip() for d in drugs]
        except Exception as e:
            log.error(f"Batch error: {e}")
            for eid in eids:
                id_to_drugs[eid] = []

        batches_since_save += 1
        if batches_since_save >= SAVE_EVERY:
            save_tagged()
            batches_since_save = 0
        log.info(f"Extracted {min(i + BATCH_SIZE, len(to_do))}/{len(to_do)}...")

    # Final save
    tagged = save_tagged()

    drug_counts = Counter(d for e in tagged for d in e["drugs_direct"])
    log.info(f"{len(tagged)} entries tagged.")
    log.info("Top drug mentions:")
    for drug, count in drug_counts.most_common(10):
        log.info(f"  {drug:<30} {count}")
    log.info(f"Wrote {tagged_path}")


def main():
    """Standalone entry point."""
    import argparse
    from utilities import get_client

    parser = argparse.ArgumentParser()
    parser.add_argument("--posts-file", required=True, help="Path to subreddit_posts.json")
    parser.add_argument("--output-dir", required=True, help="Directory for output files")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--regenerate-cache", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_extraction(get_client(), output_dir, Path(args.posts_file), args.limit, args.regenerate_cache)


if __name__ == "__main__":
    main()
