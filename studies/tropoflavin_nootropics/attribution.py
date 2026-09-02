"""Source-text corroboration for extracted comparator doses and routes."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import TypeAdapter

from studies.tropoflavin_nootropics.build_variable_corpus import UserCorpusRecord
from studies.tropoflavin_nootropics.comparator_support import ComparatorSpec
from studies.tropoflavin_nootropics.study_support import MassDosage, parse_mass_dosage
from utilities.alias_matching import compile_alias_pattern

MAX_ATTRIBUTION_DISTANCE = 400
_DOSE_PATTERN = re.compile(
    r"(?i)~?\d+(?:\.\d+)?\s*(?:(?:-|–|to)\s*~?\d+(?:\.\d+)?\s*)?"
    r"(?:mg|mcg|ug|µg|μg|g|gram|grams)\b"
)
_ROUTE_PATTERNS = {
    "oral": re.compile(r"(?i)\b(?:oral(?:ly)?|swallow(?:ed|ing)?|capsule|pill)\b"),
    "sublingual": re.compile(r"(?i)\b(?:sublingual(?:ly)?|under (?:my |the )?tongue|SL)\b"),
    "buccal": re.compile(r"(?i)\b(?:buccal(?:ly)?|inside (?:my |the )?cheek)\b"),
    "intranasal": re.compile(r"(?i)\b(?:intranasal(?:ly)?|nasal(?:ly)?|nose spray|snort(?:ed|ing)?)\b"),
    "topical": re.compile(r"(?i)\b(?:topical(?:ly)?|on (?:my |the )?skin|cream|ointment)\b"),
    "transdermal": re.compile(r"(?i)\b(?:transdermal(?:ly)?|skin patch)\b"),
    "inhaled": re.compile(r"(?i)\b(?:inhal(?:e|ed|ing)|vape(?:d|ing)?)\b"),
    "intravenous": re.compile(r"(?i)\b(?:intravenous(?:ly)?|IV|infusion)\b"),
    "intramuscular": re.compile(r"(?i)\b(?:intramuscular(?:ly)?|IM injection|IM)\b"),
    "subcutaneous": re.compile(r"(?i)\b(?:subcutaneous(?:ly)?|subq|sub-q|SC injection)\b"),
    "injection": re.compile(r"(?i)\b(?:inject(?:ed|ion|ing)?|shot)\b"),
    "rectal": re.compile(r"(?i)\brectal(?:ly)?\b"),
    "vaginal": re.compile(r"(?i)\bvaginal(?:ly)?\b"),
    "suppository": re.compile(r"(?i)\bsuppositor(?:y|ies)\b"),
}


def load_author_segments(directory: Path) -> dict[str, tuple[str, ...]]:
    """Load private author text into an in-memory corroboration index."""
    records: dict[str, tuple[str, ...]] = {}
    adapter = TypeAdapter(UserCorpusRecord)
    for path in sorted((directory / "users").glob("*.json")):
        record = adapter.validate_python(json.loads(path.read_text(encoding="utf-8")))
        texts: list[str] = []
        for post in record.posts:
            if post.title.strip():
                texts.append(post.title)
            if post.body.strip():
                texts.append(post.body)
        texts.extend(
            comment.body for comment in record.comments if comment.body.strip()
        )
        records[record.author_hash] = tuple(texts)
    return records


def _compound_spans(text: str, compound: ComparatorSpec) -> tuple[tuple[int, int], ...]:
    include = tuple(compile_alias_pattern(compound.aliases).finditer(text))
    if not compound.excluded_aliases:
        return tuple(match.span() for match in include)
    excluded = tuple(
        match.span()
        for match in compile_alias_pattern(compound.excluded_aliases).finditer(text)
    )
    return tuple(
        match.span()
        for match in include
        if not any(
            start <= match.start() and match.end() <= end for start, end in excluded
        )
    )


def _nearby(
    compound_spans: tuple[tuple[int, int], ...],
    evidence_span: tuple[int, int],
    max_distance: int,
) -> bool:
    evidence_start, evidence_end = evidence_span
    return any(
        max(evidence_start - compound_end, compound_start - evidence_end, 0)
        <= max_distance
        for compound_start, compound_end in compound_spans
    )


def corroborates_dose(
    compound: ComparatorSpec,
    raw_value: str,
    segments: tuple[str, ...],
    *,
    max_distance: int = MAX_ATTRIBUTION_DISTANCE,
) -> bool:
    """Require a matching dose near the compound in one author text segment."""
    expected = parse_mass_dosage(raw_value)
    if expected is None:
        return False
    return any(
        abs(observed.low_mg - expected.low_mg) < 1e-9
        and abs(observed.high_mg - expected.high_mg) < 1e-9
        for observed in corroborated_masses(
            compound,
            segments,
            max_distance=max_distance,
        )
    )


def corroborated_masses(
    compound: ComparatorSpec,
    segments: tuple[str, ...],
    *,
    max_distance: int = MAX_ATTRIBUTION_DISTANCE,
) -> tuple[MassDosage, ...]:
    """Return unique mass doses found near a compound in the same segment."""
    found: dict[tuple[float, float], MassDosage] = {}
    for segment in segments:
        compound_spans = _compound_spans(segment, compound)
        if not compound_spans:
            continue
        for match in _DOSE_PATTERN.finditer(segment):
            observed = parse_mass_dosage(match.group())
            if observed is None:
                continue
            if _nearby(compound_spans, match.span(), max_distance):
                found[(observed.low_mg, observed.high_mg)] = observed
    return tuple(found[key] for key in sorted(found))


def corroborates_route(
    compound: ComparatorSpec,
    raw_value: str,
    segments: tuple[str, ...],
    *,
    max_distance: int = MAX_ATTRIBUTION_DISTANCE,
) -> bool:
    """Require explicit route language near the compound in one text segment."""
    pattern = _ROUTE_PATTERNS.get(raw_value.strip().lower())
    if pattern is None:
        return False
    for segment in segments:
        compound_spans = _compound_spans(segment, compound)
        if not compound_spans:
            continue
        if any(
            _nearby(compound_spans, match.span(), max_distance)
            for match in pattern.finditer(segment)
        ):
            return True
    return False
