"""The demographics test set (#207): sampling from a scrape-format database, matching, and scoring,
with synthetic posts and stubbed replies, no API calls."""

import json
import sqlite3
from contextlib import closing

import pytest
from patientpunk._utils import LLMContentFilteredError

import demographics_testset as ts
import extract_demographics_conditions as extractor


def label(**fields):
    others = fields.pop("others", {})
    return {**{f: None for f in ts.FIELDS}, **{f: {"value": v, "evidence": e} for f, (v, e) in fields.items()},
            "others": others}


def item(post_id, text, lab, user="u1", date=0, split="dev"):
    return {"post_id": post_id, "user_id": user, "split": split, "strata": ["random"], "post_date": date,
            "subreddit": "cfs", "text": text, "label": lab}


@pytest.mark.parametrize("field, a, b", [
    ("age", "34", "34 years old"), ("age", "30s", "mid 30s"), ("country", "USA", "the United States"),
    ("country", "U.K.", "England"), ("state", "TX", "Texas"), ("city", "Austin, TX", "austin"),
    ("sex", "Female | non-binary", "non-binary|female"), ("sex", "mom", "F"), ("sex", "guy", "male"),
    ("sex", "ladies", "woman"), ("sex", "f | mom", "female"), ("country", "the States", "US"),
    ("country", "Aus", "Australia"),
])
def test_two_ways_of_writing_one_answer_match(field, a, b):
    assert ts.key(field, a) == ts.key(field, b)


@pytest.mark.parametrize("field, a, b", [("age", "34", "35"), ("state", "TX", "Ohio"), ("sex", "female", "trans woman"),
                                           ("sex", "mom", "dad"), ("sex", "non-binary | mom", "female")])
def test_different_answers_do_not_match(field, a, b):
    assert ts.key(field, a) != ts.key(field, b)


def test_score_counts_hits_misses_wrong_person_blocks_and_failures():
    items = [
        item("a", "I (33F) live in Texas", label(age=("33", "I (33F)"), sex=("F", "33F"), state=("Texas", "live in Texas"))),
        item("b", "My son is 11 and I'm 40", label(age=("40", "I'm 40"), others={"age": ["11"]})),
        item("c", "Nothing here", label()),
        item("d", "I'm 50", label(age=("50", "I'm 50"))),  # blocked: counts as no claims
        item("e", "I'm 60", label(age=("60", "I'm 60"))),  # failed: left out
    ]
    predictions = {
        "a": {"age": ("33", "I (33F)"), "sex": ("female", "33F"), "state": ("TX", "Texas")},
        "b": {"age": ("11", "My son is 11")},
        "c": {"country": ("US", "made up")},
        "d": "blocked",
        "e": None,
    }
    report = ts.score(items, predictions)
    assert report["posts"] == {"failed": 1, "blocked": 1, "scored": 4, "gold_with_claim": 3, "pred_with_claim": 3}
    age = report["fields"]["age"]
    assert (age["tp"], age["fp"], age["fn"], age["wrong_person"]) == (1, 1, 2, 1)
    assert (age["precision"], age["recall"]) == (0.5, 0.333)
    assert report["fields"]["sex"]["tp"] == 1 and report["fields"]["sex_normalized"]["tp"] == 1
    assert report["fields"]["state"]["tp"] == 1
    assert report["fields"]["state"]["evidence_matches_label"] == 1  # "Texas" is inside "live in Texas"
    country = report["fields"]["country"]
    assert (country["fp"], country["evidence_in_post"], country["recall"]) == (1, 0, None)


def test_profiles_from_labels_predictions_and_expected():
    items = [item("p1", "I'm 30, in the US", label(age=("30", "I'm 30"), country=("US", "in the US")), date=1),
             item("p2", "Now 31 and in Texas", label(age=("31", "Now 31"), state=("Texas", "in Texas")), date=2)]
    authors = [{"user_id": "u1", "split": "dev", "post_ids": ["p1", "p2"],
                "expected_profile": {"age": 31, "age_bucket": "30s", "sex": None, "sex_stated": None,
                                     "location": "United States / TX", "city": None}}]
    predictions = {"p1": {"age": ("30", "I'm 30"), "country": ("USA", "US")}, "p2": {}}
    result = ts.score_profiles(items, authors, predictions)
    assert result["labels_vs_expected"] == {f"{f}/agree": 1 for f in ts.PROFILE}
    assert result["pred_vs_labels"]["age/differ"] == 1 and result["pred_vs_labels"]["location/differ"] == 1
    assert result["pred_vs_expected"]["sex/agree"] == 1


def test_profiles_keep_a_state_across_spellings_of_its_country():
    # US, then Texas, then USA: the resolve step keeps the state (#225 review), so the profile from the
    # predictions agrees with the one the labeler expected.
    items = [item("p1", "in the US", label(country=("US", "in the US")), date=1),
             item("p2", "in Texas", label(state=("Texas", "in Texas")), date=2),
             item("p3", "USA here", label(country=("USA", "USA")), date=3)]
    authors = [{"user_id": "u1", "split": "dev", "post_ids": ["p1", "p2", "p3"],
                "expected_profile": {"age": None, "age_bucket": None, "sex": None, "sex_stated": None,
                                     "location": "United States / Texas", "city": None}}]
    predictions = {"p1": {"country": ("US", "US")}, "p2": {"state": ("TX", "Texas")}, "p3": {"country": ("USA", "USA")}}
    result = ts.score_profiles(items, authors, predictions)
    assert result["pred_vs_expected"] == result["labels_vs_expected"] == {f"{f}/agree": 1 for f in ts.PROFILE}


def scrape_db(path):
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript("""
            CREATE TABLE posts(id TEXT PRIMARY KEY, subreddit TEXT, created_utc INTEGER, score INTEGER,
              num_comments INTEGER, title TEXT, selftext TEXT, author TEXT, permalink TEXT);
            CREATE TABLE comments(id TEXT PRIMARY KEY, subreddit TEXT, created_utc INTEGER, score INTEGER,
              body TEXT, author TEXT, link_id TEXT, parent_id TEXT);""")
        conn.executemany("INSERT INTO posts (id, subreddit, created_utc, title, selftext, author) VALUES (?,?,?,?,?,?)",
                         [(f"p{i}", "cfs", i, f"Title {i}", "I'm 34 and female" if i % 2 else "[removed]", f"user{i % 5}")
                          for i in range(40)] + [("pdel", "cfs", 1, "t", "I'm 30", "[deleted]")])
        conn.executemany("INSERT INTO comments (id, subreddit, created_utc, body, author) VALUES (?,?,?,?,?)",
                         [(f"c{i}", "cfs", 100 + i, "my son is 11" if i % 3 == 0 else "same here", f"user{i % 5}")
                          for i in range(60)])
        conn.commit()


def test_sample_reads_items_as_the_extractor_does(tmp_path):
    db = tmp_path / "scrape.db"
    scrape_db(db)
    out = tmp_path / "set"
    manifest = ts.sample(db, out, seed=1, pool=101, n_random=10, n_keyword=5, n_other=5, n_authors=2,
                         max_author_posts=4)
    items = [json.loads(line) for line in (out / "testset.jsonl").read_text().splitlines()]
    authors = [json.loads(line) for line in (out / "authors.jsonl").read_text().splitlines()]
    assert manifest["eligible_in_pool"] == 100  # a [removed] body keeps its title; the deleted author is dropped
    assert all(it["label"] is None and it["user_id"] != "deleted" for it in items)
    post = next(it for it in items if it["post_id"] == "t3_p1")
    assert post["text"] == "Title 1\nI'm 34 and female" and len(post["user_id"]) == 64
    assert all(it["post_id"].startswith(("t3_", "t1_")) and it["split"] == ts.split_of(it["user_id"]) for it in items)
    assert {s for it in items for s in it["strata"]} == {"random", "keyword", "other_person", "author"}
    assert len(authors) == 2 and all(len(a["post_ids"]) <= 4 for a in authors)
    with pytest.raises(FileExistsError):
        ts.sample(db, out, seed=1, pool=10, n_random=1, n_keyword=1, n_other=1, n_authors=1, max_author_posts=1)


def test_evaluate_runs_read_post_and_writes_the_report(tmp_path, monkeypatch):
    items = [item("a", "I'm 34", label(age=("34", "I'm 34"))), item("b", "blocked one", label()),
             item("c", "unlabeled", None)]
    (tmp_path / "testset.jsonl").write_text("".join(json.dumps(it) + "\n" for it in items))
    monkeypatch.setattr(extractor, "get_client", lambda: None)

    def llm_call(client, prompt, **kwargs):
        if "blocked one" in prompt:
            raise LLMContentFilteredError("blocked")
        return json.dumps({"age": {"value": 34, "evidence": "I'm 34"}})

    monkeypatch.setattr(extractor, "llm_call", llm_call)
    assert ts.evaluate(tmp_path, "dev", "t", dry_run=True)["calls"] == 2
    report = ts.evaluate(tmp_path, "dev", "t")
    assert report["posts"]["blocked"] == 1 and report["fields"]["age"]["recall"] == 1.0
    assert json.loads((tmp_path / "report_t.json").read_text())["tag"] == "t"
    assert len((tmp_path / "predictions_t.jsonl").read_text().splitlines()) == 2


def test_stats_flags_evidence_that_is_not_quoted_from_the_text():
    good = item("a", "I'm 34", label(age=("34", "I'm 34")))
    bad = item("b", "I'm 35", label(age=("35", "I am 35")))
    result = ts.counts([good, bad])
    assert result["labeled"] == {"dev": 2} and result["fields"] == {"age/dev": 2}
    assert result["evidence_not_in_text"] == {"b": 1}
