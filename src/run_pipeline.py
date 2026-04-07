#!/usr/bin/env python3
"""
run_pipeline.py — Run the full drug mention database pipeline.

Steps:
  1. extract   — Extract drug mentions from posts → tagged_mentions.json
  2. canonicalize — Normalize synonyms for drug names → canonical_map.json, update tagged_mentions.json
  3. classify  — Classify sentiment for each entry×drug → sentiment_cache.json

Usage:
    python src/run_pipeline.py --posts-file data/posts.json --output-dir data/outputs
    python src/run_pipeline.py --posts-file data/posts.json --output-dir data/outputs extract canonicalize
    python src/run_pipeline.py --posts-file data/posts.json --output-dir data/outputs --limit 50
"""
import anthropic
import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from utilities import get_client, log


def run_extract(client: anthropic.Anthropic, output_dir: Path, posts_file: Path, limit: int, regenerate: bool):
    """Step 1: Extract drug mentions."""
    from scripts.extract_mentions import run_extraction
    run_extraction(client, output_dir, posts_file, limit=limit, regenerate_cache=regenerate)


def run_canonicalize(client: anthropic.Anthropic, output_dir: Path):
    """Step 2: Canonicalize drug names."""
    from scripts.canonicalize import run_canonicalization
    run_canonicalization(client, output_dir)


def run_classify(client: anthropic.Anthropic, output_dir: Path, limit: int, regenerate: bool):
    """Step 3: Classify sentiment."""
    from scripts.classify_sentiment import run_classification
    run_classification(client, output_dir, limit=limit, regenerate_cache=regenerate)


STEPS = {
    "extract": run_extract,
    "canonicalize": run_canonicalize,
    "classify": run_classify,
}


def main():
    parser = argparse.ArgumentParser(description="Run drug mention database pipeline")
    parser.add_argument("steps", nargs="*", default=["extract", "canonicalize", "classify"],
                        choices=list(STEPS.keys()), help="Steps to run (default: all)")
    parser.add_argument("--posts-file", required=True, help="Path to subreddit_posts.json")
    parser.add_argument("--output-dir", required=True, help="Directory for output files")
    parser.add_argument("--limit", type=int, default=100, help="Limit posts processed")
    parser.add_argument("--regenerate-cache", action="store_true", help="Ignore existing caches")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    posts_file = Path(args.posts_file)
    client = get_client()

    for step_name in args.steps:
        log.info(f"\n{'═' * 60}")
        log.info(f"  STEP: {step_name.upper()}")
        log.info(f"{'═' * 60}\n")
        
        if step_name == "extract":
            run_extract(client, output_dir, posts_file, args.limit, args.regenerate_cache)
        elif step_name == "classify":
            run_classify(client, output_dir, args.limit, args.regenerate_cache)
        else:
            run_canonicalize(client, output_dir)

    log.info(f"\n{'═' * 60}")
    log.info("  PIPELINE COMPLETE")
    log.info(f"{'═' * 60}\n")


if __name__ == "__main__":
    main()
