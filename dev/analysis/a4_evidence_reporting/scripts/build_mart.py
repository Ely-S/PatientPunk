"""Build an A4 package and emphasize the evidence mart output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import REPO_ROOT  # noqa: F401
from dev.analysis.a4_evidence_reporting.analysis import build_report
from dev.analysis.a4_evidence_reporting.common import DEFAULT_A4_REPORT_ROOT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build A4 evidence mart from an A3 analysis directory.")
    parser.add_argument("--a3", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_A4_REPORT_ROOT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report-id")
    args = parser.parse_args(argv)
    result = build_report(
        a3=args.a3,
        output_root=args.output_root,
        output_dir=args.output_dir,
        report_id=args.report_id,
        mode="private_review",
    )
    result["evidence_mart"] = str(Path(result["report_dir"]) / "evidence_mart.sqlite")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
