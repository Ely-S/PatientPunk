"""The Trial — a two-agent debate over a FROZEN evidence packet.

This package builds a deterministic real-world-evidence packet for a single
drug (``packet.py``), then stages a tone-only debate between two patient-facing
personas — Hooper (optimist) and Dr. Vex (skeptic) — over that packet, with a
hard no-fabrication gate (``validate.py``) enforcing that every number/quote
traces to a packet claim_id.

Public re-exports: ``run_trial``, ``build_packet``, ``EvidencePacket``.

Imports here are intentionally LAZY (PEP 562 ``__getattr__``): the submodules
pull in rumi / the DB layer, which not every consumer needs — the validate gate
is pure-Python and standalone, and ``build_packet`` needs no rumi at all. So
``import agents`` stays cheap; the heavy import happens only when you touch one
of the re-exported names (or import a submodule directly, e.g.
``from agents._common.validate import check_turn``).

Part of the ``src/`` sentiment system. Never import ``patientpunk`` /
``variable_extraction`` here — that decoupling boundary is frozen.
"""
from __future__ import annotations

__all__ = ["run_trial", "build_packet", "EvidencePacket"]


def __getattr__(name: str):
    # Lazy: defer the (rumi/DB-touching) submodule import until first access.
    if name in ("build_packet", "EvidencePacket"):
        from agents._common import packet

        return getattr(packet, name)
    if name == "run_trial":
        from agents.TheTrialAgent import main

        return main.run_trial
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + __all__)
