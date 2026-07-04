"""OpenRouter connectivity and tiny structured-output eval for A2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import REPO_ROOT  # noqa: F401
from dev.analysis.a0_extraction.comment_context import DEFAULT_DB
from dev.analysis.a2_batch_extraction.common import DEFAULT_RUN_ROOT
from dev.analysis.a2_batch_extraction.runner import (
    context_config_from_values,
    create_run,
    dry_render_run,
    export_run,
    live_run,
    summarize_run,
)
from dev.analysis.agents.CommentCoderAgent.manifest import DEFAULT_MODEL
from dev.analysis.agents._common.runtime import check_openrouter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate OpenRouter reachability or A2 structured extraction.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--connectivity", action="store_true")
    parser.add_argument("--sample", default="prompt_dev")
    parser.add_argument("--sample-file", type=Path)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--run-id")
    parser.add_argument("--allow-large-live", action="store_true")
    parser.add_argument("--ancestor-depth", type=int, default=2)
    parser.add_argument("--previous-sibling-limit", type=int, default=2)
    parser.add_argument("--previous-thread-limit", type=int, default=3)
    parser.add_argument("--max-body-chars", type=int, default=1200)
    parser.add_argument("--max-total-chars", type=int, default=16000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.connectivity:
        result = check_openrouter(args.model)
        payload = {
            "ok": True,
            "model": result["model"],
            "content_present": bool(result["content"]),
            "content": result["content"],
            "total_tokens": result["total_tokens"],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.limit <= 0:
        raise SystemExit("ERROR: --limit must be positive.")

    config = context_config_from_values(
        ancestor_depth=args.ancestor_depth,
        previous_sibling_limit=args.previous_sibling_limit,
        previous_thread_limit=args.previous_thread_limit,
        max_body_chars=args.max_body_chars,
        max_total_chars=args.max_total_chars,
    )
    run_dir = create_run(
        db=args.db,
        sample=args.sample,
        sample_file=args.sample_file,
        limit=args.limit,
        run_root=args.run_root,
        run_id=args.run_id,
        model=args.model,
        config=config,
    )
    dry_render_run(run_dir=run_dir, limit=args.limit, store_raw=True)
    live_status = live_run(
        run_dir=run_dir,
        limit=args.limit,
        model=args.model,
        max_attempts=args.max_attempts,
        workers=1,
        store_raw=True,
        allow_large_live=args.allow_large_live,
    )
    report = summarize_run(run_dir=run_dir, write=True)
    export_run(run_dir=run_dir)
    print(json.dumps({"run_dir": str(run_dir), "live_status": live_status, "report": report}, indent=2, sort_keys=True))
    return live_status


if __name__ == "__main__":
    raise SystemExit(main())

