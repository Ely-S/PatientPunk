"""Run or dry-render the A1 comment-coding prompt on a frozen sample."""

from __future__ import annotations

import argparse
import traceback
from pathlib import Path
from typing import Any

from common import (
    RUNS_DIR,
    append_jsonl,
    read_jsonl,
    require_file,
    sample_path,
    utc_now_compact,
    write_json,
)
from dev.analysis.a0_extraction.comment_context import DEFAULT_DB, CommentStore
from dev.analysis.agents.CommentCoderAgent.api import code_comment_with_metadata
from dev.analysis.agents.CommentCoderAgent.brain.prompts import PROMPT_VERSION, build_message
from dev.analysis.agents.CommentCoderAgent.manifest import DEFAULT_MODEL, manifest
from dev.analysis.agents._common.render_context import (
    ContextRenderConfig,
    context_comment_ids,
    render_context_for_prompt,
    stable_text_hash,
)
from dev.analysis.agents._common.runtime import analysis_world, check_openrouter


def render_input_rows(
    *,
    db: Path,
    sample_rows: list[dict[str, Any]],
    config: ContextRenderConfig,
    limit: int,
) -> list[dict[str, Any]]:
    rows = []
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
            rendered_context = render_context_for_prompt(context, config)
            prompt_message = build_message(rendered_context)
            rows.append(
                {
                    "sample": row.get("sample"),
                    "selection_bucket": row.get("selection_bucket"),
                    "comment_id": context.target.id,
                    "source_line": context.target.source_line,
                    "date_utc": context.target.date_utc,
                    "context_comment_ids_available": context_comment_ids(context),
                    "render_config": config.as_dict(),
                    "rendered_context_sha256": stable_text_hash(rendered_context),
                    "prompt_message_sha256": stable_text_hash(prompt_message),
                    "rendered_context": rendered_context,
                    "prompt_message": prompt_message,
                }
            )
    return rows


def write_run_manifest(
    *,
    run_dir: Path,
    mode: str,
    sample_name: str,
    sample_file: Path,
    db: Path,
    model: str,
    limit: int,
    max_attempts: int,
    config: ContextRenderConfig,
) -> None:
    payload = manifest() | {
        "run_id": run_dir.name,
        "mode": mode,
        "sample": sample_name,
        "sample_file": str(sample_file),
        "db": str(db),
        "model": model,
        "limit": limit,
        "max_attempts": max_attempts,
        "context_render_config": config.as_dict(),
    }
    write_json(run_dir / "manifest.json", payload)


def run_live(
    *,
    run_dir: Path,
    rendered_rows: list[dict[str, Any]],
    model: str,
    max_attempts: int,
) -> int:
    world = analysis_world(data_dir=run_dir / "rumi")
    successes = 0
    failures = 0

    for index, row in enumerate(rendered_rows, start=1):
        print(
            f"[{index}/{len(rendered_rows)}] coding "
            f"comment_id={row['comment_id']} source_line={row['source_line']}",
            flush=True,
        )
        attempt_errors: list[dict[str, str]] = []
        for attempt in range(1, max_attempts + 1):
            agent_id = f"{run_dir.name}-{row['source_line']}-a{attempt}"
            try:
                response = code_comment_with_metadata(
                    row["rendered_context"],
                    target_comment_id=row["comment_id"],
                    source_line=row["source_line"],
                    model=model,
                    world=world,
                    agent_id=agent_id,
                )
                append_jsonl(
                    run_dir / "results.jsonl",
                    {
                        "comment_id": row["comment_id"],
                        "source_line": row["source_line"],
                        "sample": row.get("sample"),
                        "selection_bucket": row.get("selection_bucket"),
                        "model": response.model,
                        "prompt_version": PROMPT_VERSION,
                        "attempt": attempt,
                        "previous_attempt_errors": attempt_errors,
                        "latency_seconds": round(response.latency_seconds, 3),
                        "metadata": response.metadata,
                        "result": response.result.model_dump(mode="json"),
                    },
                )
                successes += 1
                break
            except Exception as exc:
                attempt_errors.append(
                    {
                        "attempt": str(attempt),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "traceback": traceback.format_exc(limit=8),
                    }
                )
                if attempt < max_attempts:
                    print(
                        f"  attempt {attempt} failed: {type(exc).__name__}: {exc}; retrying",
                        flush=True,
                    )
                else:
                    append_jsonl(
                        run_dir / "failures.jsonl",
                        {
                            "comment_id": row["comment_id"],
                            "source_line": row["source_line"],
                            "sample": row.get("sample"),
                            "selection_bucket": row.get("selection_bucket"),
                            "model": model,
                            "attempts": max_attempts,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                            "attempt_errors": attempt_errors,
                        },
                    )
                    print(f"  FAILED: {type(exc).__name__}: {exc}", flush=True)
                    failures += 1

    write_json(
        run_dir / "run_status.json",
        {
            "successes": successes,
            "failures": failures,
            "result_path": str(run_dir / "results.jsonl"),
            "failure_path": str(run_dir / "failures.jsonl"),
        },
    )
    return 0 if failures == 0 else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-render or live-run A1 prompt-dev samples.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--sample", default="prompt_dev")
    parser.add_argument("--sample-file", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--run-root", type=Path, default=RUNS_DIR)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--dry-render", action="store_true")
    parser.add_argument("--check-openrouter", action="store_true")
    parser.add_argument("--allow-large-live", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--ancestor-depth", type=int, default=2)
    parser.add_argument("--previous-sibling-limit", type=int, default=2)
    parser.add_argument("--previous-thread-limit", type=int, default=3)
    parser.add_argument("--max-body-chars", type=int, default=1200)
    parser.add_argument("--max-total-chars", type=int, default=16000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.check_openrouter:
        result = check_openrouter(args.model)
        print(
            "OpenRouter check passed: "
            f"model={result['model']} reply={result['content']!r} "
            f"total_tokens={result['total_tokens']}"
        )
        return 0

    require_file(args.db, "context database")
    if args.limit is None:
        raise SystemExit("ERROR: pass --limit for dry and live runs.")
    if args.limit <= 0:
        raise SystemExit("ERROR: --limit must be positive.")
    if args.max_attempts <= 0:
        raise SystemExit("ERROR: --max-attempts must be positive.")
    if args.live and args.limit > 25 and not args.allow_large_live:
        raise SystemExit("ERROR: live A1 runs over 25 rows require --allow-large-live.")

    sample_file = require_file(sample_path(args.sample, args.sample_file), "sample file")
    sample_rows = read_jsonl(sample_file)
    if not sample_rows:
        raise SystemExit(f"ERROR: sample file is empty: {sample_file}")

    config = ContextRenderConfig(
        ancestor_depth=args.ancestor_depth,
        previous_sibling_limit=args.previous_sibling_limit,
        previous_thread_limit=args.previous_thread_limit,
        max_body_chars=args.max_body_chars,
        max_total_chars=args.max_total_chars,
    )
    run_mode = "live" if args.live else "dry_render"
    run_dir = args.run_root / f"{utc_now_compact()}_{args.sample}_{run_mode}_{args.limit}"
    run_dir.mkdir(parents=True, exist_ok=False)

    write_run_manifest(
        run_dir=run_dir,
        mode=run_mode,
        sample_name=args.sample,
        sample_file=sample_file,
        db=args.db,
        model=args.model,
        limit=args.limit,
        max_attempts=args.max_attempts,
        config=config,
    )

    rendered_rows = render_input_rows(
        db=args.db,
        sample_rows=sample_rows,
        config=config,
        limit=args.limit,
    )
    for row in rendered_rows:
        append_jsonl(run_dir / "rendered_contexts.jsonl", row)

    print(f"wrote run inputs to {run_dir}")
    if not args.live:
        print("dry render complete; pass --live to call the model")
        return 0

    return run_live(
        run_dir=run_dir,
        rendered_rows=rendered_rows,
        model=args.model,
        max_attempts=args.max_attempts,
    )


if __name__ == "__main__":
    raise SystemExit(main())
