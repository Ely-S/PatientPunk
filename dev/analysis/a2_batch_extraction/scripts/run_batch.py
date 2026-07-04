"""Dry-render or live-run an existing A2 batch."""

from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import REPO_ROOT  # noqa: F401
from dev.analysis.a2_batch_extraction.runner import dry_render_run, live_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an A2 batch in dry-render or live mode.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--run", type=Path, required=True, help="Run directory containing run.sqlite.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-render", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--model")
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--allow-large-live", action="store_true")
    parser.add_argument(
        "--store-rendered",
        choices=["none", "audit"],
        default="audit",
        help="'audit' stores raw rendered text in rendered_inputs; 'none' stores hashes only.",
    )
    parser.add_argument("--no-deterministic-skips", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store_raw = args.store_rendered == "audit"
    if args.dry_render:
        dry_render_run(run_dir=args.run, limit=args.limit, store_raw=store_raw)
        return 0
    return live_run(
        run_dir=args.run,
        limit=args.limit,
        model=args.model,
        max_attempts=args.max_attempts,
        workers=args.workers,
        store_raw=store_raw,
        allow_large_live=args.allow_large_live,
        deterministic_skips=not args.no_deterministic_skips,
    )


if __name__ == "__main__":
    raise SystemExit(main())

