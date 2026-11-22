#!/usr/bin/env python3
"""The labeled test set for per-post demographics extraction (#207), and its evaluation (#208).

``sample`` draws posts and comments from a scraped Reddit database (the posts/comments tables that
Scrapers/db_to_corpus.py reads) into a directory outside Git, as the extractor sees them: one item at
a time, title included, with the corpus's post_id and hashed user_id. ``evaluate`` sends the labeled
items through the extractor's read_post and scores its claims against the labels. Labeling rules:
docs/demographics_labeling.md.

    uv run python src/demographics_testset.py sample --db reddit_2026-06-13.db --out data/demographics_testset
    uv run python src/demographics_testset.py stats --testset data/demographics_testset
    uv run python src/demographics_testset.py evaluate --testset data/demographics_testset --split dev
"""
import argparse
import hashlib
import json
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[1] / "Scrapers"))

from db_to_corpus import author_hash

import extract_demographics_conditions as extractor
from resolve_demographics import SEX_VALUES, _resolve, normalize_sex, stated_age

FIELDS = extractor.CLAIM_FIELDS
PROFILE = ("age_bucket", "age", "sex", "sex_stated", "location", "city")  # _resolve's order
TEST_SHARE = 0.4  # of authors, by a hash of user_id, so the split never depends on what was sampled

# Sampling only: a post matching these is likelier to state a demographic. Recall is measured on the
# random stratum, which these don't touch.
DEMOGRAPHIC = re.compile(
    r"\b(?:i'?m|i am|aged?)\s+(?:a\s+|now\s+|only\s+)?\d{2}\b|\b\d{2}\s*(?:yo|y/o|years?[\s-]old|yrs?)\b"
    r"|[(\[]\s*\d{2}\s*[mf]\s*[)\]]|\b\d{2}\s?[mf]\b|\bin my (?:early |mid |late )?\d0'?s\b"
    r"|\bi'?m an?\s+(?:\w+\s+)?(?:woman|man|female|male|guy|girl|mom|mum|dad)\b|\bas an? (?:woman|man|female|male)\b"
    r"|\b(?:non-?binary|transgender|trans (?:man|woman|guy|girl)|enby|intersex)\b"
    r"|\b(?:i live in|i'?m based in|i'?m from|living in|here in)\b",
    re.IGNORECASE)
# Another person's age, the trap #85 found ("my 11yo son", "my wife is 36").
OTHER_PERSON = re.compile(
    r"\bmy\s+(?:\d{1,2}\s*(?:yo|y/o|years?[\s-]old|-year-old)\s+)?"
    r"(?:son|daughter|kid|child|wife|husband|mom|mum|mother|dad|father|partner|boyfriend|girlfriend|sister|brother)"
    r"\b[^.?!\n]{0,40}?\b\d{1,2}\b|\bwhen i was (?:\d{1,2}|a kid|a teen)",
    re.IGNORECASE)


def split_of(user_id: str) -> str:
    return "test" if int(hashlib.sha256(f"207-split:{user_id}".encode()).hexdigest()[:8], 16) < TEST_SHARE * 2**32 else "dev"


# ── Sampling ─────────────────────────────────────────────────────────────────

def _item(row: sqlite3.Row, kind: str) -> dict | None:
    """The item as the extractor sees it, or None when it would not be sent to the model."""
    user_id = author_hash(row["author"])
    title, body = (row["title"], row["selftext"]) if kind == "post" else (None, row["body"])
    text = extractor._post_text(title, body or "")
    if user_id is None or not text:
        return None
    return {"post_id": f"{'t3' if kind == 'post' else 't1'}_{row['id']}", "user_id": user_id,
            "split": split_of(user_id), "subreddit": row["subreddit"], "post_date": row["created_utc"],
            "text": text}


def _fetch(conn, kind: str, rowids: list[int]) -> list[dict]:
    table, cols = ("posts", "id, subreddit, created_utc, title, selftext, author") if kind == "post" else \
                  ("comments", "id, subreddit, created_utc, body, author")
    items = []
    for i in range(0, len(rowids), 500):
        chunk = rowids[i:i + 500]
        rows = {r["rowid"]: r for r in conn.execute(
            f"SELECT rowid, {cols} FROM {table} WHERE rowid IN ({','.join('?' * len(chunk))})", chunk)}
        items += [it for rid in chunk if rid in rows and (it := _item(rows[rid], kind))]
    return items


def sample(db: Path, out: Path, *, seed: int, pool: int, n_random: int, n_keyword: int, n_other: int,
           n_authors: int, max_author_posts: int) -> dict:
    """Write testset.jsonl (one item per line, label null), authors.jsonl and manifest.json to ``out``."""
    if (out / "testset.jsonl").exists():
        raise FileExistsError(f"{out}/testset.jsonl exists; labels would be lost. Choose another --out.")
    rng = random.Random(seed)
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        sizes = {k: conn.execute(f"SELECT MAX(rowid) FROM {t}").fetchone()[0] for k, t in
                 (("post", "posts"), ("comment", "comments"))}
        # One uniform draw over all rows of both tables, in draw order, so every stratum is a seeded
        # random sample of the eligible items in it.
        draws = rng.sample(range(sizes["post"] + sizes["comment"]), pool)
        by_kind = {"post": [d + 1 for d in draws if d < sizes["post"]],
                   "comment": [d - sizes["post"] + 1 for d in draws if d >= sizes["post"]]}
        fetched = {it["post_id"]: it for k, ids in by_kind.items() for it in _fetch(conn, k, ids)}
        drawn = list(fetched.values())
        rng.shuffle(drawn)

        chosen: dict[str, dict] = {}

        def take(items, n, stratum):
            for it in items[:n]:
                chosen.setdefault(it["post_id"], {**it, "strata": []})["strata"].append(stratum)

        take(drawn, n_random, "random")
        take([it for it in drawn if DEMOGRAPHIC.search(it["text"])], n_keyword, "keyword")
        take([it for it in drawn if OTHER_PERSON.search(it["text"])], n_other, "other_person")

        # Authors for the resolve check: keyword-hit authors not already in the set, with all their items
        # read in one pass over both tables (author has no index).
        candidates = list(dict.fromkeys(it["user_id"] for it in drawn if DEMOGRAPHIC.search(it["text"])))
        rng.shuffle(candidates)
        candidates = set(candidates[:n_authors * 10])
        history = defaultdict(list)
        for kind, table, cols in (("post", "posts", "id, subreddit, created_utc, title, selftext, author"),
                                  ("comment", "comments", "id, subreddit, created_utc, body, author")):
            for row in conn.execute(f"SELECT {cols} FROM {table} WHERE author IS NOT NULL"):
                if author_hash(row["author"]) in candidates and (it := _item(row, kind)):
                    history[it["user_id"]].append(it)
    authors = []
    for user_id in sorted(history, key=lambda u: rng.random()):
        hits = [it for it in history[user_id] if DEMOGRAPHIC.search(it["text"])]
        if len(hits) < 2 or len(history[user_id]) > 200:
            continue  # one stated value checks nothing; a very heavy poster can't be labeled in full
        rest = [it for it in history[user_id] if it not in hits]
        posts = (hits + rng.sample(rest, min(2, len(rest))))[:max_author_posts]
        take(posts, len(posts), "author")
        authors.append({"user_id": user_id, "split": split_of(user_id),
                        "post_ids": [it["post_id"] for it in sorted(posts, key=lambda it: it["post_date"] or 0)],
                        "expected_profile": None})
        if len(authors) == n_authors:
            break

    out.mkdir(parents=True, exist_ok=True)
    items = sorted(chosen.values(), key=lambda it: hashlib.sha256(it["post_id"].encode()).hexdigest())
    with open(out / "testset.jsonl", "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps({**it, "label": None}, ensure_ascii=False) + "\n")
    with open(out / "authors.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(a) + "\n" for a in authors)
    manifest = {
        "issue": 207, "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_db": str(db), "source_db_bytes": db.stat().st_size, "code_commit": extractor.get_git_commit(),
        "seed": seed, "pool": pool, "eligible_in_pool": len(drawn),
        "requested": {"random": n_random, "keyword": n_keyword, "other_person": n_other, "authors": n_authors,
                      "max_author_posts": max_author_posts},
        "test_share": TEST_SHARE,
        "selection": "Uniform draw of `pool` rows over posts+comments; deleted authors and empty or "
                     "[removed] bodies dropped; random = the first n eligible in shuffled order; keyword and "
                     "other_person = the first n matching DEMOGRAPHIC / OTHER_PERSON; authors = keyword-hit "
                     "authors with 2+ matching items and at most 200 items, their matching items plus up to 2 "
                     "others. Split by sha256('207-split:' + user_id).",
        "counts": counts(items),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def counts(items: list[dict]) -> dict:
    """Items per stratum and split, labeled values per field and split, and labeled values whose
    evidence is not an exact quote from the item's text (which should be none)."""
    c = {"items": Counter(), "labeled": Counter(), "fields": Counter(), "others": Counter(),
         "evidence_not_in_text": Counter()}
    for it in items:
        for s in it["strata"]:
            c["items"][f"{s}/{it['split']}"] += 1
        if (label := it.get("label")) is not None:
            c["labeled"][it["split"]] += 1
            c["fields"].update(f"{f}/{it['split']}" for f in FIELDS if label.get(f))
            c["others"].update(f"{f}/{it['split']}" for f, v in (label.get("others") or {}).items() if v)
            c["evidence_not_in_text"].update(
                it["post_id"] for f in FIELDS if label.get(f) and label[f]["evidence"] not in it["text"])
    return {k: dict(sorted(v.items())) for k, v in c.items()}


# ── Matching ─────────────────────────────────────────────────────────────────

_US_STATES = dict(pair.split(":") for pair in ["al:alabama", "ak:alaska", "az:arizona", "ar:arkansas", "ca:california", "co:colorado", "ct:connecticut", "de:delaware", "fl:florida", "ga:georgia", "hi:hawaii", "id:idaho", "il:illinois", "in:indiana", "ia:iowa", "ks:kansas", "ky:kentucky", "la:louisiana", "me:maine", "md:maryland", "ma:massachusetts", "mi:michigan", "mn:minnesota", "ms:mississippi", "mo:missouri", "mt:montana", "ne:nebraska", "nv:nevada", "nh:new_hampshire", "nj:new_jersey", "nm:new_mexico", "ny:new_york", "nc:north_carolina", "nd:north_dakota", "oh:ohio", "ok:oklahoma", "or:oregon", "pa:pennsylvania", "ri:rhode_island", "sc:south_carolina", "sd:south_dakota", "tn:tennessee", "tx:texas", "ut:utah", "vt:vermont", "va:virginia", "wa:washington", "wv:west_virginia", "wi:wisconsin", "wy:wyoming", "dc:district_of_columbia"])
_US_STATES = {k: v.replace("_", " ") for k, v in _US_STATES.items()}
_COUNTRIES = {"us": "united states", "usa": "united states", "united states of america": "united states",
              "america": "united states", "uk": "united kingdom", "britain": "united kingdom",
              "great britain": "united kingdom", "england": "united kingdom", "scotland": "united kingdom",
              "wales": "united kingdom", "northern ireland": "united kingdom", "nz": "new zealand",
              "holland": "netherlands", "the netherlands": "netherlands", "deutschland": "germany"}


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[.'’]", "", text.casefold())).strip().removeprefix("the ")


# Everyday words for a binary sex, scored as the word they mean ("31F, mom" and "female" agree).
# Evaluation only: the pipeline's normalize_sex keeps its own narrower list.
_FEMALE = ("mom", "mum", "mother", "mama", "wife", "girl", "gal", "lady", "ladies", "women", "girlfriend",
           "grandmother", "sister", "daughter")
_MALE = ("dad", "father", "papa", "husband", "guy", "dude", "boy", "gentleman", "men", "boyfriend", "grandfather",
         "brother", "son")
SEX_WORDS = {**SEX_VALUES, **dict.fromkeys(_FEMALE, "female"), **dict.fromkeys(_MALE, "male")}


def key(field: str, value: str) -> object:
    """A form of the value in which two ways of writing the same answer are equal."""
    if field == "age":
        stated = stated_age(value)
        return stated[0] if stated else _plain(value)
    if field == "sex":
        parts = (_plain(v) for v in re.split(r"[|/,;]", value) if v.strip())
        return frozenset(SEX_WORDS.get(v, v) for v in parts)
    text = _plain(value)
    if field == "country":
        return _COUNTRIES.get(text, text)
    if field == "state":
        return _US_STATES.get(text, text)
    return text.split(",")[0].strip()  # city: "Austin, TX" is Austin


def _overlaps(a: str, b: str) -> bool:
    a, b = a.casefold().strip(), b.casefold().strip()
    return bool(a and b) and (a in b or b in a)


# ── Evaluation ───────────────────────────────────────────────────────────────

def score(items: list[dict], predictions: dict[str, dict | None]) -> dict:
    """Per-field precision, recall, wrong-person errors and evidence checks.

    ``predictions`` maps post_id to {field: (value, evidence)}, "blocked", or None (the read failed).
    A failed read is left out of the scores; a blocked one counts as no claims, so it shows in recall.
    A wrong value is both a false positive and a false negative. A false positive whose value matches
    one the label lists under ``others`` (someone else's, or a past age) is a wrong-person error.
    """
    fields = (*FIELDS, "sex_normalized")
    m = {f: Counter() for f in fields}
    posts = Counter()
    for it in items:
        post_id, label = it["post_id"], it["label"]
        pred = predictions.get(post_id)
        if pred is None:
            posts["failed"] += 1
            continue
        posts["blocked"] += pred == "blocked"
        claims = {} if pred == "blocked" else pred
        posts["scored"] += 1
        posts["gold_with_claim"] += any(label.get(f) for f in FIELDS)
        posts["pred_with_claim"] += bool(claims)
        for f in fields:
            if f == "sex_normalized":
                g = normalize_sex(label["sex"]["value"]) if label.get("sex") else None
                p = normalize_sex(claims["sex"][0]) if "sex" in claims else None
                gk, pk = g, p
            else:
                g = label.get(f) and label[f]["value"]
                p = claims.get(f, (None,))[0]
                gk, pk = (key(f, g) if g else None), (key(f, p) if p else None)
            if gk is not None and gk == pk:
                m[f]["tp"] += 1
                if f in claims and label.get(f):
                    m[f]["evidence_matches_label"] += _overlaps(claims[f][1], label[f]["evidence"])
            else:
                m[f]["fn"] += gk is not None
                m[f]["fp"] += pk is not None
                others = {key(f, o) for o in ((label.get("others") or {}).get(f) or [])} if f in FIELDS else set()
                m[f]["wrong_person"] += pk is not None and pk in others
            if f in claims:
                m[f]["evidence_in_post"] += claims[f][1] in it["text"]
                m[f]["claims"] += 1
    report = {"posts": dict(posts), "fields": {}}
    for f, c in m.items():
        tp, fp, fn = c["tp"], c["fp"], c["fn"]
        for k in ("tp", "fp", "fn", "wrong_person", "claims"):
            c.setdefault(k, 0)  # zeros shown
        report["fields"][f] = {**c, "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                               "recall": round(tp / (tp + fn), 3) if tp + fn else None}
    return report


def score_profiles(items: list[dict], authors: list[dict], predictions: dict) -> dict:
    """For each author, the profile resolved from the labels and from the predictions, per field:
    whether they agree, and, when the labeler wrote an expected_profile, whether each agrees with it.
    Ages are not advanced (reference date None), so expected ages are as stated."""
    by_id = {it["post_id"]: it for it in items}
    agree = {k: Counter() for k in ("pred_vs_labels", "labels_vs_expected", "pred_vs_expected")}
    for a in authors:
        posts = [by_id[p] for p in a["post_ids"] if p in by_id and by_id[p]["label"] is not None]
        if not posts or any(predictions.get(p["post_id"]) is None for p in posts):
            continue
        def claims(get, posts=posts):
            rows = [(p["post_date"], p["post_id"], f, v) for p in posts for f, v in get(p).items()]
            return dict(zip(PROFILE, _resolve(sorted(rows, key=lambda r: (r[0] is None, r[0] or 0, r[1])), None)[0]))
        gold = claims(lambda p: {f: p["label"][f]["value"] for f in FIELDS if p["label"].get(f)})
        pred = claims(lambda p: {} if predictions[p["post_id"]] == "blocked"
                      else {f: v for f, (v, _) in predictions[p["post_id"]].items()})
        expected = a.get("expected_profile")
        for f in PROFILE:
            agree["pred_vs_labels"][f"{f}/{'agree' if _same(f, pred[f], gold[f]) else 'differ'}"] += 1
            if expected is not None:
                e = expected.get(f)
                agree["labels_vs_expected"][f"{f}/{'agree' if _same(f, gold[f], e) else 'differ'}"] += 1
                agree["pred_vs_expected"][f"{f}/{'agree' if _same(f, pred[f], e) else 'differ'}"] += 1
    return {k: dict(sorted(v.items())) for k, v in agree.items()}


def _same(field: str, a, b) -> bool:
    """Profile values agree, with places compared as key() compares claims."""
    if a is None or b is None:
        return a is None and b is None
    if field == "age":
        return float(a) == float(b)
    if field == "location":
        parts = lambda v: [x.strip() for x in str(v).split(" / ")]
        a, b = parts(a), parts(b)
        return len(a) == len(b) and all(key(f, x) == key(f, y) for f, x, y in zip(("country", "state"), a, b))
    if field == "city":
        return key("city", str(a)) == key("city", str(b))
    return _plain(str(a)) == _plain(str(b))


def load(testset: Path, split: str) -> tuple[list[dict], list[dict]]:
    def read(name):
        path = testset / name
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] \
            if path.exists() else []
    keep = lambda r: split == "all" or r["split"] == split
    return [it for it in read("testset.jsonl") if keep(it)], [a for a in read("authors.jsonl") if keep(a)]


def predict(items: list[dict]) -> dict[str, dict | str | None]:
    """read_post on each item, with the extractor's parallelism, retries and failure handling."""
    predictions = {}
    for post_id, claims in extractor._in_parallel(extractor.get_client(), ((it["post_id"], it["text"]) for it in items),
                                                  extractor.read_post):
        predictions[post_id] = "blocked" if claims is extractor.BLOCKED else claims
    return predictions


def evaluate(testset: Path, split: str, tag: str, *, dry_run: bool = False) -> dict:
    items, authors = load(testset, split)
    items = [it for it in items if it["label"] is not None]
    prompt = extractor.POST_DEMOGRAPHICS_PROMPT
    tokens = sum(len(prompt) + len(it["text"]) for it in items) // 4
    plan = {"split": split, "labeled_items": len(items), "calls": len(items), "approx_input_tokens": tokens,
            "model": extractor.MODEL_FAST, "provider": extractor.LLM_PROVIDER,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()[:12], "prompt_tokens": len(prompt) // 4}
    if dry_run or not items:
        return plan
    predictions = predict(items)
    with open(testset / f"predictions_{tag}.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps({"post_id": post_id, "claims": claims}, ensure_ascii=False) + "\n" for post_id, claims in predictions.items())
    report = {**plan, "tag": tag, "code_commit": extractor.get_git_commit(), "git_dirty": extractor.git_is_dirty(),
              "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
              **score(items, predictions), "profiles": score_profiles(items, authors, predictions)}
    (testset / f"report_{tag}.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sample", help="Draw the unlabeled set from a scraped Reddit database")
    s.add_argument("--db", required=True, type=Path)
    s.add_argument("--out", required=True, type=Path, help="Directory outside Git, such as data/demographics_testset")
    s.add_argument("--seed", type=int, default=207)
    s.add_argument("--pool", type=int, default=200_000, help="Rows drawn before strata are taken")
    s.add_argument("--random", type=int, default=200)
    s.add_argument("--keyword", type=int, default=250)
    s.add_argument("--other-person", type=int, default=75)
    s.add_argument("--authors", type=int, default=25)
    s.add_argument("--max-author-posts", type=int, default=8)
    t = sub.add_parser("stats", help="Item and label counts by stratum, field and split")
    t.add_argument("--testset", required=True, type=Path)
    e = sub.add_parser("evaluate", help="Run read_post on the labeled items and score its claims (paid)")
    e.add_argument("--testset", required=True, type=Path)
    e.add_argument("--split", choices=("dev", "test", "all"), required=True)
    e.add_argument("--tag", default="baseline", help="Names predictions_<tag>.jsonl and report_<tag>.json")
    e.add_argument("--prompt-file", type=Path, help="Evaluate this per-post prompt instead of the merged one")
    e.add_argument("--dry-run", action="store_true", help="Print the calls and approximate tokens, send nothing")
    a = ap.parse_args()
    if a.command == "sample":
        result = sample(a.db, a.out, seed=a.seed, pool=a.pool, n_random=a.random, n_keyword=a.keyword,
                        n_other=a.other_person, n_authors=a.authors, max_author_posts=a.max_author_posts)
    elif a.command == "stats":
        result = counts(load(a.testset, "all")[0])
    else:
        if a.prompt_file:
            extractor.POST_DEMOGRAPHICS_PROMPT = a.prompt_file.read_text(encoding="utf-8")  # read_post reads it
        result = evaluate(a.testset, a.split, a.tag, dry_run=a.dry_run)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
