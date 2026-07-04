"""CLI entrypoint for building and verifying the local Reddit comment dataset."""
from __future__ import annotations

import sys
from pathlib import Path


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from dev.analysis.a0_extraction.comment_dataset import main


if __name__ == "__main__":
    raise SystemExit(main())
