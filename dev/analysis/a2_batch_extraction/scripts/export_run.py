"""Export A2 run tables for A3 analysis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import REPO_ROOT  # noqa: F401
from dev.analysis.a2_batch_extraction.runner import export_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export an A2 run.")
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = export_run(run_dir=args.run)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

