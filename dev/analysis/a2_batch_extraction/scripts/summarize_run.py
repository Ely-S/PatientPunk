"""Write or print an A2 run report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import REPO_ROOT  # noqa: F401
from dev.analysis.a2_batch_extraction.runner import summarize_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize an A2 run.")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    report = summarize_run(run_dir=args.run, write=not args.no_write)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

