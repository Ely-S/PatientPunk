"""Ephemeral Rumi runtime for the one-shot Trial Dervishes.

The Resolver / Synthesizer / Judge agents are throwaway, single-whirl agents.
``ephemeral_world`` builds a zero-config :class:`rumi.World` exactly the way
``run_debate`` does: it loads ``.env`` (so ``OPENROUTER_API_KEY`` is present even
if the ``src/`` ``utilities`` shim was never imported) and points Rumi's on-disk
history at a fresh temp dir unless the caller pinned ``RUMI_DATA_DIR``.
"""

from __future__ import annotations

import os
import tempfile

from dotenv import load_dotenv
from rumi import World


def ephemeral_world() -> World:
    """A zero-config :class:`rumi.World` with ephemeral on-disk history.

    Loads ``.env`` first so ``OPENROUTER_API_KEY`` is available, then points
    ``RUMI_DATA_DIR`` at a throwaway temp dir unless one is already set.
    """
    load_dotenv()
    if not os.environ.get("RUMI_DATA_DIR"):
        os.environ["RUMI_DATA_DIR"] = tempfile.mkdtemp(prefix="trial-rumi-")
    return World()
