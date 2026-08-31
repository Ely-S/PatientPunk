"""Exact alias matching with optional enclosing-compound exclusions."""

from __future__ import annotations

import re
from collections.abc import Iterable


def compile_alias_pattern(aliases: Iterable[str]) -> re.Pattern[str]:
    """Compile case-insensitive aliases with the pipeline's word-boundary rules."""
    normalized = sorted(
        {alias.strip() for alias in aliases if alias.strip()},
        key=len,
        reverse=True,
    )
    if not normalized:
        raise ValueError("At least one non-empty alias is required")
    return re.compile(
        r"\b(?:" + "|".join(re.escape(alias) for alias in normalized) + r")\b",
        re.IGNORECASE,
    )


def has_unexcluded_alias(
    text: str,
    aliases: Iterable[str],
    excluded_aliases: Iterable[str] = (),
) -> bool:
    """Return whether any alias match is not enclosed by an excluded compound.

    This handles names such as ``7,8-DHF`` that occur as a substring of the
    distinct derivative ``4'-DMA-7,8-DHF``. A text that names both compounds
    still matches the parent because its separate parent span is not enclosed.
    """
    include_matches = tuple(compile_alias_pattern(aliases).finditer(text))
    if not include_matches:
        return False

    excluded = tuple(alias for alias in excluded_aliases if alias.strip())
    if not excluded:
        return True
    excluded_spans = tuple(
        match.span() for match in compile_alias_pattern(excluded).finditer(text)
    )
    return any(
        not any(
            excluded_start <= match.start() and match.end() <= excluded_end
            for excluded_start, excluded_end in excluded_spans
        )
        for match in include_matches
    )
