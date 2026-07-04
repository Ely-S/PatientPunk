"""Run full deterministic A3 analysis on an A2 run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import REPO_ROOT  # noqa: F401
from dev.analysis.a3_result_analysis.analysis import run_analysis
from dev.analysis.a3_result_analysis.common import DEFAULT_A3_RUN_ROOT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run A3 result analysis.")
    parser.add_argument("--run", type=Path)
    parser.add_argument("--exports", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_A3_RUN_ROOT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--normalization-map", type=Path)
    args = parser.parse_args(argv)
    result = run_analysis(
        run=args.run,
        exports=args.exports,
        output_root=args.output_root,
        output_dir=args.output_dir,
        normalization_map=args.normalization_map,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

