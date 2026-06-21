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
* ``MODEL`` must be an OpenRouter model id for live runs.
"""

from __future__ import annotations

from rumi import Dervish, HeartConfig, Voice

from agents._common.model import MODEL
from agents.HooperAgent.brain.prompts import INSTRUCTIONS


class Hooper(Dervish):
    """The believer. Warm, hopeful, leans on the positive evidence.

    Higher temperature (0.7) — Hooper is the enthusiastic one, but is still
    bound to the packet: every number or quote must be a packet claim id.
    """

    heart_config = HeartConfig(
        voices=[
            Voice(
                model_name=MODEL,
                instructions=INSTRUCTIONS,
                context_window=16,
                temperature=0.7,
            )
        ]
    )
