"""Render sample comment contexts for inspection or prompt dry runs."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterator

from common import read_jsonl, require_file, sample_path, write_jsonl
from dev.analysis.a0_extraction.comment_context import DEFAULT_DB, CommentStore
from dev.analysis.agents._common.render_context import (
    ContextRenderConfig,
    context_comment_ids,
    render_context_for_prompt,
    stable_text_hash,
)


def iter_rendered_rows(
    *,
    db: Path,
    sample_rows: list[dict],
    config: ContextRenderConfig,
    limit: int | None,
) -> Iterator[dict]:
    with CommentStore(db) as store:
        for row in sample_rows[:limit]:
            comment = store.get_comment(row["comment_id"])
            if comment is None:
                raise RuntimeError(f"Comment not found: {row['comment_id']}")
            context = store.get_context(
                comment,
                ancestor_depth=config.ancestor_depth,
                previous_sibling_limit=config.previous_sibling_limit,
                previous_thread_limit=config.previous_thread_limit,
            )
            rendered = render_context_for_prompt(context, config)
            yield {
                "sample": row.get("sample"),
                "selection_bucket": row.get("selection_bucket"),
                "comment_id": context.target.id,
                "source_line": context.target.source_line,
                "date_utc": context.target.date_utc,
                "context_comment_ids": context_comment_ids(context),
                "render_config": config.as_dict(),
                "rendered_sha256": stable_text_hash(rendered),
                "rendered_context": rendered,
            }


def print_rows(rows: list[dict]) -> None:
    for index, row in enumerate(rows, start=1):
        print("=" * 80)
        print(
            f"{index}. comment_id={row['comment_id']} "
            f"source_line={row['source_line']} bucket={row.get('selection_bucket')}"
        )
        print("-" * 80)
        print(row["rendered_context"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render context windows for A1 sample IDs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--sample", default="prompt_dev")
    parser.add_argument("--sample-file", type=Path)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ancestor-depth", type=int, default=2)
    parser.add_argument("--previous-sibling-limit", type=int, default=2)
    parser.add_argument("--previous-thread-limit", type=int, default=3)
    parser.add_argument("--max-body-chars", type=int, default=1200)
    parser.add_argument("--max-total-chars", type=int, default=16000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    require_file(args.db, "context database")
    rows = read_jsonl(require_file(sample_path(args.sample, args.sample_file), "sample file"))
    config = ContextRenderConfig(
        ancestor_depth=args.ancestor_depth,
        previous_sibling_limit=args.previous_sibling_limit,
        previous_thread_limit=args.previous_thread_limit,
        max_body_chars=args.max_body_chars,
        max_total_chars=args.max_total_chars,
    )
    rendered_rows = list(iter_rendered_rows(db=args.db, sample_rows=rows, config=config, limit=args.limit))
    if args.output:
        count = write_jsonl(args.output, rendered_rows)
        print(f"wrote {count} rendered contexts to {args.output}")
    else:
        print_rows(rendered_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

