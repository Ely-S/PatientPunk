"""Summarize an A1 dry or live run directory."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from common import RUNS_DIR, read_jsonl, write_json


def safe_read_jsonl(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path) if path.exists() else []


def summarize_run(run_dir: Path) -> dict[str, Any]:
    rendered = safe_read_jsonl(run_dir / "rendered_contexts.jsonl")
    results = safe_read_jsonl(run_dir / "results.jsonl")
    failures = safe_read_jsonl(run_dir / "failures.jsonl")

    claim_count = 0
    codeable = 0
    skipped = 0
    used_context = 0
    low_attribution = 0
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    total_cost = 0.0
    by_skip_reason: Counter[str] = Counter()
    by_claim_type: Counter[str] = Counter()

    for row in results:
        result = row.get("result") or {}
        claims = result.get("target_author_claims") or []
        claim_count += len(claims)
        if result.get("is_codeable"):
            codeable += 1
        else:
            skipped += 1
            by_skip_reason[str(result.get("skip_reason"))] += 1
        if result.get("used_context"):
            used_context += 1
        if result.get("attribution_confidence") == "low":
            low_attribution += 1
        for claim in claims:
            by_claim_type[str(claim.get("claim_type"))] += 1

        metadata = row.get("metadata") or {}
        prompt_tokens += int(metadata.get("prompt_tokens") or 0)
        completion_tokens += int(metadata.get("completion_tokens") or 0)
        total_tokens += int(metadata.get("total_tokens") or 0)
        total_cost += float(metadata.get("cost_usd") or 0.0)

    attempted = len(results) + len(failures)
    summary = {
        "run_dir": str(run_dir),
        "rendered_inputs": len(rendered),
        "attempted": attempted,
        "successes": len(results),
        "failures": len(failures),
        "structured_success_rate": (len(results) / attempted) if attempted else None,
        "codeable": codeable,
        "skipped": skipped,
        "claim_count": claim_count,
        "mean_claims_per_success": (claim_count / len(results)) if results else None,
        "used_context": used_context,
        "low_attribution_confidence": low_attribution,
        "skip_reasons": dict(sorted(by_skip_reason.items())),
        "claim_types": dict(sorted(by_claim_type.items())),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 8),
    }
    return summary


def newest_run(run_root: Path) -> Path:
    runs = [path for path in run_root.iterdir() if path.is_dir()]
    if not runs:
        raise SystemExit(f"ERROR: no run directories found under {run_root}")
    return max(runs, key=lambda path: path.stat().st_mtime)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize A1 run outputs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--run", type=Path)
    parser.add_argument("--run-root", type=Path, default=RUNS_DIR)
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--write", action="store_true", help="Write metrics.json into the run directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.run:
        run_dir = args.run
    elif args.latest:
        run_dir = newest_run(args.run_root)
    else:
        raise SystemExit("ERROR: pass --run <dir> or --latest.")

    if not run_dir.exists():
        raise SystemExit(f"ERROR: run directory not found: {run_dir}")

    summary = summarize_run(run_dir)
    for key, value in summary.items():
        print(f"{key}: {value}")

    if args.write:
        write_json(run_dir / "metrics.json", summary)
        print(f"wrote {run_dir / 'metrics.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

