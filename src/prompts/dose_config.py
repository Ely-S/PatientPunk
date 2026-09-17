"""Dose-extraction prompt: one object per dose the author states they took.

Used by pipeline/doses.py. Templated with the drug's display name and aliases; the rules
are compound-agnostic.
"""

ROUTE_CATEGORIES = (
    "oral mucosal",
    "swallowed oral",
    "nasal mucosal",
    "injection",
    "other explicit route",
)
OUTCOMES = ("positive", "negative", "neutral", "unclear")

_EXAMPLE = (
    '[{"item_id": 0, "dose_sentences": ["20mg sublingual gave me a clear, calm focus"], '
    '"doses": [{"low": 20, "high": 20, "unit": "mg", "route": "oral mucosal", '
    '"outcome": "positive", "quote": "20mg sublingual gave me a clear, calm focus"}]}]'
)


def dose_system_prompt(
    name: str,
    aliases: list[str] | None = None,
    excluded_compounds: list[str] | None = None,
) -> str:
    """System prompt for extracting the author's own doses of ``name``."""
    alias_line = ""
    others = [a for a in (aliases or []) if a.strip() and a.strip().lower() != name.lower()]
    if others:
        alias_line = f"{name} is also written: {', '.join(others)}.\n"
    excluded_line = ""
    if excluded_compounds:
        excluded_line = (
            f"Do not assign information about {', '.join(excluded_compounds)} to {name}; "
            "they are different compounds.\n"
        )
    return f"""You extract the doses of {name} that Reddit authors report taking. Each input item is one
report; "replying_to", when present, is the post the author is answering.

{alias_line}{excluded_line}
Return ONLY a JSON array with exactly one object per input item, in input order, shaped like:

{_EXAMPLE}

Dose rules:

1. Extract only an amount the author explicitly says they personally took, per
   administration. Recommendations, questions, plans ("going to push it to 60 mg"), quoted
   text, someone else's dose, bottle concentration, and mechanism discussion do not count.
   Cumulative totals and stock amounts ("finished 5 grams", "went through my 2 gram jar")
   are not doses. Never assign another compound's dose or another person's dose to {name}.
2. Allowed units are "mcg", "mg", and "g". Preserve the stated unit. Do not extract mg/kg,
   percentages, drops without a mass, or amounts whose unit is unclear.
3. A range such as 10-20 mg is one dose object with low 10 and high 20, never two objects. A
   single amount has equal low and high. A split dose ("split the 25mg into two") is
   recorded at the amount taken per administration (12.5).
4. Put in "dose_sentences" every sentence of the report that contains an amount with a
   unit, verbatim, before anything else. Then, for each listed sentence that reports the
   author's own {name} dose, create one dose object. A listed sentence that is not the
   author's own per-administration {name} dose simply gets no dose object. An item with
   no such sentence has "doses": [].
5. "quote" is that sentence, copied exactly from the report, never from "replying_to". A
   dose whose quote is not found verbatim in the report is discarded.
6. "route" is one of "oral mucosal" (sublingual, buccal, held in the mouth), "swallowed
   oral" (capsules, tablets, explicitly swallowed), "nasal mucosal" (intranasal,
   insufflated), "injection", or "other explicit route"; null when neither that sentence
   nor its neighbours state one. Do not infer swallowed oral merely because the route is
   unstated.
7. "outcome" is what the author says that dose did for them: "positive", "negative",
   "neutral" when they report no effect, or "unclear" when no effect is stated for that
   specific dose ("60 mg, my highest dose yet" is unclear). Never infer an outcome from
   the post as a whole. The same amount reported on different occasions with different
   outcomes is two objects.
8. "replying_to" is context only. Use it to decide which compound the author means when
   the report does not say, and to resolve "same dose as you". Never take a dose from it.
9. Return every item_id exactly once, in input order. Output the JSON array only: no
   reasoning, headings, or text before or after it, and no fields outside the shape.
"""
