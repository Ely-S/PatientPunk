#!/usr/bin/env python3
"""
run_pipeline.py — Run the full drug mention database pipeline.

Steps:
  1. extract   — Extract drug mentions from posts → tagged_mentions.json
  2. canonicalize — Normalize synonyms for drug names → canonical_map.json, update tagged_mentions.json
  3. classify  — Classify sentiment for each entry×drug → sentiment_cache.json

Usage:
    python src/run_pipeline.py --posts-file data/posts.json --output-dir data/outputs
    python src/run_pipeline.py --posts-file data/posts.json --output-dir data/outputs --skip-canonicalize
    python src/run_pipeline.py --posts-file data/posts.json --output-dir data/outputs --limit 50
"""
import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from utilities import PipelineConfig, get_client, log
from scripts.extract_mentions import run_extraction
from scripts.canonicalize import run_canonicalization
from scripts.classify_sentiment import run_classification

STEPS = [
    ("extract", run_extraction),
    ("canonicalize", run_canonicalization),
    ("classify", run_classification),
]


def main():
    parser = argparse.ArgumentParser(description="Run drug mention database pipeline")
    parser.add_argument("--posts-file", required=True, help="Path to subreddit_posts.json")
    parser.add_argument("--output-dir", required=True, help="Directory for output files")
    parser.add_argument("--limit", type=int, default=100, help="Limit posts processed")
    parser.add_argument("--regenerate-cache", action="store_true", help="Ignore existing caches")
    parser.add_argument("--skip-canonicalize", action="store_true", help="Skip canonicalization step")
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

    for step_name, step_fn in STEPS:
        if step_name == "canonicalize" and args.skip_canonicalize:
            continue
        log.info(f"\n{'═' * 60}")
        log.info(f"  STEP: {step_name.upper()}")
        log.info(f"{'═' * 60}\n")
        step_fn(config)

    log.info(f"\n{'═' * 60}")
    log.info("  PIPELINE COMPLETE")
    log.info(f"{'═' * 60}\n")


if __name__ == "__main__":
    main()
