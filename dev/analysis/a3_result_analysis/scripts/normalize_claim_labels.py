"""Generate A3 normalized claim rows from A2 claim exports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import REPO_ROOT  # noqa: F401
from dev.analysis.a3_result_analysis.common import DEFAULT_A3_RUN_ROOT, write_json
from dev.analysis.a3_result_analysis.loaders import load_a2_export_data, resolve_a2_paths
from dev.analysis.a3_result_analysis.normalization import write_normalization_outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize A2 claim labels for A3.")
    parser.add_argument("--run", type=Path)
    parser.add_argument("--exports", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--normalization-map", type=Path)
    args = parser.parse_args(argv)
    paths = resolve_a2_paths(run=args.run, exports=args.exports)
    output_dir = args.output_dir or DEFAULT_A3_RUN_ROOT / paths.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    data = load_a2_export_data(paths)
    result = write_normalization_outputs(
        claims=data.claims,
        output_dir=output_dir,
        map_path=args.normalization_map,
    )
    payload = {
        "output_dir": str(output_dir),
        "normalized_claim_count": len(result["normalized_claims"]),
        "map_row_count": len(result["map_rows"]),
        "manifest": result["manifest"],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

