"""No-tool Rumi agent for structured comment coding."""

from __future__ import annotations

from pathlib import Path

from rumi import Dervish, HeartConfig

from dev.analysis.agents.CommentCoderAgent.brain.prompts import INSTRUCTIONS
from dev.analysis.agents._common.brain import build_voice


_BRAIN_DIR = Path(__file__).parent / "brain"


def make_heart_config(model_name: str | None = None) -> HeartConfig:
    """Build a no-tool heart config for structured output calls."""
    return HeartConfig(voices=[build_voice(_BRAIN_DIR, INSTRUCTIONS, model_name=model_name)])


class CommentCoderAgent(Dervish):
    """Code one Reddit comment into the A1 structured schema."""

    heart_config = make_heart_config()


def configure_model(model_name: str | None = None) -> str:
    """Update the agent class to use a model and return the resolved name."""
    voice = build_voice(_BRAIN_DIR, INSTRUCTIONS, model_name=model_name)
    CommentCoderAgent.heart_config = HeartConfig(voices=[voice])
    return voice.model_name

