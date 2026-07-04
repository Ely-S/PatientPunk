"""Write A2 comment and claim audit templates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import REPO_ROOT  # noqa: F401
from dev.analysis.a2_batch_extraction.runner import select_audit_sample


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select A2 audit rows.")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--limit-comments", type=int, default=25)
    parser.add_argument("--limit-claims", type=int, default=50)
    args = parser.parse_args(argv)
    counts = select_audit_sample(
        run_dir=args.run,
        limit_comments=args.limit_comments,
        limit_claims=args.limit_claims,
    )
    print(json.dumps(counts, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

