"""Every drug file is well-formed, and the 7,8-DHF / 4'-DMA pair behaves under the matcher."""

from pathlib import Path

import pytest

from utilities.alias_matching import has_unexcluded_alias

DRUG_FILES = Path(__file__).parent.parent / "drug_files"
ALL = sorted(DRUG_FILES.glob("*.txt"))
_lines = lambda path: [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
PARENT = _lines(DRUG_FILES / "78dhf.txt")
EXCLUDED = _lines(DRUG_FILES / "4dma-78dhf.txt")  # the derivative's own synonyms are the exclusions


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_drug_file_has_no_blank_or_duplicate_lines(path: Path) -> None:
    lines = _lines(path)
    assert lines and all(lines), f"{path.name} has a blank line"
    lowered = [line.lower() for line in lines]
    assert len(set(lowered)) == len(lowered), f"{path.name} has duplicate spellings"


@pytest.mark.parametrize("spelling", PARENT)
def test_every_parent_spelling_matches_the_parent(spelling: str) -> None:
    assert has_unexcluded_alias(f"took {spelling} today", PARENT, EXCLUDED)


@pytest.mark.parametrize("spelling", EXCLUDED)
def test_every_excluded_spelling_alone_is_not_the_parent(spelling: str) -> None:
    assert not has_unexcluded_alias(f"took {spelling} today", PARENT, EXCLUDED)


def test_naming_both_compounds_still_counts_as_the_parent() -> None:
    text = "I got nothing from 7,8-DHF but 4'-DMA-7,8-DHF was a game changer"
    assert has_unexcluded_alias(text, PARENT, EXCLUDED)


# The three case lists below are PR #146's, unchanged; there they ran against the study's
# cohort config, here against the same spellings in drug_files/.
@pytest.mark.parametrize(
    "text",
    [
        "I tried 4'-DMA-7,8-DHF yesterday.",
        "I tried 4\u2019-DMA-7,8-DHF yesterday.",  # curly apostrophe
        "4DMA-78DHF sublingual 10mg",
        "4 dma 7'8 dhf while abstaining",
        "4-DMA-7-8-DHF has a very good mood boost",
        "4'-Dimethylamino-7,8-dihydroxyflavone making me tired",
        "Just got some 4dma.",
    ],
)
def test_derivative_spellings_are_not_the_parent(text: str) -> None:
    assert not has_unexcluded_alias(text, PARENT, EXCLUDED)
    assert has_unexcluded_alias(text, EXCLUDED)  # but they are the derivative


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
    assert has_unexcluded_alias(text, PARENT, EXCLUDED)


def test_no_false_matches() -> None:
    assert not has_unexcluded_alias("MDMA and DMAE are different things", EXCLUDED)
    assert not has_unexcluded_alias("amazon.com/4-DMA-7-8-DHF-Capsules-Count-8-Dihydroxyflavone/dp/B0", PARENT, EXCLUDED)
