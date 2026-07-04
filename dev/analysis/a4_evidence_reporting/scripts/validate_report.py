"""Validate an A4 report package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import REPO_ROOT  # noqa: F401
from dev.analysis.a4_evidence_reporting.validate import validate_report_package


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an A4 report package.")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = validate_report_package(args.report, output_path=args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
