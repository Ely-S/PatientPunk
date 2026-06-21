"""Dr. Vex — the skeptic Dervish of "The Trial".

Dr. Vex (the skeptic) is a :class:`rumi.Dervish` subclass. It argues ONLY over an
:class:`~agents._common.packet.EvidencePacket`: given the packet's
``as_prompt_block()`` as the sole evidence it may cite, referencing packet claim
ids via ``cite("...")`` / ``quote("...")``.

Design constraints (see the shared contract):

* ``heart_config`` is a CLASS-LEVEL attribute with at least one
  :class:`rumi.Voice`. ``Voice.instructions`` IS the system prompt.
* No ``@tool`` — Dr. Vex only talks, it never fetches data. All headline numbers
  and verbatim quotes are code-templated downstream by ``synthesize()``; the
  agent only ever cites/quotes packet claim ids.
* ``MODEL`` must be an OpenRouter model id for live runs.
"""

from __future__ import annotations

from rumi import Dervish, HeartConfig, Voice

from agents._common.model import MODEL
from agents.DrVexAgent.brain.prompts import INSTRUCTIONS


class DrVex(Dervish):
    """The skeptic. Cooler-headed, surfaces caveats and the silent-drop trap.

    Lower temperature (0.4) — Dr. Vex is precise and must always raise C3
    (non-experiential mentions are dropped, so a low negative count is NOT
    proof of safety). Like Hooper, bound to packet claim ids only.
    """

    heart_config = HeartConfig(
        voices=[
            Voice(
                model_name=MODEL,
                instructions=INSTRUCTIONS,
                context_window=16,
                temperature=0.4,
            )
        ]
    )
