"""Effect-extraction prompt: one object per effect the author says the drug had on them.

Used by pipeline/effects.py. Templated with the drug's display name, aliases, exclusions
and the run's domain list; the rules are compound-agnostic.
"""

DOMAINS = (
    "anxiety or stress",
    "sleep or wakefulness",
    "mood or depression",
    "focus or attention",
    "memory or learning",
    "cognition or brain fog",
    "energy or motivation",
    "neuroprotection or recovery",
    "pain or neurologic symptoms",
    "stimulant recovery or reduction",
    "cardiovascular or autonomic",
    "hair or skin",
    "gastrointestinal",
    "social functioning",
    "sexual function",
    "overall",
    "other specified effect",
)
DIRECTIONS = ("improved", "worsened", "no_change", "mixed")
ATTRIBUTIONS = ("target", "stack", "unclear", "other compound")


def _wrap(items: tuple[str, ...] | list[str], width: int = 92) -> str:
    lines: list[str] = []
    line = ""
    for item in items:
        piece = f"{item}; " if item != items[-1] else item
        if line and len(line) + len(piece) > width:
            lines.append(line.rstrip())
            line = ""
        line += piece
    lines.append(line.rstrip())
    return "\n".join(lines)


def effects_system_prompt(
    name: str,
    aliases: list[str] | None = None,
    excluded_compounds: list[str] | None = None,
    domains: tuple[str, ...] | list[str] = DOMAINS,
) -> str:
    """System prompt for extracting what authors say ``name`` did for them."""
    alias_line = ""
    others = [a for a in (aliases or []) if a.strip() and a.strip().lower() != name.lower()]
    if others:
        alias_line = f"{name} is also written: {', '.join(others)}.\n"
    excluded_line = ""
    if excluded_compounds:
        excluded_line = (
            f"Do not assign information about {', '.join(excluded_compounds)} to {name}; "
            f"they are different compounds, and their effects get \"other compound\", never \"{name}\".\n"
        )
    example = (
        '[{"item_id": 0, "effects": [{"domain": "energy or motivation", "symptom": "energy",\n'
        f'"direction": "improved", "attribution": "{name}", "quote": "50mg gave me clean energy all\n'
        'day", "dose": 1}]}]'
    )
    return f"""You extract what Reddit authors say {name} did for them. Each input item is one
report. "thread" is the title of the post that started the thread and "replying_to"
is the post the author is answering; both are context only. "doses", when present,
lists the doses already extracted from this report, each with an id and its sentence.

{alias_line}{excluded_line}
Return ONLY a JSON array with exactly one object per input item, in input order, shaped like:

{example}

Domains (use exactly one of these strings per effect):
{_wrap(tuple(domains))}

Rules:

1. Record an effect only when the author reports what happened to them after taking
   {name}, alone or in a stack. Expectations, plans, questions, recommendations,
   mechanism talk ("it raises BDNF"), other people's experiences, and quoted text do not
   count. Writing "it" counts when "thread" or "replying_to" shows that "it" is {name}.
   An item with nothing to record has "effects": [].
2. One effect object per domain and direction the author reports. "symptom" is the
   author's own words for what changed, 1-4 words ("brain fog", "less tired", "insomnia").
   Use domain "overall" for a verdict that names no symptom ("did nothing for me").
3. "direction" is what the compound did while the author was taking it: "improved",
   "worsened", "no_change" (the author says it did nothing for that symptom), or "mixed".
   Side effects are effects with direction "worsened". Getting worse after stopping it
   means "improved".
4. "attribution" is "{name}" when the author credits or blames {name} itself; "stack"
   when they credit a combination that includes it without singling it out; "unclear" when
   the report does not say which compound produced the effect; "other compound" when the
   author attributes the effect to a different compound they name. When the report does not
   name the compound, decide from "replying_to" and "thread": a reply under a post about
   another compound is about that compound, so "other compound"; if the context does not
   settle it, "unclear".
5. "quote" is the sentence that states the effect, copied exactly from "report", never
   from "replying_to". An effect whose quote is not found verbatim in the report is discarded.
6. "dose" is the id of the listed dose the author ties this effect to ("at 50 mg I got
   headaches"), or null when the effect is not tied to a listed dose. Never invent one.
7. Return every item_id exactly once, in input order. Output the JSON array only: no
   reasoning, headings, or text before or after it, and no fields outside the shape.
"""
