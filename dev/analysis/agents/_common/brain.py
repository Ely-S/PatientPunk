"""Brain loading helpers for analysis Rumi agents."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from rumi import Voice


def load_brain(brain_dir: str | Path) -> dict[str, Any]:
    """Read ``<brain_dir>/brain.json``."""
    path = Path(brain_dir) / "brain.json"
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_model(brain: dict[str, Any], model_name: str | None = None) -> str:
    """Resolve the model in priority order: explicit, env override, brain file."""
    return (
        model_name
        or os.environ.get("A1_COMMENT_CODER_MODEL")
        or os.environ.get("RUMI_MODEL")
        or brain["model"]
    )


def build_voice(
    brain_dir: str | Path,
    instructions: str,
    *,
    model_name: str | None = None,
) -> Voice:
    """Build a single Rumi voice from an analysis agent brain config."""
    brain = load_brain(brain_dir)
    kwargs: dict[str, Any] = {
        "model_name": resolve_model(brain, model_name),
        "instructions": instructions,
        "context_window": brain.get("context_window", 16),
    }
    if brain.get("temperature") is not None:
        kwargs["temperature"] = brain["temperature"]
    if brain.get("max_tokens") is not None:
        kwargs["max_tokens"] = brain["max_tokens"]
    if brain.get("extra_body"):
        kwargs["extra_body"] = brain["extra_body"]
    return Voice(**kwargs)

