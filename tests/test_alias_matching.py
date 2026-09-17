import json

import pytest

from studies.tropoflavin_nootropics.comparator_support import load_comparator_cohort, prefilter_hit
from utilities.alias_matching import compile_alias_pattern, has_unexcluded_alias

PARENT_ALIASES = ["7,8-dhf", "dhf", "tropoflavin"]
DERIVATIVE_ALIASES = ["4'-dma-7,8-dhf", "4dma-7,8dhf", "eutropoflavin"]


def test_alias_pattern_requires_at_least_one_alias() -> None:
    try:
        compile_alias_pattern([])
    except ValueError as exc:
        assert "non-empty alias" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("empty aliases should fail")


def test_enclosing_derivative_does_not_count_as_parent() -> None:
    assert not has_unexcluded_alias(
        "I tried 4'-DMA-7,8-DHF yesterday.",
        PARENT_ALIASES,
        DERIVATIVE_ALIASES,
    )


def test_separate_parent_mention_survives_derivative_exclusion() -> None:
    assert has_unexcluded_alias(
        "4'-DMA-7,8-DHF was active, while plain 7,8-DHF did nothing.",
        PARENT_ALIASES,
        DERIVATIVE_ALIASES,
    )


def test_plain_parent_and_unrelated_words_match_normally() -> None:
    assert has_unexcluded_alias(
        "Tropoflavin is the version I used.",
        PARENT_ALIASES,
        DERIVATIVE_ALIASES,
    )
    assert not has_unexcluded_alias(
        "A different flavonoid was discussed.",
        PARENT_ALIASES,
        DERIVATIVE_ALIASES,
    )


# ── Cohort spelling lists ────────────────────────────────────────────────────

COHORT_CONFIG = load_comparator_cohort()
COHORT = COHORT_CONFIG.by_slug()
PARENT, DERIVATIVE = COHORT["78dhf"], COHORT["4dma-78dhf"]


@pytest.mark.parametrize("alias", DERIVATIVE.aliases)
def test_every_derivative_alias_is_excluded_from_parent(alias: str) -> None:
    assert DERIVATIVE.matches(alias)
    assert not PARENT.matches(alias)


@pytest.mark.parametrize("alias", PARENT.aliases)
def test_every_parent_alias_matches_parent_only(alias: str) -> None:
    assert PARENT.matches(alias)
    assert not DERIVATIVE.matches(alias)


def test_direct_pattern_matches_curly_apostrophe_text() -> None:
    assert compile_alias_pattern(["4'-dma"]).search("took 4\u2019-DMA today")


@pytest.mark.parametrize(
    "text",
    [
        "I tried 4'-DMA-7,8-DHF yesterday.",
        "I tried 4’-DMA-7,8-DHF yesterday.",  # curly apostrophe
        "4DMA-78DHF sublingual 10mg",
        "4 dma 7'8 dhf while abstaining",
        "4-DMA-7-8-DHF has a very good mood boost",
        "4'-Dimethylamino-7,8-dihydroxyflavone making me tired",
        "Just got some 4dma.",
    ],
)
def test_derivative_spellings_are_not_the_parent(text: str) -> None:
    assert not PARENT.matches(text)
    assert DERIVATIVE.matches(text)


@pytest.mark.parametrize(
    "text",
    [
        "4-DMA and 7,8-DHF were my gift",
        "regular 78 dhf vs 4dma 78 dhf",
        "DMAE and 7,8-DHF",
        "The 25mg one is its parent molecule 7'8DHF",
        "7, 8-Dihydroxyflavone WTF",
    ],
)
def test_separately_named_parent_matches(text: str) -> None:
    assert PARENT.matches(text)


def test_no_false_matches() -> None:
    assert not DERIVATIVE.matches("MDMA and DMAE are different things")
    assert not PARENT.matches("amazon.com/4-DMA-7-8-DHF-Capsules-Count-8-Dihydroxyflavone/dp/B0")


def test_spans_index_the_original_text() -> None:
    text = "4’-DMA-7,8-DHF is strong; plain 7,8-DHF is subtle."
    assert [text[s:e] for s, e in PARENT.spans(text)] == ["7,8-DHF"]


@pytest.mark.parametrize("compound", COHORT_CONFIG.compounds, ids=lambda c: c.slug)
def test_every_configured_alias_passes_the_corpus_prefilter(compound) -> None:
    """A spelling that fails the bytes-level prefilter never reaches the matcher in a corpus build."""
    inert = [
        alias for alias in compound.aliases
        if not prefilter_hit(json.dumps({"body": alias}, ensure_ascii=False).encode("utf-8"), COHORT_CONFIG)
    ]
    assert inert == []
