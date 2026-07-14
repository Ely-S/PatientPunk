"""Shared per-phase result type for in-process pipeline phases."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class PhaseResult(BaseModel):
    """Outcome, timing, and artifacts for a single pipeline phase.

    Phase runner functions (``run_biomedical``, ``run_llm_extract``, etc.)
    populate ``artifacts`` and ``stats`` only; ``Pipeline._call_phase`` fills
    in ``phase``, ``label``, ``elapsed``, ``ok``, and ``error`` once the
    runner returns.
    """

    phase: int = 0
    label: str = ""
    skipped: bool = False
    elapsed: float = 0.0
    ok: bool = True
    error: str | None = None
    artifacts: dict[str, Path] = Field(default_factory=dict)
    stats: dict[str, Any] = Field(default_factory=dict)
