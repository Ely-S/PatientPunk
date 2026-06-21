"""The arena for "The Trial": wire up the Rumi World, run the debate, drive a trial.

``run_debate`` builds a single zero-config :class:`rumi.World`, instantiates
Hooper and Dr. Vex with *fresh* per-run ``agent_id``s, seeds Hooper with the
evidence packet, and runs an alternating back-and-forth driver loop. The
back-and-forth is OUR loop: we take a speaker's ``whirl(message).content``
(a plain str), append it to the transcript, then feed that string as the next
speaker's message. We never pass a ``TextIdea`` object across — ``whirl``
rejects non-user ideas.

``run_trial`` is the end-to-end entrypoint: parse the user's prompt for a drug
query, build the deterministic evidence packet, short-circuit if there are no
reports, otherwise run the debate and synthesize a briefing.
"""

from __future__ import annotations

import os
import tempfile
import uuid

from rumi import World

from utilities import get_client, llm_call, parse_json_object, MODEL_FAST

from agents._common.packet import build_packet
from agents.HooperAgent.main import Hooper
from agents.DrVexAgent.main import DrVex
from agents.TheTrialAgent.synthesize import synthesize
from agents.TheTrialAgent.brain.prompts import kickoff_parse_prompt


def _fresh_suffix(agent_suffix: str = "") -> str:
    """A collision-free agent-id suffix.

    Rumi replays disk history for a reused (world, class, agent_id) triple, so
    every run must use a brand-new id to avoid contaminating the debate with a
    prior run's turns.
    """
    base = uuid.uuid4().hex[:8]
    return f"{agent_suffix}-{base}" if agent_suffix else base


def run_debate(packet, *, rounds: int = 2, agent_suffix: str = "", on_turn=None) -> list[dict]:
    """Run the Hooper vs. Dr. Vex debate over ``packet``.

    Builds one ``World()`` (zero-config from env). If ``RUMI_DATA_DIR`` is
    unset we point it at a fresh temp dir so Rumi's on-disk history never bleeds
    across runs. Seeds Hooper with the packet's prompt block and an opening
    cue, then loops ``rounds * 2`` turns, alternating Hooper -> Dr. Vex.

    ``on_turn`` is an OPTIONAL callback. When provided, it is invoked with each
    turn dict (``{"agent": str, "text": str}``) right after that turn is appended
    to the transcript — letting a live consumer (e.g. the trial server) stream
    the debate as it unfolds. Default ``None`` is fully backward-compatible.

    Returns the transcript as a list of ``{"agent": str, "text": str}`` dicts in
    speaking order.
    """
    # Rumi's World is zero-config from the environment. Make history ephemeral
    # unless the caller has explicitly pinned a data dir.
    if not os.environ.get("RUMI_DATA_DIR"):
        os.environ["RUMI_DATA_DIR"] = tempfile.mkdtemp(prefix="trial-rumi-")

    world = World()

    suffix = _fresh_suffix(agent_suffix)
    hooper = Hooper(world=world, agent_id=f"hooper-{suffix}")
    drvex = DrVex(world=world, agent_id=f"drvex-{suffix}")

    # Hooper opens. The packet block is the ONLY evidence either agent sees.
    message = (
        packet.as_prompt_block()
        + "\n\nHOOPER, open with your pitch."
    )

    transcript: list[dict] = []
    # speaker/listener alternate; Hooper speaks first.
    speaker, name = hooper, "hooper"
    other, other_name = drvex, "drvex"

    for _ in range(rounds * 2):
        reply = speaker.whirl(message).content
        turn = {"agent": name, "text": reply}
        transcript.append(turn)
        # Stream the freshly-appended turn to a live consumer, if any.
        if on_turn is not None:
            on_turn(turn)
        # Hand the plain string to the other agent as its next user message.
        message = reply
        speaker, other = other, speaker
        name, other_name = other_name, name

    return transcript


def _parse_drug_query(user_prompt: str) -> str:
    """Best-effort extraction of the target drug from the user's free text.

    Uses the fast model with ``kickoff_parse_prompt``. Tolerates any parse
    failure by falling back to the raw user prompt as the drug query — the
    deterministic Resolver in ``build_packet`` does the real resolution.
    """
    raw_query = user_prompt.strip()
    try:
        client = get_client()
        raw = llm_call(
            client,
            kickoff_parse_prompt(user_prompt),
            model=MODEL_FAST,
            max_tokens=120,
        )
        parsed = parse_json_object(raw)
        candidate = (parsed.get("drug_query") or parsed.get("drug") or "").strip()
        if candidate:
            return candidate
    except Exception:
        # Any failure (no key, bad JSON, network) -> fall back to raw text.
        pass
    return raw_query


def run_trial(user_prompt: str, db_path: str, *, rounds: int = 2) -> dict:
    """End-to-end: parse -> build packet -> (short-circuit | debate -> synthesize).

    Returns a briefing dict. When no reports exist for the resolved drug, the
    debate is skipped entirely and a short "no reports" briefing is returned
    (``transcript`` empty, ``found`` False).
    """
    drug_query = _parse_drug_query(user_prompt)

    packet = build_packet(drug_query, db_path)

    if not packet.found:
        # No evidence -> no debate. Return an honest, empty-handed briefing.
        prov = packet.provenance or {}
        return {
            "found": False,
            "drug_query": packet.drug_query,
            "drug": packet.drug,
            "text": (
                f"No patient reports for {packet.drug_query!r} in our corpus. "
                "There is nothing to put on trial — we cannot say anything "
                "about it from this data. "
                "This is anecdotal patient data, not medical advice — please "
                "discuss with your doctor."
            ),
            "transcript": [],
            "packet": packet,
            "provenance": prov,
        }

    transcript = run_debate(packet, rounds=rounds)
    briefing = synthesize(packet, transcript)
    briefing.setdefault("found", True)
    briefing.setdefault("drug_query", packet.drug_query)
    briefing.setdefault("drug", packet.drug)
    briefing.setdefault("transcript", transcript)
    briefing.setdefault("packet", packet)
    return briefing
