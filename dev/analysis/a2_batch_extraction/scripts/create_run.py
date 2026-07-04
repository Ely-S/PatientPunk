"""Create an A2 SQLite-backed batch run."""

from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import REPO_ROOT  # noqa: F401
from dev.analysis.a0_extraction.comment_context import DEFAULT_DB
from dev.analysis.a2_batch_extraction.common import DEFAULT_RUN_ROOT
from dev.analysis.a2_batch_extraction.runner import context_config_from_values, create_run
from dev.analysis.agents.CommentCoderAgent.manifest import DEFAULT_MODEL


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create an A2 comment-coding batch run.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--run-id")
    parser.add_argument("--sample", default="prompt_dev")
    parser.add_argument("--sample-file", type=Path)
    parser.add_argument("--where-sql", default="")
    parser.add_argument("--order", default="created_utc, id")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--allow-large-selection", action="store_true")
    parser.add_argument("--ancestor-depth", type=int, default=2)
    parser.add_argument("--previous-sibling-limit", type=int, default=2)
    parser.add_argument("--previous-thread-limit", type=int, default=3)
    parser.add_argument("--max-body-chars", type=int, default=1200)
    parser.add_argument("--max-total-chars", type=int, default=16000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = context_config_from_values(
        ancestor_depth=args.ancestor_depth,
        previous_sibling_limit=args.previous_sibling_limit,
        previous_thread_limit=args.previous_thread_limit,
        max_body_chars=args.max_body_chars,
        max_total_chars=args.max_total_chars,
    )
    create_run(
        db=args.db,
        sample=args.sample,
        sample_file=args.sample_file,
        where_sql=args.where_sql,
        order=args.order,
        limit=args.limit,
        run_root=args.run_root,
        run_id=args.run_id,
        model=args.model,
        config=config,
        allow_large_selection=args.allow_large_selection,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

