"""Build comment clusters from an A4 evidence mart."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import REPO_ROOT  # noqa: F401
from dev.analysis.a0_extraction.comment_context import DEFAULT_DB
from dev.analysis.cluster.analysis import build_comment_clusters


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build exploratory comment clusters from an A4 report package.")
    parser.add_argument("--a4-report", type=Path, required=True, help="A4 report directory or evidence_mart.sqlite path.")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--comment-db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--min-meaningful-comments", type=int, default=10)
    parser.add_argument("--max-features", type=int, default=5000)
    parser.add_argument("--min-df", type=int, default=1)
    parser.add_argument("--distance-threshold", type=float, default=0.65)
    parser.add_argument("--n-clusters", type=int)
    parser.add_argument("--no-comment-body", action="store_true")
    parser.add_argument("--no-claim-text", action="store_true")
    parser.add_argument("--no-evidence-quotes", action="store_true")
    parser.add_argument("--write-feature-matrix", action="store_true")
    args = parser.parse_args(argv)

    result = build_comment_clusters(
        a4_report=args.a4_report,
        output_dir=args.output_dir,
        comment_db=args.comment_db,
        include_comment_body=not args.no_comment_body,
        include_claim_text=not args.no_claim_text,
        include_evidence_quotes=not args.no_evidence_quotes,
        min_meaningful_comments=args.min_meaningful_comments,
        max_features=args.max_features,
        min_df=args.min_df,
        distance_threshold=args.distance_threshold,
        n_clusters=args.n_clusters,
        write_feature_matrix=args.write_feature_matrix,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
