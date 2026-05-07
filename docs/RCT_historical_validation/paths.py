"""
Path resolution for the RCT historical validation reproducibility package.

This module is the single source of truth for "where is the analysis DB?"
and related paths. It is imported by `_build_paper_figures.py`, `verify.py`,
`dump_per_drug_csvs.py`, the executed notebook, and the test suite.

Resolution order
----------------
1. **Environment variable `RCT_DB_PATH`** (if set). May be absolute or
   relative; relative paths are resolved against the current working
   directory. The path must exist — we fail loudly rather than silently
   returning a nonexistent path.

2. **Marker-based anchor detection.** Walk up from the search-start
   directory looking for the package root: the directory containing both
   `_build_paper_figures.py` and `verify.py`. Then construct
   `<package_root>/data/<DB_FILENAME>`.

3. **PathResolutionError** if neither resolves, with a message listing
   the searched locations and the env-var escape hatch.

The default search start is the current working directory. Callers that
have a `__file__` available (scripts, not notebook kernels) should also
pass `start=Path(__file__).resolve().parent` to handle the case where the
script is invoked from an unrelated cwd.

Public API
----------
- `DB_FILENAME`: canonical filename of the analysis DB.
- `ENV_VAR`: name of the override env var.
- `PathResolutionError`: raised on all resolution failures.
- `find_package_root(start=None)`: returns the package root Path.
- `db_path(start=None)`: returns the absolute Path to the DB.
- `data_dir(start=None)`: returns `<package_root>/data`.
- `output_dir(start=None)`: returns `<package_root>/output`.

All public functions accept `start: Path | None`. If `start` is given,
resolution walks up from there. If `None`, walks up from `Path.cwd()`.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator, Optional

# ── Public constants ───────────────────────────────────────────────────────

DB_FILENAME = "historical_validation_2020-07_to_2022-12.db"
"""Canonical filename of the analysis SQLite database."""

ENV_VAR = "RCT_DB_PATH"
"""Environment variable name that overrides path resolution."""

PACKAGE_MARKERS = ("_build_paper_figures.py", "verify.py")
"""Filenames whose presence in a single directory uniquely identifies
the RCT historical validation package root."""


class PathResolutionError(RuntimeError):
    """Raised when the analysis DB or package root cannot be located.

    The message includes the searched paths and the env-var escape hatch
    so reviewers can fix the problem without reading source code.
    """


# ── Internals ──────────────────────────────────────────────────────────────

def _is_package_root(d: Path) -> bool:
    """True iff `d` contains every PACKAGE_MARKERS file as a regular file."""
    return all((d / m).is_file() for m in PACKAGE_MARKERS)


def _walk_up(start: Path) -> Iterator[Path]:
    """Yield `start` (resolved) and each ancestor up to the filesystem root."""
    p = start.resolve()
    yield p
    while True:
        parent = p.parent
        if parent == p:
            return
        yield parent
        p = parent


# ── Public API ─────────────────────────────────────────────────────────────

def find_package_root(start: Optional[Path] = None) -> Path:
    """Return the absolute Path to the RCT validation package root.

    Walks up from `start` (default: `Path.cwd()`) looking for a directory
    that contains every file in `PACKAGE_MARKERS`. Raises
    `PathResolutionError` if no such directory is found.

    The package root is the directory containing `_build_paper_figures.py`,
    `verify.py`, `paths.py`, the `data/` subdirectory, etc.
    """
    start_dir = Path(start).resolve() if start is not None else Path.cwd().resolve()
    searched: list[str] = []
    for d in _walk_up(start_dir):
        searched.append(str(d))
        if _is_package_root(d):
            return d
    raise PathResolutionError(
        "Could not locate the RCT historical validation package root.\n"
        f"Markers searched for: {', '.join(PACKAGE_MARKERS)}\n"
        f"Walked up from:       {start_dir}\n"
        "Directories checked:\n  - " + "\n  - ".join(searched) + "\n\n"
        "Fix: cd to docs/RCT_historical_validation/ before running, "
        f"OR set {ENV_VAR}=/absolute/path/to/{DB_FILENAME}."
    )


def db_path(start: Optional[Path] = None) -> Path:
    """Return the absolute Path to the analysis DB.

    Resolution order: `RCT_DB_PATH` env var, then anchor-based discovery
    via `find_package_root`. The returned Path is guaranteed to exist;
    if it doesn't, `PathResolutionError` is raised with a clear message.
    """
    env = os.environ.get(ENV_VAR)
    if env:
        # Resolve relative paths against cwd; absolute paths pass through.
        p = Path(env).expanduser().resolve()
        if not p.is_file():
            raise PathResolutionError(
                f"{ENV_VAR}={env!r} is set but does not point to an existing file.\n"
                f"Resolved to: {p}\n"
                f"Either correct the path or unset {ENV_VAR} to use the package default."
            )
        return p

    root = find_package_root(start=start)
    candidate = root / "data" / DB_FILENAME
    if not candidate.is_file():
        raise PathResolutionError(
            "Found the package root but the analysis DB is missing.\n"
            f"Expected: {candidate}\n"
            f"Package root: {root}\n\n"
            f"Fix: download the DB into {root / 'data'}/ "
            f"(see README), OR set {ENV_VAR}=/absolute/path/to/{DB_FILENAME}."
        )
    return candidate


def data_dir(start: Optional[Path] = None) -> Path:
    """Return `<package_root>/data`. The directory may or may not exist."""
    return find_package_root(start=start) / "data"


def output_dir(start: Optional[Path] = None) -> Path:
    """Return `<package_root>/output`. The directory may or may not exist."""
    return find_package_root(start=start) / "output"
