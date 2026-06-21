"""Hooper — the believer Dervish of "The Trial".

Hooper (the optimist) is a :class:`rumi.Dervish` subclass. It argues ONLY over an
:class:`~agents._common.packet.EvidencePacket`: given the packet's
``as_prompt_block()`` as the sole evidence it may cite, referencing packet claim
ids via ``cite("...")`` / ``quote("...")``.

Design constraints (see the shared contract):

* ``heart_config`` is a CLASS-LEVEL attribute with at least one
  :class:`rumi.Voice`. ``Voice.instructions`` IS the system prompt.
* No ``@tool`` — Hooper only talks, it never fetches data. All headline numbers
  and verbatim quotes are code-templated downstream by ``synthesize()``; the
  agent only ever cites/quotes packet claim ids.
* The model + sampling config live in ``brain/brain.json`` (OpenRouter model id,
  temperature 0.7). ``RUMI_MODEL`` is an optional global override.
"""

from __future__ import annotations

from pathlib import Path

from rumi import Dervish, HeartConfig

from agents._common.brain import build_voice
from agents.HooperAgent.brain.prompts import INSTRUCTIONS

_BRAIN_DIR = Path(__file__).parent / "brain"


class Hooper(Dervish):
    """The believer. Warm, hopeful, leans on the positive evidence.

    Higher temperature (0.7, from brain.json) — Hooper is the enthusiastic one,
    but is still bound to the packet: every number or quote must be a packet
    claim id.
    """

    heart_config = HeartConfig(
        voices=[build_voice(_BRAIN_DIR, INSTRUCTIONS)]
    )
