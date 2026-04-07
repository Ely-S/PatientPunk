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
    python src/run_pipeline.py --posts-file data/posts.json --output-dir outputs extract
    # Or standalone (run from src/):
    python -m scripts.extract_mentions --posts-file ../data/posts.json --output-dir ../outputs
"""
import json
from collections import Counter
from functools import cache
from pathlib import Path
from typing import NamedTuple, TYPE_CHECKING

if TYPE_CHECKING:
    from utilities import PipelineConfig

from prompts.intervention_config import EXTRACT_PROMPT
from utilities import (
    OutputFiles, MODEL_FAST, llm_call, parse_json_array, 
    process_in_batches, log
)

BATCH_SIZE = 20
SAVE_EVERY = 5


class PostData(NamedTuple):
    item_id: str
    text: str
    author: str
    parent_id: str | None
    post_title: str
    created_utc: int


def extract_batch(client, texts: list[str], _depth: int = 0) -> list[list[str]]:
    """Ask Haiku to extract drug mentions from a batch of texts."""
    msg = EXTRACT_PROMPT + "\n" + "".join(
        f"--- {i+1} ---\n{text[:600]}\n\n" for i, text in enumerate(texts)
    )
    raw = llm_call(client, msg, model=MODEL_FAST, max_tokens=len(texts) * 80)
    results = parse_json_array(raw)

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


def run_extraction(config: "PipelineConfig"):
    """Main extraction logic — called by pipeline or standalone."""
    client = config.client
    tagged_path = config.path(OutputFiles.TAGGED_MENTIONS)

    posts = json.loads(config.posts_file.read_text())
    if config.limit:
        posts = posts[:config.limit]
    log.info(f"Loaded {len(posts)} posts.")

    # Load existing tagged_mentions as cache
    if tagged_path.exists() and not config.regenerate_cache:
        existing = json.loads(tagged_path.read_text())
        id_to_drugs = {e["id"]: e["drugs_direct"] for e in existing}
    else:
        id_to_drugs = {}

    # Collect all items
    all_items: list[PostData] = []
    id_to_parent = {}
    for post in posts:
        post_id, created_utc = post["post_id"], post["created_utc"]
        text = f"{post.get('title', '')} {post.get('body') or ''}".strip()
        all_items.append(PostData(item_id=post_id, text=text, author=post["author_hash"], parent_id=None, post_title=post.get("title", ""), created_utc=created_utc))
        id_to_parent[post_id] = None

        for c in post.get("comments", []):
            comment_id = c["comment_id"]
            all_items.append(PostData(
                item_id=comment_id, text=c.get("body", ""), author=c["author_hash"], parent_id=c.get("parent_id"), post_title=post.get("title", ""), created_utc=c.get("created_utc", created_utc)
            ))
            id_to_parent[comment_id] = c.get("parent_id")

    # Extract uncached items
    to_do = [(item_id, text) for item_id, text in ((item.item_id, item.text) for item in all_items) 
             if item_id not in id_to_drugs and text.strip()]
    log.info(f"{len(id_to_drugs)} cached, {len(to_do)} to extract...")

    def save_tagged():
        """Rebuild and save tagged_mentions.json."""
        ancestor_drugs = compute_ancestor_drugs(id_to_parent, id_to_drugs)
        tagged = [
            {"id": item.item_id, "author": item.author, "text": item.text, "post_title": item.post_title,
             "parent_id": item.parent_id, "created_utc": item.created_utc,
             "drugs_direct": id_to_drugs.get(item.item_id, []), "drugs_context": ancestor_drugs.get(item.item_id, [])}
            for item in all_items
            if id_to_drugs.get(item.item_id) or ancestor_drugs.get(item.item_id)
        ]
        tagged_path.write_text(json.dumps(tagged, indent=2))
        return tagged

    def process_batch(batch: list[tuple[str, str]]) -> list[list[str]]:
        texts = [text for _, text in batch]
        return extract_batch(client, texts)

    # Process batches
    results = process_in_batches(
        items=to_do,
        batch_size=BATCH_SIZE,
        process_fn=process_batch,
        progress_label="Extracted",
        save_fn=save_tagged,
        save_every=SAVE_EVERY,
    )

    # Update id_to_drugs with results
    for (item_id, _), drugs in zip(to_do, results):
        if drugs is None:
            id_to_drugs[item_id] = []
        else:
            id_to_drugs[item_id] = [d.lower().strip() for d in drugs]

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
    from utilities import PipelineConfig, get_client

    parser = argparse.ArgumentParser()
    parser.add_argument("--posts-file", required=True, help="Path to subreddit_posts.json")
    parser.add_argument("--output-dir", required=True, help="Directory for output files")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--regenerate-cache", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = PipelineConfig(
        client=get_client(),
        output_dir=output_dir,
        posts_file=Path(args.posts_file),
        limit=args.limit,
        regenerate_cache=args.regenerate_cache,
    )
    run_extraction(config)


if __name__ == "__main__":
    main()
