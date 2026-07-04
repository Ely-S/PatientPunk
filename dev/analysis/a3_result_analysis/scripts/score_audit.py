"""Score reviewed A3 audit labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import REPO_ROOT  # noqa: F401
from dev.analysis.a3_result_analysis.common import DEFAULT_A3_RUN_ROOT
from dev.analysis.a3_result_analysis.loaders import resolve_a2_paths
from dev.analysis.a3_result_analysis.score import score_audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score reviewed A3 audit labels.")
    parser.add_argument("--run", type=Path)
    parser.add_argument("--exports", type=Path)
    parser.add_argument("--audit-comments", type=Path)
    parser.add_argument("--audit-claims", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    paths = resolve_a2_paths(run=args.run, exports=args.exports)
    output_dir = args.output_dir or DEFAULT_A3_RUN_ROOT / paths.run_id / "scores"
    result = score_audit(
        audit_comments_path=args.audit_comments,
        audit_claims_path=args.audit_claims,
        output_dir=output_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

