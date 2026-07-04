"""Run A3 OpenRouter connectivity or end-to-end structured eval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import REPO_ROOT  # noqa: F401
from dev.analysis.a2_batch_extraction.common import DEFAULT_RUN_ROOT as DEFAULT_A2_RUN_ROOT
from dev.analysis.a3_result_analysis.common import DEFAULT_A3_OPENROUTER_EVAL_ROOT, DEFAULT_A3_RUN_ROOT
from dev.analysis.a3_result_analysis.openrouter_eval import connectivity_eval, structured_eval
from dev.analysis.agents.CommentCoderAgent.manifest import DEFAULT_MODEL


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate OpenRouter through A2 plus A3.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--connectivity", action="store_true")
    parser.add_argument("--sample", default="prompt_dev")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_A3_OPENROUTER_EVAL_ROOT)
    parser.add_argument("--a2-run-root", type=Path, default=DEFAULT_A2_RUN_ROOT)
    parser.add_argument("--a3-run-root", type=Path, default=DEFAULT_A3_RUN_ROOT)
    args = parser.parse_args(argv)
    if args.connectivity:
        result = connectivity_eval(model=args.model, output_root=args.output_root)
    else:
        result = structured_eval(
            model=args.model,
            sample=args.sample,
            limit=args.limit,
            max_attempts=args.max_attempts,
            output_root=args.output_root,
            a2_run_root=args.a2_run_root,
            a3_run_root=args.a3_run_root,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())

