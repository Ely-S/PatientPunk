"""Build a complete A4 report package from an A3 analysis directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import REPO_ROOT  # noqa: F401
from dev.analysis.a4_evidence_reporting.analysis import build_report
from dev.analysis.a4_evidence_reporting.common import DEFAULT_A4_REPORT_ROOT, DEFAULT_MODE, DEFAULT_REPORT_TYPE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an A4 evidence report package.")
    parser.add_argument("--a3", type=Path, required=True, help="A3 analysis directory.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_A4_REPORT_ROOT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report-id")
    parser.add_argument("--report-type", default=DEFAULT_REPORT_TYPE)
    parser.add_argument("--mode", default=DEFAULT_MODE, choices=["private_review", "public_summary"])
    args = parser.parse_args(argv)
    result = build_report(
        a3=args.a3,
        output_root=args.output_root,
        output_dir=args.output_dir,
        report_id=args.report_id,
        report_type=args.report_type,
        mode=args.mode,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
