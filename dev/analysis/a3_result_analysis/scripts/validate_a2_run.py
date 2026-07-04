"""Validate an A2 run before A3 analysis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import REPO_ROOT  # noqa: F401
from dev.analysis.a3_result_analysis.loaders import resolve_a2_paths
from dev.analysis.a3_result_analysis.validate import validate_a2_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate A2 outputs for A3.")
    parser.add_argument("--run", type=Path)
    parser.add_argument("--exports", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = validate_a2_run(resolve_a2_paths(run=args.run, exports=args.exports), output_path=args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

