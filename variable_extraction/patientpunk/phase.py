"""Shared return type for in-process pipeline phases."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PhaseOutput:
    """Paths written + lightweight stats for Pipeline summaries."""

    artifacts: dict[str, Path]
    stats: dict[str, Any] = field(default_factory=dict)
