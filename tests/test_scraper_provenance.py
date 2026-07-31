"""Scraper output has to carry the subreddit aggregate counts. No API calls.

PR #109 added the `subreddits` provenance column, but neither scraper emitted a
per-post `subreddit`, so the column came out empty on every corpus they built --
which is exactly the information a multi-community run exists to keep.
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "variable_extraction"))

from patientpunk.aggregate import aggregate_corpus_by_author  # noqa: E402


def _load(name):
    """Import a Scrapers/*.py script -- the directory is not a package."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "Scrapers" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_both_scrapers_emit_the_subreddit():
    raw = {"id": "abc", "title": "t", "selftext": "b", "author": "someone",
           "created_utc": 1700000000, "subreddit": "PMDD", "permalink": "/r/PMDD/x"}
    assert _load("transform_arctic_shift").build_post(raw, [])["subreddit"] == "PMDD"
    assert _load("scrape_corpus").build_post(raw, [])["subreddit"] == "PMDD"


def test_a_scraped_post_reaches_the_provenance_column():
    """The whole point of the field: aggregate has to be able to count it."""
    build_post = _load("transform_arctic_shift").build_post
    posts = [
        build_post({"id": "1", "selftext": "x", "author": "amy", "subreddit": "cfs"}, []),
        build_post({"id": "2", "selftext": "x", "author": "amy", "subreddit": "cfs"}, []),
        build_post({"id": "3", "selftext": "x", "author": "amy", "subreddit": "PMDD"}, []),
    ]
    out, _ = aggregate_corpus_by_author(posts, min_items=1)
    assert out[0]["subreddits"] == "cfs:2 PMDD:1"


def test_a_dump_without_the_field_is_not_guessed():
    build_post = _load("transform_arctic_shift").build_post
    posts = [build_post({"id": "1", "selftext": "x", "author": "amy"}, [])]
    out, _ = aggregate_corpus_by_author(posts, min_items=1)
    assert out[0]["subreddits"] == ""
