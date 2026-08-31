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
