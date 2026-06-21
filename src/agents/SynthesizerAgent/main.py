"""SynthesizerAgent — the bottom-line Dervish of "The Trial".

A one-shot :class:`rumi.Dervish` that writes the verdict's <=2-sentence
plain-language bottom line. Its model + sampling config live in
``brain/brain.json`` (was the strong-model sonnet call in ``synthesize()``).

``write_bottom_line`` is the public entrypoint. On ANY failure it returns the
SAME deterministic fallback sentence ``synthesize()`` used before — so the
briefing is always complete and safe (never a directive).
"""

from __future__ import annotations

from pathlib import Path

from rumi import Dervish, HeartConfig

from agents._common.brain import build_voice
from agents._common.runtime import ephemeral_world
from agents.SynthesizerAgent.brain.prompts import INSTRUCTIONS, build_message

_BRAIN_DIR = Path(__file__).parent / "brain"


class SynthesizerAgent(Dervish):
    """The scribe. Writes the briefing's plain-language bottom line."""

    heart_config = HeartConfig(
        voices=[build_voice(_BRAIN_DIR, INSTRUCTIONS)]
    )


def write_bottom_line(tier: str, facts: dict, *, world=None) -> str:
    """Write the <=2-sentence bottom line for ``facts`` at confidence ``tier``.

    On ANY failure (no key, network) returns the deterministic fallback line —
    identical to the one ``synthesize()`` used before this delegation.
    """
    try:
        w = world or ephemeral_world()
        agent = SynthesizerAgent(world=w)  # auto-generated ephemeral id
        idea = agent.whirl(build_message(tier, facts))
        return str(idea.content).strip()
    except Exception:
        # If the model is unavailable, fall back to a deterministic line so the
        # briefing is still complete and safe (never a directive).
        n_users = facts.get("n_users", 0)
        return (
            f"Bottom line: with {tier} evidence from {n_users} "
            f"patient{'s' if n_users != 1 else ''}, treat this as one data "
            "point among many."
        )
