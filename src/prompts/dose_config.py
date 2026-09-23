"""Extraction prompt for stated doses and explicit routes without an amount.

Used by pipeline/doses.py. Templated with the drug's display name and aliases; the rules
are compound-agnostic.
"""

from importlib.resources import files

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
    template = files("prompts").joinpath("dose_system.txt").read_text(encoding="utf-8")
    return template.format(name=name, alias_line=alias_line, excluded_line=excluded_line, example=_EXAMPLE)
