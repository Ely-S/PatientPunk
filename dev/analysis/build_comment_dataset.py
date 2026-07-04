"""Compatibility wrapper for the A0 comment dataset builder."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from dev.analysis.a0_extraction.comment_dataset import main as a0_main

    return a0_main()


if __name__ == "__main__":
    raise SystemExit(main())
