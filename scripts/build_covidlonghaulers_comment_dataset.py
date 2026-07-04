"""Compatibility wrapper for the dataset builder now owned by dev/analysis/a0_extraction."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from dev.analysis.a0_extraction.comment_dataset import main as analysis_main

    return analysis_main()


if __name__ == "__main__":
    raise SystemExit(main())
