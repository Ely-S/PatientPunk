#!/usr/bin/env python3
"""
canonicalize.py

Step 1.5 of the drug mention database pipeline.

Collects all unique drug names from tagged_mentions.json, collapses true
synonyms (e.g. "low dose naltrexone" → "ldn") but keeps distinct drugs
separate even if related (e.g. "famotidine" and "antihistamines" are NOT merged).

Steps:
  1. Load all unique drug names from tagged_mentions.json
  2. Batch all through Haiku to find synonym groups
  3. Write canonical_map.json  — {"raw name": "canonical name", ...}
  4. Rewrite tagged_mentions.json with canonicalized drug names

Usage:
    python database_creation/canonicalize.py
"""
import anthropic
import argparse, json, os, sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from utilities import DATA_DIR

DEFAULT_OUTPUT_DIR = DATA_DIR / "outputs"
MODEL_FAST         = "claude-haiku-4-5-20251001"
BATCH_SIZE         = 50  # drug names per Haiku call


HAIKU_PROMPT = """\
You are given a list of drug/supplement/intervention names extracted from Reddit posts.
Your job is to identify true synonyms — names that refer to the exact same drug or compound.

Rules:
- Only group names if they refer to the EXACT same drug or compound.
- Do NOT group a specific drug into a broader category.
  e.g. "famotidine" and "antihistamines" are related but NOT the same — keep separate.
  e.g. "h1 blocker" and "antihistamines" are related but NOT the same — keep separate.
- Brand names and generic names for the same drug ARE synonyms.
  e.g. "pepcid" and "famotidine" → same drug → merge.
- Abbreviations for the same drug ARE synonyms.
  e.g. "ldn" and "low dose naltrexone" → same drug → merge.
- Choose the most common/recognizable name as the canonical form (usually generic name or common abbreviation).

Return a JSON object mapping every input name to its canonical form.
Every input name must appear as a key. If a name has no synonyms in the list, map it to itself.
Example: {"ldn": "ldn", "low dose naltrexone": "ldn", "pepcid": "famotidine", "famotidine": "famotidine"}
"""


def haiku_canonicalize(client, names: list[str]) -> dict[str, str]:
    """Ask Haiku to group synonyms among a list of drug names."""
    msg = HAIKU_PROMPT + f"\n\nDrug names to canonicalize:\n{json.dumps(names)}"
    resp = client.messages.create(
        model=MODEL_FAST,
        max_tokens=len(names) * 30,
        messages=[{"role": "user", "content": msg}],
    )
    raw = resp.content[0].text.strip()
    start, end = raw.find("{"), raw.rfind("}") + 1
    result = json.loads(raw[start:end]) if start >= 0 else {}
    # Ensure every input name is mapped
    for name in names:
        if name not in result:
            result[name] = name
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    tagged_path = output_dir / "tagged_mentions.json"
    canon_path  = output_dir / "canonical_map.json"

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY not set.")
    client = anthropic.Anthropic(api_key=api_key)

    tagged = json.loads(tagged_path.read_text())
    print(f"Loaded {len(tagged)} tagged entries.")

    # ── Step 1: collect all unique drug names ─────────────────────────────────
    all_drugs: set[str] = set()
    for entry in tagged:
        all_drugs.update(entry.get("drugs_direct", []))
        all_drugs.update(entry.get("drugs_context", []))
    print(f"Found {len(all_drugs)} unique drug names.")

    # ── Step 2: batch all drug names through Haiku ───────────────────────────
    canon_map: dict[str, str] = {}
    all_drugs_sorted = sorted(all_drugs)

    for i in range(0, len(all_drugs_sorted), BATCH_SIZE):
        batch = all_drugs_sorted[i:i + BATCH_SIZE]
        try:
            result = haiku_canonicalize(client, batch)
            canon_map.update(result)
        except Exception as e:
            print(f"  Haiku error on batch {i}: {e}")
            for name in batch:
                canon_map[name] = name  # fallback: identity
        print(f"  Canonicalized {min(i + BATCH_SIZE, len(all_drugs_sorted))}/{len(all_drugs_sorted)}...",
              end="\r", flush=True)
    print()

    # ── Step 4: save canonical map ────────────────────────────────────────────
    canon_path.write_text(json.dumps(canon_map, indent=2, sort_keys=True))
    print(f"Wrote {canon_path.name}")

    # Print summary of groupings
    groups = defaultdict(list)
    for raw, canonical in canon_map.items():
        if raw != canonical:
            groups[canonical].append(raw)
    if groups:
        print(f"\nSynonym groups found ({len(groups)}):")
        for canonical, synonyms in sorted(groups.items()):
            print(f"  {canonical} ← {', '.join(synonyms)}")
    else:
        print("\nNo synonym groups found.")

    # ── Step 5: rewrite tagged_mentions.json ─────────────────────────────────
    def canonicalize_list(drugs: list[str]) -> list[str]:
        return list(dict.fromkeys(canon_map.get(d, d) for d in drugs))

    for entry in tagged:
        entry["drugs_direct"]  = canonicalize_list(entry.get("drugs_direct", []))
        entry["drugs_context"] = canonicalize_list(entry.get("drugs_context", []))

    tagged_path.write_text(json.dumps(tagged, indent=2))
    print(f"Rewrote {tagged_path.name} with canonical drug names.")


if __name__ == "__main__":
    main()
