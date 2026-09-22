"""Exact alias matching with enclosing-compound exclusions.

Aliases and exclusions are literal spellings (case-insensitive, word-bounded).
Apostrophe look-alikes (’ ′ ‘ ` ´) are normalised to ``'`` and dash look-alikes
(‐ ‑ ‒ – — ― −) to ``-`` before matching;
each is one code point, so spans stay valid on the original text.

Ported from PR #146 (commit 998e634) so the core pipeline can exclude enclosing
compounds without the study layer. The code is identical to that commit; the study's
cohort config, corpus prefilter, and span-based attribution stay on the study branch.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_APOSTROPHES = re.compile("[\u2019\u2032\u2018\u0060\u00b4]")
_DASHES = re.compile("[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]")


def normalize_text(text: str) -> str:
    """Map apostrophe and dash look-alikes to ' and -; length is preserved."""
    return _DASHES.sub("-", _APOSTROPHES.sub("'", text))


def compile_alias_pattern(aliases: Iterable[str]) -> re.Pattern[str]:
    """Compile case-insensitive aliases with the pipeline's word-boundary rules."""
    normalized = sorted(
        {normalize_text(alias.strip().lower()) for alias in aliases if alias.strip()},
        key=len,
        reverse=True,
    )
    if not normalized:
        raise ValueError("At least one non-empty alias is required")
    # A straight quote in an alias also matches its curly look-alikes, so the pattern
    # is safe on un-normalised text too (alias_spans normalises anyway).
    quote_class = "['\u2019\u2032\u2018\u0060\u00b4]"
    return re.compile(
        r"\b(?:" + "|".join(re.escape(alias).replace("'", quote_class) for alias in normalized) + r")\b",
        re.IGNORECASE,
    )


def alias_spans(
    text: str,
    aliases: Iterable[str],
    excluded_aliases: Iterable[str] = (),
) -> tuple[tuple[int, int], ...]:
    """Spans of alias matches that no excluded alias encloses."""
    text = normalize_text(text)
    spans = tuple(m.span() for m in compile_alias_pattern(aliases).finditer(text))
    if not spans:
        return ()
    excluded = [alias for alias in excluded_aliases if alias.strip()]
    if not excluded:
        return spans
    blocked = tuple(m.span() for m in compile_alias_pattern(excluded).finditer(text))
    return tuple(
        (start, end)
        for start, end in spans
        if not any(bs <= start and end <= be for bs, be in blocked)
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
    return bool(alias_spans(text, aliases, excluded_aliases))
