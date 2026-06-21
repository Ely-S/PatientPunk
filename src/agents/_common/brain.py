"""Per-agent brain loading — model + sampling config from ``brain/brain.json``.

Each Trial Dervish declares its model (and optional temperature / token / context
settings) in a ``brain/brain.json`` next to its ``main.py``. This module reads
that file and builds the single :class:`rumi.Voice` the agent's ``heart_config``
needs. ``RUMI_MODEL`` stays as an OPTIONAL global override (it wins over the
per-agent default); ``brain.json`` is the per-agent source of truth.

This replaces the old per-package global ``MODEL`` constant (resolved from
``RUMI_MODEL`` / the pipeline's strong-model env). The agent layer no longer reads
the sentiment pipeline's fast/strong model env vars — those belong to ``src/``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from rumi import Voice


def load_brain(brain_dir) -> dict:
    """Read ``<brain_dir>/brain.json`` and return it as a dict."""
    path = Path(brain_dir) / "brain.json"
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def resolve_model(brain: dict) -> str:
    """The model id for this agent. ``RUMI_MODEL`` (global override) wins.

    Otherwise the per-agent ``brain.json`` ``model`` is the source of truth.
    """
    return os.environ.get("RUMI_MODEL") or brain["model"]


def build_voice(brain_dir, instructions: str) -> Voice:
    """Build the agent's single :class:`rumi.Voice` from its ``brain.json``.

    The model comes from :func:`resolve_model` (RUMI_MODEL override, else the
    brain default). ``temperature`` / ``max_tokens`` are passed only when set in
    the brain (None kwargs are omitted so Rumi's Voice defaults apply);
    ``context_window`` defaults to 16.
    """
    brain = load_brain(brain_dir)
    kwargs: dict = {
        "model_name": resolve_model(brain),
        "instructions": instructions,
        "context_window": brain.get("context_window", 16),
    }
    if brain.get("temperature") is not None:
        kwargs["temperature"] = brain["temperature"]
    if brain.get("max_tokens") is not None:
        kwargs["max_tokens"] = brain["max_tokens"]
    return Voice(**kwargs)
