"""ResolverAgent — the kickoff drug-parse Dervish of "The Trial".

A one-shot :class:`rumi.Dervish` that reads the user's free-text question and
returns a small JSON structure naming the single drug to put on trial. Its model
+ sampling config live in ``brain/brain.json`` (was the fast-model haiku call).

``resolve_query`` is the public entrypoint. It TOLERATES ANY failure (no key, bad
JSON, network) by falling back to the raw user prompt as the drug query — the
deterministic Resolver in ``build_packet`` does the real resolution.
"""

from __future__ import annotations

from pathlib import Path

from rumi import Dervish, HeartConfig

from agents._common.brain import build_voice
from agents._common.runtime import ephemeral_world
from agents.ResolverAgent.brain.prompts import INSTRUCTIONS, build_message

_BRAIN_DIR = Path(__file__).parent / "brain"


class ResolverAgent(Dervish):
    """The intake parser. Names the one drug from a free-text patient question."""

    heart_config = HeartConfig(
        voices=[build_voice(_BRAIN_DIR, INSTRUCTIONS)]
    )


def resolve_query(prompt: str, *, world=None) -> dict:
    """Parse the user's free text into ``{"drug_query", ...}``.

    Returns at least ``{"drug_query": <candidate or raw prompt>}``. Any failure
    falls back to ``{"drug_query": prompt.strip()}`` so the pipeline never breaks
    on a bad parse.
    """
    raw_query = prompt.strip()
    try:
        w = world or ephemeral_world()
        agent = ResolverAgent(world=w)  # auto-generated ephemeral id
        idea = agent.whirl(build_message(prompt))
        content = idea.content
        if isinstance(content, dict):
            parsed = content
        else:
            from utilities import parse_json_object

            parsed = parse_json_object(str(content))
        candidate = (parsed.get("drug_query") or parsed.get("drug") or "").strip()
        result = dict(parsed) if isinstance(parsed, dict) else {}
        result["drug_query"] = candidate or raw_query
        return result
    except Exception:
        # Any failure (no key, bad JSON, network) -> fall back to raw text.
        return {"drug_query": raw_query}
