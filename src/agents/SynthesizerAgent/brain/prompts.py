"""SynthesizerAgent's prompt — the bottom line, split system-vs-message.

``INSTRUCTIONS`` is the rumi Voice.instructions string (the rules: 1-2 plain calm
sentences, words only / no invented numbers, no medical instruction, end with
exactly "discuss with your doctor."). ``build_message`` carries the per-call
payload: the confidence tier + the packet-derived facts json. The rule text is
byte-faithful to the original ``bottom_line_prompt``; only the system-vs-message
split is new.

``synthesize()`` code-fills the actual headline %, quotes, and side-effects from
the packet around this sentence — the model writes framing WORDS only.
"""


INSTRUCTIONS = """Write the BOTTOM LINE for a patient-facing briefing about one treatment, based ONLY on the facts below — real-world patient self-reports, not a trial.

Write 1-2 plain, calm sentences that:
- Summarize the overall lean in WORDS only — no digits, no specific number/percent/count/dose (the briefing fills those in). E.g. "patients mostly reported improvement, though the evidence is thin".
- Match the tier honestly: 'none'/'thin' sound tentative; 'suggestive' may be more encouraging but never certain.
- Give NO medical instruction (no start/stop/take/avoid/dose).
- End with exactly this clause: "discuss with your doctor.\""""


def build_message(tier: str, facts: dict) -> str:
    """The per-call user message: the confidence tier + packet-derived facts json.

    `tier` is the confidence_tier: 'none' | 'thin' | 'moderate' | 'suggestive'.
    `facts` is already-resolved, packet-derived fields (do not change them).
    """
    import json

    facts_json = json.dumps(facts, indent=2, ensure_ascii=False)
    return f"""Confidence tier: {tier!r}
Facts (do not change them):
{facts_json}

Bottom line:"""
