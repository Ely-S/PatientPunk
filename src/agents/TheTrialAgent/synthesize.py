"""Deterministically render the trial briefing from the EvidencePacket.

The agents' banter is NEVER trusted for numbers or quotes. ``synthesize`` builds
the briefing's spine — headline sentiment split, confidence tier, side effects
to watch, real verbatim quotes, and the four caveats — entirely from the packet.
The ONLY generative call is a single tool-less bottom line from the
:class:`~agents.SynthesizerAgent.main.SynthesizerAgent` (its model lives in
``brain/brain.json``), and even that is fed packet-derived facts and constrained
by its prompt (no dose/start/stop directives).

A fixed safety coda and a provenance footer are always appended.
"""

from __future__ import annotations

from agents.SynthesizerAgent.main import write_bottom_line

# Never a medical directive — always the doctor's call.
SAFETY_CODA = (
    "This is anecdotal patient data, not medical advice — please discuss with "
    "your doctor."
)

_TIER_BLURB = {
    "none": "No usable signal.",
    "thin": "Thin evidence — treat as a rumor, not a finding.",
    "moderate": "Moderate evidence — enough to notice, not enough to bank on.",
    "suggestive": "Suggestive evidence — a real pattern, still anecdotal.",
}


def _pct(packet, key: str) -> int:
    try:
        return int(packet.pct.get(key, 0))
    except Exception:
        return 0


def _count(packet, key: str) -> int:
    try:
        return int(packet.counts.get(key, 0))
    except Exception:
        return 0


def _quotes_for_pole(packet, pole: str, limit: int = 2) -> list[dict]:
    out: list[dict] = []
    for q in packet.quotes or []:
        if q.get("pole") == pole:
            out.append(q)
        if len(out) >= limit:
            break
    return out


def _prov_footer(packet) -> str:
    prov = packet.provenance or {}
    run_id = prov.get("run_id", "?")
    commit = prov.get("commit_hash", "?")
    run_at = prov.get("run_at", "")
    tail = f" · {run_at}" if run_at else ""
    return f"[prov] run_id={run_id} · commit={commit}{tail}"


def synthesize(packet, transcript) -> dict:
    """Render the final briefing dict for a *found* drug.

    Code-fills the headline (S2/S3 over n_users), confidence tier, side effects
    (SE*), up to two real quotes per pole, and the four caveats — all from the
    packet. Then asks the SynthesizerAgent for a <=2-sentence bottom line, and
    appends the safety coda + provenance footer.
    """
    drug = packet.drug
    n_users = packet.n_users

    pos_n, pos_p = _count(packet, "positive"), _pct(packet, "positive")
    neg_n, neg_p = _count(packet, "negative"), _pct(packet, "negative")
    mixed_n, mixed_p = _count(packet, "mixed"), _pct(packet, "mixed")
    neutral_n, neutral_p = _count(packet, "neutral"), _pct(packet, "neutral")

    tier = packet.confidence_tier or "none"

    # ---- Headline (deterministic, from packet) --------------------------------
    headline = (
        f"{drug.upper()} — {pos_p}% positive · {neg_p}% negative · "
        f"{mixed_p}% mixed · {neutral_p}% neutral "
        f"(across {n_users} patient{'s' if n_users != 1 else ''})."
    )

    # ---- Side effects to watch (SE*) ------------------------------------------
    side_effects = []
    for se in packet.side_effects or []:
        eff = se.get("effect")
        cnt = se.get("count")
        if eff:
            side_effects.append(
                f"{eff}" + (f" ({cnt})" if cnt is not None else "")
            )

    # ---- Real quotes, up to 2 per pole, verbatim from packet ------------------
    pos_quotes = [q.get("text", "") for q in _quotes_for_pole(packet, "pos", 2)]
    neg_quotes = [q.get("text", "") for q in _quotes_for_pole(packet, "neg", 2)]

    # ---- The four caveats (from packet) ---------------------------------------
    caveats = [c.get("text", "") for c in (packet.caveats or [])]

    # ---- Assemble the rendered briefing body ----------------------------------
    lines: list[str] = []
    lines.append(headline)
    lines.append("")
    lines.append(f"Confidence: {tier} — {_TIER_BLURB.get(tier, '')}".rstrip())
    lines.append("")

    if pos_quotes or neg_quotes:
        lines.append("In patients' own words:")
        for t in pos_quotes:
            if t:
                lines.append(f"  (+) “{t}”")
        for t in neg_quotes:
            if t:
                lines.append(f"  (-) “{t}”")
        lines.append("")

    if side_effects:
        lines.append("Side effects to watch: " + "; ".join(side_effects) + ".")
        lines.append("")

    if caveats:
        lines.append("Read the fine print:")
        for c in caveats:
            if c:
                lines.append(f"  • {c}")
        lines.append("")

    # ---- The single generative bottom line (tool-less, packet-fed) ------------
    facts = {
        "drug": drug,
        "n_users": n_users,
        "positive": {"count": pos_n, "pct": pos_p},
        "negative": {"count": neg_n, "pct": neg_p},
        "mixed": {"count": mixed_n, "pct": mixed_p},
        "neutral": {"count": neutral_n, "pct": neutral_p},
        "signal_mix": dict(packet.signal_mix or {}),
        "side_effects": side_effects,
        "confidence_tier": tier,
    }

    # The single generative bottom line — delegated to the SynthesizerAgent
    # Dervish, which carries its own deterministic fallback sentence on failure.
    bottom_line = write_bottom_line(tier, facts)

    if bottom_line:
        if bottom_line.lower().startswith("bottom line"):
            lines.append(bottom_line)
        else:
            lines.append("Bottom line: " + bottom_line)
        lines.append("")

    # ---- Fixed safety coda + provenance footer --------------------------------
    lines.append(SAFETY_CODA)
    lines.append("")
    lines.append(_prov_footer(packet))

    text = "\n".join(lines).rstrip() + "\n"

    return {
        "found": True,
        "drug_query": packet.drug_query,
        "drug": drug,
        "tier": tier,
        "headline": headline,
        "bottom_line": bottom_line,
        "side_effects": side_effects,
        "pos_quotes": pos_quotes,
        "neg_quotes": neg_quotes,
        "caveats": caveats,
        "text": text,
        "transcript": transcript,
        "packet": packet,
        "provenance": dict(packet.provenance or {}),
    }
