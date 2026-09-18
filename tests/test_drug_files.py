"""Every drug file is well-formed, and the 7,8-DHF pair behaves under the matcher."""

from pathlib import Path

import pytest

from utilities.alias_matching import has_unexcluded_alias

DRUG_FILES = Path(__file__).parent.parent / "drug_files"
ALL = sorted(DRUG_FILES.glob("*.txt"))
_lines = lambda path: [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
PARENT = _lines(DRUG_FILES / "78dhf.txt")
EXCLUDED = _lines(DRUG_FILES / "78dhf.exclude.txt")


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
