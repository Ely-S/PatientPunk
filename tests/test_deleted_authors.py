"""Posts and comments whose author is gone are kept under DELETED_USER_ID, which is never a patient (#202).
Made-up data, no API calls.
"""
import importlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "Scrapers"))

import db_to_corpus  # noqa: E402
import dose_bands  # noqa: E402
import extract_demographics_conditions  # noqa: E402
import summarize_drug  # noqa: E402
from import_posts import DELETED_USER_ID, import_reddit_posts  # noqa: E402

REAL = "a" * 64
CORPUS = [
    {"author_hash": None, "post_id": "p1", "title": "gone", "body": "post by a deleted account",
     "url": "https://reddit.com/r/cfs/p1", "created_utc": "2026-01-01T00:00:00Z",
     "comments": [
         {"author_hash": REAL, "comment_id": "c1", "parent_id": "t3_p1", "body": "I am 34", "created_utc": "2026-01-01T01:00:00Z"},
         {"author_hash": None, "comment_id": "c2", "parent_id": "t1_c1", "body": "I am 50", "created_utc": "2026-01-01T02:00:00Z"},
     ]},
    {"author_hash": REAL, "post_id": "p2", "title": "mine", "body": "LDN helped", "url": "https://reddit.com/r/cfs/p2",
     "created_utc": "2026-01-02T00:00:00Z", "comments": []},
]


def _db(tmp_path: Path, corpus=CORPUS) -> tuple[sqlite3.Connection, int]:
    src = tmp_path / "subreddit_posts.json"
    src.write_text(json.dumps(corpus), encoding="utf-8")
    conn = sqlite3.connect(tmp_path / "posts.db")
    conn.executescript((REPO_ROOT / "schema.sql").read_text(encoding="utf-8"))
    return conn, import_reddit_posts(conn, src, subreddit="cfs")


def test_authorless_rows_are_kept_under_deleted(tmp_path):
    conn, skipped = _db(tmp_path)
    rows = dict(conn.execute("SELECT post_id, user_id FROM posts").fetchall())
    assert rows == {"p1": DELETED_USER_ID, "c1": REAL, "c2": DELETED_USER_ID, "p2": REAL}
    assert conn.execute("SELECT 1 FROM users WHERE user_id = ?", (DELETED_USER_ID,)).fetchone()
    assert skipped == 0


def test_comments_under_a_deleted_post_keep_their_parent(tmp_path):
    conn, _ = _db(tmp_path)
    parents = dict(conn.execute("SELECT post_id, parent_id FROM posts WHERE parent_id IS NOT NULL").fetchall())
    assert parents == {"c1": "p1", "c2": "c1"}


def test_skipped_rows_are_counted(tmp_path):
    corpus = CORPUS + [{**CORPUS[1], "title": "same id again"}]
    conn, skipped = _db(tmp_path, corpus)
    assert skipped == 1
    assert conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 4


def test_null_comment_body_is_stored_not_dropped(tmp_path):
    corpus = [{**CORPUS[1], "comments": [{"author_hash": None, "comment_id": "c9", "parent_id": "t3_p2",
                                          "body": None, "created_utc": "2026-01-02T01:00:00Z"}]}]
    conn, skipped = _db(tmp_path, corpus)
    assert conn.execute("SELECT body_text FROM posts WHERE post_id = 'c9'").fetchone() == ("",)
    assert skipped == 0


@pytest.mark.parametrize("limit", [0, 5])
def test_demographics_never_sends_or_profiles_deleted(tmp_path, monkeypatch, limit):
    conn, _ = _db(tmp_path)
    conn.close()
    prompts = []
    monkeypatch.setattr(extract_demographics_conditions, "get_client", lambda: None)
    monkeypatch.setattr(extract_demographics_conditions, "llm_call",
                        lambda client, prompt, **_: prompts.append(prompt) or '{"conditions": []}')
    extract_demographics_conditions.run_demographics(tmp_path / "posts.db", limit=limit)

    assert len(prompts) == 1
    assert "I am 34" in prompts[0] and "I am 50" not in prompts[0] and "deleted account" not in prompts[0]
    conn = sqlite3.connect(tmp_path / "posts.db")
    assert [r[0] for r in conn.execute("SELECT DISTINCT user_id FROM user_profiles")] == [REAL]
    assert not conn.execute("SELECT 1 FROM conditions WHERE user_id = ?", (DELETED_USER_ID,)).fetchone()


@pytest.fixture
def reports_db(tmp_path) -> Path:
    """One LDN report with a 4.5 mg dose on each of p1, c2 (deleted) and p2 (REAL)."""
    conn, _ = _db(tmp_path)
    conn.execute("INSERT INTO extraction_runs (run_id, run_at, commit_hash, extraction_type, config) VALUES (1, 0, 'x', 'sentiment', '{}')")
    conn.execute("INSERT INTO extraction_runs (run_id, run_at, commit_hash, extraction_type, config) VALUES (2, 0, 'x', 'report_doses', '{}')")
    conn.execute("INSERT INTO treatment (id, canonical_name) VALUES (1, 'ldn')")
    for i, (post, user) in enumerate([("p1", DELETED_USER_ID), ("c2", DELETED_USER_ID), ("p2", REAL)], 1):
        conn.execute("INSERT INTO treatment_reports (report_id, run_id, post_id, user_id, drug_id, sentiment, signal_strength) "
                     "VALUES (?, 1, ?, ?, 1, 'positive', 'strong')", (i, post, user))
        conn.execute("INSERT INTO report_runs (run_id, report_id) VALUES (2, ?)", (i,))
        conn.execute("INSERT INTO report_doses (report_id, run_id, ordinal, low, unit) VALUES (?, 2, 0, 4.5, 'mg')", (i,))
    conn.commit()
    conn.close()
    return tmp_path / "posts.db"


def test_author_summaries_do_not_count_deleted_as_a_patient(reports_db):
    assert set(summarize_drug.load(reports_db, "ldn", "db")) == {REAL}


def test_dose_bands_do_not_count_deleted_as_an_author(reports_db):
    data = dose_bands.load(reports_db, "ldn", cuts=[3.0], capsule_mg=None, cap_mg=100.0)
    assert {author for author, _, _ in data["reports"].values()} == {REAL}
    assert [d["author"] for d in data["doses"]] == [REAL]


@pytest.mark.parametrize("module", ["scrape_corpus", "transform_arctic_shift"])
@pytest.mark.parametrize("author", [None, "", "[deleted]", "[removed]"])
def test_scrapers_give_no_author_hash_for_missing_authors(module, author):
    scraper = importlib.import_module(module)
    raw = {"id": "x", "author": author, "created_utc": 1767225600}
    assert scraper.build_post(raw, [])["author_hash"] is None
    assert scraper.build_comment(raw)["author_hash"] is None
    assert scraper.build_post({**raw, "author": "someone"}, [])["author_hash"] == db_to_corpus.hash_username("someone")
