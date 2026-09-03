from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from studies.tropoflavin_nootropics.build_sqlite_comparator_corpora import (
    SqliteCorpusConfig,
    build_sqlite_comparator_corpora,
)


def test_builds_separate_hashed_corpora_with_parent_context(tmp_path: Path) -> None:
    source = tmp_path / "reddit.db"
    with closing(sqlite3.connect(source)) as connection:
        connection.executescript(
            """
            CREATE TABLE posts (
                id TEXT PRIMARY KEY, subreddit TEXT, created_utc INTEGER,
                score INTEGER, num_comments INTEGER, title TEXT, selftext TEXT,
                author TEXT, permalink TEXT
            );
            CREATE TABLE comments (
                id TEXT PRIMARY KEY, subreddit TEXT, created_utc INTEGER,
                score INTEGER, body TEXT, author TEXT, link_id TEXT,
                parent_id TEXT
            );
            INSERT INTO posts VALUES
                ('p1', 'cfs', 1, 2, 2, 'Question', '', 'raw_post_author',
                 '/r/cfs/comments/p1/question/'),
                ('p2', 'LongCovid', 1, 1, 0, 'Unrelated', '', 'other',
                 '/r/LongCovid/comments/p2/unrelated/');
            INSERT INTO comments VALUES
                ('c1', 'cfs', 2, 1, 'Parent context', 'raw_parent', 't3_p1', 't3_p1'),
                ('c2', 'cfs', 3, 1, 'I used 7,8-DHF', 'raw_user', 't3_p1', 't1_c1');
            """
        )

    output = tmp_path / "output"
    manifest = build_sqlite_comparator_corpora(
        SqliteCorpusConfig(
            source_database=source,
            output_directory=output,
            communities=("cfs", "LongCovid"),
        )
    )

    assert [summary.posts for summary in manifest.communities] == [1, 0]
    cfs = json.loads((output / "cfs" / "comparator_corpus.json").read_text())
    assert [comment["comment_id"] for comment in cfs[0]["comments"]] == ["c1", "c2"]
    encoded = json.dumps(cfs)
    assert "raw_user" not in encoded
    assert "raw_parent" not in encoded
    assert manifest.communities[0].matches[0].matching_items == 1
