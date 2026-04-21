#!/usr/bin/env python3
"""
extract_mentions.py — Extract drug mentions from Reddit posts.

Step 1 of the pipeline. Reads posts from SQLite and outputs tagged_mentions.json
with drugs found in each post/comment (direct mentions + inherited from upstream comments).
"""
import itertools
import json
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utilities import PipelineConfig

from prompts.intervention_config import EXTRACT_PROMPT
from utilities import TAGGED_MENTIONS, MODEL_FAST, LLMParseError, llm_call, parse_json_array, log

BATCH_SIZE = 10
SAVE_EVERY = 50  # batches between checkpoint writes


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


def compute_upstream_mentioned_drugs(id_to_parent: dict, id_to_drugs: dict, max_depth: int | None = None) -> dict[str, list[str]]:
    """Pre-compute upstream mentioned drugs with memoization. max_depth=None means unlimited."""
    @lru_cache(maxsize=None)
    def upstream(eid: str, remaining: int | None) -> tuple[str, ...]:
        if remaining == 0:
            return ()
        parent_id = id_to_parent.get(eid)
        if not parent_id:
            return ()
        parent_drugs = tuple(id_to_drugs.get(parent_id, []))
        next_remaining = None if remaining is None else remaining - 1
        return tuple(dict.fromkeys(parent_drugs + upstream(parent_id, next_remaining)))

    return {eid: list(upstream(eid, max_depth)) for eid in id_to_parent}


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

    def save_tagged_atomic() -> list:
        """Recompute upstream context and write atomically via a temp file."""
        upstream_drugs = compute_upstream_mentioned_drugs(id_to_parent, id_to_drugs, config.max_upstream_depth)
        tagged = [
            {**item, "drugs_direct": id_to_drugs.get(item["id"], []),
             "drugs_context": upstream_drugs.get(item["id"], [])}
            for item in all_items
            if id_to_drugs.get(item["id"]) or upstream_drugs.get(item["id"])
        ]
        tmp = tagged_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(tagged, indent=2))
        tmp.replace(tagged_path)
        return tagged

    # Bounded parallel extraction: at most workers * 4 futures in flight at once.
    # As each future completes the next batch is submitted (backpressure).
    # Checkpoint written every SAVE_EVERY completed batches.
    all_batches = [to_do[i:i + BATCH_SIZE] for i in range(0, len(to_do), BATCH_SIZE)]
    batch_iter = iter(all_batches)
    done_ext = 0
    batches_since_save = 0
    max_inflight = max(config.workers * 4, 1)

    with ThreadPoolExecutor(max_workers=config.workers) as pool:
        pending: dict[Future, list] = {}

        # Seed the pool
        for batch in itertools.islice(batch_iter, max_inflight):
            f = pool.submit(extract_batch, client, [t for _, t in batch])
            pending[f] = batch

        while pending:
            future = next(as_completed(pending))
            batch = pending.pop(future)

            for (item_id, _), drugs in zip(batch, future.result()):
                flat = [str(d).lower().strip() for sublist in (drugs or []) for d in (sublist if isinstance(sublist, list) else [sublist]) if d]
                id_to_drugs[item_id] = flat

            done_ext += len(batch)
            done_ext += len(batch)
            if done_ext % (BATCH_SIZE * 100) == 0:
                save_tagged()
            log.info(f"Extracted {done_ext}/{len(to_do)}...")

            # Submit next batch to keep pool saturated
            next_batch = next(batch_iter, None)
            if next_batch is not None:
                f = pool.submit(extract_batch, client, [t for _, t in next_batch])
                pending[f] = next_batch

    tagged = save_tagged_atomic()

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
