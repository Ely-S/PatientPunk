#!/usr/bin/env python3
"""Build the evaluation fixture: rebuild existing records' text and sample new ones.

Deterministic (``--seed``), so the set can be regrown or extended without
hand-curation drift. No API calls -- ``label_fixture.py`` fills in `gold` for the
records this script adds.

Two invariants this script exists to enforce:

1. ``texts`` is exactly what the production pipeline hands the extractor
   (``collect_texts_from_post(post, include_comments=False)``). The previous
   fixture stored title+body+comments while its labels came from a title+body-only
   run, which made the model look like it was hallucinating 30 values it had
   simply read out of other people's comments.
2. Sampling is *stratified by extraction density*, not uniform. 41% of the corpus
   extracts to a completely empty row; a uniform sample would spend most of its
   labeling budget on posts that score trivially and measure nothing.

Usage:
    python build_fixture.py --seed 42 --n 30 --out fixtures/eval_50.json
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from patientpunk._utils import collect_texts_from_post

ROOT = Path(__file__).parent
REPO_ROOT = ROOT.parents[1]

# Mirrors evaluate._META: columns that are run metadata, not extracted variables.
META_COLUMNS = {
    "author_hash", "source", "source_type", "post_id", "text_count",
    "schema_id", "extraction_method", "extracted_at",
}

# (name, minimum non-empty fields, how many to sample). The `empty` stratum is
# the only way to measure false positives on posts with nothing to extract, so
# it stays in the set even though such posts are boring to label.
STRATA = [
    ("high", 8, 12),
    ("medium", 4, 10),
    ("low", 1, 5),
    ("empty", 0, 3),
]

# No single subreddit may exceed this share of a stratum. Without it the sample
# is ~55% r/covidlonghaulers, matching the corpus but not the range of writing
# styles the prompt has to survive.
MAX_SUBREDDIT_SHARE = 0.5


def post_texts(post: dict) -> list[str]:
    """The text segments production would extract from this post."""
    return [
        t.strip()
        for t in collect_texts_from_post(post, include_comments=False)
        if t and t.strip() not in ("[removed]", "[deleted]")
    ]


def extracted_fields(row: dict) -> dict[str, str]:
    """The non-empty extracted variables from a records.csv row."""
    return {k: v for k, v in row.items() if k not in META_COLUMNS and v.strip()}


def stratum_of(n_fields: int) -> str:
    for name, minimum, _ in STRATA:
        if n_fields >= minimum:
            return name
    return "empty"


def sample_stratum(candidates: list[dict], n: int, rng: random.Random) -> list[dict]:
    """Pick *n* records, capping any one subreddit's share of the result."""
    pool = sorted(candidates, key=lambda r: r["post_id"])  # deterministic base order
    rng.shuffle(pool)
    cap = max(1, int(n * MAX_SUBREDDIT_SHARE))
    chosen: list[dict] = []
    seen: Counter = Counter()
    for rec in pool:
        if len(chosen) == n:
            break
        if seen[rec["subreddit"]] < cap:
            chosen.append(rec)
            seen[rec["subreddit"]] += 1
    # Cap can starve the sample when one subreddit dominates; backfill in order.
    if len(chosen) < n:
        taken = {r["post_id"] for r in chosen}
        chosen += [r for r in pool if r["post_id"] not in taken][: n - len(chosen)]
    return chosen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", type=Path, default=ROOT / "fixtures" / "spotcheck_20.json",
                        help="Existing fixture whose records are carried forward.")
    parser.add_argument("--records", type=Path, default=REPO_ROOT / "output_deepseek_10k" / "records.csv",
                        help="Extraction run used for density strata and baseline_extracted.")
    parser.add_argument("--corpus", type=Path, default=REPO_ROOT / "output_deepseek_10k" / "subreddit_posts.json",
                        help="Source posts for the run above.")
    parser.add_argument("--n", type=int, default=30, help="How many new records to add.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=ROOT / "fixtures" / "eval_50.json")
    args = parser.parse_args()

    base = json.loads(args.base.read_text())
    posts = {p["post_id"]: p for p in json.loads(args.corpus.read_text())}
    rows = {r["post_id"]: r for r in csv.DictReader(args.records.open())}

    existing_ids = {r["post_id"] for r in base["records"]}

    # Carry the base records forward, tagging where their gold came from so a
    # later scorer can separate hand-checked cells from model-adjudicated ones.
    out_records = []
    for rec in base["records"]:
        out_records.append({
            **rec,
            "gold_source": {f: "spotcheck" for f in rec["gold"]},
            "stratum": stratum_of(len(extracted_fields(rows[rec["post_id"]]))),
        })

    by_stratum: dict[str, list[dict]] = defaultdict(list)
    for post_id, row in rows.items():
        if post_id in existing_ids:
            continue
        post = posts.get(post_id)
        if post is None:
            continue
        texts = post_texts(post)
        if not texts:
            continue
        fields = extracted_fields(row)
        by_stratum[stratum_of(len(fields))].append({
            "post_id": post_id,
            "subreddit": post.get("subreddit", ""),
            "texts": texts,
            "baseline_extracted": fields,
        })

    rng = random.Random(args.seed)
    scaling = args.n / sum(n for _, _, n in STRATA)
    for name, _, target in STRATA:
        want = round(target * scaling)
        picked = sample_stratum(by_stratum[name], want, rng)
        print(f"{name:>7}: {len(picked)}/{want} from {len(by_stratum[name])} candidates")
        for rec in picked:
            out_records.append({
                "post_id": rec["post_id"],
                "subreddit": rec["subreddit"],
                "texts": rec["texts"],
                "baseline_extracted": rec["baseline_extracted"],
                "gold": {},          # filled by label_fixture.py
                "gold_source": {},
                "stratum": name,
            })

    fixture = {
        "_description": (
            f"{len(out_records)}-record evaluation set for the LLM extraction prompt "
            "(patientpunk.llm_extract.build_system_prompt). `texts` holds the post's "
            "title/body segments exactly as production collects them "
            "(collect_texts_from_post(post, include_comments=False)); feed them to "
            "build_user_message(texts), never pre-joined. `baseline_extracted` is what "
            f"the run at {args.records.parent.name} produced for that post. `gold` is the "
            "label to score against and `gold_source` records how each field's label was "
            "established -- see README.md, and never read a score without reading it."
        ),
        "schema": base["schema"],
        "source_corpus": base["source_corpus"],
        "source_records": str(args.records.relative_to(REPO_ROOT)),
        "seed": args.seed,
        "strata": {name: sum(1 for r in out_records if r["stratum"] == name)
                   for name, _, _ in STRATA},
        "records": out_records,
    }
    args.out.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(out_records)} records -> {args.out.relative_to(ROOT)}")
    print(f"strata: {fixture['strata']}")
    print(f"unlabeled (need label_fixture.py): {sum(1 for r in out_records if not r['gold'])}")


if __name__ == "__main__":
    main()
