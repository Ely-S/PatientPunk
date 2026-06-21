"""TheTrialAgent's user prompts — the kickoff parse + the bottom-line framing.

``kickoff_parse_prompt`` turns a free-text patient question into a small JSON
structure (the drug query the deterministic Resolver looks up). ``bottom_line_prompt``
drives the ONE tool-less strong-model call in ``synthesize()`` — words only, no
numbers, no medical directive. All headline numbers / quotes in the final
briefing are code-templated by ``synthesize()`` FROM the packet — never written
by an LLM.

SAFETY (non-negotiable): no prompt may elicit a drug start/stop/take/dose
directive. Evidence is scoped; the doctor decides.
"""


def kickoff_parse_prompt(user_text: str) -> str:
    """Prompt the strong model to parse a free-text user question into structure.

    Returns a JSON object: {"drug_query", "user_context", "intent"}.
      - drug_query:   the single treatment/drug/supplement the user is asking
                      about, as they wrote it (used by the deterministic
                      Resolver to look up the canonical drug). null if none.
      - user_context: any conditions / situation the user mentioned, free text
                      (e.g. "ME/CFS, brain fog"). null if none.
      - intent:       short phrase for what they want to know
                      (e.g. "does it help", "is it safe", "side effects").

    Extraction only — no advice, no numbers, no invented fields.
    """
    return f"""Extract the query from this patient's question. Return ONLY a JSON object with exactly these keys:
- "drug_query": the ONE drug/supplement/intervention they ask about, copied verbatim (do not normalize or fix spelling). null if none. If multiple, pick the primary one.
- "user_context": their conditions/situation if stated, else null. Do not infer.
- "intent": a short phrase — e.g. "does it help", "is it safe", "side effects". "general" if unclear.
No advice, no numbers, no other keys.

Patient question:
\"\"\"{user_text}\"\"\"

JSON:"""


def bottom_line_prompt(tier: str, facts: dict) -> str:
    """Prompt for the ONE tool-less strong-model bottom line in synthesize().

    `facts` is a dict of already-resolved, packet-derived fields (drug name,
    tier, whether positives outweigh negatives, etc.). The model writes 1-2
    plain sentences of framing ONLY — it must not invent numbers, round, or
    give a prescription. synthesize() code-fills the actual headline %, quotes,
    and side-effects from the packet around this sentence.

    `tier` is the confidence_tier: 'none' | 'thin' | 'moderate' | 'suggestive'.
    """
    import json

    facts_json = json.dumps(facts, indent=2, ensure_ascii=False)
    return f"""Write the BOTTOM LINE for a patient-facing briefing about one treatment, based ONLY on the facts below — real-world patient self-reports, not a trial.

Confidence tier: {tier!r}
Facts (do not change them):
{facts_json}

Write 1-2 plain, calm sentences that:
- Summarize the overall lean in WORDS only — no digits, no specific number/percent/count/dose (the briefing fills those in). E.g. "patients mostly reported improvement, though the evidence is thin".
- Match the tier honestly: 'none'/'thin' sound tentative; 'suggestive' may be more encouraging but never certain.
- Give NO medical instruction (no start/stop/take/avoid/dose).
- End with exactly this clause: "discuss with your doctor."

Bottom line:"""
