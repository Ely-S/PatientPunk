"""CLI entrypoint for building and querying the comment context database."""
from __future__ import annotations

import sys
from pathlib import Path


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from dev.analysis.a0_extraction.comment_context import main


if __name__ == "__main__":
    raise SystemExit(main())
