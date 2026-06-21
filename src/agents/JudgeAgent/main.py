"""JudgeAgent — the rubric-judge Dervish of "The Trial".

A one-shot :class:`rumi.Dervish` that scores a completed, gate-passing trial on
the four rubric axes (U/D/F/CAL), 0-3 each, at temperature 0. Its model +
sampling config live in ``brain/brain.json`` (was the strong-model sonnet
judge call in ``rubric.grade``).

``grade`` returns the JUDGE'S raw scores dict ``{"U": {"score", "reason"}, ...}``
so the caller (``eval.trial.rubric.grade``) owns the AxisResult assembly and the
pass thresholds. On ANY failure it returns ``{"error": "<msg>"}`` — the caller
turns that into its structured-error result, never crashing.
"""

from __future__ import annotations

from pathlib import Path

from rumi import Dervish, HeartConfig

from agents._common.brain import build_voice
from agents._common.runtime import ephemeral_world
from agents.JudgeAgent.brain.prompts import INSTRUCTIONS, build_message

_BRAIN_DIR = Path(__file__).parent / "brain"


class JudgeAgent(Dervish):
    """The judge. Scores a completed trial on the rubric axes at temp 0."""

    heart_config = HeartConfig(
        voices=[build_voice(_BRAIN_DIR, INSTRUCTIONS)]
    )


def grade(packet_block: str, transcript_text: str, briefing_text: str, *, world=None) -> dict:
    """Judge a gate-passing run -> the raw scores dict ``{"U": {...}, ...}``.

    Inputs are the already-rendered ground-truth packet block, the transcript
    text, and the final briefing text. On ANY failure (no key, bad JSON,
    network) returns ``{"error": "judge failed: <type>: <msg>"}`` — the caller
    turns that into its structured-error result.
    """
    try:
        w = world or ephemeral_world()
        agent = JudgeAgent(world=w)  # auto-generated ephemeral id
        idea = agent.whirl(build_message(packet_block, transcript_text, briefing_text))
        content = idea.content
        if isinstance(content, dict):
            return content
        from utilities import parse_json_object

        return parse_json_object(str(content))
    except Exception as exc:
        return {"error": f"judge failed: {type(exc).__name__}: {exc}"}
