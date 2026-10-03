"""Dose-extraction prompt for author-reported administrations."""

from importlib.resources import files
from string import Formatter

ROUTE_CATEGORIES = (
    "oral mucosal",
    "swallowed oral",
    "nasal mucosal",
    "injection",
    "other explicit route",
)
OUTCOMES = ("positive", "negative", "neutral", "unclear")

_TEMPLATE = files("prompts").joinpath("dose_system.txt").read_text(encoding="utf-8")
_VARIABLES = {name for _, name, _, _ in Formatter().parse(_TEMPLATE) if name}
if _VARIABLES != {"name", "alias_line", "excluded_line", "example"}:
    raise ValueError(f"Unexpected dose prompt variables: {_VARIABLES}")

_EXAMPLE = (
    '[{"item_id": 0, "dose_sentences": ["I took 20mg of <TARGET>", '
    '"I also took 10mg of another compound"], "doses": ['
    '{"low": 20, "high": 20, "unit": "mg", "attribution": "target", '
    '"quote": "I took 20mg of <TARGET>"}, '
    '{"low": 10, "high": 10, "unit": "mg", "attribution": "other", '
    '"quote": "I also took 10mg of another compound"}]}]'
)


def dose_system_prompt(
    name: str,
    aliases: list[str] | None = None,
    excluded_compounds: list[str] | None = None,
) -> str:
    """System prompt for identifying the author's own doses of ``name``."""
    others = [a for a in (aliases or []) if a.strip() and a.strip().lower() != name.lower()]
    alias_line = f"{name} is also written: {', '.join(others)}.\n" if others else ""
    excluded_line = (
        f"Do not assign information about {', '.join(excluded_compounds)} to {name}; "
        "they are different compounds.\n"
        if excluded_compounds else ""
    )
    return _TEMPLATE.format(
        name=name,
        alias_line=alias_line,
        excluded_line=excluded_line,
        example=_EXAMPLE.replace("<TARGET>", name),
    )
