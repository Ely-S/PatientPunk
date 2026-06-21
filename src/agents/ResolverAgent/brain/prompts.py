"""ResolverAgent's prompt — the kickoff parse, split system-vs-message.

``INSTRUCTIONS`` is the rumi Voice.instructions string (the system rules: extract
the ONE drug, return ONLY the JSON object with keys drug_query/user_context/intent,
copy-don't-normalize). ``build_message`` is the per-call user message — just the
patient's question. The rule text is byte-faithful to the original
``kickoff_parse_prompt``; only the system-vs-message split is new.

Extraction only — no advice, no numbers, no invented fields. The deterministic
Resolver in ``build_packet`` does the real canonical-drug resolution.
"""

INSTRUCTIONS = """Extract the query from this patient's question. Return ONLY a JSON object with exactly these keys:
- "drug_query": the ONE drug/supplement/intervention they ask about, copied verbatim (do not normalize or fix spelling). null if none. If multiple, pick the primary one.
- "user_context": their conditions/situation if stated, else null. Do not infer.
- "intent": a short phrase — e.g. "does it help", "is it safe", "side effects". "general" if unclear.
No advice, no numbers, no other keys."""


def build_message(user_text: str) -> str:
    """The per-call user message: just the patient's question."""
    return f"""Patient question:
\"\"\"{user_text}\"\"\"

JSON:"""
