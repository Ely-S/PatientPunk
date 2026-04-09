#!/usr/bin/env python3
"""
extract_mentions.py — optimized version
"""
import anthropic
import argparse, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from utilities import DATA_DIR

POSTS_FILE         = DATA_DIR / "subreddit_posts.json"
DEFAULT_OUTPUT_DIR = DATA_DIR / "outputs"
MODEL_FAST         = "claude-haiku-4-5-20251001"
BATCH_SIZE         = 20 # Sweet spot — faster than 20, safer than 40
SAVE_EVERY         = 5   # Save cache every N batches

EXTRACT_PROMPT = """\
For each text below, list all drugs, medications, supplements, and medical interventions mentioned.
Include brand names, generic names, abbreviations (e.g. LDN, LDA), and informal names.
Return ONLY a JSON array of arrays — one inner array per text, each containing lowercase strings.
If none are mentioned, use an empty array [].
Example: [["ldn", "low dose naltrexone"], ["famotidine", "pepcid"], []]
"""


def load_cache(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_cache(cache: dict, path: Path):
    path.write_text(encoding="utf-8", data=json.dumps(cache, indent=2))


def extract_batch(client, texts: list[str], _depth: int = 0) -> list[list[str]]:
    """Ask Haiku to extract drug mentions from a batch of texts."""
    msg = EXTRACT_PROMPT + "\n"
    for i, text in enumerate(texts):
        msg += f"--- {i+1} ---\n{text[:600]}\n\n"

    resp = client.messages.create(
        model=MODEL_FAST,
        max_tokens=len(texts) * 80,
        messages=[{"role": "user", "content": msg}],
    )
    raw = resp.content[0].text.strip()
    start, end = raw.find("["), raw.rfind("]") + 1
    results = json.loads(raw[start:end]) if start >= 0 else []

    if len(results) == len(texts):
        return results

    # Retry with smaller batches (up to 2 levels of recursion)
    if len(texts) > 1 and _depth < 2:
        print(f"  Mismatch ({len(results)}/{len(texts)}) — retrying as smaller batches...")
        mid = len(texts) // 2
        return extract_batch(client, texts[:mid], _depth + 1) + \
               extract_batch(client, texts[mid:], _depth + 1)

    print(f"  Warning: expected {len(texts)} results, got {len(results)} — giving up")
    return [[] for _ in texts]


def compute_all_ancestor_drugs(id_to_parent: dict[str, str | None],
                                id_to_drugs: dict[str, list[str]]) -> dict[str, list[str]]:
    """
    Pre-compute ancestor drugs for ALL items in one pass using memoization.
    Much faster than walking the chain for each item individually.
    """
    ancestor_cache: dict[str, list[str]] = {}

    def get_ancestors(eid: str) -> list[str]:
        if eid in ancestor_cache:
            return ancestor_cache[eid]

        parent_id = id_to_parent.get(eid)
        if not parent_id:
            ancestor_cache[eid] = []
            return []

        # Parent's direct drugs + parent's ancestors (deduplicated, order preserved)
        parent_drugs = id_to_drugs.get(parent_id, [])
        parent_ancestors = get_ancestors(parent_id)

        seen = set()
        result = []
        for drug in parent_drugs + parent_ancestors:
            if drug not in seen:
                seen.add(drug)
                result.append(drug)

        ancestor_cache[eid] = result
        return result

    # Pre-compute for all items
    for eid in id_to_parent:
        get_ancestors(eid)

    return ancestor_cache


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--limit", type=int, default=100,
                        help="Only process first N posts (default: 100)")
    parser.add_argument("--regenerate-cache", action="store_true",
                        help="Re-run Haiku extraction, ignoring cache")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = output_dir / "mentions_cache.json"

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY not set.")
    client = anthropic.Anthropic(api_key=api_key)

    posts = json.loads(POSTS_FILE.read_text(encoding="utf-8"))
    if args.limit:
        posts = posts[:args.limit]
    print(f"Loaded {len(posts)} posts.")

    cache = {} if args.regenerate_cache else load_cache(cache_path)

    # ── Step 1: collect all items ─────────────────────────────────────────────
    all_items = []
    id_to_parent: dict[str, str | None] = {}

    for post in posts:
        pid   = post["post_id"]
        title = post.get("title", "")
        body  = post.get("body") or ""
        ts    = post["created_utc"]

        all_items.append((pid, (title + " " + body).strip(),
                          post["author_hash"], None, title, ts))
        id_to_parent[pid] = None

        for c in post.get("comments", []):
            cid = c["comment_id"]
            all_items.append((cid, c.get("body", ""),
                               c["author_hash"], c.get("parent_id"), title,
                               c.get("created_utc", ts)))
            id_to_parent[cid] = c.get("parent_id")

    # ── Step 2: run Haiku extraction on uncached items ────────────────────────
    to_do = [(eid, text) for eid, text, *_ in all_items
             if eid not in cache and text.strip()]

    print(f"{len(cache)} cached, {len(to_do)} to extract...")

    batches_since_save = 0
    for i in range(0, len(to_do), BATCH_SIZE):
        batch = to_do[i:i + BATCH_SIZE]
        eids  = [eid for eid, _ in batch]
        texts = [text for _, text in batch]
        try:
            results = extract_batch(client, texts)
            for eid, drugs in zip(eids, results):
                print(eid, drugs)
                print("--------------------------------")
                cache[eid] = [d.lower().strip() for d in drugs]
        except Exception as e:
            print(f"  Batch error: {e}")
            for eid in eids:
                cache[eid] = []

        batches_since_save += 1
        if batches_since_save >= SAVE_EVERY:
            save_cache(cache, cache_path)
            batches_since_save = 0

        done = min(i + BATCH_SIZE, len(to_do))
        print(f"  Extracted {done}/{len(to_do)}...", end="\r", flush=True)

    # Final save
    if batches_since_save > 0:
        save_cache(cache, cache_path)

    if to_do:
        print()

    # ── Step 3: pre-compute ALL ancestor drugs (memoized) ───────────────────
    ancestor_drugs = compute_all_ancestor_drugs(id_to_parent, cache)

    # ── Step 4: build tagged entries ────────────────────────────────────────
    tagged = []
    for eid, text, author, parent_id, post_title, created_utc in all_items:
        drugs_direct  = cache.get(eid, [])
        drugs_context = ancestor_drugs.get(eid, [])

        if not drugs_direct and not drugs_context:
            continue

        tagged.append({
            "id":            eid,
            "author":        author,
            "text":          text,
            "post_title":    post_title,
            "parent_id":     parent_id,
            "created_utc":   created_utc,
            "drugs_direct":  drugs_direct,
            "drugs_context": drugs_context,
        })

    # ── Step 5: save ────────────────────────────────────────────────────────
    out_path = output_dir / "tagged_mentions.json"
    out_path.write_text(encoding="utf-8", data=json.dumps(tagged, indent=2))

    from collections import Counter
    drug_counts = Counter(d for e in tagged for d in e["drugs_direct"])
    print(f"\n{len(tagged)} entries tagged.")
    print(f"Top drug mentions (direct):")
    for drug, count in drug_counts.most_common(15):
        print(f"  {drug:<30} {count}")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()