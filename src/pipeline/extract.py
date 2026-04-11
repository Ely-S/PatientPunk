#!/usr/bin/env python3
"""
extract_mentions.py — Extract drug mentions from Reddit posts.

Step 1 of the pipeline. Reads posts from SQLite and outputs tagged_mentions.json
with drugs found in each post/comment (direct mentions + inherited from ancestors).
"""
import json
from collections import Counter
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utilities import PipelineConfig

from prompts.intervention_config import EXTRACT_PROMPT
from utilities import TAGGED_MENTIONS, MODEL_FAST, LLMParseError, llm_call, parse_json_array, log

BATCH_SIZE = 20
SAVE_EVERY = 5


def extract_batch(client, texts: list[str], _depth: int = 0) -> list[list[str]]:
    """Ask Haiku to extract drug mentions from a batch of texts."""
    msg = EXTRACT_PROMPT + "\n" + "".join(
        f"--- {i+1} ---\n{text}\n\n" for i, text in enumerate(texts)
    )
    raw = llm_call(client, msg, model=MODEL_FAST, max_tokens=len(texts) * 80)

    try:
        results = parse_json_array(raw)
    except LLMParseError as e:
        log.warning(f"Parse failed: {e}")
        results = []

    if len(results) == len(texts):
        return results

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


def load_posts_from_db(db_path: Path, limit: int | None = None):
    """Load posts from SQLite. Returns (items, id_to_parent).

    Each item is a dict with keys: id, text, author, parent_id, post_title, created_utc.
    """
    from utilities.db import open_db

    conn = open_db(db_path)
    rows = conn.execute(
        "SELECT post_id, title, parent_id, user_id, body_text, post_date "
        "FROM posts ORDER BY post_date"
    ).fetchall()
    conn.close()

    if limit:
        rows = rows[:limit]

    id_to_row = {r[0]: r for r in rows}

    _title_cache: dict[str, str] = {}

    def resolve_title(post_id: str) -> str:
        if post_id in _title_cache:
            return _title_cache[post_id]
        r = id_to_row.get(post_id)
        if r is None:
            _title_cache[post_id] = ""
            return ""
        if r[2] is None:  # top-level post
            _title_cache[post_id] = r[1] or ""
        else:
            _title_cache[post_id] = resolve_title(r[2])
        return _title_cache[post_id]

    items: list[dict] = []
    id_to_parent: dict[str, str | None] = {}

    for post_id, title, parent_id, user_id, body_text, post_date in rows:
        id_to_parent[post_id] = parent_id
        text = f"{title or ''} {body_text or ''}".strip() if parent_id is None else (body_text or "")
        items.append({
            "id": post_id, "text": text, "author": user_id,
            "parent_id": parent_id, "post_title": resolve_title(post_id),
            "created_utc": post_date or 0,
        })

    return items, id_to_parent


def run_extraction(config: "PipelineConfig"):
    """Main extraction logic — called by pipeline or standalone."""
    client = config.client
    tagged_path = config.path(TAGGED_MENTIONS)

    all_items, id_to_parent = load_posts_from_db(config.db_path, config.limit)
    log.info(f"Loaded {len(all_items)} posts/comments from database.")

    # Load existing tagged_mentions as cache
    if tagged_path.exists() and not config.reclassify:
        existing = json.loads(tagged_path.read_text())
        id_to_drugs = {e["id"]: e["drugs_direct"] for e in existing}
    else:
        id_to_drugs = {}

    to_do = [(item["id"], item["text"]) for item in all_items
             if item["id"] not in id_to_drugs and item["text"].strip()]
    log.info(f"{len(id_to_drugs)} cached, {len(to_do)} to extract...")

    def save_tagged():
        ancestor_drugs = compute_ancestor_drugs(id_to_parent, id_to_drugs)
        tagged = [
            {**item, "drugs_direct": id_to_drugs.get(item["id"], []),
             "drugs_context": ancestor_drugs.get(item["id"], [])}
            for item in all_items
            if id_to_drugs.get(item["id"]) or ancestor_drugs.get(item["id"])
        ]
        tagged_path.write_text(json.dumps(tagged, indent=2))
        return tagged

    # Process in batches
    batches_since_save = 0
    for i in range(0, len(to_do), BATCH_SIZE):
        batch = to_do[i:i + BATCH_SIZE]
        texts = [text for _, text in batch]
        batch_results = extract_batch(client, texts)
        for (item_id, _), drugs in zip(batch, batch_results):
            flat = []
            for d in (drugs or []):
                if isinstance(d, str):
                    flat.append(d.lower().strip())
                elif isinstance(d, list):
                    flat.extend(x.lower().strip() for x in d if isinstance(x, str))
            id_to_drugs[item_id] = flat

        batches_since_save += 1
        if batches_since_save >= SAVE_EVERY:
            save_tagged()
            batches_since_save = 0
        log.info(f"Extracted {min(i + BATCH_SIZE, len(to_do))}/{len(to_do)}...")

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
    parser.add_argument("--db", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--reclassify", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = PipelineConfig(
        client=get_client(), output_dir=output_dir,
        db_path=Path(args.db), limit=args.limit, reclassify=args.reclassify,
    )
    run_extraction(config)


if __name__ == "__main__":
    main()
