#!/usr/bin/env python3
"""
canonicalize.py — Normalize drug synonyms.

Step 2 of the pipeline. Merges synonyms (e.g. "low dose naltrexone" → "ldn")
and rewrites tagged_mentions.json with canonical names.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utilities import MODEL_FAST, parse_json_object, log
from prompts.intervention_config import HAIKU_PROMPT
BATCH_SIZE = 50



def haiku_canonicalize(client, names: list[str]) -> dict[str, str]:
    """Ask Haiku to group synonyms among a list of drug names."""
    msg = HAIKU_PROMPT + f"\n\nDrug names to canonicalize:\n{json.dumps(names)}"
    resp = client.messages.create(
        model=MODEL_FAST,
        max_tokens=len(names) * 30,
        messages=[{"role": "user", "content": msg}],
    )
    result = parse_json_object(resp.content[0].text)
    # Ensure every input name is mapped
    for name in names:
        if name not in result:
            result[name] = name
    return result


def run_canonicalization(client, output_dir: Path):
    """Main canonicalization logic — called by pipeline or standalone."""
    tagged_path = output_dir / "tagged_mentions.json"
    canon_path = output_dir / "canonical_map.json"

    tagged = json.loads(tagged_path.read_text())
    log.info(f"Loaded {len(tagged)} tagged entries.")

    # Collect all unique drug names
    all_drugs = {d for e in tagged for d in e.get("drugs_direct", []) + e.get("drugs_context", [])}
    log.info(f"Found {len(all_drugs)} unique drug names.")

    # Batch through Haiku
    canon_map = {}
    all_drugs_sorted = sorted(all_drugs)

    for i in range(0, len(all_drugs_sorted), BATCH_SIZE):
        batch = all_drugs_sorted[i:i + BATCH_SIZE]
        try:
            canon_map.update(haiku_canonicalize(client, batch))
        except Exception as e:
            log.error(f"Haiku error on batch {i}: {e}")
            for name in batch:
                canon_map[name] = name
        log.info(f"Canonicalized {min(i + BATCH_SIZE, len(all_drugs_sorted))}/{len(all_drugs_sorted)}...")

    # Save canonical map
    canon_path.write_text(json.dumps(canon_map, indent=2, sort_keys=True))
    log.info(f"Wrote {canon_path.name}")

    # Print summary
    groups = defaultdict(list)
    for raw, canonical in canon_map.items():
        if raw != canonical:
            groups[canonical].append(raw)
    if groups:
        log.info(f"Synonym groups found ({len(groups)}):")
        for canonical, synonyms in sorted(groups.items()):
            log.info(f"  {canonical} ← {', '.join(synonyms)}")

    # Rewrite tagged_mentions.json
    def canonicalize_list(drugs: list[str]) -> list[str]:
        return list(dict.fromkeys(canon_map.get(d, d) for d in drugs))

    for entry in tagged:
        entry["drugs_direct"] = canonicalize_list(entry.get("drugs_direct", []))
        entry["drugs_context"] = canonicalize_list(entry.get("drugs_context", []))

    tagged_path.write_text(json.dumps(tagged, indent=2))
    log.info(f"Rewrote {tagged_path.name} with canonical drug names.")


def main():
    """Standalone entry point."""
    import argparse
    from utilities import get_client

    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, help="Directory containing tagged_mentions.json")
    args = parser.parse_args()

    run_canonicalization(get_client(), Path(args.output_dir))


if __name__ == "__main__":
    main()
