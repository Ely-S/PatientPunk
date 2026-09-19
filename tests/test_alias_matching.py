"""Alias matching with enclosing-compound exclusions (ported from PR #146). No API calls."""

import json
import sqlite3
from pathlib import Path

import pytest

from pipeline.extract import run_extraction
from utilities import PipelineConfig
from utilities.alias_matching import alias_spans, compile_alias_pattern, has_unexcluded_alias

PARENT_ALIASES = ["7,8-dhf", "dhf", "tropoflavin"]
DERIVATIVE_ALIASES = ["4'-dma-7,8-dhf", "4dma-7,8dhf", "eutropoflavin"]


def test_alias_pattern_requires_at_least_one_alias() -> None:
    with pytest.raises(ValueError, match="non-empty alias"):
        compile_alias_pattern([])


def test_enclosing_derivative_does_not_count_as_parent() -> None:
    assert not has_unexcluded_alias("I tried 4'-DMA-7,8-DHF yesterday.", PARENT_ALIASES, DERIVATIVE_ALIASES)


def test_separate_parent_mention_survives_derivative_exclusion() -> None:
    assert has_unexcluded_alias(
        "4'-DMA-7,8-DHF was active, while plain 7,8-DHF did nothing.", PARENT_ALIASES, DERIVATIVE_ALIASES
    )


def test_plain_parent_and_unrelated_words_match_normally() -> None:
    assert has_unexcluded_alias("Tropoflavin is the version I used.", PARENT_ALIASES, DERIVATIVE_ALIASES)
    assert not has_unexcluded_alias("A different flavonoid was discussed.", PARENT_ALIASES, DERIVATIVE_ALIASES)


def test_direct_pattern_matches_curly_apostrophe_text() -> None:
    assert compile_alias_pattern(["4'-dma"]).search("took 4’-DMA today")


@pytest.mark.parametrize(
    "text",
    [
        "I tried 4'-DMA-7,8-DHF yesterday.",
        "I tried 4’-DMA-7,8-DHF yesterday.",  # curly apostrophe
        "4DMA-7,8DHF sublingual 10mg",
        "Eutropoflavin making me tired",
    ],
)
def test_derivative_spellings_are_not_the_parent(text: str) -> None:
    assert not has_unexcluded_alias(text, PARENT_ALIASES, DERIVATIVE_ALIASES)


@pytest.mark.parametrize(
    "text",
    [
        "4'-DMA-7,8-DHF and 7,8-DHF were my gift",
        "regular dhf vs 4dma-7,8dhf",
        "DMAE and 7,8-DHF",
    ],
)
def test_separately_named_parent_matches(text: str) -> None:
    assert has_unexcluded_alias(text, PARENT_ALIASES, DERIVATIVE_ALIASES)


def test_no_false_matches() -> None:
    assert not has_unexcluded_alias("MDMA and DMAE are different things", PARENT_ALIASES, DERIVATIVE_ALIASES)
    assert not has_unexcluded_alias("dhfr inhibitors", PARENT_ALIASES, DERIVATIVE_ALIASES)  # word boundary


def test_spans_index_the_original_text() -> None:
    text = "4’-DMA-7,8-DHF is strong; plain 7,8-DHF is subtle."
    assert [text[s:e] for s, e in alias_spans(text, PARENT_ALIASES, DERIVATIVE_ALIASES)] == ["7,8-DHF"]


# ── Extract step ─────────────────────────────────────────────────────────────

SCHEMA_SQL = Path(__file__).parent.parent / "schema.sql"


def test_extract_tags_with_exclusions(tmp_path: Path) -> None:
    """--drug mode: a post naming only the derivative is not a mention; one naming both is."""
    db = tmp_path / "posts.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO users (user_id, source_subreddit, scraped_at) VALUES ('u1', 'test', 0)")
        conn.executemany(
            "INSERT INTO posts (post_id, title, parent_id, user_id, body_text, post_date, scraped_at) VALUES (?, ?, ?, 'u1', ?, 1, 0)",
            [
                ("both", "Comparing them", None, "4'-DMA-7,8-DHF is strong but plain 7,8-DHF is what I take daily."),
                ("derivative_only", None, "both", "I only ever took 4'-DMA-7,8-DHF and it wired me."),
                ("neither", None, "both", "I take magnesium and that is all."),
            ],
        )
    out = tmp_path / "out"
    out.mkdir()
    config = PipelineConfig(
        client=None,
        output_dir=out,
        db_path=db,
        limit=None,
        drug="7,8-dhf",
        drug_aliases=PARENT_ALIASES,
        drug_excluded_aliases=DERIVATIVE_ALIASES,
    )
    run_extraction(config)
    tagged = {e["id"]: e for e in json.loads((out / "tagged_mentions.json").read_text(encoding="utf-8"))}

    assert tagged["both"]["drugs_direct"] == ["7,8-dhf"]
    assert tagged["derivative_only"]["drugs_direct"] == []
    # The replies still reach the output through upstream context, not their own text.
    assert tagged["derivative_only"]["drugs_context"] == ["7,8-dhf"]
    assert tagged["neither"]["drugs_direct"] == [] and tagged["neither"]["drugs_context"] == ["7,8-dhf"]


def test_dash_look_alikes_are_normalised() -> None:
    parent, excluded = ["7,8-dhf", "dhf"], ["4'-dma-7,8-dhf"]
    assert has_unexcluded_alias("took 7,8\u2013dhf today", parent, excluded)          # en dash in the parent
    assert not has_unexcluded_alias("took 4\u2019\u2013dma\u20147,8\u2011dhf", parent, excluded)  # curly quote + three dash kinds
    spans = alias_spans("x 7,8\u2012dhf y", parent)
    assert spans == ((2, 9),) and "x 7,8\u2012dhf y"[2:9] == "7,8\u2012dhf"       # spans index the original text
