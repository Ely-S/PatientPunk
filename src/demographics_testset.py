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

``curate`` and ``add-curated`` add the hand-picked ``curated`` stratum (cases in
src/demographics_testset_cases.json); tests/fixtures/demographics_synthetic.jsonl holds the
``synthetic`` stratum, written posts with no patient text, which ``evaluate`` always includes.
"""
import argparse
import hashlib
import json
import math
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
from resolve_demographics import _plain_place as _plain
from resolve_demographics import _resolve, canonical_place, normalize_sex, stated_age

FIELDS = extractor.CLAIM_FIELDS
PROFILE = ("age_bucket", "age", "sex", "sex_stated", "location", "city", "ever_minor")  # _resolve's order
TEST_SHARE = 0.4  # of authors, by a hash of user_id, so the split never depends on what was sampled
CASES = Path(__file__).with_name("demographics_testset_cases.json")
SYNTHETIC = Path(__file__).parents[1] / "tests" / "fixtures" / "demographics_synthetic.jsonl"
EXTRA_STRATA = {"curated", "synthetic"}  # chosen for what they contain, so left out of the pooled metrics
# The pipeline's condition names once #229 is merged; until then, the name as written.
canonical_condition = getattr(extractor, "canonical_condition", lambda name: name.casefold().strip())

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


# The scrape's table and columns for each kind of item.
_SOURCE = {"post": ("posts", "id, subreddit, created_utc, title, selftext, author"),
           "comment": ("comments", "id, subreddit, created_utc, body, author")}


def _fetch(conn, kind: str, rowids: list[int]) -> list[dict]:
    table, cols = _SOURCE[kind]
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
        sizes = {k: conn.execute(f"SELECT MAX(rowid) FROM {t}").fetchone()[0] for k, (t, _) in _SOURCE.items()}
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
        for kind, (table, cols) in _SOURCE.items():
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


def load_cases(path: Path = CASES) -> dict[str, dict]:
    return {k: v for k, v in json.loads(path.read_text()).items() if not k.startswith("_")}


def curate(db: Path, testset: Path, *, seed: int, factor: int = 3, cases_path: Path = CASES) -> dict:
    """candidates/<case>.jsonl: per split, ``factor`` times the case's quota of its regex matches not
    already in the set, in seeded order."""
    cases = load_cases(cases_path)
    regex = {c: re.compile(v["pattern"], re.IGNORECASE if v.get("ignore_case", True) else 0) for c, v in cases.items()}
    have = {it["post_id"] for it in load(testset, "all")[0]}
    found = defaultdict(list)
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        for kind, (table, cols) in _SOURCE.items():
            for row in conn.execute(f"SELECT {cols} FROM {table} WHERE author IS NOT NULL"):
                raw = f"{row['title'] or ''}\n{row['selftext'] or ''}" if kind == "post" else row["body"] or ""
                hits = {c: m.group() for c, r in regex.items() if (m := r.search(raw))}
                if hits and (it := _item(row, kind)) and it["post_id"] not in have:
                    for c, match in hits.items():
                        found[c].append({**it, "match": match})
    rng = random.Random(seed)
    out = testset / "candidates"
    out.mkdir(exist_ok=True)
    pools = {}
    for c, spec in cases.items():
        rows = sorted(found[c], key=lambda it: it["post_id"])
        rng.shuffle(rows)
        test = round(spec["n"] * TEST_SHARE)
        quota = {"dev": spec["n"] - test, "test": test}
        keep = [it for split in ("dev", "test") for it in [r for r in rows if r["split"] == split][:factor * quota[split]]]
        (out / f"{c}.jsonl").write_text("".join(json.dumps(it, ensure_ascii=False) + "\n" for it in keep))
        pools[c] = {"matches": len(rows), "candidates": len(keep), "quota": quota}
    summary = {"seed": seed, "factor": factor, "source_db": str(db), "cases": pools,
               "code_commit": extractor.get_git_commit()}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def add_curated(testset: Path, curation: Path) -> dict:
    """Append curation.jsonl's picks ({post_id, case, rationale, picked_by}) unlabeled, in the curated
    stratum; the rationale stays out of the labeler's sight."""
    picks = [json.loads(line) for line in curation.read_text().splitlines() if line.strip()]
    candidates = {c: {it["post_id"]: it for it in map(json.loads, (testset / "candidates" / f"{c}.jsonl").read_text().splitlines())}
                  for c in {p["case"] for p in picks}}
    items = [json.loads(line) for line in (testset / "testset.jsonl").read_text().splitlines()]
    have = {it["post_id"] for it in items}
    new: dict[str, dict] = {}
    for p in picks:
        if p["post_id"] not in candidates[p["case"]]:
            raise ValueError(f"{p['post_id']} is not a candidate for {p['case']}")
        if p["post_id"] in have:
            raise ValueError(f"{p['post_id']} is already in the set")
        it = {k: v for k, v in candidates[p["case"]][p["post_id"]].items() if k != "match"}
        new.setdefault(p["post_id"], {**it, "strata": ["curated"], "case": [], "label": None})["case"].append(p["case"])
    with open(testset / "testset.jsonl", "a", encoding="utf-8") as f:
        f.writelines(json.dumps(it, ensure_ascii=False) + "\n" for it in new.values())
    manifest_path = testset / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    summary = json.loads((testset / "candidates" / "summary.json").read_text())
    picked = Counter(f"{c}/{it['split']}" for it in new.values() for c in it["case"])
    manifest["curated"] = {**summary, "picked": dict(sorted(picked.items())), "items": len(new),
                           "picked_by": sorted({p["picked_by"] for p in picks}),
                           "selection": "Each case's regex matches in seeded order (candidates/), quota per split "
                                        "by split_of; picks and a rationale for each in curation.jsonl."}
    manifest["counts"] = counts(items + list(new.values()))
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest["curated"]


def counts(items: list[dict]) -> dict:
    """Items per stratum and split, labeled values per field and split, and labeled values whose
    evidence is not an exact quote from the item's text (which should be none)."""
    c = {"items": Counter(), "labeled": Counter(), "fields": Counter(), "others": Counter(),
         "case_mix": Counter(), "evidence_not_in_text": Counter()}
    cases = load_cases()
    for it in items:
        for s in it["strata"] + [f"case:{k}" for k in it.get("case", [])]:
            c["items"][f"{s}/{it['split']}"] += 1
        if (label := it.get("label")) is not None:
            c["labeled"][it["split"]] += 1
            c["fields"].update(f"{f}/{it['split']}" for f in (*FIELDS, "conditions") if label.get(f))
            c["others"].update(f"{f}/{it['split']}" for f, v in (label.get("others") or {}).items() if v)
            c["evidence_not_in_text"].update(
                it["post_id"] for f in FIELDS if label.get(f) and label[f]["evidence"] not in it["text"])
            for k in it.get("case", []):
                c["case_mix"][f"{k}/{it['split']}/{'positive' if is_positive(it, cases[k]) else 'near_miss'}"] += 1
    return {k: dict(sorted(v.items())) for k, v in c.items()}


def is_positive(it: dict, case: dict) -> bool:
    """The label states what the case targets (for conditions, one of its ``severities`` if it lists them)."""
    if "severities" in case:
        return any(c["severity"] in case["severities"] for c in it["label"].get("conditions") or [])
    return any(it["label"].get(f) for f in case["fields"])


# ── Matching ─────────────────────────────────────────────────────────────────

# Spellings of one identity, which normalize_sex leaves alone by design (#214: a trans answer maps to
# no binary sex). Evaluation only: "MtF" and "trans woman" are one answer. Bare "trans" says neither.
_IDENTITY = {
    **dict.fromkeys(("mtf", "m2f", "tf", "transfem", "trans fem", "transfeminine", "trans feminine", "trans woman",
                     "transwoman", "trans female", "trans girl"), "trans woman"),
    **dict.fromkeys(("ftm", "f2m", "tm", "transman", "trans masc", "transmasc", "transmasculine", "trans masculine",
                     "trans male", "trans man", "trans guy"), "trans man"),
    **dict.fromkeys(("genderfluid", "gender fluid"), "genderfluid"),
    **dict.fromkeys(("afab", "assigned female at birth", "born female", "born a female"), "afab"),
    **dict.fromkeys(("amab", "assigned male at birth", "born male", "born a male", "born in a male body"), "amab"),
    "enby": "non-binary",
}


# Metro areas named without their city, once "the", "greater" and "area" are dropped.
_METRO = dict.fromkeys(("bay", "sf bay", "san francisco bay", "sf"), "san francisco") | {"nyc": "new york",
                                                                                       "new york city": "new york"}


def key(field: str, value: str) -> object:
    """A form of the value in which two ways of writing the same answer are equal."""
    if field == "age":
        stated = stated_age(value)
        return stated[0] if stated else _plain(value)
    if field == "sex":  # each identity by the pipeline's rule ("guy" is male), else by _IDENTITY, else its words
        parts = (re.sub(r"^\d{1,2}\s*", "", _plain(v)) for v in re.split(r"[|/,;]", value) if v.strip())
        return frozenset(normalize_sex(v) or _IDENTITY.get(re.sub(r"[\s-]+", " ", v), v) for v in parts)
    if field in ("country", "state"):
        return _plain(canonical_place(field, value))  # the pipeline's spelling: "US" is United States
    city = _plain(value).split(",")[0].strip()  # "Austin, TX" is Austin
    city = re.sub(r"\s+(?:metro(?:politan)?\s+)?area$|\s+metro$", "", re.sub(r"^(?:the\s+)?(?:greater\s+)?", "", city))
    return _METRO.get(city, city)  # a metro area is its city: "the Boston area" is Boston


def _overlaps(a: str, b: str) -> bool:
    a, b = a.casefold().strip(), b.casefold().strip()
    return bool(a and b) and (a in b or b in a)


# ── Evaluation ───────────────────────────────────────────────────────────────

def score(items: list[dict], predictions: dict[str, dict | None], conditions: dict | None = None) -> dict:
    """Per-field precision, recall, wrong-person errors and evidence checks.

    ``predictions`` maps post_id to {field: (value, evidence)}, "blocked", or None (the read failed).
    A failed read is left out of the scores; a blocked one counts as no claims, so it shows in recall.
    A wrong value is both a false positive and a false negative. A false positive whose value matches
    one the label lists under ``others`` (someone else's, or a past age) is a wrong-person error.

    ``conditions`` maps post_id to read_post's conditions [(name, type, severity, evidence)], or None.
    Items whose label has a ``conditions`` list are scored on them: names matched through
    canonical_condition, and severity agreement over the matched names.
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
    if conditions is not None and (scored := score_conditions(items, predictions, conditions)):
        report["conditions"] = scored
    for f, c in m.items():
        tp, fp, fn = c["tp"], c["fp"], c["fn"]
        for k in ("tp", "fp", "fn", "wrong_person", "claims"):
            c.setdefault(k, 0)  # zeros shown
        report["fields"][f] = {**c, **rates(tp, fp, fn)}
    return report


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """Wilson score 95% interval for k successes in n trials, or None when n is 0."""
    if not n:
        return None
    p, d = k / n, 1 + z * z / n
    centre, half = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(centre - half, 3), round(centre + half, 3)]


def rates(tp: int, fp: int, fn: int) -> dict:
    """Precision and recall, each with its denominator and Wilson 95% interval."""
    return {"precision": round(tp / (tp + fp), 3) if tp + fp else None, "precision_n": tp + fp,
            "precision_ci": wilson(tp, tp + fp),
            "recall": round(tp / (tp + fn), 3) if tp + fn else None, "recall_n": tp + fn,
            "recall_ci": wilson(tp, tp + fn)}


def score_conditions(items: list[dict], predictions: dict, conditions: dict) -> dict | None:
    c = Counter()
    for it in items:
        gold = (it["label"] or {}).get("conditions")
        pred = predictions.get(it["post_id"])
        if gold is None or pred is None or (pred != "blocked" and conditions.get(it["post_id"]) is None):
            continue  # not labeled for conditions, or the read failed
        c["posts"] += 1
        g = {canonical_condition(x["name"]): x["severity"] for x in gold}
        p = {} if pred == "blocked" else {canonical_condition(n): sev for n, _, sev, _ in conditions[it["post_id"]]}
        c["tp"] += len(g.keys() & p.keys())
        c["fp"] += len(p.keys() - g.keys())
        c["fn"] += len(g.keys() - p.keys())
        c["severity_agree"] += sum(g[n] == p[n] for n in g.keys() & p.keys())
    if not c["posts"]:
        return None
    tp, fp, fn = c["tp"], c["fp"], c["fn"]
    return {**{k: c[k] for k in ("posts", "tp", "fp", "fn", "severity_agree")}, **rates(tp, fp, fn),
            "severity_agreement": round(c["severity_agree"] / tp, 3) if tp else None,
            "severity_agreement_ci": wilson(c["severity_agree"], tp)}


def score_by(key: str, items: list[dict], predictions: dict, conditions: dict | None = None) -> dict:
    """score() for each value of an item's ``key`` list ("strata" or "case") on its own: recall on the
    random stratum, wrong-person errors on other_person. An item with two values counts in both."""
    values = sorted({v for it in items for v in it.get(key, [])})
    report = {v: score([it for it in items if v in it.get(key, [])], predictions, conditions) for v in values}
    if key == "case":  # near misses can only add false positives: show the mix beside the metrics
        cases = load_cases()
        for v in values:
            mix = Counter(is_positive(it, cases[v]) for it in items if v in it.get(key, []))
            report[v]["mix"] = {"positives": mix[True], "near_miss": mix[False]}
    return report


def kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    """Cohen's kappa for two labelers' yes/no calls; None when chance agreement is total."""
    n = len(pairs)
    if not n:
        return None
    observed = sum(a == b for a, b in pairs) / n
    pa, pb = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    chance = pa * pb + (1 - pa) * (1 - pb)
    return None if chance == 1 else round((observed - chance) / (1 - chance), 3)


def agreement(items: list[dict], second: dict[str, dict]) -> tuple[dict, list[dict]]:
    """Per field, the share of items where a second label agrees with the first (both empty, or equal by
    key(); conditions as sets of canonical names) and Cohen's kappa on whether it's stated; and the
    disagreements."""
    report, diffs = {}, []
    for f in (*FIELDS, "conditions"):
        pairs, agree = [], 0
        for it in items:
            a, b = it["label"], second.get(it["post_id"])
            if b is None or f not in b or (f == "conditions" and a.get(f) is None):
                continue  # a field the second labeling didn't cover isn't compared
            if f == "conditions":
                va, vb = ({canonical_condition(x["name"]) for x in lab[f]} for lab in (a, b))
                same = va == vb
            else:
                va, vb = (lab.get(f) and lab[f]["value"] for lab in (a, b))
                same = (not va and not vb) or bool(va and vb and key(f, va) == key(f, vb))
            pairs.append((bool(va), bool(vb)))
            agree += same
            if not same:
                diffs.append({"post_id": it["post_id"], "field": f, "first": a.get(f), "second": b.get(f)})
        report[f] = {"n": len(pairs), "agree": round(agree / len(pairs), 3) if pairs else None,
                     "agree_ci": wilson(agree, len(pairs)), "kappa_stated": kappa(pairs),
                     "stated_first": sum(x for x, _ in pairs), "stated_second": sum(y for _, y in pairs)}
    return report, diffs


def write_agreement(testset: Path, second_path: Path) -> dict:
    """agreement() with a second label file, written to second_label_agreement_<its folder>.json and,
    with the text, review/second_label_disagreements_<its folder>.md."""
    second = {r["post_id"]: r["label"] for r in map(json.loads, second_path.read_text().splitlines()) if r}
    items = [it for it in load(testset, "all")[0] if it["post_id"] in second]
    report, diffs = agreement(items, second)
    report = {"items": len(items), "second_labels": str(second_path), "fields": report}
    name = second_path.parent.name
    (testset / f"second_label_agreement_{name}.json").write_text(json.dumps(report, indent=2) + "\n")
    text = {it["post_id"]: it["text"] for it in items}
    show = lambda v: "—" if not v else (", ".join(sorted({x["name"] for x in v})) if isinstance(v, list)
                                        else f"{v['value']} (`{v['evidence']}`)")
    lines = ["# Second-label disagreements (#207)", "", (f"{len(diffs)} disagreements on {len(items)} items. First: the "
             "existing label. Second: an independent label. Say which is right, or neither."), ""]
    for d in sorted(diffs, key=lambda d: (d["field"], d["post_id"])):
        lines += [f"## {d['post_id']}: {d['field']}", "", "> " + text[d["post_id"]].replace("\n", "\n> "), "",
                  f"- first: {show(d['first'])}", f"- second: {show(d['second'])}", "- [ ] first  - [ ] second  - [ ] neither:", ""]
    (testset / "review").mkdir(exist_ok=True)
    (testset / "review" / f"second_label_disagreements_{name}.md").write_text("\n".join(lines))
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
            if expected is not None and f in expected:  # a field the labeler didn't write isn't scored
                e = expected[f]
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
    excluded = excluded_ids(testset)
    keep = lambda r: split == "all" or r["split"] == split
    items = [it for it in read("testset.jsonl") if keep(it) and it["post_id"] not in excluded]
    authors = [{**a, "post_ids": [p for p in a["post_ids"] if p not in excluded]} for a in read("authors.jsonl") if keep(a)]
    return items, authors


def excluded_ids(testset: Path) -> set[str]:
    """post_ids in manifest.json's ``excluded`` list ({post_id, reason, decided_by})."""
    manifest = testset / "manifest.json"
    return {r["post_id"] for r in json.loads(manifest.read_text()).get("excluded", [])} if manifest.exists() else set()


def load_synthetic() -> list[dict]:
    return [json.loads(line) for line in SYNTHETIC.read_text(encoding="utf-8").splitlines() if line.strip()]


def predict(items: list[dict]) -> tuple[dict[str, dict | str | None], dict[str, list | None] | None]:
    """read_post on each item, with the extractor's parallelism, retries and failure handling: claims
    per post, and conditions per post once read_post returns (claims, conditions) (#229), else None."""
    predictions, conditions = {}, {}
    for post_id, result in extractor._in_parallel(extractor.get_client(), ((it["post_id"], it["text"]) for it in items),
                                                  extractor.read_post):
        # read_post returns (claims, conditions) once #229 merges; then drop this check and unpack it.
        if isinstance(result, tuple):
            result, conditions[post_id] = result
        predictions[post_id] = "blocked" if result is extractor.BLOCKED else result
    return predictions, conditions or None


def evaluate(testset: Path, split: str, tag: str, *, dry_run: bool = False) -> dict:
    items, authors = load(testset, split)
    items = [it for it in items + load_synthetic() if it["label"] is not None]
    prompt = extractor.POST_DEMOGRAPHICS_PROMPT
    tokens = sum(len(prompt) + len(it["text"]) for it in items) // 4
    plan = {"split": split, "labeled_items": len(items), "calls": len(items), "approx_input_tokens": tokens,
            "model": extractor.MODEL_FAST, "provider": extractor.LLM_PROVIDER,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()[:12], "prompt_tokens": len(prompt) // 4,
            # Which labels this was scored against: they change with every review, so compare reports only
            # when these agree.
            "testset_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest()[:16]
                               for name, path in (("testset.jsonl", testset / "testset.jsonl"),
                                                  ("authors.jsonl", testset / "authors.jsonl"),
                                                  ("synthetic", SYNTHETIC)) if path.exists()},
            "labels_by": dict(Counter(it.get("labeled_by") or "unknown" for it in items).most_common())}
    if dry_run or not items:
        return plan
    predictions, conditions = predict(items)
    with open(testset / f"predictions_{tag}.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps({"post_id": post_id, "claims": claims, "conditions": (conditions or {}).get(post_id)},
                                ensure_ascii=False) + "\n" for post_id, claims in predictions.items())
    pooled = [it for it in items if not set(it["strata"]) <= EXTRA_STRATA]
    report = {**plan, "tag": tag, "code_commit": extractor.get_git_commit(), "git_dirty": extractor.git_is_dirty(),
              "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
              **score(pooled, predictions, conditions), "by_stratum": score_by("strata", items, predictions, conditions),
              "by_case": score_by("case", items, predictions, conditions),
              "profiles": score_profiles(items, authors, predictions)}
    (testset / f"report_{tag}.json").write_text(json.dumps(report, indent=2) + "\n")
    if split in ("test", "all"):  # the test split is for final comparisons: keep a record of every look
        with open(testset / "test_runs.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({k: report[k] for k in ("tag", "created_at", "split", "prompt_sha256", "model",
                                                       "code_commit", "testset_sha256")}) + "\n")
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
    c = sub.add_parser("curate", help="Write each curated case's candidates from a scraped Reddit database")
    c.add_argument("--db", required=True, type=Path)
    c.add_argument("--testset", required=True, type=Path)
    c.add_argument("--seed", type=int, default=207)
    c.add_argument("--factor", type=int, default=3, help="Candidates per case, as a multiple of its quota")
    r = sub.add_parser("add-curated", help="Add the picks in curation.jsonl to testset.jsonl, unlabeled")
    r.add_argument("--testset", required=True, type=Path)
    r.add_argument("--curation", type=Path, help="Default: <testset>/curation.jsonl")
    g = sub.add_parser("agree", help="Agreement between the labels and a second, independent labeling")
    g.add_argument("--testset", required=True, type=Path)
    g.add_argument("--second", required=True, type=Path, help="JSON Lines of {post_id, label}")
    t = sub.add_parser("stats", help="Item and label counts by stratum, field and split")
    t.add_argument("--testset", required=True, type=Path)
    e = sub.add_parser("evaluate", help="Run read_post on the labeled items and score its claims (paid)")
    e.add_argument("--testset", required=True, type=Path)
    e.add_argument("--split", choices=("dev", "test", "all"), required=True,
                   help="Sampled and curated items in this split; the synthetic items are always included")
    e.add_argument("--tag", default="baseline", help="Names predictions_<tag>.jsonl and report_<tag>.json")
    e.add_argument("--prompt-file", type=Path, help="Evaluate this per-post prompt instead of the merged one. Give the rendered "
                   "text, not the f-string template in src/prompts/demographic_prompt.py")
    e.add_argument("--dry-run", action="store_true", help="Print the calls and approximate tokens, send nothing")
    a = ap.parse_args()
    if a.command == "sample":
        result = sample(a.db, a.out, seed=a.seed, pool=a.pool, n_random=a.random, n_keyword=a.keyword,
                        n_other=a.other_person, n_authors=a.authors, max_author_posts=a.max_author_posts)
    elif a.command == "curate":
        result = curate(a.db, a.testset, seed=a.seed, factor=a.factor)
    elif a.command == "add-curated":
        result = add_curated(a.testset, a.curation or a.testset / "curation.jsonl")
    elif a.command == "agree":
        result = write_agreement(a.testset, a.second)
    elif a.command == "stats":
        result = {**counts(load(a.testset, "all")[0]), "excluded": len(excluded_ids(a.testset))}
    else:
        if a.prompt_file:
            extractor.POST_DEMOGRAPHICS_PROMPT = a.prompt_file.read_text(encoding="utf-8")  # read_post reads it
        result = evaluate(a.testset, a.split, a.tag, dry_run=a.dry_run)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
