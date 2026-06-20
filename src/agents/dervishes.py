"""The two debate agents of "The Trial".

Hooper (the believer) and Dr. Vex (the skeptic) are :class:`rumi.Dervish`
subclasses. They argue ONLY over an :class:`~agents.packet.EvidencePacket`:
each is given the packet's ``as_prompt_block()`` as the sole evidence it may
cite, and may reference packet claim ids via ``cite("...")`` / ``quote("...")``.

Design constraints (see the shared contract):

* ``heart_config`` is a CLASS-LEVEL attribute with at least one
  :class:`rumi.Voice`. ``Voice.instructions`` IS the system prompt.
* Neither agent has any ``@tool`` — they only talk, they never fetch data.
  All headline numbers and verbatim quotes are code-templated downstream by
  ``synthesize()``; the agents only ever cite/quote packet claim ids.
* ``MODEL`` must be an OpenRouter model id for live runs.
"""

from __future__ import annotations

import os

from rumi import Dervish, HeartConfig, Voice

from prompts.trial_prompts import HOOPER_SYSTEM, DRVEX_SYSTEM

# Resolve the debate model once. RUMI_MODEL wins; otherwise fall back to the
# sentiment pipeline's strong model, then to a sane OpenRouter default.
MODEL = os.environ.get("RUMI_MODEL") or os.environ.get(
    "MODEL_STRONG", "~openai/gpt-latest"
)


class Hooper(Dervish):
    """The believer. Warm, hopeful, leans on the positive evidence.

    Higher temperature (0.7) — Hooper is the enthusiastic one, but is still
    bound to the packet: every number or quote must be a packet claim id.
    """

    heart_config = HeartConfig(
        voices=[
            Voice(
                model_name=MODEL,
                instructions=HOOPER_SYSTEM,
                context_window=16,
                temperature=0.7,
            )
        ]
    )


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
                instructions=DRVEX_SYSTEM,
                context_window=16,
                temperature=0.4,
            )
        ]
    )
